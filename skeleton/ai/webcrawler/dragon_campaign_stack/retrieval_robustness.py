"""Selected-evidence robustness and single-origin exposure for Dragon Atlas.

An observed selection is not an independent source and retrieval rank is not
factual confidence. This projection inspects *only* the policy-admitted,
exact-span, source-bound retrieved passages. It does not re-search an altered
corpus, infer unseen relevant pages, certify historical independence, or start
network, provider, worker or storage operations.

The leave-one-host-out result models how much of the *already selected*
evidence survives excluding one origin. It does not assert what a fresh
ranking would choose in a re-run; the candidate pool can differ significantly.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import Iterable

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .objectives import ObjectivePlan
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class ObjectiveExposure:
    objective_id: str
    selected_passages: int
    distinct_selected_sources: int
    distinct_selected_hosts: int
    distinct_content_families: int
    cross_host_exact_content_reuse: bool
    dominant_host: str | None
    dominant_host_selected_passages: int
    dominant_host_fraction: float
    smallest_remaining_passages_after_host_removal: int
    smallest_remaining_sources_after_host_removal: int
    host_ablation_risk: str
    unreviewed_evidence_only: bool = True
    independent_corroboration_confirmed: bool = False


@dataclass(frozen=True)
class HostRemovalScenario:
    removed_host: str
    removed_selected_passages: int
    removed_unique_sources: int
    surviving_selected_passages: int
    surviving_unique_sources: int
    surviving_distinct_content_families: int
    objectives_without_any_selected_passages: tuple[str, ...]
    objectives_left_with_one_host: tuple[str, ...]
    hypothetical_selection_only: bool = True
    reranking_executed: bool = False


@dataclass(frozen=True)
class ObjectiveSourceReuse:
    left_objective_id: str
    right_objective_id: str
    overlapping_source_ids: tuple[str, ...]
    overlapping_hosts: tuple[str, ...]
    overlapping_content_hashes: tuple[str, ...]
    union_source_count: int
    source_jaccard: float
    evidentiary_independence_proven: bool = False


@dataclass(frozen=True)
class SelectedExactContentFamily:
    """Several selected canonical sources share exactly the same text hash.

    This is a zero-effect equality observation, not a finding that one site
    plagiarized, maliciously mirrored, independently verified, or republished
    the other. Content hashes expose no stored text.
    """
    content_sha256: str
    selected_source_ids: tuple[str, ...]
    observed_hosts: tuple[str, ...]
    selected_passages: int
    is_cross_host: bool
    independent_origin_verified: bool = False


@dataclass(frozen=True)
class RetrievalRobustnessAudit:
    mandate_digest: str
    source_snapshot_digest: str
    policy_digest: str
    retrieval_digest: str
    objective_plan_digest: str
    selected_passages: int
    selected_sources: int
    selected_hosts: int
    distinct_content_families: int
    cross_host_exact_clone_groups: int
    exact_content_reuse: tuple[SelectedExactContentFamily, ...]
    analyses: tuple[ObjectiveExposure, ...]
    leave_one_host_out: tuple[HostRemovalScenario, ...]
    objective_reuse: tuple[ObjectiveSourceReuse, ...]
    flagged_objectives: tuple[str, ...]
    limitations: tuple[str, ...]
    audit_digest: str
    source_bodies_excluded: bool = True
    counterfactual_ranking_executed: bool = False
    verified_independence: bool = False
    training_authorized: bool = False
    publication_authorized: bool = False


_LIMITATIONS = (
    "observed_selected_passages_only",
    "unselected_candidates_and_missing_sources_not_recovered",
    "host_removal_does_not_rerank_or_fetch",
    "different_hosts_do_not_prove_independent_ownership",
    "equal_text_hashes_are_copy_indicators_not_plagiarism_proof",
    "lexical_rank_not_a_fact_or_confidence_probability",
    "human_source_and_claim_review_required",
)


def analyze_retrieval_robustness(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    objectives: ObjectivePlan,
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_selected: int = 32,
    max_objectives: int = 8,
    max_hosts: int = 32,
) -> RetrievalRobustnessAudit:
    """Prove all selected spans then model deterministic zero-effect ablations."""
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_selected, "selected retrieval audit capacity", 1, 32)
    integer(max_objectives, "objective audit capacity", 1, 32)
    integer(max_hosts, "host ablation audit capacity", 1, 64)
    if not isinstance(objectives, ObjectivePlan):
        raise TypeError("typed immutable objective plan required")
    if not isinstance(policy, SourcePolicyProjection):
        raise TypeError("typed current source policy required")
    if not isinstance(retrieval, RetrievalFusion):
        raise TypeError("typed source-only retrieval receipt required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    snapshot_digest = canonical["snapshot_digest"]
    if any(item != mandate.fingerprint for item in (
        objectives.mandate_digest, policy.mandate_digest,
        retrieval.mandate_digest,
    )):
        raise PermissionError("cross-mandate selected-evidence audit")
    if policy.source_snapshot_digest != snapshot_digest or (
        retrieval.source_snapshot_digest != snapshot_digest
    ):
        raise PermissionError("stale source or source-policy revision")
    if not objectives.objectives or len(objectives.objectives) > max_objectives:
        raise ValueError("bounded operator objectives required")
    if len(retrieval.results) > max_selected:
        raise ValueError("selected evidence exceeds robustness audit capacity")
    if retrieval.publication_authorized or policy.publication_authorized or (
        policy.training_authorized
    ):
        raise PermissionError("unreviewed evidence cannot gain authority")
    known_ids = set(canonical["sources"])
    allowed = set(policy.allowed_source_ids)
    excluded = set(policy.excluded_source_ids)
    if allowed & excluded or allowed | excluded != known_ids or (
        tuple(sorted(excluded)) != retrieval.excluded_sources
    ):
        raise PermissionError("incomplete or changed source-policy eligibility")
    goals = tuple(item.objective_id for item in objectives.objectives)
    if len(set(goals)) != len(goals):
        raise ValueError("duplicated research objective identities")
    identified = set(goals)
    by_goal: dict[str, list] = {x: [] for x in goals}
    seen_passages = set()
    host_to_source: dict[str, set[str]] = defaultdict(set)
    all_sources: set[str] = set()
    selected_by_hash: dict[str, list] = defaultdict(list)
    for row in retrieval.results:
        if row.source_id not in allowed:
            raise PermissionError("withheld or missing source in retrieval")
        source = canonical["sources"][row.source_id]
        if (source["content_hash"] != row.source_hash or
                source["canonical_url"] != row.canonical_url or
                type(row.start) is not int or type(row.end) is not int or
                row.start < 0 or row.end <= row.start or
                row.end > len(source["text"])):
            raise PermissionError("retrieval source identity or span mismatch")
        selected_text = source["text"][row.start:row.end]
        if (selected_text != row.text or
                sha256(selected_text.encode("utf-8")).hexdigest() != row.passage_hash):
            raise PermissionError("retrieval span hash mismatch")
        if row.host not in mandate.scope.allowed_hosts:
            raise PermissionError("retrieval escaped source host grant")
        from urllib.parse import urlsplit
        if urlsplit(row.canonical_url).hostname != row.host:
            raise PermissionError("retrieved host does not match canonical URL")
        if not isfinite(row.score) or row.score < 0:
            raise ValueError("nonfinite selected ranking score")
        identity = (row.source_id, row.passage_hash, row.start, row.end)
        if identity in seen_passages:
            raise ValueError("same retained passage selected more than once")
        seen_passages.add(identity)
        if not row.matched_objective_ids or (
            set(row.matched_objective_ids) - identified
        ):
            raise PermissionError("retrieval references a foreign objective")
        if len(set(row.matched_objective_ids)) != len(row.matched_objective_ids):
            raise ValueError("repeated objective identity within one passage")
        all_sources.add(row.source_id)
        host_to_source[row.host].add(row.source_id)
        selected_by_hash[row.source_hash].append(row)
        for goal in row.matched_objective_ids:
            by_goal[goal].append(row)
    if len(host_to_source) > max_hosts:
        raise ValueError("selected host universe exceeds audit capacity")
    clones = []
    for text_hash, passages in sorted(selected_by_hash.items()):
        identities = tuple(sorted({p.source_id for p in passages}))
        if len(identities) < 2:
            continue
        hosts = tuple(sorted({p.host for p in passages}))
        clones.append(SelectedExactContentFamily(
            content_sha256=text_hash,
            selected_source_ids=identities,
            observed_hosts=hosts,
            selected_passages=len(passages),
            is_cross_host=len(hosts) > 1,
        ))
    analyses = []
    flagged = []
    for goal in goals:
        passages = by_goal[goal]
        selected_sources = {x.source_id for x in passages}
        content_families = {x.source_hash for x in passages}
        cross_host_copy = bool(passages and len(content_families) == 1
                               and len({x.host for x in passages}) > 1)
        host_counts: dict[str, int] = defaultdict(int)
        for item in passages:
            host_counts[item.host] += 1
        hosts = tuple(sorted(host_counts))
        if hosts:
            # Equal-count host ties are resolved lexically for receipt stability.
            dominant = min(hosts, key=lambda x: (-host_counts[x], x))
            dominated = host_counts[dominant]
            remaining_passages = min(
                len(passages) - host_counts[x] for x in hosts
            )
            remaining_sources = min(
                len({x.source_id for x in passages if x.host != host})
                for host in hosts
            )
            concentration = round(dominated / len(passages), 8)
            grade = ("single_host" if len(hosts) == 1 else
                     "same_content_on_multiple_hosts" if cross_host_copy else
                     "host_concentrated" if concentration >= .75 else
                     "multiple_observed_hosts")
        else:
            dominant = None
            dominated = 0
            remaining_passages = 0
            remaining_sources = 0
            concentration = 0.0
            grade = "no_selected_evidence"
        if grade != "multiple_observed_hosts":
            flagged.append(goal)
        analyses.append(ObjectiveExposure(
            objective_id=goal,
            selected_passages=len(passages),
            distinct_selected_sources=len(selected_sources),
            distinct_selected_hosts=len(hosts),
            distinct_content_families=len(content_families),
            cross_host_exact_content_reuse=cross_host_copy,
            dominant_host=dominant,
            dominant_host_selected_passages=dominated,
            dominant_host_fraction=concentration,
            smallest_remaining_passages_after_host_removal=remaining_passages,
            smallest_remaining_sources_after_host_removal=remaining_sources,
            host_ablation_risk=grade,
        ))
    scenarios = []
    for host in sorted(host_to_source):
        remaining = tuple(x for x in retrieval.results if x.host != host)
        lost = tuple(x for x in retrieval.results if x.host == host)
        missing = []
        one_host_left = []
        for goal in goals:
            surviving_hosts = {
                item.host for item in remaining
                if goal in item.matched_objective_ids
            }
            if not surviving_hosts:
                missing.append(goal)
            elif len(surviving_hosts) == 1:
                one_host_left.append(goal)
        scenarios.append(HostRemovalScenario(
            removed_host=host,
            removed_selected_passages=len(lost),
            removed_unique_sources=len({x.source_id for x in lost}),
            surviving_selected_passages=len(remaining),
            surviving_unique_sources=len({x.source_id for x in remaining}),
            surviving_distinct_content_families=len({
                x.source_hash for x in remaining
            }),
            objectives_without_any_selected_passages=tuple(sorted(missing)),
            objectives_left_with_one_host=tuple(sorted(one_host_left)),
        ))
    overlaps = []
    for a, b in combinations(sorted(goals), 2):
        left = by_goal[a]
        right = by_goal[b]
        sources_left = {x.source_id for x in left}
        sources_right = {x.source_id for x in right}
        hosts_left = {x.host for x in left}
        hosts_right = {x.host for x in right}
        shared_sources = tuple(sorted(sources_left & sources_right))
        shared_hosts = tuple(sorted(hosts_left & hosts_right))
        shared_content_hashes = tuple(sorted(
            {x.source_hash for x in left} &
            {x.source_hash for x in right}
        ))
        union = sources_left | sources_right
        overlaps.append(ObjectiveSourceReuse(
            left_objective_id=a,
            right_objective_id=b,
            overlapping_source_ids=shared_sources,
            overlapping_hosts=shared_hosts,
            overlapping_content_hashes=shared_content_hashes,
            union_source_count=len(union),
            source_jaccard=round(len(shared_sources) / len(union), 8)
                           if union else 0.0,
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": snapshot_digest,
        "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest,
        "objective_plan": objectives.plan_digest,
        "objectives": [asdict(x) for x in analyses],
        "content_reuse": [asdict(x) for x in clones],
        "host_removals": [asdict(x) for x in scenarios],
        "reuse": [asdict(x) for x in overlaps],
        "flagged": tuple(sorted(flagged)),
        "limitations": _LIMITATIONS,
    }
    return RetrievalRobustnessAudit(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=snapshot_digest,
        policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        objective_plan_digest=objectives.plan_digest,
        selected_passages=len(retrieval.results),
        selected_sources=len(all_sources),
        selected_hosts=len(host_to_source),
        distinct_content_families=len(selected_by_hash),
        cross_host_exact_clone_groups=sum(x.is_cross_host for x in clones),
        exact_content_reuse=tuple(clones),
        analyses=tuple(analyses),
        leave_one_host_out=tuple(scenarios),
        objective_reuse=tuple(overlaps),
        flagged_objectives=tuple(sorted(flagged)),
        limitations=_LIMITATIONS,
        audit_digest=digest(payload),
    )
