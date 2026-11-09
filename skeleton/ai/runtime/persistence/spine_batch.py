"""Batch project for the P2 spine.

Projects a bounded list of operation ids. One failure is recorded and does not
stop the rest. This does not sign work off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.spine_dispatch import SpineDispatchHook, SpineDispatchReport


class SpineBatchError(RuntimeError):
    """Batch rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class SpineBatchReport:
    requested: int
    succeeded: int
    failed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "spine_batch",
            "hit": self.failed == 0,
            "law": "bounded-batch-project",
            "citation": "VOL-134",
            "requested": self.requested,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }


class SpineBatch:
    """Run the dispatch hook once per operation id."""

    def __init__(self, hook: SpineDispatchHook, *, max_ids: int = 32) -> None:
        if not isinstance(hook, SpineDispatchHook):
            raise SpineBatchError("hook must be a SpineDispatchHook")
        if isinstance(max_ids, bool) or not isinstance(max_ids, int) or max_ids < 1 or max_ids > 256:
            raise SpineBatchError("max_ids must be an integer from 1 to 256")
        self.hook = hook
        self.max_ids = max_ids

    def run(
        self,
        operation_ids: tuple[str, ...] | list[str],
        *,
        tenant_id: str,
        now: datetime | None = None,
    ) -> SpineBatchReport:
        if not isinstance(operation_ids, (tuple, list)):
            raise SpineBatchError("operation_ids must be a sequence")
        if len(operation_ids) > self.max_ids:
            raise SpineBatchError("operation_ids exceeds max_ids")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineBatchError("now must be timezone-aware")
        succeeded = 0
        failed = 0
        for operation_id in operation_ids:
            try:
                report: SpineDispatchReport = self.hook.run(
                    operation_id=operation_id,
                    tenant_id=tenant_id,
                    resource_id=f"op:{operation_id}",
                    now=instant,
                )
            except Exception:
                failed += 1
                continue
            if report.projection.poisoned:
                failed += 1
            else:
                succeeded += 1
        return SpineBatchReport(len(operation_ids), succeeded, failed)
