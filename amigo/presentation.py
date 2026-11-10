"""Native presentation harness. Does not replace the installed application."""
import json
import os
import sys
from pathlib import Path
from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from .settings import Settings

class Presentation(QObject):
    changed=pyqtSignal()
    settingsRequested=pyqtSignal()
    def __init__(self,settings):
        super().__init__(); self.settings=settings
    @pyqtProperty(str,notify=changed)
    def settingsJson(self): return json.dumps(self.settings.value,ensure_ascii=False,indent=2)
    @pyqtSlot(str,result=str)
    def saveSettings(self,text):
        try: self.settings.save(json.loads(text)); self.changed.emit(); return 'Guardado.'
        except (ValueError,OSError): return 'Configuração inválida; nada foi alterado.'
    @pyqtSlot()
    def openSettings(self): self.settingsRequested.emit()


def main():
    os.umask(0o077)
    app=QGuiApplication(sys.argv)
    app.setApplicationName('O Amigo — pré-visualização')
    app.setDesktopFileName('local.oamigo.preview')
    settings=Settings(Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'o-amigo-preview/settings.json')
    bridge=Presentation(settings)
    engine=QQmlApplicationEngine()
    engine.rootContext().setContextProperty('controller',bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'qml/Preview.qml')))
    if not engine.rootObjects(): return 1
    return app.exec()

if __name__=='__main__': sys.exit(main())
