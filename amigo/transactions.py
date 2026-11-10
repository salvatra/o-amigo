"""Trusted file broker: atomic commits, durable recovery, no generated code.

External workers produce staged files only. This module is the sole committer
for user data. Pending operations after a crash are never automatically replayed.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import threading
import time
import uuid
import ctypes
from .policy import Denied

class Conflict(RuntimeError): pass
class RecoveryUnavailable(RuntimeError): pass
class Cancelled(RuntimeError): pass


def digest(file):
    file.seek(0)
    return hashlib.file_digest(file, 'sha256').hexdigest()


class Transactions:
    def __init__(self, directory, policy, quota=2*1024**3, retention_days=7):
        self.root=Path(directory).resolve()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root.chmod(0o700)
        self.policy=policy
        self.policy.protected=(*self.policy.protected,self.root)
        self.quota=quota;self.retention=retention_days*86400
        self.lock=threading.RLock()
        self.db=sqlite3.connect(self.root/'operations.sqlite3',check_same_thread=False)
        (self.root/'operations.sqlite3').chmod(0o600)
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, created REAL, status TEXT, manifest TEXT)')
        self.db.execute("UPDATE operations SET status='interrupted' WHERE status='prepared'")
        self.db.commit()

    @contextmanager
    def parent(self,path):
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
            yield fd
        finally:os.close(fd)

    def current(self,path):
        try:
            with self.policy.open_read(str(path)) as source:
                info=os.fstat(source.fileno())
                return {'sha256':digest(source),'mode':stat.S_IMODE(info.st_mode)&0o777,
                        'atime_ns':info.st_atime_ns,'mtime_ns':info.st_mtime_ns,'size':info.st_size}
        except FileNotFoundError:return None

    def prune(self):
        for row in self.db.execute("SELECT * FROM operations WHERE created < ? AND status IN ('committed','undone','failed')",(time.time()-self.retention,)).fetchall():
            shutil.rmtree(self.root/row['id'],ignore_errors=True)
            self.db.execute("UPDATE operations SET status='expired' WHERE id=?",(row['id'],))
        self.db.commit()

    def checkpoint(self,changes):
        """changes: [{path, staged|None, times|None}]. None staged means remove.
        Timestamps-only changes set times and do not remove the file.
        """
        self.prune()
        identifier=uuid.uuid4().hex
        folder=self.root/identifier;folder.mkdir(mode=0o700)
        manifest=[];seen=set()
        try:
            used=sum(p.stat().st_size for p in self.root.glob('*/*.bak'))
            for index,change in enumerate(changes):
                path=self.policy.path(str(change['path']),exists=False)
                if path in seen:raise ValueError('Duplicate destination')
                seen.add(path)
                before=self.current(path)
                if 'expected' in change and (before or {}).get('sha256') != change['expected']:
                    raise Conflict('File changed while preparing operation: '+str(path))
                if before and used+before['size']>self.quota:
                    raise RecoveryUnavailable('Recovery quota exceeded; no original was changed')
                backup=folder/f'{index}.bak'
                if before:
                    with self.policy.open_read(str(path)) as source,backup.open('xb') as dest:
                        os.chmod(backup,0o600)
                        try:fcntl.ioctl(dest.fileno(),0x40049409,source.fileno()) # FICLONE
                        except OSError:shutil.copyfileobj(source,dest,1024*1024)
                        dest.flush();os.fsync(dest.fileno())
                    with backup.open('rb') as source:
                        if digest(source)!=before['sha256']:raise Conflict('Source changed during backup')
                    used+=before['size']
                staged=change.get('staged')
                if staged:
                    with Path(staged).open('rb') as source:after=digest(source)
                else:after=before['sha256'] if change.get('times') and before else None
                manifest.append({'path':str(path),'before':before,'after':after,'backup':backup.name if before else None,
                                 'times':change.get('times')})
            self.db.execute('INSERT INTO operations VALUES (?,?,?,?)',(identifier,time.time(),'prepared',json.dumps(manifest)))
            self.db.commit()
            return identifier,manifest
        except BaseException:
            shutil.rmtree(folder,ignore_errors=True)
            raise

    def same(self,path,expected):
        current=self.current(path)
        return (current or {}).get('sha256')==(expected or {}).get('sha256') and bool(current)==bool(expected)

    def atomic(self,path,staged,expected,mode=0o600,times=None,cancel=None):
        if not self.same(path,expected):raise Conflict('Destination changed concurrently: '+str(path))
        with self.parent(path) as fd:
            if times:
                handle=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
                try:
                    if not stat.S_ISREG(os.fstat(handle).st_mode) or os.fstat(handle).st_nlink > 1:raise Denied('Not an independent regular file')
                    with os.fdopen(os.dup(handle),'rb') as checked:
                        if digest(checked)!=(expected or {}).get('sha256'):raise Conflict('File changed before timestamp update')
                    os.utime(handle,ns=tuple(times));os.fsync(handle)
                finally:os.close(handle)
            elif staged:
                temporary='.o-amigo-'+uuid.uuid4().hex
                out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                try:
                    with os.fdopen(out,'wb') as target,Path(staged).open('rb') as source:
                        while chunk:=source.read(1024*1024):
                            if cancel and cancel.is_set():raise Cancelled('Operation cancelled before commit')
                            target.write(chunk)
                        os.fchmod(target.fileno(),mode);target.flush();os.fsync(target.fileno())
                    if cancel and cancel.is_set():raise Cancelled('Operation cancelled before commit')
                    if not self.same(path,expected):raise Conflict('Destination changed before commit')
                    if expected is None:
                        # link() is an atomic create-if-absent, unlike replace().
                        os.link(temporary,path.name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
                        os.unlink(temporary,dir_fd=fd)
                    else:os.replace(temporary,path.name,src_dir_fd=fd,dst_dir_fd=fd)
                finally:
                    try:os.unlink(temporary,dir_fd=fd)
                    except FileNotFoundError:pass
            else:
                if expected:os.unlink(path.name,dir_fd=fd)
            os.fsync(fd)

    def apply(self,changes,cancel=None):
        with self.lock:
            if cancel and cancel.is_set():raise Cancelled('Operation cancelled')
            identifier,manifest=self.checkpoint(changes)
            applied=[]
            try:
                for change,entry in zip(changes,manifest):
                    if cancel and cancel.is_set():raise Cancelled('Operation cancelled')
                    path=Path(entry['path']);before=entry['before']
                    self.atomic(path,change.get('staged'),before,(before or {}).get('mode',0o600),entry['times'],cancel=cancel)
                    applied.append(entry)
                    if (self.current(path) or {}).get('sha256')!=entry['after']:raise Conflict('Post-write verification failed')
                self.db.execute("UPDATE operations SET status='committed' WHERE id=?",(identifier,));self.db.commit()
                return {'operation_id':identifier,'status':'committed','files':[e['path'] for e in manifest]}
            except BaseException:
                conflicts=[]
                for entry in reversed(applied):
                    try:self.restore_entry(identifier,entry)
                    except (OSError,Conflict,Denied):conflicts.append(entry['path'])
                status='interrupted' if conflicts else 'failed'
                self.db.execute('UPDATE operations SET status=? WHERE id=?',(status,identifier));self.db.commit()
                raise

    def restore_entry(self,identifier,entry):
        path=self.policy.path(entry['path'],exists=False)
        current=self.current(path)
        if (current or {}).get('sha256')!=entry['after']:raise Conflict('File has changed since operation')
        if entry.get('times') and current and current['mtime_ns']!=entry['times'][1]:
            raise Conflict('Timestamp changed since operation')
        before=entry['before']
        source=self.root/identifier/entry['backup'] if before else None
        if source and not source.exists():raise RecoveryUnavailable('Recovery data expired')
        self.atomic(path,source,current,(before or {}).get('mode',0o600))
        if before:
            self.atomic(path,None,self.current(path),times=[before['atime_ns'],before['mtime_ns']])

    def undo(self,identifier):
        with self.lock:
            row=self.db.execute('SELECT * FROM operations WHERE id=?',(identifier,)).fetchone()
            if not row or row['status']!='committed':raise RecoveryUnavailable('Operation is not recoverable')
            entries=json.loads(row['manifest'])
            if entries and entries[0].get('kind')=='tree':
                entry=entries[0];path=self.policy.path(entry['path'])
                if self.tree_digest(path)!=entry['after']:raise Conflict('Extracted folder changed since operation')
                shutil.rmtree(path)
                self.db.execute("UPDATE operations SET status='undone' WHERE id=?",(identifier,));self.db.commit()
                return {'operation_id':identifier,'status':'undone'}
            for entry in entries:
                current=self.current(self.policy.path(entry['path'],exists=False))
                if (current or {}).get('sha256')!=entry['after']:raise Conflict('A file changed after the operation')
                if entry.get('times') and current and current['mtime_ns']!=entry['times'][1]:raise Conflict('Timestamp changed since operation')
            for entry in reversed(entries):self.restore_entry(identifier,entry)
            self.db.execute("UPDATE operations SET status='undone' WHERE id=?",(identifier,));self.db.commit()
            return {'operation_id':identifier,'status':'undone'}

    @staticmethod
    def tree_digest(root):
        result=hashlib.sha256();count=0;size=0
        for path in sorted(root.rglob('*')):
            info=path.lstat();count+=1;size+=info.st_size if stat.S_ISREG(info.st_mode) else 0
            if count>10000 or size>2*1024**3:raise Denied('Directory exceeds operation limit')
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):raise Denied('Special archive entry')
            if stat.S_ISREG(info.st_mode) and info.st_nlink!=1:raise Denied('Hard-linked archive entry')
            result.update(path.relative_to(root).as_posix().encode());result.update(b'\x00')
            if path.is_dir():result.update(b'directory\x00')
            else:
                with path.open('rb') as file:result.update(digest(file).encode())
        return result.hexdigest()

    def install_tree(self,staged,destination,cancel=None):
        """Publish a verified new directory only; never merge into an existing tree."""
        with self.lock:
            path=self.policy.path(str(destination),exists=False)
            if path.exists():raise Conflict('Destination folder already exists')
            for source in staged.rglob('*'):
                self.policy.path(str(path/source.relative_to(staged)),exists=False)
            expected=self.tree_digest(staged)
            identifier=uuid.uuid4().hex
            manifest=[{'kind':'tree','path':str(path),'after':expected}]
            self.db.execute('INSERT INTO operations VALUES (?,?,?,?)',(identifier,time.time(),'prepared',json.dumps(manifest)))
            self.db.commit()
            temporary=path.parent/('.o-amigo-'+identifier)
            published=False
            try:
                if cancel and cancel.is_set():raise Cancelled('Operation cancelled')
                shutil.copytree(staged,temporary)
                if self.tree_digest(temporary)!=expected:raise Conflict('Directory copy verification failed')
                if cancel and cancel.is_set():raise Cancelled('Operation cancelled')
                with self.parent(path) as fd:
                    # Linux renameat2(RENAME_NOREPLACE) makes the absent-target condition atomic.
                    libc=ctypes.CDLL(None,use_errno=True)
                    rename=libc.renameat2;rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
                    if rename(fd,os.fsencode(temporary.name),fd,os.fsencode(path.name),1):
                        error=ctypes.get_errno();raise OSError(error,os.strerror(error))
                    published=True;os.fsync(fd)
                self.db.execute("UPDATE operations SET status='committed' WHERE id=?",(identifier,));self.db.commit()
                return {'operation_id':identifier,'status':'committed','files':[str(path)]}
            except BaseException:
                self.db.execute('UPDATE operations SET status=? WHERE id=?',('interrupted' if published else 'failed',identifier));self.db.commit()
                raise
            finally:
                if temporary.exists():shutil.rmtree(temporary)

    def list(self):
        with self.lock:
            return [{'id':r['id'],'created':r['created'],'status':r['status'],
                     'files':[e['path'] for e in json.loads(r['manifest'])]}
                    for r in self.db.execute('SELECT * FROM operations ORDER BY created DESC LIMIT 100')]

    def close(self):self.db.close()
