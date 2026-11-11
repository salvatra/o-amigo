"""Native UI bridge. Credentials stay in memory/Secret Service, never in snapshots."""
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlsplit
from PyQt6.QtCore import QObject,QThread,QTimer,QUrl,QMetaType,pyqtProperty,pyqtSignal,pyqtSlot
from PyQt6.QtGui import QGuiApplication,QDesktopServices
from PyQt6.QtNetwork import QNetworkRequest,QNetworkReply
from PyQt6.QtDBus import QDBusArgument,QDBusConnection,QDBusMessage
from quickask.vault import Vault
from .agent import Agent
from .history import History
from .network import Stream
from .policy import Policy
from .protocol import request
from .settings_ui import schema
from .tools import Tools,schemas
from .transactions import Transactions
from .settings import validate
from .integration import set_shortcut
from .browser import Browser
from .approval import ApprovalGate
from .devices import Devices

def display_markdown(text):
    # Keep user/model Markdown passive: no images, HTML elements or file resources.
    text=re.sub(r'!\[([^\]]*)\]\([^)]*\)',r'[imagem: \1]',text)
    text=re.sub(r'!\[([^\]]*)\]\[[^\]]*\]',r'[imagem: \1]',text)
    text=text.replace('![','[')
    return text.replace('<','&lt;').replace('>','&gt;')

def approval_text(plan):
    lines=[plan.get('operation','Confirmar operação')]
    labels={'requested':'Pedido','printer':'Impressora','device_uri':'Destino','driver':'Controlador','description':'Descrição',
            'location':'Localização','file':'Ficheiro','bytes':'Tamanho em bytes','sha256':'SHA-256','copies':'Cópias',
            'action':'Ação','job':'Trabalho','before':'Estado atual','authentication':'Autenticação','irreversible':'Atenção'}
    for key,value in plan.items():
        if key=='operation' or value is None or value==[] or value=='':continue
        if key=='changes':
            for item in value:lines.append(f"{item['action']}: {item['name']} {item['version']} ({item['repository']})")
        else:
            text=json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(list,dict)) else str(value)
            lines.append(labels.get(key,key)+': '+text)
    return '\n\n'.join(lines)

class DeviceReader(QThread):
    result=pyqtSignal(str)
    def run(self):
        devices=Devices()
        try:self.result.emit(json.dumps({'devices':devices.identify()},ensure_ascii=False))
        except Exception:self.result.emit(json.dumps({'devices':[],'error':'Não foi possível consultar o UDisks.'}))
        finally:devices.close()

class Controller(QObject):
    changed=pyqtSignal()
    settingsChanged=pyqtSignal()
    showRequested=pyqtSignal()
    hideRequested=pyqtSignal()
    settingsRequested=pyqtSignal()
    quitRequested=pyqtSignal()
    visibilityChanged=pyqtSignal(bool)
    placementRequested=pyqtSignal(int,int,int,int)
    historyReady=pyqtSignal(str,bool)
    browserNotice=pyqtSignal(str)
    devicesReady=pyqtSignal(str)
    catalogReady=pyqtSignal(str)

    def __init__(self,settings,data_root,demo=False):
        super().__init__();self.settings=settings;self.data_root=Path(data_root);self.history=History(data_root)
        self.conversation=self.history.active();self.demo=demo;self._key='';self.validated=False;self.key_busy=False
        self.notice='';self.visible=False;self.pinned=settings.value['pinned'];self.draft='';self.rows=[];self.device_reader=None;self.catalog_reply=None
        self.vault=Vault(self,('application','o-amigo','provider','openrouter'),label='O Amigo — OpenRouter')
        self.test_stream=Stream(self);self.test_stream.finished.connect(self.key_test_finished)
        self.browser=Browser(self.data_root/'browser',settings.value['browser_idle_seconds'])
        self.browserNotice.connect(self.show_notice)
        self.approval_gate=ApprovalGate()
        self.reset_policy()
        self.agent=Agent(self.history,self.settings,self.make_tools,lambda:self._key,self)
        self.agent.changed.connect(self.changed);self.agent.finished.connect(self.completed)
        self.agent.restore(self.conversation);self.reload()
        if demo:
            self._key='demo';self.validated=True;self.notice='Modo de demonstração: sem chamadas pagas nem acesso a ficheiros pessoais.'
        else:self.vault.lookup(self.key_loaded)

    def reset_policy(self):
        old=getattr(self,'transactions',None)
        if old:old.close()
        value=self.settings.value
        self.policy=Policy(value['allowed_folders']+value['allowed_removable'],value['protected_folders'])
        self.transactions=Transactions(self.data_root/'recovery',self.policy,value['backup_bytes'],value['backup_days'])

    def make_tools(self,cancel):
        settings=self.settings.value
        disabled=settings['disabled_tools'] if settings['tools_enabled'] else [s['function']['name'] for s in schemas()]
        return Tools(self.policy,self.transactions,cancel,disabled,self.browser if settings['browser_enabled'] else None,self.approval_gate,settings['allowed_devices'])

    def show_notice(self,text):self.notice=text;self.changed.emit()

    def reload(self):
        rows=self.history.db.execute('SELECT * FROM messages WHERE conversation=? ORDER BY id DESC LIMIT 100',(self.conversation,)).fetchall()
        self.rows=[dict(row)|{'metadata':json.loads(row['metadata'])} for row in reversed(rows)]
        self.draft=self.history.setting('draft:'+self.conversation,'');self.changed.emit()

    @pyqtProperty(str,notify=changed)
    def stateJson(self):
        task=self.agent.state if self.agent.state and self.agent.state['conversation']==self.conversation else None
        rows=[]
        for row in self.rows:
            content=row['content'];status=row['status']
            if task and row['id']==task['message_id']:content=task['text']+self.agent.round_text;status=task['status']
            rows.append({'id':row['id'],'role':row['role'],'content':display_markdown(content),'raw':content,'status':status})
        return json.dumps({'ready':self.validated,'keyBusy':self.key_busy,'busy':self.agent.busy,'notice':self.notice,
                           'backgroundConversation':self.agent.state['conversation'] if self.agent.busy and not task and self.agent.state else '',
                           'conversation':self.conversation,'draft':self.draft,'messages':rows,'pinned':self.pinned,'browserEnabled':self.settings.value['browser_enabled'],
                           'task':{k:task.get(k) for k in ('status','error','rounds','searches','known_cost','unknown_cost_rounds','sources','providers','elapsed','recovery_blocked')} if task else None,
                           'approval':(task['approval']|{'summary':approval_text(task['approval']['plan'])}) if task and task.get('approval') else None,
                           'actions':[{'name':a['name'],'status':a['status'],
                                       'details':json.dumps({k:(v[:200]+'…' if isinstance(v,str) and len(v)>200 else v) for k,v in a['arguments'].items()},ensure_ascii=False,indent=2),
                                       'result':json.dumps(a.get('result',{}),ensure_ascii=False,indent=2)[:2000]} for a in task.get('actions',[])] if task else []},ensure_ascii=False)

    @pyqtProperty(str,notify=settingsChanged)
    def settingsJson(self):return json.dumps(self.settings.value,ensure_ascii=False)
    @pyqtProperty(str,constant=True)
    def settingsSchemaJson(self):return json.dumps(schema(),ensure_ascii=False)
    @pyqtProperty(str,constant=True)
    def toolsJson(self):return json.dumps([{'name':s['function']['name'],'description':s['function']['description']} for s in schemas()])
    @pyqtProperty(bool,constant=True)
    def externalClient(self):return False

    def key_loaded(self,ok,value):
        if ok and value:
            self._key=value;self.validated=self.history.setting('key_validated')=='true'
            if not self.validated:self.notice='A chave está guardada. Carrega em Testar ligação nas definições.'
        self.changed.emit()

    @pyqtSlot(str)
    def saveKey(self,value):
        if self.agent.busy or self.key_busy:return
        key=value.strip()
        if not 8<=len(key)<=512 or any(ch.isspace() for ch in key):self.notice='Introduz uma chave válida do OpenRouter.';self.changed.emit();return
        self.key_busy=True;self.changed.emit()
        def saved(ok,_):
            if not ok:self.key_busy=False;self.notice='Não foi possível guardar a chave no KWallet.';self.changed.emit();return
            self._key=key;self.validated=False;self.history.set_setting('key_validated','false');self.testKey()
        self.vault.save(key,saved)

    @pyqtSlot()
    def testKey(self):
        if self.agent.busy or self.test_stream.reply:return
        if self.demo:self.notice='Demonstração local.';self.changed.emit();return
        if not self._key:self.notice='Introduz a chave do OpenRouter.';self.key_busy=False;self.changed.emit();return
        self.key_busy=True;self.notice='A testar o modelo e os tetos de preço…';self.changed.emit()
        self.test_stream.start(self._key,request(self.settings.value,[{'role':'user','content':'Responde apenas OK.'}],search_budget=0))

    def key_test_finished(self,status,error,message,metadata):
        self.key_busy=False;self.validated=status=='complete';self.history.set_setting('key_validated','true' if self.validated else 'false')
        self.notice='Ligação validada. Pronto para conversar.' if self.validated else error;self.changed.emit()

    @pyqtSlot()
    def removeKey(self):
        if self.agent.busy or self.key_busy:return
        def removed(ok,_):
            if ok:self._key='';self.validated=False;self.history.set_setting('key_validated','false');self.notice='Chave removida do KWallet.'
            else:self.notice='Não foi possível remover a chave.'
            self.changed.emit()
        self.vault.remove(removed)

    @pyqtSlot(str,bool)
    def send(self,prompt,thinking=False):
        if not self.validated:self.notice='Valida primeiro a ligação ao OpenRouter.';self.changed.emit();return
        if self.demo:
            self.history.add(self.conversation,'user',prompt)
            self.history.add(self.conversation,'assistant','**O Amigo está pronto para a tua pergunta.**\n\nEsta resposta é uma demonstração local da interface.\n\n- Texto em português: ação, café e informação.\n- Respostas em Markdown e histórico local.\n- O trabalho pode continuar com o popup escondido.')
            self.history.set_setting('draft:'+self.conversation,'');self.reload();return
        try:
            self.agent.start(self.conversation,prompt,thinking);self.history.set_setting('draft:'+self.conversation,'');self.reload()
        except (ValueError,RuntimeError) as error:self.notice=str(error);self.changed.emit()

    @pyqtSlot(str)
    def setDraft(self,text):
        self.draft=text
        self.history.set_setting('draft:'+self.conversation,text[:131072])

    @pyqtSlot(str,bool)
    def decide(self,token,allow):self.agent.decide(token,allow)

    @pyqtSlot()
    def newConversation(self):
        self.conversation=self.history.new();self.notice='';self.reload();self.agent.restore(self.conversation)

    @pyqtSlot(str,int,result=str)
    def historyPage(self,query,offset):return json.dumps(self.history.conversations(query,offset),ensure_ascii=False)
    @pyqtSlot(str,int)
    def requestHistory(self,query,offset):self.historyReady.emit(self.historyPage(query,offset),offset>0)

    @pyqtSlot(str)
    def selectConversation(self,identifier):
        if not self.history.db.execute('SELECT id FROM conversations WHERE id=?',(identifier,)).fetchone():return
        self.conversation=identifier;self.history.set_setting('active',identifier);self.reload();self.agent.restore(identifier)

    @pyqtSlot(str)
    def deleteConversation(self,identifier):
        if self.agent.busy:return
        self.history.delete(identifier)
        if identifier==self.conversation:self.conversation=self.history.active();self.agent.restore(self.conversation)
        self.reload()

    @pyqtSlot()
    def cancel(self):self.agent.cancel()
    @pyqtSlot()
    def resume(self):self.agent.resume();self.reload()
    @pyqtSlot(str)
    def copy(self,text):QGuiApplication.clipboard().setText(text)
    @pyqtSlot(str)
    def openUrl(self,url):
        if urlsplit(url).scheme in ('https','http'):QDesktopServices.openUrl(QUrl(url))
    @pyqtSlot()
    def openSettings(self):self.settingsRequested.emit()
    @pyqtSlot()
    def showBrowser(self):
        if not self.settings.value['browser_enabled']:return
        def show():
            try:self.browser.request('show')
            except (RuntimeError,OSError,ValueError):self.browserNotice.emit('Não foi possível abrir o browser isolado.')
        threading.Thread(target=show,daemon=True).start()
    @pyqtSlot()
    def hide(self):self.hideRequested.emit()
    @pyqtSlot(bool)
    def setVisible(self,visible):
        opening=visible and not self.visible
        self.visible=visible
        if opening:self.newConversation()
        self.visibilityChanged.emit(visible)
    @pyqtSlot(bool)
    def setPinned(self,value):self.pinned=value;self.changed.emit()
    @pyqtSlot()
    def quit(self):self.quitRequested.emit()

    @pyqtSlot()
    def refreshDevices(self):
        if self.device_reader:return
        self.device_reader=DeviceReader(self);reader=self.device_reader
        reader.result.connect(self.devicesReady)
        def done():self.device_reader=None;reader.deleteLater()
        reader.finished.connect(done);reader.start()

    @pyqtSlot(str)
    def refreshCatalog(self,model):
        if self.catalog_reply:return
        req=QNetworkRequest(QUrl('https://openrouter.ai/api/v1/models'))
        req.setTransferTimeout(15000)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply=self.test_stream.manager.get(req);self.catalog_reply=reply;buffer=bytearray()
        def read():
            buffer.extend(bytes(reply.readAll()))
            if len(buffer)>8*1024**2:reply.abort()
        def done():
            read();result={'error':'Não foi possível consultar o catálogo de modelos.'}
            try:
                if reply.error()==QNetworkReply.NetworkError.NoError and reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)==200:
                    found=next((row for row in json.loads(buffer)['data'] if row['id']==model),None)
                    result={k:found.get(k) for k in ('id','name','context_length','supported_parameters','architecture')} if found else {'error':'Modelo não encontrado no catálogo atual; não foi alterado automaticamente.'}
            except (ValueError,KeyError,TypeError):pass
            self.catalog_reply=None;reply.deleteLater();self.catalogReady.emit(json.dumps(result,ensure_ascii=False))
        reply.readyRead.connect(read);reply.finished.connect(done)

    @pyqtSlot(str,result=str)
    def saveSettings(self,text):
        if self.agent.busy or self.key_busy:return 'Termina ou interrompe a tarefa antes de alterar definições.'
        try:
            value=validate(json.loads(text))
            if value['shortcut']!=self.settings.value['shortcut'] and not self.demo:set_shortcut(value['shortcut'])
            self.settings.save(value);self.reset_policy();self.pinned=self.settings.value['pinned']
            self.browser.idle_seconds=value['browser_idle_seconds']
            if not value['browser_enabled']:self.browser.close()
            self.settingsChanged.emit();self.changed.emit();return 'Definições guardadas.'
        except ValueError as error:return str(error)
        except OSError:return 'Não foi possível guardar a configuração.'

    @pyqtSlot(result=str)
    def recoveryList(self):return json.dumps(self.transactions.list(),ensure_ascii=False)
    @pyqtSlot(str,result=str)
    def undo(self,identifier):
        if self.agent.busy:return 'Interrompe ou termina a tarefa antes de recuperar ficheiros.'
        try:self.transactions.undo(identifier);return 'Operação desfeita e resultado verificado.'
        except (ValueError,RuntimeError,OSError) as error:return str(error)
    @pyqtSlot(str,result=str)
    def exportHistory(self,path):
        try:
            target=Path(path).expanduser()
            if not target.is_absolute() or target.exists():return 'Escolhe um novo ficheiro com caminho absoluto.'
            data=[dict(row)|{'messages':self.history.messages(row['id'])} for row in self.history.db.execute('SELECT * FROM conversations ORDER BY updated')]
            with target.open('x',encoding='utf-8') as file:json.dump(data,file,ensure_ascii=False,indent=2)
            target.chmod(0o600);return 'Histórico exportado.'
        except (ValueError,OSError):return 'Não foi possível exportar o histórico.'
    @pyqtSlot(result=str)
    def diagnostics(self):
        return json.dumps({'application':'O Amigo','model':self.settings.value['model'],'validated':self.validated,
                           'busy':self.agent.busy,'visible':self.visible,'pid':os.getpid(),'demo':self.demo},ensure_ascii=False,indent=2)
    def completed(self):
        self.reload()
        if not self.visible and self.settings.value['notifications'] and self.agent.state:
            message=QDBusMessage.createMethodCall('org.freedesktop.Notifications','/org/freedesktop/Notifications','org.freedesktop.Notifications','Notify')
            identifier=QDBusArgument(0,QMetaType.Type.UInt.value)
            from .integration import array
            message.setArguments(['O Amigo',identifier,'help-hint','O Amigo',
                                  'A tarefa terminou.' if self.agent.state['status']=='complete' else 'Há uma tarefa à espera de atenção.',
                                  array([],QMetaType.Type.QString),{},5000])
            QDBusConnection.sessionBus().asyncCall(message)
    def close(self):
        if self.catalog_reply:self.catalog_reply.abort()
        if self.device_reader:self.device_reader.wait(16000)
        self.browser.close();self.transactions.close();self.history.close();self._key=''
