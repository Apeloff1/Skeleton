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


_SOURCE_FIELDS = frozenset((
    "model_sha256", "tokenizer_sha256", "manifest_sha256",
    "archive_sha256", "source_sha", "installed_model_bytes",
    "installed_shard_count",
))

_HEX = frozenset("0123456789abcdef")


def valid_source_snapshot(snapshot: object, principal: ActiveModel) -> bool:
    """Reject malformed source custody even if an injected witness claims success.

    The canonical installed-source inspector remains the authority for the
    operating system's descriptors, rights, isolated child and capacity lease.
    This pure shape check is deliberately narrower than that authority: it
    prevents a drift between readiness and publication guards, including
    bool-as-int inventory fields and spurious additional source keys.
    """
    if type(snapshot) is not dict or set(snapshot) != _SOURCE_FIELDS:
        return False
    if (
        snapshot["model_sha256"] != principal.model_sha256
        or snapshot["tokenizer_sha256"] != principal.tokenizer_sha256
    ):
        return False
    for key in (
        "model_sha256", "tokenizer_sha256",
        "manifest_sha256", "archive_sha256",
    ):
        value = snapshot[key]
        if type(value) is not str or len(value) != 64 or not set(value) <= _HEX:
            return False
    source = snapshot["source_sha"]
    if type(source) is not str or len(source) not in (40, 64) or not set(source) <= _HEX:
        return False
    size = snapshot["installed_model_bytes"]
    shards = snapshot["installed_shard_count"]
    if type(size) is not int or not 1 <= size <= 10**12:
        return False
    if type(shards) is not int or not 1 <= shards <= 65536:
        return False
    return True


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
