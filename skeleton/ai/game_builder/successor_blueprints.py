"""Original-design stepping stones with separate parent/child review gates.

Changing a genre or setting is a creative constraint, not an infringement
avoidance formula. No source expression is transformed or copied here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import canonical_digest
from .dragon_porting import JurisdictionReview, legal_release_blockers
from .game_research_foundation import bounded
from .reviewed_knowledge import _id, _text, _digest
from .rights import RightsLedger, RightsState, UseKind


CREATIVE_AXES = ("era", "genre", "story", "visual_style", "time_setting", "gameplay")
ORIGINALITY_AREAS = ("characters", "plot_structure", "dialogue", "visuals", "music",
                    "level_layouts", "code", "branding", "mechanic_patent_claims")


@dataclass(frozen=True, slots=True)
class SuccessorBlueprint:
    project_id: str
    title: str
    era: str
    genre: str
    story: str
    visual_style: str
    time_setting: str
    gameplay: str
    original_assets_plan: str
    independent_code_plan: str
    authorship_evidence_digest: str
    research_source_ids: tuple[str, ...]
    parent_digest: str | None = None

    def __post_init__(self):
        _id(self.project_id, "project")
        for k in ("title", *CREATIVE_AXES, "original_assets_plan", "independent_code_plan"):
            _text(getattr(self, k), k, 4000 if k == "story" else 1024)
        _digest(self.authorship_evidence_digest, "authorship evidence")
        if self.parent_digest is not None:
            _digest(self.parent_digest, "parent digest")
        if (not isinstance(self.research_source_ids, tuple) or not 2 <= len(self.research_source_ids) <= 32
                or len(set(self.research_source_ids)) != len(self.research_source_ids)):
            raise ValueError("two or more distinct research references required")
        for sid in self.research_source_ids:
            _id(sid, "source id")

    @property
    def digest(self):
        payload = asdict(self)
        payload["research_source_ids"] = sorted(self.research_source_ids)
        return canonical_digest(payload)


@dataclass(frozen=True, slots=True)
class OriginalityReview:
    artifact_digest: str
    area: str
    reviewer_id: str
    evidence_digest: str
    disposition: str
    checked_at: int
    expires_at: int

    def __post_init__(self):
        from .reviewed_knowledge import _integer
        _digest(self.artifact_digest, "artifact digest")
        _digest(self.evidence_digest, "review evidence")
        _id(self.reviewer_id, "reviewer")
        if self.area not in ORIGINALITY_AREAS or self.disposition not in {"cleared", "blocked", "needs_review"}:
            raise ValueError("explicit originality review disposition required")
        _integer(self.checked_at, "review time", 0, 10**12)
        _integer(self.expires_at, "expiry", self.checked_at+1, 10**12)


def plan_successor_pipeline(base: SuccessorBlueprint, product: SuccessorBlueprint,
                           rights: RightsLedger, *, target_id: str,
                           jurisdictions: Iterable[str], legal_reviews: Iterable[JurisdictionReview],
                           originality_reviews: Iterable[OriginalityReview], now: int,
                           authorized: bool) -> dict:
    """Compose first/second/roof dossiers; do not inherit legal clearance.

    Two research IDs alone are not proof of independent factual support. That
    is required upstream by empirical promotion. Here all source use remains
    reference-only and every artifact gets its own existing legal gate.
    """
    if authorized is not True:
        raise PermissionError("authenticated design review required")
    if not isinstance(base, SuccessorBlueprint) or not isinstance(product, SuccessorBlueprint) or not isinstance(rights, RightsLedger):
        raise ValueError("typed original blueprints and canonical rights required")
    if base.parent_digest is not None or product.parent_digest != base.digest or base.project_id == product.project_id:
        raise ValueError("roof must bind one distinct reviewed stepping-stone project")
    changed = [axis for axis in CREATIVE_AXES if getattr(base, axis).casefold().strip() != getattr(product, axis).casefold().strip()]
    regions = bounded(jurisdictions, 32, str)
    legal = bounded(legal_reviews, 896, JurisdictionReview)
    originality = bounded(originality_reviews, 2*len(ORIGINALITY_AREAS), OriginalityReview)
    identities = {base.digest, product.digest}
    if any(r.artifact_digest not in identities for r in (*legal, *originality)):
        raise ValueError("review for unrelated artifact")
    if len({(r.artifact_digest, r.area) for r in originality}) != len(originality):
        raise ValueError("duplicate originality review")
    artifacts = []
    for blueprint in (base, product):
        blockers = list(legal_release_blockers(artifact_digest=blueprint.digest,
            target_id=target_id, jurisdictions=regions,
            reviews=tuple(r for r in legal if r.artifact_digest == blueprint.digest), now=now))
        source_bindings = []
        for sid in sorted(blueprint.research_source_ids):
            source = rights.source(sid)
            if (source.rights_state in {RightsState.UNKNOWN_QUARANTINE, RightsState.FORBIDDEN}
                    or (source.rights_state not in {RightsState.FACTS_IDEAS_REFERENCE_ONLY, RightsState.RESTRICTED_REFERENCE_ONLY}
                        and UseKind.FACTS_IDEAS_REFERENCE not in source.allowed_uses)):
                blockers.append(sid + ": research reference permission missing")
            source_bindings.append({"source_id": sid, "rights_binding": source.rights_binding_digest})
        for area in ORIGINALITY_AREAS:
            review = next((r for r in originality if r.artifact_digest == blueprint.digest and r.area == area), None)
            if (review is None or not review.checked_at <= now < review.expires_at
                    or review.disposition != "cleared" or review.reviewer_id == blueprint.project_id):
                blockers.append("originality/" + area + ": current independent clearance required")
        if blueprint is product and len(changed) < len(CREATIVE_AXES):
            blockers.append("roof creative specification must change every requested axis")
        if rights.unresolved_high_risk(artifact_digest=blueprint.digest):
            blockers.append("canonical rights ledger has unresolved high-risk similarity")
        artifacts.append({"floor": "second" if blueprint is base else "roof",
            "blueprint": asdict(blueprint), "artifact_digest": blueprint.digest,
            "source_bindings": source_bindings, "review_blockers": sorted(blockers),
            "review_ready": not blockers, "build_state": "not_built", "release_authority": False})
    body = {"schema": "skeleton.game_builder.successor_pipeline.v1", "checked_at": now,
            "target_id": target_id, "jurisdictions": sorted(regions),
            "changed_creative_axes": changed, "projects": artifacts,
            "legal_review_evidence": [r.evidence_digest for r in sorted(legal, key=lambda r: (r.artifact_digest, r.jurisdiction, r.area))],
            "originality_review_evidence": [asdict(r) for r in sorted(originality, key=lambda r: (r.artifact_digest, r.area))],
            "foundation": "reviewed_abstract_reference_only",
            "pipeline_review_ready": all(a["review_ready"] for a in artifacts),
            "release_authority": False,
            "claim_boundary": "independent authorship and artifact-specific review; no formula guarantees non-infringement"}
    return {**body, "pipeline_digest": canonical_digest(body)}
