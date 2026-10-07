from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionRequest,
    ToolIdempotencyMode,
    ToolManifest,
    ToolSideEffectClass,
    approval_ref_for_request,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime
from skeleton.skills.tool_saga import (
    AsyncToolSagaRuntime,
    SQLiteToolSagaStore,
    ToolSagaConflict,
    ToolSagaDenied,
    ToolSagaInDoubt,
    ToolSagaStatus,
    ToolSagaStep,
    tool_saga_plan_digest,
)


def _uid(value: int) -> str:
    return str(UUID(int=value))


def _now() -> datetime:
    return datetime(2026, 10, 4, 1, 40, tzinfo=timezone.utc)


def _read_manifest(tool_id: str = "repo.read") -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="bounded read fixture",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    )


def _write_manifest(
    *,
    tool_id: str = "repo.write",
    compensation_tool_id: str = "repo.undo",
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="reversible write fixture",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "fail": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.WRITE,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.COMPENSATABLE,
        effect=ToolEffect.REVERSIBLE,
        compensation_tool_id=compensation_tool_id,
    )


def _undo_manifest(tool_id: str = "repo.undo") -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="reversal fixture",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.WRITE,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        effect=ToolEffect.REVERSIBLE,
    )


def _request(
    *,
    request_id: int,
    operation_id: str,
    tool_id: str,
    key: str,
    name: str,
    fail: bool | None = None,
) -> ToolExecutionRequest:
    arguments: dict[str, object] = {"name": name}
    if fail is not None:
        arguments["fail"] = fail
    return ToolExecutionRequest(
        request_id=_uid(request_id),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id=tool_id,
        idempotency_key=key,
        arguments=arguments,
        requested_at=_now(),
    )


def _step(
    *,
    request_id: int,
    operation_id: str,
    key: str,
    name: str,
    fail: bool = False,
) -> ToolSagaStep:
    forward = _request(
        request_id=request_id,
        operation_id=operation_id,
        tool_id="repo.write",
        key=key,
        name=name,
        fail=fail,
    )
    compensation = _request(
        request_id=request_id + 100,
        operation_id=operation_id,
        tool_id="repo.undo",
        key=f"{key}:undo",
        name=name,
    )
    return ToolSagaStep(
        forward=forward,
        compensation=compensation,
    )


async def _register_write_pair(
    runtime: AsyncToolRuntime,
    *,
    calls: list[str],
    fail_undo_name: str | None = None,
) -> None:
    async def forward(request: ToolExecutionRequest) -> str:
        name = str(request.arguments["name"])
        calls.append(f"forward:{name}")
        if request.arguments.get("fail") is True:
            raise RuntimeError(f"forward failed for {name}")
        return f"artifact:forward:{name}"

    async def undo(request: ToolExecutionRequest) -> str:
        name = str(request.arguments["name"])
        calls.append(f"undo:{name}")
        if name == fail_undo_name:
            raise RuntimeError(f"undo failed for {name}")
        return f"artifact:undo:{name}"

    await runtime.register(_write_manifest(), forward)
    await runtime.register(_undo_manifest(), undo)


@pytest.mark.asyncio
async def test_saga_success_commits_forward_receipts_without_compensation(
    tmp_path,
) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    calls: list[str] = []

    async def read(request: ToolExecutionRequest) -> str:
        calls.append(f"read:{request.arguments['name']}")
        return "artifact:read"

    await runtime.register(_read_manifest(), read)
    await _register_write_pair(runtime, calls=calls)

    operation_id = _uid(10)
    steps = (
        ToolSagaStep(
            forward=_request(
                request_id=11,
                operation_id=operation_id,
                tool_id="repo.read",
                key="read-a",
                name="a",
            )
        ),
        _step(
            request_id=12,
            operation_id=operation_id,
            key="write-b",
            name="b",
        ),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    receipt = await saga.execute(_uid(13), steps, now=_now())

    assert receipt.status is ToolSagaStatus.SUCCEEDED
    assert receipt.terminal is True
    assert receipt.next_forward == 2
    assert receipt.next_compensation == -1
    assert len(receipt.forward_receipt_ids) == 2
    assert receipt.compensation_receipt_ids == ()
    assert receipt.compensation_failures == ()
    assert receipt.failed_step_index is None
    assert calls == ["read:a", "forward:b"]
    assert saga_store.get(_uid(13)) == receipt


@pytest.mark.asyncio
async def test_failed_forward_compensates_current_and_prior_steps_in_reverse(
    tmp_path,
) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    calls: list[str] = []
    await _register_write_pair(runtime, calls=calls)

    operation_id = _uid(20)
    steps = (
        _step(request_id=21, operation_id=operation_id, key="a", name="a"),
        _step(request_id=22, operation_id=operation_id, key="b", name="b"),
        _step(
            request_id=23,
            operation_id=operation_id,
            key="c",
            name="c",
            fail=True,
        ),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    receipt = await saga.execute(_uid(24), steps, now=_now())

    assert receipt.status is ToolSagaStatus.COMPENSATED
    assert receipt.failed_step_index == 2
    assert receipt.error_code == "RuntimeError"
    assert len(receipt.forward_receipt_ids) == 3
    assert len(receipt.compensation_receipt_ids) == 3
    assert receipt.compensation_failures == ()
    assert calls == [
        "forward:a",
        "forward:b",
        "forward:c",
        "undo:c",
        "undo:b",
        "undo:a",
    ]


@pytest.mark.asyncio
async def test_compensation_failure_does_not_skip_remaining_rollbacks(
    tmp_path,
) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    calls: list[str] = []
    await _register_write_pair(runtime, calls=calls, fail_undo_name="b")

    operation_id = _uid(30)
    steps = (
        _step(request_id=31, operation_id=operation_id, key="a", name="a"),
        _step(request_id=32, operation_id=operation_id, key="b", name="b"),
        _step(
            request_id=33,
            operation_id=operation_id,
            key="c",
            name="c",
            fail=True,
        ),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    receipt = await saga.execute(_uid(34), steps, now=_now())

    assert receipt.status is ToolSagaStatus.COMPENSATION_FAILED
    assert receipt.failed_step_index == 2
    assert receipt.compensation_failures == ("1:RuntimeError",)
    assert len(receipt.compensation_receipt_ids) == 3
    assert calls[-3:] == ["undo:c", "undo:b", "undo:a"]


@pytest.mark.asyncio
async def test_terminal_saga_replays_after_restart_without_side_effects(
    tmp_path,
) -> None:
    tool_path = tmp_path / "tool.sqlite3"
    saga_path = tmp_path / "saga.sqlite3"
    operation_id = _uid(40)
    saga_id = _uid(41)
    steps = (
        _step(
            request_id=42,
            operation_id=operation_id,
            key="restart-a",
            name="a",
        ),
    )
    first_calls: list[str] = []

    first_tool_store = SQLiteToolReceiptStore(tool_path)
    first_saga_store = SQLiteToolSagaStore(saga_path)
    first_runtime = AsyncToolRuntime(receipt_store=first_tool_store)
    await _register_write_pair(first_runtime, calls=first_calls)
    first_saga = AsyncToolSagaRuntime(first_runtime, first_saga_store)

    original = await first_saga.execute(saga_id, steps, now=_now())
    first_tool_store.close()
    first_saga_store.close()

    second_calls: list[str] = []
    second_tool_store = SQLiteToolReceiptStore(tool_path)
    second_saga_store = SQLiteToolSagaStore(saga_path)
    second_runtime = AsyncToolRuntime(receipt_store=second_tool_store)
    await _register_write_pair(second_runtime, calls=second_calls)
    second_saga = AsyncToolSagaRuntime(second_runtime, second_saga_store)

    replay = await second_saga.execute(saga_id, steps, now=_now())

    assert original.status is ToolSagaStatus.SUCCEEDED
    assert replay == original
    assert first_calls == ["forward:a"]
    assert second_calls == []


@pytest.mark.asyncio
async def test_saga_id_reuse_with_changed_plan_fails_closed(tmp_path) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    calls: list[str] = []
    await _register_write_pair(runtime, calls=calls)

    operation_id = _uid(50)
    saga_id = _uid(51)
    original_steps = (
        _step(
            request_id=52,
            operation_id=operation_id,
            key="stable-a",
            name="a",
        ),
    )
    changed_steps = (
        _step(
            request_id=53,
            operation_id=operation_id,
            key="stable-b",
            name="b",
        ),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)
    await saga.execute(saga_id, original_steps, now=_now())

    with pytest.raises(ToolSagaConflict, match="different tenant, operation, or plan"):
        await saga.execute(saga_id, changed_steps, now=_now())


def test_saga_requires_durable_tool_receipts(tmp_path) -> None:
    runtime = AsyncToolRuntime()
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")

    with pytest.raises(ToolSagaDenied, match="durable tool receipt store"):
        AsyncToolSagaRuntime(runtime, saga_store)


@pytest.mark.asyncio
async def test_saga_preflight_rejects_irreversible_forward_tool(tmp_path) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    manifest = ToolManifest(
        tool_id="repo.destroy",
        version="1.0.0",
        description="irreversible fixture",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.DESTRUCTIVE,
        side_effect_class=ToolSideEffectClass.LOCAL_IRREVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.RESERVATION_FENCE,
        approval_policy=ToolApprovalPolicy.ALWAYS,
        effect=ToolEffect.IRREVERSIBLE,
        approval_required=True,
    )
    calls: list[str] = []

    async def handler(_request: ToolExecutionRequest) -> str:
        calls.append("effect")
        return "artifact:destroyed"

    await runtime.register(manifest, handler)
    base = _request(
        request_id=61,
        operation_id=_uid(60),
        tool_id="repo.destroy",
        key="destroy",
        name="target",
    )
    approved = replace(base, approval_ref=approval_ref_for_request(base))
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    with pytest.raises(ToolSagaDenied, match="irreversible tools"):
        await saga.execute(
            _uid(62),
            (ToolSagaStep(forward=approved),),
            now=_now(),
        )
    assert calls == []


@pytest.mark.asyncio
async def test_saga_rejects_read_only_noop_compensation(tmp_path) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)

    async def forward(_request: ToolExecutionRequest) -> str:
        return "artifact:write"

    async def noop(_request: ToolExecutionRequest) -> str:
        return "artifact:noop"

    await runtime.register(_write_manifest(), forward)
    await runtime.register(
        ToolManifest(
            tool_id="repo.undo",
            version="1.0.0",
            description="invalid no-op compensation",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            authority_class=ToolAuthorityClass.READ,
            side_effect_class=ToolSideEffectClass.NONE,
            idempotency_mode=ToolIdempotencyMode.NOT_REQUIRED,
            effect=ToolEffect.READ_ONLY,
        ),
        noop,
    )
    operation_id = _uid(64)
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    with pytest.raises(ToolSagaDenied, match="compensation tool must be reversible"):
        await saga.execute(
            _uid(65),
            (
                ToolSagaStep(
                    forward=_request(
                        request_id=66,
                        operation_id=operation_id,
                        tool_id="repo.write",
                        key="write",
                        name="a",
                    ),
                    compensation=_request(
                        request_id=67,
                        operation_id=operation_id,
                        tool_id="repo.undo",
                        key="undo",
                        name="a",
                    ),
                ),
            ),
            now=_now(),
        )


@pytest.mark.asyncio
async def test_saga_rejects_compensation_without_mutation_authority(tmp_path) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)

    async def forward(_request: ToolExecutionRequest) -> str:
        return "artifact:write"

    async def weak_undo(_request: ToolExecutionRequest) -> str:
        return "artifact:undo"

    await runtime.register(_write_manifest(), forward)
    await runtime.register(
        ToolManifest(
            tool_id="repo.undo",
            version="1.0.0",
            description="invalid read-authority compensation",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            authority_class=ToolAuthorityClass.READ,
            side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
            idempotency_mode=ToolIdempotencyMode.INTRINSIC,
            effect=ToolEffect.REVERSIBLE,
        ),
        weak_undo,
    )
    operation_id = _uid(68)
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    with pytest.raises(ToolSagaDenied, match="requires mutation authority"):
        await saga.execute(
            _uid(69),
            (
                ToolSagaStep(
                    forward=_request(
                        request_id=70,
                        operation_id=operation_id,
                        tool_id="repo.write",
                        key="write",
                        name="a",
                    ),
                    compensation=_request(
                        request_id=71,
                        operation_id=operation_id,
                        tool_id="repo.undo",
                        key="undo",
                        name="a",
                    ),
                ),
            ),
            now=_now(),
        )


@pytest.mark.asyncio
async def test_reversible_saga_tool_requires_compensatable_contract(
    tmp_path,
) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)

    manifest = ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="wrong idempotency fixture",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.WRITE,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        effect=ToolEffect.REVERSIBLE,
        compensation_tool_id="repo.undo",
    )

    async def forward(_request: ToolExecutionRequest) -> str:
        return "artifact:write"

    async def undo(_request: ToolExecutionRequest) -> str:
        return "artifact:undo"

    await runtime.register(manifest, forward)
    await runtime.register(_undo_manifest(), undo)
    operation_id = _uid(70)
    step = ToolSagaStep(
        forward=_request(
            request_id=71,
            operation_id=operation_id,
            tool_id="repo.write",
            key="write",
            name="a",
        ),
        compensation=_request(
            request_id=72,
            operation_id=operation_id,
            tool_id="repo.undo",
            key="undo",
            name="a",
        ),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    with pytest.raises(ToolSagaDenied, match="must be compensatable"):
        await saga.execute(_uid(73), (step,), now=_now())


def test_plan_digest_rejects_duplicate_idempotency_keys() -> None:
    operation_id = _uid(80)
    step = ToolSagaStep(
        forward=_request(
            request_id=81,
            operation_id=operation_id,
            tool_id="repo.write",
            key="duplicate",
            name="a",
        ),
        compensation=_request(
            request_id=82,
            operation_id=operation_id,
            tool_id="repo.undo",
            key="duplicate",
            name="a",
        ),
    )

    with pytest.raises(ToolSagaDenied, match="distinct idempotency keys"):
        tool_saga_plan_digest((step,))


@pytest.mark.asyncio
async def test_durable_saga_owner_blocks_concurrent_executor(tmp_path) -> None:
    saga_path = tmp_path / "saga.sqlite3"
    tool_path = tmp_path / "tool.sqlite3"
    operation_id = _uid(90)
    saga_id = _uid(91)
    steps = (
        _step(
            request_id=92,
            operation_id=operation_id,
            key="concurrent",
            name="a",
        ),
    )

    entered = asyncio.Event()
    release = asyncio.Event()
    first_calls: list[str] = []
    second_calls: list[str] = []

    first_tool_store = SQLiteToolReceiptStore(tool_path)
    first_saga_store = SQLiteToolSagaStore(saga_path)
    first_runtime = AsyncToolRuntime(receipt_store=first_tool_store)

    async def first_forward(request: ToolExecutionRequest) -> str:
        first_calls.append(str(request.arguments["name"]))
        entered.set()
        await release.wait()
        return "artifact:first"

    async def first_undo(_request: ToolExecutionRequest) -> str:
        return "artifact:first-undo"

    await first_runtime.register(_write_manifest(), first_forward)
    await first_runtime.register(_undo_manifest(), first_undo)

    second_tool_store = SQLiteToolReceiptStore(tool_path)
    second_saga_store = SQLiteToolSagaStore(saga_path)
    second_runtime = AsyncToolRuntime(receipt_store=second_tool_store)

    async def second_forward(request: ToolExecutionRequest) -> str:
        second_calls.append(str(request.arguments["name"]))
        return "artifact:second"

    async def second_undo(_request: ToolExecutionRequest) -> str:
        second_calls.append("undo")
        return "artifact:second-undo"

    await second_runtime.register(_write_manifest(), second_forward)
    await second_runtime.register(_undo_manifest(), second_undo)

    first_saga = AsyncToolSagaRuntime(first_runtime, first_saga_store)
    second_saga = AsyncToolSagaRuntime(second_runtime, second_saga_store)
    first_task = asyncio.create_task(
        first_saga.execute(
            saga_id,
            steps,
            owner_token=_uid(93),
            now=_now(),
        )
    )
    await entered.wait()

    with pytest.raises(ToolSagaInDoubt, match="different durable execution owner"):
        await second_saga.execute(
            saga_id,
            steps,
            owner_token=_uid(94),
            now=_now(),
        )

    assert second_calls == []
    release.set()
    receipt = await first_task
    assert receipt.status is ToolSagaStatus.SUCCEEDED
    assert first_calls == ["a"]


@pytest.mark.asyncio
async def test_explicit_orphan_recovery_requires_same_plan(tmp_path) -> None:
    tool_store = SQLiteToolReceiptStore(tmp_path / "tool.sqlite3")
    saga_store = SQLiteToolSagaStore(tmp_path / "saga.sqlite3")
    runtime = AsyncToolRuntime(receipt_store=tool_store)
    calls: list[str] = []
    await _register_write_pair(runtime, calls=calls)

    operation_id = _uid(100)
    saga_id = _uid(101)
    steps = (
        _step(
            request_id=102,
            operation_id=operation_id,
            key="recover",
            name="a",
        ),
    )
    digest = tool_saga_plan_digest(steps)
    saga_store.claim(
        saga_id=saga_id,
        tenant_id="tenant-a",
        operation_id=operation_id,
        plan_digest=digest,
        owner_token=_uid(103),
        now=_now(),
    )
    saga = AsyncToolSagaRuntime(runtime, saga_store)

    with pytest.raises(ToolSagaInDoubt):
        await saga.execute(
            saga_id,
            steps,
            owner_token=_uid(104),
            now=_now(),
        )

    with pytest.raises(ToolSagaInDoubt, match="owner changed before orphan recovery"):
        await saga.recover_orphaned(
            saga_id,
            steps,
            expected_owner_token=_uid(999),
            now=_now(),
        )

    recovered = await saga.recover_orphaned(
        saga_id,
        steps,
        expected_owner_token=_uid(103),
        now=_now(),
    )
    assert recovered.status is ToolSagaStatus.RUNNING

    receipt = await saga.execute(
        saga_id,
        steps,
        owner_token=_uid(105),
        now=_now(),
    )
    assert receipt.status is ToolSagaStatus.SUCCEEDED
    assert calls == ["forward:a"]
