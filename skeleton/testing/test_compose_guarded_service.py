"""Protected service must not release output across Compose activation drift."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
import unittest

from skeleton.ai.runtime.inference.compose_activation import (
    ActivationBlocked, ActivationPermit, MongoGuardedActivation,
)
from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, ReviewVerdict, TrustedContextSnapshot,
    merkle_root, request_parts,
)


@dataclass(frozen=True)
class Request:
    instructions: str = "policy"
    prompt: str = "status"
    history: tuple = ()
    digest: str = "digest"
    context_digest: str | None = None

    @property
    def rendered_input(self):
        return "system: policy\nuser: status\nassistant:"


class SnapshotAuthority:
    def __init__(self, request):
        self.snapshot = TrustedContextSnapshot(
            merkle_root(request_parts(request)),
            sha256(request.instructions.encode()).hexdigest(),
            1, "tenant", "context",
        )
        self.calls = 0

    async def resolve(self, *, tenant_scope_id, context_id, request_digest):
        self.calls += 1
        if (tenant_scope_id, context_id, request_digest) != ("tenant", "context", "digest"):
            raise ValueError("foreign request")
        return self.snapshot


class Engine:
    model = object()

    def __init__(self):
        self.calls = 0
        self.after_generate = None

    async def generate(self, request, **kwargs):
        self.calls += 1
        if self.after_generate is not None:
            await self.after_generate()
        return type("Result", (), {"text": "must be guarded"})()


class GateHarness:
    """Exact gate instance with deterministic permit checks, no live Mongo."""

    def __init__(self):
        self.gate = object.__new__(MongoGuardedActivation)
        self.calls = 0
        self.revoked = False
        self.permit = ActivationPermit(
            1, "tenant", "owner", "context", 2,
            "a" * 64, "b" * 64, "c" * 64,
        )

        async def assert_active(permit=None):
            self.calls += 1
            if self.revoked or (permit is not None and permit != self.permit):
                raise ActivationBlocked("revoked or stale")
            return self.permit

        self.gate.assert_active = assert_active


class ComposeGuardServiceTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        request = Request()
        authority = SnapshotAuthority(request)
        engine = Engine()
        guarded = GuardedLocalInference(
            engine,
            reviewer=lambda text, digest: ReviewVerdict(True, digest, "reviewer", "pass"),
            tokenize=lambda text: tuple(text.encode()),
            detokenize=lambda ids: bytes(ids).decode(),
        )
        harness = GateHarness()
        service = CanonicalGuardedLocalService(
            guarded, snapshots=authority, activation_gate=harness.gate,
        )
        return request, authority, engine, harness, service

    async def test_activation_checked_before_dispatch_and_delivery(self):
        request, authority, engine, harness, service = self.make()
        answer = await service.generate(
            request, tenant_scope_id="tenant", context_id="context",
        )
        self.assertEqual(answer.result.text, "must be guarded")
        self.assertEqual(engine.calls, 1)
        self.assertEqual(authority.calls, 3)
        self.assertEqual(harness.calls, 4)

    async def test_revoked_before_preflight_denies_without_model_execution(self):
        request, authority, engine, harness, service = self.make()
        harness.revoked = True
        with self.assertRaises(ActivationBlocked):
            await service.generate(
                request, tenant_scope_id="tenant", context_id="context",
            )
        self.assertEqual(engine.calls, 0)
        self.assertEqual(authority.calls, 0)

    async def test_revoked_after_generation_suppresses_result(self):
        request, authority, engine, harness, service = self.make()

        async def revoke():
            harness.revoked = True

        engine.after_generate = revoke
        with self.assertRaises(ActivationBlocked):
            await service.generate(
                request, tenant_scope_id="tenant", context_id="context",
            )
        self.assertEqual(engine.calls, 1)
        self.assertEqual(authority.calls, 3)
        self.assertEqual(harness.calls, 4)

    async def test_revoked_before_dispatch_never_calls_model(self):
        request, authority, engine, harness, service = self.make()
        original = authority.resolve

        async def revoke_on_second_read(**kwargs):
            result = await original(**kwargs)
            if authority.calls == 2:
                harness.revoked = True
            return result

        authority.resolve = revoke_on_second_read
        # The physical dispatch guard runs after its authority revalidation.
        # Revocation between these checks must be detected at postflight at
        # latest; the canonical source guard itself may deny before dispatch.
        with self.assertRaises(ActivationBlocked):
            await service.generate(
                request, tenant_scope_id="tenant", context_id="context",
            )
        self.assertEqual(engine.calls, 0)


if __name__ == "__main__":
    unittest.main()
