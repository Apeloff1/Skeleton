"""OmniFabricService — cohesive hex facade over the Ω-fabric surface.

Wires OmniFabric + outbox + ledger catalog + projections + subscribers +
windows + checkpoints into one extend-only entrypoint. Does **not** touch
``skeleton.api.server`` lifespan; HTTP routes import this service directly.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Mapping, Sequence

from skeleton.kernel.omnifabric.core import DEFAULT_HOT_CAP, OmniFabric
from skeleton.kernel.omnifabric.errors import ChainBroken, OmniFabricError, OutboxFull
from skeleton.kernel.omnifabric.events import FabricEvent
from skeleton.kernel.omnifabric.ledgers import LedgerCatalog
from skeleton.kernel.omnifabric.merkle import CheckpointBook, build_checkpoint, inclusion_proof
from skeleton.kernel.omnifabric.metrics import FabricMetrics
from skeleton.kernel.omnifabric.outbox import FabricOutbox
from skeleton.kernel.omnifabric.projections import (
    KindCounterProjection,
    LastValueProjection,
    ProjectionHub,
    QuorumAttestationProjection,
)
from skeleton.kernel.omnifabric.queries import query_fabric
from skeleton.kernel.omnifabric.replay import FabricReplayer, boot_reconcile
from skeleton.kernel.omnifabric.subscribers import RecordingObserver, SubscriberBus
from skeleton.kernel.omnifabric.verify import evidence_bundle, verify_events
from skeleton.kernel.omnifabric.windows import WindowStore, seal_window


class OmniFabricService:
    """High-level forge-path fabric surface for skeleton hex callers."""

    def __init__(
        self,
        *,
        hot_cap: int = DEFAULT_HOT_CAP,
        outbox_cap: int = 4096,
        auto_confirm: bool = True,
        install_default_projections: bool = True,
    ) -> None:
        self.outbox = FabricOutbox(cap=outbox_cap)
        self.fabric = OmniFabric(
            self.outbox, hot_cap=hot_cap, auto_confirm=auto_confirm
        )
        self.catalog = LedgerCatalog()
        self.projections = ProjectionHub()
        self.subscribers = SubscriberBus()
        self.windows = WindowStore()
        self.checkpoints = CheckpointBook()
        self.metrics = FabricMetrics()
        self._lock = threading.RLock()
        self._drain_buffer: list[FabricEvent] = []
        if install_default_projections:
            self.projections.add(KindCounterProjection())
            self.projections.add(LastValueProjection("last_value"))
            self.projections.add(QuorumAttestationProjection("quorum_attestation"))

    def register_ledger(self, name: str, description: str = "", **meta: Any) -> dict[str, Any]:
        return self.catalog.register(name, description, **meta).to_dict()

    def append(
        self,
        ledger: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        quorum: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        self.catalog.ensure(ledger)
        try:
            ev = self.fabric.append(ledger, kind, payload, quorum)
        except (OutboxFull, OmniFabricError):
            self.metrics.record_append(ok=False)
            raise
        self.catalog.observe(ev)
        self.projections.observe(ev)
        delivered = self.subscribers.publish(ev)
        self.metrics.record_delivery(delivered)
        approx = len(json.dumps(dict(payload or {}), default=str))
        self.metrics.record_append(ok=True, ledger=ledger, kind=kind, payload_bytes=approx)
        return ev.to_dict()

    def verify(self, *, full_evidence: bool = False) -> dict[str, Any]:
        try:
            self.fabric.verify_chain()
            self.metrics.record_verify(True)
            if full_evidence:
                return evidence_bundle(self.fabric.snapshot_tail())
            return {"ok": True, "stats": self.fabric.stats()}
        except ChainBroken as exc:
            self.metrics.record_verify(False)
            return {"ok": False, "seq": exc.seq, "detail": exc.detail, "stats": self.fabric.stats()}

    def tail(self, ledger: str, limit: int = 128) -> list[dict[str, Any]]:
        self.metrics.record_query()
        return [e.to_dict() for e in self.fabric.tail(ledger, limit)]

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.metrics.record_query()
        result = query_fabric(self.fabric, **kwargs)
        return {
            "events": result.to_dicts(),
            "truncated": result.truncated,
            "scanned": result.scanned,
        }

    def seal_hot_prefix(self, count: int) -> dict[str, Any]:
        """Seal the oldest ``count`` hot-tail events into a window checkpoint."""
        with self._lock:
            snap = self.fabric.snapshot_tail()
            if count < 1 or count > len(snap):
                raise ValueError(f"count must be in 1..{len(snap)}")
            # snapshot_tail is oldest→newest
            prefix = snap[:count]
            window = seal_window(prefix)
            self.windows.add(window)
            cp = build_checkpoint(prefix, source="seal_hot_prefix")
            self.checkpoints.add(cp)
            self.metrics.record_window()
            self.metrics.record_checkpoint()
            return {"window": window.to_dict(), "checkpoint": cp.to_dict()}

    def checkpoint_tail(self) -> dict[str, Any]:
        snap = self.fabric.snapshot_tail()
        if not snap:
            return {"checkpoint": None}
        cp = build_checkpoint(snap, source="checkpoint_tail")
        self.checkpoints.add(cp)
        self.metrics.record_checkpoint()
        return cp.to_dict()

    def inclusion(self, seq: int) -> dict[str, Any]:
        return inclusion_proof(self.fabric.snapshot_tail(), seq)

    def reconcile(self) -> dict[str, Any]:
        self.metrics.record_replay()
        return boot_reconcile(self.fabric)

    def replay_unconfirmed(self, *, strict: bool = True) -> dict[str, Any]:
        self.metrics.record_replay()
        return FabricReplayer(self.outbox).replay_into(self.fabric, strict=strict).to_dict()

    def status(self) -> dict[str, Any]:
        return {
            "fabric": self.fabric.stats(),
            "catalog": self.catalog.stats(),
            "projections": self.projections.status(),
            "subscribers": self.subscribers.status(),
            "windows": self.windows.stats(),
            "checkpoints": self.checkpoints.stats(),
            "metrics": self.metrics.snapshot(),
        }

    def subscribe_recorder(self, name: str = "recorder") -> RecordingObserver:
        rec = RecordingObserver()
        self.subscribers.subscribe(name, rec)
        return rec
