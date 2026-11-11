"""Run separately from QCoreApplication unit tests: QT_QPA_PLATFORM=offscreen python tests/verify_ui.py.

Optional --capture-dir saves only synthetic demo data, never real conversations.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
import faulthandler
faulthandler.dump_traceback_later(40,exit=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QObject,QTimer,QUrl,Qt,qInstallMessageHandler
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtTest import QTest
from amigo.app import Service
from amigo.controller import Controller
from amigo.settings import Settings
from markdown_ui_fixture import verify_markdown

parser=argparse.ArgumentParser();parser.add_argument('--capture-dir',type=Path);parser.add_argument('--markdown-only',action='store_true');args=parser.parse_args()
os.umask(0o077);warnings=[]
qInstallMessageHandler(lambda kind,context,message:warnings.append(message))
app=QGuiApplication([]);app.setDesktopFileName('org.kde.oamigo');app.setQuitOnLastWindowClosed(False)
temporary=tempfile.TemporaryDirectory();base=Path(temporary.name)
controller=Controller(Settings(base/'settings.json'),base/'data',demo=True)
service=Service(controller)
# A visual fixture must not focus the separately installed application via KWin.
controller.visibilityChanged.disconnect(service.visibility)
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('controller',controller)
engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml/Main.qml')))
if not engine.rootObjects():print(json.dumps({'errors':warnings}));raise SystemExit(1)
root=engine.rootObjects()[0];outcome={'passed':False}

def capture(window,name):
    if args.capture_dir:
        args.capture_dir.mkdir(parents=True,exist_ok=True)
        assert window.grabWindow().save(str(args.capture_dir/(name+'.png')))

def verify():
    try:
        service.Show();QTest.qWait(350)
        popup=root.findChild(QQuickWindow,'amigoPopup');composer=root.findChild(QObject,'amigoComposer')
        assert popup is not None and composer is not None
        assert controller.visible
        capture(popup,'popup-empty')
        assert not root.findChild(QObject,'amigoTaskStatus').property('visible')
        assert not root.findChild(QObject,'amigoSend').property('enabled')
        composer.setProperty('text','Uma pergunta por enviar…');QTest.qWait(30);capture(popup,'popup-draft');composer.setProperty('text','')
        if args.markdown_only:
            controller.setPinned(True)
            checks=verify_markdown(controller,root,popup,capture)
            problems=[w for w in warnings if any(word in w for word in ('ReferenceError','TypeError','SyntaxError','Cannot assign','Unable to assign','Binding loop'))]
            assert not problems,problems
            outcome.update(passed=True,checks=checks,qml_errors=problems)
            return
        composer.setProperty('text','Teste de resposta');QTest.keyClick(popup,Qt.Key.Key_Return);QTest.qWait(100)
        assert len(controller.history.messages(controller.conversation))==2
        capture(popup,'popup-response')
        composer.setProperty('text','Primeira linha');QTest.keyClick(popup,Qt.Key.Key_Return,Qt.KeyboardModifier.ShiftModifier);QTest.qWait(50)
        assert '\n' in composer.property('text')
        previous=controller.conversation
        QTest.keyClick(popup,Qt.Key.Key_Escape);QTest.qWait(50);assert not controller.visible
        service.Show();QTest.qWait(100)
        assert controller.conversation==previous and 'Primeira linha' in composer.property('text')
        composer.setProperty('text','');service.Hide();QTest.qWait(50);service.Show();QTest.qWait(100)
        assert controller.conversation!=previous and composer.property('text')==''
        assert len(controller.history.messages(previous))==2
        assert [row['id'] for row in controller.history.conversations()]==[previous]
        fresh=controller.conversation
        composer.setProperty('text','Rascunho sem mensagem');service.Hide();QTest.qWait(50);service.Show();QTest.qWait(100)
        assert controller.conversation==fresh and composer.property('text')=='Rascunho sem mensagem'
        assert [row['id'] for row in controller.history.conversations()]==[previous]
        controller.selectConversation(previous);QTest.qWait(50);assert len(controller.rows)==2
        current=controller.conversation;service.Show();QTest.qWait(50);assert controller.conversation==current
        controller.openSettings();QTest.qWait(200)
        settings=root.findChild(QQuickWindow,'amigoSettings');assert settings and settings.isVisible()
        for index in range(7):
            settings.setProperty('category',index);QTest.qWait(50)
            if index in (0,3,6):capture(settings,'settings-'+str(index))
        settings.hide();controller.setPinned(True);service.Show();QTest.qWait(150)
        markdown_checks=verify_markdown(controller,root,popup,capture)
        # Contextual controls must keep cancellation and incomplete costs visible.
        controller.agent.state={'conversation':controller.conversation,'message_id':-1,'text':'','status':'requesting','providers':[], 'sources':[], 'actions':[], 'known_cost':0,'unknown_cost_rounds':0,'elapsed':0}
        controller.changed.emit();QTest.qWait(50)
        assert root.findChild(QObject,'amigoTaskStatus').property('visible')
        assert root.findChild(QObject,'amigoSend').property('text')=='Interromper'
        assert root.findChild(QObject,'amigoSend').property('enabled')
        capture(popup,'popup-working')
        controller.agent.state.update(status='complete',providers=['Fornecedor'],elapsed=1.2,known_cost=.000123,unknown_cost_rounds=1)
        controller.changed.emit();QTest.qWait(50);capture(popup,'popup-partial-cost')
        controller.agent.state=None
        controller.validated=False;controller.changed.emit();service.Show();QTest.qWait(100);capture(popup,'account-form')
        problems=[w for w in warnings if any(word in w for word in ('ReferenceError','TypeError','SyntaxError','Cannot assign','Unable to assign','Binding loop','is not defined'))]
        assert not problems,problems
        outcome.update(passed=True,checks=['native popup','Enter sends','Shift+Enter newline','Esc hides','fresh conversation without draft', 'unsent draft restored without history entry', 'old messages and draft retained', 'visible activation preserves current conversation','settings categories','account form']+markdown_checks,qml_errors=problems)
    except Exception:
        outcome['error']=traceback.format_exc();outcome['warnings']=warnings
    finally:app.exit(0)

QTimer.singleShot(0,verify);app.exec();print(json.dumps(outcome,ensure_ascii=False))
controller.close();temporary.cleanup();raise SystemExit(0 if outcome['passed'] else 1)
