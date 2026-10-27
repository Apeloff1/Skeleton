"""Verified startup composition for protected local-model deployments."""

from __future__ import annotations

import asyncio
from hashlib import sha256

import pytest

from skeleton.ai.runtime.inference.guarded_composition import (
    ProtectedLocalComponents, compose_protected_local_adapter,
)
from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine, LocalInferenceRequest, ReferenceNGramModel,
)
from skeleton.context.pre_delivery_guard import (
    ReviewVerdict, TrustedContextSnapshot, merkle_root, request_parts,
)
from skeleton.provider_runtime import ProviderPolicyError, ProviderRequest


_CONTEXT_ID = "00000000-0000-4000-8000-000000000001"
_SEGMENT_ID = "00000000-0000-4000-8000-000000000002"


class TrustedReader:
    def __init__(self, request):
        self.expected = TrustedContextSnapshot(
            merkle_root(request_parts(request)),
            sha256(request.instructions.encode("utf-8")).hexdigest(),
            1, "tenant", _CONTEXT_ID,
        )
        self.reads = 0

    async def resolve(self, *, tenant_scope_id, context_id, request_digest):
        assert tenant_scope_id == "tenant" and context_id == _CONTEXT_ID
        self.reads += 1
        return self.expected


def secure_components(reader, *, attestor=None):
    return ProtectedLocalComponents(
        snapshots=reader,
        reviewer=lambda text, digest: ReviewVerdict(True, digest, "separate-reviewer", "pass"),
        tokenize=lambda text: tuple(text.encode()),
        detokenize=lambda tokens: bytes(tokens).decode(),
        verify_native_tokenizer=(attestor if attestor is not None else
                                 lambda model, encode, decode: True),
        sampler_support=lambda model, contract: False,
        projection_attestor=lambda request, rendered, root: False,
    )


def protected_fixture():
    local = LocalInferenceRequest(
        prompt="hello", instructions="policy", max_output_tokens=4,
    )
    root = merkle_root(request_parts(local))
    local = LocalInferenceRequest(
        prompt="hello", instructions="policy", max_output_tokens=4,
        context_digest=root,
    )
    engine = LocalInferenceEngine(
        ReferenceNGramModel.train(["hello local answer"] * 6, order=2),
        require_guarded_context=True, cache_size=2,
    )
    authority = TrustedReader(local)
    request = ProviderRequest(
        prompt="hello", instructions="policy", max_output_tokens=4,
        context_id=_CONTEXT_ID, context_digest=root, tenant_id="tenant",
        context_source_snapshot=((_SEGMENT_ID, sha256(b"verified-segment").hexdigest()),),
        context_compiler_version="canonical-compiler-v1",
    )
    return engine, authority, request


def test_protected_composition_rejects_legacy_engine_and_untrusted_activation():
    engine, reader, _ = protected_fixture()
    legacy = LocalInferenceEngine(
        ReferenceNGramModel.train(["legacy"], order=2),
        require_guarded_context=False,
    )
    with pytest.raises(ProviderPolicyError, match="engine-level"):
        compose_protected_local_adapter(legacy, components=secure_components(reader))
    with pytest.raises(ProviderPolicyError, match="dependencies"):
        compose_protected_local_adapter(engine, components=None)
    with pytest.raises(ProviderPolicyError, match="identity"):
        compose_protected_local_adapter(
            engine, components=secure_components(reader, attestor=lambda *args: False),
        )


def test_identity_callback_errors_deny_without_registering_a_guard():
    engine, reader, _ = protected_fixture()

    def broken(*args):
        raise RuntimeError("native tokenizer unavailable")

    with pytest.raises(ProviderPolicyError, match="unavailable"):
        compose_protected_local_adapter(engine, components=secure_components(reader, attestor=broken))
    assert engine._verified_guard_owner is None


def test_protected_composition_executes_twice_with_per_call_authority():
    async def scenario():
        engine, reader, request = protected_fixture()
        adapter = compose_protected_local_adapter(engine, components=secure_components(reader))
        assert adapter.require_guarded_inference is True
        first = await adapter.generate(request)
        second = await adapter.generate(request)
        assert first.provider == "local" and second.provider == "local"
        assert reader.reads == 4
        with pytest.raises(ProviderPolicyError):
            await engine.generate(LocalInferenceRequest(prompt="untrusted"))
    asyncio.run(scenario())


def test_protected_component_contract_rejects_missing_dependencies():
    engine, reader, _ = protected_fixture()
    with pytest.raises(ProviderPolicyError, match="verify_native_tokenizer"):
        ProtectedLocalComponents(
            snapshots=reader,
            reviewer=lambda text, digest: ReviewVerdict(True, digest, "id", "pass"),
            tokenize=lambda text: tuple(text.encode()),
            detokenize=lambda tokens: bytes(tokens).decode(),
            verify_native_tokenizer=None,
            sampler_support=lambda model, contract: False,
            projection_attestor=lambda request, text, root: False,
        )


def test_gguf_factory_rejects_unprovisioned_protected_mode_before_filesystem_access():
    from skeleton.ai.runtime.inference.llama_cpp import build_llama_cpp_adapter, LlamaCppRuntimeError
    with pytest.raises(LlamaCppRuntimeError, match="trusted components"):
        build_llama_cpp_adapter(None, require_guarded_inference=True)
    with pytest.raises(LlamaCppRuntimeError, match="enforced local mode"):
        build_llama_cpp_adapter(None, guarded_components=object())


def test_native_transformer_factory_rejects_unprovisioned_guard():
    from skeleton.ai.runtime.inference.native_transformer import build_native_transformer_adapter
    with pytest.raises(ProviderPolicyError, match="trusted components"):
        build_native_transformer_adapter(None, require_guarded_inference=True)
    with pytest.raises(ProviderPolicyError, match="enforced transformer mode"):
        build_native_transformer_adapter(None, guarded_components=object())
