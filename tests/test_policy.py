import tempfile
import unittest
from pathlib import Path
from amigo.policy import Policy,Denied
from amigo.tools import Tools

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.policy=Policy([self.root]); self.tools=Tools(self.policy)
    def tearDown(self): self.tmp.cleanup()
    def test_read(self):
        p=self.root/'note.md'; p.write_text('Olá, ação!')
        self.assertEqual(self.tools.call('read_file',{'path':str(p)})['text'],'Olá, ação!')
    def test_escape(self):
        with self.assertRaises(Denied):self.policy.path('/etc/passwd')
        p=self.root/'escape';p.symlink_to('/etc')
        with self.assertRaises(Denied):self.policy.path(str(p/'passwd'))
    def test_metadata(self):
        p=self.root/'.env';p.write_text('credential')
        with self.assertRaises(Denied):self.policy.path(str(p))
        self.assertEqual(self.tools.call('list_files',{'path':str(self.root)}),[])
    def test_no_shell_or_writes(self):
        for name in ['exec','shell','python','write_file','install_package']:
            with self.assertRaises(Denied):self.tools.call(name,{})
    def test_injection(self):
        for topic in ['--help','cat;id','$(id)','/tmp/a','x\nsh']:
            with self.assertRaises(Denied):self.tools.call('read_manual',{'name':topic})
    def test_extra_args(self):
        with self.assertRaises(Denied):self.tools.call('read_manual',{'name':'ls','pager':'sh'})

if __name__=='__main__': unittest.main()
