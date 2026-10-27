"""Fail-closed bridge tests over existing durable engine and source owners."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

from skeleton.ai.runtime.inference.canonical_snapshot_reader import (
    CanonicalCompiledSnapshotReader,
)
from skeleton.ai.runtime.inference.engine_submission_snapshot import (
    CurrentSourceCustody, EngineSubmissionCompiledInputLoader,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError,
)


TENANT = "tenant"
CONTEXT = "00000000-0000-4000-8000-000000000001"
EXECUTION = "00000000-0000-4000-8000-000000000002"
REQUEST = "a" * 64
SEGMENTS = (("00000000-0000-4000-8000-000000000003", "b" * 64),)


class Source:
    def __init__(self):
        self.calls = 0
        self.current = CurrentSourceCustody(TENANT, CONTEXT, SEGMENTS, 7)
        self.outage = False

    async def inspect(self, *, tenant_id, context_id):
        self.calls += 1
        assert (tenant_id, context_id) == (TENANT, CONTEXT)
        if self.outage:
            raise ConnectionError("source unavailable")
        return self.current


class Repo:
    def __init__(self):
        request = SimpleNamespace(execution_id=EXECUTION, identity_digest="digest")
        self.execution = SimpleNamespace(
            request=request, operation_id="operation", version=4,
            cancellation_requested=False, terminal=False,
        )

    def get(self, execution_id):
        assert execution_id == EXECUTION
        return self.execution


class Submissions:
    def __init__(self):
        handoff = SimpleNamespace(
            execution_id=EXECUTION, operation_id="operation",
            tenant_id=TENANT, context_id=CONTEXT, handoff_digest="c" * 64,
            source_snapshot=SEGMENTS, instructions="owner policy",
            history=(("user", "initial"),), prompt="latest",
        )
        operation = SimpleNamespace(operation_id="operation", tenant_id=TENANT)
        command = SimpleNamespace(
            compiled_context=handoff, operation=operation,
            execution_request=SimpleNamespace(identity_digest="digest"),
        )
        self.stored = SimpleNamespace(command=command)

    def get_by_execution_id(self, execution_id):
        assert execution_id == EXECUTION
        return self.stored


def owner():
    return SimpleNamespace(submissions=Submissions(), repository=Repo())


def loader(service=None, custody=None):
    service = service or owner()
    custody = custody or Source()
    return EngineSubmissionCompiledInputLoader(
        service=service, execution_id=EXECUTION,
        native_request_digest=REQUEST, source_authority=custody,
    ), service, custody


async def inspect(bound):
    return await bound.read(
        tenant_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
    )


def test_valid_source_custody_and_durable_version_produce_authoritative_merkle_snapshot():
    async def scenario():
        bound, service, custody = loader()
        record = await inspect(bound)
        assert record.instructions == "owner policy"
        assert record.history == (("user", "initial"),)
        reader = CanonicalCompiledSnapshotReader(
            loader=bound, policy_sha256=sha256(b"owner policy").hexdigest(),
        )
        snapshot = await reader.resolve(
            tenant_scope_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
        )
        assert snapshot.snapshot_version == record.source_version
        assert snapshot.tenant_id == TENANT
        assert custody.calls == 2
        custody.current = replace(custody.current, version=8)
        changed = await inspect(bound)
        assert changed.source_version != record.source_version
        service.repository.execution.version += 1
        changed_again = await inspect(bound)
        assert changed_again.source_version != changed.source_version

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", [
    {"revoked": True}, {"tenant_id": "foreign"}, {"context_id": "foreign"},
    {"source_snapshot": ()}, {"version": 0}, {"version": True},
])
def test_mismatched_or_revoked_source_custody_refuses_release(damage):
    async def scenario():
        custody = Source()
        custody.current = replace(custody.current, **damage)
        bound, _, _ = loader(custody=custody)
        with pytest.raises(SealedContextIntegrityError):
            await inspect(bound)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", [
    ("cancellation_requested", True),
    ("terminal", True),
    ("version", 0),
    ("version", True),
    ("operation_id", "other"),
])
def test_cancelled_terminal_corrupt_or_foreign_execution_denied(change):
    async def scenario():
        bound, service, source = loader()
        setattr(service.repository.execution, *change)
        with pytest.raises(SealedContextBoundaryError):
            await inspect(bound)
        assert source.calls == 0
    asyncio.run(scenario())


def test_owner_outage_fails_closed():
    async def scenario():
        bound, _, source = loader()
        source.outage = True
        with pytest.raises(SealedContextBoundaryError, match="binding"):
            await inspect(bound)
    asyncio.run(scenario())


def test_cross_tenant_context_and_native_digest_never_query_source():
    async def scenario():
        bound, _, source = loader()
        for tenant, context, request in [
            ("foreign", CONTEXT, REQUEST),
            (TENANT, "foreign", REQUEST),
            (TENANT, CONTEXT, "e" * 64),
        ]:
            with pytest.raises(SealedContextBoundaryError):
                await bound.read(
                    tenant_id=tenant, context_id=context, request_digest=request,
                )
        assert source.calls == 0
    asyncio.run(scenario())


def test_missing_durable_submission_denied():
    async def scenario():
        bound, service, source = loader()
        service.submissions.stored = None
        with pytest.raises(SealedContextBoundaryError):
            await inspect(bound)
        assert source.calls == 0
    asyncio.run(scenario())


def test_loader_requires_real_existing_owner_and_source_interfaces():
    with pytest.raises(SealedContextBoundaryError):
        loader(service=SimpleNamespace(submissions=None, repository=None))
    with pytest.raises(SealedContextBoundaryError):
        loader(custody=object())


def test_durable_owner_drift_withholds_guarded_generation():
    from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
    from skeleton.context.pre_delivery_guard import GuardedLocalInference, ReviewVerdict, merkle_root
    from skeleton.context.sealed_sandwich import SealedContextReplayError

    class Request:
        instructions = "owner policy"
        history = (("user", "initial"),)
        prompt = "latest"
        digest = REQUEST
        context_digest = merkle_root((
            ("system", b"owner policy"), ("user", b"initial"), ("user", b"latest"),
        ))

        @property
        def rendered_input(self):
            return "system: owner policy\\nuser: initial\\nuser: latest\\nassistant:"

    async def scenario():
        bound, service, source = loader()
        canonical = CanonicalCompiledSnapshotReader(
            loader=bound, policy_sha256=sha256(b"owner policy").hexdigest(),
        )

        class Engine:
            model = object()
            calls = 0

            async def generate(self, request, **kwargs):
                self.calls += 1
                source.current = replace(source.current, version=source.current.version + 1)
                return SimpleNamespace(text="MUST_NOT_DELIVER")

        engine = Engine()
        guard = GuardedLocalInference(
            engine,
            reviewer=lambda text, digest: ReviewVerdict(True, digest, "separate-reviewer", "pass"),
            tokenize=lambda text: tuple(text.encode("utf-8")),
            detokenize=lambda ids: bytes(ids).decode("utf-8"),
        )
        protected = CanonicalGuardedLocalService(guard, snapshots=canonical)
        with pytest.raises(SealedContextReplayError, match="changed"):
            await protected.generate(Request(), tenant_scope_id=TENANT, context_id=CONTEXT)
        assert engine.calls == 1 and source.calls == 2

    asyncio.run(scenario())


def test_durable_owner_cancellation_during_guarded_generation_withholds_result():
    from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
    from skeleton.context.pre_delivery_guard import GuardedLocalInference, ReviewVerdict, merkle_root

    class Request:
        instructions = "owner policy"
        history = (("user", "initial"),)
        prompt = "latest"
        digest = REQUEST
        context_digest = merkle_root((
            ("system", b"owner policy"), ("user", b"initial"), ("user", b"latest"),
        ))

        @property
        def rendered_input(self):
            return "system: owner policy\\nuser: initial\\nuser: latest\\nassistant:"

    async def scenario():
        bound, service, source = loader()
        canonical = CanonicalCompiledSnapshotReader(
            loader=bound, policy_sha256=sha256(b"owner policy").hexdigest(),
        )

        class Engine:
            model = object()
            calls = 0

            async def generate(self, request, **kwargs):
                self.calls += 1
                service.repository.execution.cancellation_requested = True
                return SimpleNamespace(text="MUST_NOT_DELIVER")

        engine = Engine()
        guard = GuardedLocalInference(
            engine,
            reviewer=lambda text, digest: ReviewVerdict(True, digest, "separate-reviewer", "pass"),
            tokenize=lambda text: tuple(text.encode("utf-8")),
            detokenize=lambda ids: bytes(ids).decode("utf-8"),
        )
        protected = CanonicalGuardedLocalService(guard, snapshots=canonical)
        with pytest.raises(SealedContextBoundaryError):
            await protected.generate(Request(), tenant_scope_id=TENANT, context_id=CONTEXT)
        assert engine.calls == 1 and source.calls == 1

    asyncio.run(scenario())
