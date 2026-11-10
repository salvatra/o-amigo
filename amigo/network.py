"""Nonblocking bounded HTTPS stream; credentials never reach workers or diagnostics."""
import json
import math
import time
from PyQt6.QtCore import QObject,QTimer,QUrl,pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkReply
from quickask.core import SSEDecoder,error_message,ENDPOINT
from .protocol import Assembly

class Stream(QObject):
    changed=pyqtSignal(str)
    finished=pyqtSignal(str,str,object,dict)

    def __init__(self,parent=None,endpoint=ENDPOINT):
        super().__init__(parent);self.manager=QNetworkAccessManager(self);self.endpoint=endpoint;self.reply=None
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.timeout.connect(self.timeout)
        self.total=QTimer(self);self.total.setSingleShot(True);self.total.timeout.connect(self.timeout)
        self.batch=QTimer(self);self.batch.setSingleShot(True);self.batch.setInterval(32)
        self.batch.timeout.connect(lambda:self.changed.emit(self.assembly.text))

    def start(self,key,body):
        if self.reply:raise RuntimeError('One request at a time')
        self.assembly=Assembly();self.decoder=SSEDecoder();self.done=False;self.result=None;self.received=0;self.ending=False
        self.started=time.monotonic();self.generation=None
        request=QNetworkRequest(QUrl(self.endpoint))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,'application/json')
        request.setRawHeader(b'Authorization',('Bearer '+key).encode())
        request.setRawHeader(b'X-OpenRouter-Title',b'O Amigo')
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.reply=self.manager.post(request,json.dumps(body,ensure_ascii=False,allow_nan=False).encode())
        self.reply.readyRead.connect(self.read);self.reply.finished.connect(self.end)
        self.idle.start(60000);self.total.start(300000)

    def read(self):
        if not self.reply:return
        chunk=bytes(self.reply.readAll());self.received+=len(chunk);self.idle.start(60000)
        code=self.reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        if code>=300:return
        try:
            if self.received>16*1024**2:raise ValueError('Response too large')
            for event in self.decoder.feed(chunk):
                if event=='[DONE]':self.done=True;continue
                obj=json.loads(event)
                if obj.get('error'):
                    try:code=int(obj['error'].get('code',0))
                    except (TypeError,ValueError):code=0
                    self.result=('failed',error_message(code));self.reply.abort();return
                self.assembly.accept(obj)
                if obj.get('id'):self.generation=str(obj['id'])[:200]
            if not self.batch.isActive():self.batch.start()
        except (ValueError,TypeError,KeyError,AttributeError):
            self.result=('failed','O fornecedor devolveu uma resposta inválida. Nenhuma chamada incompleta foi executada.')
            self.reply.abort()

    def cancel(self):
        if self.reply:self.result=('interrupted','');self.reply.abort()

    def timeout(self):
        if self.reply:self.result=('failed','A ligação excedeu o tempo de espera.');self.reply.abort()

    def end(self):
        if not self.reply or self.ending:return
        self.ending=True
        self.read();reply=self.reply;self.reply=None
        self.idle.stop();self.total.stop();self.batch.stop()
        code=reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0;message=None
        if not self.result:
            if code>=300:self.result=('failed',error_message(code))
            elif reply.error()!=QNetworkReply.NetworkError.NoError:self.result=('failed',error_message(0,network=True))
            elif not self.done or not self.assembly.finish:self.result=('failed','A resposta terminou incompleta.')
            elif self.assembly.finish in ('error','content_filter'):self.result=('failed','O fornecedor não concluiu a resposta.')
            else:
                try:
                    message=self.assembly.assistant()
                    if not message.get('content') and not message.get('tool_calls'):raise ValueError('Empty')
                    self.result=('complete','')
                except (ValueError,TypeError):self.result=('failed','A resposta ou chamada de ferramenta terminou incompleta.')
        metadata={'elapsed':round(time.monotonic()-self.started,3),'provider':self.assembly.provider,
                  'generation_id':self.generation,'finish_reason':self.assembly.finish,'sources':self.assembly.sources}
        cost=self.assembly.usage.get('cost')
        if type(cost)in(int,float) and math.isfinite(cost) and cost>=0:metadata['cost']=cost
        details=self.assembly.usage.get('server_tool_use_details') or {}
        count=details.get('web_search_requests')
        if type(count)is int and count>=0:metadata['searches']=count
        self.changed.emit(self.assembly.text);reply.deleteLater();self.finished.emit(*self.result,message,metadata)
