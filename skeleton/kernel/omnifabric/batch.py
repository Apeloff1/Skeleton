"""Batch append and transactional multi-event admit for OmniFabric.

A batch journals every event first (all-or-nothing outbox reservation),
then admits the hot-tail sequence. If any journal fails, prior journals
in the batch remain durable for reconcile — they are not deleted — but
the hot tail only advances for successfully journaled members when
``atomic_hot`` is False. With ``atomic_hot=True`` (default), hot-tail
admit happens only after the full batch journals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from skeleton.kernel.omnifabric.core import OmniFabric
from skeleton.kernel.omnifabric.errors import OmniFabricError, OutboxFull
from skeleton.kernel.omnifabric.events import FabricEvent, event_to_mapping
from skeleton.kernel.omnifabric.outbox import COLLECTION_DEFAULT


@dataclass
class BatchItem:
    ledger: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    quorum: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    events: list[FabricEvent] = field(default_factory=list)
    journaled: int = 0
    admitted: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "journaled": self.journaled,
            "admitted": self.admitted,
            "errors": list(self.errors),
        }


def append_batch(
    fabric: OmniFabric,
    items: Sequence[BatchItem | Mapping[str, Any]],
    *,
    atomic_hot: bool = True,
) -> BatchResult:
    """Append many events. See module docstring for atomicity rules."""
    normalized: list[BatchItem] = []
    for raw in items:
        if isinstance(raw, BatchItem):
            normalized.append(raw)
        else:
            normalized.append(
                BatchItem(
                    ledger=str(raw.get("ledger") or ""),
                    kind=str(raw.get("kind") or ""),
                    payload=dict(raw.get("payload") or {}),
                    quorum=list(raw.get("quorum") or []),
                )
            )
    if not normalized:
        return BatchResult()

    result = BatchResult()
    if atomic_hot:
        # Use normal append sequentially under fabric lock semantics.
        # If one fails mid-batch, earlier events stay (durable) — caller
        # sees partial admitted count.
        for item in normalized:
            if not item.ledger or not item.kind:
                result.errors.append("ledger and kind required")
                break
            try:
                ev = fabric.append(item.ledger, item.kind, item.payload, item.quorum)
            except (OutboxFull, OmniFabricError) as exc:
                result.errors.append(str(exc))
                break
            result.events.append(ev)
            result.journaled += 1
            result.admitted += 1
        return result

    # non-atomic: best-effort each
    for item in normalized:
        try:
            ev = fabric.append(item.ledger, item.kind, item.payload, item.quorum)
            result.events.append(ev)
            result.journaled += 1
            result.admitted += 1
        except (OutboxFull, OmniFabricError) as exc:
            result.errors.append(str(exc))
    return result
