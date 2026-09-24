from __future__ import annotations

import json
from pathlib import Path

from skeleton.provider_contract import FinishReason, ProviderDeltaKind


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "machine" / "ai_runtime_schemas.json"


def test_provider_protocol_enums_match_machine_schema() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))

    assert payload["enums"]["FinishReason"] == [item.value for item in FinishReason]
    assert payload["enums"]["ProviderDeltaKind"] == [
        item.value for item in ProviderDeltaKind
    ]


def test_provider_delta_machine_contract_matches_runtime_surface() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["ProviderDelta"]

    assert record["schema_version"] == 1
    assert record["owner_plane"] == "model-provider"
    assert tuple(record["fields"]) == (
        "sequence",
        "kind",
        "response_id",
        "text",
        "structured_fragment",
        "tool_call",
        "usage",
        "finish_reason",
        "emitted_at",
    )
    assert record["fields"]["kind"]["type"] == "ProviderDeltaKind"
    assert record["fields"]["tool_call"]["type"] == "ProviderToolCall"
    assert record["fields"]["usage"]["type"] == "ProviderUsage"
    assert record["fields"]["finish_reason"]["type"] == "FinishReason"
    assert any(
        "no durable stream authority" in invariant
        for invariant in record["invariants"]
    )


def test_provider_request_response_schema_is_provider_native_free() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))

    request = payload["records"]["ProviderRequest"]
    response = payload["records"]["ProviderResponse"]
    field_names = tuple(request["fields"]) + tuple(response["fields"])

    assert all("sdk" not in name.lower() for name in field_names)
    assert all("credential" not in name.lower() for name in field_names)
    assert "provider-native SDK objects are not fields" in response["invariants"]


def test_provider_request_machine_contract_carries_immutable_context_identity() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    fields = payload["records"]["ProviderRequest"]["fields"]

    assert fields["operation_id"]["type"] == "OpaqueId"
    assert fields["execution_id"]["type"] == "OpaqueId"
    assert fields["turn_id"]["type"] == "OpaqueId"
    assert fields["context_id"]["type"] == "OpaqueId"
    assert fields["context_digest"]["type"] == "Digest256"
    assert fields["context_source_snapshot"]["type"] == "SourceSnapshot"
    assert fields["context_compiler_version"]["type"] == "string"
    assert fields["specific_tool_id"] == {
        "type": "OpaqueId",
        "nullable": True,
    }

    invariants = payload["records"]["ProviderRequest"]["invariants"]
    assert any(
        "immutable ContextEnvelope" in invariant
        for invariant in invariants
    )
    assert any(
        "provider-native SDK objects" in invariant
        for invariant in invariants
    )


def test_provider_response_machine_contract_only_echoes_context_identity() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["ProviderResponse"]
    fields = record["fields"]

    assert fields["context_id"] == {
        "type": "OpaqueId",
        "nullable": True,
    }
    assert fields["context_digest"] == {
        "type": "Digest256",
        "nullable": True,
    }
    assert fields["context_source_snapshot"]["type"] == "SourceSnapshot"
    assert fields["context_compiler_version"] == {
        "type": "string",
        "nullable": True,
        "min_length": 1,
        "max_length": 64,
    }
    assert fields["request_id"]["nullable"] is True
    assert fields["response_id"]["nullable"] is True

    assert any(
        "echo the admitted ProviderRequest" in invariant
        for invariant in record["invariants"]
    )


def test_source_snapshot_machine_type_preserves_ordered_pairs() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    snapshot = payload["scalar_types"]["SourceSnapshot"]

    assert snapshot["type"] == "array"
    assert snapshot["max_items"] == 4096
    assert snapshot["items"]["type"] == "array"
    assert snapshot["items"]["min_items"] == 2
    assert snapshot["items"]["max_items"] == 2
    assert snapshot["items"]["items"]["type"] == "string"

    assert (
        payload["records"]["ContextEnvelope"]["fields"]["source_snapshot"]["type"]
        == "SourceSnapshot"
    )


def test_source_snapshot_machine_type_is_ordered_pairs() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    snapshot = payload["scalar_types"]["SourceSnapshot"]

    assert snapshot["type"] == "array"
    assert snapshot["max_items"] == 4096
    pair = snapshot["items"]
    assert pair["type"] == "array"
    assert pair["min_items"] == pair["max_items"] == 2
    assert pair["items"]["type"] == "string"

    assert payload["records"]["ContextEnvelope"]["fields"]["source_snapshot"] == {
        "type": "SourceSnapshot"
    }
    assert payload["records"]["ProviderRequest"]["fields"][
        "context_source_snapshot"
    ] == {"type": "SourceSnapshot"}
    assert payload["records"]["ProviderResponse"]["fields"][
        "context_source_snapshot"
    ] == {"type": "SourceSnapshot"}
