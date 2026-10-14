"""Capability-aware original homebrew port plans using Dragon's real catalog.

A plan is not an emitter or compiled artifact. Native support and target style
are reported from the existing source emitters, never from the platform name.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import EvaluatorProvenance, canonical_digest
from ..webcrawler.dragon_native_targets import demand_target, target_catalog


REVIEW_AREAS = frozenset({"copyright", "trademark", "patent", "sdk_license",
    "distribution", "anti_circumvention", "privacy", "moral_rights", "publicity",
    "database_rights", "consumer_protection", "age_ratings", "accessibility",
    "open_source_obligations"})
DESKTOP = frozenset({"pc_linux", "pc_windows", "pc_macos", "steam_deck"})


@dataclass(frozen=True, slots=True)
class JurisdictionReview:
    artifact_digest: str
    target_id: str
    jurisdiction: str
    area: str
    disposition: str
    checked_at: int
    expires_at: int
    evidence_digest: str
    authority: EvaluatorProvenance

    def __post_init__(self) -> None:
        demand_target(self.target_id)
        if self.area not in REVIEW_AREAS or self.disposition not in {"cleared", "blocked", "needs_review"}:
            raise ValueError("known legal area and explicit disposition required")
        if not isinstance(self.jurisdiction, str) or not self.jurisdiction.strip() or len(self.jurisdiction) > 64:
            raise ValueError("explicit release jurisdiction required")
        if type(self.checked_at) is not int or type(self.expires_at) is not int or not 0 <= self.checked_at < self.expires_at:
            raise ValueError("finite review validity interval required")
        for value in (self.artifact_digest, self.evidence_digest):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("exact legal-review artifact and evidence identities required")
        if not isinstance(self.authority, EvaluatorProvenance) or self.authority.authority_kind != "deterministic_control" or self.authority.method_id != "human-legal-review" or self.evidence_digest not in self.authority.output_evidence_refs:
            raise ValueError("legal disposition requires human-review output evidence")


def legal_release_blockers(*, artifact_digest: str, target_id: str,
                           jurisdictions: Iterable[str], reviews: Iterable[JurisdictionReview],
                           now: int) -> tuple[str, ...]:
    demand_target(target_id)
    regions = tuple(jurisdictions)
    if not 1 <= len(regions) <= 32 or len(regions) != len(set(regions)) or any(not isinstance(r, str) or not r.strip() or len(r) > 64 for r in regions):
        raise ValueError("unique nonempty release jurisdiction set required")
    if type(now) is not int or now < 0:
        raise ValueError("explicit release review time required")
    rows = tuple(reviews)
    if len(rows) > 32*len(REVIEW_AREAS) or any(not isinstance(r, JurisdictionReview) for r in rows):
        raise ValueError("bounded typed legal reviews required")
    indexed = {}
    for row in rows:
        if row.artifact_digest != artifact_digest or row.target_id != target_id:
            raise ValueError("legal review belongs to another artifact or target")
        key = (row.jurisdiction, row.area)
        if key in indexed:
            raise ValueError("conflicting or duplicate legal review cells")
        indexed[key] = row
    blockers = []
    for region in sorted(regions):
        for area in sorted(REVIEW_AREAS):
            row = indexed.get((region, area))
            if row is None:
                blockers.append(f"{region}/{area}: missing review")
            elif not row.checked_at <= now < row.expires_at:
                blockers.append(f"{region}/{area}: stale or future review")
            elif row.disposition != "cleared":
                blockers.append(f"{region}/{area}: {row.disposition}")
    return tuple(blockers)


@dataclass(frozen=True, slots=True)
class MechanicInfusion:
    mechanic_id: str
    abstract_rule: str
    source_reference_id: str
    independent_design_digest: str
    historical_cost_bytes: int
    desktop_enhancement: str

    def __post_init__(self) -> None:
        for value in (self.mechanic_id, self.abstract_rule, self.source_reference_id, self.desktop_enhancement):
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                raise ValueError("bounded abstract mechanic and original enhancement required")
        if type(self.historical_cost_bytes) is not int or not 0 <= self.historical_cost_bytes <= 100_000_000:
            raise ValueError("bounded historical memory estimate required")
        value = self.independent_design_digest
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("independent mechanic design identity required")


def plan_homebrew_port(*, source_target: str, destination_target: str, style: str,
                       mechanics: Iterable[MechanicInfusion], preserve: Iterable[str],
                       memory_budget_bytes: int, artifact_digest: str,
                       jurisdictions: Iterable[str], reviews: Iterable[JurisdictionReview],
                       now: int) -> dict:
    source = demand_target(source_target)
    destination = demand_target(destination_target)
    rows = tuple(mechanics)
    if not 1 <= len(rows) <= 64 or any(not isinstance(r, MechanicInfusion) for r in rows) or len({r.mechanic_id for r in rows}) != len(rows):
        raise ValueError("bounded unique typed mechanic set required")
    anchors = tuple(preserve)
    if not anchors or len(anchors) > 32 or any(not isinstance(x, str) or not x.strip() or len(x) > 256 for x in anchors):
        raise ValueError("explicit style-preservation anchors required")
    if type(memory_budget_bytes) is not int or not 1 <= memory_budget_bytes <= 100_000_000:
        raise ValueError("explicit historical resource budget required")
    profile = next(r for r in target_catalog() if r["id"] == destination.id)
    supported = profile["status"] == "native_source" and style in profile["supported_styles"]
    historical_cost = sum(r.historical_cost_bytes for r in rows)
    blockers = list(legal_release_blockers(artifact_digest=artifact_digest,
        target_id=destination.id, jurisdictions=jurisdictions, reviews=reviews, now=now))
    if not supported:
        blockers.append("destination/style has no implemented native source emitter")
    if historical_cost > memory_budget_bytes and destination.id not in DESKTOP:
        blockers.append("historical memory budget exceeded; reduce or redesign mechanics")
    if destination.status == "licensed_sdk":
        blockers.append("licensed SDK and authorized partner distribution required")
    body = {
        "schema": "skeleton.dragon.homebrew_port_plan.v1", "artifact_digest": artifact_digest,
        "source_target": source.id, "destination_target": destination.id, "style": style,
        "preservation_anchors": list(anchors), "historical_cost_bytes": historical_cost,
        "historical_budget_bytes": memory_budget_bytes,
        "source_emitter_available": supported, "build_state": "not_built", "gameplay_state": "not_verified",
        "mechanics": [{"id": r.mechanic_id, "abstract_rule": r.abstract_rule,
            "reference_id": r.source_reference_id, "independent_design_digest": r.independent_design_digest,
            "implementation_goal": r.desktop_enhancement if destination.id in DESKTOP else r.abstract_rule,
            "implementation_state": "design_only"} for r in rows],
        "release_blockers": sorted(blockers), "release_authority": False,
        "claim_boundary": "original homebrew design plan; no commercial ROM, BIOS, key or proprietary SDK reuse",
    }
    return {**body, "plan_digest": canonical_digest(body)}
