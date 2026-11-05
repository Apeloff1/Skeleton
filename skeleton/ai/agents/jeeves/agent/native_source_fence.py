"""Fail-closed source and live-lease fence for an approved local Jeeves worker.

An independent descriptor-hashed installer receipt and the canonical isolated
GGUF child are checked before and after operator-visible native or private
SQLite actions. This class neither loads model bytes nor certifies installed
source *rights*, model quality, devices, WSL2 or release by itself.

The same worker object is mandatory throughout. No fallback, automatic
recovery, source reapproval or second model inference is performed here.
"""
from __future__ import annotations

import threading

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier, refuse,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import (
    ActiveModel,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.source_contract import (
    valid_source_snapshot,
)


class NativeSourceFence:
    """Read-only custody snapshot of one already-activated native GGUF."""

    def __init__(
        self, worker: object, installed_receipt: object, *,
        expected_tenant: str, expected_subject: str,
    ) -> None:
        tenant = identifier(expected_tenant, "tenant")
        subject = identifier(expected_subject, "subject")
        self._worker = worker
        self._receipt = installed_receipt
        self._principal = ActiveModel.from_supervisor(worker)
        if (self._principal.tenant, self._principal.subject) != (
            tenant, subject,
        ):
            refuse("activated Jeeves worker is not the requested owner")
        initial = require_activated_source(worker, installed_receipt)
        if not valid_source_snapshot(initial, self._principal):
            refuse("complete installed native source and model proof required")
        self._source = initial.copy()
        # Once a source, owner or capacity lease fails its live check,
        # this fence cannot be resurrected by a later transient healthy
        # report or an attacker reverting the archive to earlier bytes.
        self._lock = threading.RLock()
        self._revoked = False
        # A first witness is only a snapshot; the native model can still
        # exit, lose its resource lease or change its source after this point.
        self.assert_live(worker)

    def assert_live(self, worker: object) -> None:
        """Refuse stale or previously revoked installed GGUF custody.

        The same-instance lock makes revocation monotonic under concurrent
        chat, history, operator status and output publication. A real source
        failure is terminal for this fence, even if the child later recovers.
        Reopening requires a new installed-source activation and lease.
        """
        with self._lock:
            if self._revoked:
                refuse("native installed source fence permanently revoked")
            try:
                if worker is not self._worker:
                    refuse("source fence belongs to a different native worker")
                active = ActiveModel.from_supervisor(worker)
                if active != self._principal:
                    refuse("native model, tokenizer or operator scope changed")
                current = require_activated_source(worker, self._receipt)
                if (not valid_source_snapshot(current, self._principal)
                        or current != self._source):
                    refuse("installed GGUF source, rights or native lease changed")
                if ActiveModel.from_supervisor(worker) != self._principal:
                    refuse("native principal changed after source witness")
            except BaseException:
                # Never implicitly restore a previously failed source,
                # even after a malformed report, expired lease or wrong
                # owner appears transiently to become healthy again.
                self._revoked = True
                raise

    @property
    def principal(self) -> ActiveModel:
        return self._principal

    @property
    def release_certified(self) -> bool:
        # This source guard does not grant release, physical capacity,
        # model quality or third-party rights qualification.
        return False


__all__ = ["NativeSourceFence", "valid_source_snapshot"]
