"""Sealed fabric segments — durable history slices off the hot tail.

When OmniFabric drains its hot tail, sealed segments keep merkle-rooted
history for auditors. Segments are immutable once sealed.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from skeleton.kernel.omnifabric.codecs import sha256_hex, stable_json
from skeleton.kernel.omnifabric.errors import SegmentCorrupt
from skeleton.kernel.omnifabric.events import FabricEvent, event_from_mapping, event_to_mapping
from skeleton.kernel.omnifabric.verify import merkle_root_of, verify_events


@dataclass
class FabricSegment:
    segment_id: str
    start_seq: int
    end_seq: int
    start_prev_hash: str
    end_hash: str
    merkle_root: str
    events: list[dict[str, Any]]
    sealed_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start_seq": self.start_seq,
            "end_seq": self.end_seq,
            "start_prev_hash": self.start_prev_hash,
            "end_hash": self.end_hash,
            "merkle_root": self.merkle_root,
            "events": list(self.events),
            "sealed_at": self.sealed_at,
            "meta": dict(self.meta),
        }

    def event_objects(self) -> list[FabricEvent]:
        return [event_from_mapping(e) for e in self.events]

    def verify(self) -> bool:
        evs = self.event_objects()
        report = verify_events(evs)
        if not report.ok:
            raise SegmentCorrupt(report.issues[0].detail)
        if merkle_root_of(evs) != self.merkle_root:
            raise SegmentCorrupt("merkle root mismatch")
        if evs[0].seq != self.start_seq or evs[-1].seq != self.end_seq:
            raise SegmentCorrupt("seq bounds mismatch")
        if evs[-1].hash != self.end_hash:
            raise SegmentCorrupt("end_hash mismatch")
        return True


def seal_segment(events: Sequence[FabricEvent], **meta: Any) -> FabricSegment:
    if not events:
        raise ValueError("empty segment")
    ordered = sorted(events, key=lambda e: e.seq)
    report = verify_events(ordered)
    if not report.ok:
        raise SegmentCorrupt(report.issues[0].detail)
    root = merkle_root_of(ordered)
    sid = sha256_hex(f"seg:{ordered[0].seq}:{ordered[-1].hash}:{root}")[:28]
    return FabricSegment(
        segment_id=sid,
        start_seq=ordered[0].seq,
        end_seq=ordered[-1].seq,
        start_prev_hash=ordered[0].prev_hash,
        end_hash=ordered[-1].hash,
        merkle_root=root,
        events=[event_to_mapping(e) for e in ordered],
        meta=dict(meta),
    )


class SegmentStore:
    """In-memory + optional directory-backed segment archive."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self._dir = Path(directory) if directory else None
        self._lock = threading.RLock()
        self._segments: dict[str, FabricSegment] = {}
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load_dir()

    def _load_dir(self) -> None:
        assert self._dir is not None
        for path in sorted(self._dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            seg = FabricSegment(
                segment_id=data["segment_id"],
                start_seq=data["start_seq"],
                end_seq=data["end_seq"],
                start_prev_hash=data["start_prev_hash"],
                end_hash=data["end_hash"],
                merkle_root=data["merkle_root"],
                events=list(data["events"]),
                sealed_at=float(data.get("sealed_at") or time.time()),
                meta=dict(data.get("meta") or {}),
            )
            seg.verify()
            self._segments[seg.segment_id] = seg

    def add(self, segment: FabricSegment) -> None:
        segment.verify()
        with self._lock:
            self._segments[segment.segment_id] = segment
            if self._dir is not None:
                path = self._dir / f"{segment.segment_id}.json"
                path.write_text(stable_json(segment.to_dict()), encoding="utf-8")

    def get(self, segment_id: str) -> FabricSegment:
        with self._lock:
            return self._segments[segment_id]

    def list(self) -> list[FabricSegment]:
        with self._lock:
            return sorted(self._segments.values(), key=lambda s: s.start_seq)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._segments),
                "events": sum(len(s.events) for s in self._segments.values()),
                "directory": str(self._dir) if self._dir else None,
            }
