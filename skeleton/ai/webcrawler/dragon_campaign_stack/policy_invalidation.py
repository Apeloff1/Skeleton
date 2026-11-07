"""Cross-version policy invalidation with dependent evidence and claim fencing.

A source that becomes unavailable, changes policy revision, or gains a stricter
review state invalidates every downstream derivative. This report is a
conservative invalidation *proposal*, not the actual state transition or
a replacement for the application's authoritative source-use policy.

The caller must read both policy projections from the *same* fully validated
crawl snapshot and must authenticate the latest policy using the existing
backend owner before acting. Unknown, dangling and cyclic provenance fail
closed. No source bodies are copied into the invalidation report.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .claims import ClaimReviewMatrix
from .context_envelope import ResearchContextEnvelope
from .contracts import CampaignMandate, digest
from .lineage import SourceLink, LineageImpact, invalidation_closure
from .policy_matrix import SourcePolicyProjection, SourcePolicyFinding
from .retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class PolicyTransition:
    source_id: str
    old_revision: int
    new_revision: int
    old_state: str
    new_state: str
    old_eligible: bool
    new_eligible: bool
    disposition: str
    requires_context_withdrawal: bool
    requires_review: bool = True


@dataclass(frozen=True)
class EvidenceInvalidation:
    source_id: str
    passage_hashes: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    affected_objective_ids: tuple[str, ...]
    withdrawal_kind: str
    requires_new_snapshot_review: bool = True


@dataclass(frozen=True)
class PolicyInvalidation:
    mandate_digest: str
    source_snapshot_digest: str
    previous_policy_digest: str
    current_policy_digest: str
    transitions: tuple[PolicyTransition, ...]
    lineage: LineageImpact
    evidence: tuple[EvidenceInvalidation, ...]
    affected_claim_ids: tuple[str, ...]
    affected_objective_ids: tuple[str, ...]
    affected_index_source_ids: tuple[str, ...]
    affected_context_source_ids: tuple[str, ...]
    requires_index_rebuild: bool
    requires_context_rebuild: bool
    requires_claim_review: bool
    impact_digest: str
    authenticated_latest_policy: bool = False
    automatic_publication_authority: bool = False


def _check_universe(
    previous: SourcePolicyProjection,
    current: SourcePolicyProjection,
    mandate: CampaignMandate,
) -> tuple[str, ...]:
    if not isinstance(previous, SourcePolicyProjection) or not isinstance(current, SourcePolicyProjection):
        raise TypeError("two canonical source-policy projections required")
    if previous.mandate_digest != mandate.fingerprint or current.mandate_digest != mandate.fingerprint:
        raise PermissionError("cross-mandate source policy comparison")
    if previous.source_snapshot_digest != current.source_snapshot_digest:
        raise PermissionError("changed crawl snapshot requires fresh full source inspection")
    old_ids = {x.source_id for x in previous.decisions}
    new_ids = {x.source_id for x in current.decisions}
    if old_ids != new_ids or len(old_ids) != previous.source_count or len(new_ids) != current.source_count:
        raise PermissionError("incomplete or inconsistent source-policy universe")
    if old_ids != set(previous.allowed_source_ids) | set(previous.excluded_source_ids):
        raise ValueError("old policy source universe mismatch")
    if new_ids != set(current.allowed_source_ids) | set(current.excluded_source_ids):
        raise ValueError("current policy source universe mismatch")
    if set(previous.allowed_source_ids) & set(previous.excluded_source_ids):
        raise ValueError("old source policy contains duplicate state")
    if set(current.allowed_source_ids) & set(current.excluded_source_ids):
        raise ValueError("current source policy contains duplicate state")
    return tuple(sorted(old_ids))


def assess_policy_invalidation(
    mandate: CampaignMandate,
    previous: SourcePolicyProjection,
    current: SourcePolicyProjection,
    *,
    now: float,
    authorized: bool,
    links: Iterable[SourceLink] = (),
    retrieval: RetrievalFusion | None = None,
    context: ResearchContextEnvelope | None = None,
    matrix: ClaimReviewMatrix | None = None,
) -> PolicyInvalidation:
    mandate.admit(now=now, authorized=authorized)
    source_universe = _check_universe(previous, current, mandate)
    if retrieval is not None and (
        not isinstance(retrieval, RetrievalFusion)
        or retrieval.mandate_digest != mandate.fingerprint
        or retrieval.source_snapshot_digest != current.source_snapshot_digest
    ):
        raise PermissionError("foreign retrieval invalidation")
    if context is not None and (
        not isinstance(context, ResearchContextEnvelope)
        or context.mandate_digest != mandate.fingerprint
        or context.source_snapshot_digest != current.source_snapshot_digest
    ):
        raise PermissionError("foreign context invalidation")
    if matrix is not None and (
        not isinstance(matrix, ClaimReviewMatrix)
        or matrix.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("foreign claim invalidation")
    if context is not None and retrieval is None:
        raise ValueError("context invalidation needs its bound retrieval receipt")
    if context is not None and context.retrieval_digest != retrieval.fusion_digest:
        raise PermissionError("context belongs to different retrieval")
    before = {x.source_id: x for x in previous.decisions}
    after = {x.source_id: x for x in current.decisions}
    changes = []
    invalidated = set()
    for ident in source_universe:
        old, new = before[ident], after[ident]
        if not isinstance(old, SourcePolicyFinding) or not isinstance(new, SourcePolicyFinding):
            raise TypeError("typed policy findings required")
        if old.status == new.status and (
            old.policy_revision == new.policy_revision
            and old.eligible_for_inspection == new.eligible_for_inspection
            and old.reason == new.reason
        ):
            continue
        if new.policy_revision < old.policy_revision:
            raise ValueError("source policy revision rolled backward")
        changed_revision = new.policy_revision != old.policy_revision
        withdrawn = old.eligible_for_inspection and not new.eligible_for_inspection
        resurrected = not old.eligible_for_inspection and new.eligible_for_inspection
        disposition = (
            "source_use_withdrawn" if withdrawn else
            "source_use_reenabled_requires_fresh_review" if resurrected else
            "policy_revision_changed" if changed_revision else
            "source_review_state_changed"
        )
        invalidated.add(ident)
        changes.append(PolicyTransition(
            source_id=ident, old_revision=old.policy_revision,
            new_revision=new.policy_revision,
            old_state=old.status, new_state=new.status,
            old_eligible=old.eligible_for_inspection,
            new_eligible=new.eligible_for_inspection,
            disposition=disposition,
            requires_context_withdrawal=True,
        ))
    lineage = invalidation_closure(
        source_universe, tuple(links),
        revoked=tuple(sorted(invalidated)),
        limits=mandate.limits,
    )
    affected = set(lineage.affected_source_ids)
    retrieval_by_source: dict[str, set[str]] = {}
    objectives_by_source: dict[str, set[str]] = {}
    if retrieval:
        for hit in retrieval.results:
            if hit.source_id not in source_universe:
                raise PermissionError("retrieval cites foreign source")
            retrieval_by_source.setdefault(hit.source_id, set()).add(hit.passage_hash)
            objectives_by_source.setdefault(hit.source_id, set()).update(hit.matched_objective_ids)
    context_by_source: dict[str, set[str]] = {}
    if context:
        for reference in context.references:
            if reference.source_id not in source_universe:
                raise PermissionError("context cites foreign source")
            context_by_source.setdefault(reference.source_id, set()).add(reference.passage_hash)
    claims_by_source: dict[str, set[str]] = {}
    if matrix:
        for claim in matrix.claims:
            for source_id in (
                claim.support_sources + claim.refute_sources + claim.context_sources
            ):
                if source_id not in source_universe:
                    raise PermissionError("claim matrix cites foreign source")
                claims_by_source.setdefault(source_id, set()).add(claim.claim_id)
                objectives_by_source.setdefault(source_id, set()).add(claim.objective_id)
    observations = []
    for source_id in sorted(affected):
        observations.append(EvidenceInvalidation(
            source_id=source_id,
            passage_hashes=tuple(sorted(
                retrieval_by_source.get(source_id, set()) |
                context_by_source.get(source_id, set())
            )),
            affected_claim_ids=tuple(sorted(claims_by_source.get(source_id, ()))),
            affected_objective_ids=tuple(sorted(objectives_by_source.get(source_id, ()))),
            withdrawal_kind=(
                "changed_policy" if source_id in invalidated
                else "derivative_source_lineage"
            ),
        ))
    affected_context = tuple(sorted(affected & set(context_by_source)))
    affected_index = tuple(sorted(affected & set(retrieval_by_source)))
    affected_claims = tuple(sorted({
        c for row in observations for c in row.affected_claim_ids
    }))
    affected_objectives = tuple(sorted({
        x for row in observations for x in row.affected_objective_ids
    }))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current.source_snapshot_digest,
        "previous": previous.policy_digest,
        "current": current.policy_digest,
        "transitions": [asdict(x) for x in changes],
        "lineage": lineage.lineage_digest,
        "affected": [asdict(x) for x in observations],
        "index_sources": affected_index, "context_sources": affected_context,
    }
    return PolicyInvalidation(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=current.source_snapshot_digest,
        previous_policy_digest=previous.policy_digest,
        current_policy_digest=current.policy_digest,
        transitions=tuple(changes), lineage=lineage,
        evidence=tuple(observations),
        affected_claim_ids=affected_claims,
        affected_objective_ids=affected_objectives,
        affected_index_source_ids=affected_index,
        affected_context_source_ids=affected_context,
        requires_index_rebuild=bool(changes),
        requires_context_rebuild=bool(changes),
        requires_claim_review=bool(changes) or bool(affected_claims),
        impact_digest=digest(payload),
    )
