"""Canonical server startup and persisted compiled-input snapshot proofs."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.runtime.inference.canonical_snapshot_reader import (
    CanonicalCompiledInput, CanonicalCompiledSnapshotReader,
)
from skeleton.ai.runtime.inference.guarded_composition import ProtectedLocalComponents
from skeleton.api.server import ServerState
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, ReviewVerdict, merkle_root,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError,
)


_CONTEXT = "00000000-0000-4000-8000-000000000001"
_DIGEST = "d" * 64


class CanonicalLoader:
    def __init__(self):
        self.calls = 0
        self.record = CanonicalCompiledInput(
            tenant_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            source_version=5, instructions="immutable policy",
            history=(("user", "initial question"), ("assistant", "earlier answer")),
            prompt="current question",
        )

    async def read(self, *, tenant_id, context_id, request_digest):
        self.calls += 1
        return self.record


def reader(loader):
    return CanonicalCompiledSnapshotReader(
        loader=loader, policy_sha256=sha256(b"immutable policy").hexdigest(),
    )


def trusted_components(snapshot):
    return ProtectedLocalComponents(
        snapshots=snapshot,
        reviewer=lambda text, digest: ReviewVerdict(True, digest, "operator-reviewer", "pass"),
        tokenize=lambda text: tuple(text.encode("utf-8")),
        detokenize=lambda tokens: bytes(tokens).decode("utf-8"),
        verify_native_tokenizer=lambda model, tokenize, detokenize: False,
        sampler_support=lambda model, contract: False,
        projection_attestor=lambda request, rendered, root: False,
    )


def test_snapshot_exact_spans_policy_and_version_are_derived_from_persisted_source():
    async def scenario():
        loader = CanonicalLoader()
        snapshot = await reader(loader).resolve(
            tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
        )
        expected = merkle_root((
            ("system", b"immutable policy"), ("user", b"initial question"),
            ("assistant", b"earlier answer"), ("user", b"current question"),
        ))
        assert snapshot.root == expected
        assert snapshot.policy_sha256 == sha256(b"immutable policy").hexdigest()
        assert snapshot.snapshot_version == 5 and loader.calls == 1
        loader.record = replace(loader.record, source_version=6, prompt="edited question")
        next_snapshot = await reader(loader).resolve(
            tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
        )
        assert next_snapshot != snapshot
    asyncio.run(scenario())


@pytest.mark.parametrize("changed", (
    {"tenant_id": "neighbor"}, {"context_id": "other"}, {"request_digest": "e" * 64},
    {"source_version": 0}, {"source_version": True}, {"revoked": True},
))
def test_snapshot_rejects_foreign_revoked_or_malformed_source(changed):
    async def scenario():
        loader = CanonicalLoader()
        loader.record = replace(loader.record, **changed)
        with pytest.raises(SealedContextBoundaryError):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
    asyncio.run(scenario())


def test_snapshot_requires_independent_unmodified_system_policy():
    async def scenario():
        loader = CanonicalLoader()
        loader.record = replace(loader.record, instructions="changed policy")
        with pytest.raises(SealedContextIntegrityError):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
    asyncio.run(scenario())


def test_snapshot_fails_closed_on_loader_outage():
    class Offline:
        async def read(self, **kwargs):
            raise ConnectionError("primary down")
    async def scenario():
        with pytest.raises(SealedContextBoundaryError, match="unavailable"):
            await reader(Offline()).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
    asyncio.run(scenario())


def test_server_guard_configuration_is_one_time_and_before_engine_startup():
    loader = CanonicalLoader()
    state = ServerState()
    components = trusted_components(reader(loader))
    with pytest.raises(TypeError):
        state.configure_engine_local_guard(object())
    state.configure_engine_local_guard(components)
    assert state._engine_local_guard_components is components
    with pytest.raises(RuntimeError, match="rebound"):
        state.configure_engine_local_guard(components)
    other = ServerState()
    other.engine_execution_coordinator = object()
    with pytest.raises(RuntimeError, match="before startup"):
        other.configure_engine_local_guard(components)
    shutting_down = ServerState()
    shutting_down._engine_shutdown_pending = True
    with pytest.raises(RuntimeError, match="before startup"):
        shutting_down.configure_engine_local_guard(components)


def test_compiled_snapshot_cannot_be_derived_from_client_digest_alone():
    async def scenario():
        loader = CanonicalLoader()
        for forged in ("f" * 64, "", "not-hex"):
            with pytest.raises(SealedContextBoundaryError):
                await reader(loader).resolve(
                    tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=forged,
                )
        assert loader.calls == 1
    asyncio.run(scenario())


def test_canonical_source_edit_during_inference_suppresses_answer():
    from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
    from skeleton.context.sealed_sandwich import SealedContextReplayError

    class Request:
        instructions = "immutable policy"
        history = (("user", "initial question"), ("assistant", "earlier answer"))
        prompt = "current question"
        digest = _DIGEST
        context_digest = None

        @property
        def rendered_input(self):
            return ("system: immutable policy\nuser: initial question\n"
                    "assistant: earlier answer\nuser: current question\nassistant:")

    async def scenario():
        loader = CanonicalLoader()

        class Engine:
            model = object()
            calls = 0

            async def generate(self, request, **kwargs):
                self.calls += 1
                loader.record = replace(loader.record, source_version=6)
                return type("Result", (), {"text": "must never escape"})()

        engine = Engine()
        guarded = GuardedLocalInference(
            engine,
            reviewer=lambda text, digest: ReviewVerdict(True, digest, "reviewer", "pass"),
            tokenize=lambda text: tuple(text.encode()),
            detokenize=lambda ids: bytes(ids).decode(),
        )
        service = CanonicalGuardedLocalService(guarded, snapshots=reader(loader))
        with pytest.raises(SealedContextReplayError, match="changed"):
            await service.generate(Request(), tenant_scope_id="tenant", context_id=_CONTEXT)
        assert engine.calls == 1
        assert loader.calls == 2

    asyncio.run(scenario())


def test_canonical_snapshot_history_and_unicode_budgets_fail_before_merkle_allocation():
    async def scenario():
        loader = CanonicalLoader()
        loader.record = replace(loader.record, history=(("user", "x"),) * 2001)
        with pytest.raises(SealedContextBoundaryError, match="structure"):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
        loader.record = replace(loader.record, history=(("user", "\ud800"),))
        with pytest.raises(SealedContextBoundaryError, match="Unicode"):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
        loader.record = replace(loader.record, history=(), prompt="x" * (4 * 1024 * 1024 + 1))
        with pytest.raises(SealedContextBoundaryError, match="admission"):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )

    asyncio.run(scenario())


def test_canonical_server_provider_factory_receives_exact_trusted_guard(monkeypatch):
    from skeleton.provider_runtime import ProviderRegistry

    components = trusted_components(reader(CanonicalLoader()))
    admission_authority = object()
    observed = []
    registry = object()

    def record(cls, *, admission_runtime, retain_unavailable, guarded_components):
        observed.append((admission_runtime, retain_unavailable, guarded_components))
        return registry

    monkeypatch.setattr(ProviderRegistry, "from_env", classmethod(record))
    result = ServerState._activate_engine_provider_registry(
        admission_runtime=admission_authority, guarded_local_components=components,
    )
    assert result is registry
    assert observed == [(admission_authority, True, components)]
    # No magic environment-generated verifier is substituted when the app
    # has not installed one. The registry retains fail-closed admission.
    assert ServerState._activate_engine_provider_registry(
        admission_runtime=admission_authority, guarded_local_components=None,
    ) is registry
    assert observed[-1] == (admission_authority, True, None)


def test_canonical_snapshot_rejects_aggregate_history_byte_budget():
    async def scenario():
        loader = CanonicalLoader()
        # Each individual span is under 4 MiB but the combined window is
        # over 16 MiB; this must not materialize a huge Merkle workload.
        loader.record = replace(
            loader.record,
            history=(("user", "x" * (4 * 1024 * 1024)),) * 5,
        )
        with pytest.raises(SealedContextBoundaryError, match="aggregate byte budget"):
            await reader(loader).resolve(
                tenant_scope_id="tenant", context_id=_CONTEXT, request_digest=_DIGEST,
            )
    asyncio.run(scenario())


def test_canonical_application_mongo_wiring_is_one_time_and_requires_fenced_real_owners():
    from types import SimpleNamespace
    from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch
    from skeleton.testing.test_mongo_source_epoch import Database

    epoch = MongoCanonicalSourceEpoch(Database())
    conversation = SimpleNamespace(canonical_source_epoch=epoch)
    memory = SimpleNamespace(canonical_source_epoch=epoch)
    digest = sha256(b"trusted instruction policy").hexdigest()
    state = ServerState()
    with pytest.raises(RuntimeError, match="installed writer epoch"):
        state.configure_engine_canonical_mongo_owners(
            conversation=SimpleNamespace(canonical_source_epoch=None),
            shared_epoch=epoch, policy_sha256=digest,
        )
    state.configure_engine_canonical_mongo_owners(
        conversation=conversation, memory=memory, memory_namespace="memory",
        shared_epoch=epoch, policy_sha256=digest,
    )
    assert state._engine_canonical_mongo_owners[0] is conversation
    with pytest.raises(RuntimeError, match="replaced"):
        state.configure_engine_canonical_mongo_owners(
            conversation=conversation, shared_epoch=epoch, policy_sha256=digest,
        )
    too_late = ServerState()
    too_late.engine_execution_service = object()
    with pytest.raises(RuntimeError, match="precede"):
        too_late.configure_engine_canonical_mongo_owners(
            conversation=conversation, shared_epoch=epoch, policy_sha256=digest,
        )


def test_canonical_application_source_factory_configuration_is_one_time():
    from skeleton.ai.runtime.inference.canonical_execution_source_factory import (
        CanonicalExecutionSourceFactory,
    )
    from skeleton.testing.test_canonical_execution_source_factory import (
        Resolver, Conversation,
    )

    factory = CanonicalExecutionSourceFactory(
        conversation=Conversation(), resolver=Resolver(),
    )
    state = ServerState()
    with pytest.raises(TypeError):
        state.configure_engine_canonical_sources(
            factory=object(), policy_sha256="a" * 64,
        )
    state.configure_engine_canonical_sources(
        factory=factory, policy_sha256="a" * 64,
    )
    with pytest.raises(RuntimeError, match="replaced"):
        state.configure_engine_canonical_sources(
            factory=factory, policy_sha256="a" * 64,
        )


def test_trusted_protected_bootstrap_requires_complete_real_owner_registration():
    from types import SimpleNamespace
    from skeleton.api.server import _run_trusted_protected_bootstrap
    from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch
    from skeleton.testing.test_mongo_source_epoch import Database

    async def scenario():
        with pytest.raises(TypeError, match="callable"):
            await _run_trusted_protected_bootstrap(ServerState(), object())
        empty = ServerState()
        with pytest.raises(RuntimeError, match="requires native guard"):
            await _run_trusted_protected_bootstrap(empty, lambda _state: None)
        assert empty.engine_execution_service is None

        epoch = MongoCanonicalSourceEpoch(Database())
        memory = SimpleNamespace(canonical_source_epoch=epoch)
        conversation = SimpleNamespace(canonical_source_epoch=epoch)
        components = trusted_components(reader(CanonicalLoader()))
        state = ServerState()

        async def compose(target):
            target.configure_engine_local_guard(components)
            target.configure_engine_canonical_mongo_owners(
                conversation=conversation, memory=memory, memory_namespace="memory",
                shared_epoch=epoch, policy_sha256="a" * 64,
            )

        await _run_trusted_protected_bootstrap(state, compose)
        assert state._engine_local_guard_components is components
        assert state._engine_canonical_mongo_owners[1] is memory
        assert state.engine_execution_service is None
        state.engine_execution_service = object()
        with pytest.raises(RuntimeError, match="precede engine startup"):
            await _run_trusted_protected_bootstrap(state, compose)

        # A guard without canonical source owners must not bring up a
        # supposedly protected local provider or mutate the engine service.
        missing = ServerState()
        with pytest.raises(RuntimeError, match="requires native guard"):
            await _run_trusted_protected_bootstrap(
                missing, lambda target: target.configure_engine_local_guard(components),
            )
        assert missing.engine_execution_service is None

    asyncio.run(scenario())


def test_protected_memory_writer_reuses_same_fenced_owner_without_creating_mongo_client(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from skeleton.persistence.memory_repository import MongoMemoryRepository
    from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch
    from skeleton.testing.test_mongo_source_epoch import Database

    class MemoryDatabase:
        def __getitem__(self, name):
            return SimpleNamespace(create_index=AsyncMock())

    class Writer:
        def __init__(self, repository, **kwargs):
            self.repository = repository

    class Projection:
        def __init__(self, repository, **kwargs):
            self.repository = repository

    monkeypatch.setattr("skeleton.memory.writeback.AsyncGovernedMemoryWriter", Writer)
    monkeypatch.setattr("skeleton.memory.projection.AsyncMemoryProjectionCoordinator", Projection)

    async def scenario():
        epoch = MongoCanonicalSourceEpoch(Database())
        memory = MongoMemoryRepository(MemoryDatabase(), canonical_source_epoch=epoch)
        conversation = SimpleNamespace(canonical_source_epoch=epoch)
        state = ServerState()
        state.engine_execution_admission_runtime = object()
        state.bind_governance_registry = lambda: object()
        registered = []
        state.governance_lifecycle_adapters = SimpleNamespace(
            register_deletion=lambda *args: registered.append(("delete", args)),
            register_export=lambda *args: registered.append(("export", args)),
        )
        state.configure_engine_canonical_mongo_owners(
            conversation=conversation, memory=memory, memory_namespace="memory",
            shared_epoch=epoch, policy_sha256="a" * 64,
        )
        with pytest.raises(RuntimeError, match="cannot be overridden"):
            await state.bind_canonical_memory_writer(database=object())
        assert state.canonical_memory_writer is None
        writer = await state.bind_canonical_memory_writer()
        assert writer.repository is memory
        assert state.canonical_memory_repository is memory
        assert state.canonical_memory_projection_coordinator.repository is memory
        assert state.canonical_memory_mongo_client is None
        assert len(registered) == 2

        # A fabricated memory owner cannot be substituted just because its
        # epoch attribute matches the expected durable instance.
        forged = ServerState()
        forged.engine_execution_admission_runtime = object()
        forged.configure_engine_canonical_mongo_owners(
            conversation=conversation, memory=SimpleNamespace(canonical_source_epoch=epoch),
            memory_namespace="memory", shared_epoch=epoch, policy_sha256="a" * 64,
        )
        with pytest.raises(RuntimeError, match="not epoch-fenced"):
            await forged.bind_canonical_memory_writer()

    asyncio.run(scenario())
