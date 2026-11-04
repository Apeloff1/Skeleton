"""Fail-closed source and live-lease fence for an approved local Jeeves worker.

An independent descriptor-hashed installer receipt and the canonical isolated
GGUF child are checked before and after operator-visible native or private
SQLite actions. This class neither loads model bytes nor certifies installed
source *rights*, model quality, devices, WSL2 or release by itself.

The same worker object is mandatory throughout. No fallback, automatic
recovery, source reapproval or second model inference is performed here.
"""
from __future__ import annotations

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
        if (type(initial) is not dict
                or set(initial) != _SOURCE_FIELDS
                or initial["model_sha256"] != self._principal.model_sha256
                or initial["tokenizer_sha256"] != self._principal.tokenizer_sha256):
            refuse("complete installed native source and model proof required")
        self._source = initial.copy()
        # A first witness is only a snapshot; the native model can still
        # exit, lose its resource lease or change its source after this point.
        self.assert_live(worker)

    def assert_live(self, worker: object) -> None:
        """Refuse stale native identity or source before publication."""

        if worker is not self._worker:
            refuse("source fence belongs to a different native worker")
        active = ActiveModel.from_supervisor(worker)
        if active != self._principal:
            refuse("native model, tokenizer or operator scope changed")
        current = require_activated_source(worker, self._receipt)
        if type(current) is not dict or current != self._source:
            refuse("installed GGUF source, rights or native lease changed")
        if ActiveModel.from_supervisor(worker) != self._principal:
            refuse("native principal changed after source witness")

    @property
    def principal(self) -> ActiveModel:
        return self._principal

    @property
    def release_certified(self) -> bool:
        # This source guard does not grant release, physical capacity,
        # model quality or third-party rights qualification.
        return False


__all__ = ["NativeSourceFence"]
