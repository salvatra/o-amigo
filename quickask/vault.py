"""The secret is passed via stdin, never via argv, files or debug output."""
from PyQt6.QtCore import QObject, QProcess, QTimer


class Vault(QObject):
    def __init__(self, parent=None, attributes=('application', 'quick-ask', 'provider', 'openrouter')):
        super().__init__(parent)
        self.processes = set()
        self.attributes = attributes

    def run(self, action, callback, key=''):
        process = QProcess(self)
        self.processes.add(process)
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)
        args = [action]
        if action == 'store':
            args += ['--label=Quick Ask — OpenRouter']
        args += list(self.attributes)
        completed = False

        def done(code=1, *_):
            nonlocal completed
            if completed:
                return
            completed = True
            timer.stop()
            value = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').rstrip('\n') if action == 'lookup' else ''
            process.readAllStandardError()  # Never forward secret-tool errors or debug output.
            self.processes.discard(process)
            process.deleteLater()
            callback(code == 0, value)

        process.finished.connect(done)
        process.errorOccurred.connect(lambda _: done(1) if process.state() == QProcess.ProcessState.NotRunning else None)
        process.start('secret-tool', args)
        if action == 'store':
            process.write(key.encode('utf-8'))
            process.closeWriteChannel()
        timer.start(30000)

    def lookup(self, callback):
        self.run('lookup', callback)

    def save(self, key, callback):
        self.run('store', callback, key)

    def remove(self, callback):
        self.run('clear', callback)
