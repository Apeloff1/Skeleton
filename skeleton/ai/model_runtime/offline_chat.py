"""Offline, provider-free chat product over the existing native model runtime.

Loads a locally verified Skeleton native-transformer checkpoint. A single
SQLite authority stores conversations, optimistic revisions, and idempotent
turn receipts. A rejected or failed inference never commits a partial turn.
This is a local single-user interface, not an authenticated network service.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import sys
import threading
import time
from typing import Any, Iterator

from .chat_engine import NativeChatEngine
from .chat_protocol import ChatTranscript, MAX_MESSAGES
from .native_llm_runtime import NativeLLMRuntime
from .runtime_checkpoint import MAX_CHECKPOINT_BYTES
from .runtime_contracts import GenerationConfig, RuntimeContractError


MAX_ID_BYTES = 128
MAX_TURN_BYTES = 262_144
MAX_TRANSCRIPT_BYTES = 2_359_296
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_EXPORTED_TURNS = 1024
_BUNDLE_SCHEMA = "skeleton.ai.offline-chat-bundle.v1"
_BUNDLE_SCHEMA_V2 = "skeleton.ai.offline-chat-bundle.v2"


def _stable_bytes(obj: Any) -> bytes:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RuntimeContractError("invalid offline conversation bundle") from exc


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise RuntimeContractError("duplicate key in offline conversation bundle")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise RuntimeContractError("nonfinite value in offline conversation bundle")


def _sha256(value: object, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise RuntimeContractError(f"invalid {name}")
    return value



def _validate_complete_history(transcript: ChatTranscript,
                               turns: list[dict[str, Any]]) -> None:
    """Prove every saved generation has exactly one retained dialogue pair.

    Revision counters and digest-matched JSON alone are insufficient: a bundle
    may contain authentic *but truncated* history and thereby erase previously
    committed chat context on import.
    """
    messages = transcript.messages
    offset = 1 if messages and messages[0].role == "system" else 0
    dialogue = messages[offset:]
    if len(turns) > MAX_EXPORTED_TURNS or len(dialogue) != 2 * len(turns):
        raise RuntimeContractError("conversation turn history is incomplete")
    ids: set[str] = set()
    for index, turn in enumerate(turns):
        user, assistant = dialogue[index * 2:index * 2 + 2]
        if (
            user.role != "user" or not user.content.strip()
            or assistant.role != "assistant" or not assistant.content.strip()
            or assistant.content != turn["text"]
            or type(turn["revision"]) is not int
            or turn["revision"] != index + 1
        ):
            raise RuntimeContractError("conversation turn history/receipt mismatch")
        rid = _identifier("request id", turn["request_id"])
        if rid in ids:
            raise RuntimeContractError("duplicate request id in conversation")
        ids.add(rid)


def _identifier(name: str, raw: str) -> str:
    if not isinstance(raw, str) or not 1 <= len(raw) <= MAX_ID_BYTES:
        raise RuntimeContractError(f"invalid {name}")
    if any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in raw):
        raise RuntimeContractError(f"invalid {name}")
    return raw


def _digest_request(message: str, config: GenerationConfig) -> str:
    if not isinstance(message, str) or not message:
        raise RuntimeContractError("invalid or oversized chat message")
    try:
        if len(message.encode("utf-8", errors="strict")) > MAX_TURN_BYTES:
            raise RuntimeContractError("invalid or oversized chat message")
        raw = json.dumps({"message": message, "config": config.to_dict()},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, TypeError) as exc:
        raise RuntimeContractError("chat turn cannot be canonically serialized") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredChat:
    session_id: str
    revision: int
    transcript: ChatTranscript
    model_digest: str
    tokenizer_digest: str


@dataclass(frozen=True, slots=True)
class OfflineTurnReceipt:
    session_id: str
    request_id: str
    revision: int
    text: str
    output_digest: str
    prompt_tokens: int
    generated_tokens: int
    replayed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "revision": self.revision,
            "text": self.text,
            "output_digest": self.output_digest,
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "replayed": self.replayed,
        }


def _validate_private_sqlite_path(path: Path, *, main: bool) -> None:
    """Validate the SQLite database or its existing WAL/SHM sidecar.

    A private main file is not sufficient if another user can read or
    redirect write-ahead log pages containing plaintext conversation data.
    """
    if path.is_symlink():
        raise RuntimeContractError("offline database or journal symlinks are not allowed")
    try:
        details = path.stat()
    except FileNotFoundError:
        if main:
            raise RuntimeContractError("offline database file is missing")
        return
    if not stat.S_ISREG(details.st_mode):
        raise RuntimeContractError("offline database or journal must be a regular file")
    if os.name != "nt":
        if details.st_mode & 0o077:
            raise RuntimeContractError(
                "offline database and journal must have owner-only permissions (chmod 600)"
            )
        if details.st_nlink != 1:
            raise RuntimeContractError("offline database or journal must not be hard-linked")
        if hasattr(os, "getuid") and details.st_uid != os.getuid():
            raise RuntimeContractError("offline database or journal must be owned by the user")


class OfflineChatStore:
    """Local SQLite authority for model-pinned chat and replay-safe turn commits."""

    def __init__(self, path: str | Path) -> None:
        filename = str(path)
        if not filename:
            raise RuntimeContractError("offline database path required")
        if filename != ":memory:":
            p = Path(filename)
            if p.is_symlink():
                raise RuntimeContractError("offline database symlinks are not allowed")
            if not p.exists():
                # Chat transcripts contain private user content. New files must
                # not inherit world-readable SQLite creation permissions.
                try:
                    descriptor = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(descriptor)
                except FileExistsError:
                    pass
            # SQLite WAL and shared-memory sidecars may contain plaintext
            # prompts. Reject unsafe *existing* sidecars before SQLite opens
            # them, rather than checking only the main database.
            for candidate, required in (
                (p, True), (Path(filename + "-wal"), False),
                (Path(filename + "-shm"), False),
                (Path(filename + "-journal"), False),
            ):
                _validate_private_sqlite_path(candidate, main=required)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(filename, isolation_level=None,
                                   check_same_thread=False, timeout=10.0)
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA trusted_schema=OFF")
            self._db.execute("PRAGMA secure_delete=ON")
            self._db.execute("PRAGMA foreign_keys=ON")
            if filename != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS offline_sessions (
                session_id TEXT PRIMARY KEY,
                model_digest TEXT NOT NULL,
                tokenizer_digest TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 0),
                transcript_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS offline_turns (
                session_id TEXT NOT NULL REFERENCES offline_sessions(session_id) ON DELETE CASCADE,
                request_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 1),
                text TEXT NOT NULL,
                output_digest TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL CHECK (prompt_tokens >= 0),
                generated_tokens INTEGER NOT NULL CHECK (generated_tokens >= 0),
                PRIMARY KEY (session_id, request_id),
                UNIQUE (session_id, revision)
            )""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS offline_turn_evidence (
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                PRIMARY KEY (session_id, request_id),
                FOREIGN KEY (session_id, request_id)
                    REFERENCES offline_turns(session_id, request_id)
                    ON DELETE CASCADE
            )""")

            if self._db.execute("PRAGMA foreign_keys").fetchone() != (1,):
                raise RuntimeContractError("SQLite foreign-key enforcement unavailable")
            if self._db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeContractError("SQLite conversation store failed integrity check")

        except BaseException:
            self._db.close()
            raise

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                try:
                    self._db.execute("COMMIT")
                except BaseException:
                    # Disk-full and I/O failures may leave the transaction
                    # active after COMMIT fails. Release any pending writes
                    # before another request can observe the same connection.
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "OfflineChatStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def create(self, model_digest: str, tokenizer_digest: str,
               *, system: str | None = None) -> str:
        if not isinstance(model_digest, str) or len(model_digest) != 64:
            raise RuntimeContractError("invalid model digest")
        if not isinstance(tokenizer_digest, str) or len(tokenizer_digest) != 64:
            raise RuntimeContractError("invalid tokenizer digest")
        transcript = ChatTranscript(())
        if system is not None:
            if not system:
                raise RuntimeContractError("empty system message")
            transcript = transcript.append("system", system)
        serialized = transcript.to_json()
        if len(serialized.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("system message exceeds persisted budget")
        sid = secrets.token_urlsafe(24)
        with self._transaction():
            self._db.execute(
                "INSERT INTO offline_sessions VALUES (?, ?, ?, 0, ?, ?)",
                (sid, model_digest, tokenizer_digest, serialized, time.time_ns()),
            )
        return sid

    def load(self, session_id: str, model_digest: str,
             tokenizer_digest: str) -> StoredChat:
        sid = _identifier("session id", session_id)
        with self._lock:
            # Other store instances/processes have distinct Python locks.
            # A single SQLite read transaction supplies a consistent snapshot
            # across *both* tables even if another process commits meanwhile.
            own_snapshot = not self._db.in_transaction
            if own_snapshot:
                self._db.execute("BEGIN")
            try:
                row = self._db.execute(
                    "SELECT model_digest, tokenizer_digest, revision, transcript_json "
                    "FROM offline_sessions WHERE session_id=?", (sid,)
                ).fetchone()
                rows = self._db.execute(
                    "SELECT request_id, request_digest, revision, text, output_digest, "
                    "prompt_tokens, generated_tokens FROM offline_turns "
                    "WHERE session_id=? ORDER BY revision", (sid,),
                ).fetchall()
                evidence_rows = self._db.execute(
                    "SELECT e.request_id, e.evidence_json, e.evidence_digest "
                    "FROM offline_turn_evidence e JOIN offline_turns t "
                    "ON e.session_id=t.session_id AND e.request_id=t.request_id "
                    "WHERE e.session_id=? ORDER BY t.revision", (sid,),
                ).fetchall()
            finally:
                if own_snapshot:
                    self._db.execute("ROLLBACK")
        if row is None:
            raise RuntimeContractError("unknown offline conversation")
        if row[0] != model_digest or row[1] != tokenizer_digest:
            raise RuntimeContractError("offline conversation is bound to a different model/tokenizer")
        if not isinstance(row[3], str) or len(row[3].encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("persisted conversation exceeds byte budget")
        transcript = ChatTranscript.from_json(row[3])
        transcript.validate_turn_order()
        revision = row[2]
        if type(revision) is not int or not 0 <= revision <= MAX_EXPORTED_TURNS:
            raise RuntimeContractError("stored conversation revision is invalid")
        # The revision number is not itself evidence that every saved turn
        # survived. Verify all receipts against the full authoritative
        # transcript on *every* read, not only when exporting a backup.
        if len(rows) != revision:
            raise RuntimeContractError("stored conversation is missing turn receipts")
        turns: list[dict[str, Any]] = []
        for item in rows:
            _sha256(item[1], "stored request digest")
            _sha256(item[4], "stored output digest")
            if (not isinstance(item[3], str)
                    or any(type(value) is not int or value < 0
                           for value in (item[5], item[6]))):
                raise RuntimeContractError("stored conversation receipt is invalid")
            turns.append(dict(
                request_id=item[0], request_digest=item[1],
                revision=item[2], text=item[3], output_digest=item[4],
                prompt_tokens=item[5], generated_tokens=item[6],
            ))
        _validate_complete_history(transcript, turns)
        evidence_index = {item["request_id"]: item for item in turns}
        for receipt_id, encoded, claimed in evidence_rows:
            turn = evidence_index.get(receipt_id)
            if turn is None:
                raise RuntimeContractError("orphaned grounded turn evidence")
            self._validate_evidence_record(
                encoded, claimed, turn, transcript, row[0], row[1]
            )
        return StoredChat(sid, revision, transcript, row[0], row[1])

    @staticmethod
    def _validate_evidence_record(encoded: str, digest: str,
                                  turn: dict[str, Any],
                                  transcript: ChatTranscript, model_digest: str,
                                  tokenizer_digest: str) -> dict[str, Any]:
        from skeleton.app.offline_grounding import validate_evidence

        if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 6_144:
            raise RuntimeContractError("stored grounding evidence exceeds limit")
        if sha256(encoded.encode("utf-8")).hexdigest() != _sha256(
            digest, "stored grounding digest"
        ):
            raise RuntimeContractError("stored grounding evidence digest mismatch")
        try:
            item = json.loads(encoded, object_pairs_hook=_strict_pairs,
                              parse_constant=_reject_constant)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeContractError("corrupted stored grounding JSON") from exc
        messages = transcript.messages
        offset = 1 if messages and messages[0].role == "system" else 0
        question = messages[offset + 2 * (turn["revision"] - 1)].content
        reconstructed = validate_evidence(
            item, question, turn["request_digest"],
            model_digest, tokenizer_digest,
        )
        if reconstructed.decode("utf-8") != encoded:
            raise RuntimeContractError("noncanonical grounded turn evidence")
        return item

    def turn_evidence(self, session_id: str, model_digest: str,
                      tokenizer_digest: str) -> list[dict[str, Any] | None]:
        """Read validated immutable supplied-source snapshots per saved turn."""
        record = self.load(session_id, model_digest, tokenizer_digest)
        with self._lock:
            rows = self._db.execute(
                "SELECT t.request_id, t.request_digest, t.revision, t.text, "
                "t.output_digest, t.prompt_tokens, t.generated_tokens, "
                "e.evidence_json, e.evidence_digest "
                "FROM offline_turns t LEFT JOIN offline_turn_evidence e "
                "ON t.session_id=e.session_id AND t.request_id=e.request_id "
                "WHERE t.session_id=? ORDER BY t.revision",
                (record.session_id,),
            ).fetchall()
        if len(rows) != record.revision:
            raise RuntimeContractError("grounded turn read changed during lookup")
        out: list[dict[str, Any] | None] = []
        for row in rows:
            turn = dict(request_id=row[0], request_digest=row[1],
                        revision=row[2], text=row[3], output_digest=row[4],
                        prompt_tokens=row[5], generated_tokens=row[6])
            out.append(
                self._validate_evidence_record(
                    row[7], row[8], turn, record.transcript,
                    model_digest, tokenizer_digest
                ) if row[7] is not None else None
            )
        return out

    def list_sessions(self, model_digest: str, tokenizer_digest: str,
                      *, limit: int = 100) -> tuple[tuple[str, int], ...]:
        """Find resumable conversations for this exact offline model identity."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise RuntimeContractError("invalid offline listing limit")
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id, revision FROM offline_sessions "
                "WHERE model_digest=? AND tokenizer_digest=? "
                "ORDER BY updated_at DESC, session_id LIMIT ?",
                (model_digest, tokenizer_digest, limit),
            ).fetchall()
        return tuple((_identifier("session id", sid), revision)
                     for sid, revision in rows)

    def delete(self, session_id: str, model_digest: str,
               tokenizer_digest: str) -> None:
        """Delete the canonical conversation and all idempotency receipts."""
        sid = _identifier("session id", session_id)
        with self._transaction():
            cursor = self._db.execute(
                "DELETE FROM offline_sessions WHERE session_id=? "
                "AND model_digest=? AND tokenizer_digest=?",
                (sid, model_digest, tokenizer_digest),
            )
            if cursor.rowcount != 1:
                raise RuntimeContractError(
                    "unknown conversation or model/tokenizer identity mismatch"
                )

    def fork(self, session_id: str, model_digest: str, tokenizer_digest: str,
             *, after_turn: int | None = None) -> str:
        """Clone a complete conversation up to an exact committed turn boundary.

        Forking never mutates the parent. Every copied turn retains its
        idempotency identity, while subsequent generations get an independent
        session and revision sequence.
        """
        sid = _identifier("session id", session_id)
        with self._transaction():
            parent = self.load(sid, model_digest, tokenizer_digest)
            rows = self._db.execute(
                "SELECT request_id, request_digest, revision, text, output_digest, "
                "prompt_tokens, generated_tokens FROM offline_turns "
                "WHERE session_id=? ORDER BY revision",
                (sid,),
            ).fetchall()
            turns = [
                dict(request_id=row[0], request_digest=row[1], revision=row[2],
                     text=row[3], output_digest=row[4], prompt_tokens=row[5],
                     generated_tokens=row[6])
                for row in rows
            ]
            if len(turns) != parent.revision:
                raise RuntimeContractError("parent conversation revision is inconsistent")
            _validate_complete_history(parent.transcript, turns)
            if after_turn is None:
                after_turn = parent.revision
            if (type(after_turn) is not int or not 0 <= after_turn <= parent.revision):
                raise RuntimeContractError("fork turn must be within committed history")
            system_count = (
                1 if parent.transcript.messages
                and parent.transcript.messages[0].role == "system" else 0
            )
            forked = ChatTranscript(parent.transcript.messages[
                :system_count + 2 * after_turn
            ])
            new_id = secrets.token_urlsafe(24)
            self._db.execute(
                "INSERT INTO offline_sessions VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, model_digest, tokenizer_digest, after_turn,
                 forked.to_json(), time.time_ns()),
            )
            self._db.executemany(
                "INSERT INTO offline_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(new_id, *row) for row in rows[:after_turn]],
            )
            self._db.execute(
                "INSERT INTO offline_turn_evidence "
                "(session_id, request_id, evidence_json, evidence_digest) "
                "SELECT ?, e.request_id, e.evidence_json, e.evidence_digest "
                "FROM offline_turn_evidence e JOIN offline_turns t "
                "ON e.session_id=t.session_id AND e.request_id=t.request_id "
                "WHERE e.session_id=? AND t.revision <= ?",
                (new_id, sid, after_turn),
            )
            return new_id

    def export_bundle(self, session_id: str, model_digest: str,
                      tokenizer_digest: str) -> bytes:
        """Atomic read of a complete conversation and its retry receipts.

        The bundle carries all committed turns, unlike copying a UI transcript.
        It is integrity-checked but NOT encrypted or signed; operators must
        protect it as sensitive local conversation data.
        """
        sid = _identifier("session id", session_id)
        _sha256(model_digest, "model digest")
        _sha256(tokenizer_digest, "tokenizer digest")
        with self._transaction():
            stored = self.load(sid, model_digest, tokenizer_digest)
            rows = self._db.execute(
                "SELECT request_id, request_digest, revision, text, output_digest, "
                "prompt_tokens, generated_tokens FROM offline_turns "
                "WHERE session_id=? ORDER BY revision",
                (sid,),
            ).fetchall()
            if len(rows) > MAX_EXPORTED_TURNS:
                raise RuntimeContractError("conversation has too many durable turns to export")
            turns = [
                dict(request_id=row[0], request_digest=row[1], revision=row[2],
                     text=row[3], output_digest=row[4], prompt_tokens=row[5],
                     generated_tokens=row[6])
                for row in rows
            ]
            if stored.revision != len(turns):
                raise RuntimeContractError("conversation receipt count does not match revision")
            _validate_complete_history(stored.transcript, turns)
            body = {
                "schema": _BUNDLE_SCHEMA,
                "model_digest": stored.model_digest,
                "tokenizer_digest": stored.tokenizer_digest,
                "revision": stored.revision,
                "messages": stored.transcript.to_list(),
                "turns": turns,
            }
            grounding = self.turn_evidence(sid, model_digest, tokenizer_digest)
            if any(item is not None for item in grounding):
                # Legacy v1 exports stay byte/schema compatible. A v2 backup
                # carries the complete immutable source snapshot per turn.
                body["schema"] = _BUNDLE_SCHEMA_V2
                body["evidence"] = grounding
            body_bytes = _stable_bytes(body)
            bundle = _stable_bytes({
                "body": body,
                "sha256": sha256(body_bytes).hexdigest(),
            })
            if len(bundle) > MAX_BUNDLE_BYTES:
                raise RuntimeContractError("conversation export exceeds byte budget")
            return bundle

    def import_bundle(self, payload: bytes, model_digest: str,
                      tokenizer_digest: str) -> str:
        """Verify the complete portable record before an atomic new-ID import.

        Never overwrite an existing conversation. Every imported turn receipt
        preserves idempotency under its original request ID.
        """
        _sha256(model_digest, "model digest")
        _sha256(tokenizer_digest, "tokenizer digest")
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_BUNDLE_BYTES:
            raise RuntimeContractError("offline conversation import exceeds byte budget")
        try:
            envelope = json.loads(payload.decode("utf-8", errors="strict"),
                                  object_pairs_hook=_strict_pairs,
                                  parse_constant=_reject_constant)
        except (UnicodeError, ValueError) as exc:
            raise RuntimeContractError("invalid conversation bundle encoding") from exc
        if not isinstance(envelope, dict) or set(envelope) != {"body", "sha256"}:
            raise RuntimeContractError("invalid conversation bundle envelope")
        body = envelope["body"]
        common_fields = {
            "schema", "model_digest", "tokenizer_digest", "revision", "messages", "turns"
        }
        if not isinstance(body, dict) or (
            body.get("schema") == _BUNDLE_SCHEMA and set(body) != common_fields
        ) or (
            body.get("schema") == _BUNDLE_SCHEMA_V2
            and set(body) != common_fields | {"evidence"}
        ) or body.get("schema") not in {_BUNDLE_SCHEMA, _BUNDLE_SCHEMA_V2}:
            raise RuntimeContractError("unsupported conversation bundle schema")
        if not hmac.compare_digest(
            _sha256(envelope["sha256"], "bundle digest"),
            sha256(_stable_bytes(body)).hexdigest(),
        ):
            raise RuntimeContractError("conversation bundle digest mismatch")
        if (body["model_digest"] != model_digest
                or body["tokenizer_digest"] != tokenizer_digest):
            raise RuntimeContractError("bundle model/tokenizer identity mismatch")
        messages = body["messages"]
        if not isinstance(messages, list):
            raise RuntimeContractError("conversation bundle messages must be a list")
        transcript = ChatTranscript.parse(messages)
        transcript.validate_turn_order()
        # The native CLI permits one initial system instruction; the desktop
        # app preserves it when restoring the same model-bound conversation.
        instruction_offset = (
            1 if transcript.messages and transcript.messages[0].role == "system"
            else 0
        )
        dialogue = transcript.messages[instruction_offset:]
        if len(dialogue) % 2 or any(
            m.role != ("user" if i % 2 == 0 else "assistant")
            or not m.content.strip()
            for i, m in enumerate(dialogue)
        ):
            raise RuntimeContractError("bundle contains invalid dialogue roles")
        rev = body["revision"]
        turns = body["turns"]
        if (type(rev) is not int or rev < 0 or rev > MAX_EXPORTED_TURNS
                or not isinstance(turns, list) or len(turns) != rev):
            raise RuntimeContractError("bundle revision or turn count mismatch")
        validated = []
        for index, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) != {
                "request_id", "request_digest", "revision", "text",
                "output_digest", "prompt_tokens", "generated_tokens"
            }:
                raise RuntimeContractError("invalid exported turn shape")
            rid = _identifier("request id", turn["request_id"])
            _sha256(turn["request_digest"], "request digest")
            _sha256(turn["output_digest"], "output digest")
            if turn["revision"] != index + 1 or type(turn["revision"]) is not int:
                raise RuntimeContractError("nonconsecutive exported turn revisions")
            if (not isinstance(turn["text"], str)
                    or len(turn["text"].encode("utf-8")) > MAX_TRANSCRIPT_BYTES
                    or any(type(turn[key]) is not int or turn[key] < 0
                           for key in ("prompt_tokens", "generated_tokens"))):
                raise RuntimeContractError("invalid exported turn content")
            validated.append((
                rid, turn["request_digest"], turn["revision"], turn["text"],
                turn["output_digest"], turn["prompt_tokens"],
                turn["generated_tokens"],
            ))
        _validate_complete_history(transcript, turns)
        evidence = (body["evidence"] if body["schema"] == _BUNDLE_SCHEMA_V2
                    else [None] * len(turns))
        if not isinstance(evidence, list) or len(evidence) != len(turns):
            raise RuntimeContractError("grounding backup evidence count mismatch")
        checked_evidence = []
        for index, item in enumerate(evidence):
            if item is None:
                continue
            question = dialogue[index * 2].content
            from skeleton.app.offline_grounding import validate_evidence
            encoded_evidence = validate_evidence(
                item, question, turns[index]["request_digest"],
                model_digest, tokenizer_digest,
            )
            checked_evidence.append((
                turns[index]["request_id"], encoded_evidence.decode("utf-8"),
                sha256(encoded_evidence).hexdigest(),
            ))
        serialized = transcript.to_json()
        if len(serialized.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("restored conversation exceeds byte budget")
        new_id = secrets.token_urlsafe(24)
        with self._transaction():
            self._db.execute(
                "INSERT INTO offline_sessions VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, model_digest, tokenizer_digest, rev, serialized, time.time_ns()),
            )
            self._db.executemany(
                "INSERT INTO offline_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(new_id, *row) for row in validated],
            )
            self._db.executemany(
                "INSERT INTO offline_turn_evidence VALUES (?, ?, ?, ?)",
                [(new_id, *row) for row in checked_evidence],
            )
        return new_id

    @staticmethod
    def _receipt(row: tuple[Any, ...], session_id: str, request_id: str,
                 request_digest: str, *, replayed: bool) -> OfflineTurnReceipt:
        if row[0] != request_digest:
            raise RuntimeContractError("request id reused with different prompt or generation settings")
        return OfflineTurnReceipt(session_id, request_id, int(row[1]), row[2],
                                  row[3], int(row[4]), int(row[5]), replayed)

    def replay(self, session_id: str, request_id: str,
               request_digest: str) -> OfflineTurnReceipt | None:
        _identifier("session id", session_id)
        _identifier("request id", request_id)
        with self._lock:
            row = self._db.execute(
                "SELECT request_digest, revision, text, output_digest, prompt_tokens, "
                "generated_tokens FROM offline_turns WHERE session_id=? AND request_id=?",
                (session_id, request_id),
            ).fetchone()
        return None if row is None else self._receipt(
            row, session_id, request_id, request_digest, replayed=True
        )

    @staticmethod
    def ensure_can_append(session: StoredChat) -> None:
        """Preflight full-history room before spending CPU on a model turn.

        The ChatTranscript capacity includes optional system instructions.
        Model work must never begin if its result cannot be durably appended.
        """
        if not isinstance(session, StoredChat):
            raise RuntimeContractError("offline session snapshot required")
        if (session.revision >= MAX_EXPORTED_TURNS
                or len(session.transcript.messages) + 2 > MAX_MESSAGES):
            raise RuntimeContractError(
                "offline conversation has reached its durable turn capacity"
            )

    def commit(self, *, session: StoredChat, request_id: str,
               request_digest: str, transcript: ChatTranscript, text: str,
               output_digest: str, prompt_tokens: int,
               generated_tokens: int,
               evidence_manifest: dict[str, Any] | None = None) -> OfflineTurnReceipt:
        rid = _identifier("request id", request_id)
        if (not isinstance(transcript, ChatTranscript) or not isinstance(text, str)
                or not text.strip()):
            raise RuntimeContractError("invalid completed native chat result")
        transcript.validate_turn_order()
        self.ensure_can_append(session)
        prior = session.transcript.messages
        next_messages = transcript.messages
        if (
            len(next_messages) != len(prior) + 2
            or next_messages[:-2] != prior
            or next_messages[-2].role != "user"
            or next_messages[-1].role != "assistant"
            or next_messages[-1].content != text
        ):
            raise RuntimeContractError("completed turn must extend full saved transcript")
        encoded = transcript.to_json()
        if len(encoded.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("completed conversation exceeds persisted budget")
        if not isinstance(output_digest, str) or len(output_digest) != 64:
            raise RuntimeContractError("invalid native generation output digest")
        if any(type(n) is not int or n < 0 for n in (prompt_tokens, generated_tokens)):
            raise RuntimeContractError("invalid native generation token count")
        stored_evidence = None
        if evidence_manifest is not None:
            from skeleton.app.offline_grounding import validate_evidence
            stored_evidence = validate_evidence(
                evidence_manifest, next_messages[-2].content, request_digest,
                session.model_digest, session.tokenizer_digest,
            )
        with self._transaction():
            existing = self._db.execute(
                "SELECT request_digest, revision, text, output_digest, prompt_tokens, "
                "generated_tokens FROM offline_turns WHERE session_id=? AND request_id=?",
                (session.session_id, rid),
            ).fetchone()
            if existing is not None:
                return self._receipt(existing, session.session_id, rid, request_digest,
                                     replayed=True)
            cursor = self._db.execute(
                "UPDATE offline_sessions SET revision=?, transcript_json=?, updated_at=? "
                "WHERE session_id=? AND revision=? AND model_digest=? "
                "AND tokenizer_digest=? AND transcript_json=?",
                (session.revision + 1, encoded, time.time_ns(), session.session_id,
                 session.revision, session.model_digest, session.tokenizer_digest,
                 session.transcript.to_json()),
            )
            if cursor.rowcount != 1:
                raise RuntimeContractError("offline conversation revision conflict")
            self._db.execute(
                "INSERT INTO offline_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session.session_id, rid, request_digest, session.revision + 1,
                 text, output_digest, prompt_tokens, generated_tokens),
            )
            if stored_evidence is not None:
                self._db.execute(
                    "INSERT INTO offline_turn_evidence VALUES (?, ?, ?, ?)",
                    (session.session_id, rid, stored_evidence.decode("utf-8"),
                     sha256(stored_evidence).hexdigest()),
                )
            return OfflineTurnReceipt(session.session_id, rid, session.revision + 1,
                                      text, output_digest, prompt_tokens,
                                      generated_tokens, False)


class OfflineChatProduct:
    """Provider-free, exact-model-bound chat with durable idempotent turns."""

    def __init__(self, engine: NativeChatEngine, store: OfflineChatStore) -> None:
        if not isinstance(engine, NativeChatEngine) or not isinstance(store, OfflineChatStore):
            raise RuntimeContractError("native chat engine and store required")
        self.engine = engine
        self.store = store

    @property
    def model_digest(self) -> str:
        return self.engine.runtime.model_digest

    @property
    def tokenizer_digest(self) -> str:
        return self.engine.runtime.tokenizer.digest

    def create(self, *, system: str | None = None) -> str:
        return self.store.create(self.model_digest, self.tokenizer_digest, system=system)

    def list_sessions(self, *, limit: int = 100) -> tuple[tuple[str, int], ...]:
        return self.store.list_sessions(self.model_digest, self.tokenizer_digest,
                                        limit=limit)

    def delete(self, session_id: str) -> None:
        self.store.delete(session_id, self.model_digest, self.tokenizer_digest)

    def fork(self, session_id: str, *, after_turn: int | None = None) -> str:
        return self.store.fork(session_id, self.model_digest,
                               self.tokenizer_digest, after_turn=after_turn)

    def export_session(self, session_id: str) -> bytes:
        return self.store.export_bundle(session_id, self.model_digest,
                                        self.tokenizer_digest)

    def import_session(self, payload: bytes) -> str:
        return self.store.import_bundle(payload, self.model_digest,
                                        self.tokenizer_digest)

    def turn(self, session_id: str, message: str, config: GenerationConfig,
             *, request_id: str | None = None) -> OfflineTurnReceipt:
        if not isinstance(config, GenerationConfig):
            raise RuntimeContractError("generation configuration required")
        rid = _identifier("request id", request_id if request_id is not None
                          else secrets.token_urlsafe(18))
        request_digest = _digest_request(message, config)
        session = self.store.load(session_id, self.model_digest, self.tokenizer_digest)
        old = self.store.replay(session_id, rid, request_digest)
        if old is not None:
            return old
        self.store.ensure_can_append(session)
        # The engine owns token budgets, role framing and inference. On an
        # exception the store is never touched.
        result = self.engine.turn(session.transcript, message, config)
        generation = result.generation
        # The native engine may evict old dialogue to fit its token window.
        # Persist the complete prior transcript plus the committed new turn,
        # never that shortened inference-only projection.
        full_transcript = session.transcript.append("user", message).append(
            "assistant", generation.text
        )
        return self.store.commit(
            session=session,
            request_id=rid,
            request_digest=request_digest,
            transcript=full_transcript,
            text=generation.text,
            output_digest=generation.output_digest,
            prompt_tokens=result.prompt_tokens,
            generated_tokens=len(generation.generated_ids),
        )


def load_offline_engine(path: str | Path) -> NativeChatEngine:
    """Open an integrity-checked local checkpoint without network fallback."""
    checkpoint = Path(path)
    size = checkpoint.stat().st_size
    if size <= 0 or size > MAX_CHECKPOINT_BYTES:
        raise RuntimeContractError("native model checkpoint outside supported size budget")
    with checkpoint.open("rb") as source:
        raw = source.read(MAX_CHECKPOINT_BYTES + 1)
    if len(raw) != size:
        raise RuntimeContractError("native checkpoint changed while loading")
    runtime = NativeLLMRuntime.restore_json(raw)
    return NativeChatEngine(runtime)


def save_private_bundle(path: str | Path, payload: bytes) -> None:
    """Create-only, owner-readable backup. Refuse accidental overwrites."""
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_BUNDLE_BYTES:
        raise RuntimeContractError("invalid export payload budget")
    target = Path(path)
    if target.is_symlink():
        raise RuntimeContractError("refusing conversation export to symlink")
    created = False
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as writer:
            writer.write(payload)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def load_private_bundle(path: str | Path) -> bytes:
    source = Path(path)
    if source.is_symlink():
        raise RuntimeContractError("refusing conversation import from symlink")
    if not source.is_file():
        raise RuntimeContractError("offline conversation backup is not a file")
    if not 1 <= source.stat().st_size <= MAX_BUNDLE_BYTES:
        raise RuntimeContractError("conversation backup exceeds byte budget")
    with source.open("rb") as reader:
        data = reader.read(MAX_BUNDLE_BYTES + 1)
    if not 1 <= len(data) <= MAX_BUNDLE_BYTES:
        raise RuntimeContractError("conversation backup changed or exceeds byte budget")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline native-transformer chat; never contacts model providers"
    )
    parser.add_argument("--checkpoint", required=True, type=Path,
                        help="local Skeleton native runtime checkpoint JSON")
    parser.add_argument("--database", type=Path, default=Path("skeleton-offline-chat.sqlite3"))
    parser.add_argument("--session", help="reuse a previous conversation id")
    parser.add_argument("--system", help="system instruction for a new conversation only")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message", help="one user message")
    mode.add_argument("--interactive", action="store_true",
                      help="continue a local multi-turn chat until /exit or EOF")
    mode.add_argument("--list", action="store_true",
                      help="list locally saved conversations for this model")
    mode.add_argument("--delete-session", metavar="ID",
                      help="delete a saved conversation and its turn receipts")
    mode.add_argument("--export-session", metavar="ID",
                      help="export one local conversation, with its retry receipts")
    mode.add_argument("--import-bundle", metavar="FILE", type=Path,
                      help="import a portable offline conversation backup")
    parser.add_argument("--request-id", help="stable idempotency id for safe retries")
    parser.add_argument("--output", type=Path,
                        help="create-only output file for --export-session")
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="print receipt as JSON")
    args = parser.parse_args(argv)
    if args.session and args.system is not None:
        parser.error("--system only applies to new conversations")
    if args.request_id and args.interactive:
        parser.error("--request-id applies to one-shot --message only")
    if (args.list or args.delete_session or args.export_session or args.import_bundle) and (
        args.system is not None or args.session is not None or args.request_id is not None
    ):
        parser.error("session creation and turn arguments are invalid for management")
    if bool(args.output) != bool(args.export_session):
        parser.error("--output is required exclusively for --export-session")
    try:
        engine = load_offline_engine(args.checkpoint)
        config = GenerationConfig(max_new_tokens=args.max_new_tokens,
                                  seed=args.seed, temperature=args.temperature)
        with OfflineChatStore(args.database) as store:
            product = OfflineChatProduct(engine, store)
            if args.list:
                rows = product.list_sessions()
                if args.json:
                    print(json.dumps([{"session_id": sid, "revision": rev}
                                      for sid, rev in rows], sort_keys=True))
                else:
                    for sid, rev in rows:
                        print(f"{sid}  revision={rev}")
                return 0
            if args.delete_session:
                product.delete(args.delete_session)
                if args.json:
                    print(json.dumps({"deleted": args.delete_session}))
                else:
                    print("Deleted:", args.delete_session)
                return 0
            if args.export_session:
                save_private_bundle(args.output, product.export_session(
                    args.export_session
                ))
                print(json.dumps({"exported": args.export_session,
                                  "path": str(args.output)}))
                return 0
            if args.import_bundle:
                restored_id = product.import_session(load_private_bundle(
                    args.import_bundle
                ))
                print(json.dumps({"imported_session_id": restored_id}))
                return 0

            session = args.session or product.create(system=args.system)
            if args.interactive:
                print("Session:", session)
                print("Type /exit to finish; /id to show the resumable session ID.")
                while True:
                    try:
                        message = input("You> ")
                    except EOFError:
                        break
                    if message.strip() == "/exit":
                        break
                    if message.strip() == "/id":
                        print("Session:", session)
                        continue
                    if not message:
                        continue
                    receipt = product.turn(session, message, config)
                    if args.json:
                        print(json.dumps(receipt.to_dict(), sort_keys=True,
                                         ensure_ascii=False))
                    else:
                        print("AI>", receipt.text)
                return 0

            receipt = product.turn(session, args.message, config,
                                   request_id=args.request_id)
        if args.json:
            print(json.dumps(receipt.to_dict(), sort_keys=True, ensure_ascii=False))
        else:
            print("Session:", receipt.session_id)
            print(receipt.text)
        return 0
    except (RuntimeContractError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"Offline chat failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OfflineChatProduct", "OfflineChatStore", "OfflineTurnReceipt",
    "StoredChat", "load_offline_engine", "load_private_bundle",
    "save_private_bundle", "main",
]
