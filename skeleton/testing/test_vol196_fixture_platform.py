from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.fixture_platform import FixtureRegistry
from skeleton.ai.runtime.deferred.operations_experience import Fixture


A = "a" * 64
B = "b" * 64


def test_manifest_order_and_digest_are_deterministic() -> None:
    first = FixtureRegistry((Fixture("z", B, True), Fixture("a", A, True))).manifest()
    second = FixtureRegistry((Fixture("a", A, True), Fixture("z", B, True))).manifest()
    assert first == second
    assert first.fixture_ids == ("a", "z")


def test_registry_rejects_nonhermetic_or_side_effecting_fixture() -> None:
    with pytest.raises(ValueError):
        FixtureRegistry((Fixture("remote", A, False, True),))
    with pytest.raises(ValueError):
        FixtureRegistry((Fixture("local", A, False, False),))


def test_require_fails_closed_on_unknown_or_digest_drift() -> None:
    registry = FixtureRegistry((Fixture("state", A, True),))
    assert registry.require("state", expected_digest=A).digest == A
    with pytest.raises(KeyError):
        registry.require("missing", expected_digest=A)
    with pytest.raises(ValueError):
        registry.require("state", expected_digest=B)


def test_duplicate_fixture_identity_is_rejected() -> None:
    with pytest.raises(ValueError):
        FixtureRegistry((Fixture("same", A, True), Fixture("same", B, True)))
