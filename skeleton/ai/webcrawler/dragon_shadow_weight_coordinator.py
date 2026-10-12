"""Bounded trusted-worker orchestration of Dragon acquisition into sparse weights.

The idle planner cannot fetch, and this coordinator never fetches either. A
canonical worker supplies independently reviewed acquisition receipts and
pinned holdout tests. The coordinator stages/benchmarks them automatically,
and activates only when the existing human-approval ledger has authorized a
fully verified memory promotion for that exact knowledge identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from .dragon_adversarial_review_worker import AdversarialReviewOutput
from .dragon_analysis_chains import LayerReceipt
from .dragon_knowledge_normalization_worker import NormalizedKnowledge
from .dragon_memory_promotion_worker import MemoryPromotionOutput
from .dragon_nest_progression import _id, _iso
from .dragon_nest_research_scheduler import IdleResearchPlan
from .dragon_resource_session import HardwareSample
from .dragon_shadow_weight_automation import (
    ShadowWeightAutomation, BenchmarkCase,
)


@dataclass(frozen=True)
class ReviewedAcquisition:
    source_id: str
    note_id: str
    search_query: str
    normalized_knowledge_id: str
    normalized_records: tuple[NormalizedKnowledge, ...]
    analysis_receipts: tuple[LayerReceipt, ...]
    adversarial_output: AdversarialReviewOutput
    benchmark: tuple[BenchmarkCase, ...] = ()
    promoted_memory: MemoryPromotionOutput | None = None
    human_review_id: str = ""

    def __post_init__(self) -> None:
        _id(self.source_id)
        _id(self.note_id)
        if (not isinstance(self.search_query, str)
                or not 1 <= len(self.search_query) <= 300):
            raise ValueError("bounded reviewed topic required")


@dataclass(frozen=True)
class ShadowAutomationItem:
    source_id: str
    note_id: str
    state: str
    reason: str
    candidate_id: str = ""


@dataclass(frozen=True)
class ShadowAutomationReport:
    schema: str
    owner: str
    at: str
    items: tuple[ShadowAutomationItem, ...]
    staged: int
    benchmarked: int
    activated: int
    deferred: int
    # This report cannot grant provider/network work or neural fine-tuning.
    execution_authorized: bool = False
    neural_training_authorized: bool = False


def run_shadow_automation(
    automation: ShadowWeightAutomation, library: ReviewedKnowledgeStore,
    plan: IdleResearchPlan, reviewed: tuple[ReviewedAcquisition, ...],
    *, now: str, idle_since: str, hardware: HardwareSample,
    hardware_now: float, consented: bool, authorized: bool,
    privacy_clear: bool, max_candidates: int = 6,
) -> ShadowAutomationReport:
    """One finite iteration, never an unbounded daemon or invisible background job."""
    if authorized is not True:
        raise PermissionError("authenticated acquisition worker required")
    if (not isinstance(automation, ShadowWeightAutomation)
            or not isinstance(library, ReviewedKnowledgeStore)
            or not isinstance(plan, IdleResearchPlan)
            or not plan.requires_worker_admission
            or plan.execution_authorized or plan.memory_promotion_authorized
            or not isinstance(reviewed, tuple)
            or len(reviewed) > 64
            or any(not isinstance(x, ReviewedAcquisition) for x in reviewed)
            or type(max_candidates) is not int or not 1 <= max_candidates <= 24):
        raise ValueError("bounded planner/canonical-worker handoff required")
    if _iso(now) != _iso(plan.at):
        raise ValueError("plan must bind the exact trusted execution clock")
    _id(plan.owner)
    # Assignment IDs originate from the idle fairness planner, while receipts
    # must originate from the independent canonical reviewed knowledge store.
    admitted_sources = {x.source_id for x in plan.assignments}
    if len(admitted_sources) != len(plan.assignments):
        raise ValueError("one source must not consume multiple specialist slots")
    if len({(x.source_id, x.note_id) for x in reviewed}) != len(reviewed):
        raise ValueError("duplicate reviewed acquisitions cannot multiply work")
    if any(x.source_id not in admitted_sources for x in reviewed):
        raise PermissionError("unscheduled source cannot consume background resources")
    if len(reviewed) > max_candidates:
        raise ValueError("batch exceeds bounded inference/work budget")
    items = []
    staged = evaluated = activated = 0
    for candidate in reviewed:
        try:
            brief = library.build_brief(
                plan.owner, candidate.search_query, authorized=True,
                max_hits=32, min_independent_groups=2,
            )
            shadow = automation.stage_shadow(
                plan.owner, brief, candidate.source_id, candidate.note_id,
                normalized_knowledge_id=candidate.normalized_knowledge_id,
                normalized_records=candidate.normalized_records,
                receipts=candidate.analysis_receipts,
                adversarial_output=candidate.adversarial_output,
                at=now, idle_since=idle_since, hardware=hardware,
                hardware_now=hardware_now, consented=consented,
                authorized=True, privacy_clear=privacy_clear,
            )
            staged += 1
            if not candidate.benchmark:
                items.append(ShadowAutomationItem(
                    candidate.source_id, candidate.note_id, "shadow",
                    "awaiting_independent_holdout", shadow.candidate_id,
                ))
                continue
            result = automation.evaluate(
                plan.owner, shadow.candidate_id, candidate.benchmark,
                at=now, authorized=True,
            )
            if not result.accepted:
                items.append(ShadowAutomationItem(
                    candidate.source_id, candidate.note_id, "shadow",
                    "benchmark_no_improvement_or_regression", shadow.candidate_id,
                ))
                continue
            evaluated += 1
            if candidate.promoted_memory is None or not candidate.human_review_id:
                items.append(ShadowAutomationItem(
                    candidate.source_id, candidate.note_id, "tested",
                    "awaiting_independent_human_promotion", shadow.candidate_id,
                ))
                continue
            automation.promote(
                plan.owner, shadow.candidate_id, candidate.benchmark,
                memory_promotion=candidate.promoted_memory,
                review_id=candidate.human_review_id, at=now, authorized=True,
            )
            activated += 1
            items.append(ShadowAutomationItem(
                candidate.source_id, candidate.note_id, "active",
                "approved_usefulness_verified", shadow.candidate_id,
            ))
        except (ValueError, PermissionError, LookupError) as exc:
            # Failure of one candidate must not turn a later candidate into an
            # implicit approval. Expose a fixed reason, not untrusted text.
            items.append(ShadowAutomationItem(
                candidate.source_id, candidate.note_id, "deferred",
                type(exc).__name__.lower(),
            ))
    return ShadowAutomationReport(
        "skeleton.dragon.shadow_automation_report.v1", plan.owner, _iso(now),
        tuple(items), staged, evaluated, activated,
        sum(x.state == "deferred" for x in items),
    )
