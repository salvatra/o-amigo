#!/usr/bin/env python3
"""User-local immutable releases, targeted KDE integration and private migration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amigo.settings import Settings
from amigo.migration import migrate

SOURCE=Path(__file__).resolve().parents[1]
CODE_DIRS=('amigo','qml')
CORE_FILES=('quickask/__init__.py','quickask/core.py','quickask/vault.py','LICENSE','THIRD_PARTY.md','SOURCE_REVISION')

def run(*args,check=True):
    result=subprocess.run([str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    if check and result.returncode:raise RuntimeError('Falhou '+str(args[0])+': '+result.stderr[:600])
    return result.stdout.strip()

def write(path,text,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write(text)
        os.chmod(name,mode);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

def copy_code(destination):
    for directory in CODE_DIRS:
        shutil.copytree(SOURCE/directory,destination/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in CORE_FILES:
        if not (SOURCE/name).is_file():continue
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,target)
    shutil.copytree(SOURCE/'kwin',destination/'kwin')
    shutil.copytree(SOURCE/'scripts',destination/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))

def source_revision():
    value=(SOURCE/'SOURCE_REVISION').read_text().strip() if (SOURCE/'SOURCE_REVISION').exists() else ''
    import re
    if re.fullmatch('[0-9a-f]{40}',value):return value
    result=subprocess.run(['git','-C',str(SOURCE),'rev-parse','HEAD'],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else None

def code_id():
    digest=hashlib.sha256()
    for directory in (*CODE_DIRS,'kwin','scripts','quickask'):
        for path in sorted((SOURCE/directory).rglob('*')):
            if path.is_file() and path.suffix in ('.py','.qml','.js','.json'):
                digest.update(str(path.relative_to(SOURCE)).encode());digest.update(path.read_bytes())
    return digest.hexdigest()[:16]

class Install:
    def __init__(self,home=None,activate=True):
        self.home=Path(home or Path.home());self.activate=activate
        self.data=Path(os.environ.get('XDG_DATA_HOME',self.home/'.local/share')) if home is None else self.home/'.local/share'
        self.config=Path(os.environ.get('XDG_CONFIG_HOME',self.home/'.config')) if home is None else self.home/'.config'
        self.root=self.data/'o-amigo';self.launcher=self.home/'.local/bin/o-amigo'
    def cfg(self,file,group,key,value=None):
        args=['kwriteconfig6','--file',self.config/file,'--group',group,'--key',key]
        run(*args,*(['--delete'] if value is None else [str(value)]))
    def readcfg(self,file,group,key):return run('kreadconfig6','--file',self.config/file,'--group',group,'--key',key)
    def release(self):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.root.chmod(0o700)
        version=code_id();releases=self.root/'releases';releases.mkdir(exist_ok=True)
        release=releases/version
        if not release.exists():
            stage=Path(tempfile.mkdtemp(prefix='.staging-',dir=releases))
            try:copy_code(stage);os.rename(stage,release)
            finally:
                if stage.exists():shutil.rmtree(stage)
        current=self.root/'current';previous=current.resolve() if current.is_symlink() else None
        if current.exists() and not current.is_symlink():raise RuntimeError('O destino current não é uma ligação gerida pelo instalador.')
        temporary=self.root/'.current-new';temporary.unlink(missing_ok=True);temporary.symlink_to(release);os.replace(temporary,current)
        if previous and previous!=release:
            backup=self.root/'previous';backup.unlink(missing_ok=True);backup.symlink_to(previous)
        return version
    def artifacts(self):
        current=self.root/'current'
        write(self.launcher,'#!/usr/bin/python -I\nimport sys\nsys.path.insert(0,'+repr(str(current))+')\nfrom amigo.app import main\nraise SystemExit(main())\n',0o700)
        desktop='[Desktop Entry]\nType=Application\nName=O Amigo\nComment=Assistente nativo com OpenRouter\nExec="'+str(self.launcher)+'" --show\nIcon=help-hint\nTerminal=false\nCategories=Utility;\nStartupNotify=false\nStartupWMClass=org.kde.oamigo\n'
        write(self.data/'applications/org.kde.oamigo.desktop',desktop)
        write(self.config/'autostart/org.kde.oamigo.desktop',desktop.replace('--show','--background')+'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n')
        write(self.data/'dbus-1/services/org.kde.OAmigo.service','[D-BUS Service]\nName=org.kde.OAmigo\nExec="'+str(self.launcher)+'" --background\n')
        destination=self.data/'kwin/scripts/o-amigo'
        if destination.exists():shutil.rmtree(destination)
        shutil.copytree(current/'kwin',destination)
        # Match only the popup; settings and browser remain ordinary decorated windows.
        order=self.readcfg('kwinrulesrc','General','Order')
        self.cfg('kwinrulesrc','General','Order',','.join([v for v in order.split(',') if v and v!='o-amigo-popup']+['o-amigo-popup']))
        values={'Description':'O Amigo — popup','wmclass':'org.kde.oamigo','wmclassmatch':1,'wmclasscomplete':'false',
                'title':'O Amigo','titlematch':1,'desktops':'','desktopsrule':2,'skiptaskbar':'true','skiptaskbarrule':2,
                'skippager':'true','skippagerrule':2,'skipswitcher':'true','skipswitcherrule':2,'above':'true','aboverule':2,
                'acceptfocus':'true','acceptfocusrule':2}
        for key,value in values.items():self.cfg('kwinrulesrc','o-amigo-popup',key,value)
        self.cfg('kwinrc','Plugins','o-amigoEnabled','true')
    def has_owner(self):return run('qdbus6','org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus.NameHasOwner','org.kde.OAmigo')=='true'
    def start(self):
        if self.has_owner():
            # Hide first so QML flushes its debounce timer. Keep transient drafts
            # outside SQLite: upgrades must not create empty history entries.
            run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.Hide')
            snapshot=json.loads(run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.Snapshot'))
            if snapshot.get('busy'):raise RuntimeError('Uma tarefa começou durante a instalação; não foi interrompida.')
            write(self.root/'composer-handoff.json',json.dumps({k:snapshot[k] for k in ('conversation','draft')},ensure_ascii=False))
            run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.Quit',check=False)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if not self.has_owner():break
            time.sleep(.05)
        else:raise RuntimeError('A instância anterior ainda está a terminar; a instalação não a matou.')
        subprocess.Popen([str(self.launcher),'--background'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            state=run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.State',check=False)
            if state:break
            time.sleep(.1)
        else:raise RuntimeError('O serviço novo não confirmou o arranque.')
        run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','o-amigo',check=False)
        run('qdbus6','org.kde.KWin','/KWin','org.kde.KWin.reconfigure')
        if run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.isScriptLoaded','o-amigo')!='true':
            run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',self.data/'kwin/scripts/o-amigo/contents/code/main.js','o-amigo')
        run('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start')
        from PyQt6.QtCore import QCoreApplication
        from amigo.integration import set_shortcut
        app=QCoreApplication.instance() or QCoreApplication([])
        set_shortcut(Settings(self.config/'o-amigo/settings.json').value['shortcut'])
        run('kbuildsycoca6','--noincremental',check=False)
        return json.loads(state)
    def install(self,profile=None,migration=False):
        if self.activate:
            state=run('qdbus6','org.kde.OAmigo','/OAmigo','org.kde.OAmigo.State',check=False) if self.has_owner() else ''
            if state and json.loads(state).get('busy'):raise RuntimeError('Termina a tarefa ativa antes de atualizar a aplicação.')
        settings=Settings(self.config/'o-amigo/settings.json')
        if profile:settings.save(json.loads(Path(profile).read_text()))
        elif not settings.path.exists():settings.save(settings.value)
        if migration:migrate(self.data/'quick-ask',self.root,with_key=self.activate)
        version=self.release();self.artifacts()
        state=self.start() if self.activate else {'activation':'skipped'}
        write(self.root/'installation.json',json.dumps({'version':version,'commit':source_revision(),'source':str(SOURCE),'installed':True,'activated':self.activate},indent=2))
        return {'version':version,'service':state,'legacy_preserved':True}

def main():
    os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,help='Disposable install root; requires --no-activate')
    parser.add_argument('--no-activate',action='store_true');parser.add_argument('--profile',type=Path)
    parser.add_argument('--migrate-quick-ask',action='store_true')
    args=parser.parse_args()
    if args.home and not args.no_activate:parser.error('--home requires --no-activate')
    print(json.dumps(Install(args.home,not args.no_activate).install(args.profile,args.migrate_quick_ask),ensure_ascii=False))

if __name__=='__main__':main()
