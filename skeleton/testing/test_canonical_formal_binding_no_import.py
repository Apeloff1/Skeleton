"""Formal binding verification cannot import modules from serialized metadata."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from skeleton.contracts.formal_methods import (
    FormalMethodError as CanonicalError,
    ImplementationBinding as CanonicalBinding,
)
from skeleton.ai.runtime.contracts.formal_methods import (
    FormalMethodError as RuntimeError,
    ImplementationBinding as RuntimeBinding,
)


@pytest.mark.parametrize(
    ("binding_type", "error_type"),
    [(CanonicalBinding, CanonicalError), (RuntimeBinding, RuntimeError)],
)
def test_trusted_loaded_implementation_verifies_without_dynamic_import(binding_type, error_type):
    binding = binding_type.from_object(contract_id="FM.NOIMPORT.001", obj=binding_type)
    with patch("importlib.import_module", side_effect=AssertionError("dynamic import")) as loader:
        assert binding.resolve() is binding_type
        binding.verify()
    loader.assert_not_called()


@pytest.mark.parametrize(
    ("binding_type", "error_type"),
    [(CanonicalBinding, CanonicalError), (RuntimeBinding, RuntimeError)],
)
def test_unloaded_implementation_is_denied_without_import(binding_type, error_type):
    untrusted = "skeleton.testing.not_loaded_untrusted_formal_binding"
    assert untrusted not in sys.modules
    binding = binding_type(
        contract_id="FM.NOIMPORT.002",
        module_path=untrusted,
        symbol="UnreviewedImplementation",
        source_sha256="0" * 64,
    )
    with patch("importlib.import_module", side_effect=AssertionError("dynamic import")) as loader:
        with pytest.raises(error_type, match="is not loaded"):
            binding.resolve()
    loader.assert_not_called()


@pytest.mark.parametrize(
    ("binding_type", "error_type"),
    [(CanonicalBinding, CanonicalError), (RuntimeBinding, RuntimeError)],
)
def test_stale_source_hash_remains_fatal(binding_type, error_type):
    binding = binding_type(
        contract_id="FM.NOIMPORT.003",
        module_path=binding_type.__module__,
        symbol="ImplementationBinding",
        source_sha256="0" * 64,
    )
    with pytest.raises(error_type, match="binding drift"):
        binding.verify()
