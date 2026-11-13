"""AI builder engine: model-routed prompt -> plan -> forge data.

The model only proposes. ``compile_brief`` stays the commit authority, every
provider call is gated by capsec, and every plan carries a b038 provenance
record. Forge's existing materialise/verify path and ``build_playable_game``
do the rest; this package adds no second materialise path.
"""
from __future__ import annotations

from .clarify import clarifying_questions
from .engine import AiBuilderEngine, EngineResult
from .forge_data import forge_plan_data
from .hooks import router_planner_hook
from .model_planner import ModelPlanner, PlanOutcome, grant_providers
from .plan_guard import guard_proposal
from .plan_schema import MUTABLE_FIELDS, PLAN_SCHEMA, parse_model_plan
from .prompt_normalizer import normalize_prompt
from .receipts import PlanLedger, plan_provenance

__all__ = [
    "AiBuilderEngine", "EngineResult", "MUTABLE_FIELDS", "ModelPlanner", "PLAN_SCHEMA",
    "PlanLedger", "PlanOutcome", "clarifying_questions", "forge_plan_data", "grant_providers",
    "guard_proposal", "normalize_prompt", "parse_model_plan", "plan_provenance",
    "router_planner_hook",
]
