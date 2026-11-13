"""Instruction + plan -> PlanDiff via the same capsec-gated ExecutingModelRouter
the ModelPlanner uses; deterministic rules are the fallback."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.frontier.runtime.model_router_contract import CallBudget, RouteStatus, RoutingReceipt
from skeleton.frontier.runtime.model_routing import ModelRouteRequest, RouteBudget
from skeleton.frontier.runtime.model_runtime import ModelMessage

from ..model_planner import ModelPlanner, _compiler_receipt, _response_payload
from ..prompt_normalizer import normalize_prompt
from .diff import DiffError, PlanDiff
from .rules import rule_based_diff

TASK_TYPE = "forge.plan_edit"
EDIT_SCHEMA = "skeleton.forge.ai_builder.plan_edit.v1"
_SYSTEM = (
    f"You edit a GamePlan. Reply JSON only: {{\"schema\": {EDIT_SCHEMA!r}, \"ops\": [{{\"op\": "
    "\"add\"|\"remove\"|\"change\", \"path\": [...], \"value\": ...}]}. Paths select list items by id."
)
RESPONSE_SCHEMA = {"type": "object", "required": ["ops"],
                   "properties": {"schema": {"const": EDIT_SCHEMA}, "ops": {"type": "array"}}}


@dataclass(frozen=True)
class EditProposal:
    instruction: str
    diff: PlanDiff | None
    source: str  # "model" | "rules" | "none"
    receipt: RoutingReceipt
    fallback_reason: str | None = None


def _parse(raw: Any) -> PlanDiff:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw.strip().strip("`").removeprefix("json"))
        except json.JSONDecodeError as exc:
            raise DiffError(f"not json: {exc.msg}") from exc
    if isinstance(raw, Mapping) and raw.get("schema", EDIT_SCHEMA) != EDIT_SCHEMA:
        raise DiffError("wrong edit schema")
    return PlanDiff.from_obj(raw)


class EditPlanner:
    def __init__(self, router: Any, *, gate: Any, cap: str | None, budget: CallBudget | None = None,
                 max_output_tokens: int = 1200) -> None:
        if gate is None:
            raise ValueError("a capsec gate is required")
        self._router, self._gate, self._cap, self._budget = router, gate, cap, budget
        self._max_out = max_output_tokens

    @classmethod
    def from_planner(cls, planner: ModelPlanner, **kw: Any) -> "EditPlanner":
        """Share the ModelPlanner's router, gate and capability token."""
        return cls(planner._router, gate=planner._gate, cap=planner._cap, budget=planner._budget, **kw)

    async def propose(self, instruction: str, plan: Mapping[str, Any], *,
                      request_id: str | None = None) -> EditProposal:
        text = normalize_prompt(instruction)
        rid = request_id or f"aie-{uuid.uuid4().hex[:12]}"

        def fallback(receipt: RoutingReceipt, reason: str) -> EditProposal:
            d = rule_based_diff(text, plan)
            return EditProposal(text, d, "rules" if d else "none", receipt, reason)

        req = ModelRouteRequest(
            request_id=rid,
            messages=(ModelMessage("system", _SYSTEM),
                      ModelMessage("user", json.dumps({"instruction": text, "plan": plan}, sort_keys=True,
                                                      default=str))),
            required_capabilities=frozenset({"chat"}), response_schema=RESPONSE_SCHEMA,
            max_output_tokens=self._max_out, budget=RouteBudget(max_output_tokens=self._max_out),
            metadata={"task": TASK_TYPE})
        try:
            call = await self._router.execute(req, gate=self._gate, cap=self._cap, task_type=TASK_TYPE,
                                              budget=self._budget)
        except Exception as exc:
            return fallback(_compiler_receipt(rid, RouteStatus.FAILED, f"error:{type(exc).__name__}"),
                            f"router_error:{type(exc).__name__}")
        if call.receipt.status != RouteStatus.OK:
            return fallback(call.receipt, f"route:{call.receipt.status}")
        try:
            return EditProposal(text, _parse(_response_payload(call.result)), "model", call.receipt)
        except DiffError as exc:
            return fallback(call.receipt, f"parse:{exc}")
