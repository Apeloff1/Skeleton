from __future__ import annotations

import pytest

from skeleton.testing.fixtures import (
    Fixture,
    FixtureContractError,
    FixtureRegistry,
    FixtureVersion,
)


def test_registry_inventory_is_deterministic_and_versioned() -> None:
    left = FixtureRegistry()
    right = FixtureRegistry()
    fixtures = [
        Fixture("zeta", lambda: {"ok": True}, owner="tests", version=FixtureVersion(2, 1, 0)),
        Fixture("alpha", lambda: (1, 2), owner="tests", provenance="synthetic:v1"),
    ]
    for fixture in fixtures:
        left.register(fixture)
    for fixture in reversed(fixtures):
        right.register(fixture)

    assert left.names() == ("alpha", "zeta")
    assert left.manifest() == right.manifest()
    assert left.receipt("zeta").version == "2.1.0"
    assert left.build("alpha") == (1, 2)


@pytest.mark.parametrize(
    "fixture",
    [
        Fixture("net", lambda: None, allows_network=True),
        Fixture("clock", lambda: None, allows_wall_clock=True),
        Fixture("random", lambda: None, allows_randomness=True),
    ],
)
def test_registry_rejects_nonhermetic_authority_by_default(fixture: Fixture) -> None:
    registry = FixtureRegistry()
    with pytest.raises(FixtureContractError, match="non-hermetic"):
        registry.register(fixture)


def test_explicit_nonhermetic_registry_preserves_receipt_warning() -> None:
    registry = FixtureRegistry(require_hermetic=False)
    registry.register(Fixture("networked", lambda: 1, allows_network=True))
    receipt = registry.receipt("networked")
    assert receipt.hermetic is False
    assert registry.manifest()["fixtures"][0]["hermetic"] is False


def test_duplicate_name_fails_closed_instead_of_replacing_fixture() -> None:
    registry = FixtureRegistry()
    registry.register(Fixture("stable", lambda: "first"))
    with pytest.raises(FixtureContractError, match="duplicate"):
        registry.register(Fixture("stable", lambda: "second"))
    assert registry.build("stable") == "first"


def test_fixture_identity_changes_with_provenance_version_or_authority() -> None:
    base = Fixture("sample", lambda: None, owner="team", provenance="corpus:a")
    changed_version = Fixture(
        "sample", lambda: None, owner="team", provenance="corpus:a",
        version=FixtureVersion(1, 0, 1),
    )
    changed_provenance = Fixture("sample", lambda: None, owner="team", provenance="corpus:b")
    changed_authority = Fixture(
        "sample", lambda: None, owner="team", provenance="corpus:a", allows_network=True
    )
    assert len({base.identity, changed_version.identity, changed_provenance.identity, changed_authority.identity}) == 4


def test_invalid_metadata_and_versions_fail_closed() -> None:
    with pytest.raises(FixtureContractError):
        Fixture("", lambda: None)
    with pytest.raises(FixtureContractError):
        FixtureVersion(-1, 0, 0)
