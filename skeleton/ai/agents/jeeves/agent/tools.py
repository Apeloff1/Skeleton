"""Capability registry and deterministic tool execution for Jeeves.

The model never owns capabilities.  Tools are registered by trusted host code,
then separately granted to a run through ``ToolGrant`` objects.  Arguments are
validated before handlers see them; budgets, timeouts, idempotency, caching,
and evidence conversion are all enforced outside the model.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    EvidenceKind,
    EvidenceRef,
    RiskTier,
    ToolCall,
    ToolObservation,
    finite_number,
    json_safe,
    positive_int,
    require_id,
    require_tool_name,
    stable_fingerprint,
    stable_id,
)


class ToolError(RuntimeError):
    pass


class ToolDenied(ToolError):
    pass


class ToolTimeout(ToolError):
    pass


class ToolValidationError(ToolError):
    pass


@dataclass(frozen=True, slots=True)
class ArgumentRule:
    name: str
    type_name: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()
    max_length: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_id("argument name", self.name))
        allowed = {"string", "integer", "number", "boolean", "object", "array"}
        normalized = str(self.type_name).strip().lower()
        if normalized not in allowed:
            raise AgentContractError("unsupported argument type", context={"type": normalized})
        object.__setattr__(self, "type_name", normalized)
        if self.minimum is not None:
            object.__setattr__(self, "minimum", finite_number("minimum", self.minimum))
        if self.maximum is not None:
            object.__setattr__(self, "maximum", finite_number("maximum", self.maximum))
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise AgentContractError("argument minimum exceeds maximum")
        choices = tuple(json_safe(value) for value in self.choices)
        object.__setattr__(self, "choices", choices)
        if self.max_length is not None:
            object.__setattr__(self, "max_length", positive_int("max_length", self.max_length, maximum=1_000_000))
        object.__setattr__(self, "description", str(self.description).strip()[:2048])

    def validate(self, value: Any) -> Any:
        value = json_safe(value)
        if self.type_name == "string":
            if not isinstance(value, str):
                raise ToolValidationError(f"{self.name} must be a string")
            if self.max_length is not None and len(value) > self.max_length:
                raise ToolValidationError(f"{self.name} exceeds maximum length")
        elif self.type_name == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolValidationError(f"{self.name} must be an integer")
            self._validate_range(float(value))
        elif self.type_name == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ToolValidationError(f"{self.name} must be numeric")
            number = finite_number(self.name, value)
            self._validate_range(number)
        elif self.type_name == "boolean":
            if not isinstance(value, bool):
                raise ToolValidationError(f"{self.name} must be boolean")
        elif self.type_name == "object":
            if not isinstance(value, dict):
                raise ToolValidationError(f"{self.name} must be an object")
            if self.max_length is not None and len(value) > self.max_length:
                raise ToolValidationError(f"{self.name} has too many keys")
        elif self.type_name == "array":
            if not isinstance(value, list):
                raise ToolValidationError(f"{self.name} must be an array")
            if self.max_length is not None and len(value) > self.max_length:
                raise ToolValidationError(f"{self.name} has too many items")
        if self.choices and value not in self.choices:
            raise ToolValidationError(f"{self.name} is not an allowed choice")
        return value

    def _validate_range(self, number: float) -> None:
        if self.minimum is not None and number < self.minimum:
            raise ToolValidationError(f"{self.name} is below minimum")
        if self.maximum is not None and number > self.maximum:
            raise ToolValidationError(f"{self.name} is above maximum")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    risk: RiskTier = RiskTier.READ_ONLY
    arguments: tuple[ArgumentRule, ...] = ()
    allow_extra_arguments: bool = False
    idempotent: bool = True
    cache_ttl_seconds: float | None = None
    timeout_seconds: float = 20.0
    produces_evidence: bool = True
    evidence_kind: EvidenceKind = EvidenceKind.TOOL

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_tool_name(self.name))
        description = str(self.description).strip()
        if not description or len(description) > 4096:
            raise AgentContractError("tool description must be 1..4096 characters")
        object.__setattr__(self, "description", description)
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        rules = tuple(self.arguments)
        if any(not isinstance(rule, ArgumentRule) for rule in rules):
            raise AgentContractError("tool arguments must be ArgumentRule values")
        names = [rule.name for rule in rules]
        if len(set(names)) != len(names):
            raise AgentContractError("duplicate tool argument rule")
        object.__setattr__(self, "arguments", rules)
        if self.cache_ttl_seconds is not None:
            ttl = finite_number("cache_ttl_seconds", self.cache_ttl_seconds)
            if ttl <= 0:
                raise AgentContractError("cache_ttl_seconds must be > 0")
            object.__setattr__(self, "cache_ttl_seconds", ttl)
        timeout = finite_number("timeout_seconds", self.timeout_seconds)
        if timeout <= 0 or timeout > 600:
            raise AgentContractError("timeout_seconds must be in (0, 600]")
        object.__setattr__(self, "timeout_seconds", timeout)
        if not isinstance(self.evidence_kind, EvidenceKind):
            object.__setattr__(self, "evidence_kind", EvidenceKind(str(self.evidence_kind)))

    def validate_arguments(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ToolValidationError("tool arguments must be an object")
        raw = dict(arguments)
        rules = {rule.name: rule for rule in self.arguments}
        missing = [name for name, rule in rules.items() if rule.required and name not in raw]
        if missing:
            raise ToolValidationError("missing required arguments: " + ", ".join(sorted(missing)))
        extra = set(raw) - set(rules)
        if extra and not self.allow_extra_arguments:
            raise ToolValidationError("unexpected arguments: " + ", ".join(sorted(extra)))
        result: dict[str, Any] = {}
        for name, value in raw.items():
            rule = rules.get(name)
            result[name] = rule.validate(value) if rule is not None else json_safe(value)
        return result

    def schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for rule in self.arguments:
            item: dict[str, Any] = {"type": rule.type_name, "description": rule.description}
            if rule.minimum is not None:
                item["minimum"] = rule.minimum
            if rule.maximum is not None:
                item["maximum"] = rule.maximum
            if rule.max_length is not None:
                item["maxLength" if rule.type_name == "string" else "maxItems"] = rule.max_length
            if rule.choices:
                item["enum"] = list(rule.choices)
            properties[rule.name] = item
            if rule.required:
                required.append(rule.name)
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk.value,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": self.allow_extra_arguments,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolGrant:
    tool_name: str
    allowed_risks: tuple[RiskTier, ...] = (RiskTier.READ_ONLY,)
    expires_at: float | None = None
    max_calls: int = 1
    argument_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", require_tool_name(self.tool_name))
        risks = tuple(risk if isinstance(risk, RiskTier) else RiskTier(str(risk)) for risk in self.allowed_risks)
        if not risks:
            raise AgentContractError("tool grant requires at least one allowed risk")
        object.__setattr__(self, "allowed_risks", risks)
        if self.expires_at is not None:
            expiry = finite_number("expires_at", self.expires_at)
            if expiry < 0:
                raise AgentContractError("expires_at must be non-negative")
            object.__setattr__(self, "expires_at", expiry)
        object.__setattr__(self, "max_calls", positive_int("max_calls", self.max_calls, maximum=1000))
        if self.argument_fingerprint is not None:
            object.__setattr__(self, "argument_fingerprint", str(self.argument_fingerprint).strip()[:128])

    def permits(self, spec: ToolSpec, arguments: Mapping[str, Any], *, now: float) -> bool:
        if spec.name != self.tool_name or spec.risk not in self.allowed_risks:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        if self.argument_fingerprint is not None:
            return stable_fingerprint(arguments) == self.argument_fingerprint
        return True


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    run_id: str
    user_id: str
    trace_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        object.__setattr__(self, "trace_id", require_id("trace_id", self.trace_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


ToolHandler = Callable[[Mapping[str, Any], ToolExecutionContext], Any]
EvidenceBuilder = Callable[[ToolCall, Any], Sequence[EvidenceRef]]


@dataclass(slots=True)
class _RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler
    evidence_builder: EvidenceBuilder | None = None


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    observation: ToolObservation


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}
        self._lock = threading.RLock()

    def register(
        self,
        spec: ToolSpec,
        handler: ToolHandler,
        *,
        evidence_builder: EvidenceBuilder | None = None,
    ) -> None:
        if not isinstance(spec, ToolSpec):
            raise TypeError("spec must be ToolSpec")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if evidence_builder is not None and not callable(evidence_builder):
            raise TypeError("evidence_builder must be callable")
        with self._lock:
            if spec.name in self._tools:
                raise ToolError(f"tool already registered: {spec.name}")
            self._tools[spec.name] = _RegisteredTool(spec, handler, evidence_builder)

    def get(self, name: str) -> _RegisteredTool | None:
        with self._lock:
            return self._tools.get(require_tool_name(name))

    def specs(self) -> tuple[ToolSpec, ...]:
        with self._lock:
            return tuple(self._tools[name].spec for name in sorted(self._tools))

    def model_schemas(self, allowed: Iterable[str] | None = None) -> tuple[dict[str, Any], ...]:
        allowed_set = None if allowed is None else {require_tool_name(name) for name in allowed}
        return tuple(
            spec.schema()
            for spec in self.specs()
            if allowed_set is None or spec.name in allowed_set
        )


class ToolExecutor:
    """Execute granted tools under per-run and per-grant budgets."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        max_workers: int = 4,
    ) -> None:
        self._registry = registry
        self._clock = clock
        self._monotonic = monotonic
        self._max_workers = positive_int("max_workers", max_workers, maximum=32)
        self._cache: dict[str, _CacheEntry] = {}
        self._grant_usage: dict[tuple[str, str], int] = {}
        self._idempotency: dict[tuple[str, str], ToolObservation] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        call: ToolCall,
        context: ToolExecutionContext,
        *,
        grants: Sequence[ToolGrant],
    ) -> ToolObservation:
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        registered = self._registry.get(call.name)
        if registered is None:
            raise ToolDenied(f"tool is not registered: {call.name}")
        spec = registered.spec
        arguments = spec.validate_arguments(call.arguments)
        grant = self._select_grant(spec, arguments, context, grants)
        self._consume_grant(context, grant)

        idempotency_key = stable_fingerprint({"tool": spec.name, "arguments": arguments, "run": context.run_id})
        if spec.idempotent:
            with self._lock:
                prior = self._idempotency.get((context.run_id, idempotency_key))
            if prior is not None:
                return ToolObservation(
                    call_id=call.call_id,
                    tool_name=prior.tool_name,
                    ok=prior.ok,
                    payload=prior.payload,
                    error=prior.error,
                    evidence=prior.evidence,
                    latency_ms=0.0,
                    cached=True,
                )

        cache_key = stable_fingerprint({"tool": spec.name, "arguments": arguments})
        cached = self._cache_get(cache_key, spec)
        if cached is not None:
            return ToolObservation(
                call_id=call.call_id,
                tool_name=cached.tool_name,
                ok=cached.ok,
                payload=cached.payload,
                error=cached.error,
                evidence=cached.evidence,
                latency_ms=0.0,
                cached=True,
            )

        started = self._monotonic()
        try:
            payload = self._invoke_with_timeout(registered.handler, arguments, context, spec.timeout_seconds)
            payload = json_safe(payload)
            evidence = self._build_evidence(registered, call, payload, spec)
            observation = ToolObservation(
                call_id=call.call_id,
                tool_name=spec.name,
                ok=True,
                payload=payload,
                evidence=evidence,
                latency_ms=(self._monotonic() - started) * 1000.0,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            observation = ToolObservation(
                call_id=call.call_id,
                tool_name=spec.name,
                ok=False,
                payload=None,
                error=f"{type(exc).__name__}: {str(exc)[:1024]}",
                evidence=(),
                latency_ms=(self._monotonic() - started) * 1000.0,
            )

        if spec.idempotent:
            with self._lock:
                self._idempotency[(context.run_id, idempotency_key)] = observation
        if observation.ok and spec.cache_ttl_seconds is not None:
            with self._lock:
                self._cache[cache_key] = _CacheEntry(self._clock() + spec.cache_ttl_seconds, observation)
        return observation

    def _select_grant(
        self,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
        grants: Sequence[ToolGrant],
    ) -> ToolGrant:
        now = self._clock()
        matches = [grant for grant in grants if grant.permits(spec, arguments, now=now)]
        if not matches:
            raise ToolDenied(f"no active grant permits tool {spec.name} at risk {spec.risk.value}")
        matches.sort(key=lambda grant: (grant.expires_at is None, grant.expires_at or float("inf"), grant.max_calls))
        for grant in matches:
            used = self._grant_usage.get((context.run_id, self._grant_key(grant)), 0)
            if used < grant.max_calls:
                return grant
        raise ToolDenied(f"all grants exhausted for tool {spec.name}")

    @staticmethod
    def _grant_key(grant: ToolGrant) -> str:
        return stable_fingerprint(
            {
                "tool": grant.tool_name,
                "risks": [risk.value for risk in grant.allowed_risks],
                "expires_at": grant.expires_at,
                "max_calls": grant.max_calls,
                "argument_fingerprint": grant.argument_fingerprint,
            }
        )

    def _consume_grant(self, context: ToolExecutionContext, grant: ToolGrant) -> None:
        key = (context.run_id, self._grant_key(grant))
        with self._lock:
            current = self._grant_usage.get(key, 0)
            if current >= grant.max_calls:
                raise ToolDenied("tool grant call budget exhausted")
            self._grant_usage[key] = current + 1

    def _cache_get(self, cache_key: str, spec: ToolSpec) -> ToolObservation | None:
        if spec.cache_ttl_seconds is None:
            return None
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                self._cache.pop(cache_key, None)
                return None
            return entry.observation

    def _invoke_with_timeout(
        self,
        handler: ToolHandler,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
        timeout: float,
    ) -> Any:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="jeeves-tool")
        future = executor.submit(handler, arguments, context)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ToolTimeout(f"tool exceeded timeout of {timeout:.3f}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_evidence(
        self,
        registered: _RegisteredTool,
        call: ToolCall,
        payload: Any,
        spec: ToolSpec,
    ) -> tuple[EvidenceRef, ...]:
        if not spec.produces_evidence:
            return ()
        if registered.evidence_builder is not None:
            refs = tuple(registered.evidence_builder(call, payload))
            if any(not isinstance(ref, EvidenceRef) for ref in refs):
                raise ToolValidationError("evidence builder returned non-EvidenceRef")
            return refs
        fingerprint = stable_fingerprint(payload)
        evidence_id = stable_id(
            "evidence",
            {"tool": spec.name, "call": call.call_id, "arguments": call.arguments, "payload": fingerprint},
        )
        return (
            EvidenceRef(
                evidence_id=evidence_id,
                kind=spec.evidence_kind,
                source=f"tool:{spec.name}",
                fingerprint=fingerprint,
                confidence=1.0,
                observed_at=self._clock(),
            ),
        )

    def clear_run(self, run_id: str) -> None:
        run_id = require_id("run_id", run_id)
        with self._lock:
            self._grant_usage = {key: value for key, value in self._grant_usage.items() if key[0] != run_id}
            self._idempotency = {key: value for key, value in self._idempotency.items() if key[0] != run_id}

    def cache_stats(self) -> dict[str, int]:
        now = self._clock()
        with self._lock:
            expired = [key for key, entry in self._cache.items() if now >= entry.expires_at]
            for key in expired:
                self._cache.pop(key, None)
            return {"entries": len(self._cache), "idempotency_entries": len(self._idempotency)}


def function_tool(
    name: str,
    description: str,
    handler: ToolHandler,
    *,
    arguments: Sequence[ArgumentRule] = (),
    risk: RiskTier = RiskTier.READ_ONLY,
    timeout_seconds: float = 20.0,
    cache_ttl_seconds: float | None = None,
    idempotent: bool = True,
    produces_evidence: bool = True,
) -> tuple[ToolSpec, ToolHandler]:
    spec = ToolSpec(
        name=name,
        description=description,
        risk=risk,
        arguments=tuple(arguments),
        timeout_seconds=timeout_seconds,
        cache_ttl_seconds=cache_ttl_seconds,
        idempotent=idempotent,
        produces_evidence=produces_evidence,
    )
    return spec, handler
