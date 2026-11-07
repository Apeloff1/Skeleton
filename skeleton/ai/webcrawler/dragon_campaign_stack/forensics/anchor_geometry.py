"""Source passage geometry, overlap and scope concentration for review.

Overlapping windows are counted as one continuous source region; repeated
windows cannot inflate claims of independent corroboration. No textual
contents or attacker-controlled snippets are returned.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from .frames import FrameSet


@dataclass(frozen=True)
class SourceGeometry:
    source_id: str
    host: str
    anchored_passages: int
    unique_covered_characters: int
    summed_passage_characters: int
    overlap_excess_characters: int
    disjoint_regions: int
    objective_ids: tuple[str, ...]
    duplicate_region_review: bool


@dataclass(frozen=True)
class AnchorGeometry:
    frame_set_digest: str
    by_source: tuple[SourceGeometry, ...]
    total_unique_covered_characters: int
    total_overlap_excess_characters: int
    high_overlap_source_ids: tuple[str, ...]
    source_count: int
    host_count: int
    report_digest: str
    claimed_independence: bool = False
    source_text_exported: bool = False


def measure_anchor_geometry(frames: FrameSet) -> AnchorGeometry:
    if not isinstance(frames, FrameSet):
        raise TypeError("source-bound frames required")
    groups = defaultdict(list)
    for frame in frames.frames:
        groups[frame.anchor.source_id].append(frame.anchor)
    rows = []
    overlap_ids = []
    for source_id, anchors in sorted(groups.items()):
        spans = sorted((a.start, a.end) for a in anchors)
        merged: list[list[int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        actual = sum(end - start for start, end in merged)
        summed = sum(a.end - a.start for a in anchors)
        excess = summed - actual
        row = SourceGeometry(
            source_id, anchors[0].host, len(anchors), actual,
            summed, excess, len(merged),
            tuple(sorted({goal for a in anchors for goal in a.objective_ids})),
            bool(excess),
        )
        if excess:
            overlap_ids.append(source_id)
        rows.append(row)
    payload = {
        "frame_set": frames.frame_set_digest,
        "sources": [asdict(x) for x in rows],
    }
    return AnchorGeometry(
        frames.frame_set_digest, tuple(rows),
        sum(x.unique_covered_characters for x in rows),
        sum(x.overlap_excess_characters for x in rows),
        tuple(overlap_ids), len(rows), len({x.host for x in rows}),
        digest(payload),
    )
