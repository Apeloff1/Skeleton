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
