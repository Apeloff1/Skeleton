"""Provider-neutral model routing and eval contracts for product/runtime calls.

This is a reusable runtime primitive, not a planning plane. Callers declare
capabilities and budgets; the router selects a deterministic provider order,
executes through ``ModelRuntime``, and returns a stable result with provenance
and redacted traces. Supervisor, studio, and Jeeves orchestration paths are
intentionally not imported or modified.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from skeleton.frontier.contracts import ProvenanceRecord, stable_content_digest
from skeleton.frontier.model_runtime import (
    ChatRequest,
    ChatResponse,
    ModelCapability,
    ModelMessage,
    ModelRuntime,
    ProviderAdapter,
    ProviderCancelledError,
    ProviderError,
    ProviderTimeoutError,
    RetryPolicy,
    TokenUsage,
    ToolDefinition,
)
from skeleton.observability.redaction import (
    REDACTED,
    redact_payload,
    safe_exception_text,
)

_EXECUTION_CAPABILITIES = frozenset(capability.value for capability in ModelCapability)
_SENSITIVE_TRACE_KEYS = frozenset(
    {"api_key", "token", "secret", "password", "authorization"}
)
_METADATA_REQUIRED_KEYS = frozenset(
    {
        "provider_id",
        "adapter_name",
        "model",
        "capabilities",
        "max_input_tokens",
        "max_output_tokens",
        "input_cost_per_million",
        "output_cost_per_million",
        "timeout_seconds",
        "priority",
    }
)
_METADATA_OPTIONAL_KEYS = frozenset(
    {"enabled", "max_attempts", "backoff_seconds"}
)
_METADATA_ALLOWED_KEYS = _METADATA_REQUIRED_KEYS | _METADATA_OPTIONAL_KEYS


class ModelRoutingError(RuntimeError):
    """Base routing/eval contract failure."""


class ProviderMetadataError(ModelRoutingError):
    """Raised when provider metadata is missing, malformed, or inconsistent."""


class RouteRequestError(ModelRoutingError):
    """Raised when a routing request violates the stable contract."""


def _require_normalized_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return value


def _require_finite_float(value: object, field_name: str, *, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    if number < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return number


def _normalize_capabilities(
    capabilities: object,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> frozenset[str]:
    if isinstance(capabilities, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    if not isinstance(capabilities, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    normalized: set[str] = set()
    for capability in capabilities:
        if isinstance(capability, ModelCapability):
            value = capability.value
        elif isinstance(capability, str):
            value = capability.strip().lower()
            if value != capability:
                raise ValueError(f"{field_name} entries must be normalized")
        else:
            raise TypeError(f"{field_name} entries must be strings")
        if not value:
            raise ValueError(f"{field_name} entries must not be empty")
        normalized.add(value)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return frozenset(normalized)


def _mapping_keys(data: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in data:
        if not isinstance(key, str):
            raise ProviderMetadataError("provider metadata keys must be strings")
        keys.add(key)
    return keys


def _redact_trace(value: Any) -> Any:
    return redact_payload(value)


def _usage_cost(metadata: ProviderMetadata, usage: TokenUsage) -> float:
    return (
        usage.input_tokens * metadata.input_cost_per_million
        + usage.output_tokens * metadata.output_cost_per_million
    ) / 1_000_000.0


def _estimate_cost(
    metadata: ProviderMetadata,
    *,
    input_tokens: int,
    output_tokens: int,
) -> float:
    return (
        max(0, input_tokens) * metadata.input_cost_per_million
        + max(0, output_tokens) * metadata.output_cost_per_million
    ) / 1_000_000.0


def _planned_output_tokens(
    metadata: ProviderMetadata,
    request: ModelRouteRequest,
    *,
    remaining_output: int | None = None,
) -> int:
    """Use one output-token estimate for planning and execution."""
    planned = (
        request.max_output_tokens
        if request.max_output_tokens is not None
        else metadata.max_output_tokens
    )
    if remaining_output is not None:
        planned = min(planned, remaining_output)
    return planned


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Capability catalog entry for one interchangeable runtime endpoint."""

    provider_id: str
    adapter_name: str
    model: str
    capabilities: frozenset[str]
    max_input_tokens: int
    max_output_tokens: int
    input_cost_per_million: float
    output_cost_per_million: float
    timeout_seconds: float
    priority: int
    enabled: bool = True
    max_attempts: int = 2
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "provider_id", _require_normalized_text(self.provider_id, "provider_id")
        )
        object.__setattr__(
            self,
            "adapter_name",
            _require_normalized_text(self.adapter_name, "adapter_name"),
        )
        object.__setattr__(self, "model", _require_normalized_text(self.model, "model"))
        object.__setattr__(
            self,
            "capabilities",
            _normalize_capabilities(self.capabilities, field_name="capabilities"),
        )
        object.__setattr__(
            self,
            "max_input_tokens",
            _require_int(self.max_input_tokens, "max_input_tokens", minimum=1),
        )
        object.__setattr__(
            self,
            "max_output_tokens",
            _require_int(self.max_output_tokens, "max_output_tokens", minimum=1),
        )
        object.__setattr__(
            self,
            "input_cost_per_million",
            _require_finite_float(
                self.input_cost_per_million, "input_cost_per_million", minimum=0.0
            ),
        )
        object.__setattr__(
            self,
            "output_cost_per_million",
            _require_finite_float(
                self.output_cost_per_million, "output_cost_per_million", minimum=0.0
            ),
        )
        object.__setattr__(
            self,
            "timeout_seconds",
            _require_finite_float(self.timeout_seconds, "timeout_seconds", minimum=0.001),
        )
        object.__setattr__(
            self, "priority", _require_int(self.priority, "priority", minimum=0)
        )
        object.__setattr__(self, "enabled", _require_bool(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "max_attempts",
            _require_int(self.max_attempts, "max_attempts", minimum=1),
        )
        object.__setattr__(
            self,
            "backoff_seconds",
            _require_finite_float(self.backoff_seconds, "backoff_seconds", minimum=0.0),
        )

    @classmethod
    def from_mapping(cls, data: object) -> ProviderMetadata:
        if not isinstance(data, Mapping):
            raise ProviderMetadataError("provider metadata must be a mapping")
        keys = _mapping_keys(data)
        missing = sorted(_METADATA_REQUIRED_KEYS - keys)
        unknown = sorted(keys - _METADATA_ALLOWED_KEYS)
        if missing or unknown:
            details: list[str] = []
            if missing:
                details.append("missing keys: " + ", ".join(missing))
            if unknown:
                details.append("unknown keys: " + ", ".join(unknown))
            raise ProviderMetadataError("; ".join(details))
        try:
            return cls(
                provider_id=data["provider_id"],
                adapter_name=data["adapter_name"],
                model=data["model"],
                capabilities=data["capabilities"],
                max_input_tokens=data["max_input_tokens"],
                max_output_tokens=data["max_output_tokens"],
                input_cost_per_million=data["input_cost_per_million"],
                output_cost_per_million=data["output_cost_per_million"],
                timeout_seconds=data["timeout_seconds"],
                priority=data["priority"],
                enabled=data.get("enabled", True),
                max_attempts=data.get("max_attempts", 2),
                backoff_seconds=data.get("backoff_seconds", 0.0),
            )
        except (TypeError, ValueError) as exc:
            raise ProviderMetadataError(str(exc)) from exc

    def retry_policy(self, bound: RetryPolicy) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=min(self.max_attempts, bound.max_attempts),
            backoff_seconds=max(self.backoff_seconds, bound.backoff_seconds),
        )


@dataclass(frozen=True, slots=True)
class RouteBudget:
    """Hard ceilings for one routed invocation, including fallbacks."""

    max_cost: float | None = None
    max_output_tokens: int | None = None
    max_provider_attempts: int = 3

    def __post_init__(self) -> None:
        if self.max_cost is not None:
            object.__setattr__(
                self,
                "max_cost",
                _require_finite_float(self.max_cost, "max_cost", minimum=0.0),
            )
        if self.max_output_tokens is not None:
            object.__setattr__(
                self,
                "max_output_tokens",
                _require_int(self.max_output_tokens, "max_output_tokens", minimum=0),
            )
        object.__setattr__(
            self,
            "max_provider_attempts",
            _require_int(
                self.max_provider_attempts, "max_provider_attempts", minimum=1
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelRouteRequest:
    """Stable product/runtime request. The router, not the caller, selects a model."""

    request_id: str
    messages: tuple[ModelMessage, ...]
    required_capabilities: frozenset[str]
    tools: tuple[ToolDefinition, ...] = ()
    response_schema: Mapping[str, Any] | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    timeout_seconds: float = 5.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    budget: RouteBudget = field(default_factory=RouteBudget)
    estimated_input_tokens: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _require_normalized_text(self.request_id, "request_id"),
        )
        if not isinstance(self.messages, tuple) or not self.messages:
            raise ValueError("messages must be a non-empty tuple")
        for index, message in enumerate(self.messages):
            if not isinstance(message, ModelMessage):
                raise TypeError(f"messages[{index}] must be a ModelMessage")
        object.__setattr__(
            self,
            "required_capabilities",
            _normalize_capabilities(
                self.required_capabilities, field_name="required_capabilities"
            ),
        )
        if not isinstance(self.tools, tuple):
            raise TypeError("tools must be a tuple")
        if self.max_output_tokens is not None:
            object.__setattr__(
                self,
                "max_output_tokens",
                _require_int(self.max_output_tokens, "max_output_tokens", minimum=1),
            )
        if self.temperature is not None:
            object.__setattr__(
                self,
                "temperature",
                _require_finite_float(self.temperature, "temperature", minimum=0.0),
            )
            if self.temperature > 2.0:
                raise ValueError("temperature must be <= 2.0")
        object.__setattr__(
            self,
            "timeout_seconds",
            _require_finite_float(self.timeout_seconds, "timeout_seconds", minimum=0.001),
        )
        if not isinstance(self.retry_policy, RetryPolicy):
            raise TypeError("retry_policy must be a RetryPolicy")
        if not isinstance(self.budget, RouteBudget):
            raise TypeError("budget must be a RouteBudget")
        object.__setattr__(
            self,
            "estimated_input_tokens",
            _require_int(
                self.estimated_input_tokens, "estimated_input_tokens", minimum=0
            ),
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.response_schema is not None and not isinstance(
            self.response_schema, Mapping
        ):
            raise TypeError("response_schema must be a mapping")


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    provider_id: str
    adapter_name: str
    model: str
    outcome: str
    latency_ms: float
    usage: TokenUsage
    estimated_cost: float
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "adapter_name": self.adapter_name,
            "model": self.model,
            "outcome": self.outcome,
            "latency_ms": round(self.latency_ms, 4),
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
            },
            "estimated_cost": round(self.estimated_cost, 8),
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    spent_cost: float
    spent_output_tokens: int
    remaining_cost: float | None
    remaining_output_tokens: int | None
    remaining_provider_attempts: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "spent_cost": round(self.spent_cost, 8),
            "spent_output_tokens": self.spent_output_tokens,
            "remaining_cost": (
                None if self.remaining_cost is None else round(self.remaining_cost, 8)
            ),
            "remaining_output_tokens": self.remaining_output_tokens,
            "remaining_provider_attempts": self.remaining_provider_attempts,
        }


@dataclass(frozen=True, slots=True)
class RoutePlan:
    request_id: str
    provider_ids: tuple[str, ...]
    rejected: Mapping[str, tuple[str, ...]]

    @property
    def selected_provider_id(self) -> str | None:
        return self.provider_ids[0] if self.provider_ids else None

    @property
    def fallback_provider_ids(self) -> tuple[str, ...]:
        return self.provider_ids[1:]

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "provider_ids": list(self.provider_ids),
            "rejected": {key: list(value) for key, value in self.rejected.items()},
        }


@dataclass(frozen=True, slots=True)
class ModelRouteResult:
    request_id: str
    status: str
    selected_provider_id: str | None
    planned_provider_ids: tuple[str, ...]
    fallback_provider_ids: tuple[str, ...]
    response: ChatResponse | None
    attempts: tuple[AttemptRecord, ...]
    provenance: ProvenanceRecord
    trace: Mapping[str, Any]
    budget: BudgetSnapshot

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "selected_provider_id": self.selected_provider_id,
            "planned_provider_ids": list(self.planned_provider_ids),
            "fallback_provider_ids": list(self.fallback_provider_ids),
            "response": None
            if self.response is None
            else {
                "model": self.response.model,
                "text": self.response.text,
                "finish_reason": self.response.finish_reason,
                "usage": {
                    "input_tokens": self.response.usage.input_tokens,
                    "output_tokens": self.response.usage.output_tokens,
                },
            },
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "provenance": self.provenance.as_dict(),
            "trace": dict(self.trace),
            "budget": self.budget.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class RouteEvalCase:
    """One offline eval case against the routing contract."""

    case_id: str
    request: ModelRouteRequest
    expect_status: str | None = None
    expect_provider_id: str | None = None
    expect_capabilities: frozenset[str] | None = None
    require_provenance: bool = True
    forbid_secret_fragments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "case_id", _require_normalized_text(self.case_id, "case_id")
        )
        if not isinstance(self.request, ModelRouteRequest):
            raise TypeError("request must be a ModelRouteRequest")
        if self.expect_status is not None:
            object.__setattr__(
                self,
                "expect_status",
                _require_normalized_text(self.expect_status, "expect_status"),
            )
        if self.expect_provider_id is not None:
            object.__setattr__(
                self,
                "expect_provider_id",
                _require_normalized_text(self.expect_provider_id, "expect_provider_id"),
            )
        if self.expect_capabilities is not None:
            object.__setattr__(
                self,
                "expect_capabilities",
                _normalize_capabilities(
                    self.expect_capabilities, field_name="expect_capabilities"
                ),
            )
        if not isinstance(self.require_provenance, bool):
            raise TypeError("require_provenance must be a boolean")
        if not isinstance(self.forbid_secret_fragments, tuple):
            raise TypeError("forbid_secret_fragments must be a tuple")


@dataclass(frozen=True, slots=True)
class RouteEvalVerdict:
    case_id: str
    passed: bool
    reasons: tuple[str, ...]
    result: ModelRouteResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "status": self.result.status,
            "selected_provider_id": self.result.selected_provider_id,
        }


@dataclass(frozen=True, slots=True)
class RouteEvalReport:
    verdicts: tuple[RouteEvalVerdict, ...]

    @property
    def passed(self) -> bool:
        return all(verdict.passed for verdict in self.verdicts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verdicts": [verdict.as_dict() for verdict in self.verdicts],
        }


class RouteEvalContract:
    """Deterministic judge for routed request/result pairs."""

    def judge(
        self,
        case: RouteEvalCase,
        result: ModelRouteResult,
        *,
        catalog: Mapping[str, ProviderMetadata] | None = None,
    ) -> RouteEvalVerdict:
        if not isinstance(case, RouteEvalCase):
            raise TypeError("case must be a RouteEvalCase")
        if not isinstance(result, ModelRouteResult):
            raise TypeError("result must be a ModelRouteResult")
        if result.request_id != case.request.request_id:
            raise RouteRequestError("eval result request_id does not match the case")

        reasons: list[str] = []
        if case.expect_status is not None and result.status != case.expect_status:
            reasons.append(
                f"status {result.status!r} != expected {case.expect_status!r}"
            )
        if (
            case.expect_provider_id is not None
            and result.selected_provider_id != case.expect_provider_id
        ):
            reasons.append(
                "selected_provider_id "
                f"{result.selected_provider_id!r} != expected {case.expect_provider_id!r}"
            )
        if case.expect_capabilities and catalog is not None:
            selected = result.selected_provider_id
            if selected is None or selected not in catalog:
                reasons.append("selected provider missing from catalog")
            elif not case.expect_capabilities <= catalog[selected].capabilities:
                reasons.append("selected provider lacks expected capabilities")
        if case.require_provenance:
            provenance = result.provenance
            if not provenance.content_sha256:
                reasons.append("missing provenance digest")
            if provenance.operation != "model_route":
                reasons.append("provenance operation is not model_route")
            if result.ok and not provenance.actor:
                reasons.append("missing provenance actor")
        serialized = result.as_dict()
        haystack = repr(_redact_trace(serialized))
        for fragment in case.forbid_secret_fragments:
            if fragment and fragment in haystack:
                reasons.append("secret material leaked into result traces")
                break
        caller_keys = {
            str(key).lower().replace("-", "_") for key in case.request.metadata
        }
        trace_meta = result.trace.get("caller_metadata", {})
        leaked_metadata = caller_keys & _SENSITIVE_TRACE_KEYS and (
            not isinstance(trace_meta, Mapping)
            or any(
                str(key).lower().replace("-", "_") in _SENSITIVE_TRACE_KEYS
                and value != REDACTED
                for key, value in trace_meta.items()
            )
        )
        if leaked_metadata:
            reasons.append("caller metadata was not redacted")
        return RouteEvalVerdict(
            case_id=case.case_id,
            passed=not reasons,
            reasons=tuple(reasons),
            result=result,
        )

    async def run(
        self,
        router: ModelRouter,
        cases: Sequence[RouteEvalCase],
    ) -> RouteEvalReport:
        if not isinstance(router, ModelRouter):
            raise TypeError("router must be a ModelRouter")
        verdicts: list[RouteEvalVerdict] = []
        for case in cases:
            result = await router.invoke(case.request)
            verdicts.append(
                self.judge(case, result, catalog=router.catalog())
            )
        return RouteEvalReport(verdicts=tuple(verdicts))


class ModelRouter:
    """Capability-based router with bounded fallback over ``ModelRuntime``."""

    def __init__(self, runtime: ModelRuntime | None = None) -> None:
        if runtime is not None and not isinstance(runtime, ModelRuntime):
            raise TypeError("runtime must be a ModelRuntime")
        self._runtime = runtime if runtime is not None else ModelRuntime()
        self._providers: dict[str, ProviderMetadata] = {}

    @property
    def runtime(self) -> ModelRuntime:
        return self._runtime

    def catalog(self) -> dict[str, ProviderMetadata]:
        return dict(self._providers)

    def register(
        self,
        metadata: ProviderMetadata | Mapping[str, Any],
        adapter: ProviderAdapter,
        *,
        replace: bool = False,
    ) -> ProviderMetadata:
        parsed = (
            metadata
            if isinstance(metadata, ProviderMetadata)
            else ProviderMetadata.from_mapping(metadata)
        )
        # Fail before touching ModelRuntime. A rejected duplicate provider must
        # not leak a newly named adapter into the runtime registry.
        if parsed.provider_id in self._providers and not replace:
            raise ProviderMetadataError(
                f"provider already registered: {parsed.provider_id}"
            )
        if not hasattr(adapter, "name") or not hasattr(adapter, "capabilities"):
            raise ProviderMetadataError("adapter must declare name and capabilities")
        adapter_name = _require_normalized_text(adapter.name, "adapter name")
        if adapter_name != parsed.adapter_name:
            raise ProviderMetadataError(
                f"adapter name {adapter_name!r} != metadata adapter_name "
                f"{parsed.adapter_name!r}"
            )
        adapter_caps = _normalize_capabilities(
            adapter.capabilities, field_name="adapter capabilities", allow_empty=True
        )
        missing_execution = (
            parsed.capabilities & _EXECUTION_CAPABILITIES
        ) - adapter_caps
        if missing_execution:
            raise ProviderMetadataError(
                "adapter lacks claimed execution capabilities: "
                + ", ".join(sorted(missing_execution))
            )
        existing_runtime = None
        try:
            existing_runtime = self._runtime.resolve(adapter_name)
        except KeyError:
            existing_runtime = None
        if existing_runtime is None:
            self._runtime.register(adapter)
        elif existing_runtime is not adapter:
            raise ProviderMetadataError(
                f"adapter name already registered with a different adapter: {adapter_name}"
            )
        self._providers[parsed.provider_id] = parsed
        return parsed

    def plan(self, request: ModelRouteRequest) -> RoutePlan:
        if not isinstance(request, ModelRouteRequest):
            raise TypeError("request must be a ModelRouteRequest")
        required = request.required_capabilities
        rejected: dict[str, tuple[str, ...]] = {}
        eligible: list[ProviderMetadata] = []
        for metadata in self._providers.values():
            reasons = self._rejection_reasons(metadata, request, required)
            if reasons:
                rejected[metadata.provider_id] = tuple(reasons)
                continue
            eligible.append(metadata)
        eligible.sort(
            key=lambda item: (
                item.priority,
                _estimate_cost(
                    item,
                    input_tokens=request.estimated_input_tokens,
                    output_tokens=_planned_output_tokens(
                        item,
                        request,
                        remaining_output=request.budget.max_output_tokens,
                    ),
                ),
                item.timeout_seconds,
                item.provider_id,
            )
        )
        limited = eligible[: request.budget.max_provider_attempts]
        return RoutePlan(
            request_id=request.request_id,
            provider_ids=tuple(item.provider_id for item in limited),
            rejected=rejected,
        )

    async def invoke(self, request: ModelRouteRequest) -> ModelRouteResult:
        plan = self.plan(request)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + request.timeout_seconds
        spent_cost = 0.0
        spent_output = 0
        attempts: list[AttemptRecord] = []
        selected_id: str | None = None
        response: ChatResponse | None = None
        budget_rejected = any(
            any("route budget" in reason or "output token budget" in reason for reason in reasons)
            for reasons in plan.rejected.values()
        )
        status = (
            "budget_exhausted"
            if not plan.provider_ids and budget_rejected
            else "no_capable_provider"
            if not plan.provider_ids
            else "provider_failed"
        )

        for provider_id in plan.provider_ids:
            remaining_time = deadline - loop.time()
            if remaining_time <= 0:
                status = "timeout"
                break
            metadata = self._providers[provider_id]
            remaining_cost = (
                None
                if request.budget.max_cost is None
                else max(0.0, request.budget.max_cost - spent_cost)
            )
            remaining_output = (
                None
                if request.budget.max_output_tokens is None
                else max(0, request.budget.max_output_tokens - spent_output)
            )
            if remaining_output is not None and remaining_output <= 0:
                status = "budget_exhausted"
                break
            planned_output = _planned_output_tokens(
                metadata,
                request,
                remaining_output=remaining_output,
            )
            estimated = _estimate_cost(
                metadata,
                input_tokens=request.estimated_input_tokens,
                output_tokens=planned_output,
            )
            if remaining_cost is not None and estimated > remaining_cost:
                status = "budget_exhausted"
                continue

            started = loop.time()
            try:
                chat = ChatRequest(
                    model=metadata.model,
                    messages=request.messages,
                    tools=request.tools,
                    response_schema=request.response_schema,
                    max_output_tokens=planned_output,
                    temperature=request.temperature,
                )
                provider_timeout = min(metadata.timeout_seconds, remaining_time)
                response = await self._runtime.chat(
                    metadata.adapter_name,
                    chat,
                    timeout_seconds=provider_timeout,
                    retry_policy=metadata.retry_policy(request.retry_policy),
                )
            except ProviderCancelledError:
                latency_ms = (loop.time() - started) * 1000.0
                attempts.append(
                    AttemptRecord(
                        provider_id=metadata.provider_id,
                        adapter_name=metadata.adapter_name,
                        model=metadata.model,
                        outcome="cancelled",
                        latency_ms=latency_ms,
                        usage=TokenUsage(),
                        estimated_cost=0.0,
                        error_type="ProviderCancelledError",
                    )
                )
                status = "cancelled"
                response = None
                break
            except ProviderTimeoutError:
                latency_ms = (loop.time() - started) * 1000.0
                attempts.append(
                    AttemptRecord(
                        provider_id=metadata.provider_id,
                        adapter_name=metadata.adapter_name,
                        model=metadata.model,
                        outcome="timeout",
                        latency_ms=latency_ms,
                        usage=TokenUsage(),
                        estimated_cost=0.0,
                        error_type="ProviderTimeoutError",
                    )
                )
                status = "timeout"
                continue
            except ProviderError as exc:
                latency_ms = (loop.time() - started) * 1000.0
                attempts.append(
                    AttemptRecord(
                        provider_id=metadata.provider_id,
                        adapter_name=metadata.adapter_name,
                        model=metadata.model,
                        outcome="error",
                        latency_ms=latency_ms,
                        usage=TokenUsage(),
                        estimated_cost=0.0,
                        error_type=safe_exception_text(exc),
                    )
                )
                status = "provider_failed"
                continue

            latency_ms = (loop.time() - started) * 1000.0
            actual_cost = _usage_cost(metadata, response.usage)
            spent_cost += actual_cost
            spent_output += response.usage.output_tokens
            cost_exhausted = (
                request.budget.max_cost is not None
                and spent_cost > request.budget.max_cost
            )
            output_exhausted = (
                request.budget.max_output_tokens is not None
                and spent_output > request.budget.max_output_tokens
            )
            provider_output_exhausted = response.usage.output_tokens > planned_output
            if cost_exhausted or output_exhausted or provider_output_exhausted:
                attempts.append(
                    AttemptRecord(
                        provider_id=metadata.provider_id,
                        adapter_name=metadata.adapter_name,
                        model=metadata.model,
                        outcome="budget_exhausted",
                        latency_ms=latency_ms,
                        usage=response.usage,
                        estimated_cost=actual_cost,
                    )
                )
                status = "budget_exhausted"
                response = None
                break
            attempts.append(
                AttemptRecord(
                    provider_id=metadata.provider_id,
                    adapter_name=metadata.adapter_name,
                    model=metadata.model,
                    outcome="ok",
                    latency_ms=latency_ms,
                    usage=response.usage,
                    estimated_cost=actual_cost,
                )
            )
            selected_id = metadata.provider_id
            status = "ok"
            break

        return self._result(
            request=request,
            plan=plan,
            status=status,
            selected_provider_id=selected_id,
            response=response,
            attempts=tuple(attempts),
            spent_cost=spent_cost,
            spent_output_tokens=spent_output,
        )

    def _rejection_reasons(
        self,
        metadata: ProviderMetadata,
        request: ModelRouteRequest,
        required: frozenset[str],
    ) -> list[str]:
        reasons: list[str] = []
        if not metadata.enabled:
            reasons.append("disabled")
        missing = required - metadata.capabilities
        if missing:
            reasons.append("missing capabilities: " + ",".join(sorted(missing)))
        planned_output = _planned_output_tokens(
            metadata,
            request,
            remaining_output=request.budget.max_output_tokens,
        )
        if request.estimated_input_tokens > metadata.max_input_tokens:
            reasons.append(
                "input tokens "
                f"{request.estimated_input_tokens} exceeds {metadata.max_input_tokens}"
            )
        if (
            request.max_output_tokens is not None
            and request.max_output_tokens > metadata.max_output_tokens
        ):
            reasons.append("output tokens exceed provider maximum")
        if request.budget.max_output_tokens is not None and request.budget.max_output_tokens <= 0:
            reasons.append("output token budget exhausted")
        estimated = _estimate_cost(
            metadata,
            input_tokens=request.estimated_input_tokens,
            output_tokens=planned_output,
        )
        if request.budget.max_cost is not None and estimated > request.budget.max_cost:
            reasons.append("estimated cost exceeds route budget")
        return reasons

    def _result(
        self,
        *,
        request: ModelRouteRequest,
        plan: RoutePlan,
        status: str,
        selected_provider_id: str | None,
        response: ChatResponse | None,
        attempts: tuple[AttemptRecord, ...],
        spent_cost: float,
        spent_output_tokens: int,
    ) -> ModelRouteResult:
        remaining_cost = (
            None
            if request.budget.max_cost is None
            else max(0.0, request.budget.max_cost - spent_cost)
        )
        remaining_output = (
            None
            if request.budget.max_output_tokens is None
            else max(0, request.budget.max_output_tokens - spent_output_tokens)
        )
        budget = BudgetSnapshot(
            spent_cost=spent_cost,
            spent_output_tokens=spent_output_tokens,
            remaining_cost=remaining_cost,
            remaining_output_tokens=remaining_output,
            remaining_provider_attempts=max(
                0, request.budget.max_provider_attempts - len(attempts)
            ),
        )
        payload = {
            "request_id": request.request_id,
            "status": status,
            "selected_provider_id": selected_provider_id,
            "model": None if response is None else response.model,
            "text_digest": None
            if response is None
            else stable_content_digest(response.text),
            "attempts": [attempt.as_dict() for attempt in attempts],
        }
        provenance = ProvenanceRecord.for_artifact(
            source_repository="runtime://model-routing",
            payload=payload,
            operation="model_route",
            actor=selected_provider_id or "model-router",
            metadata={
                "request_id": request.request_id,
                "required_capabilities": sorted(request.required_capabilities),
                "status": status,
            },
        )
        trace = _redact_trace(
            {
                "request_id": request.request_id,
                "required_capabilities": sorted(request.required_capabilities),
                "planned_provider_ids": list(plan.provider_ids),
                "rejected": plan.as_dict()["rejected"],
                "attempts": [attempt.as_dict() for attempt in attempts],
                "status": status,
                "selected_provider_id": selected_provider_id,
                "caller_metadata": dict(request.metadata),
            }
        )
        return ModelRouteResult(
            request_id=request.request_id,
            status=status,
            selected_provider_id=selected_provider_id,
            planned_provider_ids=plan.provider_ids,
            fallback_provider_ids=plan.fallback_provider_ids,
            response=response,
            attempts=attempts,
            provenance=provenance,
            trace=trace,
            budget=budget,
        )


__all__ = [
    "AttemptRecord",
    "BudgetSnapshot",
    "ModelRouteRequest",
    "ModelRouteResult",
    "ModelRouter",
    "ModelRoutingError",
    "ProviderMetadata",
    "ProviderMetadataError",
    "RouteBudget",
    "RouteEvalCase",
    "RouteEvalContract",
    "RouteEvalReport",
    "RouteEvalVerdict",
    "RoutePlan",
    "RouteRequestError",
]
