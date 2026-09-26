from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolContractError,
    ToolEffect,
    ToolIdempotencyMode,
    ToolRiskClass,
    ToolSideEffectClass,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
    approval_ref_for_request,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import (
    AsyncToolRuntime,
    ToolExecutionConflict,
    ToolRuntime,
)


def _now() -> datetime:
    return datetime(2026, 9, 23, 16, 30, tzinfo=timezone.utc)


def _manifest(
    tool_id: str = "repo.read",
    *,
    effect: ToolEffect = ToolEffect.READ_ONLY,
    approval_required: bool = False,
    data_policy: str = "internal:test",
    network_policy: str = "none",
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="test tool",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=effect,
        approval_required=approval_required,
        data_policy=data_policy,
        network_policy=network_policy,
    )


def _request(
    *,
    operation_id: str | None = None,
    request_id: str | None = None,
    tool_id: str = "repo.read",
    key: str = "idem-1",
    path: str = "README.md",
    approval_ref: str | None = None,
    data_class: str = "internal",
    transfer_purpose: str = "tool-execution",
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        request_id=request_id or str(uuid4()),
        operation_id=operation_id or str(uuid4()),
        tenant_id="tenant-a",
        tool_id=tool_id,
        idempotency_key=key,
        arguments={"path": path},
        requested_at=_now(),
        approval_ref=approval_ref,
        data_class=data_class,
        transfer_purpose=transfer_purpose,
    )


def _approved(request: ToolExecutionRequest) -> ToolExecutionRequest:
    return replace(
        request,
        approval_ref=approval_ref_for_request(request),
    )


@pytest.mark.parametrize(
    "tool_id",
    ["", "Repo.Read", "../escape", "has space", "x" * 129],
)
def test_manifest_rejects_unsafe_tool_ids(tool_id: str) -> None:
    with pytest.raises(ToolContractError):
        _manifest(tool_id)


def test_irreversible_tool_requires_approval_contract() -> None:
    with pytest.raises(ToolContractError, match="require approval"):
        _manifest(
            "repo.delete",
            effect=ToolEffect.IRREVERSIBLE,
            approval_required=False,
        )


def test_request_digest_is_order_independent_and_secret_free() -> None:
    left = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="k",
        arguments={"token": "super-secret", "b": 2, "a": 1},
        requested_at=_now(),
    )
    right = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="k2",
        arguments={"a": 1, "b": 2, "token": "super-secret"},
        requested_at=_now(),
    )
    assert left.arguments_digest == right.arguments_digest
    assert len(left.arguments_digest) == 64
    assert all(char in "0123456789abcdef" for char in left.arguments_digest)
    assert "super-secret" not in left.arguments_digest


def test_exact_idempotent_replay_executes_once_and_returns_same_receipt() -> None:
    calls: list[str] = []
    runtime = ToolRuntime()
    runtime.register(_manifest(), lambda request: calls.append(request.request_id) or "artifact:1")
    operation_id = str(uuid4())
    request = _request(operation_id=operation_id, key="same")

    first = runtime.execute(request, now=_now())
    second = runtime.execute(request, now=_now())

    assert first == second
    assert first.status is ToolExecutionStatus.SUCCEEDED
    assert first.result_ref == "artifact:1"
    assert first.request_id == request.request_id
    assert first.operation_id == operation_id
    assert len(calls) == 1


def test_idempotency_replay_with_changed_arguments_conflicts() -> None:
    runtime = ToolRuntime()
    runtime.register(_manifest(), lambda request: "artifact:1")
    operation_id = str(uuid4())
    runtime.execute(
        _request(operation_id=operation_id, key="same", path="a"),
        now=_now(),
    )

    with pytest.raises(ToolExecutionConflict, match="different tool or arguments"):
        runtime.execute(
            _request(operation_id=operation_id, key="same", path="b"),
            now=_now(),
        )


def test_approval_denial_is_receipted_without_handler_execution() -> None:
    calls: list[str] = []
    runtime = ToolRuntime()
    runtime.register(
        _manifest(
            "repo.delete",
            effect=ToolEffect.IRREVERSIBLE,
            approval_required=True,
        ),
        lambda request: calls.append(request.request_id) or "deleted:1",
    )

    receipt = runtime.execute(
        _request(tool_id="repo.delete"),
        now=_now(),
    )

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "approval_required"
    assert receipt.metered_tool_calls == 0
    assert calls == []


def test_approved_irreversible_tool_retains_approval_lineage() -> None:
    runtime = ToolRuntime()
    runtime.register(
        _manifest(
            "repo.delete",
            effect=ToolEffect.IRREVERSIBLE,
            approval_required=True,
        ),
        lambda request: "deletion-receipt:1",
    )
    request = _approved(_request(tool_id="repo.delete"))

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    assert receipt.approval_ref == approval_ref_for_request(request)
    assert receipt.arguments_digest == request.arguments_digest


def test_handler_failure_is_sanitized_into_receipt() -> None:
    runtime = ToolRuntime()

    def fail(_request):
        raise RuntimeError("sensitive backend details")

    runtime.register(_manifest(), fail)
    receipt = runtime.execute(_request(), now=_now())

    assert receipt.status is ToolExecutionStatus.FAILED
    assert receipt.error_code == "RuntimeError"
    assert receipt.result_ref is None
    assert "sensitive backend details" not in str(receipt.as_dict())


def test_admission_meter_runs_before_handler_side_effect() -> None:
    events: list[str] = []

    class Meter:
        def meter_tool_call(self, operation_id, event_id, *, now_wall=None):
            events.append(f"meter:{operation_id}:{event_id}")
            return object()

    runtime = ToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]
    runtime.register(
        _manifest(),
        lambda request: events.append(f"handler:{request.operation_id}") or "artifact:1",
    )
    request = _request()

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    assert events[0].startswith(f"meter:{request.operation_id}:tool:")
    assert events[1] == f"handler:{request.operation_id}"


def test_registry_rejects_manifest_redefinition() -> None:
    runtime = ToolRuntime()
    runtime.register(_manifest(), lambda request: "one")

    with pytest.raises(ToolExecutionConflict, match="different manifest"):
        runtime.register(
            ToolManifest(
                tool_id="repo.read",
                version="2.0.0",
                description="different",
                input_schema={"type": "object"},
            ),
            lambda request: "two",
        )


def test_manifest_rejects_malformed_schema_shapes() -> None:
    with pytest.raises(ToolContractError, match="required references unknown"):
        ToolManifest(
            tool_id="repo.bad",
            version="1.0.0",
            description="bad schema",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["missing"],
            },
        )

    with pytest.raises(ToolContractError, match="nesting depth"):
        schema = {"type": "object"}
        cursor = schema
        for _ in range(18):
            child = {"type": "object"}
            cursor["properties"] = {"x": child}
            cursor = child
        ToolManifest(
            tool_id="repo.deep",
            version="1.0.0",
            description="too deep",
            input_schema=schema,
        )


def test_schema_invalid_request_is_denied_before_handler_or_meter() -> None:
    events: list[str] = []

    class Meter:
        def meter_tool_call(self, operation_id, event_id, *, now_wall=None):
            events.append("meter")
            return object()

    runtime = ToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]
    runtime.register(
        _manifest(),
        lambda request: events.append("handler") or "artifact:1",
    )
    request = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="bad-args",
        arguments={},
        requested_at=_now(),
    )

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "arguments_invalid"
    assert receipt.metered_tool_calls == 0
    assert events == []


def test_schema_rejects_additional_arguments_when_closed() -> None:
    runtime = ToolRuntime()
    runtime.register(_manifest(), lambda request: "artifact:1")
    request = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="extra-args",
        arguments={"path": "README.md", "unexpected": True},
        requested_at=_now(),
    )

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "arguments_invalid"


@pytest.mark.asyncio
async def test_async_concurrent_exact_retries_execute_once() -> None:
    runtime = AsyncToolRuntime()
    calls = 0
    release = asyncio.Event()

    async def handler(_request):
        nonlocal calls
        calls += 1
        await release.wait()
        return "artifact:shared"

    await runtime.register(_manifest(), handler)
    operation_id = str(uuid4())
    request = _request(operation_id=operation_id, key="concurrent")
    first_task = asyncio.create_task(runtime.execute(request, now=_now()))
    await asyncio.sleep(0)
    second_task = asyncio.create_task(runtime.execute(request, now=_now()))
    await asyncio.sleep(0)

    assert calls == 1
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first == second
    assert first.status is ToolExecutionStatus.SUCCEEDED
    assert calls == 1


@pytest.mark.asyncio
async def test_async_conflicting_retry_is_rejected_while_first_is_inflight() -> None:
    runtime = AsyncToolRuntime()
    release = asyncio.Event()

    async def handler(_request):
        await release.wait()
        return "artifact:shared"

    await runtime.register(_manifest(), handler)
    operation_id = str(uuid4())
    first = _request(operation_id=operation_id, key="same", path="a")
    first_task = asyncio.create_task(runtime.execute(first, now=_now()))
    await asyncio.sleep(0)

    with pytest.raises(ToolExecutionConflict, match="different tool or arguments"):
        await runtime.execute(
            _request(operation_id=operation_id, key="same", path="b"),
            now=_now(),
        )

    release.set()
    receipt = await first_task
    assert receipt.status is ToolExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_async_postcondition_failure_runs_compensation_and_receipts_it() -> None:
    runtime = AsyncToolRuntime()
    events: list[str] = []
    manifest = ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="write tool",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        compensation_tool_id="repo.rollback",
    )

    async def handler(_request):
        events.append("write")
        return "mutation:1"

    async def postcondition(_request, result_ref):
        events.append(f"verify:{result_ref}")
        return False

    async def compensate(_request, result_ref):
        events.append(f"rollback:{result_ref}")
        return "compensation:1"

    await runtime.register(
        manifest,
        handler,
        postcondition=postcondition,
        compensate=compensate,
    )
    request = _request(tool_id="repo.write")

    receipt = await runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.FAILED
    assert receipt.error_code == "postcondition_failed"
    assert receipt.compensation_ref == "compensation:1"
    assert events == ["write", "verify:mutation:1", "rollback:mutation:1"]


@pytest.mark.asyncio
async def test_async_budget_denial_happens_before_handler() -> None:
    events: list[str] = []

    class Meter:
        def meter_tool_call(self, operation_id, event_id, *, now_wall=None):
            events.append("meter")
            raise RuntimeError("budget exhausted")

    runtime = AsyncToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]

    async def handler(_request):
        events.append("handler")
        return "artifact:1"

    await runtime.register(_manifest(), handler)
    receipt = await runtime.execute(_request(), now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "budget_denied"
    assert receipt.metered_tool_calls == 0
    assert events == ["meter"]


def test_sync_budget_denial_is_receipted_before_handler() -> None:
    events: list[str] = []

    class Meter:
        def meter_tool_call(self, operation_id, event_id, *, now_wall=None):
            events.append("meter")
            raise RuntimeError("budget exhausted")

    runtime = ToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]
    runtime.register(
        _manifest(),
        lambda request: events.append("handler") or "artifact:1",
    )

    receipt = runtime.execute(_request(), now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "budget_denied"
    assert receipt.metered_tool_calls == 0
    assert events == ["meter"]


@pytest.mark.asyncio
async def test_async_owner_cancellation_releases_reservation_for_retry() -> None:
    runtime = AsyncToolRuntime()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return "artifact:1"

    await runtime.register(_manifest(), handler)
    operation_id = str(uuid4())
    request = _request(operation_id=operation_id, key="cancel-retry")

    owner = asyncio.create_task(runtime.execute(request, now=_now()))
    await entered.wait()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner

    release.set()
    retry = await runtime.execute(request, now=_now())

    assert retry.status is ToolExecutionStatus.SUCCEEDED
    assert calls == 2



def test_sync_approval_required_denial_can_resume_with_approval() -> None:
    calls = []
    runtime = ToolRuntime()
    runtime.register(
        _manifest(
            "repo.write",
            effect=ToolEffect.REVERSIBLE,
            approval_required=True,
        ),
        lambda request: calls.append(request.approval_ref) or "artifact:write",
    )
    operation_id = str(uuid4())
    pending = _request(
        operation_id=operation_id,
        tool_id="repo.write",
        key="approval-resume",
    )

    denied = runtime.execute(pending, now=_now())
    approved_request = _approved(
        _request(
            operation_id=operation_id,
            request_id=pending.request_id,
            tool_id="repo.write",
            key="approval-resume",
        )
    )
    approved = runtime.execute(approved_request, now=_now())

    assert denied.status is ToolExecutionStatus.DENIED
    assert denied.error_code == "approval_required"
    assert approved.status is ToolExecutionStatus.SUCCEEDED
    assert approved.approval_ref == approval_ref_for_request(approved_request)
    assert calls == [approved_request.approval_ref]


@pytest.mark.asyncio
async def test_async_approval_required_denial_can_resume_with_approval() -> None:
    calls = []
    runtime = AsyncToolRuntime()

    async def handler(request):
        calls.append(request.approval_ref)
        return "artifact:write"

    await runtime.register(
        _manifest(
            "repo.write",
            effect=ToolEffect.REVERSIBLE,
            approval_required=True,
        ),
        handler,
    )
    operation_id = str(uuid4())
    pending = _request(
        operation_id=operation_id,
        tool_id="repo.write",
        key="approval-resume-async",
    )

    denied = await runtime.execute(pending, now=_now())
    approved_request = _approved(
        _request(
            operation_id=operation_id,
            request_id=pending.request_id,
            tool_id="repo.write",
            key="approval-resume-async",
        )
    )
    approved = await runtime.execute(approved_request, now=_now())

    assert denied.status is ToolExecutionStatus.DENIED
    assert denied.error_code == "approval_required"
    assert approved.status is ToolExecutionStatus.SUCCEEDED
    assert approved.approval_ref == approval_ref_for_request(approved_request)
    assert calls == [approved_request.approval_ref]



def test_sync_durable_receipt_replays_after_runtime_restart(tmp_path) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    operation_id = str(uuid4())
    request = _request(
        operation_id=operation_id,
        key="restart-sync",
    )
    calls: list[str] = []

    first_store = SQLiteToolReceiptStore(path)
    first_runtime = ToolRuntime(receipt_store=first_store)
    first_runtime.register(
        _manifest(),
        lambda _request: calls.append("first") or "artifact:1",
    )
    first = first_runtime.execute(request, now=_now())
    first_store.close()

    second_store = SQLiteToolReceiptStore(path)
    second_runtime = ToolRuntime(receipt_store=second_store)
    second_runtime.register(
        _manifest(),
        lambda _request: calls.append("duplicate") or "artifact:2",
    )
    replay = second_runtime.execute(request, now=_now())

    assert first.status is ToolExecutionStatus.SUCCEEDED
    assert replay == first
    assert calls == ["first"]
    assert (
        second_runtime.receipt(
            tenant_id="tenant-a",
            operation_id=operation_id,
            idempotency_key="restart-sync",
        )
        == first
    )


@pytest.mark.asyncio
async def test_async_durable_receipt_replays_after_runtime_restart(tmp_path) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    operation_id = str(uuid4())
    request = _request(
        operation_id=operation_id,
        key="restart-async",
    )
    calls: list[str] = []

    first_store = SQLiteToolReceiptStore(path)
    first_runtime = AsyncToolRuntime(receipt_store=first_store)

    async def first_handler(_request):
        calls.append("first")
        return "artifact:1"

    await first_runtime.register(_manifest(), first_handler)
    first = await first_runtime.execute(request, now=_now())
    first_store.close()

    second_store = SQLiteToolReceiptStore(path)
    second_runtime = AsyncToolRuntime(receipt_store=second_store)

    async def duplicate_handler(_request):
        calls.append("duplicate")
        return "artifact:2"

    await second_runtime.register(_manifest(), duplicate_handler)
    replay = await second_runtime.execute(request, now=_now())

    assert first.status is ToolExecutionStatus.SUCCEEDED
    assert replay == first
    assert calls == ["first"]
    assert (
        await second_runtime.receipt(
            tenant_id="tenant-a",
            operation_id=operation_id,
            idempotency_key="restart-async",
        )
        == first
    )


def test_sync_pending_durable_reservation_fails_closed_without_effect(tmp_path) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    operation_id = str(uuid4())
    request = _request(
        operation_id=operation_id,
        key="in-doubt-sync",
    )
    store = SQLiteToolReceiptStore(path)
    reservation = store.reserve(request, now=_now())
    assert reservation.status == "owner"
    store.close()

    calls: list[str] = []
    reopened = SQLiteToolReceiptStore(path)
    runtime = ToolRuntime(receipt_store=reopened)
    runtime.register(
        _manifest(),
        lambda _request: calls.append("effect") or "artifact:1",
    )

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "execution_in_doubt"
    assert receipt.metered_tool_calls == 0
    assert calls == []


@pytest.mark.asyncio
async def test_async_pending_durable_reservation_fails_closed_without_effect(
    tmp_path,
) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    operation_id = str(uuid4())
    request = _request(
        operation_id=operation_id,
        key="in-doubt-async",
    )
    store = SQLiteToolReceiptStore(path)
    reservation = store.reserve(request, now=_now())
    assert reservation.status == "owner"
    store.close()

    calls: list[str] = []
    reopened = SQLiteToolReceiptStore(path)
    runtime = AsyncToolRuntime(receipt_store=reopened)

    async def handler(_request):
        calls.append("effect")
        return "artifact:1"

    await runtime.register(_manifest(), handler)
    receipt = await runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "execution_in_doubt"
    assert receipt.metered_tool_calls == 0
    assert calls == []

def test_tool_request_requires_complete_execution_lineage() -> None:
    with pytest.raises(ToolContractError, match="must be supplied together"):
        ToolExecutionRequest(
            request_id=str(uuid4()),
            operation_id=str(uuid4()),
            execution_id=str(uuid4()),
            tenant_id="tenant-a",
            tool_id="repo.read",
            idempotency_key="partial-lineage",
            arguments={"path": "README.md"},
            requested_at=_now(),
        )


def test_approval_binding_preserves_legacy_identity_and_binds_full_lineage() -> None:
    request = _request(key="approval-legacy")
    legacy_material = "\x1f".join(
        (
            request.operation_id,
            request.tenant_id,
            request.tool_id,
            request.arguments_digest,
        )
    ).encode("utf-8")
    legacy_ref = "approval:" + hashlib.sha256(legacy_material).hexdigest()

    assert approval_ref_for_request(request) == legacy_ref

    lineaged = replace(
        request,
        execution_id=str(uuid4()),
        turn_id=str(uuid4()),
        call_id=str(uuid4()),
    )
    assert approval_ref_for_request(lineaged) != legacy_ref

def test_manifest_governance_metadata_is_normalized_and_serialized() -> None:
    manifest = ToolManifest(
        tool_id="repo.write",
        version="2.1.0",
        description="Write one bounded repository object",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        capabilities=("repository.write", "repository.write"),
        authority_class=ToolAuthorityClass.WRITE,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.RESERVATION_FENCE,
        approval_policy=ToolApprovalPolicy.ALWAYS,
        network_policy="none",
        data_policy="internal:repository",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=65536,
        max_concurrency=4,
        effect=ToolEffect.REVERSIBLE,
    )

    payload = manifest.as_dict()
    assert manifest.capabilities == ("repository.write",)
    assert manifest.approval_required is True
    assert payload["authority_class"] == "write"
    assert payload["risk_class"] == "high"
    assert payload["side_effect_class"] == "local_reversible"
    assert payload["idempotency_mode"] == "reservation_fence"
    assert payload["approval_policy"] == "always"
    assert payload["network_policy"] == "none"
    assert payload["data_policy"] == "internal:repository"
    assert payload["cost_model"] == {
        "kind": "request",
        "estimated_units": 1,
    }
    assert payload["result_size_limit"] == 65536
    assert payload["max_concurrency"] == 4
    assert payload["enabled"] is True


def test_non_read_manifest_requires_explicit_idempotency_mode() -> None:
    with pytest.raises(
        ToolContractError,
        match="non-read authority requires an idempotency mode",
    ):
        ToolManifest(
            tool_id="repo.write",
            version="1.0.0",
            description="Unsafe write manifest",
            input_schema={
                "type": "object",
                "additionalProperties": False,
            },
            authority_class=ToolAuthorityClass.WRITE,
        )


def test_critical_or_irreversible_manifest_requires_approval_policy() -> None:
    with pytest.raises(
        ToolContractError,
        match="critical tools require non-never approval policy",
    ):
        ToolManifest(
            tool_id="ops.critical",
            version="1.0.0",
            description="Critical operator action",
            input_schema={
                "type": "object",
                "additionalProperties": False,
            },
            risk_class=ToolRiskClass.CRITICAL,
        )

    with pytest.raises(
        ToolContractError,
        match="irreversible side effects require approval policy",
    ):
        ToolManifest(
            tool_id="repo.erase",
            version="1.0.0",
            description="Irreversible local change",
            input_schema={
                "type": "object",
                "additionalProperties": False,
            },
            authority_class=ToolAuthorityClass.DESTRUCTIVE,
            risk_class=ToolRiskClass.HIGH,
            side_effect_class=ToolSideEffectClass.LOCAL_IRREVERSIBLE,
            idempotency_mode=ToolIdempotencyMode.RESERVATION_FENCE,
        )


def test_manifest_output_schema_and_bounds_fail_closed() -> None:
    with pytest.raises(ToolContractError):
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Bad output contract",
            input_schema={"type": "object"},
            output_schema={"type": "definitely-not-json"},
        )

    with pytest.raises(ToolContractError, match="result_size_limit"):
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Oversized result contract",
            input_schema={"type": "object"},
            result_size_limit=2 * 1024 * 1024 * 1024,
        )

    with pytest.raises(ToolContractError, match="max_concurrency"):
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Invalid concurrency contract",
            input_schema={"type": "object"},
            max_concurrency=0,
        )

def test_manifest_cost_model_is_metered_before_sync_handler() -> None:
    events = []

    class Meter:
        def record_usage_event(
            self,
            operation_id,
            event_id,
            category,
            delta,
            *,
            now_wall=None,
        ):
            events.append(
                (
                    "meter",
                    operation_id,
                    event_id,
                    category,
                    delta.tool_calls,
                    delta.cost_usd,
                )
            )
            return object()

    runtime = ToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]
    manifest = ToolManifest(
        tool_id="repo.read",
        version="1.0.0",
        description="metered read",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        cost_model={
            "kind": "request",
            "estimated_cost_usd": 0.25,
        },
    )
    runtime.register(
        manifest,
        lambda request: events.append(("handler", request.operation_id))
        or "artifact:metered",
    )
    request = _request()

    receipt = runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    assert events[0][0] == "meter"
    assert events[0][1] == request.operation_id
    assert events[0][3:] == ("tool", 1, 0.25)
    assert events[1] == ("handler", request.operation_id)


@pytest.mark.asyncio
async def test_async_manifest_max_concurrency_is_enforced_per_tool() -> None:
    runtime = AsyncToolRuntime()
    entered_first = asyncio.Event()
    release_first = asyncio.Event()
    entered_second = asyncio.Event()
    active = 0
    peak = 0
    calls = 0

    async def handler(_request):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            if calls == 1:
                entered_first.set()
                await release_first.wait()
            else:
                entered_second.set()
            await asyncio.sleep(0)
            return f"artifact:{calls}"
        finally:
            active -= 1

    manifest = ToolManifest(
        tool_id="repo.read",
        version="1.0.0",
        description="serialized read",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        max_concurrency=1,
    )
    await runtime.register(manifest, handler)

    first = asyncio.create_task(
        runtime.execute(
            _request(
                operation_id=str(uuid4()),
                key="concurrency-first",
            ),
            now=_now(),
        )
    )
    await entered_first.wait()

    second = asyncio.create_task(
        runtime.execute(
            _request(
                operation_id=str(uuid4()),
                key="concurrency-second",
            ),
            now=_now(),
        )
    )
    await asyncio.sleep(0)
    assert entered_second.is_set() is False

    release_first.set()
    first_receipt, second_receipt = await asyncio.gather(first, second)

    assert first_receipt.status is ToolExecutionStatus.SUCCEEDED
    assert second_receipt.status is ToolExecutionStatus.SUCCEEDED
    assert entered_second.is_set() is True
    assert peak == 1
    assert calls == 2


def test_manifest_rejects_invalid_estimated_cost() -> None:
    with pytest.raises(
        ToolContractError,
        match="estimated_cost_usd must be non-negative numeric",
    ):
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="bad cost",
            input_schema={"type": "object"},
            cost_model={
                "kind": "request",
                "estimated_cost_usd": -0.01,
            },
        )

def test_sync_tool_privacy_denial_precedes_meter_and_handler() -> None:
    events: list[str] = []

    class Meter:
        def meter_tool_call(self, operation_id, event_id, *, now_wall=None):
            events.append("meter")
            return object()

    runtime = ToolRuntime(admission_runtime=Meter())  # type: ignore[arg-type]
    runtime.register(
        _manifest(
            "web.search",
            data_policy="public:untrusted",
            network_policy="public-search:bounded-egress",
        ),
        lambda request: events.append("handler") or "search:1",
    )

    receipt = runtime.execute(
        _request(
            tool_id="web.search",
            data_class="internal",
        ),
        now=_now(),
    )

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "tool_data_ceiling_exceeded"
    assert receipt.governance_decision_ref.startswith("gov-tool-")
    assert receipt.metered_tool_calls == 0
    assert events == []


def test_sync_public_tool_transfer_executes_with_governance_receipt() -> None:
    calls: list[str] = []
    runtime = ToolRuntime()
    runtime.register(
        _manifest(
            "web.search",
            data_policy="public:untrusted",
            network_policy="public-search:bounded-egress",
        ),
        lambda request: calls.append(request.data_class) or "search:1",
    )

    receipt = runtime.execute(
        _request(
            tool_id="web.search",
            data_class="public",
        ),
        now=_now(),
    )

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    assert receipt.data_class == "public"
    assert receipt.transfer_purpose == "tool-execution"
    assert receipt.governance_decision_ref.startswith("gov-tool-")
    assert calls == ["public"]


def test_privacy_context_change_conflicts_for_same_idempotency_identity() -> None:
    runtime = ToolRuntime()
    runtime.register(_manifest(), lambda request: "artifact:1")
    operation_id = str(uuid4())
    runtime.execute(
        _request(
            operation_id=operation_id,
            key="privacy-replay",
            data_class="internal",
        ),
        now=_now(),
    )

    with pytest.raises(ToolExecutionConflict, match="privacy context"):
        runtime.execute(
            _request(
                operation_id=operation_id,
                key="privacy-replay",
                data_class="public",
            ),
            now=_now(),
        )


@pytest.mark.asyncio
async def test_async_tool_privacy_denial_precedes_handler() -> None:
    calls: list[str] = []
    runtime = AsyncToolRuntime()

    async def handler(request):
        calls.append(request.data_class)
        return "search:1"

    await runtime.register(
        _manifest(
            "web.search",
            data_policy="public:untrusted",
            network_policy="public-search:bounded-egress",
        ),
        handler,
    )
    receipt = await runtime.execute(
        _request(
            tool_id="web.search",
            data_class="internal",
        ),
        now=_now(),
    )

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "tool_data_ceiling_exceeded"
    assert receipt.governance_decision_ref.startswith("gov-tool-")
    assert calls == []
