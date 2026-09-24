from __future__ import annotations

import json
from pathlib import Path

from skeleton.contracts.ai_execution import ExecutionState


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "machine" / "ai_runtime_schemas.json"


def test_execution_state_matches_machine_schema() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    assert payload["enums"]["ExecutionState"] == [
        item.value for item in ExecutionState
    ]


def test_execution_request_machine_contract_is_resume_stable() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["AIExecutionRequest"]
    fields = record["fields"]

    assert record["owner_plane"] == "orchestration"
    assert fields["operation_id"]["type"] == "OpaqueId"
    assert fields["execution_id"]["type"] == "OpaqueId"
    assert fields["context_policy"]["type"] == "JsonObject"
    assert fields["tool_policy"]["type"] == "JsonObject"
    assert fields["resource_budget"]["type"] == "ResourceBudget"
    assert fields["stop_policy"]["type"] == "JsonObject"
    assert fields["checkpoint_ref"]["nullable"] is True
    assert any(
        "monotonic across resume/retry" in invariant
        for invariant in record["invariants"]
    )


def test_agent_turn_machine_contract_binds_context_and_receipts() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    fields = payload["records"]["AgentTurn"]["fields"]

    assert fields["turn_index"]["type"] == "NonNegativeInt"
    assert fields["phase"]["type"] == "ExecutionState"
    assert fields["context_digest"]["type"] == "Digest256"
    assert fields["tool_receipt_ids"]["type"] == "array<OpaqueId>"
    assert fields["verification_receipt_id"]["nullable"] is True
    assert fields["usage_delta"]["type"] == "JsonObject"


def test_execution_result_machine_contract_binds_terminal_evidence() -> None:
    payload = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    record = payload["records"]["AIExecutionResult"]
    fields = record["fields"]

    assert fields["verification"]["nullable"] is True
    assert fields["provider_receipts"]["type"] == "array<Ref>"
    assert fields["tool_receipts"]["type"] == "array<Ref>"
    assert fields["memory_refs"]["type"] == "array<Ref>"
    assert fields["artifact_refs"]["type"] == "array<Ref>"
    assert fields["usage"]["type"] == "JsonObject"
    assert fields["stream_terminal_event"]["nullable"] is True
    assert any(
        "canonical result commit" in invariant
        for invariant in record["invariants"]
    )
