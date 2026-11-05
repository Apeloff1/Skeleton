"""Retained checkpoint recovery stays durable, bounded and metered."""

import asyncio
from datetime import timedelta

import pytest

from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import EngineServiceError
from skeleton.contracts.ai_execution import AIExecutionResult
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_runtime import AsyncToolRuntime
from skeleton.testing.test_engine_checkpoint_upgrade import _legacy_checkpoint
from skeleton.testing.test_engine_execution_coordinator import (
    FakeProvider, FakeRegistry, _bundle, _now, _service, _verified_execution,
)


def _submit(service, execution_id, *, waiting=False, legacy=True):
    _, command = _bundle(execution_id=execution_id)
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    if legacy:
        _legacy_checkpoint(service, command, provider, waiting=waiting)
    else:
        runtime = CognitiveExecutionRuntime(
            service.repository, provider, AsyncToolRuntime(), verification_hook=_verified_execution,
        )
        handoff = command.compiled_context
        payload = runtime._initial_payload(
            command.execution_request, instructions=handoff.instructions,
            prompt=handoff.prompt, history=(), context_digest=handoff.context_digest,
        )
        current = service.repository.get(execution_id)
        service.repository.checkpoint(
            execution_id, payload, expected_execution_version=current.version,
            expected_checkpoint_version=current.checkpoint_version,
        )
    return command, provider


def _deny(*_args, **_kwargs):
    raise EngineServiceError("admission unavailable")


def _coordinator(service, provider=None):
    return EngineExecutionCoordinator(
        service, provider_registry=FakeRegistry(provider, unavailable=provider is None),
        tool_runtime=AsyncToolRuntime(), verification_hook=_verified_execution,
    )


async def _drain(coordinator):
    await asyncio.gather(*tuple(coordinator._tasks.values()))
    await asyncio.sleep(0)


def _due_ids(repo, now, *, include_waiting=False):
    return {item.execution_id for item in repo.recoverable_page(now=now, include_waiting=include_waiting)}


@pytest.mark.parametrize("waiting", [False, True])
def test_deferral_survives_reopen_and_respects_backoff(tmp_path, waiting):
    service = _service(tmp_path)
    command, _ = _submit(service, "retained", waiting=waiting)
    repo = service.repository
    now = _now()
    before = repo.latest_checkpoint("retained")
    assert repo.defer_checkpoint_admission("retained", now=now)
    # Startup also respects a durable retry deadline. Ordinary waiters have no
    # such marker and are visited once, without polling them every five seconds.
    assert not _due_ids(repo, now, include_waiting=True)
    reopened = SQLiteExecutionRepository(repo.path)
    try:
        assert not _due_ids(reopened, now + timedelta(seconds=29))
        assert _due_ids(reopened, now + timedelta(seconds=30)) == {command.execution_request.execution_id}
        assert reopened.latest_checkpoint("retained") == before
        reopened.clear_checkpoint_admission_deferral("retained")
        assert _due_ids(reopened, now + timedelta(seconds=31)) == (set() if waiting else {"retained"})
    finally:
        reopened.close()
        repo.close()
        service.submissions.close()


def test_deferral_does_not_create_retry_authority_for_new_or_terminal_work(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="new")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    repo = service.repository
    assert not repo.defer_checkpoint_admission("new")
    current = repo.get("new")
    result = AIExecutionResult(
        execution_id="new", operation_id=current.operation_id, status="failed", usage={}, completed_at=_now(),
    )
    repo.finalize(result, expected_execution_version=current.version)
    assert not repo.defer_checkpoint_admission("new")
    assert not _due_ids(repo, _now() + timedelta(days=1), include_waiting=True)


def test_idle_recovery_query_work_does_not_grow_with_passive_waiters(tmp_path):
    service = _service(tmp_path)
    repo = service.repository
    _submit(service, "idle-000", waiting=True)
    def count_instructions():
        count = 0
        def progress():
            nonlocal count
            count += 1
            return 0
        repo._connection.set_progress_handler(progress, 1)
        try:
            assert not repo.recoverable_page(include_waiting=False)
        finally:
            repo._connection.set_progress_handler(None, 0)
        return count
    small = count_instructions()
    for i in range(1, 257):
        _submit(service, f"idle-{i:03}", waiting=True)
    large = count_instructions()
    # Count SQLite VM work instead of timing a busy test host. Traversing the
    # passive backlog used thousands of instructions; index seeks stay flat.
    assert large <= small + 64, (small, large)


def test_recovery_merge_pages_actionable_and_due_waiters_without_duplicates(tmp_path):
    service = _service(tmp_path)
    repo = service.repository
    now = _now()
    expected = set()
    for i in range(6):
        execution_id = f"mixed-{i}"
        _submit(service, execution_id, waiting=bool(i % 2))
        repo.defer_checkpoint_admission(execution_id, now=now - timedelta(seconds=31))
        expected.add(execution_id)
    service.cancel("mixed-3", verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    _submit(service, "passive-unmarked", waiting=True)
    _submit(service, "future-active")
    repo.defer_checkpoint_admission("future-active", now=now)
    seen = []
    cursor = None
    for _ in range(4):
        page = repo.recoverable_page(
            include_waiting=False, now=now, limit=2,
            after_updated_at=None if cursor is None else cursor.updated_at,
            after_execution_id=None if cursor is None else cursor.execution_id,
        )
        seen.extend(item.execution_id for item in page)
        if not page:
            break
        cursor = page[-1]
    assert set(seen) == expected
    assert len(seen) == len(expected)


@pytest.mark.asyncio
async def test_due_admission_retry_resumes_original_provider_once(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, provider = _submit(service, "retry-provider", legacy=False)
    coordinator = _coordinator(service, provider)
    original = service.ensure_execution_admission
    monkeypatch.setattr(service, "ensure_execution_admission", _deny)
    try:
        await coordinator._drive(command)
        assert not provider.requests
        assert not await coordinator._recover_pending()
        monkeypatch.setattr(service, "ensure_execution_admission", original)
        service.repository.defer_checkpoint_admission("retry-provider", now=_now() - timedelta(seconds=31))
        assert await coordinator._recover_pending() == ("retry-provider",)
        await _drain(coordinator)
        result = service.repository.result("retry-provider")
        assert result is not None and result.status == "completed"
        assert result.final_output == "engine answer"
        assert len(provider.requests) == 1
        assert not await coordinator._recover_pending()
        assert not service.repository._connection.execute(
            "SELECT 1 FROM ai_execution_admission_deferral WHERE execution_id=?", ("retry-provider",),
        ).fetchone()
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_terminal_result_completes_admission_without_redundant_retry_delete(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, provider = _submit(service, "terminal-retry", legacy=False)
    coordinator = _coordinator(service, provider)
    service.repository.defer_checkpoint_admission("terminal-retry")
    completed = []
    original_complete = service.complete_execution_admission
    def complete(execution_id, **kwargs):
        completed.append(execution_id)
        return original_complete(execution_id, **kwargs)
    monkeypatch.setattr(service, "complete_execution_admission", complete)
    def unavailable(*_args, **_kwargs):
        raise AssertionError("terminal commit already deleted the marker atomically")
    monkeypatch.setattr(service.repository, "clear_checkpoint_admission_deferral", unavailable)
    try:
        await coordinator._drive(command)
        assert service.repository.result("terminal-retry").status == "completed"
        assert completed == ["terminal-retry"]
        assert not service.repository._connection.execute(
            "SELECT 1 FROM ai_execution_admission_deferral WHERE execution_id=?", ("terminal-retry",),
        ).fetchone()
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_waiter_cancellation_bypasses_retry_delay_and_uses_storage_meter(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, provider = _submit(service, "retry-cancel", waiting=True)
    coordinator = _coordinator(service)
    original = service.ensure_execution_admission
    monkeypatch.setattr(service, "ensure_execution_admission", _deny)
    metered = []
    original_meter = service.meter_execution_storage
    def meter(*args, **kwargs):
        metered.append(args[1:3])
        return original_meter(*args, **kwargs)
    monkeypatch.setattr(service, "meter_execution_storage", meter)
    try:
        await coordinator._drive(command)
        monkeypatch.setattr(service, "ensure_execution_admission", original)
        service.cancel("retry-cancel", verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
        assert await coordinator._recover_pending() == ("retry-cancel",)
        await _drain(coordinator)
        result = service.repository.result("retry-cancel")
        assert result is not None and result.status == "cancelled"
        assert metered
        assert not provider.requests
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_provider_outage_retains_approved_waiter_retry(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, _ = _submit(service, "retry-approved", waiting=True)
    coordinator = _coordinator(service)
    monkeypatch.setattr(service, "active_approval_refs", lambda _: {"call-upgrade": "approval-ref"})
    before = service.repository.latest_checkpoint("retry-approved")
    try:
        await coordinator._drive(command)
        assert service.repository.result("retry-approved") is None
        assert service.repository.latest_checkpoint("retry-approved") == before
        assert not _due_ids(service.repository, _now())
        assert _due_ids(service.repository, _now() + timedelta(seconds=31)) == {"retry-approved"}
        # Once there is no active approval to act on, passive observation can
        # clear the retry without executing the tool or calling the provider.
        monkeypatch.setattr(service, "active_approval_refs", lambda _: {})
        await coordinator._drive(command)
        assert not _due_ids(service.repository, _now() + timedelta(seconds=31))
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_retry_write_outage_preserves_waiter_and_schedules_bounded_rescan(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, _ = _submit(service, "retry-write", waiting=True)
    coordinator = _coordinator(service)
    coordinator._startup_waiter_scan = False
    monkeypatch.setattr(service, "ensure_execution_admission", _deny)
    def unavailable(*_args, **_kwargs):
        raise OSError("retry store temporarily unavailable")
    monkeypatch.setattr(service.repository, "defer_checkpoint_admission", unavailable)
    before = service.repository.latest_checkpoint("retry-write")
    try:
        await coordinator._drive(command)
        assert coordinator._startup_waiter_scan
        assert service.repository.result("retry-write") is None
        assert service.repository.latest_checkpoint("retry-write") == before
        assert coordinator.supervision_snapshot()["recovery"]["last_driver_error"] == "_PassiveRecoveryUnavailable"
    finally:
        await coordinator.shutdown()


@pytest.mark.parametrize("available", [False, True])
@pytest.mark.asyncio
async def test_retry_clear_outage_cannot_replace_waiter_with_failure(tmp_path, monkeypatch, available):
    service = _service(tmp_path)
    command, provider = _submit(service, "retry-clear", waiting=True)
    coordinator = _coordinator(service, provider if available else None)
    coordinator._startup_waiter_scan = False
    before = service.repository.latest_checkpoint("retry-clear")
    def unavailable(*_args, **_kwargs):
        raise OSError("retry acknowledgement temporarily unavailable")
    monkeypatch.setattr(service.repository, "clear_checkpoint_admission_deferral", unavailable)
    try:
        await coordinator._drive(command)
        assert coordinator._startup_waiter_scan
        assert service.repository.result("retry-clear") is None
        assert service.repository.latest_checkpoint("retry-clear") == before
        assert not provider.requests
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_startup_visits_waiters_across_all_pages_then_stops_polling(tmp_path):
    service = _service(tmp_path)
    expected = {f"waiter-{i:03}" for i in range(137)}
    for execution_id in sorted(expected):
        _submit(service, execution_id, waiting=True)
    coordinator = _coordinator(service)
    recovered = []
    try:
        for _ in range(8):
            ids = await coordinator._recover_pending(include_waiting=coordinator._startup_waiter_scan)
            assert len(ids) <= 32
            recovered.extend(ids)
            await _drain(coordinator)
            if not coordinator._startup_waiter_scan:
                break
        assert set(recovered) == expected
        assert len(recovered) == len(expected)
        assert not coordinator._startup_waiter_scan
        assert not await coordinator._recover_pending()
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_persistently_failing_early_waiter_does_not_starve_later_pages(tmp_path, monkeypatch):
    service = _service(tmp_path)
    expected = {f"fair-{i:03}" for i in range(70)}
    for execution_id in sorted(expected):
        _submit(service, execution_id, waiting=True)
    coordinator = _coordinator(service)
    monkeypatch.setattr(service, "ensure_execution_admission", _deny)
    def unavailable(*_args, **_kwargs):
        raise OSError("retry store temporarily unavailable")
    monkeypatch.setattr(service.repository, "defer_checkpoint_admission", unavailable)
    recovered = []
    try:
        for _ in range(3):
            recovered.extend(await coordinator._recover_pending(include_waiting=coordinator._startup_waiter_scan))
            await _drain(coordinator)
        assert set(recovered) == expected
        assert len(recovered) == len(expected)
        assert coordinator._startup_waiter_scan
        assert coordinator._recovery_cursor is None
        assert all(service.repository.result(execution_id) is None for execution_id in expected)
    finally:
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_restart_rediscovers_waiter_without_successful_retry_write(tmp_path, monkeypatch):
    service = _service(tmp_path)
    command, _ = _submit(service, "restart-unmarked", waiting=True)
    coordinator = _coordinator(service)
    original_admit = service.ensure_execution_admission
    monkeypatch.setattr(service, "ensure_execution_admission", _deny)
    def unavailable(*_args, **_kwargs):
        raise OSError("retry store temporarily unavailable")
    original_defer = service.repository.defer_checkpoint_admission
    monkeypatch.setattr(service.repository, "defer_checkpoint_admission", unavailable)
    await coordinator._drive(command)
    await coordinator.shutdown()
    monkeypatch.setattr(service, "ensure_execution_admission", original_admit)
    monkeypatch.setattr(service.repository, "defer_checkpoint_admission", original_defer)
    resumed = _coordinator(service)
    try:
        assert await resumed._recover_pending(include_waiting=resumed._startup_waiter_scan) == ("restart-unmarked",)
        await _drain(resumed)
        assert service.repository.result("restart-unmarked") is None
        assert not await resumed._recover_pending()
    finally:
        await resumed.shutdown()
