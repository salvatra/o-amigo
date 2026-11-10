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
faulthandler.dump_traceback_later(15,exit=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QObject,QTimer,QUrl,Qt,qInstallMessageHandler
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtTest import QTest
from amigo.app import Service
from amigo.controller import Controller
from amigo.settings import Settings

parser=argparse.ArgumentParser();parser.add_argument('--capture-dir',type=Path);args=parser.parse_args()
os.umask(0o077);warnings=[]
qInstallMessageHandler(lambda kind,context,message:warnings.append(message))
app=QGuiApplication([]);app.setDesktopFileName('org.kde.oamigo');app.setQuitOnLastWindowClosed(False)
temporary=tempfile.TemporaryDirectory();base=Path(temporary.name)
controller=Controller(Settings(base/'settings.json'),base/'data',demo=True)
service=Service(controller);engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('controller',controller)
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
        composer.setProperty('text','Teste de resposta');QTest.keyClick(popup,Qt.Key.Key_Return);QTest.qWait(100)
        assert len(controller.history.messages(controller.conversation))==2
        capture(popup,'popup-response')
        composer.setProperty('text','Primeira linha');QTest.keyClick(popup,Qt.Key.Key_Return,Qt.KeyboardModifier.ShiftModifier);QTest.qWait(50)
        assert '\n' in composer.property('text')
        QTest.keyClick(popup,Qt.Key.Key_Escape);QTest.qWait(50);assert not controller.visible
        service.Show();QTest.qWait(100);assert 'Primeira linha' in composer.property('text')
        controller.openSettings();QTest.qWait(200)
        settings=root.findChild(QQuickWindow,'amigoSettings');assert settings and settings.isVisible()
        for index in range(7):
            settings.setProperty('category',index);QTest.qWait(50)
            if index in (0,3,6):capture(settings,'settings-'+str(index))
        settings.hide();controller.validated=False;controller.changed.emit();service.Show();QTest.qWait(100);capture(popup,'account-form')
        problems=[w for w in warnings if any(word in w for word in ('ReferenceError','TypeError','SyntaxError','Cannot assign','Unable to assign','Binding loop','is not defined'))]
        assert not problems,problems
        outcome.update(passed=True,checks=['native popup','Enter sends','Shift+Enter newline','Esc hides','draft retained','settings categories','account form'],qml_errors=problems)
    except Exception:
        outcome['error']=traceback.format_exc();outcome['warnings']=warnings
    finally:app.exit(0)

QTimer.singleShot(0,verify);app.exec();print(json.dumps(outcome,ensure_ascii=False))
controller.close();temporary.cleanup();raise SystemExit(0 if outcome['passed'] else 1)
