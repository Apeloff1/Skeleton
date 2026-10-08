"""Bounded multi-session serving plane for native Skeleton transformer conversations.

This is a synchronous in-process serving layer, not a distributed queue or database.
Every session is isolated by a server-assigned opaque identifier.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets
import threading
import time
from typing import Any, Mapping

from .native_llm_runtime import NativeConversationSession, NativeLLMRuntime, GenerationResult
from .runtime_contracts import GenerationConfig, RuntimeContractError


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    created_at: float
    updated_at: float
    revision: int
    turns: int
    context_tokens: int
    pinned: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class ServingReceipt:
    request_id: str
    session_id: str
    revision: int
    output_digest: str
    elapsed_ms: float
    generated_tokens: int


class NativeConversationService:
    """Thread-safe session registry with bounded storage and atomic turns.

    40 public operations cover session lifecycle, inference, state, governance,
    admission, observability and portable persistence. Model execution is
    serialized to protect mutable transformer device/cache state.
    """

    def __init__(self, runtime: NativeLLMRuntime, *, max_sessions: int = 128,
                 max_events: int = 2048, idle_seconds: float = 3600.0) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise RuntimeContractError("NativeLLMRuntime required")
        if type(max_sessions) is not int or not 1 <= max_sessions <= 100000:
            raise RuntimeContractError("invalid session capacity")
        if type(max_events) is not int or not 1 <= max_events <= 100000:
            raise RuntimeContractError("invalid event capacity")
        if not isinstance(idle_seconds, (int, float)) or not 1 <= idle_seconds <= 31536000:
            raise RuntimeContractError("invalid idle timeout")
        self.runtime = runtime
        self.max_sessions = max_sessions
        self.idle_seconds = float(idle_seconds)
        self._lock = threading.RLock()
        self._sessions: dict[str, NativeConversationSession] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._requests = 0
        self._failures = 0
        self._generated = 0

    def _get(self, session_id: str) -> NativeConversationSession:
        if not isinstance(session_id, str) or session_id not in self._sessions:
            raise RuntimeContractError("unknown conversation session")
        return self._sessions[session_id]

    def _touch(self, session_id: str) -> None:
        self._meta[session_id]["updated_at"] = time.time()
        self._meta[session_id]["revision"] += 1

    def _event(self, action: str, session_id: str, **fields: Any) -> None:
        self._events.append({"action": action, "session_id": session_id,
                             "timestamp": time.time(), **fields})

    # Session lifecycle (1-10)
    def create(self) -> str:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeContractError("session capacity exhausted")
            sid = secrets.token_urlsafe(24)
            now = time.time()
            self._sessions[sid] = NativeConversationSession(self.runtime)
            self._meta[sid] = {"created_at": now, "updated_at": now,
                               "revision": 0, "pinned": False}
            self._event("create", sid)
            return sid

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id)
            del self._sessions[session_id]
            del self._meta[session_id]
            self._event("delete", session_id)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return isinstance(session_id, str) and session_id in self._sessions

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def list_sessions(self) -> tuple[SessionRecord, ...]:
        with self._lock:
            return tuple(self.describe(sid) for sid in sorted(self._sessions))

    def describe(self, session_id: str) -> SessionRecord:
        with self._lock:
            session = self._get(session_id)
            m = self._meta[session_id]
            return SessionRecord(session_id, m["created_at"], m["updated_at"],
                                 m["revision"], session.turns, session.context_used,
                                 m["pinned"])

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id).reset()
            self._touch(session_id)
            self._event("reset", session_id)

    def fork(self, session_id: str) -> str:
        with self._lock:
            parent = self._get(session_id)
            sid = self.create()
            self._sessions[sid] = parent.fork()
            self._event("fork", sid, parent_id=session_id)
            return sid

    def pin(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id)
            self._meta[session_id]["pinned"] = True
            self._touch(session_id)

    def unpin(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id)
            self._meta[session_id]["pinned"] = False
            self._touch(session_id)

    # Token-native state and inference (11-20)
    def tokens(self, session_id: str) -> tuple[int, ...]:
        with self._lock:
            return self._get(session_id).token_ids

    def text(self, session_id: str) -> str:
        with self._lock:
            return self._get(session_id).history_text()

    def digest(self, session_id: str) -> str:
        with self._lock:
            return self._get(session_id).history_digest()

    def remaining(self, session_id: str) -> int:
        with self._lock:
            return self._get(session_id).context_remaining

    def preview(self, session_id: str, prompt: str) -> tuple[int, ...]:
        with self._lock:
            return self._get(session_id).preview_context(prompt)

    def preview_kv(self, session_id: str, prompt: str) -> int:
        with self._lock:
            return self._get(session_id).preview_kv_bytes(prompt)

    def infer(self, session_id: str, prompt: str, *, use_cache: bool = True):
        with self._lock:
            return self._get(session_id).infer_next(prompt, use_cache=use_cache)

    def append_text(self, session_id: str, text: str) -> None:
        with self._lock:
            self._get(session_id).append_text(text)
            self._touch(session_id)
            self._event("append", session_id)

    def append_tokens(self, session_id: str, token_ids: tuple[int, ...]) -> None:
        with self._lock:
            self._get(session_id).append_tokens(token_ids)
            self._touch(session_id)
            self._event("append", session_id)

    def truncate(self, session_id: str, keep_last: int) -> None:
        with self._lock:
            self._get(session_id).truncate(keep_last)
            self._touch(session_id)
            self._event("truncate", session_id)

    # Serving and controlled mutation (21-30)
    def generate(self, session_id: str, prompt: str,
                 config: GenerationConfig | None = None) -> GenerationResult:
        with self._lock:
            session = self._get(session_id)
            self._requests += 1
            started = time.monotonic()
            try:
                result = session.generate(prompt, config)
            except Exception:
                self._failures += 1
                self._event("generation_failed", session_id)
                raise
            self._generated += len(result.generated_ids)
            self._touch(session_id)
            self._event("generate", session_id, output_digest=result.output_digest,
                        generated_tokens=len(result.generated_ids),
                        elapsed_ms=round((time.monotonic()-started)*1000, 3))
            return result

    def generate_receipt(self, session_id: str, prompt: str,
                         config: GenerationConfig | None = None) -> ServingReceipt:
        start = time.monotonic()
        result = self.generate(session_id, prompt, config)
        return ServingReceipt(secrets.token_urlsafe(18), session_id,
                              self.describe(session_id).revision, result.output_digest,
                              round((time.monotonic()-start)*1000, 3),
                              len(result.generated_ids))

    def compare_and_generate(self, session_id: str, expected_revision: int,
                             prompt: str, config: GenerationConfig | None = None):
        with self._lock:
            if type(expected_revision) is not int or self.describe(session_id).revision != expected_revision:
                raise RuntimeContractError("session revision conflict")
            return self.generate(session_id, prompt, config)

    def compare_and_append(self, session_id: str, expected_revision: int,
                           token_ids: tuple[int, ...]) -> None:
        with self._lock:
            if type(expected_revision) is not int or self.describe(session_id).revision != expected_revision:
                raise RuntimeContractError("session revision conflict")
            self.append_tokens(session_id, token_ids)

    def replace(self, session_id: str, token_ids: tuple[int, ...]) -> None:
        with self._lock:
            self._get(session_id).replace_history(token_ids)
            self._touch(session_id)
            self._event("replace", session_id)

    def merge(self, target_id: str, source_id: str) -> None:
        with self._lock:
            if target_id == source_id:
                raise RuntimeContractError("cannot merge session into itself")
            self._get(target_id).merge_history(self._get(source_id))
            self._touch(target_id)
            self._event("merge", target_id, source_id=source_id)

    def drop_prefix(self, session_id: str, count: int) -> None:
        with self._lock:
            self._get(session_id).drop_prefix(count)
            self._touch(session_id)

    def capacity_for(self, session_id: str, prompt: str) -> int:
        with self._lock:
            return self._get(session_id).capacity_for(prompt)

    def is_empty(self, session_id: str) -> bool:
        with self._lock:
            return self._get(session_id).is_empty

    def turns(self, session_id: str) -> int:
        with self._lock:
            return self._get(session_id).turns

    # Bulk lifecycle, state transfer and capacity governance
    def create_many(self, count: int) -> tuple[str, ...]:
        """Create an all-or-nothing cohort without exceeding session capacity."""
        with self._lock:
            if type(count) is not int or count < 0 or count > self.max_sessions:
                raise RuntimeContractError("invalid cohort size")
            if len(self._sessions) + count > self.max_sessions:
                raise RuntimeContractError("session capacity exhausted")
            return tuple(self.create() for _ in range(count))

    def delete_many(self, session_ids: tuple[str, ...]) -> int:
        """Delete a cohort after validating every identifier."""
        with self._lock:
            ids = tuple(session_ids)
            if len(set(ids)) != len(ids):
                raise RuntimeContractError("duplicate session identifiers")
            for sid in ids:
                self._get(sid)
            for sid in ids:
                self.delete(sid)
            return len(ids)

    def snapshot_many(self, session_ids: tuple[str, ...]) -> dict[str, Mapping[str, Any]]:
        with self._lock:
            ids = tuple(session_ids)
            if len(set(ids)) != len(ids):
                raise RuntimeContractError("duplicate session identifiers")
            return {sid: self.snapshot(sid) for sid in ids}

    def restore_many(self, snapshots: tuple[Mapping[str, Any], ...]) -> tuple[str, ...]:
        """Validate the entire cohort before allocating any session IDs."""
        with self._lock:
            items = tuple(snapshots)
            if len(self._sessions) + len(items) > self.max_sessions:
                raise RuntimeContractError("session capacity exhausted")
            restored = [NativeConversationSession.restore(self.runtime, item) for item in items]
            ids = self.create_many(len(restored))
            for sid, session in zip(ids, restored):
                self._sessions[sid] = session
                self._event("restore", sid)
            return ids

    def clear_unpinned(self) -> int:
        with self._lock:
            ids = tuple(sid for sid, meta in self._meta.items() if not meta["pinned"])
            return self.delete_many(ids)

    def capacity_remaining(self) -> int:
        with self._lock:
            return self.max_sessions - len(self._sessions)

    def pinned_count(self) -> int:
        with self._lock:
            return sum(bool(meta["pinned"]) for meta in self._meta.values())

    def evict_oldest_unpinned(self) -> str | None:
        with self._lock:
            candidates = (sid for sid in self._sessions if not self._meta[sid]["pinned"])
            sid = min(candidates, key=lambda key: self._meta[key]["updated_at"], default=None)
            if sid is not None:
                self.delete(sid)
            return sid

    def enforce_capacity(self, target: int) -> int:
        with self._lock:
            if type(target) is not int or not 0 <= target <= self.max_sessions:
                raise RuntimeContractError("invalid target capacity")
            excess = len(self._sessions) - target
            if excess <= 0:
                return 0
            candidates = sorted(
                (sid for sid in self._sessions if not self._meta[sid]["pinned"]),
                key=lambda sid: self._meta[sid]["updated_at"],
            )
            if len(candidates) < excess:
                raise RuntimeContractError("pinned sessions prevent capacity enforcement")
            self.delete_many(tuple(candidates[:excess]))
            return excess

    def session_age_seconds(self, session_id: str) -> float:
        with self._lock:
            self._get(session_id)
            return max(0.0, time.time() - self._meta[session_id]["created_at"])

    def session_idle_seconds(self, session_id: str) -> float:
        with self._lock:
            self._get(session_id)
            return max(0.0, time.time() - self._meta[session_id]["updated_at"])

    def find_by_digest(self, history_digest: str) -> tuple[str, ...]:
        with self._lock:
            if not isinstance(history_digest, str) or len(history_digest) != 64:
                raise RuntimeContractError("invalid history digest")
            return tuple(sid for sid in self._sessions
                         if hmac.compare_digest(self.digest(sid), history_digest))

    def context_utilization(self) -> Mapping[str, int]:
        with self._lock:
            values = [session.context_used for session in self._sessions.values()]
            return {"total_tokens": sum(values), "max_tokens": max(values, default=0),
                    "session_count": len(values),
                    "context_capacity": self.runtime.limits.max_context * len(values)}

    def export_manifest(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "runtime_model_digest": self.runtime.model_digest,
                "session_count": len(self._sessions),
                "sessions": [self.describe(sid).to_dict() for sid in sorted(self._sessions)],
                "metrics": dict(self.metrics()),
            }

    def verify_all_sessions(self) -> int:
        with self._lock:
            for session in self._sessions.values():
                session._assert_identity()
            return len(self._sessions)

    # Portability, governance and observability (31-40)
    def snapshot(self, session_id: str) -> Mapping[str, Any]:
        with self._lock:
            return self._get(session_id).snapshot()

    def snapshot_json(self, session_id: str) -> str:
        with self._lock:
            return json.dumps(self.snapshot(session_id), sort_keys=True,
                              separators=(",", ":"), allow_nan=False)

    def restore(self, snapshot: Mapping[str, Any]) -> str:
        with self._lock:
            restored = NativeConversationSession.restore(self.runtime, snapshot)
            sid = self.create()
            self._sessions[sid] = restored
            self._event("restore", sid)
            return sid

    def restore_json(self, payload: str) -> str:
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > 2_000_000:
            raise RuntimeContractError("invalid or oversized session JSON")
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise RuntimeContractError("invalid session JSON") from exc
        return self.restore(obj)

    def prune_idle(self) -> int:
        with self._lock:
            now = time.time()
            expired = [sid for sid, m in self._meta.items()
                       if not m["pinned"] and now-m["updated_at"] >= self.idle_seconds]
            for sid in expired:
                self.delete(sid)
            return len(expired)

    def oldest(self) -> SessionRecord | None:
        with self._lock:
            if not self._sessions:
                return None
            sid = min(self._meta, key=lambda key: self._meta[key]["created_at"])
            return self.describe(sid)

    def newest(self) -> SessionRecord | None:
        with self._lock:
            if not self._sessions:
                return None
            sid = max(self._meta, key=lambda key: self._meta[key]["created_at"])
            return self.describe(sid)

    def metrics(self) -> Mapping[str, int]:
        with self._lock:
            return {"sessions": len(self._sessions), "requests": self._requests,
                    "failures": self._failures, "generated_tokens": self._generated,
                    "events": len(self._events)}

    def recent_events(self, limit: int = 100) -> tuple[Mapping[str, Any], ...]:
        if type(limit) is not int or not 0 <= limit <= self._events.maxlen:
            raise RuntimeContractError("invalid event limit")
        with self._lock:
            return tuple(list(self._events)[-limit:]) if limit else ()

    def health(self) -> Mapping[str, Any]:
        with self._lock:
            return {"metrics": self.metrics(), "capacity": self.max_sessions,
                    "runtime": self.runtime.health_snapshot()}


__all__ = ["NativeConversationService", "SessionRecord", "ServingReceipt"]
