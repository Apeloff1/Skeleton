"""AiBuilderEngine: prompt -> routed plan -> forge data -> (optional) Godot build."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .clarify import clarifying_questions
from .forge_data import forge_plan_data
from .model_planner import ModelPlanner, PlanOutcome
from .receipts import PlanLedger


@dataclass(frozen=True)
class EngineResult:
    outcome: PlanOutcome
    provenance_hash: str
    questions: list[dict[str, str]]
    forge_data: Mapping[str, Any] | None = None
    build: Mapping[str, Any] | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        o = self.outcome
        return {
            "spec": dict(o.spec), "source": o.source, "fallback_reason": o.fallback_reason,
            "violations": list(o.violations), "receipt": o.receipt.as_dict(),
            "provenance_hash": self.provenance_hash, "questions": self.questions,
            "forge_data": self.forge_data, "build": self.build,
        }


class AiBuilderEngine:
    def __init__(self, planner: ModelPlanner, *, ledger: PlanLedger | None = None,
                 build_fn: Callable[..., Mapping[str, Any]] | None = None) -> None:
        self.planner = planner
        self.ledger = ledger if ledger is not None else PlanLedger()
        self._build_fn = build_fn

    async def plan(self, prompt: str, *, era: str = "", forge_target: str | None = "json") -> EngineResult:
        outcome = await self.planner.plan(prompt, era=era)
        h = self.ledger.record(outcome)
        data = forge_plan_data(outcome.spec, target=forge_target) if forge_target else None
        return EngineResult(outcome, h, clarifying_questions(outcome.brief, outcome.spec), data)

    async def build(self, prompt: str, *, era: str = "", **build_kwargs: Any) -> EngineResult:
        """Plan, then hand the committed spec to ``build_playable_game``.

        The committed spec reaches forge as a ``planner`` hook, so forge's own
        lock on genre/engine/brief/scope still applies.
        """
        planned = await self.plan(prompt, era=era, forge_target=None)
        build_fn = self._build_fn
        if build_fn is None:
            from skeleton.forge.game_builder import build_playable_game as build_fn  # heavy; lazy
        committed = dict(planned.outcome.spec)
        result = build_fn(planned.outcome.brief, era=era, planner=lambda _spec: committed, **build_kwargs)
        return EngineResult(planned.outcome, planned.provenance_hash, planned.questions, None, dict(result))

    def enqueue(self, outcome: PlanOutcome, **kwargs: Any):
        """Queue a ``game.build`` job for the planned brief via forge's build queue."""
        from skeleton.forge.game_build_queue import enqueue_game_build

        return enqueue_game_build({"brief": outcome.brief, "era": outcome.spec.get("era", "")}, **kwargs)
