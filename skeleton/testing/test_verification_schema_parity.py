from __future__ import annotations

import json
from pathlib import Path

from skeleton.contracts.verification import (
    ConfidenceBand,
    VerificationLevel,
    VerificationOutcome,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "machine" / "ai_runtime_schemas.json"


def test_verification_enums_match_machine_schema() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))

    assert payload["enums"]["VerificationLevel"] == [
        item.value for item in VerificationLevel
    ]
    assert payload["enums"]["VerificationOutcome"] == [
        item.value for item in VerificationOutcome
    ]
    assert payload["enums"]["ConfidenceBand"] == [
        item.value for item in ConfidenceBand
    ]


def test_verification_request_machine_contract_is_policy_owned() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["VerificationRequest"]
    fields = record["fields"]

    assert record["owner_plane"] == "reasoning-verification"
    assert fields["operation_id"]["type"] == "OpaqueId"
    assert fields["execution_id"]["type"] == "OpaqueId"
    assert fields["turn_id"]["type"] == "OpaqueId"
    assert fields["required_level"]["type"] == "VerificationLevel"
    assert fields["context_snapshot_id"]["type"] == "OpaqueId"
    assert fields["evidence_refs"]["type"] == "array<Ref>"
    assert fields["tool_receipt_refs"]["type"] == "array<Ref>"
    assert fields["deadline"]["nullable"] is True
    assert any(
        "selected by policy rather than model output" in invariant
        for invariant in record["invariants"]
    )


def test_verification_receipt_machine_contract_is_observable_only() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["VerificationReceipt"]
    fields = record["fields"]

    assert record["owner_plane"] == "reasoning-verification"
    assert fields["outcome"]["type"] == "VerificationOutcome"
    assert fields["claim_checks"]["type"] == "array<JsonObject>"
    assert fields["postcondition_checks"]["type"] == "array<JsonObject>"
    assert fields["evidence_refs"]["type"] == "array<Ref>"
    assert fields["repair_directive"]["nullable"] is True
    assert fields["confidence_band"]["type"] == "ConfidenceBand"

    encoded = json.dumps(fields, sort_keys=True).lower()
    assert "chain_of_thought" not in encoded
    assert "reasoning_trace" not in encoded
    assert any(
        "observable checks/evidence" in invariant
        for invariant in record["invariants"]
    )


def test_evidence_reference_machine_contract_is_digest_bound() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["EvidenceReference"]
    fields = record["fields"]

    assert fields["content_digest"]["type"] == "Digest256"
    assert fields["provenance"]["type"] == "JsonObject"
    assert fields["citation_metadata"]["type"] == "JsonObject"
    assert fields["observed_at"]["type"] == "RFC3339"
    assert fields["tenant_id"]["nullable"] is True
