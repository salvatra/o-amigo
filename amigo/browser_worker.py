"""Fixed browser worker, executed only inside the isolated browser namespace.

stdin/stdout carry structured commands/results. The model cannot supply JavaScript.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import urlsplit
sys.path.insert(0,'/app')
from amigo.web_policy import browsing_url
from amigo.web_proxy import relay
from PyQt6.QtCore import QCoreApplication,QSocketNotifier,QTimer,QUrl,Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication,QMainWindow,QToolBar,QLabel,QPushButton
from PyQt6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineSettings,QWebEngineUrlRequestInterceptor,QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView

WRITE_LOCK=threading.Lock()
def emit(value):
    with WRITE_LOCK:
        sys.stdout.write(json.dumps(value,ensure_ascii=False)+'\n');sys.stdout.flush()

def bridge():
    listener=socket.socket();listener.bind(('127.0.0.1',18737));listener.listen(32)
    def connection(local):
        remote=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:remote.connect('/gateway/proxy.sock');relay(local,remote)
        except (OSError,ValueError):pass
        finally:local.close();remote.close()
    while True:
        local,_=listener.accept();threading.Thread(target=connection,args=(local,),daemon=True).start()

class Interceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self,request):
        url=request.requestUrl();scheme=url.scheme()
        if scheme in ('data','blob') and request.resourceType()!=request.ResourceType.ResourceTypeMainFrame:return
        try:
            browsing_url(url.toString())
            if bytes(request.requestMethod()) not in (b'GET',b'HEAD',b'OPTIONS'):raise ValueError('Read-only browser')
        except ValueError:request.block(True)

class Page(QWebEnginePage):
    def acceptNavigationRequest(self,url,kind,main):
        try:browsing_url(url.toString());return True
        except ValueError:return False
    def chooseFiles(self,mode,old,mime):return []
    def javaScriptConsoleMessage(self,*args):pass

class Window(QMainWindow):
    def closeEvent(self,event):event.ignore();self.hide();emit({'event':'visibility','visible':False})

READ_SCRIPT=r'''(() => {
  const candidates = Array.from(document.querySelectorAll('a[href], button, input[type="search"], input[name="q"], input[name="query"], input[name="search"]')).slice(0,150);
  globalThis.__amigoTargets = candidates;
  return {title:document.title,url:location.href,text:(document.body?.innerText||'').slice(0,60000),
    elements:candidates.map((element,index)=>({id:index,tag:element.tagName.toLowerCase(),text:(element.innerText||element.getAttribute('aria-label')||element.placeholder||'').slice(0,180),url:element.href||''}))};
})()'''

class Browser:
    def __init__(self,app):
        self.app=app;self.window=Window();self.window.setWindowTitle('Browser — O Amigo');self.window.resize(1100,760)
        self.view=QWebEngineView(self.window);self.window.setCentralWidget(self.view)
        self.profile=QWebEngineProfile('o-amigo',self.window)
        self.profile.setPersistentStoragePath('/profile/storage');self.profile.setCachePath('/profile/cache')
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.interceptor=Interceptor(self.profile);self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page=Page(self.profile,self.view);self.view.setPage(self.page)
        self.page.setBackgroundColor(app.palette().color(QPalette.ColorRole.Base))
        for setting in (QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                        QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                        QWebEngineSettings.WebAttribute.AllowRunningInsecureContent):self.page.settings().setAttribute(setting,False)
        self.page.permissionRequested.connect(lambda permission:permission.deny())
        self.page.certificateError.connect(lambda error:error.rejectCertificate())
        self.page.authenticationRequired.connect(lambda url,auth:(auth.setUser(''),auth.setPassword('')))
        self.profile.downloadRequested.connect(self.download_requested)
        self.pending_download=None;self.pending=None;self.buffer=bytearray()
        self.timeout=QTimer();self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.timed_out)
        toolbar=QToolBar();toolbar.setMovable(False);self.window.addToolBar(toolbar)
        label=QLabel(' Browser isolado · sem contas pessoais ou publicação ');toolbar.addWidget(label)
        hide=QPushButton('Esconder');hide.clicked.connect(self.window.close);toolbar.addWidget(hide)
        self.notifier=QSocketNotifier(sys.stdin.fileno(),QSocketNotifier.Type.Read);self.notifier.activated.connect(self.read_commands)
        self.page.loadFinished.connect(self.loaded)

    def read_commands(self):
        data=os.read(sys.stdin.fileno(),65536)
        if not data:self.app.exit(0);return
        self.buffer.extend(data)
        if len(self.buffer)>1024**2:self.app.exit(1);return
        while b'\n' in self.buffer:
            line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            try:self.command(json.loads(line))
            except Exception:emit({'id':None,'ok':False,'error':'Invalid browser command'})

    def finish(self,result=None,error=None,identifier=None):
        if not self.pending or identifier is not None and self.pending!=identifier:return
        identifier=self.pending;self.pending=None;self.expected_download=None;self.timeout.stop()
        emit({'id':identifier,'ok':error is None,'result':result,'error':error})

    def callback(self,function):
        identifier=self.pending
        return lambda value:function(value) if self.pending==identifier else None

    def command(self,message):
        identifier=message['id'];operation=message['operation'];args=message.get('arguments',{})
        if operation=='show':
            self.window.show();self.window.raise_();self.window.activateWindow()
            emit({'event':'visibility','visible':True});emit({'id':identifier,'ok':True,'result':{'visible':True}});return
        if operation=='hide':
            self.window.hide();emit({'event':'visibility','visible':False});emit({'id':identifier,'ok':True,'result':{'visible':False}});return
        if operation=='quit':self.app.exit(0);return
        if operation=='cancel':
            self.page.triggerAction(QWebEnginePage.WebAction.Stop)
            if self.pending_download:self.pending_download.cancel();self.pending_download=None
            self.finish(error='Browser operation cancelled');return
        if self.pending:emit({'id':identifier,'ok':False,'error':'Browser already has work pending'});return
        self.pending=identifier;self.operation=operation;self.timeout.start(45000)
        try:
            if operation=='navigate':self.page.setUrl(QUrl(browsing_url(args['url'])))
            elif operation=='read':self.page.runJavaScript(READ_SCRIPT,QWebEngineScript.ScriptWorldId.ApplicationWorld,self.callback(self.finish))
            elif operation=='scroll':
                amount=max(-5,min(5,int(args['pages'])))
                self.page.runJavaScript(f'window.scrollBy(0,window.innerHeight*{amount}); true',QWebEngineScript.ScriptWorldId.ApplicationWorld,self.callback(lambda value:self.finish({'scrolled':bool(value)})))
            elif operation=='click':
                index=int(args['id'])
                script='''(() => { const e=globalThis.__amigoTargets?.[INDEX]; if(!e || !e.isConnected) return {error:'Stale element; read the page again'};
                  if(e.matches('a[href]')) return {navigate:e.href};
                  if(e.matches('button[type="button"],button:not([type])') && !e.closest('form')) {e.click();return {clicked:true};}
                  return {error:'Only navigation links and non-form buttons are allowed'}; })()'''.replace('INDEX',str(index))
                self.page.runJavaScript(script,QWebEngineScript.ScriptWorldId.ApplicationWorld,self.callback(self.clicked))
            elif operation=='search':
                index=int(args['id']);text=json.dumps(str(args['text'])[:1000])
                script='''(() => { const e=globalThis.__amigoTargets?.[INDEX]; if(!e || !e.isConnected || !e.matches('input[type="search"],input[name="q"],input[name="query"],input[name="search"]')) return {error:'Select a search field from the page snapshot'};
                  const f=e.form; if(!f || (f.method||'get').toLowerCase()!=='get' || f.querySelector('input[type="password"]')) return {error:'Only public GET search forms are allowed'};
                  const u=new URL(f.action||location.href,location.href); const p=new URLSearchParams(new FormData(f)); p.set(e.name||'q',TEXT);u.search=p.toString();return {navigate:u.href};})()'''.replace('INDEX',str(index)).replace('TEXT',text)
                self.page.runJavaScript(script,QWebEngineScript.ScriptWorldId.ApplicationWorld,self.callback(self.clicked))
            elif operation=='download':
                self.expected_download=args['filename'];self.expected_url=browsing_url(args['url']);self.timeout.start(180000)
                self.page.download(QUrl(browsing_url(args['url'])),self.expected_download)
            else:self.finish(error='Unknown browser capability')
        except (ValueError,KeyError,TypeError):self.finish(error='Invalid browser arguments')

    def clicked(self,value):
        if not isinstance(value,dict):self.finish(error='Page did not return a valid element');return
        if value.get('navigate'):
            try:self.page.setUrl(QUrl(browsing_url(value['navigate'])))
            except ValueError:self.finish(error='Navigation is outside the browser scope')
        elif value.get('error'):self.finish(error=value['error'])
        else:self.finish(value)

    def loaded(self,ok):
        if self.pending and self.operation in ('navigate','click','search') and not self.pending_download:
            if ok:self.page.runJavaScript(READ_SCRIPT,QWebEngineScript.ScriptWorldId.ApplicationWorld,self.callback(self.finish))
            else:self.finish(error='Page could not be loaded (network policy or remote failure)')

    def timed_out(self):
        self.page.triggerAction(QWebEnginePage.WebAction.Stop)
        if self.pending_download:self.pending_download.cancel();self.pending_download=None
        self.finish(error='Browser operation timed out')

    def download_requested(self,download):
        expected=getattr(self,'expected_download',None)
        if not self.pending or self.operation!='download' or not expected:download.cancel();return
        requested=QUrl(self.expected_url);actual=download.url()
        if not requested.path():requested.setPath('/')
        if not actual.path():actual.setPath('/')
        requested.setFragment('');actual.setFragment('')
        if actual!=requested:
            download.cancel();self.finish(error='Download URL changed; request the final public URL explicitly');return
        identifier=self.pending
        self.expected_download=None;self.pending_download=download
        download.setDownloadDirectory('/downloads');download.setDownloadFileName(expected)
        def progress():
            if download.receivedBytes()>512*1024**2 or download.totalBytes()>512*1024**2:download.cancel()
        def state():
            if not download.isFinished():return
            if self.pending_download is download:self.pending_download=None
            file=Path('/downloads')/expected
            if download.state()!=download.DownloadState.DownloadCompleted:
                file.unlink(missing_ok=True);self.finish(error='Download failed, cancelled or exceeded 512 MiB',identifier=identifier);return
            with file.open('rb') as source:sha=hashlib.file_digest(source,'sha256').hexdigest()
            self.finish({'filename':expected,'bytes':file.stat().st_size,'sha256':sha},identifier=identifier)
        download.receivedBytesChanged.connect(progress);download.totalBytesChanged.connect(progress)
        download.isFinishedChanged.connect(state);download.accept()

def main():
    os.umask(0o077);threading.Thread(target=bridge,daemon=True).start()
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(['o-amigo-browser']);app.setDesktopFileName('org.kde.oamigo.browser');app.setQuitOnLastWindowClosed(False)
    browser=Browser(app);emit({'event':'ready'});result=app.exec()
    browser.page.deleteLater();return result

if __name__=='__main__':sys.exit(main())
