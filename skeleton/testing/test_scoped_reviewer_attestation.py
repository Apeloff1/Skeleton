"""Trusted execution reader attestation binding, using isolated owner fixtures."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from skeleton.ai.runtime.inference.canonical_execution_source_factory import CanonicalExecutionSourceFactory
from skeleton.ai.runtime.inference.engine_submission_snapshot import ScopedEngineCompiledSnapshotReader
from skeleton.ai.runtime.inference.reviewer_custody import ReviewerCustodyVerifier
from skeleton.ai.runtime.inference.native_guard_binding import NativeGuardPins
from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
from skeleton.context.pre_delivery_guard import TrustedContextSnapshot, GuardedLocalInference
from skeleton.context.sealed_sandwich import SealedContextBoundaryError, SealedContextIntegrityError
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

DIGEST = "a"*64
SNAPSHOT = TrustedContextSnapshot("b"*64, "c"*64, 999, "tenant", "thread")
PIN = NativeGuardPins("local", "d"*64, "e"*64, "f"*64)


def fixture():
    operation = SimpleNamespace(tenant_id="tenant", actor_id="durable-actor", operation_id="op")
    handoff = SimpleNamespace(tenant_id="tenant", context_id="thread", execution_id="exec",
                              handoff_digest="handoff")
    request = SimpleNamespace(execution_id="exec", identity_digest="identity")
    command = SimpleNamespace(operation=operation, compiled_context=handoff, execution_request=request,
                              submission_digest="submission")
    execution = SimpleNamespace(request=request, operation_id="op", cancellation_requested=False,
                                terminal=False, version=4)
    service = SimpleNamespace(submissions=SimpleNamespace(get_by_execution_id=lambda _: SimpleNamespace(command=command)),
                              repository=SimpleNamespace(get=lambda _: execution))
    epoch = object.__new__(MongoCanonicalSourceEpoch)
    epoch.read_epoch = AsyncMock(return_value=8)
    factory = object.__new__(CanonicalExecutionSourceFactory)
    factory.shared_epoch = epoch
    reader = ScopedEngineCompiledSnapshotReader(service=service, source_authority_factory=factory,
                                                policy_sha256="c"*64)
    reader.resolve = AsyncMock(return_value=SNAPSHOT)
    verifier = object.__new__(ReviewerCustodyVerifier)
    verifier.verify = AsyncMock(return_value=None)
    return reader, verifier, epoch, operation, execution


def scope(reader):
    return reader.bind_execution(execution_id="exec", tenant_id="tenant", context_id="thread",
                                 request_digest=DIGEST)


def test_attestation_uses_real_epoch_not_snapshot_version_and_durable_actor():
    async def run():
        reader, verifier, epoch, _, _ = fixture()
        with scope(reader):
            await reader.attest_reviewer(verifier=verifier, pin=PIN, snapshot=SNAPSHOT,
                                        request_digest=DIGEST)
        verifier.verify.assert_awaited_once_with(tenant_id="tenant", actor_id="durable-actor",
            context_id="thread", epoch=8, model_digest=PIN.model_digest,
            runtime_digest=PIN.runtime_digest, tokenizer_digest=PIN.tokenizer_digest)
        assert epoch.read_epoch.await_count == 2
    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["epoch", "actor", "cancelled", "snapshot"])
def test_attestation_after_network_denies_changed_authority(mutation):
    async def run():
        reader, verifier, epoch, owner, execution = fixture()
        async def rotate(**kwargs):
            if mutation == "epoch":
                epoch.read_epoch.return_value = 10
            elif mutation == "actor":
                owner.actor_id = "other"
            elif mutation == "cancelled":
                execution.cancellation_requested = True
            elif mutation == "snapshot":
                reader.resolve.return_value = TrustedContextSnapshot(
                    SNAPSHOT.root, SNAPSHOT.policy_sha256, 1000, "tenant", "thread")
        verifier.verify.side_effect = rotate
        with scope(reader):
            with pytest.raises((SealedContextBoundaryError, SealedContextIntegrityError)):
                await reader.attest_reviewer(verifier=verifier, pin=PIN, snapshot=SNAPSHOT,
                                            request_digest=DIGEST)
    asyncio.run(run())


def test_foreign_request_and_child_task_are_denied_before_verifier():
    async def run():
        reader, verifier, _, _, _ = fixture()
        with scope(reader):
            for task in (reader.attest_reviewer(verifier=verifier, pin=PIN, snapshot=SNAPSHOT,
                                               request_digest="0"*64),
                         asyncio.create_task(reader.attest_reviewer(verifier=verifier, pin=PIN,
                                                    snapshot=SNAPSHOT, request_digest=DIGEST))):
                with pytest.raises(SealedContextBoundaryError):
                    await task
        verifier.verify.assert_not_awaited()
    asyncio.run(run())


def test_guard_service_rejects_nonempty_attestation_result_and_redacts_error():
    async def run():
        reader, _, _, _, _ = fixture()
        engine = SimpleNamespace(generate=AsyncMock())
        guard = GuardedLocalInference(engine, reviewer=lambda *a: None)
        for answer in (True, {"raw":"authority"}):
            service = CanonicalGuardedLocalService(guard, snapshots=reader,
                                                  attest_source=AsyncMock(return_value=answer))
            with pytest.raises(SealedContextBoundaryError):
                await service._read(tenant_scope_id="tenant", context_id="thread",
                                    request_digest=DIGEST)
        service = CanonicalGuardedLocalService(guard, snapshots=reader,
            attest_source=AsyncMock(side_effect=RuntimeError("private connection")))
        with pytest.raises(SealedContextBoundaryError) as error:
            await service._read(tenant_scope_id="tenant", context_id="thread", request_digest=DIGEST)
        assert "private" not in str(error.value)
        engine.generate.assert_not_awaited()
    asyncio.run(run())
