"""One durable agent task, streamed model rounds and sequential typed capabilities."""
import copy
import json
import threading
from PyQt6.QtCore import QObject,QThread,QTimer,pyqtSignal
from .network import Stream
from .protocol import request
from .policy import Denied
from .approval import ApprovalRequired
from .transactions import Conflict,RecoveryUnavailable,Cancelled

MUTATIONS={'create_folder','write_file','edit_file','copy_file','move_file','trash_file','set_file_times',
           'pdf_pages','pdf_split','archive_create','archive_extract','obsidian_move',
           'usb_mount','usb_unmount','usb_eject','printer_configure','printer_action','printer_print','package_install','browser_download'}

class ToolWorker(QThread):
    result=pyqtSignal(object)
    def __init__(self,tools,name,args,parent=None):
        super().__init__(parent);self.tools=tools;self.name=name;self.args=args
    def run(self):
        try:self.result.emit({'ok':True,'result':self.tools.call(self.name,self.args)})
        except ApprovalRequired as error:self.result.emit({'approval':{'token':error.token,'plan':error.plan}})
        except RecoveryUnavailable as error:self.result.emit({'ok':False,'error':str(error),'recovery_required':True})
        except (Denied,Conflict,Cancelled,OSError,ValueError,RuntimeError) as error:
            self.result.emit({'ok':False,'error':str(error)[:1200]})
        except Exception:self.result.emit({'ok':False,'error':'A ferramenta falhou sem confirmar alterações. Verifica o registo de recuperação.'})

class Agent(QObject):
    changed=pyqtSignal()
    finished=pyqtSignal()

    def __init__(self,history,settings,tools_factory,key,parent=None,stream=None):
        super().__init__(parent);self.history=history;self.settings=settings;self.tools_factory=tools_factory;self.key=key
        self.stream=stream or Stream(self);self.stream.changed.connect(self.on_text);self.stream.finished.connect(self.on_response)
        self.state=None;self.identifier=None;self.worker=None;self.cancel_event=threading.Event();self.round_text=''
        self.checkpoint=QTimer(self);self.checkpoint.setSingleShot(True);self.checkpoint.setInterval(750)
        self.checkpoint.timeout.connect(self.persist)

    @property
    def busy(self):return bool(self.worker or self.stream.reply or self.state and self.state.get('status') in ('running','requesting','tool','approval'))

    def start(self,conversation,prompt,thinking=False):
        if self.busy:raise RuntimeError('Já existe uma tarefa em curso.')
        if not self.key():raise ValueError('Guarda e testa a chave do OpenRouter primeiro.')
        if not prompt.strip() or len(prompt)>131072:raise ValueError('Prompt vazio ou demasiado longo.')
        self.history.add(conversation,'user',prompt)
        messages=self.history.context(conversation)
        mid=self.history.add(conversation,'assistant','','streaming')
        settings=copy.deepcopy(self.settings.value)
        self.state={'conversation':conversation,'message_id':mid,'messages':messages,'base_count':len(messages),
                    'thinking':thinking,'settings':settings,'rounds':0,'searches':0,'round_limit':settings['max_rounds'],
                    'search_limit':settings['max_searches'],'status':'running','text':'','actions':[],
                    'known_cost':0.0,'unknown_cost_rounds':0,'sources':[],'pending':[],'error':'','providers':[]}
        self.state['elapsed']=0.0
        self.state['fetches']=0;self.state['fetch_limit']=settings.get('max_fetches',6)
        self.identifier=None;self.round_text='';self.cancel_event.clear();self.persist();self.next_round()

    def restore(self,conversation):
        if self.busy:return
        latest=self.history.latest_task(conversation)
        if latest:self.identifier,self.state=latest;self.round_text=''
        else:self.identifier=None;self.state=None
        self.changed.emit()

    def resume(self):
        if self.busy or not self.state or self.state['status'] not in ('paused','interrupted','failed'):return
        self.settle_pending()
        # Counters never reset. Continue grants another explicit bounded tranche.
        self.state['round_limit']=max(self.state['round_limit'],self.state['rounds'])+self.settings.value['max_rounds']
        self.state['search_limit']=max(self.state['search_limit'],self.state['searches'])+self.settings.value['max_searches']
        self.state['fetch_limit']=max(self.state.get('fetch_limit',0),self.state.get('fetches',0))+self.settings.value.get('max_fetches',6)
        self.state['status']='running';self.state['error']='';self.cancel_event.clear();self.persist();self.next_round()

    def persist(self):
        if not self.state:return
        self.identifier=self.history.save_task(self.state['conversation'],self.state,self.identifier)
        metadata={k:self.state[k] for k in ('known_cost','unknown_cost_rounds','sources','actions','rounds','searches','providers')}
        metadata['protocol_messages']=self.state['messages'][self.state['base_count']:]
        metadata['task_id']=self.identifier;metadata['error']=self.state.get('error','')
        status=self.state['status']
        display_status='streaming' if status in ('running','requesting','tool') else status
        self.history.update(self.state['message_id'],self.state['text']+self.round_text,display_status,metadata)
        self.changed.emit()

    def on_text(self,text):
        if not self.state:return
        self.round_text=text;self.changed.emit()
        if not self.checkpoint.isActive():self.checkpoint.start()

    def next_round(self):
        if self.cancel_event.is_set():self.finish('interrupted');return
        if self.state['rounds']>=self.state['round_limit']:
            self.finish('paused','Limite de rondas atingido. O progresso ficou guardado; podes continuar.');return
        if not self.key():self.finish('failed','A chave não está disponível.');return
        self.round_text='';settings=self.state['settings'];remaining=max(0,self.state['search_limit']-self.state['searches'])
        fetch_remaining=max(0,self.state.get('fetch_limit',0)-self.state.get('fetches',0)) if settings['web_enabled'] else 0
        body=request(settings,self.state['messages'],self.state['thinking'],settings['tools_enabled'],remaining,fetch_remaining)
        self.state['fetch_reservation']=fetch_remaining;self.state['fetches']=self.state.get('fetches',0)+fetch_remaining
        reserve=remaining if settings['web_enabled'] else 0
        self.state['search_reservation']=reserve;self.state['searches']+=reserve
        self.state['rounds']+=1;self.state['status']='requesting';self.persist()
        try:self.stream.start(self.key(),body)
        except Exception:self.finish('failed','Não foi possível iniciar o pedido. A chave não foi registada.')

    def on_response(self,status,error,message,metadata):
        if not self.state:return
        self.checkpoint.stop()
        reserved=self.state.pop('search_reservation',0)
        used=metadata.get('searches')
        if type(used)is int and 0<=used<=reserved:self.state['searches']-=reserved-used
        elif reserved:self.state['search_usage_uncertain']=True
        reserved_fetches=self.state.pop('fetch_reservation',0);used_fetches=metadata.get('fetches')
        if type(used_fetches)is int and 0<=used_fetches<=reserved_fetches:self.state['fetches']-=reserved_fetches-used_fetches
        if 'cost' in metadata:self.state['known_cost']+=metadata['cost']
        else:self.state['unknown_cost_rounds']+=1
        self.state['elapsed']=self.state.get('elapsed',0)+metadata.get('elapsed',0)
        provider=metadata.get('provider')
        if provider and provider not in self.state['providers']:self.state['providers'].append(provider)
        for source in metadata.get('sources',[]):
            if source not in self.state['sources']:self.state['sources'].append(source)
        if self.round_text:self.state['text']+=self.round_text+'\n\n'
        self.round_text=''
        if status!='complete':self.finish(status,error);return
        self.state['messages'].append(message)
        calls=message.get('tool_calls',[])
        if not calls:
            if metadata.get('finish_reason')=='length':self.finish('paused','A resposta atingiu o limite de tokens. Podes continuar.')
            else:self.finish('complete')
            return
        self.state['pending']=calls;self.state['status']='tool';self.persist();self.next_tool()

    def next_tool(self):
        if self.cancel_event.is_set():self.settle_pending();self.finish('interrupted');return
        if not self.state['pending']:
            self.state['status']='running';self.persist();QTimer.singleShot(0,self.next_round);return
        call=self.state['pending'][0];name=call['function']['name'];args=json.loads(call['function']['arguments'])
        existing=self.history.call(self.identifier,call['id'])
        if existing:
            if existing['fingerprint']!=self.history.fingerprint(name,args):
                self.finish('failed','O fornecedor reutilizou um identificador de chamada com argumentos diferentes.');return
            result=json.loads(existing['result']) if existing['result'] else {'ok':False,'error':'Resultado incerto após interrupção. Não repetir automaticamente.'}
            self.consume_tool(result);return
        previous=self.history.previous_call(self.identifier,name,args) if name in MUTATIONS else None
        self.history.begin_call(self.identifier,call['id'],name,args)
        if previous:
            result=json.loads(previous['result']) if previous['result'] else {'ok':False,'error':'Operação idêntica já iniciada; resultado incerto. Verifica a recuperação antes de repetir.'}
            self.history.finish_call(self.identifier,call['id'],result);self.consume_tool(result);return
        if not self.state['settings']['tools_enabled']:
            result={'ok':False,'error':'Ferramentas locais desativadas nas definições.'}
            self.history.finish_call(self.identifier,call['id'],result);self.consume_tool(result);return
        self.state['actions'].append({'id':call['id'],'name':name,'arguments':args,'status':'running'})
        self.persist()
        self.launch_worker(self.tools_factory(self.cancel_event),name,args)

    def launch_worker(self,tools,name,args):
        self.waiting_tools=tools
        self.worker=ToolWorker(tools,name,args,self)
        self.worker.result.connect(self.worker_result);self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def worker_result(self,result):self.pending_result=result

    def worker_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        result=getattr(self,'pending_result',None) or {'ok':False,'error':'A execução terminou sem confirmar o resultado.'}
        self.pending_result=None
        call=self.state['pending'][0]
        if 'approval' in result and not self.cancel_event.is_set():
            self.state['approval']=result['approval'];self.state['status']='approval'
            self.history.finish_call(self.identifier,call['id'],{'ok':False,'error':'A aguardar confirmação.'},status='approval')
            for action in self.state['actions']:
                if action['id']==call['id']:action['status']='approval'
            self.persist();return
        self.history.finish_call(self.identifier,call['id'],result)
        self.consume_tool(result)

    def decide(self,token,allow):
        if not self.state or self.state['status']!='approval' or self.worker:return
        approval=self.state.get('approval')
        if not approval or approval['token']!=token:return
        self.waiting_tools.gate.decide(token,allow)
        self.state.pop('approval',None);call=self.state['pending'][0]
        if not allow:
            result={'ok':False,'error':'O utilizador recusou esta operação. Não voltar a propô-la nesta tarefa.'}
            self.history.finish_call(self.identifier,call['id'],result,status='denied')
            self.state['status']='tool';self.consume_tool(result);return
        # Preparation runs again. A changed target/version/plan needs a new approval.
        self.history.finish_call(self.identifier,call['id'],{'ok':False,'error':'Resultado incerto até confirmação da execução.'},status='running')
        self.state['status']='tool';self.persist()
        self.launch_worker(self.waiting_tools,call['function']['name'],json.loads(call['function']['arguments']))

    def consume_tool(self,result):
        call=self.state['pending'].pop(0)
        for action in self.state['actions']:
            if action['id']==call['id']:action['status']='complete' if result.get('ok') else 'failed';action['result']=result
        content=json.dumps({'untrusted_tool_data':result},ensure_ascii=False)
        if len(content)>131072:content=json.dumps({'ok':False,'error':'Resultado excede o limite de contexto; consulta um subconjunto.'})
        self.state['messages'].append({'role':'tool','tool_call_id':call['id'],'content':content})
        self.persist();QTimer.singleShot(0,self.next_tool)

    def settle_pending(self):
        for call in self.state.get('pending',[]):
            stored=self.history.call(self.identifier,call['id'])
            result=json.loads(stored['result']) if stored and stored['result'] else {'ok':False,'error':'Chamada interrompida. Se já foi iniciada, o resultado é incerto; não repetir sem verificação.'}
            self.state['messages'].append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
        self.state['pending']=[]

    def cancel(self):
        if not self.state:return
        self.cancel_event.set()
        waiting=getattr(self,'waiting_tools',None)
        if waiting and getattr(waiting,'gate',None):waiting.gate.clear()
        self.state.pop('approval',None)
        if self.stream.reply:self.stream.cancel()
        elif not self.worker:self.settle_pending();self.finish('interrupted')

    def finish(self,status,error=''):
        self.checkpoint.stop();self.state['status']=status;self.state['error']=error;self.persist();self.finished.emit()
