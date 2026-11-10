"""Structured file operations through the transactional broker."""
from datetime import datetime
from pathlib import Path
import fnmatch
import hashlib
import os
import shutil
import tempfile
from zoneinfo import ZoneInfo
from .policy import Denied
from .transactions import Conflict, Cancelled

class Files:
    def __init__(self,policy,transactions,cancel=None):
        self.policy=policy;self.transactions=transactions;self.cancel=cancel

    def check_cancel(self):
        if self.cancel and self.cancel.is_set():raise Cancelled('Operation cancelled')

    def stage(self,path,destination):
        with self.policy.open_read(str(path)) as source,destination.open('xb') as target:
            while chunk:=source.read(1024*1024):
                self.check_cancel();target.write(chunk)
        return destination

    def write(self,path,text,expected='unrestricted'):
        if len(text.encode('utf-8'))>16*1024**2:raise Denied('Text exceeds 16 MiB')
        target=self.policy.path(path,exists=False)
        with tempfile.TemporaryDirectory(prefix='o-amigo-write-') as directory:
            staged=Path(directory)/'data';staged.write_text(text)
            change={'path':target,'staged':staged}
            if expected!='unrestricted':change['expected']=expected
            return self.transactions.apply([change],self.cancel)

    def replace(self,path,old,new):
        if not old:raise Denied('Empty search text')
        with self.policy.open_read(path) as source:
            content=source.read(16*1024**2+1)
        if len(content)>16*1024**2:raise Denied('File exceeds edit limit')
        text=content.decode('utf-8')
        if text.count(old)!=1:raise Conflict('Replacement requires exactly one matching occurrence')
        return self.write(path,text.replace(old,new,1),hashlib.sha256(content).hexdigest())

    def copy(self,source,destination,move=False):
        src=self.policy.path(source);dest=self.policy.path(destination,exists=False)
        if move and (self.in_vault(src) or self.in_vault(dest)):
            raise Denied('Use the Obsidian adapter to move notes or attachments without breaking links')
        if src==dest:raise Denied('Source and destination are identical')
        if dest.exists():raise Conflict('Destination already exists; choose a different name')
        with tempfile.TemporaryDirectory(prefix='o-amigo-copy-') as directory:
            staged=self.stage(src,Path(directory)/'data')
            with staged.open('rb') as file:sha=hashlib.file_digest(file,'sha256').hexdigest()
            changes=[{'path':dest,'staged':staged}]
            if move:changes.append({'path':src,'staged':None,'expected':sha})
            result=self.transactions.apply(changes,self.cancel)
            return result|{'sha256':sha,'bytes':staged.stat().st_size}

    @staticmethod
    def in_vault(path):
        return any((parent/'.obsidian').is_dir() for parent in path.parents)

    def mkdir(self,path):
        with tempfile.TemporaryDirectory(prefix='o-amigo-folder-') as directory:
            return self.transactions.install_tree(Path(directory),path,self.cancel)

    def trash(self,path):
        from PyQt6.QtCore import QFile
        target=self.policy.path(path)
        if self.in_vault(target):raise Denied('Use the Obsidian adapter for vault changes')
        with self.transactions.lock:
            identifier,manifest=self.transactions.checkpoint([{'path':target,'staged':None}])
            try:
                self.check_cancel()
                if not self.transactions.same(target,manifest[0]['before']):raise Conflict('File changed before Trash')
                ok,location=QFile.moveToTrash(str(target))
                if not ok:raise OSError('Desktop Trash operation failed')
                status='committed' if not target.exists() else 'interrupted'
                self.transactions.db.execute('UPDATE operations SET status=? WHERE id=?',(status,identifier))
                self.transactions.db.commit()
                return {'operation_id':identifier,'status':status,'trash_location':location,
                        'recovery':'Undo restores the recovery copy; the desktop Trash copy is retained.'}
            except BaseException:
                self.transactions.db.execute("UPDATE operations SET status='interrupted' WHERE id=?",(identifier,))
                self.transactions.db.commit();raise

    def timestamps(self,path,mtime,atime=None,timezone='Europe/Lisbon'):
        target=self.policy.path(path)
        def timestamp(value):
            dt=datetime.fromisoformat(value)
            if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo(timezone))
            return int(dt.timestamp()*1e9)
        info=target.stat()
        times=[timestamp(atime) if atime else info.st_atime_ns,timestamp(mtime)]
        return self.transactions.apply([{'path':target,'times':times}],self.cancel)

    def search(self,root,pattern='*',text=None,limit=100):
        root=self.policy.path(root);found=[];visited=0
        if not 1<=limit<=500:raise Denied('Limit must be between 1 and 500')
        for directory,dirs,names in os.walk(root,followlinks=False):
            self.check_cancel()
            permitted=[]
            for name in sorted(dirs):
                try:self.policy.path(str(Path(directory)/name));permitted.append(name)
                except (Denied,OSError):pass
            dirs[:]=permitted
            for name in sorted(names):
                visited+=1
                if visited>100000:return {'matches':found,'truncated':True}
                if not fnmatch.fnmatchcase(name,pattern):continue
                p=Path(directory)/name
                try:
                    self.policy.path(str(p))
                    if text is not None:
                        with self.policy.open_read(str(p)) as file:data=file.read(1024*1024)
                        if b'\x00' in data or text.casefold() not in data.decode('utf-8',errors='replace').casefold():continue
                    found.append(str(p))
                except (Denied,OSError):continue
                if len(found)>=limit:return {'matches':found,'truncated':True}
        return {'matches':found,'truncated':False}
