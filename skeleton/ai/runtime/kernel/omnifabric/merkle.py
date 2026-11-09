"""Merkle checkpoints and segment digests for OmniFabric history.

Periodic checkpoints summarize ranges of the fabric so auditors can
verify inclusion without replaying every event. Roots are SHA-256 binary
merkle over event hashes (ordered by seq).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from skeleton.kernel.omnifabric.codecs import sha256_hex
from skeleton.kernel.omnifabric.errors import SegmentCorrupt
from skeleton.kernel.omnifabric.events import FabricEvent
from skeleton.kernel.omnifabric.verify import merkle_root_of, verify_events


@dataclass
class MerkleCheckpoint:
    checkpoint_id: str
    start_seq: int
    end_seq: int
    root: str
    leaf_count: int
    created_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "start_seq": self.start_seq,
            "end_seq": self.end_seq,
            "root": self.root,
            "leaf_count": self.leaf_count,
            "created_at": self.created_at,
            "meta": dict(self.meta),
        }


def build_checkpoint(events: Sequence[FabricEvent], **meta: Any) -> MerkleCheckpoint:
    if not events:
        raise ValueError("empty checkpoint")
    ordered = sorted(events, key=lambda e: e.seq)
    report = verify_events(ordered)
    if not report.ok:
        raise SegmentCorrupt(report.issues[0].detail)
    root = merkle_root_of(ordered)
    cid = sha256_hex(f"{ordered[0].seq}:{ordered[-1].seq}:{root}")[:24]
    return MerkleCheckpoint(
        checkpoint_id=cid,
        start_seq=ordered[0].seq,
        end_seq=ordered[-1].seq,
        root=root,
        leaf_count=len(ordered),
        meta=dict(meta),
    )


def inclusion_proof(events: Sequence[FabricEvent], seq: int) -> dict[str, Any]:
    """Build a simple merkle inclusion proof for ``seq``.

    Returns sibling hashes along the path to the root. Adequate for
    hex-level audits; not a production sparse-merkle circuit.
    """
    ordered = sorted(events, key=lambda e: e.seq)
    idx = next((i for i, e in enumerate(ordered) if e.seq == seq), None)
    if idx is None:
        raise KeyError(f"seq {seq} not in events")
    layers: list[list[str]] = [[e.hash for e in ordered]]
    while len(layers[-1]) > 1:
        cur = layers[-1]
        nxt: list[str] = []
        for i in range(0, len(cur), 2):
            if i + 1 < len(cur):
                nxt.append(sha256_hex(cur[i] + cur[i + 1]))
            else:
                nxt.append(sha256_hex(cur[i] + cur[i]))
        layers.append(nxt)
    path: list[dict[str, Any]] = []
    i = idx
    for layer in layers[:-1]:
        if i % 2 == 0:
            sib_i = i + 1 if i + 1 < len(layer) else i
            side = "right"
        else:
            sib_i = i - 1
            side = "left"
        path.append({"side": side, "hash": layer[sib_i]})
        i //= 2
    return {
        "seq": seq,
        "leaf": ordered[idx].hash,
        "root": layers[-1][0],
        "path": path,
    }


def verify_inclusion(leaf: str, path: list[dict[str, Any]], root: str) -> bool:
    cur = leaf
    for step in path:
        sib = step["hash"]
        if step["side"] == "right":
            cur = sha256_hex(cur + sib)
        else:
            cur = sha256_hex(sib + cur)
    return cur == root


class CheckpointBook:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: list[MerkleCheckpoint] = []

    def add(self, cp: MerkleCheckpoint) -> None:
        with self._lock:
            self._items.append(cp)

    def list(self) -> list[MerkleCheckpoint]:
        with self._lock:
            return list(self._items)

    def latest(self) -> MerkleCheckpoint | None:
        with self._lock:
            return self._items[-1] if self._items else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._items),
                "latest": self._items[-1].to_dict() if self._items else None,
            }
