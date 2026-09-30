from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    authority: frozenset[str]
    data: frozenset[str]
    cost: int


def contract(primary: Capability, fallback: Capability) -> bool:
    return (
        fallback.authority <= primary.authority
        and fallback.data <= primary.data
        and fallback.cost <= primary.cost
    )


def test_dependency_fault_contracts_capability():
    primary = Capability(frozenset({"read"}), frozenset({"tenant-data"}), 10)
    fallback = Capability(frozenset({"read"}), frozenset({"tenant-data"}), 6)
    assert contract(primary, fallback)


def test_fallback_cannot_widen_authority_or_data():
    primary = Capability(frozenset({"read"}), frozenset({"tenant-data"}), 10)
    widened = Capability(frozenset({"read", "write"}), frozenset({"tenant-data", "global-data"}), 1)
    assert not contract(primary, widened)


def test_provider_outage_fails_closed():
    primary = Capability(frozenset({"read"}), frozenset({"tenant-data"}), 10)
    unavailable = Capability(frozenset(), frozenset(), 0)
    assert contract(primary, unavailable)
