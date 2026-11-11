import json
from pathlib import Path
import tempfile
import unittest
from PyQt6.QtCore import QCoreApplication
from amigo.controller import Controller
from amigo.settings import Settings,DEFAULTS

app=QCoreApplication.instance() or QCoreApplication([])

class PopupConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.controller=Controller(Settings(root/'settings.json'),root/'data',demo=True)
    def tearDown(self):
        self.controller.close();self.temp.cleanup()
    def test_upgrade_handoff_restores_transient_draft_without_history(self):
        c=self.controller;c.newConversation();identifier=c.conversation
        path=c.data_root/'composer-handoff.json'
        path.write_text(json.dumps({'conversation':identifier,'draft':'Não perder < & >\n café'}))
        c.newConversation();c.restore_composer()
        self.assertEqual(c.conversation,identifier)
        self.assertEqual(c.draft,'Não perder < & >\n café')
        self.assertFalse(path.exists());self.assertEqual(c.history.conversations(),[])
        self.assertEqual(c.history.db.execute('SELECT count(*) FROM conversations').fetchone()[0],0)

    def test_upgrade_handoff_preserves_sent_conversation_and_draft(self):
        c=self.controller;c.send('Pergunta');identifier=c.conversation
        (c.data_root/'composer-handoff.json').write_text(json.dumps({'conversation':identifier,'draft':'Próxima pergunta'}))
        c.newConversation();c.restore_composer()
        self.assertEqual(c.conversation,identifier);self.assertEqual(c.draft,'Próxima pergunta')
        self.assertEqual(len(c.rows),2)
        self.assertEqual(c.history.setting('draft:'+identifier),'Próxima pergunta')

    def test_reopen_preserves_draft_and_starts_fresh_after_sending(self):
        c=self.controller;c.setVisible(True);old=c.conversation
        c.send('Pergunta sintética');c.setDraft('Rascunho guardado')
        c.setVisible(True);self.assertEqual(c.conversation,old)
        c.setVisible(False);c.setVisible(True)
        self.assertEqual(c.conversation,old);self.assertEqual(c.draft,'Rascunho guardado')
        self.assertEqual(len(c.rows),2)
        c.send(c.draft);self.assertEqual(c.draft,'')
        c.setVisible(False);c.setVisible(True)
        self.assertNotEqual(c.conversation,old);self.assertEqual(c.rows,[]);self.assertEqual(c.draft,'')
        self.assertEqual(len(c.history.messages(old)),4)
        c.selectConversation(old);self.assertEqual(len(c.rows),4)

    def test_transient_draft_survives_popup_and_widget_reopening_without_history(self):
        c=self.controller;c.setVisible(True);original=c.conversation
        text='Uma pergunta por enviar\ncom ação e café.'
        c.setDraft(text);c.setVisible(False);c.setVisible(True)
        self.assertEqual(c.conversation,original);self.assertEqual(c.draft,text)
        c.prepareConversation();self.assertEqual(c.conversation,original);self.assertEqual(c.draft,text)
        self.assertEqual(c.history.conversations(),[])
        self.assertEqual(c.history.db.execute('SELECT count(*) FROM conversations').fetchone()[0],0)
        c.setDraft('');c.setVisible(False);c.setVisible(True)
        self.assertNotEqual(c.conversation,original);self.assertEqual(c.draft,'')
        c.setDraft(text);c.newConversation();self.assertEqual(c.draft,'')
        self.assertEqual(c.history.conversations(),[])

    def test_reopening_keeps_inflight_task_attached_to_original_conversation(self):
        c=self.controller;c.setVisible(True);old=c.conversation;c.send('Pergunta sintética')
        task={'conversation':old,'status':'requesting','message_id':c.rows[-1]['id'],'text':'Resposta em curso','actions':[]}
        c.agent.state=task;c.agent.identifier='original-task';c.agent.round_text=' parcial'
        c.setVisible(False);c.setVisible(True);fresh=c.conversation
        self.assertNotEqual(fresh,old);self.assertIs(c.agent.state,task)
        self.assertEqual(c.agent.identifier,'original-task');self.assertFalse(c.agent.cancel_event.is_set())
        state=json.loads(c.stateJson);self.assertTrue(state['busy']);self.assertEqual(state['backgroundConversation'],old)
        self.assertEqual(state['messages'],[])
        c.selectConversation(old);self.assertEqual(c.conversation,old);self.assertIs(c.agent.state,task)
        self.assertEqual(json.loads(c.stateJson)['backgroundConversation'],'')
        c.newConversation();fresh=c.conversation;c.setDraft('A próxima pergunta');task['status']='complete';c.completed()
        self.assertEqual(c.conversation,fresh);self.assertEqual(c.rows,[]);self.assertEqual(c.draft,'A próxima pergunta')
    def test_unsent_openings_do_not_create_history_or_draft_rows(self):
        c=self.controller
        for _ in range(8):
            c.setVisible(True);c.setDraft('Ainda não enviada');c.send('   ');c.setVisible(False)
        self.assertEqual(c.history.db.execute('SELECT count(*) FROM conversations').fetchone()[0],0)
        self.assertEqual(c.history.db.execute("SELECT count(*) FROM settings WHERE key LIKE 'draft:%'").fetchone()[0],0)
        self.assertEqual(json.loads(c.historyPage('',0)),[])
        c.setVisible(True);self.assertEqual(c.draft,'Ainda não enviada')
        c.send('Primeira mensagem');saved=c.conversation
        c.send('Segunda mensagem')
        self.assertEqual([row['id'] for row in c.history.conversations()],[saved])
        self.assertEqual(len(c.history.messages(saved)),4)
        c.setVisible(False);c.setVisible(True)
        self.assertEqual([row['id'] for row in c.history.conversations()],[saved])
        self.assertEqual(c.history.db.execute('SELECT count(*) FROM conversations').fetchone()[0],1)

    def test_legacy_empty_entries_are_cleaned_without_losing_messages_or_drafts(self):
        from amigo.history import History
        c=self.controller;empty=c.history.new();draft=c.history.new()
        c.history.set_setting('draft:'+draft,'Rascunho antigo a preservar')
        sent=c.history.new();c.history.add(sent,'user','Mensagem guardada')
        c.history.close();c.history=History(c.data_root)
        self.assertFalse(c.history.db.execute('SELECT 1 FROM conversations WHERE id=?',(empty,)).fetchone())
        self.assertEqual(c.history.setting('draft:'+draft),'Rascunho antigo a preservar')
        self.assertEqual([row['id'] for row in c.history.conversations()],[sent])
        self.assertEqual(c.history.conversations('Nova conversa'),[])
        self.assertEqual([row['id'] for row in c.history.conversations('guardada')],[sent])
        exported=Path(self.temp.name)/'export.json';c.exportHistory(str(exported))
        self.assertEqual([row['id'] for row in json.loads(exported.read_text())],[sent])

    def test_default_shortcut_requires_super(self):
        self.assertEqual(DEFAULTS['shortcut'],'Meta+F12')

if __name__=='__main__':unittest.main()
