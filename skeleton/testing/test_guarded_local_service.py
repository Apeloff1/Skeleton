"""Guarded local service refuses stale snapshots and authority overrides."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256

import pytest

from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, ReviewVerdict, TrustedContextSnapshot,
    merkle_root, request_parts,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextReplayError,
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
        self.drift = False
        self.cross_tenant = False

    async def resolve(self, *, tenant_scope_id, context_id, request_digest):
        assert request_digest == "request-digest"
        self.calls += 1
        old = self.snapshot
        if self.drift and self.calls == 2:
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
    assert authority.calls == 2 and answer.canonical_snapshot_version == 1


def test_concurrent_policy_or_thread_edit_suppresses_output():
    request, engine = _Request(), _Engine()
    authority = _Authority(request)
    authority.drift = True
    with pytest.raises(SealedContextReplayError):
        asyncio.run(_service(engine, authority).generate(
            request, tenant_scope_id="tenant", context_id="thread",
        ))
    assert engine.calls == 1


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
    assert engine.calls == 0
