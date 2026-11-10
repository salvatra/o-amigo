"""Native KWin integration check. Uses a temporary demo service and unloads its scripts."""
import faulthandler
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QObject,QTimer,QUrl,QPoint,pyqtClassInfo,pyqtSlot
from PyQt6.QtDBus import QDBusConnection,QDBusMessage
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtTest import QTest
from amigo.app import Service,SERVICE,OBJECT,INTERFACE
from amigo.controller import Controller
from amigo.settings import Settings

faulthandler.dump_traceback_later(30,exit=True)
os.umask(0o077);app=QGuiApplication([]);app.setDesktopFileName('org.kde.oamigo');app.setQuitOnLastWindowClosed(False)
temporary=tempfile.TemporaryDirectory();root=Path(temporary.name)
controller=Controller(Settings(root/'settings.json'),root/'data',demo=True);service=Service(controller)
bus=QDBusConnection.sessionBus();assert bus.registerService(SERVICE),'Stop the real service before running isolated demo validation'
bus.registerObject(OBJECT,service,QDBusConnection.RegisterOption.ExportAllSlots|QDBusConnection.RegisterOption.ExportAllSignals)
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('controller',controller)
engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml/Main.qml')));assert engine.rootObjects()

def dbus(target,path,iface,method,*args):
    message=QDBusMessage.createMethodCall(target,path,iface,method);message.setArguments(list(args));reply=bus.call(message)
    if reply.type()==QDBusMessage.MessageType.ErrorMessage:raise RuntimeError(reply.errorName()+': '+reply.errorMessage())
    return reply.arguments()

@pyqtClassInfo('D-Bus Interface','org.kde.OAmigo.Probe')
class Probe(QObject):
    result=None
    @pyqtSlot(str)
    def Report(self,value):self.result=json.loads(value)
probe=Probe();bus.registerObject('/Probe',probe,QDBusConnection.RegisterOption.ExportAllSlots)

def scripting(method,*args):return dbus('org.kde.KWin','/Scripting','org.kde.kwin.Scripting',method,*args)
def snapshot():
    probe.result=None
    script=root/'probe.js'
    script.write_text('''function info(w) { return w ? {id:String(w.internalId),own:String(w.resourceClass)==='org.kde.oamigo',all:w.onAllDesktops,skip:w.skipSwitcher,active:w.active,caption:String(w.caption),geometry:{x:w.frameGeometry.x,y:w.frameGeometry.y,width:w.frameGeometry.width,height:w.frameGeometry.height}} : null; }
callDBus('org.kde.OAmigo','/Probe','org.kde.OAmigo.Probe','Report',JSON.stringify({active:info(workspace.activeWindow),windows:workspace.stackingOrder.filter(w=>String(w.resourceClass)==='org.kde.oamigo').map(info),desktop:workspace.currentDesktop.id,screens:workspace.screens.map(s=>({name:s.name,geometry:s.geometry}))}));''')
    scripting('unloadScript','o-amigo-validation-probe');scripting('loadScript',str(script),'o-amigo-validation-probe');scripting('start')
    deadline=time.monotonic()+2
    while probe.result is None and time.monotonic()<deadline:QTest.qWait(10)
    assert probe.result is not None,'KWin probe did not respond'
    return probe.result

def shortcut():dbus('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component','invokeShortcut','O Amigo Toggle')

result={}
def verify():
    try:
        scripting('unloadScript','o-amigo-validation')
        scripting('loadScript',str(Path(__file__).resolve().parents[1]/'kwin/contents/code/main.js'),'o-amigo-validation');scripting('start');QTest.qWait(100)
        before=snapshot();start=time.monotonic();shortcut()
        while not controller.visible and time.monotonic()-start<2:QTest.qWait(5)
        shown_latency=(time.monotonic()-start)*1000;QTest.qWait(100);shown=snapshot()
        assert controller.visible,'KDE shortcut did not open popup'
        assert shown['desktop']==before['desktop'],'Popup changed the current desktop'
        assert shown['active'] and shown['active']['own'],'Popup did not receive focus'
        assert shown['windows'][0]['all'] and shown['windows'][0]['skip'],'Popup workspace/task-switcher policy failed'
        geometry=shown['windows'][0]['geometry'];screen=shown['screens'][0]['geometry']
        result['position_debug']={'geometry':geometry,'screen':screen,'available':str(engine.rootObjects()[0].property('available')),'qml_x':engine.rootObjects()[0].findChild(QQuickWindow,'amigoPopup').x()}
        assert abs(geometry['x']-(screen['x']+(screen['width']-geometry['width'])/2))<=2,'Popup is not centered'
        shortcut();QTest.qWait(150);hidden=snapshot();assert not controller.visible
        if before['active']:assert hidden['active'] and hidden['active']['id']==before['active']['id'],'Previous focus was not restored'
        # The service timer only opens, never toggles; leaving before delay cancels.
        service.HotspotEnter(0,30,1440,870);QTest.qWait(100);service.HotspotLeave();QTest.qWait(250);assert not controller.visible
        service.HotspotEnter(0,30,1440,870);QTest.qWait(350);assert controller.visible
        service.HotspotEnter(0,30,1440,870);QTest.qWait(350);assert controller.visible
        service.Hide();service.HotspotLeave()
        result.update(passed=True,shortcut_focus_restore=True,desktop_preserved=True,hotspot_timer=True,warm_open_ms=round(shown_latency,2),geometry=shown['windows'][0]['geometry'])
    except Exception:result.update(passed=False,error=traceback.format_exc())
    finally:
        scripting('unloadScript','o-amigo-validation');scripting('unloadScript','o-amigo-validation-probe');app.exit(0)
QTimer.singleShot(0,verify);app.exec();controller.close();temporary.cleanup();print(json.dumps(result));raise SystemExit(0 if result.get('passed') else 1)
