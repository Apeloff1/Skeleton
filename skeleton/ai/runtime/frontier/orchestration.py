"""Canonical agent orchestration lifecycle.

This module owns run/step transitions, bounded retries, cooperative cancellation,
tool invocation lifecycle, and explicit capability authorization. Provider- and
agent-specific drivers adapt their turn generation to :class:`OrchestrationDriver`
rather than owning another loop.
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from skeleton.frontier.model_runtime import CancellationToken, ProviderCancelledError


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepKind(str, Enum):
    MODEL = "model"
    TOOL = "tool"


class ToolCapability(str, Enum):
    """Sensitive capabilities that tools must declare explicitly."""

    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PROCESS = "process"
    SECRETS = "secrets"
    REPOSITORY_MUTATION = "repository_mutation"


RUN_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}

STEP_TRANSITIONS: Mapping[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.CANCELLED}),
    StepStatus.RUNNING: frozenset(
        {
            StepStatus.RETRYING,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.RETRYING: frozenset({StepStatus.RUNNING, StepStatus.CANCELLED}),
    StepStatus.SUCCEEDED: frozenset(),
    StepStatus.FAILED: frozenset(),
    StepStatus.CANCELLED: frozenset(),
}


class OrchestrationError(RuntimeError):
    """Base error for canonical orchestration failures."""


class InvalidTransitionError(OrchestrationError):
    """Raised when code tries to violate the run/step state machine."""


class RetryBudgetExceeded(OrchestrationError):
    """Raised when a retryable tool exhausts its explicit budget."""


class TransientToolError(OrchestrationError):
    """Explicitly retryable tool failure."""


class ToolNotFoundError(OrchestrationError):
    """Requested tool is not registered."""


class CapabilityDeniedError(OrchestrationError):
    """Raised when a tool requests capabilities the run was not granted."""


class ToolExecutionError(OrchestrationError):
    """Stable tool failure boundary that does not persist handler messages."""


@dataclass(frozen=True, slots=True)
class RetryBudget:
    max_attempts: int = 1
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise TypeError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    call_id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    name: str
    output: Any


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    """One model/agent turn returned by an orchestration driver."""

    output: Any = None
    tool_calls: tuple[ToolInvocation, ...] = ()
    terminal: bool = False

    def __post_init__(self) -> None:
        if self.terminal and self.tool_calls:
            raise ValueError("terminal turn cannot also request tools")
        if not self.terminal and not self.tool_calls:
            raise ValueError("non-terminal turn must request at least one tool")


@dataclass(slots=True)
class StepRecord:
    step_id: str
    kind: StepKind
    status: StepStatus = StepStatus.PENDING
    attempt: int = 0
    name: str | None = None
    result: Any = None
    error: str | None = None

    def transition(self, target: StepStatus) -> None:
        if target not in STEP_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"invalid step transition: {self.status.value} -> {target.value}"
            )
        self.status = target


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """Auditable capability decision for one tool invocation."""

    run_id: str
    call_id: str
    tool_name: str
    capability: ToolCapability
    allowed: bool


@dataclass(slots=True)
class RunRecord:
    run_id: str
    status: RunStatus = RunStatus.PENDING
    steps: list[StepRecord] = field(default_factory=list)
    capability_decisions: list[CapabilityDecision] = field(default_factory=list)
    output: Any = None
    error: str | None = None
    turns: int = 0

    def transition(self, target: RunStatus) -> None:
        if target not in RUN_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"invalid run transition: {self.status.value} -> {target.value}"
            )
        self.status = target

    @property
    def terminal(self) -> bool:
        return self.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }


class OrchestrationDriver(Protocol):
    """Provider/agent-specific turn producer used by the canonical loop."""

    async def next_turn(
        self,
        *,
        run: RunRecord,
        tool_results: tuple[ToolResult, ...],
    ) -> TurnOutcome:
        ...


ToolHandler = Callable[[Mapping[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Registered tool handler plus its explicit capability requirements."""

    name: str
    handler: ToolHandler
    capabilities: frozenset[ToolCapability] = frozenset()


class ToolRegistry:
    """Explicit registry for tool handlers used by the canonical lifecycle."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        capabilities: Iterable[ToolCapability | str] = (),
    ) -> None:
        normalized = _normalized_name(name, "tool name")
        if normalized in self._definitions:
            raise ValueError(f"tool already registered: {normalized}")
        self._definitions[normalized] = ToolDefinition(
            name=normalized,
            handler=handler,
            capabilities=_normalize_capabilities(capabilities),
        )

    def definition(self, name: str) -> ToolDefinition:
        return _tool_definition(self._definitions, name)

    def resolve(self, name: str) -> ToolHandler:
        """Resolve a handler while preserving the pre-capability registry API."""
        return self.definition(name).handler

    def snapshot(self) -> Mapping[str, ToolDefinition]:
        """Return an immutable registry view for a single orchestration run."""
        return MappingProxyType(dict(self._definitions))


@dataclass(slots=True)
class CanonicalOrchestrator:
    """One run loop for model turns, tool calls, retries, and terminal states."""

    tools: ToolRegistry = field(default_factory=ToolRegistry)
    tool_retry_budget: RetryBudget = RetryBudget()
    max_turns: int = 16

    def __post_init__(self) -> None:
        if isinstance(self.max_turns, bool) or not isinstance(self.max_turns, int):
            raise TypeError("max_turns must be an integer")
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1")

    async def run(
        self,
        driver: OrchestrationDriver,
        *,
        cancellation: CancellationToken | None = None,
        run_id: str | None = None,
        capabilities: Iterable[ToolCapability | str] = (),
    ) -> RunRecord:
        granted_capabilities = _normalize_capabilities(capabilities)
        tool_definitions = self.tools.snapshot()
        record = RunRecord(run_id=run_id or uuid.uuid4().hex)
        if cancellation is not None and cancellation.cancelled:
            record.transition(RunStatus.CANCELLED)
            record.error = "run cancelled before start"
            return record

        record.transition(RunStatus.RUNNING)
        tool_results: tuple[ToolResult, ...] = ()
        try:
            while record.turns < self.max_turns:
                _raise_if_cancelled(cancellation)
                model_step = StepRecord(
                    step_id=uuid.uuid4().hex,
                    kind=StepKind.MODEL,
                    name="model.turn",
                )
                record.steps.append(model_step)
                model_step.transition(StepStatus.RUNNING)
                model_step.attempt = 1
                try:
                    outcome = await _await_with_cancellation(
                        driver.next_turn(run=record, tool_results=tool_results),
                        cancellation,
                    )
                except ProviderCancelledError:
                    model_step.transition(StepStatus.CANCELLED)
                    raise
                except BaseException as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        model_step.transition(StepStatus.CANCELLED)
                        raise
                    model_step.error = _error_text(exc)
                    model_step.transition(StepStatus.FAILED)
                    raise

                record.turns += 1
                model_step.result = outcome
                model_step.transition(StepStatus.SUCCEEDED)
                if outcome.terminal:
                    record.output = outcome.output
                    record.transition(RunStatus.COMPLETED)
                    return record

                results: list[ToolResult] = []
                for call in outcome.tool_calls:
                    _raise_if_cancelled(cancellation)
                    result = await self._execute_tool(
                        record,
                        call,
                        cancellation=cancellation,
                        granted_capabilities=granted_capabilities,
                        tool_definitions=tool_definitions,
                    )
                    results.append(result)
                tool_results = tuple(results)

            record.error = f"maximum turn budget exhausted ({self.max_turns})"
            record.transition(RunStatus.FAILED)
            return record
        except ProviderCancelledError as exc:
            self._cancel_running_steps(record)
            record.error = str(exc)
            if record.status is RunStatus.RUNNING:
                record.transition(RunStatus.CANCELLED)
            return record
        except asyncio.CancelledError:
            self._cancel_running_steps(record)
            record.error = "orchestration task cancelled"
            if record.status is RunStatus.RUNNING:
                record.transition(RunStatus.CANCELLED)
            raise
        except BaseException as exc:
            self._fail_running_steps(record, exc)
            record.error = _error_text(exc)
            if record.status is RunStatus.RUNNING:
                record.transition(RunStatus.FAILED)
            return record

    async def _execute_tool(
        self,
        record: RunRecord,
        call: ToolInvocation,
        *,
        cancellation: CancellationToken | None,
        granted_capabilities: frozenset[ToolCapability],
        tool_definitions: Mapping[str, ToolDefinition],
    ) -> ToolResult:
        definition = _tool_definition(tool_definitions, call.name)
        step = StepRecord(
            step_id=uuid.uuid4().hex,
            kind=StepKind.TOOL,
            name=call.name,
        )
        record.steps.append(step)

        denied: list[ToolCapability] = []
        for capability in sorted(definition.capabilities, key=lambda item: item.value):
            allowed = capability in granted_capabilities
            record.capability_decisions.append(
                CapabilityDecision(
                    run_id=record.run_id,
                    call_id=call.call_id,
                    tool_name=definition.name,
                    capability=capability,
                    allowed=allowed,
                )
            )
            if not allowed:
                denied.append(capability)

        if denied:
            step.transition(StepStatus.RUNNING)
            step.attempt = 1
            names = ", ".join(capability.value for capability in denied)
            error = CapabilityDeniedError(
                f"tool {call.name!r} denied capabilities: {names}"
            )
            step.error = _error_text(error)
            step.transition(StepStatus.FAILED)
            raise error

        handler = definition.handler
        last_error: BaseException | None = None
        for attempt in range(1, self.tool_retry_budget.max_attempts + 1):
            _raise_if_cancelled(cancellation)
            step.transition(StepStatus.RUNNING)
            step.attempt = attempt
            try:
                candidate = handler(dict(call.arguments))
                if inspect.isawaitable(candidate):
                    output = await _await_with_cancellation(candidate, cancellation)
                else:
                    output = candidate
            except ProviderCancelledError:
                step.transition(StepStatus.CANCELLED)
                raise
            except TransientToolError as exc:
                last_error = exc
                step.error = f"{type(exc).__name__}: retryable tool failure"
                if attempt >= self.tool_retry_budget.max_attempts:
                    step.transition(StepStatus.FAILED)
                    raise RetryBudgetExceeded(
                        f"tool {call.name!r} exhausted retry budget "
                        f"after {attempt} attempts"
                    ) from exc
                step.transition(StepStatus.RETRYING)
                await _sleep_with_cancellation(
                    self.tool_retry_budget.backoff_seconds,
                    cancellation,
                )
                continue
            except BaseException as exc:
                if isinstance(exc, asyncio.CancelledError):
                    step.transition(StepStatus.CANCELLED)
                    raise
                error = ToolExecutionError(
                    f"tool {call.name!r} failed with {type(exc).__name__}"
                )
                step.error = _error_text(error)
                step.transition(StepStatus.FAILED)
                raise error from exc
            else:
                step.error = None
                step.result = output
                step.transition(StepStatus.SUCCEEDED)
                return ToolResult(call.call_id, call.name, output)

        assert last_error is not None
        raise RetryBudgetExceeded(f"tool {call.name!r} exhausted retry budget")

    @staticmethod
    def _cancel_running_steps(record: RunRecord) -> None:
        for step in record.steps:
            if step.status in {
                StepStatus.RUNNING,
                StepStatus.RETRYING,
                StepStatus.PENDING,
            }:
                step.transition(StepStatus.CANCELLED)

    @staticmethod
    def _fail_running_steps(record: RunRecord, exc: BaseException) -> None:
        for step in record.steps:
            if step.status is StepStatus.RUNNING:
                step.error = _error_text(exc)
                step.transition(StepStatus.FAILED)


def _tool_definition(
    definitions: Mapping[str, ToolDefinition],
    name: str,
) -> ToolDefinition:
    normalized = _normalized_name(name, "tool name")
    try:
        return definitions[normalized]
    except KeyError as exc:
        raise ToolNotFoundError(f"unknown tool: {normalized}") from exc


def _normalized_name(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _normalize_capabilities(
    capabilities: Iterable[ToolCapability | str],
) -> frozenset[ToolCapability]:
    if isinstance(capabilities, (str, bytes)):
        raise TypeError("capabilities must be an iterable of capability values")

    normalized: set[ToolCapability] = set()
    for capability in capabilities:
        if isinstance(capability, ToolCapability):
            normalized.add(capability)
            continue
        if not isinstance(capability, str):
            raise TypeError("capability values must be ToolCapability or str")
        try:
            normalized.add(ToolCapability(capability))
        except ValueError as exc:
            raise ValueError(f"unknown tool capability: {capability}") from exc
    return frozenset(normalized)


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation is not None:
        cancellation.raise_if_cancelled()


async def _await_with_cancellation(
    awaitable: Awaitable[Any],
    cancellation: CancellationToken | None,
) -> Any:
    if cancellation is None:
        return await awaitable
    cancellation.raise_if_cancelled()
    operation = asyncio.ensure_future(awaitable)
    cancel_waiter = asyncio.create_task(cancellation.wait())
    try:
        done, _ = await asyncio.wait(
            {operation, cancel_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if operation in done:
            cancel_waiter.cancel()
            return await operation
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        raise ProviderCancelledError("orchestration cancelled")
    except asyncio.CancelledError:
        operation.cancel()
        cancel_waiter.cancel()
        await asyncio.gather(operation, cancel_waiter, return_exceptions=True)
        raise
    finally:
        if not cancel_waiter.done():
            cancel_waiter.cancel()


async def _sleep_with_cancellation(
    seconds: float,
    cancellation: CancellationToken | None,
) -> None:
    if seconds <= 0:
        _raise_if_cancelled(cancellation)
        return
    await _await_with_cancellation(asyncio.sleep(seconds), cancellation)