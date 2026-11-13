"""Formal implementation binding verification must not execute imports."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from skeleton.ai.runtime.contracts.formal_methods import (
    FormalMethodError,
    ImplementationBinding,
)

_MODULE = "skeleton.ai.runtime.contracts.formal_methods"


def test_loaded_trusted_symbol_resolves_without_import_side_effects() -> None:
    binding = ImplementationBinding.from_object(
        contract_id="formal-binding-1",
        obj=ImplementationBinding,
    )
    assert binding.module_path == _MODULE
    with patch("importlib.import_module", side_effect=AssertionError("untrusted import executed")) as loader:
        assert binding.resolve() is ImplementationBinding
        binding.verify()
    loader.assert_not_called()


def test_unloaded_module_is_denied_without_importing_it() -> None:
    path = "skeleton.testing.__untrusted_binding_not_loaded__"
    assert path not in sys.modules
    binding = ImplementationBinding(
        contract_id="formal-binding-2",
        module_path=path,
        symbol="Untrusted",
        source_sha256="a" * 64,
    )
    with patch("importlib.import_module", side_effect=AssertionError("unexpected import")) as loader:
        with pytest.raises(FormalMethodError, match="is not loaded"):
            binding.resolve()
    loader.assert_not_called()


def test_loaded_module_missing_symbol_still_fails_closed() -> None:
    binding = ImplementationBinding(
        contract_id="formal-binding-3",
        module_path=_MODULE,
        symbol="NotAnAdmittedSymbol",
        source_sha256="b" * 64,
    )
    with pytest.raises(FormalMethodError, match="implementation symbol"):
        binding.resolve()


def test_loaded_module_with_stale_source_digest_is_rejected() -> None:
    binding = ImplementationBinding(
        contract_id="formal-binding-4",
        module_path=_MODULE,
        symbol="ImplementationBinding",
        source_sha256="0" * 64,
    )
    with pytest.raises(FormalMethodError, match="implementation binding drift"):
        binding.verify()
