from __future__ import annotations

import math

import pytest

from skeleton.contracts.canonical import (
    CanonicalContractError,
    CanonicalEnvelope,
    EvidenceRef,
    Identity,
)


def envelope(payload: dict[str, object]) -> CanonicalEnvelope:
    return CanonicalEnvelope(
        schema_version=1,
        kind="test.contract",
        identity=Identity(repository="Apeloff1/Skeleton", commit_sha="a" * 40),
        evidence=(EvidenceRef(source="test", digest="b" * 64),),
        constraints=("z", "a", "a"),
        payload=payload,
    )


def test_digest_is_independent_of_object_insertion_order() -> None:
    left = envelope({"b": 2, "a": {"y": 2, "x": 1}})
    right = envelope({"a": {"x": 1, "y": 2}, "b": 2})
    assert left.digest == right.digest
    assert left.canonical_payload()["constraints"] == ["a", "z"]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CanonicalContractError, match="non-finite"):
        envelope({"value": value}).digest


@pytest.mark.parametrize(
    "payload",
    [
        {"tuple": (1, 2)},
        {"set": {1, 2}},
        {1: "non-string-key"},
    ],
)
def test_non_json_payload_types_are_rejected(payload: dict[object, object]) -> None:
    with pytest.raises(CanonicalContractError):
        envelope(payload).digest  # type: ignore[arg-type]


def test_payload_byte_budget_uses_canonical_utf8_bytes() -> None:
    oversized = "ø" * 30_000
    with pytest.raises(CanonicalContractError, match="byte budget"):
        envelope({"value": oversized}).canonical_payload()
