"""SQLite WAL append-only hash chain with idempotency and transactional CAS."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any
from ..contracts.canonical import dumps, loads, digest
from ..contracts.errors import ContractError, ConflictError, IntegrityError
from ..contracts.identity import identifier
SCHEMA = '\nPRAGMA foreign_keys=ON;\nCREATE TABLE IF NOT EXISTS streams(stream TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision>=0), root TEXT NOT NULL);\nCREATE TABLE IF NOT EXISTS events(stream TEXT NOT NULL, revision INTEGER NOT NULL, token TEXT NOT NULL, kind TEXT NOT NULL, body BLOB NOT NULL, prior TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(stream,revision), UNIQUE(stream,token));\nCREATE INDEX IF NOT EXISTS events_stream_ix ON events(stream,revision);\n'
GENESIS = '0' * 64

class Journal:

    def __init__(self, path: str | Path=':memory:'):
        if str(path) != ':memory:' and (not isinstance(path, (str, Path)) or Path(path).is_symlink()):
            raise ContractError('SQLite journal path rejected')
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=10.0)
        self.db.execute('PRAGMA busy_timeout=10000')
        if str(path) != ' :memory:'.strip():
            self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def head(self, stream: str) -> tuple[int, str]:
        identifier(stream)
        row = self.db.execute('SELECT revision,root FROM streams WHERE stream=?', (stream,)).fetchone()
        return (int(row[0]), str(row[1])) if row else (0, GENESIS)

    def append(self, stream: str, token: str, kind: str, body: dict[str, Any], *, expected_revision: int) -> dict:
        identifier(stream)
        identifier(token)
        identifier(kind)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ContractError('invalid expected revision')
        raw = dumps(body)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = self.db.execute('SELECT revision,kind,body,digest FROM events WHERE stream=? AND token=?', (stream, token)).fetchone()
            if existing:
                if existing[1] != kind or existing[2] != raw:
                    raise ConflictError('idempotency token reused for different operation')
                result = {'revision': existing[0], 'digest': existing[3], 'duplicate': True}
                self.db.execute('COMMIT')
                return result
            revision, prior = self.head(stream)
            if revision != expected_revision:
                raise ConflictError('stream revision mismatch')
            index = revision + 1
            seal = digest({'stream': stream, 'revision': index, 'token': token, 'kind': kind, 'body': body, 'prior': prior})
            self.db.execute('INSERT INTO events(stream,revision,token,kind,body,prior,digest) VALUES(?,?,?,?,?,?,?)', (stream, index, token, kind, raw, prior, seal))
            self.db.execute('INSERT INTO streams(stream,revision,root) VALUES(?,?,?) ON CONFLICT(stream) DO UPDATE SET revision=excluded.revision,root=excluded.root', (stream, index, seal))
            self.db.execute('COMMIT')
            return {'revision': index, 'digest': seal, 'duplicate': False}
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def replay(self, stream: str, *, max_events: int=100000) -> list[dict]:
        identifier(stream)
        if not 1 <= max_events <= 1000000:
            raise ContractError('invalid replay ceiling')
        rows = self.db.execute('SELECT revision,token,kind,body,prior,digest FROM events WHERE stream=? ORDER BY revision LIMIT ?', (stream, max_events + 1)).fetchall()
        if len(rows) > max_events:
            raise IntegrityError('stream exceeds replay ceiling')
        chain = GENESIS
        out = []
        for revision, token, kind, raw, prior, seal in rows:
            body = loads(raw)
            expected = digest({'stream': stream, 'revision': revision, 'token': token, 'kind': kind, 'body': body, 'prior': chain})
            if prior != chain or expected != seal or revision != len(out) + 1:
                raise IntegrityError('event chain corrupt')
            out.append({'revision': revision, 'token': token, 'kind': kind, 'body': body, 'digest': seal})
            chain = seal
        head = self.head(stream)
        if head != (len(out), chain):
            raise IntegrityError('stream head diverges from event chain')
        return out
