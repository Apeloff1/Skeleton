"""GamePlan validation and scoring: schema, references, playability, verdict.

Problems reuse forge's ``ValidationProblem``/``Severity`` (skeleton.forge.validator).
Nothing here runs unless a caller opts in.
"""
from __future__ import annotations

from .engine_ext import ValidatingEngine
from .playability import (check_cycles, check_reachability, check_winnable, dead_end_states, exit_graph,
                          one_way_exits)
from .qa_hook import plan_qa_hook
from .references import check_references
from .schema import GAME_PLAN_SCHEMA, check_schema
from .scoring import Thresholds, Verdict, score_plan, validate_plan

__all__ = [
    "GAME_PLAN_SCHEMA", "Thresholds", "ValidatingEngine", "Verdict", "check_cycles",
    "check_reachability", "check_references", "check_schema", "check_winnable", "dead_end_states",
    "exit_graph", "one_way_exits",
    "plan_qa_hook", "score_plan", "validate_plan",
]
