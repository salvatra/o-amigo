"""Exercise the actual QML D-Bus widget bridge against a synthetic service."""
import json
import re
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QUrl,qInstallMessageHandler
from PyQt6.QtDBus import QDBusConnection
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine,QQmlExpression
from PyQt6.QtTest import QTest
from amigo.app import Service,OBJECT
SERVICE="org.kde.OAmigo.WidgetTest"
from amigo.controller import Controller
from amigo.settings import Settings

app=QGuiApplication([]);warnings=[];qInstallMessageHandler(lambda kind,context,message:warnings.append(message))
temporary=tempfile.TemporaryDirectory();root=Path(temporary.name)
controller=Controller(Settings(root/'settings.json'),root/'data',demo=True);service=Service(controller)
bus=QDBusConnection.sessionBus();assert bus.registerService(SERVICE)
bus.registerObject(OBJECT,service,QDBusConnection.RegisterOption.ExportAllSlots|QDBusConnection.RegisterOption.ExportAllSignals)
engine=QQmlApplicationEngine();directory=root/'ui';directory.mkdir()
source=(Path(__file__).resolve().parents[1]/'widget/contents/ui/Bridge.qml').read_text()
# A fixture-only bus name prevents missing-service checks from auto-starting the
# user's installed assistant, even if this test runs on the real session bus.
source=re.sub(r'\b(service|watchedService):\s*"org.kde.OAmigo"',lambda match:match[1]+': "'+SERVICE+'"',source)
(directory/'Bridge.qml').write_text(source)
engine.loadData(('''import QtQuick
import "'''+directory.as_uri()+'''"
Item { id: test; property alias bridge: backend; property string historyResult: ""
Bridge { id: backend }
Connections { target: backend; function onHistoryReady(text, append) { test.historyResult = text; } }
}''').encode(),QUrl.fromLocalFile(str(root/'test.qml')))
assert engine.rootObjects(),warnings
harness=engine.rootObjects()[0];bridge=harness.property('bridge')
def wait(predicate):
    deadline=time.monotonic()+3
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate(),warnings
def evaluate(code):
    expression=QQmlExpression(engine.rootContext(),bridge,code);expression.evaluate()
    assert not expression.hasError(),expression.error().toString()
wait(lambda:bridge.property('connected'))
wait(lambda:json.loads(bridge.property('stateJson'))['ready'])
evaluate('send("Olá widget", false)')
wait(lambda:len(json.loads(bridge.property('stateJson'))['messages'])==2)
evaluate('requestHistory("Olá", 0)');wait(lambda:bool(harness.property('historyResult')))
assert len(json.loads(harness.property('historyResult')))==1
previous=controller.conversation
evaluate('setDraft("Rascunho do widget")');wait(lambda:controller.draft=='Rascunho do widget')
evaluate('prepareConversation()');QTest.qWait(50)
assert controller.conversation==previous and controller.draft=='Rascunho do widget'
evaluate('setDraft("")');wait(lambda:controller.draft=='')
evaluate('prepareConversation()');wait(lambda:controller.conversation!=previous)
assert len(controller.history.conversations())==1
bus.unregisterService(SERVICE);wait(lambda:not bridge.property('connected'))
errors=[w for w in warnings if any(word in w for word in ('ReferenceError','TypeError','SyntaxError','Cannot assign','Unable to assign','Binding loop'))]
assert not errors,errors
print(json.dumps({'passed':True,'checks':['D-Bus snapshot','push updates','send','history','reopen keeps draft','empty reopen starts fresh','missing service']}))
controller.close();temporary.cleanup()
