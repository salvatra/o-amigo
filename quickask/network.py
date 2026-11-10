"""Nonblocking HTTPS streaming. No logging of credentials, requests or errors."""
import json
import time
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from .core import ENDPOINT, SSEDecoder, error_message, request_body


class Stream(QObject):
    changed = pyqtSignal(str)
    finished = pyqtSignal(str, str, dict)  # status, safe error, metadata

    def __init__(self, parent=None, endpoint=ENDPOINT):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.endpoint = endpoint  # Only overridden by in-process tests; no user-configurable base URL.
        self.reply = None
        self.text = ''
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)
        self.total = QTimer(self)
        self.total.setSingleShot(True)
        self.total.timeout.connect(self.timeout)

    def start(self, key, messages, thinking=False):
        if self.reply:
            raise RuntimeError('Request already active')
        self.text = ''
        self.metadata = {}
        self.decoder = SSEDecoder()
        self.raw = bytearray()
        self.result = None
        self.got_done = False
        self.got_finish = False
        self.started = time.monotonic()
        req = QNetworkRequest(QUrl(self.endpoint))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        req.setRawHeader(b'Authorization', ('Bearer ' + key).encode())
        req.setRawHeader(b'X-OpenRouter-Title', b'Quick Ask')
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        data = json.dumps(request_body(messages, thinking), ensure_ascii=False).encode()
        self.reply = self.manager.post(req, data)
        self.reply.readyRead.connect(self.read)
        self.reply.finished.connect(self.end)
        self.timer.start(60000)
        self.total.start(300000 if thinking else 180000)

    def read(self):
        if not self.reply:
            return
        chunk = bytes(self.reply.readAll())
        self.timer.start(60000)
        code = self.reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if code and code >= 300:
            return  # Deliberately do not display or log raw error bodies.
        try:
            for event in self.decoder.feed(chunk):
                if event == '[DONE]':
                    self.got_done = True
                    continue
                obj = json.loads(event)
                if obj.get('error'):
                    err = obj['error']
                    try:
                        code = int(err.get('code', 0))
                    except (TypeError, ValueError):
                        code = 0
                    self.result = ('failed', error_message(code))
                    self.reply.abort()
                    return
                if obj.get('provider'):
                    self.metadata['provider'] = str(obj['provider'])[:100]
                if obj.get('id'):
                    self.metadata['generation_id'] = str(obj['id'])[:160]
                usage = obj.get('usage') or {}
                if isinstance(usage.get('cost'), (int, float)) and usage['cost'] >= 0:
                    self.metadata['cost'] = usage['cost']
                for field in ('prompt_tokens', 'completion_tokens'):
                    if isinstance(usage.get(field), int):
                        self.metadata[field] = usage[field]
                for choice in obj.get('choices') or []:
                    if choice.get('index', 0) != 0:
                        continue
                    delta = choice.get('delta') or {}
                    content = delta.get('content') or ''
                    if isinstance(content, str) and content:
                        self.text += content
                        self.changed.emit(self.text)
                    reason = choice.get('finish_reason')
                    if reason:
                        self.got_finish = True
                        self.metadata['finish_reason'] = reason
                        if reason == 'error':
                            self.result = ('failed', error_message(502))
        except (ValueError, TypeError, AttributeError):
            self.result = ('failed', 'O fornecedor devolveu uma resposta inválida. Tenta novamente.')
            self.reply.abort()

    def cancel(self):
        if self.reply:
            self.result = ('interrupted', '')
            self.reply.abort()

    def timeout(self):
        if self.reply:
            self.result = ('failed', 'A ligação excedeu o tempo de espera. Tenta novamente.')
            self.reply.abort()

    def end(self):
        if not self.reply:
            return
        self.read()
        reply, self.reply = self.reply, None
        self.timer.stop()
        self.total.stop()
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        if not self.result:
            if code >= 300:
                self.result = ('failed', error_message(code))
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                self.result = ('failed', error_message(0, network=True))
            elif not self.got_done or not self.text.strip():
                self.result = ('failed', 'A resposta terminou incompleta ou vazia. Podes tentar novamente.')
            else:
                self.result = ('complete', '')
        self.metadata['elapsed'] = round(time.monotonic() - self.started, 2)
        reply.deleteLater()
        self.finished.emit(*self.result, self.metadata.copy())
