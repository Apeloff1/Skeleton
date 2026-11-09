"""Explicit persistence bridge between live conversations and SQLite.

This layer does not silently overwrite concurrent database changes. Each
binding tracks its last acknowledged durable revision.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Mapping

from .conversation_service import NativeConversationService
from .conversation_store import ConversationStore
from .runtime_contracts import RuntimeContractError


@dataclass(frozen=True)
class PersistenceBinding:
    session_id: str
    durable_revision: int
    live_revision: int


class DurableConversationCoordinator:
    def __init__(self, service: NativeConversationService,
                 store: ConversationStore) -> None:
        if not isinstance(service, NativeConversationService):
            raise RuntimeContractError("conversation service required")
        if not isinstance(store, ConversationStore):
            raise RuntimeContractError("conversation store required")
        if service.runtime is not store.runtime:
            raise RuntimeContractError("service and store must share the same runtime")
        self.service = service
        self.store = store
        self._lock = threading.RLock()
        self._bindings: dict[str, PersistenceBinding] = {}

    def create(self, *, pinned: bool = False) -> str:
        with self._lock, self.service._lock:
            sid = self.service.create()
            try:
                session = self.service._get(sid)
                if pinned:
                    self.service.pin(sid)
                self.store.create(sid, session, pinned=pinned)
                self._bindings[sid] = PersistenceBinding(
                    sid, 0, self.service.revision(sid))
                return sid
            except BaseException:
                self.service.delete(sid)
                raise

    def attach(self, session_id: str) -> PersistenceBinding:
        """Restore an existing durable ID into a live service instance."""
        with self._lock, self.service._lock:
            if session_id in self._bindings:
                raise RuntimeContractError("session already bound")
            if self.service.exists(session_id):
                raise RuntimeContractError("session already loaded")
            if not self.service.can_admit():
                raise RuntimeContractError("session capacity exhausted")
            record = self.store.load(session_id)
            from .native_llm_runtime import NativeConversationSession
            session = NativeConversationSession.restore(self.store.runtime, record.snapshot)
            self.service._sessions[session_id] = session
            self.service._meta[session_id] = {
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "revision": record.revision,
                "pinned": record.pinned,
            }
            binding = PersistenceBinding(session_id, record.revision, record.revision)
            self._bindings[session_id] = binding
            return binding

    def save(self, session_id: str) -> PersistenceBinding:
        with self._lock, self.service._lock:
            binding = self._bindings.get(session_id)
            if binding is None:
                raise RuntimeContractError("session not bound to durable storage")
            current = self.service.revision(session_id)
            if current < binding.live_revision:
                raise RuntimeContractError("live revision regressed")
            session = self.service._get(session_id)
            pinned = self.service.is_pinned(session_id)
            new_revision = self.store.save(session_id, binding.durable_revision,
                                           session, pinned=pinned)
            updated = PersistenceBinding(session_id, new_revision, current)
            self._bindings[session_id] = updated
            return updated

    def save_all(self) -> Mapping[str, PersistenceBinding]:
        """Atomic checkpoint of all bound sessions."""
        with self._lock, self.service._lock:
            updates = []
            for sid, binding in self._bindings.items():
                current = self.service.revision(sid)
                if current < binding.live_revision:
                    raise RuntimeContractError("live revision regressed")
                updates.append((sid, binding.durable_revision, self.service._get(sid)))
            pinned = {sid: self.service.is_pinned(sid) for sid, _, _ in updates}
            revisions = self.store.save_many(tuple(updates), pinned=pinned)
            for sid, new_revision in revisions.items():
                self._bindings[sid] = PersistenceBinding(
                    sid, new_revision, self.service.revision(sid))
            return dict(self._bindings)

    def save_dirty(self) -> Mapping[str, PersistenceBinding]:
        """Persist only sessions modified since their last checkpoint."""
        with self._lock, self.service._lock:
            dirty = []
            for sid, binding in self._bindings.items():
                current = self.service.revision(sid)
                if current != binding.live_revision:
                    dirty.append((sid, binding.durable_revision, self.service._get(sid)))
            if not dirty:
                return {}
            pinned = {sid: self.service.is_pinned(sid) for sid, _, _ in dirty}
            revisions = self.store.save_many(tuple(dirty), pinned=pinned)
            result = {}
            for sid, durable_revision in revisions.items():
                binding = PersistenceBinding(
                    sid, durable_revision, self.service.revision(sid))
                self._bindings[sid] = binding
                result[sid] = binding
            return result

    def dirty_ids(self) -> tuple[str, ...]:
        with self._lock, self.service._lock:
            return tuple(sorted(sid for sid, binding in self._bindings.items()
                                if self.service.revision(sid) != binding.live_revision))

    def reload(self, session_id: str) -> PersistenceBinding:
        """Replace unmodified live state with the latest validated disk state."""
        with self._lock, self.service._lock:
            binding = self.binding(session_id)
            if self.service.revision(session_id) != binding.live_revision:
                raise RuntimeContractError("refusing to discard unsaved live changes")
            record = self.store.load(session_id)
            if record.revision < binding.durable_revision:
                raise RuntimeContractError("durable revision regressed")
            from .native_llm_runtime import NativeConversationSession
            restored = NativeConversationSession.restore(self.store.runtime, record.snapshot)
            self.service._sessions[session_id] = restored
            self.service._meta[session_id]["revision"] = record.revision
            self.service._meta[session_id]["updated_at"] = record.updated_at
            self.service._meta[session_id]["pinned"] = record.pinned
            new_binding = PersistenceBinding(session_id, record.revision, record.revision)
            self._bindings[session_id] = new_binding
            return new_binding

    def detach(self, session_id: str, *, save: bool = True) -> None:
        with self._lock, self.service._lock:
            if session_id not in self._bindings:
                raise RuntimeContractError("session not bound to durable storage")
            if save:
                self.save(session_id)
            self.service.delete(session_id)
            del self._bindings[session_id]

    def delete(self, session_id: str) -> None:
        with self._lock, self.service._lock:
            binding = self._bindings.get(session_id)
            if binding is None:
                raise RuntimeContractError("session not bound to durable storage")
            self.store.delete(session_id, expected_revision=binding.durable_revision)
            self.service.delete(session_id)
            del self._bindings[session_id]

    def binding(self, session_id: str) -> PersistenceBinding:
        with self._lock:
            try:
                return self._bindings[session_id]
            except KeyError as exc:
                raise RuntimeContractError("session not bound to durable storage") from exc

    def checkpoint_and_detach(self, session_id: str) -> PersistenceBinding:
        """Atomically checkpoint a live session before removing its binding."""
        with self._lock, self.service._lock:
            saved = self.save(session_id)
            self.service.delete(session_id)
            del self._bindings[session_id]
            return saved

    def recover_all(self, *, limit: int = 1000) -> tuple[str, ...]:
        """Restore a bounded cohort of persisted sessions after restart."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise RuntimeContractError("invalid recovery limit")
        with self._lock, self.service._lock:
            available = self.service.capacity_remaining()
            if available <= 0:
                return ()
            ids = self.store.list_ids(limit=min(limit, available))
            restored = []
            for sid in ids:
                if sid in self._bindings or self.service.exists(sid):
                    continue
                self.attach(sid)
                restored.append(sid)
            return tuple(restored)

    def bound_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._bindings))


__all__ = ["DurableConversationCoordinator", "PersistenceBinding"]
