"""Exact-backend factory custody; fixtures are not a physical model run."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from skeleton.ai.runtime.inference.guarded_composition import (
    ProtectedLocalComponentFactory, is_protected_component_source, resolve_protected_components,
)
from skeleton.ai.runtime.inference.native_guard_binding import (
    NativeGuardPins, make_pinned_native_guard_factory,
    native_transformer_guard_components,
)
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient
from skeleton.ai.runtime.inference.reviewer_custody import ReviewerTrustAnchor
from skeleton.testing.test_native_guard_binding import authorities, backend
from skeleton.provider_runtime import ProviderPolicyError
from skeleton.api.server import ServerState


def test_factory_constructs_separate_tokenizer_bindings_after_loading():
    snapshot, reviewer = authorities()
    factory = ProtectedLocalComponentFactory(snapshot, lambda model, owner:
        native_transformer_guard_components(model, snapshots=owner, reviewer=reviewer))
    first, _ = backend()
    second, _ = backend()
    first_components = resolve_protected_components(factory, first)
    second_components = resolve_protected_components(factory, second)
    assert first_components.snapshots is snapshot
    assert second_components.snapshots is snapshot
    assert first_components.verify_native_tokenizer(first, first_components.tokenize,
                                                   first_components.detokenize)
    assert not first_components.verify_native_tokenizer(second, first_components.tokenize,
                                                       first_components.detokenize)
    assert second_components.verify_native_tokenizer(second, second_components.tokenize,
                                                    second_components.detokenize)


def test_factory_rebinding_only_uses_trusted_startup_reader():
    snapshot, reviewer = authorities()
    actual, _ = authorities()
    model, _ = backend()
    source = ProtectedLocalComponentFactory(snapshot, lambda active, owner:
        native_transformer_guard_components(active, snapshots=owner, reviewer=reviewer))
    assert replace(source, snapshots=actual).for_backend(model).snapshots is actual
    invalid = ProtectedLocalComponentFactory(actual, lambda active, owner:
        native_transformer_guard_components(active, snapshots=snapshot, reviewer=reviewer))
    with pytest.raises(ProviderPolicyError, match="changed snapshot"):
        invalid.for_backend(model)


def test_factory_failure_redacts_and_never_returns_arbitrary_objects():
    snapshot, _ = authorities()
    def fail(*args):
        raise RuntimeError("private source authority")
    with pytest.raises(ProviderPolicyError) as caught:
        ProtectedLocalComponentFactory(snapshot, fail).for_backend(object())
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None
    with pytest.raises(ProviderPolicyError):
        ProtectedLocalComponentFactory(snapshot, lambda *args: True).for_backend(object())
    assert not is_protected_component_source(lambda *args: True)
    assert not is_protected_component_source(None)


def test_server_can_bind_factory_once_before_startup():
    snapshot, reviewer = authorities()
    factory = ProtectedLocalComponentFactory(snapshot, lambda model, owner:
        native_transformer_guard_components(model, snapshots=owner, reviewer=reviewer))
    state = ServerState()
    state.configure_engine_local_guard(factory)
    assert state._engine_local_guard_components is factory
    with pytest.raises(RuntimeError, match="rebound"):
        state.configure_engine_local_guard(factory)
    started = ServerState()
    started.engine_execution_service = object()
    with pytest.raises(RuntimeError, match="before startup"):
        started.configure_engine_local_guard(factory)
    with pytest.raises(TypeError):
        ServerState().configure_engine_local_guard(object())


def signed_reviewer_fixture():
    # No network or private reviewer service is fabricated by this fixture.
    reviewer = object.__new__(SignedReviewerClient)
    reviewer._anchor = ReviewerTrustAnchor("reviewer", "independent", b"r" * 32)
    return reviewer


def test_independent_pins_reject_foreign_model_and_reviewer_rotation():
    snapshot, _ = authorities()
    reviewer = signed_reviewer_fixture()
    model, tokenizer = backend()
    model.model_id = "native-model"
    pins = NativeGuardPins(model.model_id, model.model_digest, model.runtime_digest, tokenizer.digest)
    factory = make_pinned_native_guard_factory(snapshots=snapshot, reviewer=reviewer, pins=(pins,))
    components = factory.for_backend(model)
    assert components.verify_native_tokenizer(model, components.tokenize, components.detokenize)
    tokenizer.unavailable = True
    assert not components.verify_native_tokenizer(model, components.tokenize, components.detokenize)
    tokenizer.unavailable = False
    reviewer._anchor = ReviewerTrustAnchor("reviewer", "replacement", b"s" * 32)
    assert not components.verify_native_tokenizer(model, components.tokenize, components.detokenize)
    with pytest.raises(ProviderPolicyError):
        factory.for_backend(model)


def test_pin_inventory_requires_exact_supported_backend_and_no_fallback():
    snapshot, _ = authorities()
    reviewer = signed_reviewer_fixture()
    model, tokenizer = backend()
    model.model_id = "native-model"
    pins = NativeGuardPins(model.model_id, "f" * 64, model.runtime_digest, tokenizer.digest)
    for inventory in ((), (pins, pins), [pins]):
        with pytest.raises(ProviderPolicyError):
            make_pinned_native_guard_factory(snapshots=snapshot, reviewer=reviewer, pins=inventory)
    source = make_pinned_native_guard_factory(snapshots=snapshot, reviewer=reviewer, pins=(pins,))
    with pytest.raises(ProviderPolicyError):
        source.for_backend(model)
    with pytest.raises(ProviderPolicyError):
        source.for_backend(SimpleNamespace(model_id=model.model_id, runtime=model.runtime))
    with pytest.raises(ProviderPolicyError):
        make_pinned_native_guard_factory(snapshots=snapshot, reviewer=lambda *_: True, pins=(pins,))


def test_checkpoint_backend_uses_its_own_admitted_native_tokenizer():
    snapshot, _ = authorities()
    reviewer = signed_reviewer_fixture()
    _, tokenizer = backend()
    model = object.__new__(NativeRuntimeLocalModel)
    model.model_id = "checkpoint"
    model.runtime = SimpleNamespace(tokenizer=tokenizer)
    model._model_digest = "1" * 64
    model._runtime_digest = "2" * 64
    model._tokenizer_digest = tokenizer.digest
    # The production class checks real runtime identity; this fixture isolates
    # the component-factory contract without claiming that model has loaded.
    from unittest.mock import patch
    with patch.object(NativeRuntimeLocalModel, "assert_identity", lambda self: None):
        pin = NativeGuardPins(model.model_id, model.model_digest, model.runtime_digest, tokenizer.digest)
        source = make_pinned_native_guard_factory(snapshots=snapshot, reviewer=reviewer, pins=(pin,))
        components = source.for_backend(model)
        assert components.tokenize("native") == tuple(b"native")
        assert components.verify_native_tokenizer(model, components.tokenize, components.detokenize)
        model.runtime.tokenizer = backend()[1]
        assert not components.verify_native_tokenizer(model, components.tokenize, components.detokenize)
