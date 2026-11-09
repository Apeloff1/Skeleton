"""Reconcile selected exact spans against operator query and rank support.

A retrieval hit is merely selected lexical evidence, not proof that the
question is answered. Each selected anchor must have a valid registered
operator query, rank, objective, and provenance in the current Atlas lattice.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest, integer
from ..query_lattice import QueryLattice
from ..retrieval_fusion import RetrievalFusion
from .frames import FrameSet


@dataclass(frozen=True)
class QuerySupportFinding:
    objective_id: str
    query_variants_in_lattice: int
    selected_query_variants: int
    selected_source_count: int
    selected_passages: int
    selected_query_families: tuple[str, ...]
    query_family_count: int
    rank_one_selected_passages: int
    only_one_query_variant: bool
    no_selected_evidence: bool
    relevance_certified: bool = False


@dataclass(frozen=True)
class QuerySupportAudit:
    frame_set_digest: str
    lattice_digest: str
    retrieval_digest: str
    findings: tuple[QuerySupportFinding, ...]
    selected_anchors_checked: int
    query_variants_unused: int
    single_query_objectives: tuple[str, ...]
    missing_evidence_objectives: tuple[str, ...]
    audit_digest: str
    live_search_reexecuted: bool = False
    source_relevance_human_verified: bool = False


def audit_query_support(
    frames: FrameSet, lattice: QueryLattice, retrieval: RetrievalFusion,
    *, max_query_variants: int = 128, max_selected: int = 64,
) -> QuerySupportAudit:
    if not all(isinstance(x, cls) for x, cls in (
        (frames, FrameSet), (lattice, QueryLattice), (retrieval, RetrievalFusion),
    )):
        raise TypeError("typed current source-bound query receipts required")
    integer(max_query_variants, "query support universe", 1, 128)
    integer(max_selected, "query support selection", 1, 64)
    if (lattice.mandate_digest != frames.mandate_digest
            or retrieval.mandate_digest != frames.mandate_digest
            or retrieval.source_snapshot_digest != frames.snapshot_digest
            or retrieval.fusion_digest != frames.retrieval_digest
            or retrieval.lattice_digest != lattice.lattice_digest
            or lattice.may_crawl or lattice.may_promote_knowledge):
        raise PermissionError("query support references foreign or executable campaign")
    if len(lattice.queries) > max_query_variants or len(retrieval.results) > max_selected:
        raise ValueError("query universe capacity exceeded")
    if len(frames.frames) != len(retrieval.results):
        raise PermissionError("different selected passage counts")
    query_goals: dict[str, list[int]] = defaultdict(list)
    for i, query in enumerate(lattice.queries):
        query_goals[query.objective_id].append(i)
    query_selected: dict[str, set[int]] = defaultdict(set)
    source_selected: dict[str, set[str]] = defaultdict(set)
    family_selected: dict[str, set[str]] = defaultdict(set)
    passage_count: dict[str, int] = defaultdict(int)
    rank_one_count: dict[str, int] = defaultdict(int)
    all_used: set[int] = set()
    for frame, selected in zip(frames.frames, retrieval.results):
        a = frame.anchor
        if ((a.source_id, a.passage_hash, a.start, a.end)
                != (selected.source_id, selected.passage_hash,
                    selected.start, selected.end)):
            raise PermissionError("query selected passage order or identity changed")
        if not selected.query_rank_support:
            raise PermissionError("source selection has no query rank provenance")
        query_ids = set()
        for query_id, rank in selected.query_rank_support:
            if (type(query_id) is not int or not 0 <= query_id < len(lattice.queries)
                    or type(rank) is not int or not 1 <= rank <= 4096):
                raise PermissionError("invalid query index or source rank")
            if query_id in query_ids:
                raise ValueError("duplicate query selection support")
            query_ids.add(query_id)
        if set(selected.matched_queries) != {
            lattice.queries[i].query for i in query_ids
        }:
            raise PermissionError("query support labels disagree with operator lattice")
        goals = {lattice.queries[i].objective_id for i in query_ids}
        if goals != set(a.objective_ids):
            raise PermissionError("selected source objective differs from query support")
        all_used |= query_ids
        for goal in goals:
            passage_count[goal] += 1
            source_selected[goal].add(a.source_id)
            for i, rank in selected.query_rank_support:
                query = lattice.queries[i]
                if query.objective_id == goal:
                    query_selected[goal].add(i)
                    family_selected[goal].add(query.family)
                    if rank == 1:
                        rank_one_count[goal] += 1
    findings, single, missing = [], [], []
    for goal in sorted(query_goals):
        count = len(query_selected[goal])
        absent = passage_count[goal] == 0
        if count == 1 and not absent:
            single.append(goal)
        if absent:
            missing.append(goal)
        findings.append(QuerySupportFinding(
            goal, len(query_goals[goal]), count,
            len(source_selected[goal]), passage_count[goal],
            tuple(sorted(family_selected[goal])),
            len(family_selected[goal]), rank_one_count[goal],
            count == 1 and not absent, absent,
        ))
    payload = {"frames": frames.frame_set_digest,
               "lattice": lattice.lattice_digest,
               "retrieval": retrieval.fusion_digest,
               "findings": [asdict(x) for x in findings],
               "used_query_ids": sorted(all_used)}
    return QuerySupportAudit(
        frames.frame_set_digest, lattice.lattice_digest,
        retrieval.fusion_digest, tuple(findings), len(frames.frames),
        len(lattice.queries) - len(all_used),
        tuple(single), tuple(missing), digest(payload),
    )
