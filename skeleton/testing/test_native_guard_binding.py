"""Adversarial custody tests for native transformer tokenizer admission."""

from __future__ import annotations

from types import SimpleNamespace
import pytest

from skeleton.ai.runtime.inference.native_guard_binding import (
    build_guarded_native_transformer_adapter,
    native_transformer_guard_components,
)
from skeleton.ai.runtime.inference.native_transformer import NativeTransformerModel
from skeleton.context.pre_delivery_guard import ReviewVerdict
from skeleton.provider_runtime import ProviderPolicyError


class FakeNativeTokenizer:
    def __init__(self):
        self.digest = "3" * 64
        self.unavailable = False

    def assert_unchanged(self):
        if self.unavailable:
            raise RuntimeError("mutated tokenizer")

    def encode_ids(self, text: str):
        self.assert_unchanged()
        return tuple(text.encode("utf-8"))

    def decode_ids(self, tokens):
        self.assert_unchanged()
        return bytes(tokens).decode("utf-8")


def backend():
    """Use an uninitialized typed backend only for custody contract tests."""
    active = object.__new__(NativeTransformerModel)
    tokenizer = FakeNativeTokenizer()
    active.runtime = SimpleNamespace(tokenizer=tokenizer)
    active._model_digest = "1" * 64
    active._runtime_digest = "2" * 64
    active._tokenizer_digest = tokenizer.digest

    def assert_identity():
        if active.runtime.tokenizer is not tokenizer or tokenizer.digest != active._tokenizer_digest:
            raise RuntimeError("model/tokenizer drift")
        tokenizer.assert_unchanged()

    active._assert_identity = assert_identity
    return active, tokenizer


def authorities():
    snapshot = SimpleNamespace(resolve=lambda **kwargs: None)
    reviewer = lambda text, digest: ReviewVerdict(True, digest, "trusted-reviewer", "ok")
    return snapshot, reviewer


def test_native_component_custody_is_tied_to_exact_methods_and_model():
    active, tokenizer = backend()
    snapshot, reviewer = authorities()
    component = native_transformer_guard_components(active, snapshots=snapshot, reviewer=reviewer)
    assert component.verify_native_tokenizer(
        active, component.tokenize, component.detokenize,
    ) is True
    assert component.tokenize is not None
    assert component.detokenize(component.tokenize("exact byte roundtrip")) == "exact byte roundtrip"
    assert component.verify_native_tokenizer(
        object(), component.tokenize, component.detokenize,
    ) is False
    assert component.verify_native_tokenizer(
        active, lambda text: tuple(text.encode()), component.detokenize,
    ) is False
    assert component.verify_native_tokenizer(
        active, component.tokenize, lambda tokens: bytes(tokens).decode(),
    ) is False
    assert component.sampler_support(active, object()) is False
    assert component.projection_attestor(None, "", "") is False


def test_native_component_rechecks_tokenizer_mutation_and_replacement():
    active, tokenizer = backend()
    snapshot, reviewer = authorities()
    component = native_transformer_guard_components(active, snapshots=snapshot, reviewer=reviewer)
    tokenizer.unavailable = True
    assert component.verify_native_tokenizer(
        active, component.tokenize, component.detokenize,
    ) is False
    tokenizer.unavailable = False
    active.runtime.tokenizer = FakeNativeTokenizer()
    assert component.verify_native_tokenizer(
        active, component.tokenize, component.detokenize,
    ) is False
    active.runtime.tokenizer = tokenizer
    tokenizer.digest = "4" * 64
    assert component.verify_native_tokenizer(
        active, component.tokenize, component.detokenize,
    ) is False


def test_native_activation_rejects_invalid_backend_authority_and_identity():
    active, tokenizer = backend()
    snapshot, reviewer = authorities()
    with pytest.raises(ProviderPolicyError, match="exact transformer"):
        native_transformer_guard_components(object(), snapshots=snapshot, reviewer=reviewer)
    with pytest.raises(ProviderPolicyError, match="application-owned"):
        native_transformer_guard_components(active, snapshots=None, reviewer=reviewer)
    with pytest.raises(ProviderPolicyError, match="application-owned"):
        native_transformer_guard_components(active, snapshots=snapshot, reviewer=None)
    tokenizer.digest = "bad"
    with pytest.raises(ProviderPolicyError, match="identity admission"):
        native_transformer_guard_components(active, snapshots=snapshot, reviewer=reviewer)


def test_one_step_native_factory_rejects_caller_downgrade_and_substitution():
    snapshot, reviewer = authorities()
    for options in (
        {"require_guarded_inference": False},
        {"require_guarded_inference": True},
        {"guarded_components": object()},
        {"guarded_components_factory": lambda backend: object()},
    ):
        with pytest.raises(ProviderPolicyError, match="mandatory|cannot be replaced"):
            build_guarded_native_transformer_adapter(
                None, snapshots=snapshot, reviewer=reviewer, **options,
            )


def test_one_step_factory_constructs_exact_native_component_after_backend(monkeypatch):
    from skeleton.ai.runtime.inference import native_transformer as native_module
    active, _ = backend()
    snapshot, reviewer = authorities()

    def fake_adapter(runtime, **kwargs):
        assert runtime == "runtime"
        assert kwargs["require_guarded_inference"] is True
        components = kwargs["guarded_components_factory"](active)
        assert components.verify_native_tokenizer(
            active, components.tokenize, components.detokenize,
        ) is True
        return components

    monkeypatch.setattr(native_module, "build_native_transformer_adapter", fake_adapter)
    result = build_guarded_native_transformer_adapter(
        "runtime", snapshots=snapshot, reviewer=reviewer,
    )
    assert result.verify_native_tokenizer(active, result.tokenize, result.detokenize) is True


def test_native_factory_does_not_start_without_trusted_component_factory():
    from skeleton.ai.runtime.inference.native_transformer import build_native_transformer_adapter
    with pytest.raises(ProviderPolicyError, match="exactly one"):
        build_native_transformer_adapter(None, require_guarded_inference=True)
    with pytest.raises(ProviderPolicyError, match="enforced"):
        build_native_transformer_adapter(None, guarded_components_factory=lambda backend: None)
