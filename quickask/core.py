"""Pure request policy, incremental SSE decoding and private conversation storage."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import os
import sqlite3
import uuid

MODEL = 'deepseek/deepseek-v4.1-flash-1017'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
APP_ID = 'local.quickask'
SYSTEM = ('Responde em português europeu, de forma breve, clara e útil. '
          'Explicita unidades, pressupostos e incertezas relevantes. '
          'Em cálculos mostra o essencial e verifica as unidades. '
          'Se faltarem dados importantes, pede-os; não inventes factos. '
          'Não tens acesso a pesquisa web nem a ferramentas nesta conversa. ')


def request_body(messages, thinking=False, now=None):
    now = now or datetime.now(ZoneInfo('Europe/Lisbon'))
    return {
        'model': MODEL, 'stream': True,
        'reasoning': {'enabled': bool(thinking)},
        'provider': {'allow_fallbacks': True, 'require_parameters': True,
                     'max_price': {'prompt': 0.30, 'completion': 1.20}},
        'max_tokens': 4096 if thinking else 1024,
        'messages': [{'role': 'system', 'content': SYSTEM +
                      'Data e hora em Lisboa: ' + now.astimezone(ZoneInfo('Europe/Lisbon')).isoformat(timespec='seconds')}] +
                    [{'role': m['role'], 'content': m['content']} for m in messages
                     if m['role'] in ('user', 'assistant')],
    }


def error_message(code, network=False):
    if network:
        return 'Falha de rede ou ligação interrompida. Verifica a ligação e tenta novamente.'
    return {
        400: 'O pedido foi recusado. Verifica a disponibilidade e os parâmetros deste modelo.',
        401: 'Chave inválida ou revogada. Altera a chave nas definições.',
        402: 'Saldo ou limite da chave insuficiente no OpenRouter.',
        403: 'O OpenRouter recusou o acesso. Verifica as permissões da chave e da conta.',
        404: 'Não há um fornecedor elegível para este modelo e estes limites. O teto de preço foi mantido.',
        408: 'O fornecedor demorou demasiado tempo a responder. Tenta novamente.',
        429: 'Limite de pedidos atingido. Aguarda um pouco antes de tentar novamente.',
        502: 'O fornecedor falhou. Tenta novamente; os limites de preço mantêm-se.',
        503: 'Não há fornecedor disponível dentro das condições do pedido. Os limites mantêm-se.',
        504: 'O fornecedor demorou demasiado tempo a responder. Tenta novamente.',
    }.get(code, 'Não foi possível concluir o pedido. Os limites de preço e o modelo mantêm-se.')


class SSEDecoder:
    """Byte buffering keeps UTF-8 code points intact across network fragments."""
    def __init__(self):
        self.buffer = bytearray()
        self.lines = []

    def feed(self, chunk):
        self.buffer.extend(chunk)
        events = []
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            line = bytes(line).rstrip(b'\r')
            if not line:
                if self.lines:
                    events.append(b'\n'.join(self.lines).decode('utf-8'))
                    self.lines = []
            elif line.startswith(b'data:'):
                self.lines.append(line[5:].lstrip(b' '))
        if len(self.buffer) > 4_000_000:
            raise ValueError('SSE event too large')
        return events


class Store:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.path = directory / 'history.sqlite3'
        self.db = sqlite3.connect(self.path)
        self.path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        PRAGMA secure_delete=ON;
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        self.db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")
        self.db.commit()

    def setting(self, key, default=''):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(value)))
        self.db.commit()

    def new(self):
        cid = str(uuid.uuid4())
        self.db.execute('INSERT INTO conversations VALUES (?,?,?)', (cid, 'Nova conversa', datetime.now().isoformat()))
        self.set_setting('active', cid)
        return cid

    def active(self):
        cid = self.setting('active')
        if not self.db.execute('SELECT id FROM conversations WHERE id=?', (cid,)).fetchone():
            cid = self.new()
        return cid

    def conversations(self, query=''):
        # Literal substring matching, including accented Portuguese text.
        rows = self.db.execute('SELECT * FROM conversations ORDER BY updated DESC').fetchall()
        needle = query.casefold()
        return [dict(r) for r in rows if not needle or needle in r['title'].casefold() or
                any(needle in m['content'].casefold() for m in self.messages(r['id']))]

    def messages(self, cid):
        rows = self.db.execute('SELECT * FROM messages WHERE conversation=? ORDER BY id', (cid,)).fetchall()
        return [dict(r) | {'metadata': json.loads(r['metadata'])} for r in rows]

    def add(self, cid, role, content, status='complete'):
        cur = self.db.execute('INSERT INTO messages (conversation,role,content,status) VALUES (?,?,?,?)',
                              (cid, role, content, status))
        if role == 'user':
            count = self.db.execute("SELECT count(*) FROM messages WHERE conversation=? AND role='user'", (cid,)).fetchone()[0]
            if count == 1:
                self.db.execute('UPDATE conversations SET title=? WHERE id=?', (' '.join(content.split())[:72], cid))
        self.db.execute('UPDATE conversations SET updated=? WHERE id=?', (datetime.now().isoformat(), cid))
        self.db.commit()
        return cur.lastrowid

    def update(self, mid, content, status, metadata=None):
        self.db.execute('UPDATE messages SET content=?,status=?,metadata=? WHERE id=?',
                        (content, status, json.dumps(metadata or {}, ensure_ascii=False), mid))
        self.db.commit()

    def context(self, cid):
        return [{'role': m['role'], 'content': m['content']} for m in self.messages(cid)
                if m['content'] and (m['role'] == 'user' or m['status'] == 'complete')]

    def delete(self, cid):
        self.db.execute('DELETE FROM conversations WHERE id=?', (cid,))
        self.db.commit()

    def close(self):
        self.db.close()
