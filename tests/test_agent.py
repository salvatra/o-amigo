import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from PyQt6.QtCore import QCoreApplication,QObject,QTimer,pyqtSignal
from amigo.agent import Agent
from amigo.history import History
from amigo.settings import Settings
from amigo.protocol import request,Assembly
from amigo.approval import ApprovalGate,ApprovalRequired
from amigo.transactions import RecoveryUnavailable

APP=QCoreApplication.instance() or QCoreApplication([])

def wait_for(predicate,timeout=3):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        APP.processEvents();time.sleep(.001)
    if not predicate():raise AssertionError('Timed out')

def call(identifier,name='write_file',**args):
    return {'id':identifier,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}

class FakeStream(QObject):
    changed=pyqtSignal(str);finished=pyqtSignal(str,str,object,dict)
    def __init__(self,responses):super().__init__();self.responses=list(responses);self.bodies=[];self.reply=None
    def start(self,key,body):
        self.bodies.append(copy.deepcopy(body));self.reply=True
        response=self.responses.pop(0)
        def finish():
            self.reply=None
            if response[2] and response[2].get('content'):self.changed.emit(response[2]['content'])
            self.finished.emit(*response)
        QTimer.singleShot(0,finish)
    def cancel(self):self.reply=None;self.finished.emit('interrupted','',None,{})

def response(message,**metadata):return ('complete','',message,{'cost':.001,'searches':0,**metadata})

class FakeTools:
    def __init__(self):self.calls=[]
    def call(self,name,args):self.calls.append((name,args));return {'verified':True}

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.history=History(self.root/'data')
        self.settings=Settings(self.root/'settings.json');self.settings.value['tools_enabled']=True
        self.conversation=self.history.active();self.tools=FakeTools()
    def tearDown(self):self.history.close();self.tmp.cleanup()
    def agent(self,responses):
        self.stream=FakeStream(responses)
        return Agent(self.history,self.settings,lambda cancel:self.tools,lambda:'test-key',stream=self.stream)
    def test_tool_rounds_context_cost_and_exact_policy(self):
        invocation=call('one',path='/authorized/note',text='Olá')
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[invocation]}),response({'role':'assistant','content':'Concluído.'})])
        agent.start(self.conversation,'Escreve Olá');wait_for(lambda:agent.state['status']=='complete')
        self.assertEqual(len(self.tools.calls),1);self.assertEqual(len(self.stream.bodies),2)
        self.assertEqual(self.stream.bodies[1]['messages'][-1]['tool_call_id'],'one')
        self.assertEqual(agent.state['known_cost'],.002)
        for body in self.stream.bodies:
            self.assertEqual(body['model'],'deepseek/deepseek-v4.1-flash-1017')
            self.assertEqual(body['provider']['max_price'],{'prompt':.3,'completion':1.2})
            self.assertEqual(body['max_tokens'],4096)
        self.assertNotIn('test-key',self.history.path.read_bytes().decode(errors='ignore'))
    def test_duplicate_mutation_not_replayed(self):
        args={'path':'/note','text':'one'}
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one',**args)]}),
                          response({'role':'assistant','content':None,'tool_calls':[call('two',**args)]}),
                          response({'role':'assistant','content':'Done'})])
        agent.start(self.conversation,'write');wait_for(lambda:agent.state['status']=='complete')
        self.assertEqual(len(self.tools.calls),1)
    def test_round_limit_and_continue_keeps_counters(self):
        self.settings.value['max_rounds']=1
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one',path='/note',text='one')]}),
                          response({'role':'assistant','content':'Done'})])
        agent.start(self.conversation,'write');wait_for(lambda:agent.state['status']=='paused')
        self.assertEqual(agent.state['rounds'],1);agent.resume();wait_for(lambda:agent.state['status']=='complete')
        self.assertEqual(agent.state['rounds'],2);self.assertEqual(len(self.tools.calls),1)
    def test_search_budget_reservation_and_known_usage(self):
        self.settings.value['web_enabled']=True
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one',path='/note',text='one')]},searches=2),
                          response({'role':'assistant','content':'Done'},searches=1)])
        agent.start(self.conversation,'pesquisa');wait_for(lambda:agent.state['status']=='complete')
        budgets=[next(t['parameters']['max_uses'] for t in b['tools'] if t['type']=='openrouter:web_search') for b in self.stream.bodies]
        self.assertEqual(budgets,[3,1]);self.assertEqual(agent.state['searches'],3)
    def test_missing_search_usage_never_refunds(self):
        self.settings.value['web_enabled']=True
        agent=self.agent([('complete','',{'role':'assistant','content':None,'tool_calls':[call('one',path='/note',text='one')]},{}),
                          response({'role':'assistant','content':'Done'})])
        agent.start(self.conversation,'pesquisa');wait_for(lambda:agent.state['status']=='complete')
        self.assertFalse(any(t['type']=='openrouter:web_search' for t in self.stream.bodies[1]['tools']))
        self.assertEqual(agent.state['unknown_cost_rounds'],1)
    def test_approval_is_required_and_exactly_once(self):
        gate=ApprovalGate();executed=[]
        class GuardedTools:
            def __init__(self):self.gate=gate
            def call(self,name,args):
                self.gate.require({'operation':'install','packages':['example;1.0;x86_64;extra']})
                executed.append(args);return {'verified':True}
        self.tools=GuardedTools()
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one','package_install',names=['example'])]}),response({'role':'assistant','content':'Done'})])
        agent.start(self.conversation,'install');wait_for(lambda:agent.state['status']=='approval')
        self.assertTrue(agent.busy);self.assertEqual(executed,[])
        token=agent.state['approval']['token'];agent.decide('wrong-token',True);self.assertEqual(executed,[])
        agent.decide(token,True);wait_for(lambda:agent.state['status']=='complete');self.assertEqual(len(executed),1)
        with self.assertRaises(ApprovalRequired):gate.require({'operation':'install','packages':['example;1.0;x86_64;extra']})

    def test_changed_plan_requires_new_approval_and_denial_does_not_execute(self):
        gate=ApprovalGate();plans=[1,2];executed=[]
        class GuardedTools:
            def __init__(self):self.gate=gate
            def call(self,name,args):
                self.gate.require({'version':plans[0]});executed.append(True)
        self.tools=GuardedTools()
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one','package_install',names=['example'])]}),response({'role':'assistant','content':'Cancelled'})])
        agent.start(self.conversation,'install');wait_for(lambda:agent.state['status']=='approval')
        first=agent.state['approval']['token'];plans.pop(0);agent.decide(first,True)
        wait_for(lambda:agent.state['status']=='approval' and agent.state['approval']['token']!=first)
        self.assertEqual(executed,[]);agent.decide(agent.state['approval']['token'],False)
        wait_for(lambda:agent.state['status']=='complete');self.assertEqual(executed,[])
        self.assertEqual(self.history.call(agent.identifier,'one')['status'],'denied')

    def test_recovery_failure_pauses_and_only_explicit_continue_retries(self):
        calls=[]
        class RecoverableTools:
            def call(self,name,args):
                calls.append(args)
                if len(calls)==1:raise RecoveryUnavailable('quota')
                return {'verified':True}
        self.tools=RecoverableTools();args={'path':'/note','text':'one'}
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one',**args)]}),
                          response({'role':'assistant','content':None,'tool_calls':[call('two',**args)]}),
                          response({'role':'assistant','content':'Done'})])
        agent.start(self.conversation,'write');wait_for(lambda:agent.state['status']=='paused')
        self.assertEqual(len(calls),1);self.assertFalse(agent.busy)
        agent.resume();wait_for(lambda:agent.state['status']=='complete');self.assertEqual(len(calls),2)

    def test_restart_marks_calls_uncertain(self):
        task=self.history.save_task(self.conversation,{'status':'tool'})
        self.history.begin_call(task,'one','write_file',{'path':'/note','text':'x'})
        self.history.close();self.history=History(self.root/'data')
        self.assertEqual(self.history.call(task,'one')['status'],'uncertain')
        self.assertEqual(self.history.latest_task(self.conversation)[1]['status'],'interrupted')
    def test_history_search_pagination_portuguese(self):
        for i in range(35):
            conversation=self.history.new();self.history.add(conversation,'user',f'Ação número {i}')
        self.assertEqual(len(self.history.conversations('AÇÃO',limit=30)),30)
        self.assertEqual(len(self.history.conversations('AÇÃO',offset=30,limit=30)),5)
    def test_failure_preserves_completed_actions_in_context(self):
        agent=self.agent([response({'role':'assistant','content':None,'tool_calls':[call('one',path='/note',text='one')]}),('failed','network',None,{})])
        agent.start(self.conversation,'write');wait_for(lambda:agent.state['status']=='failed')
        self.assertTrue(any(m['role']=='tool' for m in self.history.context(self.conversation)))

if __name__=='__main__':unittest.main()
