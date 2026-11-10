"""One-time private migration. Never copies a credential into a filesystem file."""
from contextlib import closing
import json
from pathlib import Path
import os
import sqlite3
import subprocess
import tempfile

ATTRS=['provider','openrouter']

def secret(action,application,value=None):
    args=['/usr/bin/secret-tool',action]
    if action=='store':args+=['--label=O Amigo — OpenRouter']
    args+=['application',application,*ATTRS]
    result=subprocess.run(args,input=value,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=35)
    return result.returncode==0,result.stdout.rstrip(b'\n') if action=='lookup' else b''

def migrate_history(source,target):
    source=Path(source);target=Path(target)
    if not source.is_file():return {'history':'absent'}
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if target.exists():raise RuntimeError('O destino já contém histórico; a migração recusa substituí-lo.')
    fd,name=tempfile.mkstemp(dir=target.parent);os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(name)) as new:
            old.backup(new)
            counts={table:new.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('conversations','messages')}
            active=new.execute("SELECT value FROM settings WHERE key='active'").fetchone()
            valid=new.execute("SELECT value FROM settings WHERE key='validated'").fetchone()
            new.execute("INSERT OR REPLACE INTO settings VALUES ('key_validated',?)",('true' if valid and valid[0]=='yes' else 'false',))
            new.commit()
            if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('A cópia do histórico não passou a verificação SQLite.')
        # Exclusive link prevents a concurrent first start from being overwritten.
        os.link(name,target);target.chmod(0o600)
        return {'history':'copied','counts':counts,'active_preserved':bool(active),'legacy_validated':bool(valid and valid[0]=='yes')}
    finally:Path(name).unlink(missing_ok=True)

def migrate(source_root,target_root,with_key=True):
    source_root=Path(source_root);target_root=Path(target_root);marker=target_root/'migration.json'
    target_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if marker.exists():result=json.loads(marker.read_text())
    else:
        result=migrate_history(source_root/'history.sqlite3',target_root/'history.sqlite3');result['key']='pending'
        marker.write_text(json.dumps(result,indent=2));marker.chmod(0o600)
    if result.get('key') not in ('pending','not-requested'):return result
    result['key']='not-requested'
    if with_key:
        existing,newkey=secret('lookup','o-amigo')
        old,oldkey=secret('lookup','quick-ask')
        if existing and newkey:
            result['key']='existing'
            if oldkey and oldkey!=newkey and (target_root/'history.sqlite3').exists():
                with closing(sqlite3.connect(target_root/'history.sqlite3')) as db:
                    db.execute("INSERT OR REPLACE INTO settings VALUES ('key_validated','false')");db.commit()
        elif old and oldkey:
            saved,_=secret('store','o-amigo',oldkey)
            if not saved:raise RuntimeError('O histórico foi copiado, mas o KWallet não confirmou a cópia da chave. A instalação antiga mantém-se disponível.')
            ok,verified=secret('lookup','o-amigo')
            if not ok or verified!=oldkey:raise RuntimeError('O KWallet não confirmou a chave migrada.')
            result['key']='copied-and-verified'
        else:result['key']='absent'
        oldkey=newkey=b''
    marker.write_text(json.dumps(result,indent=2));marker.chmod(0o600)
    return result
