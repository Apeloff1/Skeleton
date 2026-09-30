from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class V1:
    value: str


@dataclass(frozen=True)
class V2:
    value: str
    marker: str = "v2"


def decode_v1(obj: V1) -> V2:
    return V2(obj.value)


def decode_v2(obj: V2) -> V1:
    return V1(obj.value)


def test_mixed_version_round_trip_preserves_value():
    old = V1("payload")
    upgraded = decode_v1(old)
    assert decode_v2(upgraded) == old


def test_upgrade_then_downgrade_is_compatible():
    current = V2("state")
    legacy = decode_v2(current)
    restored = decode_v1(legacy)
    assert restored.value == current.value


def test_rollback_does_not_drop_authoritative_value():
    current = V2("authoritative")
    legacy = decode_v2(current)
    assert legacy.value == "authoritative"
