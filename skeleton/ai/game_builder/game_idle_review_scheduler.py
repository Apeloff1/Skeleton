"""Opt-in cooperative idle-game reviewer qualification, not a background daemon.

The host owns consent, foreground activity signals and hardware pressure
telemetry. We never infer that a user is absent or activate model weights
because a system appears idle. A scheduled host call can collect the required
independent idle cohort; the evaluator retains all model-promotion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable

from .contracts import canonical_digest
from .game_model_promotion import PromotionError
from .game_reviewer_registry import ReviewerRegistry, ReviewPreempted
from .quest_scene_engine import DirectorWorld


@dataclass(frozen=True, slots=True)
class IdleEvaluationBudget:
    max_wall_seconds: int = 300
    max_worlds: int = 4

    def __post_init__(self):
        if (type(self.max_wall_seconds) is not int
                or not 5 <= self.max_wall_seconds <= 600
                or type(self.max_worlds) is not int
                or not 2 <= self.max_worlds <= 8):
            raise PromotionError("finite explicit consumer idle evaluation budget required")

    def payload(self):
        return dict(max_wall_seconds=self.max_wall_seconds,
                    max_worlds=self.max_worlds,
                    cooperative_preemption=True,
                    no_unbounded_worker_loops=True)


def qualify_when_idle(
    registry: ReviewerRegistry, worlds: tuple[DirectorWorld, ...], *,
    authorized: bool, consent: bool,
    host_is_idle: Callable[[], bool],
    hardware_is_safe: Callable[[], bool],
    budget: IdleEvaluationBudget = IdleEvaluationBudget(),
    quest_key: str = "quest_00",
    clock: Callable[[], float] = monotonic,
) -> dict:
    """Run one finite independent idle cohort or return an explicit deferral.

    Probe failures (exceptions, non-boolean results) fail closed. Cooperative
    checks occur before and between gameplay personas and fault mutations;
    this is NOT a hard real-time OS preemption guarantee. No writes occur if
    the host withdraws consent or reports activity before model publication.
    """
    if authorized is not True or consent is not True:
        raise PermissionError("explicit host and operator authority are mandatory")
    if not isinstance(registry, ReviewerRegistry):
        raise PromotionError("canonical local model registry is required")
    if not isinstance(budget, IdleEvaluationBudget):
        raise PromotionError("typed finite idle execution budget required")
    if (type(worlds) is not tuple or not 2 <= len(worlds) <= budget.max_worlds
            or any(not isinstance(w, DirectorWorld) for w in worlds)
            or len({w.digest for w in worlds}) != len(worlds)):
        raise PromotionError("bounded distinct actual original worlds required")
    if not all(callable(x) for x in (host_is_idle, hardware_is_safe, clock)):
        raise PromotionError("explicit live host activity, hardware, clock probes required")

    registry.read_state()
    budget_digest=canonical_digest(budget.payload())
    cohort_identity=canonical_digest([w.digest for w in worlds])
    started=clock()
    if type(started) not in (int,float) or not -1e30 < started < 1e30:
        raise PromotionError("finite monotonic runtime budget start required")
    deadline=started+budget.max_wall_seconds

    def observe_guards():
        idle=host_is_idle()
        safe=hardware_is_safe()
        now=clock()
        if (type(idle) is not bool or type(safe) is not bool
                or type(now) not in (int,float) or not -1e30 < now < 1e30):
            raise PromotionError("hardware and foreground telemetry must be fresh and typed")
        return idle, safe, now

    idle,safe,now=observe_guards()
    if not idle or not safe or now>=deadline:
        return dict(schema="skeleton.game_builder.idle_review_dispatch.v1",
                    status="deferred",mode="idle",
                    reason="foreground_or_hardware_guard",
                    source_cohort_digest=cohort_identity,
                    budget_digest=budget_digest,
                    model_state_mutated=False,
                    new_weights_installed=False)

    def should_preempt():
        still_idle,still_safe,current=observe_guards()
        return not still_idle or not still_safe or current>=deadline

    try:
        result=registry.observe(worlds,mode="idle",authorized=True,
                                quest_key=quest_key,preempt_check=should_preempt)
    except ReviewPreempted:
        return dict(schema="skeleton.game_builder.idle_review_dispatch.v1",
                    status="deferred",mode="idle",
                    reason="preempted_before_publishing",
                    source_cohort_digest=cohort_identity,
                    budget_digest=budget_digest,
                    model_state_mutated=False,
                    new_weights_installed=False)
    return dict(schema="skeleton.game_builder.idle_review_dispatch.v1",
                status=result["status"],mode="idle",
                source_cohort_digest=cohort_identity,
                budget_digest=budget_digest,
                evaluation=result,
                model_weights_updated=False,
                automatic_promotion_performed=False)


__all__ = ["IdleEvaluationBudget", "qualify_when_idle"]
