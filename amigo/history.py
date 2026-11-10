"""Conversation storage plus durable task/call state. No credentials are stored here."""
import hashlib
import json
import time
import uuid
from quickask.core import Store

class History(Store):
    def __init__(self,directory):
        super().__init__(directory)
        self.db.create_function('casefold',1,lambda text:(text or '').casefold())
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            updated REAL NOT NULL, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tool_calls (
            task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            id TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT, PRIMARY KEY(task,id));
        CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation,id);
        CREATE INDEX IF NOT EXISTS tasks_conversation ON tasks(conversation,updated);
        ''')
        self.db.execute("UPDATE tool_calls SET status='uncertain' WHERE status='running'")
        for row in self.db.execute('SELECT id,state FROM tasks').fetchall():
            state=json.loads(row['state'])
            if state.get('status') in ('running','tool','requesting','approval'):
                state.pop('approval',None)
                state['status']='interrupted';state['error']='A aplicação foi interrompida. As operações não foram repetidas.'
                self.db.execute('UPDATE tasks SET state=? WHERE id=?',(json.dumps(state),row['id']))
        self.db.commit()

    def conversations(self,query='',offset=0,limit=30):
        limit=max(1,min(int(limit),100));offset=max(0,int(offset));needle=query.casefold()
        rows=self.db.execute('''SELECT * FROM conversations c WHERE ?='' OR instr(casefold(c.title),?)>0
             OR EXISTS(SELECT 1 FROM messages m WHERE m.conversation=c.id AND instr(casefold(m.content),?)>0)
             ORDER BY updated DESC LIMIT ? OFFSET ?''',(needle,needle,needle,limit,offset)).fetchall()
        return [dict(row) for row in rows]

    def context(self,cid):
        result=[]
        for message in self.messages(cid):
            if message['role']=='user':result.append({'role':'user','content':message['content']})
            elif message['status'] in ('complete','failed','interrupted','paused'):
                sequence=message['metadata'].get('protocol_messages')
                if isinstance(sequence,list):
                    pending={call['id'] for item in sequence for call in item.get('tool_calls',[])}
                    returned={item.get('tool_call_id') for item in sequence if item.get('role')=='tool'}
                    if pending<=returned:result.extend(sequence)
                elif message['content'] and message['status']=='complete':result.append({'role':'assistant','content':message['content']})
        return result

    def save_task(self,conversation,state,identifier=None):
        identifier=identifier or uuid.uuid4().hex
        self.db.execute('INSERT INTO tasks VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,state=excluded.state',
                        (identifier,conversation,time.time(),json.dumps(state,ensure_ascii=False)))
        self.db.commit();return identifier

    def latest_task(self,conversation):
        row=self.db.execute('SELECT * FROM tasks WHERE conversation=? ORDER BY updated DESC LIMIT 1',(conversation,)).fetchone()
        return (row['id'],json.loads(row['state'])) if row else None

    def call(self,task,identifier):
        row=self.db.execute('SELECT * FROM tool_calls WHERE task=? AND id=?',(task,identifier)).fetchone()
        return dict(row) if row else None

    def previous_call(self,task,name,args):
        fingerprint=self.fingerprint(name,args)
        row=self.db.execute('SELECT * FROM tool_calls WHERE task=? AND fingerprint=? ORDER BY rowid DESC LIMIT 1',(task,fingerprint)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def fingerprint(name,args):
        return hashlib.sha256(json.dumps([name,args],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def begin_call(self,task,identifier,name,args):
        self.db.execute('INSERT INTO tool_calls VALUES (?,?,?,?,?,NULL)',
                        (task,identifier,self.fingerprint(name,args),'running',json.dumps({'name':name,'arguments':args},ensure_ascii=False)))
        self.db.commit()

    def finish_call(self,task,identifier,result,status='complete'):
        self.db.execute('UPDATE tool_calls SET status=?,result=? WHERE task=? AND id=?',
                        (status,json.dumps(result,ensure_ascii=False),task,identifier));self.db.commit()
