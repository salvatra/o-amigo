"""Application lifecycle, session D-Bus singleton and KDE focus integration."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
from PyQt6.QtCore import QObject, QTimer, pyqtClassInfo, pyqtSlot, Qt, QEvent
from PyQt6.QtDBus import QDBusConnection, QDBusMessage
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from .core import APP_ID, Store
from .network import Stream
from .vault import Vault
from .ui import Window


def kwin_action(action):
    message = QDBusMessage.createMethodCall('org.kde.kglobalaccel', '/component/kwin',
                                           'org.kde.kglobalaccel.Component', 'invokeShortcut')
    message.setArguments([action])
    QDBusConnection.sessionBus().asyncCall(message)


@pyqtClassInfo('D-Bus Interface', APP_ID)
class Service(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.window:
            if event.type() == QEvent.Type.Hide:
                kwin_action('Quick Ask Restore Focus')
            elif event.type() == QEvent.Type.Show:
                QTimer.singleShot(100, lambda: kwin_action('Quick Ask Focus'))
        return False

    @pyqtSlot(result=bool)
    def Toggle(self):
        if self.window.isVisible():
            self.Hide()
            return False
        self.Show()
        return True

    @pyqtSlot()
    def Show(self):
        self.window.show_window()

    @pyqtSlot()
    def Hide(self):
        self.window.hide()

    @pyqtSlot()
    def Quit(self):
        self.window.quit_callback()

    @pyqtSlot(result=str)
    def State(self):
        # Diagnostics expose no key, prompt, answer or conversation contents.
        focus = self.window.focusWidget()
        return json.dumps({'visible': self.window.isVisible(), 'active': self.window.isActiveWindow(),
                           'busy': self.window.busy, 'validated': self.window.ready,
                           'page': 'key' if self.window.pages.currentWidget() == self.window.key_page else 'chat',
                           'focus': 'key' if focus is self.window.key_input else 'composer' if focus is self.window.composer else 'other',
                           'pid': os.getpid()})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='Quick Ask — Super+F12')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--background', action='store_true')
    group.add_argument('--show', action='store_true')
    group.add_argument('--toggle', action='store_true')
    group.add_argument('--quit', action='store_true')
    # Capture the app's own empty key form for installation diagnostics; never a password.
    parser.add_argument('--capture-empty-form', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName('quick-ask')
    app.setOrganizationName('Quick Ask')
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon.fromTheme(APP_ID))
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print('Quick Ask: a sessão D-Bus não está disponível.', file=sys.stderr)
        return 1
    if not bus.registerService(APP_ID):
        if args.background:
            return 0
        action = 'Quit' if args.quit else 'Show' if args.show else 'Toggle'
        response = bus.call(QDBusMessage.createMethodCall(APP_ID, '/QuickAsk', APP_ID, action))
        return int(response.type() == QDBusMessage.MessageType.ErrorMessage)
    if args.quit:
        return 0
    data_root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'quick-ask'
    store = Store(data_root)
    quitting = False
    def quit_app():
        nonlocal quitting
        if quitting:
            return
        quitting = True
        window.shutdown()
        window.hide()
        app.quit()
    window = Window(store, Vault(), Stream(), quit_app)
    service = Service(window)
    bus.registerObject('/QuickAsk', service, QDBusConnection.RegisterOption.ExportAllSlots)
    tray = QSystemTrayIcon(QIcon.fromTheme(APP_ID), app)
    tray.setToolTip('Quick Ask · Super + F12')
    menu = QMenu()
    menu.addAction('Abrir / esconder', service.Toggle)
    menu.addAction('Nova conversa', lambda: (service.Show(), window.new_conversation()))
    menu.addAction('Definições', lambda: (service.Show(), window.settings()))
    menu.addSeparator()
    menu.addAction('Sair', quit_app)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: service.Toggle() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)
    signal.signal(signal.SIGTERM, lambda *_: quit_app())
    signal.signal(signal.SIGINT, lambda *_: quit_app())
    if not args.background:
        QTimer.singleShot(0, service.Show)
    if args.capture_empty_form:
        def capture():
            if window.pages.currentWidget() == window.key_page and not window.key_input.text():
                window.grab().save(str(args.capture_empty_form))
        QTimer.singleShot(1500, capture)
    result = app.exec()
    store.close()
    return result


if __name__ == '__main__':
    sys.exit(main())
