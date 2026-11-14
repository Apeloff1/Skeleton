"""Private SQLite admission metadata for opt-in local chat queues.

A queue-owner lease is separate from the native inference lease. The former
fences recovery of admission metadata; the latter remains the only authority
for model execution. This ledger contains no prompt, scope, output or token.
An interrupted admission is never evidence that inference did or did not run.
Only a committed conversation receipt proves a completed reply.
"""
from __future__ import annotations

from pathlib import Path
import re
import threading
import time

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _identifier
from skeleton.app.jeeves_local_lease import LocalInferenceLease

MAX_ADMISSIONS = 4096
MAX_SESSION_ADMISSIONS = 256
MAX_RECOVERY_ROWS = 32
FINAL_STATES = frozenset({"settled", "failed", "cancelled", "interrupted"})


class AdmissionRejected(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class QueueAdmissionOwner:
    """Hold one non-inherited, workspace-scoped OS lease on its own thread.

    No model or user callback runs on that thread. A live peer cannot declare
    pending work interrupted; the owner is released only after local workers
    and their SQLite authority have drained.
    """

    def __init__(self, database: Path) -> None:
        self._lease = LocalInferenceLease(
            database.with_name(database.name + ".turn-queue")
        )
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._failed = threading.Event()
        self._thread = threading.Thread(
            target=self._hold, name="skeleton-turn-queue-owner", daemon=False,
        )
        self._thread.start()
        if not self._ready.wait(10) or self._failed.is_set():
            self.close()
            raise AdmissionRejected(503, "exclusive local queue ownership unavailable")

    def _hold(self) -> None:
        try:
            with self._lease.hold():
                self._ready.set()
                self._stop.wait()
        except BaseException:
            self._failed.set()
            self._ready.set()

    def assert_owned(self) -> None:
        if (not self._ready.is_set() or self._failed.is_set()
                or self._stop.is_set() or not self._thread.is_alive()):
            raise AdmissionRejected(503, "exclusive local queue ownership unavailable")

    def close(self) -> None:
        self._stop.set()
        self._thread.join()


class DurableTurnAdmissions:
    """Additive metadata in the existing model-scoped conversation authority."""

    def __init__(self, store: OfflineChatStore, model: str, tokenizer: str) -> None:
        self._store = store
        self._model = model
        self._tokenizer = tokenizer
        with store._transaction():
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_turn_admissions (
                session_id TEXT NOT NULL REFERENCES offline_sessions(session_id) ON DELETE CASCADE,
                request_id TEXT NOT NULL,
                request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
                attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 2147483647),
                state TEXT NOT NULL CHECK(state IN ('admitted','settled','failed','cancelled','interrupted')),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(session_id, request_id)
            )""")

    def _scope(self, sid: str) -> str:
        sid = _identifier("session id", sid)
        found = self._store._db.execute(
            "SELECT 1 FROM offline_sessions WHERE session_id=? "
            "AND model_digest=? AND tokenizer_digest=?",
            (sid, self._model, self._tokenizer),
        ).fetchone()
        if found is None:
            raise AdmissionRejected(404, "local conversation unavailable")
        return sid

    def recover(self, owner: QueueAdmissionOwner) -> None:
        owner.assert_owned()
        with self._store._transaction():
            self._store._db.execute(
                "UPDATE offline_turn_admissions SET state='interrupted',updated_at=? "
                "WHERE state='admitted' AND session_id IN "
                "(SELECT session_id FROM offline_sessions WHERE model_digest=? AND tokenizer_digest=?)",
                (time.time(), self._model, self._tokenizer),
            )

    def lookup(self, sid: str, rid: str) -> dict[str, object] | None:
        rid = _identifier("request id", rid)
        with self._store.read_snapshot():
            sid = self._scope(sid)
            row = self._store._db.execute(
                "SELECT request_digest,attempt,state,created_at,updated_at "
                "FROM offline_turn_admissions WHERE session_id=? AND request_id=?",
                (sid, rid),
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("digest", "attempt", "state", "created_at", "updated_at"), row))

    def claim(self, owner: QueueAdmissionOwner, sid: str, rid: str,
              digest: str, *, retry: bool) -> int:
        owner.assert_owned()
        rid = _identifier("request id", rid)
        if type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise AdmissionRejected(400, "invalid admission identity")
        if type(retry) is not bool:
            raise AdmissionRejected(400, "invalid admission retry")
        with self._store._transaction():
            sid = self._scope(sid)
            row = self._store._db.execute(
                "SELECT request_digest,attempt,state FROM offline_turn_admissions "
                "WHERE session_id=? AND request_id=?", (sid, rid),
            ).fetchone()
            now = time.time()
            # A peer may commit between the HTTP replay check and this
            # write transaction. Never reserve a new attempt over that truth.
            committed = self._store._db.execute(
                "SELECT request_digest FROM offline_turns WHERE session_id=? AND request_id=?",
                (sid, rid),
            ).fetchone()
            if committed is not None:
                if committed[0] != digest:
                    raise AdmissionRejected(409, "request ID belongs to different turn content")
                raise AdmissionRejected(409, "reply already committed; read saved history")
            if row is not None:
                previous_digest, attempt, state = row
                if previous_digest != digest:
                    raise AdmissionRejected(409, "request ID belongs to different turn content")
                if not retry or state == "settled" or attempt >= 2147483647:
                    raise AdmissionRejected(409, "exact explicit retry required; verify saved reply first")
                # The application checks the live ticket under its admission
                # lock. Exclusive owner custody excludes a second queue process.
                changed = self._store._db.execute(
                    "UPDATE offline_turn_admissions SET attempt=?,state='admitted',updated_at=? "
                    "WHERE session_id=? AND request_id=? AND attempt=? AND request_digest=?",
                    (attempt + 1, now, sid, rid, attempt, digest),
                )
                if changed.rowcount != 1:
                    raise AdmissionRejected(409, "admission identity changed")
                return attempt + 1
            total = self._store._db.execute(
                "SELECT COUNT(*) FROM offline_turn_admissions"
            ).fetchone()[0]
            count = self._store._db.execute(
                "SELECT COUNT(*) FROM offline_turn_admissions WHERE session_id=?", (sid,),
            ).fetchone()[0]
            if total >= MAX_ADMISSIONS or count >= MAX_SESSION_ADMISSIONS:
                raise AdmissionRejected(429, "durable admission capacity reached; export and delete old conversations")
            self._store._db.execute(
                "INSERT INTO offline_turn_admissions VALUES (?,?,?,?,?,?,?)",
                (sid, rid, digest, 1, "admitted", now, now),
            )
            return 1

    def finish(self, owner: QueueAdmissionOwner, sid: str, rid: str,
               digest: str, attempt: int, state: str) -> None:
        owner.assert_owned()
        if state not in FINAL_STATES or state == "interrupted":
            raise AdmissionRejected(409, "invalid admission settlement")
        with self._store._transaction():
            changed = self._store._db.execute(
                "UPDATE offline_turn_admissions SET state=?,updated_at=? "
                "WHERE session_id=? AND request_id=? AND request_digest=? "
                "AND attempt=? AND state='admitted'",
                (state, time.time(), sid, rid, digest, attempt),
            )
            if changed.rowcount != 1:
                raise AdmissionRejected(409, "admission settlement identity changed")

    def recovery_rows(self, sid: str) -> list[dict[str, object]]:
        with self._store.read_snapshot():
            sid = self._scope(sid)
            rows = self._store._db.execute(
                "SELECT a.request_id,a.attempt,a.state,a.created_at,a.updated_at "
                "FROM offline_turn_admissions a WHERE a.session_id=? "
                "AND NOT EXISTS (SELECT 1 FROM offline_turns t "
                "WHERE t.session_id=a.session_id AND t.request_id=a.request_id) "
                "ORDER BY a.updated_at DESC,a.request_id LIMIT ?",
                (sid, MAX_RECOVERY_ROWS),
            ).fetchall()
        return [dict(zip(("request_id", "attempt", "state", "created_at", "updated_at"), row))
                for row in rows]

    def assert_unowned(self, sid: str, rid: str) -> None:
        if self.lookup(sid, rid) is not None:
            raise AdmissionRejected(409, "request has durable queue custody; use the exact queue recovery path")

    def assert_deletable(self, sid: str) -> None:
        with self._store.read_snapshot():
            sid = self._scope(sid)
            if self._store._db.execute(
                "SELECT 1 FROM offline_turn_admissions WHERE session_id=? AND state='admitted' LIMIT 1",
                (sid,),
            ).fetchone() is not None:
                raise AdmissionRejected(409, "local queue admission is unresolved")


__all__ = ["AdmissionRejected", "DurableTurnAdmissions", "QueueAdmissionOwner"]
