"""Latest-wins background presentation cache; no history or credentials here."""
from collections import OrderedDict
import hashlib
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from .markdown import render


class RenderJob(QThread):
    result = pyqtSignal(object)

    def __init__(self, identifier, text, digest, parent):
        super().__init__(parent)
        self.identifier, self.text, self.digest = identifier, text, digest

    def run(self):
        try: blocks = render(self.text)
        except Exception:
            # Presentation errors must never lose a response or produce active HTML.
            blocks = [{'id': '0', 'kind': 'plain', 'text': self.text, 'indent': 0, 'quote': 0, 'marker': ''}]
        self.result.emit((self.identifier, self.digest, blocks))


class Presentation(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = OrderedDict(); self.pending = OrderedDict(); self.wanted = {}; self.worker = None
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(32)
        self.timer.timeout.connect(self.start)
        self.closed = False

    def get(self, identifier, text):
        digest = hashlib.blake2b(text.encode(), digest_size=16).digest()
        entry = self.cache.get(identifier)
        if entry: self.cache.move_to_end(identifier)
        if not entry or entry[0] != digest:
            if self.wanted.get(identifier) != digest:
                self.wanted[identifier] = digest
                self.pending[identifier] = (text, digest)
                if not self.worker and not self.timer.isActive(): self.timer.start()
        # Keep existing delegates during streaming; an initial block is plain text.
        return entry[1] if entry else ([{'id':'0','kind':'plain','text':text,'indent':0,'quote':0,'marker':''}] if text else [])

    def start(self):
        if self.closed or self.worker or not self.pending: return
        identifier, (text, digest) = self.pending.popitem(last=False)
        self.worker = RenderJob(identifier, text, digest, self)
        self.worker.result.connect(self.accept)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def accept(self, result):
        identifier, digest, blocks = result
        if self.closed: return
        # Jobs finish in order. Display each completed revision while a newer
        # one is queued, so a long stream cannot starve its visual updates.
        self.cache[identifier] = (digest, blocks)
        while len(self.cache) > 128:
            old, _ = self.cache.popitem(last=False); self.wanted.pop(old, None)
        self.changed.emit()

    def finished(self):
        self.worker.deleteLater(); self.worker = None
        if self.pending and not self.closed: self.timer.start()

    def close(self):
        self.closed = True; self.timer.stop(); self.pending.clear()
        if self.worker: self.worker.wait()
