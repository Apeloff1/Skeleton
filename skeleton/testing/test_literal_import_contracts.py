"""Exact literal-source loading contracts for first-install source qualification.

No name supplied by a caller can create an import path. Every accepted loader
has a static Python string constant that an AST gate can review independently.
"""
from __future__ import annotations

import pytest

from skeleton.ai.runtime.operational_ai.offline_cognition.catalog import FAMILIES
from skeleton.ai.runtime.operational_ai.offline_cognition.core.approved_imports import (
    OPERATIONS, _LOADERS, resolve_module,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,
)
from skeleton.ai.runtime.operational_ai.agent_fabric.assurance import measurements
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import (
    DOMAINS, registry,
)


def _literal(loader) -> str:
    values = [value for value in loader.__code__.co_consts if isinstance(value, str)]
    assert len(values) == 1, "static import must have one exact target"
    return values[0]


def test_1280_cognition_family_operation_targets_are_exact_and_literal():
    expected = {(family, operation) for family in FAMILIES
                for operation in OPERATIONS}
    assert len(FAMILIES) == 64
    assert len(OPERATIONS) == 20
    assert len(_LOADERS) == 1280
    assert set(_LOADERS) == expected
    for (family, operation), loader in _LOADERS.items():
        assert _literal(loader) == (
            "skeleton.ai.runtime.operational_ai.offline_cognition.families."
            + family + "." + operation
        )


@pytest.mark.parametrize("family,operation", [
    ("missing", "source"), ("burst_control", "missing"),
    (None, "source"), ("burst_control", None),
    ([], "source"), ("burst_control", []),
])
def test_cognition_import_rejects_unregistered_names_before_loading(family, operation):
    with pytest.raises(CognitionError):
        resolve_module(family, operation)


def test_cognition_loader_reaches_real_source_implementation():
    source = resolve_module("burst_control", "source")
    assert callable(source.ingest)
    assert callable(source.partition)


def test_measurement_packages_use_explicit_literal_loaders():
    assert set(measurements._DOMAIN_LOADERS) == measurements.DOMAINS
    for domain, loader in measurements._DOMAIN_LOADERS.items():
        assert _literal(loader).endswith(".measurements." + domain)
        group = loader()
        assert set(group._LOADERS) == group.ALLOWED
        for name, implementation in group._LOADERS.items():
            assert _literal(implementation).endswith(
                ".measurements." + domain + "." + name
            )


def test_jeeves_laptop_domain_dispatch_is_closed_and_real():
    assert len(DOMAINS) == 20
    for domain in DOMAINS:
        module = registry(domain)
        assert callable(module.contracts)
        assert callable(module.evaluate)
    with pytest.raises(LaptopGateHold):
        registry("unknown")
