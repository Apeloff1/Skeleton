"""Chunk-level world-edit receipts.

A receipt is emitted only for a chunk the edit touches. Shader, light,
shadow, terrain, weather, and vertex-diff references are content-addressed
with the canonical frame digest and chained to the predecessor receipt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from skeleton.frontier_evidence.common import EvidenceRejected, content_digest, seal, seal_ok

SCHEMA = "skeleton.frontier_evidence.world_edit_bundle.v1"
CHUNK_SCHEMA = "skeleton.frontier_evidence.chunk_edit_receipt.v1"
SOURCE_KINDS = ("shader", "light", "shadow", "terrain", "weather")


@dataclass(frozen=True)
class SourceRef:
    kind: str
    source_id: str
    content: object

    def reference(self) -> dict:
        if self.kind not in SOURCE_KINDS:
            raise EvidenceRejected(f"unknown source kind {self.kind!r}")
        if not isinstance(self.source_id, str) or not self.source_id or len(self.source_id) > 128:
            raise EvidenceRejected("source id required")
        return {"id": self.source_id, "content_digest": content_digest(self.content)}


@dataclass(frozen=True)
class ChunkTouch:
    chunk_xy: tuple[int, int]
    sources: tuple[SourceRef, ...] = ()
    vertices_before: tuple[tuple[float, float, float], ...] = ()
    vertices_after: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True)
class WorldEdit:
    edit_id: str
    chunks: tuple[ChunkTouch, ...]


def _chunk_id(value: tuple[int, int]) -> list[int]:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or type(value[0]) is not int
        or type(value[1]) is not int
    ):
        raise EvidenceRejected("chunk id must be an integer pair")
    return [value[0], value[1]]


def _vertices(points: Sequence[tuple[float, float, float]], label: str) -> list[list[float]]:
    out: list[list[float]] = []
    for point in points:
        if not isinstance(point, tuple) or len(point) != 3:
            raise EvidenceRejected(f"{label} vertices must be 3D")
        coords: list[float] = []
        for coord in point:
            if isinstance(coord, bool) or not isinstance(coord, (int, float)) or not math.isfinite(coord):
                raise EvidenceRejected(f"{label} vertex is not finite")
            coords.append(float(coord))
        out.append(coords)
    return out


def _vertex_diff(
    before: Sequence[tuple[float, float, float]],
    after: Sequence[tuple[float, float, float]],
) -> dict:
    earlier = _vertices(before, "before")
    later = _vertices(after, "after")
    moved = [index for index in range(min(len(earlier), len(later))) if earlier[index] != later[index]]
    max_disp = max((math.dist(earlier[index], later[index]) for index in moved), default=0.0)
    return {
        "before_digest": content_digest(earlier),
        "after_digest": content_digest(later),
        "moved": moved,
        "added": max(0, len(later) - len(earlier)),
        "removed": max(0, len(earlier) - len(later)),
        "max_displacement": round(max_disp, 9),
    }


def _source_groups(touch: ChunkTouch) -> dict[str, list[dict]]:
    groups = {kind: [] for kind in SOURCE_KINDS}
    seen: set[tuple[str, str]] = set()
    for ref in touch.sources:
        if not isinstance(ref, SourceRef):
            raise EvidenceRejected("typed source reference required")
        key = (ref.kind, ref.source_id)
        if key in seen:
            raise EvidenceRejected(f"duplicate {ref.kind} source {ref.source_id}")
        seen.add(key)
        groups[ref.kind].append(ref.reference())
    for kind in groups:
        groups[kind].sort(key=lambda item: item["id"])
    return groups


def seal_world_edit(edit: WorldEdit, *, previous: Mapping | None = None) -> dict:
    """Seal receipts for the chunks ``edit`` touches and chain the predecessor."""
    if not isinstance(edit, WorldEdit):
        raise EvidenceRejected("typed world edit required")
    if not isinstance(edit.edit_id, str) or not edit.edit_id or len(edit.edit_id) > 128:
        raise EvidenceRejected("edit_id required")
    if not edit.chunks:
        raise EvidenceRejected("edit must touch at least one chunk")
    if previous is not None:
        if (
            not seal_ok(previous)
            or previous.get("schema") != SCHEMA
            or not isinstance(previous.get("edit_id"), str)
            or not isinstance(previous.get("receipt_digest"), str)
        ):
            raise EvidenceRejected("forged predecessor")
        previous_digest = previous["receipt_digest"]
        previous_edit_id = previous["edit_id"]
    else:
        previous_digest = None
        previous_edit_id = None
    seen_chunks: set[tuple[int, int]] = set()
    receipts = []
    for touch in sorted(edit.chunks, key=lambda item: item.chunk_xy):
        if touch.chunk_xy in seen_chunks:
            raise EvidenceRejected(f"duplicate chunk {touch.chunk_xy}")
        seen_chunks.add(touch.chunk_xy)
        sources = _source_groups(touch)
        diff = _vertex_diff(touch.vertices_before, touch.vertices_after)
        if not any(sources.values()) and not (diff["moved"] or diff["added"] or diff["removed"]):
            raise EvidenceRejected(f"chunk {touch.chunk_xy} has no source reference or vertex change")
        receipts.append(
            seal(
                {
                    "schema": CHUNK_SCHEMA,
                    "edit_id": edit.edit_id,
                    "chunk_id": _chunk_id(touch.chunk_xy),
                    "shader": sources["shader"],
                    "light": sources["light"],
                    "shadow": sources["shadow"],
                    "terrain": sources["terrain"],
                    "weather": sources["weather"],
                    "vertex_diff": diff,
                    "previous_digest": previous_digest,
                }
            )
        )
    return seal(
        {
            "schema": SCHEMA,
            "edit_id": edit.edit_id,
            "chunk_ids": [receipt["chunk_id"] for receipt in receipts],
            "previous_digest": previous_digest,
            "previous_edit_id": previous_edit_id,
            "receipts": receipts,
        }
    )


def verify_world_edit(receipt: Mapping, edit: WorldEdit, *, predecessor: Mapping | None = None) -> bool:
    """Recompute the receipt. A forged predecessor does not verify."""
    try:
        return seal_ok(receipt) and seal_world_edit(edit, previous=predecessor) == dict(receipt)
    except (EvidenceRejected, TypeError, ValueError, AttributeError):
        return False


def verify_edit_chain(receipts: Sequence[Mapping], edits: Sequence[WorldEdit]) -> bool:
    if len(receipts) != len(edits):
        return False
    predecessor: Mapping | None = None
    for receipt, edit in zip(receipts, edits):
        if not verify_world_edit(receipt, edit, predecessor=predecessor):
            return False
        predecessor = receipt
    return True
