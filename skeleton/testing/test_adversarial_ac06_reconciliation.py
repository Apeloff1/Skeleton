from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Projection:
    delivered: set[str] = field(default_factory=set)
    orphans: set[str] = field(default_factory=set)

    def deliver(self, message_id: str) -> None:
        self.delivered.add(message_id)

    def reconcile(self, source: set[str]) -> None:
        self.orphans = self.delivered - source

    def rebuild(self, source: set[str]) -> None:
        self.delivered &= source


def test_duplicate_delivery_is_idempotent():
    projection = Projection()
    projection.deliver("m-1")
    projection.deliver("m-1")
    assert projection.delivered == {"m-1"}


def test_orphan_sweep_removes_missing_source_objects():
    projection = Projection()
    projection.deliver("m-1")
    projection.deliver("m-2")
    projection.reconcile({"m-1"})
    assert projection.orphans == {"m-2"}
    projection.rebuild({"m-1"})
    assert projection.delivered == {"m-1"}


def test_projection_rebuild_converges_to_authoritative_source():
    projection = Projection()
    projection.delivered.update({"m-1", "stale"})
    projection.rebuild({"m-1", "m-3"})
    assert projection.delivered == {"m-1"}
