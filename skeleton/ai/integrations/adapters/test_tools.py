"""Tests for tool adapters, the registry and the capsec-gated executor."""

from __future__ import annotations

import asyncio
import time

import pytest

from .capsec import AllowAllChecker, AllowListChecker, CapsecGate
from .deadline import CancellationToken
from .errors import (
    CapabilityDeniedError,
    DuplicateRegistrationError,
    OperationCancelledError,
    SchemaValidationError,
    ToolArgumentError,
    ToolExecutionError,
    ToolNotFoundError,
)
from .observe import EventLog, ObserverHub
from .tools import FunctionTool, ToolExecutor, ToolExecutorConfig, ToolRegistry, tool
from .types import ToolCall, ToolSpec


def run(coro):
    return asyncio.run(coro)


@tool("add", description="Add numbers", capabilities=["math.compute"])
def add(a: int, b: int = 2) -> int:
    return a + b


@tool(capabilities=["time.read"])
async def clock(tz: str = "UTC") -> dict:
    """Return a fake time."""
    return {"tz": tz, "time": "12:00"}


def executor(*tools, checker=None, **cfg) -> ToolExecutor:
    reg = ToolRegistry(tools)
    return ToolExecutor(reg, CapsecGate(checker or AllowAllChecker()), ToolExecutorConfig(**cfg) if cfg else None)


def test_decorator_infers_schema_and_spec():
    assert add.spec.name == "add" and add.spec.capabilities == ("math.compute",)
    params = add.spec.parameters
    assert params["required"] == ["a"]
    assert params["properties"]["a"] == {"type": "integer"}
    assert params["properties"]["b"] == {"type": "integer", "default": 2}
    assert params["additionalProperties"] is False
    assert clock.spec.description == "Return a fake time."


def test_function_tool_rejects_bad_schema():
    with pytest.raises(SchemaValidationError):
        FunctionTool(lambda: 1, ToolSpec("bad", parameters={"type": "nope"}))


def test_registry_operations():
    reg = ToolRegistry([add])
    assert "add" in reg and len(reg) == 1 and reg.names() == ["add"]
    with pytest.raises(DuplicateRegistrationError):
        reg.register(add)
    reg.register(add, replace=True)
    reg.register(clock)
    assert [s.name for s in reg.specs()] == ["add", "clock"]
    assert [s.name for s in reg.specs(["clock", "ghost"])] == ["clock"]
    reg.unregister("clock")
    with pytest.raises(ToolNotFoundError):
        reg.unregister("clock")
    with pytest.raises(ToolNotFoundError):
        reg.get("clock")


def test_invoke_sync_and_async_tools_with_defaults():
    ex = executor(add, clock)
    assert run(ex.invoke(ToolCall("1", "add", {"a": 1}), principal="p")) == 3
    assert run(ex.invoke(ToolCall("2", "clock", {}), principal="p")) == {"tz": "UTC", "time": "12:00"}


def test_default_gate_denies_and_never_runs_tool():
    ran: list[int] = []

    @tool("side_effect")
    def side_effect() -> str:
        ran.append(1)
        return "done"

    ex = ToolExecutor(ToolRegistry([side_effect]))  # default gate: deny-all
    with pytest.raises(CapabilityDeniedError):
        run(ex.invoke(ToolCall("1", "side_effect"), principal="p"))
    result = run(ex.execute(ToolCall("1", "side_effect"), principal="p"))
    assert result.is_error and result.error_code == "capability_denied"
    assert "denied by capability policy" in result.content["message"]
    assert ran == []
    audit = ex.gate.audit()
    assert len(audit) == 2 and not audit[0].allowed


def test_allow_list_scopes_capabilities():
    checker = AllowListChecker({"agent:math": ["tool.invoke:add", "math.*"]})
    ex = executor(add, clock, checker=checker)
    assert run(ex.invoke(ToolCall("1", "add", {"a": 5}), principal="agent:math")) == 7
    denied = run(ex.execute(ToolCall("2", "clock", {}), principal="agent:math"))
    assert denied.error_code == "capability_denied"
    other = run(ex.execute(ToolCall("3", "add", {"a": 1}), principal="agent:other"))
    assert other.error_code == "capability_denied"


def test_capsec_sees_digest_and_resources_not_arguments():
    seen = []

    class Spy:
        def check(self, request):
            seen.append(request)
            return AllowAllChecker().check(request)

    reader = FunctionTool(
        lambda path: f"read {path}",
        ToolSpec("read", parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                 capabilities=("fs.read",)),
        resources=lambda args: [f"file:{args['path']}"],
    )
    ex = executor(reader, checker=Spy())
    run(ex.invoke(ToolCall("1", "read", {"path": "/tmp/x"}), principal="p"))
    request = seen[0]
    assert request.resources == ("file:/tmp/x",)
    assert len(request.arguments_digest) == 64
    assert "/tmp/x" not in repr(request.attributes)


def test_argument_validation_happens_before_capsec():
    seen = []

    class Spy:
        def check(self, request):
            seen.append(request)
            return AllowAllChecker().check(request)

    ex = executor(add, checker=Spy())
    with pytest.raises(ToolArgumentError):
        run(ex.invoke(ToolCall("1", "add", {"a": "one"}), principal="p"))
    with pytest.raises(ToolArgumentError):
        run(ex.invoke(ToolCall("1", "add", {"a": 1, "zzz": 1}), principal="p"))
    assert seen == []


def test_unknown_tool_is_error_result():
    result = run(executor(add).execute(ToolCall("1", "ghost"), principal="p"))
    assert result.is_error and result.error_code == "tool_not_found"


def test_tool_exceptions_are_wrapped():
    @tool("explode")
    def explode() -> None:
        raise ValueError("kaboom")

    ex = executor(explode)
    with pytest.raises(ToolExecutionError, match="kaboom"):
        run(ex.invoke(ToolCall("1", "explode"), principal="p"))
    result = run(ex.execute(ToolCall("1", "explode"), principal="p"))
    assert result.error_code == "tool_execution_failed"


def test_tool_timeout_from_adapter_and_default():
    @tool("sleepy", timeout=0.02)
    async def sleepy() -> str:
        await asyncio.sleep(5)
        return "late"

    result = run(executor(sleepy).execute(ToolCall("1", "sleepy"), principal="p"))
    assert result.error_code == "deadline_exceeded"

    @tool("sleepy2")
    async def sleepy2() -> str:
        await asyncio.sleep(5)
        return "late"

    result2 = run(executor(sleepy2, default_timeout=0.02).execute(ToolCall("1", "sleepy2"), principal="p"))
    assert result2.error_code == "deadline_exceeded"


def test_cancellation_propagates_from_execute():
    token = CancellationToken()
    token.cancel("stop")
    with pytest.raises(OperationCancelledError):
        run(executor(add).execute(ToolCall("1", "add", {"a": 1}), principal="p", token=token))


def test_ctx_is_passed_when_requested():
    @tool("whoami")
    def whoami(ctx) -> str:
        return f"{ctx.principal}:{ctx.call_id}"

    assert run(executor(whoami).invoke(ToolCall("c9", "whoami"), principal="agent:z")) == "agent:z:c9"


def test_output_bounding_and_serialisation():
    @tool("big")
    def big() -> str:
        return "x" * 10_000

    @tool("bigobj")
    def bigobj() -> dict:
        return {"data": "y" * 10_000}

    @tool("weird")
    def weird() -> object:
        return {"s": {1, 2}}

    ex = executor(big, bigobj, weird, max_output_chars=1000)
    out = run(ex.invoke(ToolCall("1", "big"), principal="p"))
    assert len(out) == 1000 and out.endswith("chars]")
    obj = run(ex.invoke(ToolCall("1", "bigobj"), principal="p"))
    assert isinstance(obj, str) and len(obj) == 1000
    assert run(ex.invoke(ToolCall("1", "weird"), principal="p")) == {"s": "{1, 2}"}


def test_execute_many_preserves_order_and_runs_concurrently():
    @tool("nap")
    async def nap(ms: int) -> int:
        await asyncio.sleep(ms / 1000)
        return ms

    ex = executor(nap, max_parallel=4)
    calls = [ToolCall(str(i), "nap", {"ms": ms}) for i, ms in enumerate([40, 10, 30, 20])]
    started = time.perf_counter()
    results = run(ex.execute_many(calls, principal="p"))
    elapsed = time.perf_counter() - started
    assert [r.content for r in results] == [40, 10, 30, 20]
    assert elapsed < 0.09


def test_executor_emits_events():
    log = EventLog()
    ex = ToolExecutor(ToolRegistry([add]), CapsecGate(AllowAllChecker()), observers=ObserverHub([log]))
    run(ex.execute(ToolCall("1", "add", {"a": 1}), principal="p"))
    run(ex.execute(ToolCall("2", "ghost"), principal="p"))
    assert log.kinds() == ["tool_succeeded", "tool_failed"]


def test_executor_config_validation():
    with pytest.raises(ValueError):
        ToolExecutorConfig(default_timeout=0)
    with pytest.raises(ValueError):
        ToolExecutorConfig(max_output_chars=10)
    with pytest.raises(ValueError):
        ToolExecutorConfig(max_parallel=0)
