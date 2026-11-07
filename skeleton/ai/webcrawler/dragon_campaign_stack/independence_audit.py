"""Source-independence counter-audit for claim evidence and origin lineage.

Independence attestations can be overcounted by copied documents, mirrored
captures and revision/derivation links. This module detects those apparent
dependencies and conservatively collapses claims to remaining groups. It
never asserts factual truth or legal rights, and it cannot improve a claim's
original assessment into a reviewed or published state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .claims import ClaimReviewMatrix, IndependenceAttestation
from .contracts import CampaignMandate, digest, ensure_snapshot_scope
from .lineage import SourceLink, validate_lineage


@dataclass(frozen=True)
class CorrelatedGroups:
    left_group: str
    right_group: str
    relationship: str
    source_pairs: tuple[tuple[str, str], ...]
    review_required: bool = True


@dataclass(frozen=True)
class ClaimIndependence:
    claim_id: str
    asserted_support_groups: int
    effective_support_groups_upper_bound: int
    potentially_correlated_groups: tuple[str, ...]
    source_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    factual_truth_established: bool = False


@dataclass(frozen=True)
class IndependenceAudit:
    mandate_digest: str
    source_snapshot_digest: str
    matrix_digest: str
    findings: tuple[CorrelatedGroups, ...]
    claims: tuple[ClaimIndependence, ...]
    ambiguous_group_count: int
    tainted_source_count: int
    audit_digest: str
    automated_corroboration_approval: bool = False


def audit_independence(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    matrix: ClaimReviewMatrix,
    attestations: Iterable[IndependenceAttestation],
    *,
    now: float,
    authorized: bool,
    links: Iterable[SourceLink] = (),
    revoked_source_ids: Iterable[str] = (),
) -> IndependenceAudit:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(matrix, ClaimReviewMatrix) or matrix.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign claim matrix")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    sources = canonical["sources"]
    groups = tuple(attestations)
    if len(groups) > 64:
        raise ValueError("group audit capacity exceeded")
    revoked = tuple(revoked_source_ids)
    if len(set(revoked)) != len(revoked) or not set(revoked).issubset(sources):
        raise PermissionError("invalid current source withdrawals")
    lineage = validate_lineage(sources, links, limits=mandate.limits)
    # Derivation/revision ancestry is transitive. Two attested origins may
    # share an un-attested intermediary even when there is no direct edge
    # between their own captured source identities.
    parents = {source_id: set() for source_id in sources}
    for edge in lineage:
        if edge.relation in ("derived_from", "revision_of"):
            parents[edge.child_source_id].add(edge.parent_source_id)
    ancestry = {}
    for source_id in sorted(sources):
        visited = set()
        pending = list(parents[source_id])
        while pending:
            previous = pending.pop()
            if previous in visited:
                continue
            visited.add(previous)
            pending.extend(parents[previous] - visited)
        ancestry[source_id] = visited | {source_id}
    by_group = {}
    membership = {}
    for group in groups:
        if not isinstance(group, IndependenceAttestation):
            raise TypeError("typed attestation required")
        if group.group_id in by_group:
            raise ValueError("duplicate independence group")
        if not set(group.source_ids).issubset(sources):
            raise PermissionError("attestation cites unrecognized source")
        if any(source in membership for source in group.source_ids):
            raise ValueError("overlapping source independence claims")
        for source in group.source_ids:
            membership[source] = group.group_id
        by_group[group.group_id] = group
    if any(
        claim.attested_support_groups > len(groups)
        for claim in matrix.claims
    ):
        raise ValueError("claim matrix references more groups than attestations")
    # Pairwise comparisons are bounded to <= 64 groups, <= 128 sources.
    correlations = {}
    for i, left in enumerate(groups):
        for right in groups[i+1:]:
            reasons = {}
            for a in left.source_ids:
                for b in right.source_ids:
                    if sources[a]["content_hash"] == sources[b]["content_hash"]:
                        reasons.setdefault("identical_captured_content", []).append((a, b))
                    if ancestry[a] & ancestry[b]:
                        reasons.setdefault("shared_derivation_ancestry", []).append((a, b))
            for link in lineage:
                a, b = link.child_source_id, link.parent_source_id
                if ((a in left.source_ids and b in right.source_ids)
                        or (b in left.source_ids and a in right.source_ids)):
                    if link.relation in ("derived_from", "revision_of", "same_content"):
                        reasons.setdefault("related_source_lineage", []).append((a, b))
            if reasons:
                key = tuple(sorted((left.group_id, right.group_id)))
                correlations[key] = CorrelatedGroups(
                    left_group=key[0], right_group=key[1],
                    relationship="+".join(sorted(reasons)),
                    source_pairs=tuple(sorted(set(pair for vals in reasons.values()
                                                  for pair in vals))),
                )
    tainted = set(revoked)
    for finding in correlations.values():
        for a, b in finding.source_pairs:
            tainted.update((a, b))
    assessments = []
    for claim in matrix.claims:
        support = tuple(sorted(claim.support_sources))
        related = sorted({
            membership[source] for source in support
            if source in membership and by_group[membership[source]].provenance_reviewed
        })
        unsupported = set(support) - set(membership)
        contaminated = set()
        for finding in correlations.values():
            if finding.left_group in related and finding.right_group in related:
                contaminated.update((finding.left_group, finding.right_group))
        for source in support:
            if source in revoked and source in membership:
                contaminated.add(membership[source])
        # Upper bound: assume every involved correlated group needs fresh
        # provenance review; do not count it as independent corroboration.
        effective = len(set(related) - contaminated)
        effective = min(effective, claim.attested_support_groups)
        blockers = []
        if unsupported:
            blockers.append("support_has_no_reviewed_origin_group")
        if contaminated:
            blockers.append("source_origin_correlation_needs_review")
        if set(support) & set(revoked):
            blockers.append("current_source_policy_withdrawal")
        if effective < claim.attested_support_groups:
            blockers.append("asserted_corroboration_not_reproduced")
        if claim.conflicted:
            blockers.append("contradictory_evidence_unresolved")
        blockers.append("human_factual_review_required")
        assessments.append(ClaimIndependence(
            claim_id=claim.claim_id,
            asserted_support_groups=claim.attested_support_groups,
            effective_support_groups_upper_bound=effective,
            potentially_correlated_groups=tuple(sorted(contaminated)),
            source_ids=support,
            blockers=tuple(sorted(set(blockers))),
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "matrix": matrix.matrix_digest,
        "groups": [asdict(x) for x in groups],
        "lineage": [asdict(x) for x in lineage],
        "revoked": sorted(revoked),
        "findings": [asdict(x) for x in correlations.values()],
        "claims": [asdict(x) for x in assessments],
    }
    return IndependenceAudit(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        matrix_digest=matrix.matrix_digest,
        findings=tuple(sorted(correlations.values(),
                              key=lambda x: (x.left_group, x.right_group))),
        claims=tuple(assessments),
        ambiguous_group_count=len({
            key for finding in correlations.values()
            for key in (finding.left_group, finding.right_group)
        }),
        tainted_source_count=len(tainted),
        audit_digest=digest(payload),
    )
