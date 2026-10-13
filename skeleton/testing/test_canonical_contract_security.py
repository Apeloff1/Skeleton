from __future__ import annotations

import math

import pytest

from skeleton.contracts.canonical import (
    CanonicalContractError,
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
    canonical_json_bytes,
)


def _envelope(payload: dict[str, object], constraints: tuple[str, ...] = ()) -> CanonicalEnvelope:
    return CanonicalEnvelope(
        schema_version=1,
        kind="test.contract",
        identity=Identity(repository="Apeloff1/Skeleton", commit_sha="a" * 40),
        evidence=(EvidenceRef(source="repo", digest="b" * 64),),
        constraints=constraints,
        payload=payload,
    )


def test_canonical_bytes_ignore_mapping_insertion_order() -> None:
    left = _envelope({"z": 1, "a": {"y": 2, "x": 3}})
    right = _envelope({"a": {"x": 3, "y": 2}, "z": 1})
    assert left.canonical_bytes == right.canonical_bytes
    assert left.digest == right.digest


def test_canonical_bytes_normalize_constraints() -> None:
    left = _envelope({"ok": True}, ("beta", "alpha", "beta"))
    right = _envelope({"ok": True}, ("alpha", "beta"))
    assert left.canonical_bytes == right.canonical_bytes


def test_canonical_bytes_use_utf8() -> None:
    encoded = canonical_json_bytes({"text": "Ω雪"})
    assert "Ω雪".encode("utf-8") in encoded
    assert b"\\u03a9" not in encoded


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_fail_before_digest(value: float) -> None:
    with pytest.raises(CanonicalContractError, match="non-finite numbers are not canonical JSON"):
        _ = _envelope({"value": value}).digest


def test_non_json_values_fail_before_digest() -> None:
    with pytest.raises(CanonicalContractError, match="strict canonical JSON"):
        _ = _envelope({"value": object()}).canonical_bytes
