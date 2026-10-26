"""Inference receipts must hash every admissible field without lossy coercion."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.inference.provider_bridge import provider_payload_digest
from skeleton.inference.session import InferenceContractError


@pytest.mark.parametrize("payload", [
    {"1": "reviewed", 1: "unreviewed"},
    {True: "reviewed", "True": "unreviewed"},
    {None: "reviewed", "None": "unreviewed"},
    {1: "integer-only-key"},
])
def test_nonstring_mapping_keys_cannot_collide_in_receipt_digest(payload):
    with pytest.raises(InferenceContractError, match="mapping keys must be strings"):
        provider_payload_digest(payload)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_values_are_denied_with_typed_contract_error(invalid):
    with pytest.raises(InferenceContractError, match="nonfinite number"):
        provider_payload_digest({"metric": [{"observed": invalid}]})


def test_hash_is_insertion_order_independent_without_dropping_fields():
    first = {"beta": {"name": "second", "tags": [3, 2, 1]}, "alpha": True}
    second = {"alpha": True, "beta": {"tags": [3, 2, 1], "name": "second"}}
    digest = provider_payload_digest(first)
    assert digest == provider_payload_digest(second)
    assert len(digest) == 64


def test_differing_string_key_values_cannot_share_digest():
    left = {"1": "one", "2": "two"}
    right = {"1": "two", "2": "one"}
    assert provider_payload_digest(left) != provider_payload_digest(right)


def test_dataclass_instance_supported_but_class_object_is_not():
    @dataclass(frozen=True)
    class Claim:
        name: str
        quantity: int

    assert len(provider_payload_digest(Claim(name="verified", quantity=3))) == 64
    with pytest.raises(InferenceContractError, match="requires dataclass instances"):
        provider_payload_digest(Claim)


def test_nested_unsupported_object_is_denied_not_stringified():
    with pytest.raises(InferenceContractError, match="not canonically serializable"):
        provider_payload_digest({"untrusted": [object()]})
