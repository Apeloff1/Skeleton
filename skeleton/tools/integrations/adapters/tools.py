"""Tool adapters behind one interface, routed through the capsec gate.

Every invocation follows the same fixed pipeline, and none of it can be
skipped by an adapter:

1. resolve the tool by name (unknown → ``tool_not_found``),
2. apply schema defaults and validate arguments (→ ``tool_arguments_invalid``),
3. authorize the signed capability token through the canonical kernel capsec
   gate for ``tool.<name>:invoke`` plus every declared capability
   (→ ``capability_denied``; fail-closed),
4. run the adapter under timeout / deadline / cancellation,
5. bound and normalise the output.

:meth:`ToolExecutor.execute` converts failures into error
:class:`~.types.ToolResult` values for model loops; :meth:`ToolExecutor.invoke`
raises instead.
"""

from __future__ import annotations

import abc
import asyncio
import inspect
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping

from skeleton.kernel.capsec import CapabilityGate

from .capsec import KernelToolAuthorizer
from .deadline import CancellationToken, Deadline, run_with_deadline
from .errors import (
    CapabilityDeniedError,
    DuplicateRegistrationError,
    IntegrationError,
    OperationCancelledError,
    SchemaValidationError,
    ToolArgumentError,
    ToolExecutionError,
    ToolNotFoundError,
    classify_exception,
)
from .observe import ObserverHub
from .schema import apply_defaults, check_schema, validate
from .types import ToolCall, ToolResult, ToolSpec

__all__ = [
    "ToolContext",
    "ToolAdapter",
    "FunctionTool",
    "ToolRegistry",
    "ToolExecutor",
    "ToolExecutorConfig",
    "tool",
]


@dataclass
class ToolContext:
    principal: str
    deadline: Deadline
    token: CancellationToken
    call_id: str = ""
    trace_id: str = ""


class ToolAdapter(abc.ABC):
    """One tool.  Implementations declare a spec and an async ``invoke``."""

    @property
    @abc.abstractmethod
    def spec(self) -> ToolSpec: ...

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def timeout(self) -> float | None:
        return None

    def resources(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        """Resource identifiers (paths, hosts) the capsec layer may scope on."""

        return ()

    @abc.abstractmethod
    async def invoke(self, arguments: Mapping[str, Any], ctx: ToolContext) -> Any: ...


class FunctionTool(ToolAdapter):
    """Adapt a plain sync or async callable.

    Sync callables run in a worker thread so they cannot block the loop.  If
    the callable accepts a ``ctx`` keyword it receives the :class:`ToolContext`.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        spec: ToolSpec,
        *,
        timeout: float | None = None,
        resources: Callable[[Mapping[str, Any]], Iterable[str]] | None = None,
    ) -> None:
        check_schema(spec.parameters)
        self._func = func
        self._spec = spec
        self._timeout = timeout
        self._resources = resources
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            params = {}  # type: ignore[assignment]
        self._wants_ctx = "ctx" in params
        self._is_async = inspect.iscoroutinefunction(func)

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    @property
    def timeout(self) -> float | None:
        return self._timeout

    def resources(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        if self._resources is None:
            return ()
        return tuple(self._resources(arguments))

    async def invoke(self, arguments: Mapping[str, Any], ctx: ToolContext) -> Any:
        kwargs = dict(arguments)
        if self._wants_ctx:
            kwargs["ctx"] = ctx
        if self._is_async:
            return await self._func(**kwargs)
        result = await asyncio.to_thread(self._func, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def tool(
    name: str | None = None,
    *,
    description: str = "",
    parameters: Mapping[str, Any] | None = None,
    capabilities: Iterable[str] = (),
    timeout: float | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]:
    """Decorator: ``@tool("clock", capabilities=["time.read"])``."""

    def wrap(func: Callable[..., Any]) -> FunctionTool:
        spec = ToolSpec(
            name=name or func.__name__,
            description=description or (inspect.getdoc(func) or "").split("\n", 1)[0],
            parameters=dict(parameters) if parameters is not None else _infer_parameters(func),
            capabilities=tuple(capabilities),
        )
        return FunctionTool(func, spec, timeout=timeout)

    return wrap


_PY_TO_SCHEMA = {int: "integer", float: "number", str: "string", bool: "boolean", list: "array", dict: "object"}


def _infer_parameters(func: Callable[..., Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in inspect.signature(func).parameters.items():
        if pname == "ctx" or param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        schema: dict[str, Any] = {}
        annotation = param.annotation
        if isinstance(annotation, str):
            annotation = {"int": int, "float": float, "str": str, "bool": bool, "list": list, "dict": dict}.get(
                annotation, None
            )
        if annotation in _PY_TO_SCHEMA:
            schema["type"] = _PY_TO_SCHEMA[annotation]
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            schema["default"] = param.default
        props[pname] = schema
    result: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        result["required"] = required
    return result


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolAdapter] = ()) -> None:
        self._lock = threading.Lock()
        self._tools: dict[str, ToolAdapter] = {}
        for item in tools:
            self.register(item)

    def register(self, adapter: ToolAdapter, *, replace: bool = False) -> ToolAdapter:
        with self._lock:
            if not replace and adapter.name in self._tools:
                raise DuplicateRegistrationError(f"tool {adapter.name!r} is already registered")
            self._tools[adapter.name] = adapter
        return adapter

    def unregister(self, name: str) -> None:
        with self._lock:
            if self._tools.pop(name, None) is None:
                raise ToolNotFoundError(f"tool {name!r} is not registered")

    def get(self, name: str) -> ToolAdapter:
        with self._lock:
            adapter = self._tools.get(name)
        if adapter is None:
            raise ToolNotFoundError(f"tool {name!r} is not registered")
        return adapter

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._tools)

    def specs(self, names: Iterable[str] | None = None) -> tuple[ToolSpec, ...]:
        with self._lock:
            chosen = sorted(self._tools) if names is None else list(names)
            return tuple(self._tools[n].spec for n in chosen if n in self._tools)

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._tools

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)


@dataclass(frozen=True)
class ToolExecutorConfig:
    default_timeout: float | None = 30.0
    max_output_chars: int = 64_000
    max_parallel: int = 8

    def __post_init__(self) -> None:
        if self.default_timeout is not None and self.default_timeout <= 0:
            raise ValueError("default_timeout must be positive or None")
        if self.max_output_chars < 256:
            raise ValueError("max_output_chars must be >= 256")
        if self.max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        gate: CapabilityGate | None = None,
        config: ToolExecutorConfig | None = None,
        *,
        observers: ObserverHub | None = None,
    ) -> None:
        self.registry = registry
        self.authorizer = KernelToolAuthorizer(gate)
        self.gate = self.authorizer.gate
        self.config = config or ToolExecutorConfig()
        self.observers = observers or ObserverHub()

    def _prepare(self, call: ToolCall) -> tuple[ToolAdapter, dict[str, Any]]:
        adapter = self.registry.get(call.name)
        schema = adapter.spec.parameters
        arguments = apply_defaults(dict(call.arguments), schema)
        try:
            validate(arguments, schema)
        except SchemaValidationError as exc:
            raise ToolArgumentError(f"invalid arguments for {call.name!r}: {exc.message}") from exc
        return adapter, arguments

    def _bound_output(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, sort_keys=True, default=str)
                if len(text) <= self.config.max_output_chars:
                    return json.loads(text)
            except (TypeError, ValueError) as exc:
                raise ToolExecutionError(f"tool output is not serialisable: {exc}") from exc
        limit = self.config.max_output_chars
        if len(text) <= limit:
            return text
        marker = f"...[truncated {len(text)} chars]"
        return text[: limit - len(marker)] + marker

    async def invoke(
        self,
        call: ToolCall,
        *,
        cap: str | None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        trace_id: str = "",
    ) -> Any:
        """Run one call through the full pipeline; raise on any failure."""

        tok = token or CancellationToken()
        dl = deadline or Deadline.never()
        tok.check()
        adapter, arguments = self._prepare(call)
        authorization = self.authorizer.authorize(
            cap,
            tool_name=adapter.name,
            capabilities=adapter.spec.capabilities,
            resources=adapter.resources(arguments),
        )
        ctx = ToolContext(
            principal=authorization.subject,
            deadline=dl,
            token=tok,
            call_id=call.id,
            trace_id=trace_id,
        )
        timeout = adapter.timeout if adapter.timeout is not None else self.config.default_timeout

        async def run() -> Any:
            return await adapter.invoke(arguments, ctx)

        try:
            raw = await run_with_deadline(run, timeout=timeout, deadline=dl, token=tok, what=f"tool {call.name}")
        except IntegrationError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapters may raise anything
            raise ToolExecutionError(f"tool {call.name!r} failed: {type(exc).__name__}: {exc}") from exc
        return self._bound_output(raw)

    async def execute(
        self,
        call: ToolCall,
        *,
        cap: str | None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        trace_id: str = "",
    ) -> ToolResult:
        """Like :meth:`invoke` but returns failures as error results.

        Cancellation is still raised: a cancelled loop must stop, not feed the
        model a synthetic error.
        """

        started = time.perf_counter()
        try:
            content = await self.invoke(call, cap=cap, deadline=deadline, token=token, trace_id=trace_id)
        except OperationCancelledError:
            raise
        except asyncio.CancelledError:
            raise
        except BaseException as raw:  # noqa: BLE001
            if isinstance(raw, (KeyboardInterrupt, SystemExit)):
                raise
            err = classify_exception(raw)
            elapsed = (time.perf_counter() - started) * 1000.0
            self.observers.emit("tool_failed", tool=call.name, code=err.code, latency_ms=elapsed)
            message = err.message
            if isinstance(err, CapabilityDeniedError):
                message = f"denied by capability policy: {err.reason or 'not permitted'}"
            return ToolResult(
                call_id=call.id,
                name=call.name,
                content={"error": err.code, "message": message},
                is_error=True,
                error_code=err.code,
                duration_ms=elapsed,
            )
        elapsed = (time.perf_counter() - started) * 1000.0
        self.observers.emit("tool_succeeded", tool=call.name, latency_ms=elapsed)
        return ToolResult(call_id=call.id, name=call.name, content=content, duration_ms=elapsed)

    async def execute_many(
        self,
        calls: Iterable[ToolCall],
        *,
        cap: str | None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        trace_id: str = "",
    ) -> list[ToolResult]:
        """Execute calls concurrently (bounded), preserving input order."""

        semaphore = asyncio.Semaphore(self.config.max_parallel)

        async def one(call: ToolCall) -> ToolResult:
            async with semaphore:
                return await self.execute(
                    call, cap=cap, deadline=deadline, token=token, trace_id=trace_id
                )

        tasks: list[Awaitable[ToolResult]] = [one(c) for c in calls]
        return list(await asyncio.gather(*tasks))
