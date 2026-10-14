"""Mother Dragon's reviewed-insight gate before the shadow-weight coordinator.

The mother does not turn inferred subtext into model facts. Instead, verified
cross-source hypotheses prioritize which child acquisitions deserve expensive
shadow-weight scrutiny and holdout evaluation. All existing calibrated
normalization, adversarial replay, signed holdout and human-review gates remain.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from .dragon_mother_glean_ledger import MotherGleanLedger
from .dragon_mother_glean_matrix import HatchlingReceipt, MotherGleanReport
from .dragon_nest_progression import DragonNest, _iso
from .dragon_nest_research_scheduler import IdleResearchPlan
from .dragon_resource_session import HardwareSample
from .dragon_shadow_weight_automation import ShadowWeightAutomation
from .dragon_shadow_weight_coordinator import (
    ReviewedAcquisition, ShadowAutomationReport, run_shadow_automation,
)


@dataclass(frozen=True)
class MotherGleanHandoff:
    mother: MotherGleanReport
    shadow: ShadowAutomationReport | None
    insight_priority: tuple[str, ...]
    deferred_sources: tuple[str, ...]
    research_queries: tuple[str, ...]
    neural_training_authorized: bool = False


def run_mother_to_shadow(
    ledger: MotherGleanLedger,
    automation: ShadowWeightAutomation,
    library: ReviewedKnowledgeStore,
    nest: DragonNest,
    plan: IdleResearchPlan,
    reviewed: tuple[ReviewedAcquisition, ...],
    acquisitions: tuple[HatchlingReceipt, ...], *,
    now: str, idle_since: str,
    hardware: HardwareSample, hardware_now: float,
    consented: bool, background_allowed: bool,
    owner_authorized: bool, privacy_clear: bool,
) -> MotherGleanHandoff:
    """Bounded, explicit iteration; does not schedule an OS background job."""
    if owner_authorized is not True:
        raise PermissionError("mother worker requires owner authorization")
    if (not isinstance(plan, IdleResearchPlan)
            or not isinstance(reviewed, tuple)
            or not isinstance(acquisitions, tuple)
            or len(reviewed) > 6
            or len(acquisitions) != len(reviewed)
            or not isinstance(nest, DragonNest)
            or nest.owner != plan.owner
            or _iso(now) != _iso(plan.at)):
        raise ValueError("same-owner, same-time idle research lineage required")
    assignments = {(x.lane, x.source_id) for x in plan.assignments}
    pairs = {(a.lane, a.source_id) for a in acquisitions}
    if (len(pairs) != len(acquisitions)
            or not pairs.issubset(assignments)
            or {a.source_id for a in acquisitions} != {r.source_id for r in reviewed}
            or len({(r.source_id, r.note_id) for r in reviewed}) != len(reviewed)
            or not all(any(a.source_id == r.source_id and a.note_id == r.note_id
                           for a in acquisitions) for r in reviewed)):
        raise ValueError("every shadow candidate must come from its actual scheduled hatchling")
    report = ledger.run(
        library, nest, acquisitions, at=now, idle_since=idle_since,
        owner_authorized=True, consented=consented,
        background_allowed=background_allowed,
    )
    significant = {
        (h.lane, h.source_id, h.note_id)
        for h in report.hypotheses
        if h.status == "shadow_hypothesis" and h.independent_groups >= 2
    }
    eligible = tuple(
        r for r in reviewed
        if any(a.source_id == r.source_id and a.note_id == r.note_id
               and (a.lane, a.source_id, a.note_id) in significant
               for a in acquisitions)
    )
    deferred = tuple(sorted(set(r.source_id for r in reviewed)
                            - set(r.source_id for r in eligible)))
    # The only path to active routing is the existing independent authorization
    # and signed usefulness validation. No glean report carries approval flags.
    shadow_report = (
        run_shadow_automation(
            automation, library, plan, eligible,
            now=now, idle_since=idle_since, hardware=hardware,
            hardware_now=hardware_now, consented=consented,
            authorized=True, privacy_clear=privacy_clear,
        ) if eligible else None
    )
    return MotherGleanHandoff(
        report, shadow_report, tuple(sorted(r.source_id for r in eligible)),
        deferred, report.research_gaps,
    )
