"""Prompt -> plan through an ExecutingModelRouter, under a real capsec gate.

Deny by default: the planner only holds a token minted for
``Capability("provider.<id>", "call")`` per provider it was granted. The
router checks every candidate with ``gate.check(cap, provider_action(id))``.
Any non-OK route, unusable output, or exception falls back to
``compile_brief``; a receipt is always returned.
"""
from __future__ import annotations

import time
import uuid
import re
from itertools import islice
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.forge.game_design_spec import compile_brief
from skeleton.frontier.runtime.model_router_contract import (
    CallBudget,
    ExecutingModelRouter,
    RouteStatus,
    RoutingReceipt,
)
from skeleton.frontier.runtime.model_routing import ModelRouteRequest, RouteBudget
from skeleton.frontier.runtime.model_runtime import ModelMessage
from skeleton.kernel.capsec import Capability, TokenIssuer

from .plan_guard import guard_proposal
from .plan_schema import PLAN_SCHEMA, RESPONSE_SCHEMA, PlanParseError, parse_model_plan
from .prompt_normalizer import normalize_prompt

TASK_TYPE = "forge.plan"
_SYSTEM = (
    "You refine a compiled game design spec. Reply with JSON only, schema "
    f"{PLAN_SCHEMA!r}, keys title, fantasy, core_loop, systems. Do not change genre, "
    "engine, scope or brief. systems may only reorder or drop the given systems."
)


def grant_providers(issuer: TokenIssuer, provider_ids: Iterable[str], *, subject: str = "forge.ai_builder") -> str:
    """Mint a token covering exactly ``provider.<id>``/``call`` for each id."""
    selected = tuple(islice(iter(provider_ids), 65))
    if (not selected or len(selected) > 64 or
            any(type(pid) is not str or
                re.fullmatch(r"[A-Za-z0-9_-]{1,96}", pid) is None for pid in selected)):
        raise ValueError("grant 1..64 bounded provider identifiers")
    caps = [Capability(f"provider.{pid}", "call") for pid in dict.fromkeys(selected)]
    return issuer.mint(subject, caps)


@dataclass(frozen=True)
class PlanOutcome:
    brief: str
    compiled: Mapping[str, Any]
    spec: Mapping[str, Any]
    source: str  # "model" | "compiler"
    receipt: RoutingReceipt
    violations: tuple[str, ...] = ()
    fallback_reason: str | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def used_model(self) -> bool:
        return self.source == "model"


def _compiler_receipt(request_id: str, status: str, reason: str) -> RoutingReceipt:
    """Receipt for a plan that never reached a provider (router raised)."""
    return RoutingReceipt(
        request_id=request_id, task_type=TASK_TYPE, backend="forge.ai_builder.compiler",
        status=status, selected_provider_id=None, fallback_chain=(),
        rejected={"router": (reason,)}, budget=CallBudget(), decided_at=time.time(),
    )


def _response_payload(result: Any) -> Any:
    response = getattr(result, "response", None)
    if response is None:
        return None
    structured = getattr(response, "structured", None)
    return dict(structured) if structured else getattr(response, "text", None)


class ModelPlanner:
    def __init__(self, router: ExecutingModelRouter, *, gate: Any, cap: str | None,
                 budget: CallBudget | None = None, max_output_tokens: int = 800) -> None:
        if gate is None:
            raise ValueError("a capsec gate is required")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 8192:
            raise ValueError("bounded model planner output budget required")
        self._router = router
        self._gate = gate
        self._cap = cap
        self._budget = budget
        self._max_out = max_output_tokens

    def _request(self, compiled: Mapping[str, Any], request_id: str) -> ModelRouteRequest:
        import json

        view = {k: compiled[k] for k in ("title", "genre", "fantasy", "core_loop", "scope", "systems")}
        return ModelRouteRequest(
            request_id=request_id,
            messages=(ModelMessage("system", _SYSTEM),
                      ModelMessage("user", json.dumps({"brief": compiled["brief"], "spec": view}, sort_keys=True))),
            required_capabilities=frozenset({"chat"}),
            response_schema=RESPONSE_SCHEMA,
            max_output_tokens=self._max_out,
            budget=RouteBudget(max_output_tokens=self._max_out),
            metadata={"task": TASK_TYPE, "spec_id": compiled["spec_id"]},
        )

    async def plan(self, brief: str, *, era: str = "", request_id: str | None = None) -> PlanOutcome:
        text = normalize_prompt(brief)
        compiled = compile_brief(text, era=era)
        rid = request_id or f"aib-{uuid.uuid4().hex[:12]}"

        def fallback(receipt: RoutingReceipt, reason: str, violations: tuple[str, ...] = ()) -> PlanOutcome:
            return PlanOutcome(text, compiled, compiled, "compiler", receipt, violations, reason)

        try:
            call = await self._router.execute(self._request(compiled, rid), gate=self._gate, cap=self._cap,
                                              task_type=TASK_TYPE, budget=self._budget)
        except Exception as exc:  # router fault never blocks a build
            return fallback(_compiler_receipt(rid, RouteStatus.FAILED, f"error:{type(exc).__name__}"),
                            f"router_error:{type(exc).__name__}")
        receipt = call.receipt
        if receipt.status != RouteStatus.OK:
            return fallback(receipt, f"route:{receipt.status}")
        try:
            proposal = parse_model_plan(_response_payload(call.result))
        except PlanParseError as exc:
            return fallback(receipt, f"parse:{exc}")
        spec, violations = guard_proposal(compiled, proposal)
        if spec["spec_id"] == compiled["spec_id"]:
            return fallback(receipt, "no_change", violations)
        return PlanOutcome(text, compiled, spec, "model", receipt, violations)
