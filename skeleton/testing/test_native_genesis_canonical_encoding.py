"""Canonical Genesis encoding must remain identical to the candidate boundary."""
import hashlib

import pytest

from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected
from skeleton.ai.runtime.operational_ai.native_genesis.canonical import encode, source_digest


def test_native_genesis_canonical_encoding_preserves_source_digest():
    records = [{"z": [1, "é"], "a": True}]
    raw = encode(records)
    assert raw == '[{"a":true,"z":[1,"é"]}]'.encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == source_digest(records)


@pytest.mark.parametrize("value", [float("inf"), {1: "invalid"}, {"a": "x" * 65537}])
def test_native_genesis_canonical_encoding_rejects_invalid_values(value):
    with pytest.raises(CandidateRejected):
        encode(value)
