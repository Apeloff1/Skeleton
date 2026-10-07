"""Revisioned AI session checkpoint storage with compare-and-swap."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.ai.checkpoint import AISessionCheckpoint


@dataclass(frozen=True)
class StoredAISession:
    session_id: str
    revision: int
    checkpoint: AISessionCheckpoint
    superseded: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "revision": self.revision,
            "checkpoint_digest": self.checkpoint.digest,
            "superseded": self.superseded,
        }


class AISessionConflict(RuntimeError):
    pass


class AISessionStore:
    def __init__(self, *, max_sessions: int = 10000, max_versions: int = 128) -> None:
        if max_sessions <= 0 or max_versions <= 0:
            raise ValueError("AI session store limits must be positive")
        self.max_sessions = max_sessions
        self.max_versions = max_versions
        self._items: dict[str, list[StoredAISession]] = {}
        self._lock = threading.RLock()

    def put(
        self,
        checkpoint: AISessionCheckpoint,
        *,
        expected_revision: int | None = None,
    ) -> StoredAISession:
        with self._lock:
            history = self._items.get(checkpoint.session_id)
            if history is None:
                if len(self._items) >= self.max_sessions:
                    raise RuntimeError("AI session store capacity exhausted")
                if expected_revision not in {None, 0}:
                    raise AISessionConflict("AI session does not exist")
                item = StoredAISession(checkpoint.session_id, 1, checkpoint)
                self._items[checkpoint.session_id] = [item]
                return item
            current = history[-1]
            if expected_revision is not None and current.revision != expected_revision:
                raise AISessionConflict("AI session revision conflict")
            if current.checkpoint.digest == checkpoint.digest:
                return current
            history[-1] = StoredAISession(
                current.session_id,
                current.revision,
                current.checkpoint,
                True,
            )
            item = StoredAISession(
                checkpoint.session_id,
                current.revision + 1,
                checkpoint,
            )
            history.append(item)
            if len(history) > self.max_versions:
                del history[:-self.max_versions]
            return item

    def current(self, session_id: str) -> StoredAISession:
        with self._lock:
            return self._items[session_id][-1]

    def history(self, session_id: str) -> tuple[StoredAISession, ...]:
        with self._lock:
            return tuple(self._items[session_id])

    def at(self, session_id: str, revision: int) -> StoredAISession:
        with self._lock:
            for item in self._items[session_id]:
                if item.revision == revision:
                    return item
        raise KeyError((session_id, revision))
