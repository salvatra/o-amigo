"""Standalone Plasma popup, D-Bus singleton and event-driven process lifecycle."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
from PyQt6.QtCore import QObject,QTimer,QUrl,QSocketNotifier,pyqtClassInfo,pyqtSignal,pyqtSlot
from PyQt6.QtDBus import QDBusConnection,QDBusMessage
from PyQt6.QtGui import QGuiApplication,QCursor,QIcon
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow
from .settings import Settings
from .controller import Controller

SERVICE='org.kde.OAmigo'
INTERFACE='org.kde.OAmigo'
OBJECT='/OAmigo'
APP_ID='org.kde.oamigo'

def kwin_action(name):
    call=QDBusMessage.createMethodCall('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component','invokeShortcut')
    call.setArguments([name]);QDBusConnection.sessionBus().asyncCall(call)

@pyqtClassInfo('D-Bus Interface',INTERFACE)
class Service(QObject):
    StateChanged=pyqtSignal()
    def __init__(self,controller):
        super().__init__();self.controller=controller;controller.changed.connect(self.StateChanged)
        controller.visibilityChanged.connect(self.visibility)
        self.hover=QTimer(self);self.hover.setSingleShot(True);self.hover.timeout.connect(self.hover_open)
        self.hover_area=None
        controller.settingsChanged.connect(lambda:kwin_action('O Amigo Reload'))
    def visibility(self,visible):
        kwin_action('O Amigo Focus' if visible else 'O Amigo Restore Focus');self.StateChanged.emit()
    @pyqtSlot(result=bool)
    def Toggle(self):
        if self.controller.visible:self.Hide();return False
        self.Show();return True
    @pyqtSlot(int,int,int,int,result=bool)
    def ToggleAt(self,x,y,width,height):
        if self.controller.visible:self.Hide();return False
        self.ShowAt(x,y,width,height);return True
    @pyqtSlot()
    def Show(self):
        screen=QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area=screen.availableGeometry();self.ShowAt(area.x(),area.y(),area.width(),area.height())
    @pyqtSlot(int,int,int,int)
    def ShowAt(self,x,y,width,height):
        if width<100 or height<100:return
        self.controller.placementRequested.emit(x,y,width,height);self.controller.showRequested.emit()
    @pyqtSlot()
    def Hide(self):self.controller.hideRequested.emit()
    @pyqtSlot()
    def Settings(self):self.controller.openSettings()
    @pyqtSlot()
    def Quit(self):self.controller.quitRequested.emit()
    @pyqtSlot(result=str)
    def State(self):return self.controller.diagnostics()
    @pyqtSlot(result=str)
    def Snapshot(self):return self.controller.stateJson
    @pyqtSlot(str,bool)
    def Send(self,prompt,thinking):self.controller.send(prompt,thinking)
    @pyqtSlot()
    def NewConversation(self):self.controller.newConversation()
    @pyqtSlot()
    def PrepareConversation(self):self.controller.prepareConversation()
    @pyqtSlot()
    def Cancel(self):self.controller.cancel()
    @pyqtSlot(str,bool)
    def Decide(self,token,allow):self.controller.decide(token,allow)
    @pyqtSlot()
    def Continue(self):self.controller.resume()
    @pyqtSlot(str,int,result=str)
    def History(self,query,offset):return self.controller.historyPage(query,offset)
    @pyqtSlot(str)
    def SelectConversation(self,identifier):self.controller.selectConversation(identifier)
    @pyqtSlot(str)
    def DeleteConversation(self,identifier):self.controller.deleteConversation(identifier)
    @pyqtSlot(str)
    def SetDraft(self,text):self.controller.setDraft(text)
    @pyqtSlot(bool)
    def SetPinned(self,value):self.controller.setPinned(value)
    @pyqtSlot(str)
    def Copy(self,text):self.controller.copy(text)
    @pyqtSlot()
    def Browser(self):self.controller.showBrowser()
    @pyqtSlot(result=str)
    def IntegrationSettings(self):
        return json.dumps({k:self.controller.settings.value[k] for k in ('shortcut','hotspot_enabled','hotspot_width','hotspot_delay')})
    @pyqtSlot(int,int,int,int)
    def HotspotEnter(self,x,y,width,height):
        if not self.controller.settings.value['hotspot_enabled']:return
        self.hover_area=(x,y,width,height);self.hover.start(self.controller.settings.value['hotspot_delay'])
    @pyqtSlot()
    def HotspotLeave(self):self.hover.stop();self.hover_area=None
    def hover_open(self):
        if self.hover_area and not self.controller.visible:self.ShowAt(*self.hover_area)

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description='O Amigo — assistente nativo para KDE Plasma')
    action=parser.add_mutually_exclusive_group()
    for option in ('show','toggle','background','quit','settings'):action.add_argument('--'+option,action='store_true')
    parser.add_argument('--demo',action='store_true',help='Local UI demonstration without API or tools')
    parser.add_argument('--data-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--capture-demo',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.capture_demo and not args.demo:parser.error('Capture requires --demo')
    app=QGuiApplication([sys.argv[0]])
    app.setApplicationName('o-amigo');app.setOrganizationName('O Amigo');app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme('help-hint'));app.setQuitOnLastWindowClosed(False)
    bus=QDBusConnection.sessionBus();service_name=SERVICE+'.Demo' if args.demo else SERVICE
    if not bus.registerService(service_name):
        if args.background:return 0
        method='Quit' if args.quit else 'Show' if args.show else 'Settings' if args.settings else 'Toggle'
        reply=bus.call(QDBusMessage.createMethodCall(service_name,OBJECT,INTERFACE,method))
        return int(reply.type()==QDBusMessage.MessageType.ErrorMessage)
    if args.quit:return 0
    data=args.data_dir or Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/('o-amigo-demo' if args.demo else 'o-amigo')
    config=(data/'settings.json') if args.data_dir or args.demo else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'o-amigo/settings.json'
    controller=Controller(Settings(config),data,args.demo);service=Service(controller)
    bus.registerObject(OBJECT,service,QDBusConnection.RegisterOption.ExportAllSlots|QDBusConnection.RegisterOption.ExportAllSignals)
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('controller',controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml/Main.qml')))
    if not engine.rootObjects():controller.close();return 1
    quitting=False
    def shutdown():
        nonlocal quitting
        if quitting:return
        quitting=True
        if controller.agent.busy:
            controller.agent.finished.connect(lambda:app.exit(0));controller.agent.cancel()
        else:app.exit(0)
    controller.quitRequested.connect(shutdown)
    read_fd,write_fd=os.pipe2(os.O_NONBLOCK|os.O_CLOEXEC)
    signal.set_wakeup_fd(write_fd)
    signal.signal(signal.SIGTERM,lambda *_:None);signal.signal(signal.SIGINT,lambda *_:None)
    notifier=QSocketNotifier(read_fd,QSocketNotifier.Type.Read)
    def receive_signal():
        try:os.read(read_fd,4096)
        except BlockingIOError:pass
        shutdown()
    notifier.activated.connect(receive_signal)
    if not args.background:QTimer.singleShot(0,controller.openSettings if args.settings else service.Show)
    if args.capture_demo:
        def capture():
            for window in app.allWindows():
                if window.objectName()=='amigoPopup' and isinstance(window,QQuickWindow):window.grabWindow().save(str(args.capture_demo))
        QTimer.singleShot(1200,capture)
    result=app.exec()
    engine.setOutputWarningsToStandardError(False)
    from PyQt6 import sip
    sip.delete(engine);controller.close();signal.set_wakeup_fd(-1);os.close(read_fd);os.close(write_fd)
    return result

if __name__=='__main__':sys.exit(main())
