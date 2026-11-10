"""Native Qt widgets; credentials never enter conversation storage."""
from html import escape
import json
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QTextDocument, QDesktopServices, QIcon, QCursor
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QTextBrowser, QStackedWidget, QCheckBox,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QMenu)
from .core import MODEL


class Composer(QPlainTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class Transcript(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.follow)

    def loadResource(self, resource_type, name):
        # Model output must not fetch remote tracking pixels or local files.
        return None

    def follow(self, url):
        if url.scheme() in ('https', 'http'):
            QDesktopServices.openUrl(url)


def button(text, callback, icon=None):
    widget = QPushButton(text)
    if icon:
        widget.setIcon(QIcon.fromTheme(icon))
    widget.clicked.connect(callback)
    return widget


def markdown_html(text):
    document = QTextDocument()
    document.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                         QTextDocument.MarkdownFeature.MarkdownNoHTML)
    rendered = document.toHtml()
    return rendered.split('<body', 1)[1].split('>', 1)[1].rsplit('</body>', 1)[0]


class Window(QWidget):
    def __init__(self, store, vault, stream, quit_callback):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Quick Ask')
        self.setObjectName('quickAsk')
        self.setWindowIcon(QIcon.fromTheme('local.quickask'))
        self.resize(760, 560)
        self.setMinimumSize(540, 420)
        self.store, self.vault, self.stream = store, vault, stream
        self.quit_callback = quit_callback
        self.key = ''
        self.ready = False
        self.busy = False
        self.testing = False
        self.loading = True
        self.active = store.active()
        self.pending = None
        self.dirty = False
        self.drafts = {}
        self.persist_timer = QTimer(self)
        self.persist_timer.setInterval(600)
        self.persist_timer.timeout.connect(self.persist_partial)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(60)
        self.render_timer.timeout.connect(self.render)
        self.stream.changed.connect(self.on_chunk)
        self.stream.finished.connect(self.on_finished)
        self.build()
        self.shortcuts = []
        for key, callback in [('Escape', self.hide), ('Ctrl+N', self.new_conversation)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.vault.lookup(self.loaded_key)

    def build(self):
        self.setStyleSheet('''
            QWidget#quickAsk { background: palette(window); }
            QPushButton { padding: 6px 10px; }
            QLineEdit, QPlainTextEdit { padding: 8px; border-radius: 7px; }
            QTextBrowser { border: none; background: palette(base); border-radius: 8px; padding: 10px; }
            QLabel#title { font-size: 22px; font-weight: 600; }
            QLabel#muted { color: palette(mid); }
            QPushButton#primary { background: palette(highlight); color: palette(highlighted-text); border-radius: 6px; }
        ''')
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        self.pages = QStackedWidget()
        root.addWidget(self.pages)
        self.build_key_page()
        self.build_chat_page()
        self.pages.setCurrentWidget(self.key_page)

    def build_key_page(self):
        self.key_page = QWidget()
        layout = QVBoxLayout(self.key_page)
        layout.setContentsMargins(40, 15, 40, 12)
        top = QHBoxLayout()
        title = QLabel('Quick Ask')
        title.setObjectName('title')
        top.addWidget(title)
        top.addStretch()
        self.back = button('Voltar', self.back_to_chat, 'go-previous')
        self.back.hide()
        top.addWidget(self.back)
        layout.addLayout(top)
        layout.addStretch(1)
        heading = QLabel('Uma pergunta. Uma resposta. De volta ao que estavas a fazer.')
        heading.setWordWrap(True)
        heading.setStyleSheet('font-size: 18px; font-weight: 600;')
        layout.addWidget(heading)
        description = QLabel('DeepSeek V4.1 Flash 1017 · OpenRouter\nSuper + F12 para abrir ou esconder, em qualquer ambiente de trabalho.')
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(12)
        label = QLabel('Chave API do OpenRouter')
        layout.addWidget(label)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText('Cola aqui a tua chave')
        self.key_input.setClearButtonEnabled(True)
        self.key_input.returnPressed.connect(self.save_key)
        label.setBuddy(self.key_input)
        layout.addWidget(self.key_input)
        privacy = QLabel('Guardada no KWallet. Não fica nas configurações nem no histórico.')
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        row = QHBoxLayout()
        self.save_button = button('Guardar e testar', self.save_key)
        self.save_button.setObjectName('primary')
        self.save_button.setEnabled(False)
        row.addWidget(self.save_button)
        self.remove_button = button('Remover chave', self.remove_key)
        self.remove_button.hide()
        row.addWidget(self.remove_button)
        row.addStretch()
        layout.addLayout(row)
        self.key_status = QLabel('A consultar o KWallet…')
        self.key_status.setWordWrap(True)
        self.key_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.key_status)
        layout.addStretch(1)
        caps = QLabel('Seleção equilibrada · teto por milhão de tokens: $0,30 entrada / $1,20 saída\nRespostas até 1.024 tokens; “Pensar mais” até 4.096.')
        caps.setWordWrap(True)
        caps.setStyleSheet('font-size: 11px;')
        layout.addWidget(caps)
        footer = QHBoxLayout()
        footer.addWidget(button('Obter chave ↗', lambda: QDesktopServices.openUrl(QUrl('https://openrouter.ai/settings/keys'))))
        footer.addStretch()
        footer.addWidget(button('Sair', self.quit_callback))
        layout.addLayout(footer)
        self.pages.addWidget(self.key_page)

    def build_chat_page(self):
        self.chat_page = QWidget()
        layout = QVBoxLayout(self.chat_page)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel('Quick Ask')
        title.setObjectName('title')
        titles.addWidget(title)
        subtitle = QLabel('DeepSeek V4.1 Flash 1017 · OpenRouter')
        subtitle.setStyleSheet('font-size: 11px;')
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.history_button = button('Histórico', self.toggle_history, 'view-history')
        self.new_button = button('Nova', self.new_conversation, 'document-new')
        self.settings_button = button('Definições', self.settings, 'configure')
        for widget in (self.history_button, self.new_button, self.settings_button):
            header.addWidget(widget)
        layout.addLayout(header)
        splitter = QSplitter()
        self.history_panel = QWidget()
        hbox = QVBoxLayout(self.history_panel)
        hbox.setContentsMargins(0, 0, 8, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Pesquisar conversas…')
        self.search.textChanged.connect(self.refresh_history)
        self.history = QListWidget()
        self.history.itemActivated.connect(self.choose_conversation)
        self.history.itemClicked.connect(self.choose_conversation)
        self.delete_button = button('Eliminar conversa', self.delete_conversation, 'edit-delete')
        hbox.addWidget(self.search)
        hbox.addWidget(self.history)
        hbox.addWidget(self.delete_button)
        splitter.addWidget(self.history_panel)
        self.history_panel.hide()
        self.transcript = Transcript()
        splitter.addWidget(self.transcript)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([210, 510])
        layout.addWidget(splitter, 1)
        self.notice = QLabel('')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        actions = QHBoxLayout()
        self.thinking = QCheckBox('Pensar mais')
        self.thinking.setToolTip('Ativa raciocínio e permite até 4.096 tokens de saída. Pode demorar e custar mais.')
        actions.addWidget(self.thinking)
        actions.addStretch()
        self.copy_button = button('Copiar resposta', self.copy_answer, 'edit-copy')
        actions.addWidget(self.copy_button)
        layout.addLayout(actions)
        self.composer = Composer()
        self.composer.setPlaceholderText('O que queres saber?')
        self.composer.setFixedHeight(76)
        self.composer.submitted.connect(self.send)
        layout.addWidget(self.composer)
        bottom = QHBoxLayout()
        hint = QLabel('Enter enviar · Shift+Enter nova linha · Esc esconder')
        hint.setStyleSheet('font-size: 10px;')
        bottom.addWidget(hint)
        bottom.addStretch()
        self.stop_button = button('Interromper', self.stream.cancel, 'process-stop')
        self.stop_button.hide()
        self.send_button = button('Perguntar', self.send, 'mail-send')
        self.send_button.setObjectName('primary')
        bottom.addWidget(self.stop_button)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        self.pages.addWidget(self.chat_page)
        self.render()

    def loaded_key(self, ok, value):
        self.loading = False
        self.save_button.setEnabled(True)
        if ok and value:
            self.key = value
            self.ready = self.store.setting('validated') == 'yes'
            self.remove_button.show()
            self.back.setVisible(self.ready)
            if self.ready:
                self.back_to_chat()
            else:
                self.key_status.setText('Existe uma chave guardada. Carrega em “Guardar e testar” para validar a ligação.')
        else:
            self.key_status.setText('Cola a chave e valida a ligação para começar.')
        self.focus_input()

    def save_key(self):
        if self.busy or self.loading:
            return
        candidate = self.key_input.text().strip() or self.key
        if not candidate:
            self.key_status.setText('Cola primeiro a tua chave do OpenRouter.')
            return
        if any(c.isspace() for c in candidate) or not candidate.isascii():
            self.key_status.setText('A chave contém espaços ou caracteres inválidos. Confirma o que colaste.')
            return
        self.set_busy(True)
        self.ready = False
        self.store.set_setting('validated', 'no')
        self.key_status.setText('A guardar no KWallet…')

        def saved(ok, _):
            if not ok:
                self.set_busy(False)
                self.key_status.setText('Não foi possível guardar no KWallet. Verifica se a carteira está desbloqueada.')
                return
            self.key = candidate
            self.key_input.clear()
            self.remove_button.show()
            self.testing = True
            self.key_status.setText('Chave guardada. A testar o DeepSeek com os limites configurados…')
            self.stream.start(self.key, [{'role': 'user', 'content': 'Responde apenas: OK'}], False)
        self.vault.save(candidate, saved)

    def remove_key(self):
        if self.busy:
            return
        answer = QMessageBox.question(self, 'Remover chave', 'Remover a chave do KWallet? O histórico será mantido.')
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.set_busy(True)
        def removed(ok, _):
            self.set_busy(False)
            if ok:
                self.key = ''
                self.ready = False
                self.key_input.clear()
                self.store.set_setting('validated', 'no')
                self.remove_button.hide()
                self.back.hide()
                self.key_status.setText('Chave removida. O histórico foi mantido.')
            else:
                self.key_status.setText('Não foi possível remover a chave do KWallet.')
        self.vault.remove(removed)

    def settings(self):
        if self.busy:
            return
        self.key_input.clear()
        self.back.setVisible(self.ready)
        self.key_status.setText('Ligação validada. A chave está guardada no KWallet.' if self.ready else 'Ligação ainda não validada.')
        self.pages.setCurrentWidget(self.key_page)
        self.focus_input()

    def back_to_chat(self):
        if self.ready:
            self.pages.setCurrentWidget(self.chat_page)
            self.render()
            self.focus_input()

    def set_busy(self, value):
        self.busy = value
        for widget in (self.new_button, self.history, self.delete_button, self.settings_button,
                       self.thinking, self.save_button, self.remove_button, self.key_input, self.back):
            widget.setEnabled(not value)
        self.send_button.setVisible(not value)
        self.stop_button.setVisible(value)
        self.composer.setReadOnly(value)

    def send(self):
        text = self.composer.toPlainText().strip()
        if not text or self.busy or not self.ready:
            return
        self.store.add(self.active, 'user', text)
        context = self.store.context(self.active)
        self.pending = self.store.add(self.active, 'assistant', '', 'streaming')
        self.partial = ''
        self.composer.clear()
        self.drafts.pop(self.active, None)
        self.notice.setText('A pensar…' if self.thinking.isChecked() else 'A responder…')
        self.set_busy(True)
        self.render(scroll=True)
        self.persist_timer.start()
        self.stream.start(self.key, context, self.thinking.isChecked())

    def on_chunk(self, text):
        if self.testing:
            return
        self.partial = text
        self.dirty = True
        self.notice.setText('A responder…')
        if not self.render_timer.isActive():
            self.render_timer.start()

    def persist_partial(self):
        if self.pending and self.dirty:
            self.store.update(self.pending, self.partial, 'streaming')
            self.dirty = False

    def on_finished(self, status, error, metadata):
        self.persist_timer.stop()
        self.render_timer.stop()
        if self.testing:
            self.testing = False
            self.set_busy(False)
            if status == 'complete':
                self.ready = True
                self.store.set_setting('validated', 'yes')
                self.back_to_chat()
                self.notice.setText('Ligação validada. Podes fazer a primeira pergunta.')
            else:
                self.key_status.setText(error or 'Teste interrompido. Podes voltar a tentar.')
            return
        if self.pending:
            metadata = metadata | ({'error': error} if error else {})
            self.store.update(self.pending, self.stream.text, status, metadata)
        self.pending = None
        self.set_busy(False)
        self.notice.setText(error if error else ('Resposta interrompida.' if status == 'interrupted' else ''))
        self.render()
        if self.isVisible():
            self.composer.setFocus()

    def render(self, scroll=False):
        if not hasattr(self, 'transcript'):
            return
        bar = self.transcript.verticalScrollBar()
        follow = scroll or bar.maximum() - bar.value() < 35
        old = bar.value()
        messages = self.store.messages(self.active)
        if not messages:
            self.transcript.setHtml('<h2>Uma dúvida rápida?</h2><p>Escreve a tua pergunta. Podes continuar a conversa ou começar outra com <b>Ctrl + N</b>.</p>')
        else:
            sections = []
            for m in messages:
                content = self.partial if self.pending == m['id'] else m['content']
                who = 'Tu' if m['role'] == 'user' else 'DeepSeek'
                details = []
                if m['role'] == 'assistant':
                    labels = {'streaming': 'A responder…', 'interrupted': 'Interrompida', 'failed': 'Falhou'}
                    if m['status'] in labels:
                        details.append(labels[m['status']])
                    meta = m['metadata']
                    if meta.get('provider'):
                        details.append(meta['provider'])
                    if 'elapsed' in meta:
                        details.append(f"{meta['elapsed']:.1f} s")
                    if 'cost' in meta:
                        details.append(f"${meta['cost']:.8g} · custo comunicado pela API")
                    if meta.get('finish_reason') == 'length':
                        details.append('Limite de tokens atingido')
                    if meta.get('error'):
                        details.append(meta['error'])
                sections.append('<p><b>' + who + '</b></p>' + markdown_html(content or '…') +
                                ('<p><small>' + escape(' · '.join(details)) + '</small></p>' if details else '') + '<hr>')
            self.transcript.setHtml(''.join(sections))
        bar.setValue(bar.maximum() if follow else old)
        self.copy_button.setEnabled(any(m['role'] == 'assistant' and m['content'] for m in messages))

    def copy_answer(self):
        if self.pending and self.stream.text:
            QApplication.clipboard().setText(self.stream.text)
            return
        for m in reversed(self.store.messages(self.active)):
            if m['role'] == 'assistant' and m['content']:
                QApplication.clipboard().setText(m['content'])
                self.notice.setText('Resposta copiada.')
                break

    def toggle_history(self):
        self.history_panel.setVisible(not self.history_panel.isVisible())
        self.refresh_history()
        if self.history_panel.isVisible():
            self.search.setFocus()

    def refresh_history(self, *_):
        self.history.clear()
        for row in self.store.conversations(self.search.text()):
            item = QListWidgetItem(row['title'])
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.history.addItem(item)
            if row['id'] == self.active:
                self.history.setCurrentItem(item)

    def choose_conversation(self, item):
        if self.busy:
            return
        self.drafts[self.active] = self.composer.toPlainText()
        self.active = item.data(Qt.ItemDataRole.UserRole)
        self.store.set_setting('active', self.active)
        self.composer.setPlainText(self.drafts.get(self.active, ''))
        self.notice.clear()
        self.render(scroll=True)
        self.composer.setFocus()

    def new_conversation(self):
        if self.busy or not self.ready:
            return
        self.drafts[self.active] = self.composer.toPlainText()
        # Reuse an empty conversation rather than accumulating empty history entries.
        if self.store.messages(self.active):
            self.active = self.store.new()
        self.composer.clear()
        self.thinking.setChecked(False)
        self.notice.clear()
        self.refresh_history()
        self.back_to_chat()

    def delete_conversation(self):
        if self.busy:
            return
        if QMessageBox.question(self, 'Eliminar conversa', 'Eliminar esta conversa do histórico local?') != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(self.active)
        self.drafts.pop(self.active, None)
        self.active = self.store.active()
        self.composer.clear()
        self.refresh_history()
        self.render(scroll=True)

    def focus_input(self):
        target = self.key_input if self.pages.currentWidget() == self.key_page else self.composer
        target.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def show_window(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        self.resize(min(self.width(), bounds.width() - 30), min(self.height(), bounds.height() - 30))
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(40, self.focus_input)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def shutdown(self):
        self.stream.cancel()
        self.persist_timer.stop()
        self.render_timer.stop()
