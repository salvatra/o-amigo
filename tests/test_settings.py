import copy
import json
from pathlib import Path
import tempfile
import unittest
from amigo.settings import DEFAULTS,Settings,validate
from amigo.settings_ui import schema
from amigo.controller import display_markdown
from amigo.policy import Policy,Denied
from amigo.tools import Tools

class SettingsTests(unittest.TestCase):
    def test_all_settings_have_controls(self):
        self.assertEqual({f['key'] for group in schema() for f in group['fields']},set(DEFAULTS))
    def test_strict_types_and_limits(self):
        for key,value in [('tools_enabled','yes'),('max_rounds',True),('max_searches',100),('temperature',float('nan')),('input_price',float('inf')),('allowed_folders',['relative']),('providers','abc'),('search_engine','native'),('backup_days',0)]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):validate({key:value})
        with self.assertRaises(ValueError):validate({'allowed_domains':['example.com'],'excluded_domains':['test.com']})
    def test_private_atomic_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=Settings(Path(directory)/'settings.json');settings.save(DEFAULTS)
            self.assertEqual(settings.path.stat().st_mode&0o777,0o600)
            original=settings.path.read_bytes()
            with self.assertRaises(ValueError):settings.save({'tools_enabled':'yes'})
            self.assertEqual(settings.path.read_bytes(),original)
    def test_disabled_capability_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'note';path.write_text('private')
            tools=Tools(Policy([directory]),disabled=['read_file'])
            with self.assertRaises(Denied):tools.call('read_file',{'path':str(path)})
    def test_markdown_cannot_load_images_or_html(self):
        value='![remote](https://example.com/pixel) ![ref][id] ![shortcut]\n[id]: file:///home/user/.ssh/id_rsa\n<img src="file:///etc/passwd">'
        safe=display_markdown(value)
        self.assertNotIn('![',safe);self.assertNotIn('<img',safe)

if __name__=='__main__':unittest.main()
