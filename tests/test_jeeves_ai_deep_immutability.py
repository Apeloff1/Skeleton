"""Regression coverage for deep immutability of Jeeves assurance payloads."""
import pytest

from skeleton.jeeves.ai.contracts import ContractRecord
from skeleton.jeeves.ai.evaluation import EvalRecord
from skeleton.jeeves.ai.orchestration import OrchestrRecord


@pytest.mark.parametrize("constructor", (ContractRecord, EvalRecord, OrchestrRecord))
def test_assurance_payload_is_deeply_immutable(constructor):
    record = constructor(
        "immutable",
        payload={
            "nested": {"mode": "read", "deeper": {"enabled": True}},
            "sequence": [{"step": 1}, ["a", "b"]],
        },
    )
    digest = record.digest

    with pytest.raises(TypeError):
        record.payload["nested"]["mode"] = "write"
    with pytest.raises(TypeError):
        record.payload["nested"]["deeper"]["enabled"] = False
    with pytest.raises(TypeError):
        record.payload["sequence"][0]["step"] = 2
    with pytest.raises(TypeError):
        record.payload["sequence"][1][0] = "changed"

    assert record.digest == digest
    assert record.payload["nested"]["mode"] == "read"
    assert record.payload["sequence"][0]["step"] == 1


@pytest.mark.parametrize("constructor", (ContractRecord, EvalRecord, OrchestrRecord))
def test_deep_freeze_preserves_canonical_digest_semantics(constructor):
    left = constructor(
        "stable",
        payload={"nested": {"b": [2, 3], "a": 1}},
    )
    right = constructor(
        "stable",
        payload={"nested": {"a": 1, "b": [2, 3]}},
    )

    assert left.digest == right.digest
