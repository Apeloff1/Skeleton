"""Guarded local service refuses stale snapshots and authority overrides."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
import time

import pytest

from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, ReviewVerdict, TrustedContextSnapshot,
    merkle_root, request_parts,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextError, SealedContextReplayError,
)


@dataclass(frozen=True)
class _Request:
    instructions: str = "policy"
    history: tuple = ()
    prompt: str = "Report status"
    digest: str = "request-digest"
    context_digest: str | None = None

    @property
    def rendered_input(self):
        return f"system: {self.instructions}\nuser: {self.prompt}\nassistant:"


class _Engine:
    model = object()

    def __init__(self):
        self.calls = 0

    async def generate(self, request, **kwargs):
        self.calls += 1
        return type("Result", (), {"text": "ok"})()


class _Authority:
    def __init__(self, request):
        self.snapshot = TrustedContextSnapshot(
            merkle_root(request_parts(request)),
            sha256(request.instructions.encode()).hexdigest(),
            1, "tenant", "thread",
        )
        self.calls = 0
        self.drift_at = None
        self.cross_tenant = False

    async def resolve(self, *, tenant_scope_id, context_id, request_digest):
        assert request_digest == "request-digest"
        self.calls += 1
        old = self.snapshot
        if self.drift_at == self.calls:
            return TrustedContextSnapshot(
                old.root, old.policy_sha256, old.snapshot_version + 1,
                old.tenant_id, old.context_id,
            )
        if self.cross_tenant:
            return TrustedContextSnapshot(
                old.root, old.policy_sha256, old.snapshot_version,
                "other", old.context_id,
            )
        return old


def _service(engine, authority):
    guard = GuardedLocalInference(
        engine,
        reviewer=lambda text, digest: ReviewVerdict(True, digest, "reviewer-v1", "pass"),
        tokenize=lambda text: list(text.encode()),
        detokenize=lambda token_ids: bytes(token_ids).decode(),
    )
    return CanonicalGuardedLocalService(guard, snapshots=authority)


def test_preflight_and_postflight_accept_unchanged_authority():
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    answer = asyncio.run(_service(engine, authority).generate(
        request, tenant_scope_id="tenant", context_id="thread",
    ))
    assert answer.result.text == "ok" and engine.calls == 1
    assert authority.calls == 3 and answer.canonical_snapshot_version == 1


def test_concurrent_policy_or_thread_edit_suppresses_output():
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    authority.drift_at = 3
    with pytest.raises(SealedContextReplayError):
        asyncio.run(_service(engine, authority).generate(
            request, tenant_scope_id="tenant", context_id="thread",
        ))
    assert engine.calls == 1


def test_revocation_during_review_denies_before_model_execution():
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    authority.drift_at = 2
    with pytest.raises(SealedContextReplayError, match="before local inference"):
        asyncio.run(_service(engine, authority).generate(
            request, tenant_scope_id="tenant", context_id="thread",
        ))
    assert engine.calls == 0


def test_stalled_pre_dispatch_authority_is_bounded_and_fails_closed():
    request, engine = _Request(), _Engine()

    class StalledAuthority(_Authority):
        async def resolve(self, **kwargs):
            if self.calls == 1:
                await asyncio.Event().wait()
            return await super().resolve(**kwargs)

    service = _service(engine, StalledAuthority(request))
    service.guard.review_timeout_seconds = 0.05
    with pytest.raises(SealedContextBoundaryError, match="authority timed out"):
        asyncio.run(service.generate(request, tenant_scope_id="tenant", context_id="thread"))
    assert engine.calls == 0


def test_cross_tenant_reader_denies_before_model_execution():
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    authority.cross_tenant = True
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(_service(engine, authority).generate(
            request, tenant_scope_id="tenant", context_id="thread",
        ))
    assert engine.calls == 0


def test_caller_cannot_supply_prepared_tensors_or_snapshot():
    request, engine = _Request(), _Engine()
    service = _service(engine, _Authority(request))
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(service.generate(
            request, tenant_scope_id="tenant", context_id="thread",
            prepared_input=object(),
        ))
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(service.generate(
            request, tenant_scope_id="tenant", context_id="thread",
            _before_dispatch=lambda: None,
        ))
    assert engine.calls == 0


@pytest.mark.parametrize("timeout", [True, None, 0, -1, 31, float("nan"), float("inf")])
def test_source_timeout_requires_finite_bounded_value(timeout):
    request, engine = _Request(), _Engine()
    service = _service(engine, _Authority(request))
    with pytest.raises(SealedContextError, match="source authority timeout"):
        CanonicalGuardedLocalService(
            service.guard, snapshots=service.snapshots, source_timeout_seconds=timeout,
        )


@pytest.mark.parametrize("read_number,expected_calls", [(1, 0), (3, 1)])
def test_initial_and_final_authority_reads_are_bounded(read_number, expected_calls):
    request, engine = _Request(), _Engine()

    class StalledAuthority(_Authority):
        async def resolve(self, **kwargs):
            if self.calls + 1 == read_number:
                await asyncio.Event().wait()
            return await super().resolve(**kwargs)

    service = _service(engine, StalledAuthority(request))
    service.source_timeout_seconds = 0.05

    async def scenario():
        with pytest.raises(SealedContextBoundaryError, match="source authority timed out"):
            await asyncio.wait_for(service.generate(
                request, tenant_scope_id="tenant", context_id="thread",
            ), timeout=1)
        assert engine.calls == expected_calls

    asyncio.run(scenario())


@pytest.mark.parametrize("read_number", [1, 3])
def test_source_read_respects_shared_inference_deadline_and_task_custody(read_number):
    request, engine = _Request(), _Engine()
    observed_tasks = []

    class StalledAuthority(_Authority):
        async def resolve(self, **kwargs):
            observed_tasks.append(asyncio.current_task())
            if self.calls + 1 == read_number:
                await asyncio.Event().wait()
            return await super().resolve(**kwargs)

    service = _service(engine, StalledAuthority(request))
    service.source_timeout_seconds = 2

    async def scenario():
        owner = asyncio.current_task()
        with pytest.raises(SealedContextBoundaryError, match="source authority timed out"):
            async with asyncio.timeout(1):
                await service.generate(
                    request, tenant_scope_id="tenant", context_id="thread",
                    deadline=time.monotonic() + 0.05,
                )
        assert observed_tasks and all(task is owner for task in observed_tasks)
        assert engine.calls == (0 if read_number == 1 else 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf"), -1, "tomorrow"])
def test_invalid_or_expired_deadline_rejects_before_source_or_model_call(deadline):
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    service = _service(engine, authority)
    with pytest.raises(SealedContextBoundaryError, match="deadline"):
        asyncio.run(service.generate(
            request, tenant_scope_id="tenant", context_id="thread", deadline=deadline,
        ))
    assert engine.calls == 0 and authority.calls == 0


@pytest.mark.parametrize("read_number", [1, 3])
def test_cancellation_during_source_read_propagates_and_withholds_output(read_number):
    request, engine = _Request(), _Engine()

    async def scenario():
        entered = asyncio.Event()

        class StalledAuthority(_Authority):
            async def resolve(self, **kwargs):
                if self.calls + 1 == read_number:
                    entered.set()
                    await asyncio.Event().wait()
                return await super().resolve(**kwargs)

        service = _service(engine, StalledAuthority(request))
        task = asyncio.create_task(service.generate(
            request, tenant_scope_id="tenant", context_id="thread",
        ))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert engine.calls == (0 if read_number == 1 else 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("read_number", [1, 2, 3])
@pytest.mark.parametrize("error_type", [RuntimeError, SealedContextReplayError])
def test_source_callback_failure_does_not_expose_private_context(read_number, error_type):
    import traceback

    request, engine = _Request(), _Engine()
    secret = "private-authority-source-canary-f82a"

    class FailedAuthority(_Authority):
        async def resolve(self, **kwargs):
            if self.calls + 1 == read_number:
                raise error_type("source failure involving " + secret)
            return await super().resolve(**kwargs)

    service = _service(engine, FailedAuthority(request))
    with pytest.raises(SealedContextBoundaryError, match="source authority unavailable") as caught:
        asyncio.run(service.generate(request, tenant_scope_id="tenant", context_id="thread"))
    assert secret not in str(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert engine.calls == int(read_number == 3)
