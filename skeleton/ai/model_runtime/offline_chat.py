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
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time
from typing import Any, Iterator

from .chat_engine import NativeChatEngine
from .chat_protocol import ChatTranscript
from .native_llm_runtime import NativeLLMRuntime
from .runtime_checkpoint import MAX_CHECKPOINT_BYTES
from .runtime_contracts import GenerationConfig, RuntimeContractError


MAX_ID_BYTES = 128
MAX_TURN_BYTES = 262_144
MAX_TRANSCRIPT_BYTES = 2_359_296


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
        self._lock = threading.RLock()
        self._db = sqlite3.connect(filename, isolation_level=None,
                                   check_same_thread=False, timeout=10.0)
        self._db.execute("PRAGMA busy_timeout=10000")
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
                self._db.execute("COMMIT")

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
            row = self._db.execute(
                "SELECT model_digest, tokenizer_digest, revision, transcript_json "
                "FROM offline_sessions WHERE session_id=?", (sid,)
            ).fetchone()
        if row is None:
            raise RuntimeContractError("unknown offline conversation")
        if row[0] != model_digest or row[1] != tokenizer_digest:
            raise RuntimeContractError("offline conversation is bound to a different model/tokenizer")
        if not isinstance(row[3], str) or len(row[3].encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("persisted conversation exceeds byte budget")
        transcript = ChatTranscript.from_json(row[3])
        transcript.validate_turn_order()
        return StoredChat(sid, row[2], transcript, row[0], row[1])

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

    def commit(self, *, session: StoredChat, request_id: str,
               request_digest: str, transcript: ChatTranscript, text: str,
               output_digest: str, prompt_tokens: int,
               generated_tokens: int) -> OfflineTurnReceipt:
        rid = _identifier("request id", request_id)
        if not isinstance(transcript, ChatTranscript) or not isinstance(text, str):
            raise RuntimeContractError("invalid completed native chat result")
        transcript.validate_turn_order()
        encoded = transcript.to_json()
        if len(encoded.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
            raise RuntimeContractError("completed conversation exceeds persisted budget")
        if not isinstance(output_digest, str) or len(output_digest) != 64:
            raise RuntimeContractError("invalid native generation output digest")
        if any(type(n) is not int or n < 0 for n in (prompt_tokens, generated_tokens)):
            raise RuntimeContractError("invalid native generation token count")
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
                "WHERE session_id=? AND revision=? AND model_digest=? AND tokenizer_digest=?",
                (session.revision + 1, encoded, time.time_ns(), session.session_id,
                 session.revision, session.model_digest, session.tokenizer_digest),
            )
            if cursor.rowcount != 1:
                raise RuntimeContractError("offline conversation revision conflict")
            self._db.execute(
                "INSERT INTO offline_turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session.session_id, rid, request_digest, session.revision + 1,
                 text, output_digest, prompt_tokens, generated_tokens),
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
        # The engine owns token budgets, role framing and inference. On an
        # exception the store is never touched.
        result = self.engine.turn(session.transcript, message, config)
        generation = result.generation
        return self.store.commit(
            session=session,
            request_id=rid,
            request_digest=request_digest,
            transcript=result.transcript,
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
    parser.add_argument("--request-id", help="stable idempotency id for safe retries")
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="print receipt as JSON")
    args = parser.parse_args(argv)
    if args.session and args.system is not None:
        parser.error("--system only applies to new conversations")
    if args.request_id and args.interactive:
        parser.error("--request-id applies to one-shot --message only")
    if (args.list or args.delete_session) and (
        args.system is not None or args.session is not None or args.request_id is not None
    ):
        parser.error("session creation and turn arguments are invalid for list/delete")
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
    "StoredChat", "load_offline_engine", "main",
]
