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


def envelope(payload: dict[str, object], constraints: tuple[str, ...] = ()) -> CanonicalEnvelope:
    return CanonicalEnvelope(
        schema_version=1,
        kind="test.contract",
        identity=Identity(repository="Apeloff1/Skeleton", commit_sha="a" * 40),
        evidence=(EvidenceRef(source="repo", digest="b" * 64),),
        constraints=constraints,
        payload=payload,
    )


def test_canonical_bytes_are_independent_of_mapping_insertion_order() -> None:
    left = envelope({"z": 1, "a": {"y": 2, "x": 3}})
    right = envelope({"a": {"x": 3, "y": 2}, "z": 1})
    assert left.canonical_bytes == right.canonical_bytes
    assert left.digest == right.digest


def test_canonical_bytes_sort_and_deduplicate_constraints() -> None:
    left = envelope({"ok": True}, ("beta", "alpha", "beta"))
    right = envelope({"ok": True}, ("alpha", "beta"))
    assert left.canonical_bytes == right.canonical_bytes
    assert left.digest == right.digest


def test_canonical_bytes_use_utf8_not_environment_dependent_ascii_escaping() -> None:
    encoded = canonical_json_bytes({"text": "Ω雪"})
    assert "Ω雪".encode("utf-8") in encoded
    assert b"\\u03a9" not in encoded


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected_before_digest(value: float) -> None:
    candidate = envelope({"value": value})
    with pytest.raises(CanonicalContractError, match="strict canonical JSON"):
        _ = candidate.digest


def test_non_json_payload_values_are_rejected_before_digest() -> None:
    candidate = envelope({"value": object()})
    with pytest.raises(CanonicalContractError, match="strict canonical JSON"):
        _ = candidate.canonical_bytes
