"""Dragon Atlas: end-to-end bounded research inspection over canonical CrawlRun.

The Atlas is a synchronous, deterministic advisory projection. It never
fetches, starts a crawler, updates Mongo, authorizes agents, trains a model or
promotes external text to knowledge. Its source-use policy must be supplied
by an already authenticated application boundary and must cover every source
in the current canonical snapshot before any retained text is examined.

Pipeline:
  mandate -> canonical snapshot -> complete source policy -> workbench
  -> query lattice -> current-source lexical index -> diverse rank fusion
  -> exact-span context envelope -> independence audit -> resource fairness
  -> evidence scorecard -> immutable stage receipt chain -> human review.

All external mutations, acquisition, writes, licenses, independent review,
publication and rollback require separate existing application authorities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .claims import ClaimCitation, IndependenceAttestation, ResearchClaim
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .context_envelope import ResearchContextEnvelope, build_research_context
from .frontier_allocator import AllocationAdvice, allocate_frontier_advisory
from .independence_audit import IndependenceAudit, audit_independence
from .lineage import SourceLink
from .objectives import ResearchObjective
from .policy_matrix import (
    SourcePolicyDecision, SourcePolicyProjection, project_source_policy,
)
from .pressure import (
    PressureDecision, ResourceObservation, recommend_crawl_pressure,
)
from .quality_scorecard import ResearchScorecard, measure_research_scorecard
from .query_lattice import QueryLattice, compile_query_lattice
from .retrieval_fusion import RetrievalFusion, fuse_retrieval
from .source_drift import SnapshotDrift, analyze_snapshot_drift
from .source_index import EphemeralIndex, build_ephemeral_index
from .workbench import DragonWorkbench, compose_dragon_workbench


STAGES = (
    "protected_source_policy",
    "canonical_research_workbench",
    "operator_query_lattice",
    "retained_source_index",
    "source_diverse_retrieval",
    "source_bound_context",
    "independence_counter_audit",
    "resource_bounded_frontier",
    "human_review_scorecard",
    "optional_checkpoint_drift",
)


@dataclass(frozen=True)
class AtlasStage:
    ordinal: int
    name: str
    input_chain_digest: str
    receipt_digest: str
    chain_digest: str
    content_may_be_trusted: bool = False
    external_effect_committed: bool = False


@dataclass(frozen=True)
class DragonAtlas:
    run_id: str
    mandate_digest: str
    source_snapshot_digest: str
    source_sequence: int
    issued_at: float
    policies: SourcePolicyProjection
    workbench: DragonWorkbench
    lattice: QueryLattice
    index: EphemeralIndex
    retrieval: RetrievalFusion
    context: ResearchContextEnvelope
    independence: IndependenceAudit | None
    pressure: PressureDecision | None
    allocation: AllocationAdvice
    scorecard: ResearchScorecard
    drift: SnapshotDrift | None
    stages: tuple[AtlasStage, ...]
    atlas_digest: str
    operational_state: str = "human_review_required"
    remote_network_used: bool = False
    persistent_corpus_written: bool = False
    external_text_trusted: bool = False
    model_training_authorized: bool = False
    publication_authorized: bool = False
    dispatch_authorized: bool = False


def _stage_chain(
    mandate: CampaignMandate, snapshot_digest: str,
    receipts: Iterable[tuple[str, str | None]],
) -> tuple[AtlasStage, ...]:
    rows = tuple(receipts)
    if tuple(x[0] for x in rows) != STAGES:
        raise ValueError("unexpected Dragon Atlas stage order")
    chain = digest({
        "schema": "skeleton.dragon.atlas.v1",
        "mandate": mandate.fingerprint,
        "snapshot": snapshot_digest,
    })
    result = []
    for i, (name, receipt) in enumerate(rows):
        if receipt is None:
            receipt = digest({
                "absent": name, "mandate": mandate.fingerprint,
                "snapshot": snapshot_digest,
            })
        if not isinstance(receipt, str) or len(receipt) != 64 or any(
            letter not in "0123456789abcdef" for letter in receipt
        ):
            raise ValueError("invalid Atlas stage receipt digest")
        previous = chain
        chain = digest({
            "at": i, "name": name,
            "previous": previous, "receipt": receipt,
        })
        result.append(AtlasStage(i, name, previous, receipt, chain))
    return tuple(result)


def _receipts(atlas: DragonAtlas) -> tuple[tuple[str, str | None], ...]:
    return (
        ("protected_source_policy", atlas.policies.policy_digest),
        ("canonical_research_workbench", atlas.workbench.workbench_digest),
        ("operator_query_lattice", atlas.lattice.lattice_digest),
        ("retained_source_index", atlas.index.index_digest),
        ("source_diverse_retrieval", atlas.retrieval.fusion_digest),
        ("source_bound_context", atlas.context.envelope_digest),
        ("independence_counter_audit",
         atlas.independence.audit_digest if atlas.independence else None),
        ("resource_bounded_frontier", atlas.allocation.advice_digest),
        ("human_review_scorecard", atlas.scorecard.scorecard_digest),
        ("optional_checkpoint_drift", atlas.drift.drift_digest if atlas.drift else None),
    )


def compose_dragon_atlas(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    *,
    objectives: Iterable[ResearchObjective],
    source_policies: Iterable[SourcePolicyDecision],
    policy_snapshot_authenticated: bool,
    now: float,
    authorized: bool,
    claims: Iterable[ResearchClaim] = (),
    claim_citations: Iterable[ClaimCitation] = (),
    independence_attestations: Iterable[IndependenceAttestation] = (),
    source_links: Iterable[SourceLink] = (),
    telemetry: Iterable[ResourceObservation] = (),
    previous_snapshot: dict[str, object] | None = None,
    max_index_passages: int = 2048,
    max_retrieved_passages: int = 16,
    max_context_chars: int = 8000,
) -> DragonAtlas:
    """Compose one immutable, review-only source-bound research snapshot.

    Caller contracts:
      - current tenant/owner, request and source policy came from protected
        authenticated backend authority, never crawler/page/LLM suggestions;
      - a later consumer *re-fetches* both snapshot and source-use policy
        before acting on any reference; this receipt cannot certify either;
      - no resource pressure observation may be invented, re-timed or treated
        as permission to spawn a worker.
    """
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_index_passages, "index capacity", 1, 4096)
    integer(max_retrieved_passages, "retrieval capacity", 1, 32)
    integer(max_context_chars, "context capacity", 512, 24_000)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    policy_rows = tuple(source_policies)
    objective_rows = tuple(objectives)
    claim_rows = tuple(claims)
    citation_rows = tuple(claim_citations)
    groups = tuple(independence_attestations)
    links = tuple(source_links)
    observations = tuple(telemetry)
    # STOP before reading external page bodies unless ALL retained sources
    # have current, revision-accurate source-use decisions from the backend.
    policy = project_source_policy(
        mandate, canonical, policy_rows, now=now, authorized=authorized,
        policy_snapshot_authenticated=policy_snapshot_authenticated,
    )
    withdrawn = policy.excluded_source_ids
    workbench = compose_dragon_workbench(
        mandate, canonical, objectives=objective_rows,
        claims=claim_rows, claim_citations=citation_rows,
        independence_attestations=groups,
        revoked_source_ids=withdrawn,
        source_links=links,
        now=now, authorized=authorized,
    )
    lattice = compile_query_lattice(
        mandate, workbench.objectives, now=now, authorized=authorized,
    )
    index = build_ephemeral_index(
        mandate, canonical, now=now, authorized=authorized,
        revoked_source_ids=withdrawn, max_passages=max_index_passages,
    )
    fused = fuse_retrieval(
        mandate, canonical, index, lattice, now=now,
        authorized=authorized, revoked_source_ids=withdrawn,
        max_results=max_retrieved_passages,
        max_context_chars=max_context_chars,
    )
    context = build_research_context(
        mandate, canonical, fused, now=now, authorized=authorized,
        revoked_source_ids=withdrawn,
        max_context_chars=max_context_chars,
        max_references=max_retrieved_passages,
    )
    independent = (
        audit_independence(
            mandate, canonical, workbench.claim_matrix, groups,
            links=links, revoked_source_ids=withdrawn,
            now=now, authorized=authorized,
        ) if workbench.claim_matrix else None
    )
    pressure = (
        recommend_crawl_pressure(
            mandate, workbench.inspection.budget, observations,
            now=now, authorized=authorized,
        ) if observations else None
    )
    allocation = allocate_frontier_advisory(
        mandate, workbench.topology, workbench.strategy,
        workbench.inspection.budget, pressure=pressure,
        now=now, authorized=authorized,
    )
    scorecard = measure_research_scorecard(
        mandate, workbench.inspection, workbench.coverage,
        policy, fused, context, independent, now=now, authorized=authorized,
    )
    drift = (
        analyze_snapshot_drift(
            mandate, previous_snapshot, canonical, now=now,
            authorized=authorized, revoked_source_ids=withdrawn,
        ) if previous_snapshot is not None else None
    )
    root = DragonAtlas(
        run_id=canonical["run_id"],
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        source_sequence=canonical["sequence"],
        issued_at=now, policies=policy, workbench=workbench,
        lattice=lattice, index=index, retrieval=fused, context=context,
        independence=independent, pressure=pressure,
        allocation=allocation, scorecard=scorecard, drift=drift,
        stages=(), atlas_digest="",
    )
    stages = _stage_chain(
        mandate, canonical["snapshot_digest"], _receipts(root),
    )
    output_digest = digest({
        "mandate": mandate.fingerprint,
        "run": canonical["run_id"],
        "snapshot": canonical["snapshot_digest"],
        "sequence": canonical["sequence"],
        "at": now,
        "final_stage": stages[-1].chain_digest,
        "holds": scorecard.alerts,
        "source_policy": policy.policy_digest,
        "review_only": True,
    })
    return DragonAtlas(
        **{**root.__dict__, "stages": stages, "atlas_digest": output_digest},
    )


def verify_dragon_atlas_trace(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    atlas: DragonAtlas,
    *,
    now: float,
    authorized: bool,
) -> None:
    """Verify receipt-chain integrity; NOT authenticate the source policy."""
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(atlas, DragonAtlas):
        raise TypeError("typed Atlas result required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if atlas.mandate_digest != mandate.fingerprint or (
        atlas.source_snapshot_digest != canonical["snapshot_digest"]
        or atlas.run_id != canonical["run_id"]
        or atlas.source_sequence != canonical["sequence"]
    ):
        raise PermissionError("Atlas no longer bound to the current crawl")
    if atlas.issued_at > now or atlas.issued_at < mandate.created_at:
        raise ValueError("invalid Atlas receipt clock")
    if any((
        atlas.remote_network_used, atlas.persistent_corpus_written,
        atlas.external_text_trusted, atlas.model_training_authorized,
        atlas.publication_authorized, atlas.dispatch_authorized,
    )):
        raise PermissionError("Atlas cannot assert elevated authority")
    if atlas.operational_state != "human_review_required":
        raise PermissionError("unapproved Atlas operational state")
    expected = _stage_chain(
        mandate, canonical["snapshot_digest"], _receipts(atlas),
    )
    if expected != atlas.stages:
        raise ValueError("Atlas stage chain mismatch")
    payload = {
        "mandate": mandate.fingerprint,
        "run": canonical["run_id"],
        "snapshot": canonical["snapshot_digest"],
        "sequence": canonical["sequence"],
        "at": atlas.issued_at,
        "final_stage": expected[-1].chain_digest,
        "holds": atlas.scorecard.alerts,
        "source_policy": atlas.policies.policy_digest,
        "review_only": True,
    }
    if digest(payload) != atlas.atlas_digest:
        raise ValueError("Atlas digest mismatch")
    if atlas.policies.excluded_source_ids != atlas.retrieval.excluded_sources:
        raise PermissionError("Atlas withdrawal set inconsistent")
    if atlas.context.retrieval_digest != atlas.retrieval.fusion_digest:
        raise PermissionError("Atlas context attached to foreign retrieval")
    if atlas.scorecard.source_snapshot_digest != atlas.source_snapshot_digest:
        raise PermissionError("Atlas scorecard attached to foreign source")
