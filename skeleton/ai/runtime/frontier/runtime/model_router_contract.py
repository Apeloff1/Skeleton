"""Unified ``ModelRouter`` contract (B031, frozen interface v1).

Skeleton already has three routing surfaces. This module puts one Protocol in
front of them **without forking any of them**:

- :mod:`skeleton.frontier.runtime.model_routing` — capability/budget router
  that *executes* through ``ModelRuntime`` with bounded fallback. Wrapped by
  :class:`FrontierModelRouterAdapter` (select + execute).
- :mod:`skeleton.ai.compat.backend_core.model_router` — telemetry-scored,
  privacy-aware *selection-only* router. Phase 2 adds a select-only
  ``ModelRouter`` adapter next to the code it wraps
  (``skeleton/ai/compat/backend_core/``) so this module stays free of compat
  imports; it will conform to the same frozen Protocol.
- :mod:`skeleton.intelligence.routing_context_receipt` — the P1 evidence
  receipt joining a route with compiled context/admission/quality. Linked by
  :func:`link_context_receipt` (duck-typed, so no upward import from the
  frontier runtime into ``skeleton.intelligence``).

Frozen surface (callers — Klint in ``skeleton/tools/``, Bork in
``skeleton/integrations/``, ``skeleton/ai/providers`` — code against these):

- :class:`RouteTask` — *what* is being routed (task type, capabilities,
  token estimates, provider preferences/exclusions, privacy).
- :class:`CallBudget` — per-call ceilings: cost, output tokens, latency,
  attempts (primary + fallbacks).
- :class:`RoutingReceipt` / :class:`ReceiptAttempt` — immutable record of
  the decision: selected provider, ordered fallback chain, rejections with
  reasons, attempts, spend, capsec decision ids, context-receipt digest.
- :class:`ModelRouter` — ``select(task, budget) -> RoutingReceipt`` (no
  provider call).
- :class:`ExecutingModelRouter` — adds ``execute(...)`` which runs the
  fallback chain and gates **every provider** through a
  :class:`skeleton.kernel.capsec.CapabilityGate` (deny-by-default).

Phase 2 additions (additive, interface version unchanged):

- :func:`gate_receipt` — filter any planned receipt's chain through capsec.
- :func:`execute_receipt_chain` + :class:`ProviderOutcome` / :class:`ChainCall`
  — run a planned receipt's fallback chain under capsec and the full
  :class:`CallBudget` (cost, output tokens, latency, attempts), for
  select-only routers such as the compat adapter.

Ordering semantics: ``RoutingReceipt.provider_chain`` is
``(selected_provider_id, *fallback_chain)``, at most ``budget.max_attempts``
long; callers that execute themselves MUST try providers in that order and
stop at the first success or budget exhaustion.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

from skeleton.frontier.runtime.contracts import stable_content_digest
from skeleton.frontier.runtime.model_routing import (
    ModelRouter as FrontierModelRouter,
    ModelRouteRequest,
    ModelRouteResult,
    RouteBudget,
    RoutePlan,
)
from skeleton.frontier.runtime.model_runtime import ModelMessage
from skeleton.kernel.capsec import Action, CapabilityGate, Decision

__all__ = [
    "ROUTER_INTERFACE_VERSION",
    "CallBudget",
    "ChainCall",
    "ExecutingModelRouter",
    "FrontierModelRouterAdapter",
    "ModelRouter",
    "ProviderOutcome",
    "ReceiptAttempt",
    "RouteStatus",
    "RouteTask",
    "RoutedCall",
    "RoutingReceipt",
    "RoutingReceiptMismatch",
    "execute_receipt_chain",
    "gate_receipt",
    "link_context_receipt",
    "provider_action",
]

#: Bumped only on a breaking change to the dataclasses or Protocols.
ROUTER_INTERFACE_VERSION = 1


class RoutingReceiptMismatch(ValueError):
    """A receipt cannot be joined with evidence that disagrees with it."""


class RouteStatus:
    """Normalised receipt status vocabulary (backend status kept verbatim in
    ``RoutingReceipt.backend_status``)."""

    PLANNED = "planned"          # select(): a chain exists, nothing called
    OK = "ok"                    # execute(): a provider succeeded
    NO_ROUTE = "no_route"        # no provider satisfies hard constraints
    BUDGET_EXHAUSTED = "budget_exhausted"
    DENIED = "denied"            # capsec denied every candidate provider
    FAILED = "failed"            # providers attempted, none succeeded

    ALL = frozenset({PLANNED, OK, NO_ROUTE, BUDGET_EXHAUSTED, DENIED, FAILED})


def provider_action(provider_id: str, verb: str = "call") -> Action:
    """The capsec :class:`Action` every provider call is gated on.

    Grant ``Capability("provider.<provider_id>", "call")`` per provider, or
    ``Capability("*", "call")`` for all providers. Note that kernel scope
    matching is exact, so ``"provider.*"`` is **not** a prefix wildcard.
    """

    return Action(scope=f"provider.{provider_id}", verb=verb, resource=provider_id)


def _opt_nonneg_float(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and >= 0")
    return number


def _opt_nonneg_int(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be an int >= 0")
    return value


@dataclass(frozen=True, slots=True)
class CallBudget:
    """Per-call ceilings, covering the primary attempt *and* all fallbacks.

    ``None`` means "no ceiling" for that dimension. ``max_attempts`` bounds
    the length of the provider chain (primary + fallbacks).
    """

    max_cost: float | None = None
    max_output_tokens: int | None = None
    max_latency_ms: float | None = None
    max_attempts: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_cost", _opt_nonneg_float(self.max_cost, "max_cost"))
        object.__setattr__(
            self, "max_output_tokens", _opt_nonneg_int(self.max_output_tokens, "max_output_tokens")
        )
        object.__setattr__(
            self, "max_latency_ms", _opt_nonneg_float(self.max_latency_ms, "max_latency_ms")
        )
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max_attempts must be an int >= 1")

    def to_route_budget(self) -> RouteBudget:
        """Translate to the frontier router's :class:`RouteBudget`."""

        return RouteBudget(
            max_cost=self.max_cost,
            max_output_tokens=self.max_output_tokens,
            max_provider_attempts=self.max_attempts,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_cost": self.max_cost,
            "max_output_tokens": self.max_output_tokens,
            "max_latency_ms": self.max_latency_ms,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class RouteTask:
    """Backend-neutral description of what is being routed.

    ``required_capabilities`` uses normalised lowercase names (e.g. ``chat``,
    ``tools``, ``structured_output``). An empty set means "chat" for backends
    that require at least one capability. ``privacy`` is one of ``public``,
    ``private``, ``sensitive``, ``local_only``.
    """

    task_type: str
    required_capabilities: frozenset[str] = frozenset()
    estimated_input_tokens: int = 0
    expected_output_tokens: int = 0
    preferred_providers: tuple[str, ...] = ()
    excluded_providers: frozenset[str] = frozenset()
    privacy: str = "public"
    request_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task_type, str) or not self.task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        object.__setattr__(self, "task_type", self.task_type.strip())
        object.__setattr__(
            self, "required_capabilities", frozenset(self.required_capabilities)
        )
        object.__setattr__(self, "preferred_providers", tuple(self.preferred_providers))
        object.__setattr__(self, "excluded_providers", frozenset(self.excluded_providers))
        _opt_nonneg_int(self.estimated_input_tokens, "estimated_input_tokens")
        _opt_nonneg_int(self.expected_output_tokens, "expected_output_tokens")
        if self.privacy not in {"public", "private", "sensitive", "local_only"}:
            raise ValueError(f"unknown privacy level: {self.privacy!r}")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def resolved_request_id(self) -> str:
        if self.request_id:
            return self.request_id
        return "route-" + stable_content_digest(
            {
                "task_type": self.task_type,
                "caps": sorted(self.required_capabilities),
                "in": self.estimated_input_tokens,
                "out": self.expected_output_tokens,
            }
        )[:16]


@dataclass(frozen=True, slots=True)
class ReceiptAttempt:
    """One provider attempt inside a routed call."""

    provider_id: str
    outcome: str
    latency_ms: float = 0.0
    estimated_cost: float = 0.0
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "outcome": self.outcome,
            "latency_ms": round(self.latency_ms, 4),
            "estimated_cost": round(self.estimated_cost, 8),
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class RoutingReceipt:
    """Immutable, auditable record of one routing decision / routed call.

    ``selected_provider_id`` is the *primary* of the planned chain;
    ``served_by`` is the provider that actually produced the response after
    ``execute`` (a fallback when the primary failed; ``None`` for ``select``
    or when nothing succeeded). ``receipt_digest()`` is stable over
    :meth:`identity_payload`, which excludes wall-clock fields
    (``decided_at``, attempt latencies).
    """

    request_id: str
    task_type: str
    backend: str
    status: str
    selected_provider_id: str | None
    fallback_chain: tuple[str, ...]
    rejected: Mapping[str, tuple[str, ...]]
    budget: CallBudget
    decided_at: float
    backend_status: str | None = None
    served_by: str | None = None
    estimated_cost: float | None = None
    attempts: tuple[ReceiptAttempt, ...] = ()
    spent_cost: float = 0.0
    spent_output_tokens: int = 0
    capability_decisions: tuple[str, ...] = ()
    context_receipt_digest: str | None = None
    schema_version: int = ROUTER_INTERFACE_VERSION

    def __post_init__(self) -> None:
        if self.status not in RouteStatus.ALL:
            raise ValueError(f"unknown route status: {self.status!r}")
        if self.selected_provider_id is None and self.fallback_chain:
            raise ValueError("fallback_chain requires a selected provider")
        if self.selected_provider_id is not None and self.selected_provider_id in self.fallback_chain:
            raise ValueError("selected provider must not repeat in fallback_chain")
        if len(self.provider_chain) > self.budget.max_attempts:
            raise ValueError("provider chain exceeds budget.max_attempts")
        if self.served_by is not None and self.served_by not in self.provider_chain:
            raise ValueError("served_by must be a member of the provider chain")
        if self.status == RouteStatus.OK and self.served_by is None:
            raise ValueError("an ok receipt must name served_by")
        object.__setattr__(self, "fallback_chain", tuple(self.fallback_chain))
        object.__setattr__(
            self, "rejected", {k: tuple(v) for k, v in dict(self.rejected).items()}
        )

    @property
    def ok(self) -> bool:
        return self.status == RouteStatus.OK

    @property
    def provider_chain(self) -> tuple[str, ...]:
        if self.selected_provider_id is None:
            return ()
        return (self.selected_provider_id, *self.fallback_chain)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "task_type": self.task_type,
            "backend": self.backend,
            "status": self.status,
            "backend_status": self.backend_status,
            "selected_provider_id": self.selected_provider_id,
            "fallback_chain": list(self.fallback_chain),
            "served_by": self.served_by,
            "rejected": {k: list(v) for k, v in sorted(self.rejected.items())},
            "budget": self.budget.as_dict(),
            "estimated_cost": self.estimated_cost,
            "attempts": [
                {"provider_id": a.provider_id, "outcome": a.outcome, "error_type": a.error_type}
                for a in self.attempts
            ],
            "spent_cost": round(self.spent_cost, 8),
            "spent_output_tokens": self.spent_output_tokens,
            "capability_decisions": list(self.capability_decisions),
            "context_receipt_digest": self.context_receipt_digest,
        }

    def receipt_digest(self) -> str:
        return stable_content_digest(self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        payload = self.identity_payload()
        payload["decided_at"] = self.decided_at
        payload["attempts"] = [a.as_dict() for a in self.attempts]
        payload["receipt_digest"] = self.receipt_digest()
        return payload


@dataclass(frozen=True, slots=True)
class RoutedCall:
    """Result of :meth:`ExecutingModelRouter.execute`: receipt + raw result."""

    receipt: RoutingReceipt
    result: ModelRouteResult | None

    @property
    def ok(self) -> bool:
        return self.receipt.ok


@runtime_checkable
class ModelRouter(Protocol):
    """Select a provider chain by task, cost and latency. No provider call."""

    backend: str

    def select(self, task: RouteTask, budget: CallBudget | None = None) -> RoutingReceipt: ...


@runtime_checkable
class ExecutingModelRouter(ModelRouter, Protocol):
    """A router that also executes the chain, gating each provider on capsec.

    Contract: before any provider is attempted, ``gate.check(cap,
    provider_action(provider_id))`` must allow it; denied providers are
    removed from the chain and listed in ``receipt.rejected`` with a
    ``"capsec:<reason>"`` entry. If no provider survives, nothing is called
    and the receipt status is :data:`RouteStatus.DENIED`.
    """

    async def execute(
        self,
        request: ModelRouteRequest,
        *,
        gate: CapabilityGate,
        cap: str | None,
        task_type: str = "chat",
        budget: CallBudget | None = None,
    ) -> RoutedCall: ...


def link_context_receipt(receipt: RoutingReceipt, context_receipt: Any) -> RoutingReceipt:
    """Bind a ``skeleton.intelligence.routing_context_receipt.RoutingContextReceipt``.

    Duck-typed (needs ``request_id``, ``selected_provider_id``,
    ``fallback_provider_ids`` and ``receipt_digest()``). The context receipt's
    ``selected_provider_id`` is the provider that *served* the call, so it is
    compared with ``receipt.served_by``. Fails closed if the evidence
    disagrees with this receipt on identity or provider order.
    """

    if getattr(context_receipt, "request_id", None) != receipt.request_id:
        raise RoutingReceiptMismatch("request_id mismatch")
    if getattr(context_receipt, "selected_provider_id", None) != receipt.served_by:
        raise RoutingReceiptMismatch("served provider mismatch")
    if tuple(getattr(context_receipt, "fallback_provider_ids", ())) != receipt.fallback_chain:
        raise RoutingReceiptMismatch("fallback chain mismatch")
    digest = context_receipt.receipt_digest()
    if not isinstance(digest, str) or not digest:
        raise RoutingReceiptMismatch("context receipt has no digest")
    return replace(receipt, context_receipt_digest=digest)


_FRONTIER_STATUS = {
    "ok": RouteStatus.OK,
    "budget_exhausted": RouteStatus.BUDGET_EXHAUSTED,
    "no_capable_provider": RouteStatus.NO_ROUTE,
}


class FrontierModelRouterAdapter:
    """:class:`ExecutingModelRouter` over the frontier ``ModelRouter``.

    Delegates planning/execution to the wrapped router unchanged. Capsec
    filtering for :meth:`execute` builds a transient frontier router over the
    *same* ``ModelRuntime`` and adapters containing only allowed providers,
    so the frontier router's ordering/budget/fallback logic is reused as-is.
    """

    backend = "frontier"

    def __init__(self, router: FrontierModelRouter, *, clock: Any = None) -> None:
        if not isinstance(router, FrontierModelRouter):
            raise TypeError("router must be a frontier ModelRouter")
        self._router = router
        self._clock = clock or time.time

    @property
    def router(self) -> FrontierModelRouter:
        return self._router

    def _request_for(self, task: RouteTask, budget: CallBudget) -> ModelRouteRequest:
        timeout = 5.0 if budget.max_latency_ms is None else max(budget.max_latency_ms / 1000.0, 0.001)
        return ModelRouteRequest(
            request_id=task.resolved_request_id(),
            # Planning never sends messages; a placeholder satisfies validation.
            messages=(ModelMessage(role="user", content=""),),
            required_capabilities=task.required_capabilities or frozenset({"chat"}),
            max_output_tokens=task.expected_output_tokens or None,
            timeout_seconds=timeout,
            budget=budget.to_route_budget(),
            estimated_input_tokens=task.estimated_input_tokens,
            metadata=dict(task.metadata),
        )

    def _apply_task_filters(self, plan: RoutePlan, task: RouteTask, budget: CallBudget) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
        rejected = {k: tuple(v) for k, v in plan.rejected.items()}
        chain = [p for p in plan.provider_ids if p not in task.excluded_providers]
        for p in plan.provider_ids:
            if p in task.excluded_providers:
                rejected[p] = ("excluded by task",)
        if task.preferred_providers:
            rank = {p: i for i, p in enumerate(task.preferred_providers)}
            chain.sort(key=lambda p: rank.get(p, len(rank)))
        return tuple(chain[: budget.max_attempts]), rejected

    def select(self, task: RouteTask, budget: CallBudget | None = None) -> RoutingReceipt:
        budget = budget or CallBudget()
        request = self._request_for(task, replace(budget, max_attempts=max(budget.max_attempts, len(self._router.catalog()) or 1)))
        plan = self._router.plan(request)
        chain, rejected = self._apply_task_filters(plan, task, budget)
        if chain:
            status = RouteStatus.PLANNED
        elif any("budget" in r for rs in rejected.values() for r in rs):
            status = RouteStatus.BUDGET_EXHAUSTED
        else:
            status = RouteStatus.NO_ROUTE
        return RoutingReceipt(
            request_id=request.request_id,
            task_type=task.task_type,
            backend=self.backend,
            status=status,
            selected_provider_id=chain[0] if chain else None,
            fallback_chain=chain[1:],
            rejected=rejected,
            budget=budget,
            decided_at=float(self._clock()),
            backend_status=None,
        )

    async def execute(
        self,
        request: ModelRouteRequest,
        *,
        gate: CapabilityGate,
        cap: str | None,
        task_type: str = "chat",
        budget: CallBudget | None = None,
    ) -> RoutedCall:
        if not isinstance(request, ModelRouteRequest):
            raise TypeError("request must be a ModelRouteRequest")
        if budget is not None:
            request = replace(request, budget=budget.to_route_budget())
        else:
            budget = CallBudget(
                max_cost=request.budget.max_cost,
                max_output_tokens=request.budget.max_output_tokens,
                max_latency_ms=request.timeout_seconds * 1000.0,
                max_attempts=request.budget.max_provider_attempts,
            )
        catalog = self._router.catalog()
        decisions: list[Decision] = []
        allowed: list[str] = []
        denied: dict[str, tuple[str, ...]] = {}
        for provider_id in sorted(catalog):
            decision = gate.check(cap, provider_action(provider_id))
            decisions.append(decision)
            if decision.allowed:
                allowed.append(provider_id)
            else:
                denied[provider_id] = (f"capsec:{decision.reason}",)
        decision_ids = tuple(d.audit.record_id for d in decisions)
        if not allowed:
            receipt = RoutingReceipt(
                request_id=request.request_id,
                task_type=task_type,
                backend=self.backend,
                status=RouteStatus.DENIED,
                selected_provider_id=None,
                fallback_chain=(),
                rejected=denied,
                budget=budget,
                decided_at=float(self._clock()),
                capability_decisions=decision_ids,
            )
            return RoutedCall(receipt=receipt, result=None)

        router = self._router
        if denied:
            router = FrontierModelRouter(runtime=self._router.runtime)
            for provider_id in allowed:
                meta = catalog[provider_id]
                router.register(meta, self._router.runtime.resolve(meta.adapter_name))
        result = await router.invoke(request)
        rejected = {k: tuple(v) for k, v in result.trace.get("rejected", {}).items()} if isinstance(result.trace.get("rejected"), Mapping) else {}
        rejected.update(denied)
        attempts = tuple(
            ReceiptAttempt(
                provider_id=a.provider_id,
                outcome=a.outcome,
                latency_ms=a.latency_ms,
                estimated_cost=a.estimated_cost,
                error_type=a.error_type,
            )
            for a in result.attempts
        )
        planned = tuple(result.planned_provider_ids)
        if result.status == "ok":
            status = RouteStatus.OK
        else:
            status = _FRONTIER_STATUS.get(result.status, RouteStatus.FAILED)
        receipt = RoutingReceipt(
            request_id=result.request_id,
            task_type=task_type,
            backend=self.backend,
            status=status,
            selected_provider_id=planned[0] if planned else None,
            fallback_chain=planned[1:],
            rejected=rejected,
            budget=budget,
            decided_at=float(self._clock()),
            backend_status=result.status,
            served_by=result.selected_provider_id,
            attempts=attempts,
            spent_cost=result.budget.spent_cost,
            spent_output_tokens=result.budget.spent_output_tokens,
            capability_decisions=decision_ids,
        )
        return RoutedCall(receipt=receipt, result=result)


# ---------------------------------------------------------------------------
# Phase 2 (additive): capsec + fallback execution for select-only routers.
# ---------------------------------------------------------------------------


def gate_receipt(receipt: RoutingReceipt, *, gate: CapabilityGate, cap: str | None) -> RoutingReceipt:
    """Filter a planned receipt's provider chain through capsec.

    Every provider in ``receipt.provider_chain`` is checked with
    ``gate.check(cap, provider_action(provider_id))`` in chain order. Denied
    providers leave the chain and get a ``"capsec:<reason>"`` entry in
    ``rejected``; survivors keep their order. Every decision's audit record id
    is appended to ``capability_decisions``. If nothing survives the status
    becomes :data:`RouteStatus.DENIED`. Receipts with an empty chain are
    returned unchanged.
    """

    chain = receipt.provider_chain
    if not chain:
        return receipt
    rejected = {k: tuple(v) for k, v in receipt.rejected.items()}
    survivors: list[str] = []
    decision_ids: list[str] = []
    for provider_id in chain:
        decision = gate.check(cap, provider_action(provider_id))
        decision_ids.append(decision.audit.record_id)
        if decision.allowed:
            survivors.append(provider_id)
        else:
            rejected[provider_id] = (*rejected.get(provider_id, ()), f"capsec:{decision.reason}")
    return replace(
        receipt,
        status=receipt.status if survivors else RouteStatus.DENIED,
        selected_provider_id=survivors[0] if survivors else None,
        fallback_chain=tuple(survivors[1:]),
        served_by=None,
        rejected=rejected,
        capability_decisions=(*receipt.capability_decisions, *decision_ids),
    )


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """What a provider invocation reports back to :func:`execute_receipt_chain`.

    ``ok=False`` means the provider answered but the answer is unusable (it
    still costs ``cost``/``output_tokens``, and the chain falls back).
    Raising from the invoke callable is also a failed attempt, with no spend.
    """

    value: Any = None
    cost: float = 0.0
    output_tokens: int = 0
    ok: bool = True
    error_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cost", _opt_nonneg_float(self.cost, "cost") or 0.0)
        object.__setattr__(
            self, "output_tokens", _opt_nonneg_int(self.output_tokens, "output_tokens") or 0
        )


@dataclass(frozen=True, slots=True)
class ChainCall:
    """Result of :func:`execute_receipt_chain`: receipt + the served value."""

    receipt: RoutingReceipt
    value: Any = None

    @property
    def ok(self) -> bool:
        return self.receipt.ok


def _pre_attempt_exhaustion(budget: CallBudget, cost: float, tokens: int, elapsed_ms: float) -> str | None:
    if budget.max_latency_ms is not None and elapsed_ms >= budget.max_latency_ms:
        return "latency budget exhausted"
    if budget.max_cost is not None and cost > 0 and cost >= budget.max_cost:
        return "cost budget exhausted"
    if budget.max_output_tokens is not None and tokens > 0 and tokens >= budget.max_output_tokens:
        return "output token budget exhausted"
    return None


def _overspend(budget: CallBudget, cost: float, tokens: int, elapsed_ms: float) -> str | None:
    if budget.max_cost is not None and cost > budget.max_cost:
        return "cost budget exceeded"
    if budget.max_output_tokens is not None and tokens > budget.max_output_tokens:
        return "output token budget exceeded"
    if budget.max_latency_ms is not None and elapsed_ms > budget.max_latency_ms:
        return "latency budget exceeded"
    return None


async def execute_receipt_chain(
    receipt: RoutingReceipt,
    invoke: Callable[[str], Any],
    *,
    gate: CapabilityGate,
    cap: str | None,
    clock: Callable[[], float] | None = None,
) -> ChainCall:
    """Run a planned receipt's fallback chain under capsec and its budget.

    For select-only routers (e.g. the compat adapter): ``invoke(provider_id)``
    performs the call and returns a :class:`ProviderOutcome` (any other value
    is treated as ``ProviderOutcome(value=...)``); it may be sync or async.

    Semantics:

    1. Non-``planned`` receipts are returned unchanged with no call.
    2. The chain is gated with :func:`gate_receipt` first; a fully denied
       chain makes no call and returns status ``denied``.
    3. Providers are tried in chain order (already bounded by
       ``budget.max_attempts``) until one succeeds within budget.
    4. Before each attempt the remaining latency/cost/token budget is
       checked; once exhausted, the rest of the chain is skipped and listed
       in ``rejected`` as ``"not attempted: <reason>"``.
    5. Async calls are bounded by the remaining latency budget
       (``asyncio.wait_for``); a timeout is a failed attempt.
    6. A success whose spend pushes past ``max_cost`` / ``max_output_tokens``
       or whose latency overruns ``max_latency_ms`` is *not* served: the
       attempt is recorded as ``budget_exhausted`` and the call stops.
    7. Spend from every attempt is accumulated into ``spent_cost`` and
       ``spent_output_tokens``.

    ``clock`` is a monotonic seconds clock used for latency (default
    :func:`time.monotonic`).
    """

    if receipt.status != RouteStatus.PLANNED or not receipt.provider_chain:
        return ChainCall(receipt=receipt)
    gated = gate_receipt(receipt, gate=gate, cap=cap)
    if gated.status == RouteStatus.DENIED:
        return ChainCall(receipt=gated)

    tick = clock or time.monotonic
    budget = gated.budget
    chain = gated.provider_chain
    rejected = {k: tuple(v) for k, v in gated.rejected.items()}
    attempts: list[ReceiptAttempt] = []
    spent_cost, spent_tokens = 0.0, 0
    status, served, value = RouteStatus.FAILED, None, None
    start = tick()

    def _skip_rest(index: int, reason: str) -> None:
        for provider_id in chain[index:]:
            rejected[provider_id] = (*rejected.get(provider_id, ()), f"not attempted: {reason}")

    for index, provider_id in enumerate(chain):
        elapsed_ms = (tick() - start) * 1000.0
        exhausted = _pre_attempt_exhaustion(budget, spent_cost, spent_tokens, elapsed_ms)
        if exhausted:
            status = RouteStatus.BUDGET_EXHAUSTED
            _skip_rest(index, exhausted)
            break
        remaining_s = (
            None if budget.max_latency_ms is None
            else max((budget.max_latency_ms - elapsed_ms) / 1000.0, 0.0)
        )
        t0 = tick()
        try:
            outcome = invoke(provider_id)
            if inspect.isawaitable(outcome):
                awaited: Awaitable[Any] = outcome
                outcome = await (awaited if remaining_s is None else asyncio.wait_for(awaited, remaining_s))
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, TimeoutError):
            attempts.append(ReceiptAttempt(provider_id, "timeout", (tick() - t0) * 1000.0, 0.0, "TimeoutError"))
            continue
        except Exception as exc:  # noqa: BLE001 — provider failure means fall back
            attempts.append(ReceiptAttempt(provider_id, "error", (tick() - t0) * 1000.0, 0.0, type(exc).__name__))
            continue
        if not isinstance(outcome, ProviderOutcome):
            outcome = ProviderOutcome(value=outcome)
        latency_ms = (tick() - t0) * 1000.0
        spent_cost += outcome.cost
        spent_tokens += outcome.output_tokens
        over = _overspend(budget, spent_cost, spent_tokens, (tick() - start) * 1000.0)
        if over:
            attempts.append(ReceiptAttempt(provider_id, "budget_exhausted", latency_ms, outcome.cost, None))
            status = RouteStatus.BUDGET_EXHAUSTED
            rejected[provider_id] = (*rejected.get(provider_id, ()), over)
            _skip_rest(index + 1, over)
            break
        if not outcome.ok:
            attempts.append(ReceiptAttempt(provider_id, "error", latency_ms, outcome.cost,
                                           outcome.error_type or "ProviderOutcomeNotOk"))
            continue
        attempts.append(ReceiptAttempt(provider_id, "ok", latency_ms, outcome.cost, None))
        status, served, value = RouteStatus.OK, provider_id, outcome.value
        break

    final = replace(
        gated,
        status=status,
        served_by=served,
        attempts=tuple(attempts),
        spent_cost=spent_cost,
        spent_output_tokens=spent_tokens,
        rejected=rejected,
    )
    return ChainCall(receipt=final, value=value)
