from __future__ import annotations

import uuid

import pytest

from skeleton.foundation.identifier import (
    Identifier,
    IdentifierCodec,
    IdentifierKind,
    deterministic_identifier,
)


def test_round_trip_is_exact_and_versioned() -> None:
    identifier = Identifier(IdentifierKind.OPERATION, "abc-123")
    encoded = IdentifierCodec.encode(identifier)
    assert encoded == "id1:operation:abc-123"
    assert IdentifierCodec.parse(encoded) == identifier


def test_generated_identifiers_are_opaque_lowercase_values() -> None:
    identifier = IdentifierCodec.new(IdentifierKind.EVIDENCE)
    assert identifier.kind is IdentifierKind.EVIDENCE
    assert len(identifier.value) == 32
    assert identifier.value == identifier.value.lower()
    assert IdentifierCodec.parse(str(identifier)) == identifier


def test_deterministic_identifier_replays_from_immutable_name() -> None:
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    left = deterministic_identifier(IdentifierKind.ARTIFACT, namespace, "sha256:immutable-input")
    right = deterministic_identifier(IdentifierKind.ARTIFACT, namespace, "sha256:immutable-input")
    other = deterministic_identifier(IdentifierKind.ARTIFACT, namespace, "sha256:other")
    assert left == right
    assert left != other


@pytest.mark.parametrize(
    "raw",
    [
        "ID1:operation:abc",
        "id1:Operation:abc",
        " id1:operation:abc",
        "id1:operation:abc ",
        "id1:operation:ABC",
        "id1:unknown:abc",
        "id1:operation:abc:def",
        "id2:operation:abc",
        "id1:operation:",
        "id1:operation:tenant/role/admin",
    ],
)
def test_ambiguous_or_authority_shaped_forms_fail_closed(raw: str) -> None:
    with pytest.raises(ValueError):
        IdentifierCodec.parse(raw)


def test_unicode_compatibility_alias_fails_closed() -> None:
    with pytest.raises(ValueError):
        IdentifierCodec.parse("ｉｄ１:operation:abc")


def test_display_or_authority_metadata_cannot_be_encoded_as_value() -> None:
    for value in ("Alice Smith", "tenant:admin", "role=owner", "../admin", "user@example.com"):
        with pytest.raises(ValueError):
            Identifier(IdentifierKind.AGENT, value)


def test_noncanonical_deterministic_name_fails_closed() -> None:
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    with pytest.raises(ValueError):
        deterministic_identifier(IdentifierKind.RECEIPT, namespace, "Ａ")
