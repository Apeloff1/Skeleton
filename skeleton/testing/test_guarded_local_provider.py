"""Exact production local provider route: guarded admission and no unsafe fallback."""

from __future__ import annotations

import asyncio
from hashlib import sha256

import pytest

from skeleton.ai.runtime.inference.guarded_service import CanonicalGuardedLocalService
from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine, LocalInferenceRequest, LocalModelAdapter, ReferenceNGramModel,
)
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, ReviewVerdict, TrustedContextSnapshot, merkle_root, request_parts,
)
from skeleton.context.sealed_sandwich import (
    SealedContextIntegrityError, SealedContextReplayError,
)
from skeleton.provider_runtime import ProviderPolicyError, ProviderRequest


class Authority:
    def __init__(self, *, root: str, instruction_digest: str):
        self.snapshot = TrustedContextSnapshot(root, instruction_digest, 1, "tenant", "00000000-0000-4000-8000-000000000001")
        self.calls = 0
        self.mutate = False

    async def resolve(self, *, tenant_scope_id, context_id, request_digest):
        self.calls += 1
        assert tenant_scope_id == "tenant"
        assert context_id == "00000000-0000-4000-8000-000000000001"
        assert len(request_digest) == 64
        if self.mutate and self.calls == 2:
            s = self.snapshot
            return TrustedContextSnapshot(
                s.root, s.policy_sha256, s.snapshot_version + 1, s.tenant_id, s.context_id
            )
        return self.snapshot


def fixture():
    model = ReferenceNGramModel.train(["hello trusted answer"] * 6, order=2)
    engine = LocalInferenceEngine(model, cache_size=2, require_guarded_context=True)
    local = LocalInferenceRequest(prompt="hello", instructions="policy", max_output_tokens=4)
    root = merkle_root(request_parts(local))
    authority = Authority(root=root, instruction_digest=sha256(b"policy").hexdigest())
    guard = GuardedLocalInference(
        engine,
        reviewer=lambda text, digest: ReviewVerdict(True, digest, "trusted-reviewer", "pass"),
        tokenize=lambda value: tuple(value.encode("utf-8")),
        detokenize=lambda tokens: bytes(tokens).decode("utf-8"),
    )
    service = CanonicalGuardedLocalService(guard, snapshots=authority)
    adapter = LocalModelAdapter(engine, guarded_service=service, require_guarded_inference=True)
    request = ProviderRequest(
        instructions="policy", prompt="hello", max_output_tokens=4,
        tenant_id="tenant", context_id="00000000-0000-4000-8000-000000000001",
        context_digest=root,
        context_source_snapshot=((
            "00000000-0000-4000-8000-000000000002",
            sha256(b"policy and hello authoritative segment").hexdigest(),
        ),),
        context_compiler_version="verified-test-compiler-v1",
    )
    return engine, authority, service, adapter, request


def test_guard_required_adapter_requires_exact_engine_and_guard():
    engine, _, service, _, _ = fixture()
    other_engine = LocalInferenceEngine(
        ReferenceNGramModel.train(["different local weights"], order=2)
    )
    with pytest.raises(ProviderPolicyError):
        LocalModelAdapter(engine, require_guarded_inference=True)
    with pytest.raises(ProviderPolicyError):
        LocalModelAdapter(other_engine, guarded_service=service, require_guarded_inference=True)
    with pytest.raises(ProviderPolicyError):
        LocalModelAdapter(engine, guarded_service=service)
    with pytest.raises(ProviderPolicyError):
        LocalModelAdapter(engine, require_guarded_inference="enabled")


def test_protected_provider_uses_guard_for_result_and_cache_hit():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        one = await adapter.generate(request)
        two = await adapter.generate(request)
        assert one.provider == "local" and two.provider == "local"
        assert authority.calls == 4
        assert adapter.status()["guard_required"] is True
    asyncio.run(scenario())


def test_protected_provider_denies_missing_tenant_and_context_before_authority_read():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        from dataclasses import replace
        for kwargs in ({"tenant_id": None}, {"context_id": None}):
            with pytest.raises(ProviderPolicyError):
                await adapter.generate(replace(request, **kwargs))
        assert authority.calls == 0
    asyncio.run(scenario())


def test_protected_provider_suppresses_output_if_canonical_snapshot_changes():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        authority.mutate = True
        with pytest.raises(SealedContextReplayError):
            await adapter.generate(request)
        assert authority.calls == 2
    asyncio.run(scenario())


def test_protected_provider_rejects_mismatched_merkle_without_model_response():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        from dataclasses import replace
        bad = replace(request, context_digest="a" * 64)
        with pytest.raises(SealedContextIntegrityError):
            await adapter.generate(bad)
        assert authority.calls == 1
    asyncio.run(scenario())


def test_provider_rejects_rewritten_delivery_receipt():
    async def scenario():
        from dataclasses import replace
        _, authority, service, adapter, request = fixture()
        genuine = service.generate

        async def tamper(*args, **kwargs):
            result = await genuine(*args, **kwargs)
            return replace(result, receipt=replace(
                result.receipt, response_sha256="f" * 64,
            ))

        service.generate = tamper
        with pytest.raises(ProviderPolicyError, match="receipt"):
            await adapter.generate(request)
        assert authority.calls == 2
    asyncio.run(scenario())


def test_provider_rejects_unsolicited_tool_calls():
    async def scenario():
        from dataclasses import replace
        from skeleton.ai.runtime.inference.local import LocalToolCall
        _, _, service, adapter, request = fixture()
        genuine = service.generate

        async def tamper(*args, **kwargs):
            verified = await genuine(*args, **kwargs)
            modified = replace(
                verified.result, finish_reason="tool_calls",
                tool_calls=(LocalToolCall("call-1", "dangerous-tool", {}),),
            )
            return replace(verified, result=modified)

        service.generate = tamper
        with pytest.raises(ProviderPolicyError, match="tool calls"):
            await adapter.generate(request)
    asyncio.run(scenario())


def test_provider_rejects_unsolicited_structured_output():
    async def scenario():
        from dataclasses import replace
        _, _, service, adapter, request = fixture()
        genuine = service.generate

        async def tamper(*args, **kwargs):
            verified = await genuine(*args, **kwargs)
            return replace(
                verified,
                result=replace(verified.result, structured_output={"unverified": True}),
            )

        service.generate = tamper
        with pytest.raises(ProviderPolicyError, match="unsolicited structured"):
            await adapter.generate(request)
    asyncio.run(scenario())


def test_direct_engine_cache_and_preparation_cannot_bypass_protected_mode():
    async def scenario():
        engine, authority, _, adapter, request = fixture()
        from skeleton.ai.runtime.inference.local import LocalInferenceRequest
        native = LocalInferenceRequest(
            prompt=request.prompt, instructions=request.instructions,
            max_output_tokens=4, context_digest=request.context_digest,
        )
        from skeleton.provider_runtime import ProviderPolicyError
        for call in (
            lambda: engine.prepare_input(native, tenant_scope_id="tenant"),
        ):
            with pytest.raises(ProviderPolicyError):
                call()
        with pytest.raises(ProviderPolicyError):
            await engine.generate(native, tenant_scope_id="tenant")
        with pytest.raises(ProviderPolicyError):
            await engine.generate_many((native,), tenant_scope_id="tenant")
        # Provider entrypoint may still run, including a subsequent cached run,
        # but only while the guarded preflight and postflight are both valid.
        await adapter.generate(request)
        await adapter.generate(request)
        assert authority.calls == 4
        with pytest.raises(ProviderPolicyError):
            await engine.generate(native, tenant_scope_id="tenant")
    asyncio.run(scenario())


def test_guard_permit_rejects_inherited_child_task():
    async def scenario():
        engine, _, service, _, request = fixture()
        from skeleton.ai.runtime.inference.local import LocalInferenceRequest
        from skeleton.provider_runtime import ProviderPolicyError
        from hashlib import sha256
        native = LocalInferenceRequest(
            prompt=request.prompt, instructions=request.instructions,
            max_output_tokens=4, context_digest=request.context_digest,
        )
        # Even code carrying the right verifier object cannot hand a permit
        # to a child task by relying on ContextVar inheritance.
        with engine._verified_guard_scope(
            native, context_root=request.context_digest,
            token_echo=sha256(native.rendered_input.encode()).hexdigest(),
            reviewer_id="independent-reviewer", guard_identity=service.guard,
        ):
            child = asyncio.create_task(engine.generate(native, tenant_scope_id="tenant"))
            with pytest.raises(ProviderPolicyError, match="child task"):
                await child
        with pytest.raises(ProviderPolicyError, match="verified context"):
            await engine.generate(native, tenant_scope_id="tenant")
    asyncio.run(scenario())


def test_guards_from_different_composition_roots_cannot_rebind_engine():
    engine, _, _, _, request = fixture()
    from skeleton.context.pre_delivery_guard import GuardedLocalInference, ReviewVerdict
    other = GuardedLocalInference(
        engine, reviewer=lambda t, d: ReviewVerdict(True, d, "other", "ok"),
        tokenize=lambda t: list(t.encode()),
        detokenize=lambda v: bytes(v).decode(),
    )
    with pytest.raises(ProviderPolicyError, match="cannot be replaced"):
        engine._bind_verified_guard(other)


def test_guarded_provider_stream_buffers_until_postflight_authority_recheck():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        authority.mutate = True
        emitted = []
        with pytest.raises(SealedContextReplayError):
            async for delta in adapter.stream(request):
                emitted.append(delta)
        # Streaming must never send the first byte of an unverified answer.
        assert emitted == []
        assert authority.calls == 2

    asyncio.run(scenario())


def test_guarded_provider_stream_yields_only_after_verified_generation():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        chunks = [delta async for delta in adapter.stream(request)]
        assert chunks
        assert authority.calls == 2
        assert all(chunk is not None for chunk in chunks)

    asyncio.run(scenario())


def test_guarded_provider_stream_rejects_forged_delivery_receipt_without_deltas():
    async def scenario():
        from dataclasses import replace
        _, _, service, adapter, request = fixture()
        original = service.generate

        async def forge(*args, **kwargs):
            generation = await original(*args, **kwargs)
            return replace(generation, receipt=replace(
                generation.receipt, response_sha256="0" * 64,
            ))

        service.generate = forge
        chunks = []
        with pytest.raises(ProviderPolicyError, match="receipt"):
            async for delta in adapter.stream(request):
                chunks.append(delta)
        assert chunks == []

    asyncio.run(scenario())


def test_protected_stream_does_not_emit_before_guard_postflight():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        authority.mutate = True
        observed = []
        with pytest.raises(SealedContextReplayError):
            async for delta in adapter.stream(request):
                observed.append(delta)
        assert observed == []
        assert authority.calls == 2
    asyncio.run(scenario())


def test_protected_stream_only_emits_verified_buffered_result():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        events = [event async for event in adapter.stream(request)]
        assert authority.calls == 2
        assert [item.sequence for item in events] == list(range(len(events)))
        assert len(events) >= 3
        assert events[0].text is not None
        assert events[-1].finish_reason is not None
    asyncio.run(scenario())


def test_forged_guarded_receipt_blocks_stream_first_byte():
    async def scenario():
        from dataclasses import replace
        _, authority, service, adapter, request = fixture()
        original = service.generate

        async def forged(*args, **kwargs):
            result = await original(*args, **kwargs)
            return replace(
                result,
                receipt=replace(result.receipt, response_sha256="e" * 64),
            )

        service.generate = forged
        emitted = []
        with pytest.raises(ProviderPolicyError, match="receipt"):
            async for event in adapter.stream(request):
                emitted.append(event)
        assert emitted == []
        assert authority.calls == 2
    asyncio.run(scenario())


def test_provider_requires_token_sequence_commitment_before_delivery():
    async def scenario():
        from dataclasses import replace

        _, authority, service, adapter, request = fixture()
        real_generate = service.generate

        async def remove_token_proof(*args, **kwargs):
            verified = await real_generate(*args, **kwargs)
            return replace(
                verified,
                receipt=replace(verified.receipt, token_sequence_sha256=None),
            )

        service.generate = remove_token_proof
        with pytest.raises(ProviderPolicyError, match="receipt"):
            await adapter.generate(request)
        assert authority.calls == 2

        emitted = []
        with pytest.raises(ProviderPolicyError, match="receipt"):
            async for delta in adapter.stream(request):
                emitted.append(delta)
        assert emitted == []
        assert authority.calls == 4

    asyncio.run(scenario())


def test_protected_stream_emits_only_after_complete_verified_generation():
    """Provider-neutral streaming cannot expose unreviewed partial tokens."""
    from skeleton.provider_runtime import ProviderDeltaKind

    async def scenario():
        _, authority, _, adapter, request = fixture()
        deltas = [delta async for delta in adapter.stream(request)]
        assert authority.calls == 2
        assert deltas
        assert deltas[0].kind == ProviderDeltaKind.TEXT
        assert deltas[0].text is not None
        assert deltas[-1].kind == ProviderDeltaKind.FINAL

    asyncio.run(scenario())


def test_protected_stream_revocation_yields_no_deltas():
    async def scenario():
        _, authority, _, adapter, request = fixture()
        authority.mutate = True
        observed = []
        with pytest.raises(SealedContextReplayError):
            async for delta in adapter.stream(request):
                observed.append(delta)
        assert observed == []
        assert authority.calls == 2

    asyncio.run(scenario())


def test_protected_stream_forged_receipt_never_yields_a_partial_delta():
    from dataclasses import replace

    async def scenario():
        _, authority, service, adapter, request = fixture()
        genuine = service.generate

        async def forge(*args, **kwargs):
            generation = await genuine(*args, **kwargs)
            return replace(generation, receipt=replace(
                generation.receipt, response_sha256="0" * 64,
            ))

        service.generate = forge
        observed = []
        with pytest.raises(ProviderPolicyError, match="receipt"):
            async for delta in adapter.stream(request):
                observed.append(delta)
        assert observed == []
        assert authority.calls == 2

    asyncio.run(scenario())
