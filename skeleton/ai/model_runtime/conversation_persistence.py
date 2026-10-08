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
        with self._lock:
            sid = self.service.create()
            try:
                session = self.service._get(sid)
                self.store.create(sid, session, pinned=pinned)
                if pinned:
                    self.service.pin(sid)
                self._bindings[sid] = PersistenceBinding(
                    sid, 0, self.service.revision(sid))
                return sid
            except BaseException:
                self.service.delete(sid)
                raise

    def attach(self, session_id: str) -> PersistenceBinding:
        """Restore an existing durable ID into a live service instance."""
        with self._lock, self.service._lock:
            if self.service.exists(session_id):
                raise RuntimeContractError("session already loaded")
            if not self.service.can_admit():
                raise RuntimeContractError("session capacity exhausted")
            record = self.store.load(session_id)
            session = self.store.restore_session(session_id)
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
            revisions = self.store.save_many(tuple(updates))
            for sid, new_revision in revisions.items():
                self._bindings[sid] = PersistenceBinding(
                    sid, new_revision, self.service.revision(sid))
            return dict(self._bindings)

    def detach(self, session_id: str, *, save: bool = True) -> None:
        with self._lock:
            if session_id not in self._bindings:
                raise RuntimeContractError("session not bound to durable storage")
            if save:
                self.save(session_id)
            self.service.delete(session_id)
            del self._bindings[session_id]

    def delete(self, session_id: str) -> None:
        with self._lock:
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

    def bound_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._bindings))


__all__ = ["DurableConversationCoordinator", "PersistenceBinding"]
