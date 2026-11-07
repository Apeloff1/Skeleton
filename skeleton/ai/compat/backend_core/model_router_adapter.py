"""B031 ``ModelRouter`` adapter over the compat backend-core router.

Wraps :class:`skeleton.ai.compat.backend_core.model_router.ModelRouter`
(itself a staged mirror of ``backend/core/model_router.py``) **unchanged**:
no fork, no subclass, no private-state access. The compat router is
selection-only, so this adapter implements the frozen
:class:`skeleton.frontier.runtime.model_router_contract.ModelRouter` Protocol
(``select``) and leaves execution to
:func:`~skeleton.frontier.runtime.model_router_contract.execute_receipt_chain`,
which gates every provider through capsec and enforces the ``CallBudget``.

Mapping (``RouteTask`` + ``CallBudget`` -> compat ``RouteRequest``):

- ``provider_id`` in receipts is the compat ``endpoint_id``.
- ``estimated_input_tokens`` -> ``context_tokens``.
- ``expected_output_tokens`` -> ``expected_output_tokens``, clamped to
  ``budget.max_output_tokens`` (as ``RouteRequest.from_resource_budget`` does).
- ``budget.max_cost`` -> ``cost_budget``; ``budget.max_latency_ms`` ->
  ``latency_budget_ms`` (both hard filters in the compat router).
- ``privacy`` -> ``PrivacyLevel``.
- ``preferred_providers`` -> compat ``preferred_providers`` (a soft score
  over endpoint *provider names*); additionally, endpoints whose id is listed
  are moved to the front of the chain in the given order.
- ``excluded_providers`` match an endpoint id *or* provider name and become
  compat ``excluded_endpoints`` (a hard filter).
- ``metadata["minimum_reliability"]`` / ``metadata["minimum_quality"]`` and
  ``metadata["required_modalities"]`` pass through when present.

Governed requests (privacy owned by a ``GovernanceContext``) should be built
with ``RouteRequest.from_governance_context`` and routed through
:meth:`CompatModelRouterAdapter.select_request`, so the adapter can never
weaken governed privacy.

When the compat router raises ``NoRoute`` the per-endpoint reasons are
recovered from its message (best effort; unparseable detail is kept under
the ``"*"`` key) and the receipt status is ``budget_exhausted`` if any reason
is a budget rejection, otherwise ``no_route``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from skeleton.ai.compat.backend_core.model_router import (
    ModelRouter as CompatModelRouter,
    NoRoute,
    PrivacyLevel,
    RouteDecision,
    RouteRequest,
)
from skeleton.frontier.runtime.model_router_contract import (
    CallBudget,
    RouteStatus,
    RouteTask,
    RoutingReceipt,
)

__all__ = ["CompatModelRouterAdapter", "parse_no_route_detail"]

_NO_ROUTE_PREFIX = "no endpoint satisfies route request ("


def parse_no_route_detail(message: str) -> dict[str, tuple[str, ...]]:
    """Recover ``{endpoint_id: reasons}`` from a compat ``NoRoute`` message."""

    text = str(message)
    if not text.startswith(_NO_ROUTE_PREFIX) or not text.endswith(")"):
        return {"*": (text,)} if text else {}
    body = text[len(_NO_ROUTE_PREFIX):-1]
    if not body:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for chunk in body.split("; "):
        endpoint_id, sep, reasons = chunk.partition(": ")
        if not sep or not endpoint_id:
            return {"*": (text,)}
        out[endpoint_id] = tuple(r for r in reasons.split(", ") if r)
    return out


def _is_budget_reason(reason: str) -> bool:
    return "exceeds budget" in reason


class CompatModelRouterAdapter:
    """Select-only :class:`ModelRouter` over the compat router (backend ``"compat"``)."""

    backend = "compat"

    def __init__(self, router: CompatModelRouter, *, clock: Callable[[], float] | None = None) -> None:
        if not isinstance(router, CompatModelRouter):
            raise TypeError("router must be a compat backend_core ModelRouter")
        self._router = router
        self._clock = clock or time.time

    @property
    def router(self) -> CompatModelRouter:
        return self._router

    # -- request mapping ----------------------------------------------------

    def _endpoint_providers(self) -> dict[str, str]:
        snapshot = self._router.snapshot()
        return {
            row["endpoint_id"]: str(row["provider"]).strip().lower()
            for row in snapshot.get("endpoints", [])
        }

    def request_for(self, task: RouteTask, budget: CallBudget | None = None) -> RouteRequest:
        """The compat ``RouteRequest`` this adapter routes for ``task``/``budget``."""

        budget = budget or CallBudget()
        expected = task.expected_output_tokens
        if budget.max_output_tokens is not None:
            expected = min(expected, budget.max_output_tokens)
        excluded = {str(p).strip().lower() for p in task.excluded_providers}
        excluded_endpoints = {
            endpoint_id
            for endpoint_id, provider in self._endpoint_providers().items()
            if endpoint_id.lower() in excluded or provider in excluded
        }
        meta: Mapping[str, Any] = task.metadata
        kwargs: dict[str, Any] = {}
        for key in ("minimum_reliability", "minimum_quality"):
            if key in meta:
                kwargs[key] = float(meta[key])
        if "required_modalities" in meta:
            kwargs["required_modalities"] = frozenset(meta["required_modalities"])
        return RouteRequest(
            task_type=task.task_type,
            required_capabilities=task.required_capabilities,
            context_tokens=task.estimated_input_tokens,
            expected_output_tokens=expected,
            privacy=PrivacyLevel.parse(task.privacy),
            latency_budget_ms=budget.max_latency_ms,
            cost_budget=budget.max_cost,
            preferred_providers=task.preferred_providers,
            excluded_endpoints=frozenset(excluded_endpoints),
            **kwargs,
        )

    # -- ModelRouter Protocol ------------------------------------------------

    def select(self, task: RouteTask, budget: CallBudget | None = None) -> RoutingReceipt:
        budget = budget or CallBudget()
        request = self.request_for(task, budget)
        receipt = self._receipt(request, budget, request_id=task.resolved_request_id(),
                                task_type=task.task_type,
                                preferred_ids=task.preferred_providers)
        return receipt

    def select_request(self, request: RouteRequest, budget: CallBudget | None = None, *,
                       request_id: str) -> RoutingReceipt:
        """Route a native compat ``RouteRequest`` (e.g. a governed one).

        ``budget`` bounds the chain length (``max_attempts``) and is recorded
        on the receipt; cost/latency filtering is whatever ``request`` says.
        """

        if not isinstance(request, RouteRequest):
            raise TypeError("request must be a compat RouteRequest")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        return self._receipt(request, budget or CallBudget(), request_id=request_id.strip(),
                             task_type=request.task_type, preferred_ids=())

    # -- internals ----------------------------------------------------------

    def _receipt(self, request: RouteRequest, budget: CallBudget, *, request_id: str,
                 task_type: str, preferred_ids: tuple[str, ...]) -> RoutingReceipt:
        try:
            decision: RouteDecision = self._router.route(request)
        except NoRoute as exc:
            rejected = parse_no_route_detail(str(exc))
            budget_hit = any(_is_budget_reason(r) for rs in rejected.values() for r in rs)
            return RoutingReceipt(
                request_id=request_id,
                task_type=task_type,
                backend=self.backend,
                status=RouteStatus.BUDGET_EXHAUSTED if budget_hit else RouteStatus.NO_ROUTE,
                selected_provider_id=None,
                fallback_chain=(),
                rejected=rejected,
                budget=budget,
                decided_at=float(self._clock()),
                backend_status="no_route",
            )
        ranked = [c.endpoint_id for c in decision.candidates]
        if preferred_ids:
            rank = {p: i for i, p in enumerate(preferred_ids)}
            ranked.sort(key=lambda e: rank.get(e, len(rank)))  # stable: keeps compat score order
        rejected = {k: tuple(v) for k, v in decision.rejected.items()}
        chain = ranked[: budget.max_attempts]
        for endpoint_id in ranked[budget.max_attempts:]:
            rejected[endpoint_id] = ("beyond budget.max_attempts",)
        costs = {c.endpoint_id: c.estimated_cost for c in decision.candidates}
        return RoutingReceipt(
            request_id=request_id,
            task_type=task_type,
            backend=self.backend,
            status=RouteStatus.PLANNED,
            selected_provider_id=chain[0],
            fallback_chain=tuple(chain[1:]),
            rejected=rejected,
            budget=budget,
            decided_at=float(self._clock()),
            backend_status="routed",
            estimated_cost=costs.get(chain[0]),
        )
