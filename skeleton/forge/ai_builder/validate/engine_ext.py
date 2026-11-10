"""Opt-in validation on top of AiBuilderEngine; defaults are unchanged."""
from __future__ import annotations

from typing import Any, Mapping

from ..engine import AiBuilderEngine, EngineResult
from .qa_hook import plan_qa_hook
from .scoring import Thresholds, Verdict, score_plan


class ValidatingEngine(AiBuilderEngine):
    """``validate=False`` (default) behaves exactly like AiBuilderEngine."""

    def __init__(self, *args: Any, validate: bool = False, thresholds: Thresholds = Thresholds(), **kw: Any):
        super().__init__(*args, **kw)
        self.validate = validate
        self.thresholds = thresholds

    def score(self, plan: Mapping[str, Any]) -> Verdict:
        return score_plan(plan, self.thresholds)

    async def build(self, prompt: str, *, era: str = "", **build_kwargs: Any) -> EngineResult:
        if self.validate and "qa" not in build_kwargs:
            build_kwargs["qa"] = plan_qa_hook(thresholds=self.thresholds)
        return await super().build(prompt, era=era, **build_kwargs)
