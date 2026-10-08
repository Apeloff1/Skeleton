"""Lineage-bound, adversarial assurance for the crawler's repeated-source evidence.

This module intentionally does *not* fetch URLs, approve research, or calibrate
probabilities. It converts declared source custody into conservative dependency
groups before probabilistic distillation and performs leave-one-group-out stress
tests. All outputs are deterministic and remain proposals for human review.

Input provenance must come from a trusted custody/ingestion boundary; this
module does not authenticate the custodian or infer copyright permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
from urllib.parse import urlsplit
import json

from .core import CrawlPolicy
from .dragon_adaptive_rereads import plan_adaptive_rereads
from .dragon_probabilistic_distillation import (
    Belief, EvidencePass, EvidencePolicy, ProbabilisticKnowledgeDistiller,
)
from .dragon_source_independence import (
    SourceProvenance, derive_dependency_clusters,
)


def _fingerprint(data: object) -> str:
    return sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceCluster:
    """A conservative equivalence class, never proof of independence."""

    cluster_id: str
    source_ids: tuple[str, ...]
    content_digests: tuple[str, ...]
    reasons: tuple[str, ...]
    readings: int
    supporting_readings: int
    opposing_readings: int


@dataclass(frozen=True)
class ClusterHoldout:
    cluster_id: str
    remaining_groups: int
    remaining_readings: int
    heldout_probability: float
    probability_delta: float
    flips_majority: bool


@dataclass(frozen=True)
class ResearchNextAction:
    kind: str
    target: str
    priority: float
    rationale: str


@dataclass(frozen=True)
class ProvenanceAssurance:
    claim_id: str
    belief: Belief
    clusters: tuple[SourceCluster, ...]
    holdouts: tuple[ClusterHoldout, ...]
    minimum_heldout_probability: float
    independent_groups: int
    provenance_relabels: int
    source_coverage_complete: bool
    needs_human_review: bool
    candidate_for_review: bool
    blockers: tuple[str, ...]
    next_actions: tuple[ResearchNextAction, ...]
    fingerprint: str
    probability_semantics: str = "heuristic_logistic_score"
    promotion_authorized: bool = False


@dataclass(frozen=True)
class AssurancePolicy:
    """Risk preferences, not empirical calibration of the evidence model."""

    min_independent_groups: int = 2
    min_supporting_probability: float = 0.72
    min_heldout_probability: float = 0.58
    maximum_sources: int = 10000
    maximum_actions: int = 100
    maximum_holdout_groups: int = 500


def _verify_policy(policy: AssurancePolicy) -> None:
    if not isinstance(policy.min_independent_groups, int) or not (
        2 <= policy.min_independent_groups <= 1000
    ):
        raise ValueError("invalid independent group requirement")
    for name in ("min_supporting_probability", "min_heldout_probability"):
        value = getattr(policy, name)
        if not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value < 1:
            raise ValueError(f"invalid {name}")
    if not 1 <= policy.maximum_sources <= 100000:
        raise ValueError("invalid source capacity")
    if not 1 <= policy.maximum_actions <= 1000:
        raise ValueError("invalid action capacity")
    if not 1 <= policy.maximum_holdout_groups <= 1000:
        raise ValueError("invalid holdout group capacity")


def _manifest(
    evidence: tuple[EvidencePass, ...],
    sources: tuple[SourceProvenance, ...],
    max_sources: int,
) -> dict[str, SourceProvenance]:
    if len(sources) > max_sources:
        raise ValueError("provenance source budget exceeded")
    by_id: dict[str, SourceProvenance] = {}
    admit = CrawlPolicy()
    for source in sources:
        if not isinstance(source, SourceProvenance):
            raise ValueError("unrecognized source provenance")
        if not isinstance(source.source_id, str) or not 1 <= len(source.source_id) <= 256:
            raise ValueError("invalid provenance source identity")
        if source.source_id in by_id:
            raise ValueError("duplicate provenance source identity")
        if not isinstance(source.canonical_uri, str) or not admit.admits(source.canonical_uri):
            raise ValueError("untrusted provenance origin")
        origin = urlsplit(source.canonical_uri)
        if origin.username is not None or origin.password is not None:
            raise ValueError("untrusted provenance origin")
        if not isinstance(source.content_digest, str) or (
            len(source.content_digest) != 64
            or any(c not in "0123456789abcdef" for c in source.content_digest)
        ):
            raise ValueError("invalid provenance content digest")
        if any(not isinstance(token, str) or not 1 <= len(token) <= 256
               for token in source.lineage_tokens):
            raise ValueError("invalid provenance lineage token")
        if any(not isinstance(pid, str) or not pid for pid in source.parent_source_ids):
            raise ValueError("invalid parent source identity")
        by_id[source.source_id] = source
    if any(item.source_id not in by_id for item in evidence):
        raise ValueError("missing provenance for evidence source")
    # A superset is legitimate: parental sources can be part of a derivation
    # chain even when they do not themselves contain a reading for this claim.
    for source in sources:
        if any(pid not in by_id for pid in source.parent_source_ids):
            raise ValueError("unknown provenance parent")
    return by_id


def _assured_groups(
    evidence: tuple[EvidencePass, ...],
    sources: tuple[SourceProvenance, ...],
    by_id: dict[str, SourceProvenance],
    max_sources: int,
) -> tuple[tuple[SourceCluster, ...], dict[str, str]]:
    """Take the transitive closure of *both* custody and asserted dependence.

    A caller's independence label is an additional reason to *merge* groups,
    never authority to split groups proven dependent by content or lineage.
    """
    provenance_groups = derive_dependency_clusters(
        sources, authorized=True, max_sources=max_sources,
    )
    parents = {key: key for key in by_id}
    reasons: dict[str, set[str]] = {key: set() for key in by_id}

    def root(node: str) -> str:
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    def union(left: str, right: str, reason: str) -> None:
        a, b = root(left), root(right)
        if a != b:
            parents[max(a, b)] = min(a, b)
        reasons[left].add(reason)
        reasons[right].add(reason)

    for cluster in provenance_groups:
        ids = cluster.source_ids
        for key in ids:
            reasons[key].update(cluster.reasons)
        for other in ids[1:]:
            union(ids[0], other, "provenance_dependency")
    labelled: dict[str, str] = {}
    for item in evidence:
        if item.independence_group in labelled:
            union(item.source_id, labelled[item.independence_group],
                  "asserted_shared_group")
        else:
            labelled[item.independence_group] = item.source_id

    evidence_by_source: dict[str, list[EvidencePass]] = {}
    for reading in evidence:
        evidence_by_source.setdefault(reading.source_id, []).append(reading)
    grouped: dict[str, list[str]] = {}
    for sid in sorted(by_id):
        grouped.setdefault(root(sid), []).append(sid)
    by_source_group: dict[str, str] = {}
    clusters: list[SourceCluster] = []
    for ids in grouped.values():
        members = tuple(sorted(ids))
        # Include only sampled groups in a claim's effective evidence count.
        readings = tuple(e for sid in members for e in evidence_by_source.get(sid, ()))
        if not readings:
            continue
        identity = _fingerprint(["custody_cluster_v1", members])
        for sid in members:
            by_source_group[sid] = identity
        clusters.append(SourceCluster(
            identity,
            members,
            tuple(sorted({by_id[sid].content_digest for sid in members})),
            tuple(sorted(set().union(*(reasons[sid] for sid in members)))),
            len(readings),
            sum(e.supports for e in readings),
            sum(not e.supports for e in readings),
        ))
    clusters.sort(key=lambda c: c.source_ids)
    return tuple(clusters), by_source_group


def _actions(
    claim_id: str,
    belief: Belief,
    clusters: tuple[SourceCluster, ...],
    evidence: tuple[EvidencePass, ...],
    blockers: tuple[str, ...],
    limit: int,
    reread_min: int,
    reread_max: int,
) -> tuple[ResearchNextAction, ...]:
    result: list[ResearchNextAction] = []
    if "insufficient_independent_sources" in blockers:
        result.append(ResearchNextAction(
            "discover_independent_source", claim_id, 5.0,
            "Acquire a genuinely separate origin or primary observation; a mirror is not independent.",
        ))
    if "cross_source_contradiction" in blockers:
        for cluster in clusters:
            if cluster.opposing_readings:
                result.append(ResearchNextAction(
                    "falsify_opposition", cluster.cluster_id, 4.5,
                    "Inspect opposing evidence and seek a falsifying observation.",
                ))
    for cluster in clusters:
        if cluster.supporting_readings and cluster.opposing_readings:
            result.append(ResearchNextAction(
                "resolve_internal_contradiction", cluster.cluster_id, 4.75,
                "Trace incompatible observations to their original locators and time scopes.",
            ))
    if reread_min > 12:
        result.append(ResearchNextAction(
            "extend_lens_schedule", claim_id, 3.0,
            "A policy requiring more than twelve readings needs an explicitly reviewed lens schedule.",
        ))
    elif any(code in blockers for code in (
        "incomplete_reread_coverage", "cross_source_contradiction",
        "weak_heuristic_support",
    )):
        for decision in plan_adaptive_rereads(
            belief, evidence, authorized=True, min_passes=reread_min,
            max_passes=reread_max, limit=min(1000, max(limit * 2, 1)),
        ):
            if decision.next_pass is not None:
                result.append(ResearchNextAction(
                    "reread_with_lens",
                    f"{decision.source_id}@{decision.revision}#{decision.next_pass.pass_index}",
                    round(decision.priority, 6),
                    decision.next_pass.lens,
                ))
    if "fragile_to_source_removal" in blockers:
        result.append(ResearchNextAction(
            "replicate_with_new_custody", claim_id, 3.75,
            "Seek a held-out primary source; do not count another pass on an existing cluster.",
        ))
    # Drop duplicates, retain the highest-priority action, deterministic ties.
    unique: dict[tuple[str, str], ResearchNextAction] = {}
    for action in result:
        key = action.kind, action.target
        if key not in unique or unique[key].priority < action.priority:
            unique[key] = action
    return tuple(sorted(
        unique.values(), key=lambda x: (-x.priority, x.kind, x.target),
    )[:limit])


def assure_crawler_evidence(
    claim_id: str,
    evidence: Iterable[EvidencePass],
    provenance: Iterable[SourceProvenance],
    *,
    authorized: bool,
    evidence_policy: EvidencePolicy = EvidencePolicy(),
    assurance_policy: AssurancePolicy = AssurancePolicy(),
) -> ProvenanceAssurance:
    """Derive trusted *dependency* boundaries and stress-test the belief.

    The supplied manifest is a custody assertion, not a provenance signature.
    No human approval or memory promotion is performed, even when all heuristic
    research thresholds pass.
    """
    if not authorized:
        raise PermissionError("provenance analysis requires authorization")
    _verify_policy(assurance_policy)
    distiller = ProbabilisticKnowledgeDistiller(evidence_policy)
    items = tuple(evidence)
    sources = tuple(provenance)
    if len(items) > evidence_policy.max_evidence:
        raise ValueError("evidence budget exceeded")
    # Validate even when evidence is empty; detect cross-claim and replay errors.
    for item in items:
        distiller._validate(item)
    if not isinstance(claim_id, str) or not 1 <= len(claim_id) <= 256:
        raise ValueError("invalid claim identity")
    by_id = _manifest(items, sources, assurance_policy.maximum_sources)
    clusters, lookup = _assured_groups(
        items, sources, by_id, assurance_policy.maximum_sources,
    )
    from dataclasses import replace
    normalized = tuple(replace(
        item, independence_group=lookup[item.source_id],
    ) for item in items)
    belief = distiller.distill(claim_id, normalized)
    relabels = sum(
        left.independence_group != right.independence_group
        for left, right in zip(items, normalized)
    )
    if len(clusters) > assurance_policy.maximum_holdout_groups:
        raise ValueError("holdout group budget exceeded")

    holdouts: list[ClusterHoldout] = []
    for cluster in clusters:
        remaining = tuple(
            item for item in normalized
            if item.independence_group != cluster.cluster_id
        )
        hypothetical = distiller.distill(claim_id, remaining)
        holdouts.append(ClusterHoldout(
            cluster.cluster_id, hypothetical.independent_groups, len(remaining),
            hypothetical.probability,
            round(belief.probability - hypothetical.probability, 8),
            (belief.probability >= 0.5) != (hypothetical.probability >= 0.5),
        ))
    min_probability = min(
        (x.heldout_probability for x in holdouts),
        default=distiller.distill(claim_id, ()).probability,
    )
    # These are audit diagnostics; absence of a blocker is NOT approval.
    blockers: list[str] = []
    if len(clusters) < assurance_policy.min_independent_groups:
        blockers.append("insufficient_independent_sources")
    if not items:
        blockers.append("no_evidence")
    if belief.opposing_groups > 0 or any(
        c.supporting_readings and c.opposing_readings for c in clusters
    ):
        blockers.append("cross_source_contradiction")
    per_revision: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item.source_id, item.source_revision)
        per_revision[key] = per_revision.get(key, 0) + 1
    coverage = bool(items) and all(
        num >= evidence_policy.min_passes_per_source
        for num in per_revision.values()
    )
    if not coverage:
        blockers.append("incomplete_reread_coverage")
    if belief.probability < assurance_policy.min_supporting_probability:
        blockers.append("weak_heuristic_support")
    if min_probability < assurance_policy.min_heldout_probability:
        blockers.append("fragile_to_source_removal")
    blockers_tuple = tuple(blockers)
    actions = _actions(
        claim_id, belief, clusters, normalized, blockers_tuple,
        assurance_policy.maximum_actions,
        evidence_policy.min_passes_per_source,
        min(evidence_policy.max_passes_per_source, 12),
    )
    fingerprint = _fingerprint({
        "schema": "skeleton.crawler.provenance_assurance.v1",
        "claim": claim_id, "belief": belief.evidence_digest,
        "policy": [assurance_policy.min_independent_groups,
                   assurance_policy.min_supporting_probability,
                   assurance_policy.min_heldout_probability,
                   assurance_policy.maximum_holdout_groups],
        "sources": sorted([
            [s.source_id, s.content_digest, s.canonical_uri,
             sorted(s.parent_source_ids), sorted(s.lineage_tokens)]
            for s in sources
        ]),
        "clusters": [(c.cluster_id, c.source_ids) for c in clusters],
        "holdouts": [(h.cluster_id, h.heldout_probability) for h in holdouts],
    })
    candidate = not blockers_tuple
    return ProvenanceAssurance(
        claim_id, belief, clusters, tuple(holdouts),
        min_probability, belief.independent_groups,
        relabels, coverage, True, candidate,
        blockers_tuple, actions, fingerprint,
    )
