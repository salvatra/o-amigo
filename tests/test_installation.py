import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from quickask.core import Store
from amigo.migration import migrate,migrate_history
from scripts.install import Install,write
from scripts.uninstall import uninstall
from scripts.rollback import rollback

class InstallationTests(unittest.TestCase):
    def test_clean_reinstall_and_uninstall_preserve_unrelated_config(self):
        with tempfile.TemporaryDirectory() as folder:
            i=Install(Path(folder),False)
            write(i.config/'kwinrc','[Plugins]\nexistingEnabled=true\n')
            write(i.config/'kwinrulesrc','[General]\nOrder=existing\n\n[existing]\nDescription=Existing window\n')
            first=i.install();second=i.install()
            self.assertEqual(first['version'],second['version'])
            self.assertTrue(i.launcher.exists());self.assertEqual(i.readcfg('kwinrc','Plugins','existingEnabled'),'true')
            store=Store(i.root);cid=store.active();store.add(cid,'user','Synthetic history');store.close()
            self.assertEqual(i.readcfg('kwinrulesrc','General','Order'),'existing,o-amigo-popup')
            uninstall(i)
            self.assertEqual(i.readcfg('kwinrulesrc','General','Order'),'existing')
            self.assertEqual(i.readcfg('kwinrc','Plugins','existingEnabled'),'true')
            self.assertTrue((i.root/'history.sqlite3').exists());self.assertFalse(i.launcher.exists())
            i.install();self.assertTrue(i.launcher.exists())
            uninstall(i,delete_history=True);self.assertFalse(i.root.exists())
    def test_code_rollback_retains_private_data(self):
        with tempfile.TemporaryDirectory() as folder:
            i=Install(Path(folder),False)
            with patch('scripts.install.code_id',return_value='version-one'):i.install()
            write(i.root/'private-note','retain')
            with patch('scripts.install.code_id',return_value='version-two'):i.install()
            self.assertEqual((i.root/'current').resolve().name,'version-two')
            self.assertEqual(rollback(i),'version-one')
            self.assertEqual((i.root/'private-note').read_text(),'retain')

    def test_history_migration_preserves_active_and_validated_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=Store(root/'old');cid=old.active();old.add(cid,'user','Ação sintética');old.set_setting('validated','yes');old.close()
            result=migrate(root/'old',root/'new',with_key=False)
            self.assertEqual(result['counts']['messages'],1)
            new=Store(root/'new');self.assertEqual(new.active(),cid);self.assertEqual(new.setting('key_validated'),'true');new.close()
            self.assertEqual(migrate(root/'old',root/'new',with_key=False)['history'],'copied')
            with self.assertRaises(RuntimeError):migrate_history(root/'old/history.sqlite3',root/'new/history.sqlite3')
    def test_key_failure_can_resume_without_overwriting_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=Store(root/'old');old.active();old.close()
            def failure(action,app,value=None):
                return (True,b'synthetic-key') if action=='lookup' and app=='quick-ask' else (False,b'')
            with patch('amigo.migration.secret',side_effect=failure):
                with self.assertRaises(RuntimeError):migrate(root/'old',root/'new')
            def success(action,app,value=None):
                return (True,b'synthetic-key') if action=='lookup' else (True,b'')
            with patch('amigo.migration.secret',side_effect=success):self.assertEqual(migrate(root/'old',root/'new')['key'],'existing')
            self.assertNotIn(b'synthetic-key',(root/'new/history.sqlite3').read_bytes())
            self.assertNotIn('synthetic-key',(root/'new/migration.json').read_text())

if __name__=='__main__':unittest.main()
