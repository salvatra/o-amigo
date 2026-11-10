import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from amigo.policy import Policy,Denied
from amigo.transactions import Transactions,Conflict
from amigo.files import Files
from amigo.obsidian import Obsidian,links

class ObsidianTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.vault=self.root/'vault';self.vault.mkdir()
        (self.vault/'.obsidian').mkdir();(self.vault/'notes').mkdir();(self.vault/'assets').mkdir()
        self.policy=Policy([self.vault]);self.tx=Transactions(self.root/'recovery',self.policy)
        self.adapter=Obsidian(Files(self.policy,self.tx))
    def tearDown(self):self.tx.close();self.tmp.cleanup()
    def write(self,name,text):
        path=self.vault/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_text(text);return path
    def test_note_rename_updates_incoming_and_preserves_code(self):
        source=self.write('notes/Olá.md','Contents')
        initial='[[Olá#Título|rótulo]] ![[notes/Olá]] [read](notes/Ol%C3%A1.md#section)\n`[[Olá]]`\n```md\n[[Olá]]\n```\n'
        index=self.write('index.md',initial)
        result=self.adapter.move(str(self.vault),str(source),str(self.vault/'notes/Novo.md'))
        text=index.read_text()
        self.assertIn('[[notes/Novo#Título|rótulo]]',text);self.assertIn('![[notes/Novo]]',text)
        self.assertIn('(notes/Novo.md#section)',text);self.assertIn('`[[Olá]]`',text);self.assertIn('```md\n[[Olá]]\n```',text)
        self.tx.undo(result['operation_id']);self.assertEqual(index.read_text(),initial);self.assertEqual(source.read_text(),'Contents')
    def test_outgoing_relative_links_follow_moved_note(self):
        source=self.write('notes/a.md','[image](../assets/image.png) [[b]] [self](#heading)')
        self.write('notes/b.md','B');(self.vault/'assets/image.png').write_bytes(b'fake image')
        self.adapter.move(str(self.vault),str(source),str(self.vault/'a.md'))
        self.assertIn('[image](assets/image.png)',(self.vault/'a.md').read_text())
        self.assertIn('[self](#heading)',(self.vault/'a.md').read_text())
    def test_attachment_embed_reference_html_and_canvas(self):
        attachment=self.vault/'assets/image.png';attachment.write_bytes(b'image')
        note=self.write('index.md','![[assets/image.png|200]]\n[image][ref]\n[ref]: assets/image.png "Title"\n<img src="assets/image.png">')
        canvas=self.write('board.canvas',json.dumps({'nodes':[{'id':'n','type':'file','file':'assets/image.png'}],'edges':[]}))
        result=self.adapter.move(str(self.vault),str(attachment),str(self.vault/'assets/new.png'))
        self.assertNotIn('assets/image.png',note.read_text())
        self.assertIn('assets/new.png',canvas.read_text());self.assertIn('board.canvas',result['updated_notes'])
    def test_ambiguous_link_aborts_without_changes(self):
        a=self.write('notes/a.md','A');self.write('elsewhere/a.md','other');index=self.write('index.md','[[a]]')
        with self.assertRaises(Conflict):self.adapter.move(str(self.vault),str(a),str(self.vault/'notes/new.md'))
        self.assertTrue(a.exists());self.assertEqual(index.read_text(),'[[a]]');self.assertEqual(self.tx.list(),[])
    def test_concurrent_note_edit_is_preserved(self):
        source=self.write('notes/a.md','A');index=self.write('index.md','[[a]]');apply=self.tx.apply
        def race(changes,cancel):
            index.write_text('User editing now')
            return apply(changes,cancel)
        with patch.object(self.tx,'apply',side_effect=race):
            with self.assertRaises(Conflict):self.adapter.move(str(self.vault),str(source),str(self.vault/'notes/new.md'))
        self.assertTrue(source.exists());self.assertEqual(index.read_text(),'User editing now')
    def test_external_and_encoded_parentheses(self):
        source=self.write('notes/a (1).md','A');index=self.write('index.md','[a](notes/a%20%281%29.md) [web](https://example.com/a)')
        self.adapter.move(str(self.vault),str(source),str(self.vault/'notes/b.md'))
        self.assertEqual(index.read_text(),'[a](notes/b.md) [web](https://example.com/a)')
    def test_scope_and_metadata_rejected(self):
        source=self.write('notes/a.md','A')
        with self.assertRaises(Denied):self.adapter.move(str(self.vault),str(source),str(self.vault/'.obsidian/evil.md'))
        with self.assertRaises(Denied):self.adapter.move(str(self.vault),str(source),str(self.root/'outside.md'))

if __name__=='__main__':unittest.main()
