"""Typed contracts shared by the evidence-first Jeeves agent runtime.

The runtime treats model output as untrusted proposals.  These value objects
are the boundary between probabilistic generation and deterministic host code:
plans, tool calls, evidence, claims, budgets, usage, model traffic, and final
results are all validated before they move between subsystems.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_MAX_TEXT = 128_000
_MAX_JSON_DEPTH = 12
_MAX_JSON_NODES = 10_000


class AgentContractError(ValueError):
    """Raised when data crossing an agent boundary violates its contract."""

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = dict(context or {})


class AgentPhase(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"
    REQUIRE_CONFIRMATION = "require_confirmation"


class RiskTier(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    MUTATING = "mutating"
    EXTERNAL = "external"
    HIGH_IMPACT = "high_impact"


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TerminationReason(str, Enum):
    GOAL_REACHED = "goal_reached"
    MAX_STEPS = "max_steps"
    MAX_MODEL_CALLS = "max_model_calls"
    MAX_TOOL_CALLS = "max_tool_calls"
    MAX_TOKENS = "max_tokens"
    WALL_CLOCK = "wall_clock"
    POLICY_DENIED = "policy_denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    PLAN_INVALID = "plan_invalid"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TOOL_FAILURE = "tool_failure"
    VERIFICATION_FAILED = "verification_failed"
    GROUNDING_FAILED = "grounding_failed"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"


class EvidenceKind(str, Enum):
    USER = "user"
    TOOL = "tool"
    RETRIEVAL = "retrieval"
    DATABASE = "database"
    FILE = "file"
    API = "api"
    SENSOR = "sensor"
    FIXTURE = "fixture"
    MEMORY = "memory"
    DERIVED = "derived"


class MemoryKind(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    PROFILE = "profile"


class ModelRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentContractError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AgentContractError(f"{name} must be finite")
    return result


def probability(name: str, value: Any) -> float:
    result = finite_number(name, value)
    if not 0.0 <= result <= 1.0:
        raise AgentContractError(f"{name} must be in [0, 1]")
    return result


def positive_int(name: str, value: Any, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AgentContractError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise AgentContractError(f"{name} exceeds maximum {maximum}")
    return value


def non_negative_int(name: str, value: Any, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentContractError(f"{name} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise AgentContractError(f"{name} exceeds maximum {maximum}")
    return value


def require_id(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise AgentContractError(f"{name} must be a string identifier")
    normalized = value.strip()
    if not _ID_RE.fullmatch(normalized):
        raise AgentContractError(f"{name} is not a valid identifier")
    return normalized


def require_tool_name(value: Any) -> str:
    if not isinstance(value, str):
        raise AgentContractError("tool name must be a string")
    normalized = value.strip().lower()
    if not _TOOL_RE.fullmatch(normalized):
        raise AgentContractError("invalid tool name")
    return normalized


def bounded_text(name: str, value: Any, *, maximum: int = _MAX_TEXT, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AgentContractError(f"{name} must be text")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise AgentContractError(f"{name} must be non-empty")
    if len(normalized) > maximum:
        raise AgentContractError(f"{name} exceeds {maximum} characters")
    return normalized


def json_safe(value: Any) -> Any:
    """Copy a value into a bounded JSON-only representation.

    This intentionally rejects arbitrary Python objects instead of calling
    ``default=str``.  Boundary data should be serializable by construction;
    silently stringifying custom objects can execute attacker-controlled code
    and destroys deterministic replay semantics.
    """

    budget = [_MAX_JSON_NODES]

    def walk(item: Any, depth: int) -> Any:
        if depth > _MAX_JSON_DEPTH:
            raise AgentContractError("JSON value exceeds maximum depth")
        budget[0] -= 1
        if budget[0] < 0:
            raise AgentContractError("JSON value exceeds node budget")
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise AgentContractError("JSON numbers must be finite")
            return float(item)
        if type(item) is str:
            if len(item) > _MAX_TEXT:
                raise AgentContractError("JSON string exceeds size limit")
            return item
        if type(item) in {list, tuple}:
            return [walk(child, depth + 1) for child in item]
        if type(item) is dict:
            result: dict[str, Any] = {}
            for key, child in item.items():
                if type(key) is not str or not key:
                    raise AgentContractError("JSON object keys must be non-empty strings")
                if len(key) > 512:
                    raise AgentContractError("JSON object key exceeds size limit")
                result[key] = walk(child, depth + 1)
            return result
        raise AgentContractError(f"unsupported JSON value type: {type(item).__name__}")

    return walk(value, 0)


def canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any, *, length: int = 20) -> str:
    prefix = require_id("prefix", prefix)
    if isinstance(length, bool) or not isinstance(length, int) or not 8 <= length <= 64:
        raise AgentContractError("stable id length must be in [8, 64]")
    return f"{prefix}:{stable_fingerprint(value)[:length]}"


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    objective: str
    success_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", require_id("goal_id", self.goal_id))
        object.__setattr__(self, "objective", bounded_text("objective", self.objective, maximum=32_000))
        criteria = tuple(bounded_text("success criterion", item, maximum=4096) for item in self.success_criteria)
        constraints = tuple(bounded_text("constraint", item, maximum=4096) for item in self.constraints)
        if len(criteria) > 64 or len(constraints) > 64:
            raise AgentContractError("goal has too many criteria or constraints")
        object.__setattr__(self, "success_criteria", criteria)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class Budget:
    max_steps: int = 24
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_tokens: int = 64_000
    max_wall_seconds: float = 180.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_steps", positive_int("max_steps", self.max_steps, maximum=10_000))
        object.__setattr__(self, "max_model_calls", positive_int("max_model_calls", self.max_model_calls, maximum=10_000))
        object.__setattr__(self, "max_tool_calls", positive_int("max_tool_calls", self.max_tool_calls, maximum=100_000))
        object.__setattr__(self, "max_tokens", positive_int("max_tokens", self.max_tokens, maximum=100_000_000))
        wall = finite_number("max_wall_seconds", self.max_wall_seconds)
        if wall <= 0 or wall > 86_400:
            raise AgentContractError("max_wall_seconds must be in (0, 86400]")
        object.__setattr__(self, "max_wall_seconds", wall)


@dataclass(frozen=True, slots=True)
class Usage:
    steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_model_calls: int = 0

    def __post_init__(self) -> None:
        for name in ("steps", "model_calls", "tool_calls", "prompt_tokens", "completion_tokens", "cached_model_calls"):
            object.__setattr__(self, name, non_negative_int(name, getattr(self, name), maximum=1_000_000_000))

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(
        self,
        *,
        steps: int = 0,
        model_calls: int = 0,
        tool_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_model_calls: int = 0,
    ) -> "Usage":
        values = {
            "steps": steps,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_model_calls": cached_model_calls,
        }
        for name, value in values.items():
            non_negative_int(name, value)
        return Usage(
            steps=self.steps + steps,
            model_calls=self.model_calls + model_calls,
            tool_calls=self.tool_calls + tool_calls,
            prompt_tokens=self.prompt_tokens + prompt_tokens,
            completion_tokens=self.completion_tokens + completion_tokens,
            cached_model_calls=self.cached_model_calls + cached_model_calls,
        )


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    kind: EvidenceKind
    source: str
    fingerprint: str
    confidence: float = 1.0
    observed_at: float = field(default_factory=time.time)
    uri: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", require_id("evidence_id", self.evidence_id))
        if not isinstance(self.kind, EvidenceKind):
            object.__setattr__(self, "kind", EvidenceKind(str(self.kind)))
        object.__setattr__(self, "source", bounded_text("evidence source", self.source, maximum=1024))
        fingerprint = str(self.fingerprint).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{32,128}", fingerprint):
            raise AgentContractError("evidence fingerprint must be hexadecimal")
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "confidence", probability("evidence confidence", self.confidence))
        observed = finite_number("observed_at", self.observed_at)
        if observed < 0:
            raise AgentContractError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", observed)
        if self.uri is not None:
            object.__setattr__(self, "uri", bounded_text("evidence uri", self.uri, maximum=4096))


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    text: str
    confidence: float
    evidence: tuple[EvidenceRef, ...] = ()
    derived: bool = True
    subject: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", require_id("claim_id", self.claim_id))
        object.__setattr__(self, "text", bounded_text("claim text", self.text, maximum=16_384))
        object.__setattr__(self, "confidence", probability("claim confidence", self.confidence))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("claim evidence must contain EvidenceRef values")
        if len({ref.evidence_id for ref in refs}) != len(refs):
            raise AgentContractError("claim evidence contains duplicate ids")
        object.__setattr__(self, "evidence", refs)
        if self.subject is not None:
            object.__setattr__(self, "subject", bounded_text("claim subject", self.subject, maximum=512))


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", require_id("call_id", self.call_id))
        object.__setattr__(self, "name", require_tool_name(self.name))
        object.__setattr__(self, "arguments", json_safe(dict(self.arguments)))
        object.__setattr__(self, "reason", bounded_text("tool reason", self.reason, maximum=4096, allow_empty=True))


@dataclass(frozen=True, slots=True)
class ToolObservation:
    call_id: str
    tool_name: str
    ok: bool
    payload: Any = None
    error: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    latency_ms: float = 0.0
    cached: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", require_id("call_id", self.call_id))
        object.__setattr__(self, "tool_name", require_tool_name(self.tool_name))
        if not isinstance(self.ok, bool):
            raise AgentContractError("tool observation ok must be boolean")
        object.__setattr__(self, "payload", json_safe(self.payload))
        if self.error is not None:
            object.__setattr__(self, "error", bounded_text("tool error", self.error, maximum=8192))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("tool evidence must contain EvidenceRef values")
        object.__setattr__(self, "evidence", refs)
        latency = finite_number("latency_ms", self.latency_ms)
        if latency < 0:
            raise AgentContractError("latency_ms must be non-negative")
        object.__setattr__(self, "latency_ms", latency)


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    title: str
    description: str
    dependencies: tuple[str, ...] = ()
    tool: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    verification: str = ""
    risk: RiskTier = RiskTier.READ_ONLY
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    max_attempts: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", require_id("step_id", self.step_id))
        object.__setattr__(self, "title", bounded_text("step title", self.title, maximum=1024))
        object.__setattr__(self, "description", bounded_text("step description", self.description, maximum=8192))
        dependencies = tuple(require_id("dependency", item) for item in self.dependencies)
        if self.step_id in dependencies or len(set(dependencies)) != len(dependencies):
            raise AgentContractError("step dependencies are self-referential or duplicated")
        object.__setattr__(self, "dependencies", dependencies)
        if self.tool is not None:
            object.__setattr__(self, "tool", require_tool_name(self.tool))
        object.__setattr__(self, "arguments", json_safe(dict(self.arguments)))
        object.__setattr__(self, "expected_outcome", bounded_text("expected_outcome", self.expected_outcome, maximum=4096, allow_empty=True))
        object.__setattr__(self, "verification", bounded_text("verification", self.verification, maximum=4096, allow_empty=True))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        if not isinstance(self.status, StepStatus):
            object.__setattr__(self, "status", StepStatus(str(self.status)))
        object.__setattr__(self, "attempts", non_negative_int("attempts", self.attempts, maximum=1000))
        object.__setattr__(self, "max_attempts", positive_int("max_attempts", self.max_attempts, maximum=1000))
        if self.attempts > self.max_attempts:
            raise AgentContractError("attempts cannot exceed max_attempts")

    def with_status(self, status: StepStatus, *, increment_attempt: bool = False) -> "PlanStep":
        if not isinstance(status, StepStatus):
            status = StepStatus(str(status))
        attempts = self.attempts + (1 if increment_attempt else 0)
        if attempts > self.max_attempts:
            raise AgentContractError("step attempt budget exhausted")
        return replace(self, status=status, attempts=attempts)


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    goal_id: str
    steps: tuple[PlanStep, ...]
    version: int = 1
    rationale: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_id("plan_id", self.plan_id))
        object.__setattr__(self, "goal_id", require_id("goal_id", self.goal_id))
        steps = tuple(self.steps)
        if not steps:
            raise AgentContractError("plan must contain at least one step")
        if any(not isinstance(step, PlanStep) for step in steps):
            raise AgentContractError("plan steps must be PlanStep values")
        ids = [step.step_id for step in steps]
        if len(set(ids)) != len(ids):
            raise AgentContractError("plan contains duplicate step ids")
        known = set(ids)
        for step in steps:
            unknown = set(step.dependencies) - known
            if unknown:
                raise AgentContractError("step depends on unknown ids", context={"step": step.step_id, "missing": sorted(unknown)})
        self._reject_cycles(steps)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "version", positive_int("version", self.version, maximum=100_000))
        object.__setattr__(self, "rationale", bounded_text("plan rationale", self.rationale, maximum=16_384, allow_empty=True))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)

    @staticmethod
    def _reject_cycles(steps: Sequence[PlanStep]) -> None:
        graph = {step.step_id: step.dependencies for step in steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise AgentContractError("plan dependency graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for parent in graph[node]:
                visit(parent)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def step(self, step_id: str) -> PlanStep:
        step_id = require_id("step_id", step_id)
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)

    def replace_step(self, new_step: PlanStep) -> "Plan":
        if not isinstance(new_step, PlanStep):
            raise TypeError("new_step must be PlanStep")
        if new_step.step_id not in {step.step_id for step in self.steps}:
            raise KeyError(new_step.step_id)
        return replace(self, steps=tuple(new_step if step.step_id == new_step.step_id else step for step in self.steps))

    def ready_steps(self) -> tuple[PlanStep, ...]:
        success = {step.step_id for step in self.steps if step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}}
        return tuple(
            step
            for step in self.steps
            if step.status in {StepStatus.PENDING, StepStatus.READY}
            and all(dep in success for dep in step.dependencies)
            and step.attempts < step.max_attempts
        )

    @property
    def complete(self) -> bool:
        return all(step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED} for step in self.steps)

    @property
    def failed(self) -> bool:
        return any(step.status in {StepStatus.FAILED, StepStatus.BLOCKED} for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "version": self.version,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "steps": [
                {
                    "step_id": step.step_id,
                    "title": step.title,
                    "description": step.description,
                    "dependencies": list(step.dependencies),
                    "tool": step.tool,
                    "arguments": dict(step.arguments),
                    "expected_outcome": step.expected_outcome,
                    "verification": step.verification,
                    "risk": step.risk.value,
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "max_attempts": step.max_attempts,
                }
                for step in self.steps
            ],
        }


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: ModelRole | str
    content: str
    name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, ModelRole):
            object.__setattr__(self, "role", ModelRole(str(self.role)))
        object.__setattr__(self, "content", bounded_text("message content", self.content, maximum=128_000, allow_empty=True))
        if self.name is not None:
            object.__setattr__(self, "name", require_id("message name", self.name))


@dataclass(frozen=True, slots=True)
class ModelRequest:
    request_id: str
    messages: tuple[ModelMessage, ...]
    max_tokens: int = 2048
    temperature: float = 0.0
    tools: tuple[Mapping[str, Any], ...] = ()
    response_schema: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", require_id("request_id", self.request_id))
        messages = tuple(self.messages)
        if not messages or any(not isinstance(message, ModelMessage) for message in messages):
            raise AgentContractError("model request requires ModelMessage values")
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "max_tokens", positive_int("max_tokens", self.max_tokens, maximum=1_000_000))
        temperature = finite_number("temperature", self.temperature)
        if not 0.0 <= temperature <= 2.0:
            raise AgentContractError("temperature must be in [0, 2]")
        object.__setattr__(self, "temperature", temperature)
        object.__setattr__(self, "tools", tuple(json_safe(dict(tool)) for tool in self.tools))
        if self.response_schema is not None:
            object.__setattr__(self, "response_schema", json_safe(dict(self.response_schema)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "messages": [(message.role.value, message.name, message.content) for message in self.messages],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "tools": self.tools,
                "response_schema": self.response_schema,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class ModelResponse:
    request_id: str
    provider: str
    model: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    cached: bool = False
    latency_ms: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", require_id("request_id", self.request_id))
        object.__setattr__(self, "provider", require_id("provider", self.provider))
        object.__setattr__(self, "model", bounded_text("model", self.model, maximum=256))
        object.__setattr__(self, "content", bounded_text("model content", self.content, maximum=256_000, allow_empty=True))
        calls = tuple(self.tool_calls)
        if any(not isinstance(call, ToolCall) for call in calls):
            raise AgentContractError("model tool_calls must contain ToolCall values")
        object.__setattr__(self, "tool_calls", calls)
        object.__setattr__(self, "prompt_tokens", non_negative_int("prompt_tokens", self.prompt_tokens, maximum=100_000_000))
        object.__setattr__(self, "completion_tokens", non_negative_int("completion_tokens", self.completion_tokens, maximum=100_000_000))
        object.__setattr__(self, "finish_reason", bounded_text("finish_reason", self.finish_reason, maximum=128, allow_empty=True))
        latency = finite_number("latency_ms", self.latency_ms)
        if latency < 0:
            raise AgentContractError("latency_ms must be non-negative")
        object.__setattr__(self, "latency_ms", latency)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class AgentResult:
    run_id: str
    goal_id: str
    success: bool
    reason: TerminationReason
    answer: str
    usage: Usage
    claims: tuple[Claim, ...] = ()
    observations: tuple[ToolObservation, ...] = ()
    plan: Plan | None = None
    trace_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "goal_id", require_id("goal_id", self.goal_id))
        if not isinstance(self.success, bool):
            raise AgentContractError("success must be boolean")
        if not isinstance(self.reason, TerminationReason):
            object.__setattr__(self, "reason", TerminationReason(str(self.reason)))
        object.__setattr__(self, "answer", bounded_text("answer", self.answer, maximum=256_000, allow_empty=True))
        if not isinstance(self.usage, Usage):
            raise AgentContractError("usage must be Usage")
        claims = tuple(self.claims)
        observations = tuple(self.observations)
        if any(not isinstance(claim, Claim) for claim in claims):
            raise AgentContractError("claims must contain Claim values")
        if any(not isinstance(item, ToolObservation) for item in observations):
            raise AgentContractError("observations must contain ToolObservation values")
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "observations", observations)
        if self.plan is not None and not isinstance(self.plan, Plan):
            raise AgentContractError("plan must be Plan or None")
        if self.trace_fingerprint:
            fingerprint = self.trace_fingerprint.strip().lower()
            if not re.fullmatch(r"[0-9a-f]{32,128}", fingerprint):
                raise AgentContractError("trace_fingerprint must be hexadecimal")
            object.__setattr__(self, "trace_fingerprint", fingerprint)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


def usage_from_response(response: ModelResponse) -> Usage:
    if not isinstance(response, ModelResponse):
        raise TypeError("response must be ModelResponse")
    return Usage(
        model_calls=1,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        cached_model_calls=1 if response.cached else 0,
    )


def merge_usage(values: Iterable[Usage]) -> Usage:
    total = Usage()
    for value in values:
        if not isinstance(value, Usage):
            raise TypeError("merge_usage expects Usage values")
        total = total.add(
            steps=value.steps,
            model_calls=value.model_calls,
            tool_calls=value.tool_calls,
            prompt_tokens=value.prompt_tokens,
            completion_tokens=value.completion_tokens,
            cached_model_calls=value.cached_model_calls,
        )
    return total
