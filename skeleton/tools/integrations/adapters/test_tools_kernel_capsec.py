from __future__ import annotations

import asyncio

import pytest

from skeleton.kernel.capabilities import TokenIssuer
from skeleton.kernel.capsec import mint_scoped

from .capsec import tool_actions
from .errors import CapabilityDeniedError, ToolArgumentError
from .tools import FunctionTool, ToolExecutor, ToolRegistry, tool
from .types import ToolCall, ToolSpec


def run(coro):
    return asyncio.run(coro)


def _executor(*adapters):
    issuer = TokenIssuer(secret=b"t" * 32)
    executor = ToolExecutor(ToolRegistry(adapters), issuer.gate())
    return issuer, executor


def _cap(issuer: TokenIssuer, name: str, capabilities=(), resources=()):
    return mint_scoped(
        issuer,
        "agent:verified",
        tool_actions(name, capabilities, resources),
        ttl_seconds=60,
    )


@tool("add", capabilities=("math.compute",))
def add(a: int, b: int = 2) -> int:
    return a + b


def test_default_executor_denies_unsigned_calls_and_never_runs_tool() -> None:
    ran: list[int] = []

    @tool("side_effect")
    def side_effect() -> str:
        ran.append(1)
        return "done"

    executor = ToolExecutor(ToolRegistry([side_effect]))

    with pytest.raises(CapabilityDeniedError):
        run(executor.invoke(ToolCall("1", "side_effect"), cap=None))
    result = run(executor.execute(ToolCall("2", "side_effect"), cap=None))

    assert result.is_error is True
    assert result.error_code == "capability_denied"
    assert ran == []


def test_valid_signed_token_executes_declared_capability() -> None:
    issuer, executor = _executor(add)
    cap = _cap(issuer, "add", ("math.compute",))

    assert run(executor.invoke(ToolCall("1", "add", {"a": 5}), cap=cap)) == 7


def test_tool_context_identity_comes_from_verified_token_subject() -> None:
    @tool("whoami")
    def whoami(ctx) -> str:
        return ctx.principal

    issuer, executor = _executor(whoami)
    cap = _cap(issuer, "whoami")

    assert run(executor.invoke(ToolCall("id", "whoami"), cap=cap)) == "agent:verified"


def test_missing_declared_capability_denies_before_tool_side_effect() -> None:
    ran: list[int] = []

    @tool("write", capabilities=("fs.write",))
    def write() -> str:
        ran.append(1)
        return "written"

    issuer, executor = _executor(write)
    cap = _cap(issuer, "write")

    with pytest.raises(CapabilityDeniedError):
        run(executor.invoke(ToolCall("1", "write"), cap=cap))
    assert ran == []


def test_resource_scoped_token_cannot_be_reused_for_another_resource() -> None:
    reader = FunctionTool(
        lambda path: f"read:{path}",
        ToolSpec(
            "reader",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            capabilities=("fs.read",),
        ),
        resources=lambda arguments: (f"file:{arguments['path']}",),
    )
    issuer, executor = _executor(reader)
    cap = _cap(issuer, "reader", ("fs.read",), ("file:/tmp/a",))

    assert run(
        executor.invoke(ToolCall("1", "reader", {"path": "/tmp/a"}), cap=cap)
    ) == "read:/tmp/a"

    denied = run(
        executor.execute(ToolCall("2", "reader", {"path": "/tmp/b"}), cap=cap)
    )
    assert denied.is_error is True
    assert denied.error_code == "capability_denied"


def test_argument_validation_occurs_before_authority_and_side_effects() -> None:
    issuer, executor = _executor(add)
    cap = _cap(issuer, "add", ("math.compute",))

    with pytest.raises(ToolArgumentError):
        run(executor.invoke(ToolCall("1", "add", {"a": "five"}), cap=cap))
    with pytest.raises(ToolArgumentError):
        run(executor.invoke(ToolCall("2", "add", {"a": 1, "extra": 2}), cap=cap))


def test_execute_many_preserves_input_order_under_one_verified_token() -> None:
    issuer, executor = _executor(add)
    cap = _cap(issuer, "add", ("math.compute",))

    results = run(
        executor.execute_many(
            (
                ToolCall("1", "add", {"a": 1}),
                ToolCall("2", "add", {"a": 5, "b": 4}),
            ),
            cap=cap,
        )
    )

    assert [item.content for item in results] == [3, 9]
    assert all(item.is_error is False for item in results)


def test_revoked_token_fails_closed() -> None:
    issuer, executor = _executor(add)
    cap = _cap(issuer, "add", ("math.compute",))
    token = issuer.verify(cap)
    issuer.revoke(token.token_id)

    result = run(executor.execute(ToolCall("1", "add", {"a": 1}), cap=cap))
    assert result.is_error is True
    assert result.error_code == "capability_denied"
    assert "denied by capability policy" in result.content["message"]
