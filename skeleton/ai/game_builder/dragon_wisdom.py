"""Dragon's four-square advisory review of the canonical two-rival forge.

This is an evidence projection, not a third producer or release authority.
Industry grades require independently measured, workload-matched comparators.
Unknown comparator evidence stays unknown rather than becoming a perfect score.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Iterable

from .contracts import Candidate, EvaluatorProvenance, QUALITY_AXES, Rival, canonical_digest
from .dual_rival_forge import DualRivalForge
from .evaluation import EvaluationPanel
from .knowledge_rights_bridge import ClearedResearchPacket, require_cleared_research_current
from .reviewed_knowledge import ReviewedKnowledgeStore
from .rights import IncorporationDecision, RightsLedger
from .dragon_porting import JurisdictionReview, legal_release_blockers
from .dragon_legal_updates import LegalSourceObservation, legal_update_impact


SQUARES = (
    ("play", "Play & depth", ("player_value", "fun_engagement", "mechanical_depth", "replayability", "clarity_readability")),
    ("craft", "Story & craft", ("originality", "narrative_coherence", "longform_consistency", "emotional_impact", "aesthetic_coherence")),
    ("delivery", "Technical delivery", ("technical_correctness", "performance", "accessibility", "platform_fit", "state_integrity", "reproducibility", "maintainability", "testability")),
    ("trust", "Rights & evidence", ("rights_provenance_safety", "security_privacy", "source_evidence_quality")),
)


def _digest(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256 identity")


@dataclass(frozen=True, slots=True)
class IndustryMeasurement:
    """One scoped comparator, measured by a declared independent evaluator."""

    product_id: str
    workload_digest: str
    quality: tuple[tuple[str, float], ...]
    measured_at: int
    expires_at: int
    evidence_digest: str
    provenance: EvaluatorProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, str) or not self.product_id.strip() or len(self.product_id) > 192:
            raise ValueError("bounded comparator product identity required")
        for value in (self.workload_digest, self.evidence_digest):
            _digest(value)
        if type(self.measured_at) is not int or type(self.expires_at) is not int or not 0 <= self.measured_at < self.expires_at:
            raise ValueError("comparator validity interval required")
        if not isinstance(self.quality, tuple) or len(self.quality) != len(QUALITY_AXES) or set(dict(self.quality)) != set(QUALITY_AXES):
            raise ValueError("comparator must measure every quality axis exactly once")
        for _, score in self.quality:
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score) or not 0 <= score <= 1:
                raise ValueError("finite normalized comparator scores required")
        if not isinstance(self.provenance, EvaluatorProvenance) or self.provenance.evaluator_id in {r.value for r in Rival}:
            raise ValueError("comparator evaluator must be independent of rivals")
        if self.evidence_digest not in self.provenance.output_evidence_refs:
            raise ValueError("comparator measurement needs evaluator output evidence")


@dataclass(frozen=True, slots=True)
class Improvement:
    square: str
    axis: str
    target: str
    priority: str
    instruction: str
    evidence_refs: tuple[str, ...]

    def to_payload(self) -> dict:
        return {"square": self.square, "axis": self.axis, "target": self.target,
                "priority": self.priority, "instruction": self.instruction,
                "evidence_refs": list(self.evidence_refs)}


@dataclass(frozen=True, slots=True)
class SquareReview:
    candidate_digest: str
    artifact_digest: str
    workload_digest: str
    panel_digest: str
    rights_ledger_digest: str
    knowledge_root: str | None
    completed_rounds: int
    planned_rounds: int
    squares: tuple[dict, ...]
    improvements: tuple[Improvement, ...]
    blockers: tuple[str, ...]
    comparator_evidence: tuple[str, ...]
    legal_evidence_root: str
    terminal: bool

    def to_payload(self) -> dict:
        body = {
            "schema": "skeleton.dragon.square_review.v1",
            "candidate_digest": self.candidate_digest, "artifact_digest": self.artifact_digest,
            "workload_digest": self.workload_digest, "panel_digest": self.panel_digest,
            "rights_ledger_digest": self.rights_ledger_digest, "knowledge_root": self.knowledge_root,
            "completed_rounds": self.completed_rounds, "planned_rounds": self.planned_rounds,
            "squares": list(self.squares), "improvements": [r.to_payload() for r in self.improvements],
            "blockers": list(self.blockers), "comparator_evidence": list(self.comparator_evidence),
            "legal_evidence_root": self.legal_evidence_root,
            "terminal": self.terminal, "release_authority": False,
            "claim_boundary": "advisory quality projection; legal clearance and release remain independent",
        }
        return {**body, "review_digest": canonical_digest(body)}


def review_candidate(
    forge: DualRivalForge, panel: EvaluationPanel, rights: RightsLedger, *,
    candidate: Candidate, workload_digest: str, now: int,
    incorporation_decisions: Iterable[IncorporationDecision],
    target_id: str, jurisdictions: Iterable[str], legal_reviews: Iterable[JurisdictionReview],
    comparators: Iterable[IndustryMeasurement] = (),
    research: ClearedResearchPacket | None = None,
    library: ReviewedKnowledgeStore | None = None,
    terminal: bool = False,
    legal_source_baseline: Iterable[LegalSourceObservation] = (),
    legal_source_current: Iterable[LegalSourceObservation] = (),
) -> SquareReview:
    """Review actual panel evidence, with no provider calls or forge mutation.

    During refinement, review either pending rival or current champion. The
    user-facing terminal card is produced only after the exact round budget.
    Research packets are rechecked against canonical source and rights state.
    """
    _digest(workload_digest)
    if type(now) is not int or now < 0 or type(terminal) is not bool:
        raise ValueError("explicit integer review time and terminal flag required")
    if terminal and (not forge.completed or candidate.digest != forge.champion.digest):
        raise ValueError("terminal dragon review requires completed champion")
    known = {forge.champion.digest}
    if forge.pending_construct is not None:
        known.add(forge.pending_construct.digest)
    if forge.pending_challenge is not None:
        known.add(forge.pending_challenge.improved_candidate.digest)
    if candidate.digest not in known:
        raise ValueError("dragon cannot review an unbound candidate")
    decision = panel.decide(candidate.digest)
    if set(decision.quality_map) != set(QUALITY_AXES):
        raise ValueError("panel axes are incomplete")
    knowledge_root = None
    if research is not None:
        if library is None or research.artifact_digest != candidate.artifact.artifact_digest or research.project_id != candidate.producer_provenance.project_id:
            raise ValueError("research packet must match candidate project and artifact")
        require_cleared_research_current(research, library, rights, authorized=True)
        knowledge_root = research.knowledge_root
    allowed, rights_blockers = rights.release_gate(
        artifact_digest=candidate.artifact.artifact_digest,
        incorporation_decisions=incorporation_decisions,
    )
    blockers = list(rights_blockers)
    legal_rows = tuple(legal_reviews)
    legal_blockers = list(legal_release_blockers(artifact_digest=candidate.artifact.artifact_digest,
        target_id=target_id, jurisdictions=jurisdictions, reviews=legal_rows, now=now))
    old_sources, new_sources = tuple(legal_source_baseline), tuple(legal_source_current)
    if new_sources and not old_sources:
        raise ValueError("monitored legal sources require a baseline")
    if old_sources:
        impact = legal_update_impact(old_sources, new_sources, legal_rows, now=now)
        for artifact, target, region, area in impact["invalidated_reviews"]:
            if artifact == candidate.artifact.artifact_digest and target == target_id:
                legal_blockers.append(f"{region}/{area}: monitored primary source requires re-review")
    legal_root = canonical_digest({
        "reviews": sorted((r.artifact_digest, r.target_id, r.jurisdiction, r.area,
            r.disposition, r.checked_at, r.expires_at, r.evidence_digest, r.authority.digest) for r in legal_rows),
        "source_baseline": sorted((r.source_id, r.url, r.jurisdiction, sorted(r.areas),
            r.content_digest, r.captured_at, r.custody_evidence_digest, r.provenance.digest) for r in old_sources),
        "source_current": sorted((r.source_id, r.url, r.jurisdiction, sorted(r.areas),
            r.content_digest, r.captured_at, r.custody_evidence_digest, r.provenance.digest) for r in new_sources),
    })
    blockers.extend(legal_blockers)
    allowed = allowed and not legal_blockers
    if not decision.eligible:
        blockers.append("independent panel requires appeal")
    measurements = tuple(comparators)
    if len(measurements) > 128 or any(not isinstance(r, IndustryMeasurement) for r in measurements):
        raise ValueError("bounded typed comparator set required")
    if len({r.product_id for r in measurements}) != len(measurements):
        raise ValueError("duplicate comparator products cannot inflate comparison")
    usable = tuple(r for r in measurements if r.workload_digest == workload_digest and r.measured_at <= now < r.expires_at)
    baseline = {axis: median(dict(r.quality)[axis] for r in usable) for axis in QUALITY_AXES} if usable else {}
    quality = decision.quality_map
    squares = []
    improvements = []
    for key, label, axes in SQUARES:
        # Use the weakest dimension, so narrative polish cannot conceal broken
        # continuity, and rights cannot compensate for a security regression.
        score = min(quality[a] for a in axes)
        reference = min(baseline[a] for a in axes) if baseline else None
        status = "blocked" if key == "trust" and not allowed else "review" if not decision.eligible else "improve" if score < .75 else "ready"
        squares.append({"id": key, "label": label, "score": round(score * 100, 2),
                        "industry_score": round(reference * 100, 2) if reference is not None else None,
                        "industry_delta": round((score-reference)*100, 2) if reference is not None else None,
                        "status": status, "axes": list(axes),
                        "comparison_state": "matched_measurements" if usable else "unknown"})
        for axis in axes:
            target_score = max(.75, baseline.get(axis, 0))
            if quality[axis] >= target_score and axis not in decision.disagreement_axes:
                continue
            for target in (Rival.A.value, Rival.B.value):
                action = "produce a measured improvement" if target == forge.builder.value else "challenge the improvement with counterexamples and an alternative"
                improvements.append(Improvement(key, axis, target,
                    "critical" if key == "trust" else "high" if quality[axis] < .5 else "normal",
                    f"{action} for {axis}; target {target_score:.2f}; preserve every protected axis",
                    (decision.evidence_root,) + tuple(r.evidence_digest for r in usable)))
    if not allowed:
        for target in (Rival.A.value, Rival.B.value):
            improvements.append(Improvement("trust", "rights_provenance_safety", target,
                "critical", "resolve rights blockers with independent evidence; renaming or changing an era is not clearance",
                (rights.snapshot()["digest"],)))
    return SquareReview(candidate.digest, candidate.artifact.artifact_digest, workload_digest,
        decision.decision_digest, rights.snapshot()["digest"], knowledge_root,
        forge.completed_rounds, forge.effort_mode.rounds, tuple(squares), tuple(improvements),
        tuple(sorted(set(blockers))), tuple(r.evidence_digest for r in usable), legal_root, terminal)
