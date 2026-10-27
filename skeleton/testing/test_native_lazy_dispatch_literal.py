"""Native lazy exports resolve only the pinned implementation module."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import skeleton.ai.runtime.inference as inference


@pytest.mark.parametrize("symbol", ["NativeTransformerModel", "build_native_transformer_adapter"])
def test_native_exports_call_only_literal_trusted_module(symbol: str) -> None:
    marker = object()
    namespace = SimpleNamespace(**{symbol: marker})
    prior = inference.__dict__.get(symbol)
    existed = symbol in inference.__dict__
    try:
        with patch.object(inference, "_inference_import_module", return_value=namespace) as loader:
            assert inference.__getattr__(symbol) is marker
            loader.assert_called_once_with(".native_transformer", inference.__name__)
    finally:
        if existed:
            inference.__dict__[symbol] = prior
        else:
            inference.__dict__.pop(symbol, None)


def test_unregistered_native_export_cannot_trigger_module_load() -> None:
    with patch.object(inference, "_inference_import_module") as loader:
        with pytest.raises(AttributeError):
            inference.__getattr__("skeleton.untrusted.dynamic.module")
        loader.assert_not_called()


def test_dispatch_table_targets_are_exactly_reviewed_native_implementation() -> None:
    assert set(inference._NATIVE_EXPORTS) == {
        "NativeTransformerModel", "build_native_transformer_adapter",
    }
    assert set(inference._NATIVE_EXPORTS.values()) == {".native_transformer"}
