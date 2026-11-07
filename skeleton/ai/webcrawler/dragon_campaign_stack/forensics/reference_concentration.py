"""Selected-passage reuse accounting across goals and source identities.

A citation counted for several goals still denotes the *same* external
evidence. This stage detects evidence concentration and prevents duplicate
passages from masquerading as independent corroboration or diverse sources.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from .frames import FrameSet


@dataclass(frozen=True)
class CitationConcentration:
    source_id: str
    unique_passage_anchors: int
    distinct_objective_count: int
    objective_ids: tuple[str, ...]
    repeated_cross_objective_anchors: int
    all_selected_passages_under_one_source: bool
    independent_claims_verified: bool = False


@dataclass(frozen=True)
class CitationConcentrationReport:
    frame_set_digest: str
    source_profiles: tuple[CitationConcentration, ...]
    total_anchor_records: int
    unique_passage_text_hashes: int
    cross_objective_reused_source_count: int
    single_source_concentration: bool
    repeated_text_hashes_across_sources: int
    held_source_ids: tuple[str, ...]
    report_digest: str
    source_independence_confirmed: bool = False
    citation_truth_verified: bool = False


def inspect_reference_concentration(frames: FrameSet) -> CitationConcentrationReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("exact source-bound passages required")
    source_to_anchors = defaultdict(list)
    content_by_hash = defaultdict(set)
    for frame in frames.frames:
        a = frame.anchor
        source_to_anchors[a.source_id].append(a)
        content_by_hash[a.passage_hash].add(a.source_id)
    results = []
    held = set()
    for source_id, anchors in sorted(source_to_anchors.items()):
        goals = {x for a in anchors for x in a.objective_ids}
        # One anchor selected for several goals is not multiple evidence items.
        shared = sum(len(a.objective_ids) > 1 for a in anchors)
        if len(goals) > 1 or shared:
            held.add(source_id)
        results.append(CitationConcentration(
            source_id, len(anchors), len(goals), tuple(sorted(goals)),
            shared, len(source_to_anchors) == 1,
        ))
    duplicated_hashes = sum(len(sources) > 1 for sources in content_by_hash.values())
    payload = {
        "frames": frames.frame_set_digest,
        "sources": [asdict(x) for x in results],
        "passage_hash_count": len(content_by_hash),
        "reused_across_sources": duplicated_hashes,
    }
    return CitationConcentrationReport(
        frames.frame_set_digest, tuple(results), len(frames.frames),
        len(content_by_hash), sum(row.distinct_objective_count > 1 for row in results),
        len(source_to_anchors) == 1 and bool(source_to_anchors),
        duplicated_hashes, tuple(sorted(held)), digest(payload),
    )
