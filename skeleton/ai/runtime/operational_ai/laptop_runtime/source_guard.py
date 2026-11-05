"""Monotonic installed-GGUF lease guard shared by laptop I/O and HTTP.

This guard never creates source rights, installs a model, grants native calls,
changes SQLite custody or certifies a physical device. The independent
installer and isolated native child remain the only source authorities.
"""
from __future__ import annotations

import threading
from typing import Any

from .contracts import identifier, refuse
from .identity import ActiveModel
from .installed_witness import require_activated_source
from .source_contract import valid_source_snapshot
from .dispatcher import LaptopDispatcher


class LocalSourceFence:
    """One-time source admission with permanent revocation after failure."""

    def __init__(
        self, worker: object, installed_receipt: object, *,
        tenant: str, subject: str,
    ) -> None:
        self.worker = worker
        self.receipt = installed_receipt
        self.tenant = identifier(tenant, "tenant")
        self.subject = identifier(subject, "subject")
        self.identity = ActiveModel.from_supervisor(worker)
        if (self.identity.tenant, self.identity.subject) != (
            self.tenant, self.subject,
        ):
            refuse("local GGUF worker belongs to another principal")
        source = require_activated_source(worker, installed_receipt)
        if not valid_source_snapshot(source, self.identity):
            refuse("complete installed GGUF source required")
        self.source = source.copy()
        self._mutex = threading.RLock()
        self._revoked = False
        # The initial source is only a snapshot, not a permanent grant.
        self.assert_live(worker)

    def assert_live(self, worker: object) -> None:
        """All private operations must observe this exact healthy child.

        After an unavailable health probe, missing lease, changed source,
        swapped worker or model epoch, this instance can never be resurrected
        by a later valid-looking observation. The operator must reactivate an
        independently checked model/lease to continue.
        """
        with self._mutex:
            if self._revoked:
                refuse("local installed GGUF source fence permanently revoked")
            try:
                if worker is not self.worker:
                    refuse("local GGUF source fence belongs to another worker")
                if ActiveModel.from_supervisor(worker) != self.identity:
                    refuse("local native principal or model identity changed")
                actual = require_activated_source(worker, self.receipt)
                if (not valid_source_snapshot(actual, self.identity)
                        or actual != self.source):
                    refuse("installed GGUF source, rights or live lease changed")
                if ActiveModel.from_supervisor(worker) != self.identity:
                    refuse("native principal changed after source inspection")
            except BaseException:
                self._revoked = True
                raise

    @property
    def release_certified(self) -> bool:
        return False


class SourceFencedLaptopDispatcher(LaptopDispatcher):
    """Bound the actual local HTTP dispatcher to one installed GGUF source.

    LaptopDispatcher still owns its single-flight lock and canonical SQLite
    replay; this wrapper adds source/rights/lease checks around every exposed
    operation and protocol metadata request, without allowing an alternate
    backend or inferred permissions.
    """

    def __init__(self, worker: Any, guard: LocalSourceFence) -> None:
        if not isinstance(guard, LocalSourceFence):
            refuse("typed installed model source guard required")
        guard.assert_live(worker)
        super().__init__(worker)
        self.source_guard = guard

    def _dispatch_exclusive(self, operation, data):
        """Check source under the same lock as SQLite and native effects.

        The base dispatch() owns the nonblocking single-flight admission.
        Source inspection outside that critical section would let a second
        request begin between a turn and its final lease verification.
        """
        self.source_guard.assert_live(self.worker)
        try:
            return super()._dispatch_exclusive(operation, data)
        finally:
            self.source_guard.assert_live(self.worker)

    def protocol(self):
        # Protocol reads also must not interleave active native work.
        if not self._flight.acquire(blocking=False):
            refuse("native dispatcher already has an active request")
        try:
            self.source_guard.assert_live(self.worker)
            try:
                return super().protocol()
            finally:
                self.source_guard.assert_live(self.worker)
        finally:
            self._flight.release()
