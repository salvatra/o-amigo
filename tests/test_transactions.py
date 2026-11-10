import os
import errno
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from amigo.policy import Policy,Denied
from amigo.transactions import Transactions,Conflict,RecoveryUnavailable,Cancelled
from amigo.files import Files

class TransactionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.data=self.base/'data';self.data.mkdir()
        self.policy=Policy([self.data])
        self.tx=Transactions(self.base/'recovery',self.policy)
        self.files=Files(self.policy,self.tx)
    def tearDown(self):self.tx.close();self.tmp.cleanup()
    def test_create_edit_undo(self):
        p=self.data/'ação.md'
        created=self.files.write(str(p),'Olá')
        edited=self.files.replace(str(p),'Olá','Adeus')
        self.assertEqual(p.read_text(),'Adeus')
        self.tx.undo(edited['operation_id']);self.assertEqual(p.read_text(),'Olá')
        self.tx.undo(created['operation_id']);self.assertFalse(p.exists())
    def test_conflicting_undo_preserves_user_change(self):
        p=self.data/'note';p.write_text('original')
        result=self.files.write(str(p),'agent');p.write_text('new user data')
        with self.assertRaises(Conflict):self.tx.undo(result['operation_id'])
        self.assertEqual(p.read_text(),'new user data')
    def test_quota_before_change(self):
        p=self.data/'note';p.write_text('original')
        self.tx.quota=2
        with self.assertRaises(RecoveryUnavailable):self.files.write(str(p),'replacement')
        self.assertEqual(p.read_text(),'original')
    def test_move_and_restore(self):
        a=self.data/'a';b=self.data/'b';a.write_bytes(b'x'*100000)
        result=self.files.copy(str(a),str(b),move=True)
        self.assertFalse(a.exists());self.assertEqual(b.stat().st_size,100000)
        self.tx.undo(result['operation_id']);self.assertTrue(a.exists());self.assertFalse(b.exists())
    def test_existing_copy_destination(self):
        a=self.data/'a';b=self.data/'b';a.write_text('A');b.write_text('B')
        with self.assertRaises(Conflict):self.files.copy(str(a),str(b))
        self.assertEqual(b.read_text(),'B')
    def test_timestamp_and_recovery(self):
        p=self.data/'note';p.write_text('same');old=p.stat().st_mtime_ns
        result=self.files.timestamps(str(p),'2024-01-01T12:00:00+00:00')
        self.assertEqual(int(p.stat().st_mtime),1704110400)
        self.tx.undo(result['operation_id']);self.assertEqual(p.stat().st_mtime_ns,old)
    def test_cancel_and_restart(self):
        p=self.data/'note';p.write_text('old');event=threading.Event();event.set()
        self.files.cancel=event
        with self.assertRaises(Cancelled):self.files.write(str(p),'new')
        self.assertEqual(p.read_text(),'old')
        self.tx.db.execute("INSERT INTO operations VALUES ('pending',0,'prepared','[]')");self.tx.db.commit()
        self.tx.close();self.tx=Transactions(self.base/'recovery',self.policy)
        self.assertEqual(next(r for r in self.tx.list() if r['id']=='pending')['status'],'interrupted')
    def test_symlink_and_hardlink_write(self):
        outside=self.base/'outside';outside.write_text('protected')
        link=self.data/'link';link.symlink_to(outside)
        with self.assertRaises(Denied):self.files.write(str(link),'bad')
        link.unlink();os.link(outside,link)
        with self.assertRaises(Denied):self.files.write(str(link),'bad')
        self.assertEqual(outside.read_text(),'protected')
    def test_search_excludes_secrets(self):
        (self.data/'.env').write_text('secret')
        (self.data/'note.md').write_text('Ação')
        result=self.files.search(str(self.data),text='AÇÃO')
        self.assertEqual(result['matches'],[str(self.data/'note.md')])

    def test_partial_batch_rolls_back_on_failure(self):
        from unittest.mock import patch
        a=self.data/'a';b=self.data/'b';a.write_text('old A');b.write_text('old B')
        staged=self.base/'staged';staged.write_text('new')
        original=self.tx.atomic
        def injected(path,source,expected,mode=0o600,times=None,cancel=None):
            if path==b and source==staged:raise OSError(errno.ENOSPC,'simulated full disk')
            return original(path,source,expected,mode,times,cancel=cancel)
        with patch.object(self.tx,'atomic',side_effect=injected):
            with self.assertRaises(OSError):
                self.tx.apply([{'path':a,'staged':staged},{'path':b,'staged':staged}])
        self.assertEqual(a.read_text(),'old A');self.assertEqual(b.read_text(),'old B')
        self.assertEqual(self.tx.list()[0]['status'],'failed')

    def test_private_recovery_and_no_policy_bypass(self):
        p=self.data/'note';p.write_text('private contents')
        self.files.write(str(p),'updated')
        self.assertEqual(self.tx.root.stat().st_mode&0o777,0o700)
        for p in self.tx.root.glob('*/*.bak'):
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaises(Denied):self.policy.path(str(p))

    def test_quota_batch_checks_before_any_write(self):
        a=self.data/'a';b=self.data/'b';a.write_text('1234');b.write_text('5678')
        staged=self.base/'new';staged.write_text('X');self.tx.quota=6
        with self.assertRaises(RecoveryUnavailable):
            self.tx.apply([{'path':a,'staged':staged},{'path':b,'staged':staged}])
        self.assertEqual(a.read_text(),'1234');self.assertEqual(b.read_text(),'5678')

    def test_large_copy_and_explicit_free_space_check(self):
        from unittest.mock import patch
        from collections import namedtuple
        source=self.data/'large';target=self.data/'copy';block=bytes(range(256))*4096
        with source.open('wb') as file:
            for _ in range(64):file.write(block)
        result=self.files.copy(str(source),str(target))
        self.assertEqual(result['bytes'],64*1024**2)
        with target.open('rb') as file:self.assertEqual(hashlib.file_digest(file,'sha256').hexdigest(),result['sha256'])
        self.tx.undo(result['operation_id']);self.assertFalse(target.exists())
        usage=namedtuple('Usage','total used free')(100,100,0)
        with patch('amigo.files.shutil.disk_usage',return_value=usage):
            with self.assertRaises(OSError) as error:self.files.copy(str(source),str(target))
        self.assertEqual(error.exception.errno,errno.ENOSPC);self.assertFalse(target.exists())

    def test_cancel_during_atomic_staging_preserves_original(self):
        from unittest.mock import patch
        original=self.data/'original';original.write_text('keep')
        staged=self.base/'staged';staged.write_bytes(b'x'*(4*1024**2));event=threading.Event()
        real_open=Path.open
        class CancellingFile:
            def __init__(self,file):self.file=file
            def __enter__(self):return self
            def __exit__(self,*args):self.file.close()
            def read(self,size):event.set();return self.file.read(size)
        def opened(path,*args,**kwargs):
            file=real_open(path,*args,**kwargs)
            return CancellingFile(file) if path==staged else file
        expected=self.tx.current(original)
        with patch.object(Path,'open',opened):
            with self.assertRaises(Cancelled):self.tx.atomic(original,staged,expected,cancel=event)
        self.assertEqual(original.read_text(),'keep');self.assertEqual(list(self.data.glob('.o-amigo-*')),[])
