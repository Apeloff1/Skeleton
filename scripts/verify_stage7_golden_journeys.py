#!/usr/bin/env python3
"""Independent Stage-7 golden-journey closure verifier.

This verifier does not import product runtime modules. It inspects source and
machine contracts directly so exact-head closure evidence cannot be satisfied
by the implementation under test merely returning a successful result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/testing/test_ai_golden_journeys.py": (
        "test_stage7_prompt_only_journey_preserves_operation_context_and_terminal_lineage",
        "test_stage7_multi_turn_journey_preserves_canonical_history_and_trace",
        "test_stage7_retrieval_tool_provider_journey_binds_durable_lineage",
        "test_stage7_approval_write_survives_restart_and_executes_effect_once",
        "test_stage7_expired_approval_can_be_renewed_without_widening_identity",
        "test_stage7_artifact_action_is_receipted_once",
        "test_stage7_governance_export_delete_spans_artifact_and_retrieval_planes",
        "test_stage7_provider_outage_is_durable_degraded_result_without_tool_io",
        "test_stage7_cancel_race_fences_late_provider_success",
        "test_stage7_restart_ambiguity_never_replays_uncommitted_tool_effect",
    ),
    "backend/tests/test_engine_cross_service_closure.py": (
        "test_cross_service_golden_journey_preserves_receipt_lineage",
        "test_cross_service_cancel_fences_late_provider_result",
    ),
    "backend/tests/test_ai_chat_engine_cutover.py": (
        "test_configured_chat_routes_through_engine_and_commits_engine_lineage",
        "test_configured_engine_outage_never_falls_back_to_backend_provider",
    ),
    "frontend/services/operationStreamSession.ts": (
        "export class OperationBrowserSession",
        "async replayOnce(",
        "async resync(",
        "async resume(",
        "async follow(",
        "async cancel(",
    ),
    "frontend/scripts/test-operation-stream-session.mjs": (
        "browser disconnect and reconnect resumes from persisted accepted cursor",
        "slow browser recovers from compacted replay gap through authoritative floor",
        "cancel-complete race exposes exactly one canonical terminal outcome per session",
        "terminal authoritative resync snapshot reconciles canonical output before fencing",
        "browser terminal artifact result linkage survives reconnect",
    ),
    "backend/tests/test_engine_live_process_boundary.py": (
        "test_engine_client_crosses_real_tcp_process_boundary",
        "test_engine_state_survives_real_process_restart",
    ),
    "skeleton/frontier/operation_stream_store_mongo.py": (
        "class MongoOperationEventStore",
        "def validate_transaction_capability(",
        "Mongo stream authority requires transaction-capable deployment",
    ),
    "skeleton/testing/test_operation_stream_store_mongo.py": (
        "test_mongo_stream_transaction_preflight_executes_real_transactional_read",
        "test_mongo_stream_transaction_preflight_rejects_standalone_topology",
        "test_mongo_stream_transaction_preflight_rejects_client_without_sessions",
    ),
    "backend/tests/test_operation_stream_mongo_stage7.py": (
        "test_stage7_mongo_shared_authority_survives_transient_update_failure",
        "configureFailPoint",
        "\"errorCode\": 112",
        "TransientTransactionError",
    ),
    "backend/tests/test_operation_stream_mongo_integration.py": (
        "test_mongo_shared_authority_replays_across_workers_and_compacts_by_ack",
        "test_mongo_cancel_complete_race_projects_exactly_one_terminal_event",
    ),
    "skeleton/testing/test_engine_execution_service.py": (
        "test_expired_persisted_approval_can_be_safely_reauthorized",
        "test_expired_persisted_approval_is_not_replayed_into_resume",
    ),
    "skeleton/api/engine_service.py": (
        "active approval cannot be widened or renewed",
        "renewed approval must extend an expired approval window",
        "def approve_tool_call(",
        "def active_approval_refs(",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/api/engine_service.py",
        "skeleton/ai/runtime/api/engine_service.py",
    ),
    (
        "skeleton/frontier/operation_stream_store_mongo.py",
        "skeleton/ai/runtime/frontier/operation_stream_store_mongo.py",
    ),
    (
        "skeleton/persistence/operation_store_mongo.py",
        "skeleton/ai/runtime/persistence/operation_store_mongo.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-state-authority-convergence",
    "gap-governance-registry",
    "gap-cost-admission",
    "gap-provider-surface-convergence",
    "gap-conversation-state-authority",
    "gap-memory-durable-authority",
    "gap-tool-runtime-convergence",
    "gap-context-compiler-convergence",
    "gap-provider-interaction-protocol",
    "gap-verification-evidence-contract",
    "gap-cognitive-execution-loop",
    "gap-engine-application-execution-boundary",
    "gap-streaming-protocol",
}


class VerificationError(RuntimeError):
    """Independent Stage-7 verification failed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _find_entry(
    payload: dict[str, Any],
    key: str,
    value: str,
) -> dict[str, Any] | None:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    for item in entries:
        if isinstance(item, dict) and item.get(key) == value:
            return item
    return None


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"Stage-7 boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost Stage-7 token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return digests


def _verify_mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file() or not mirror.is_file():
            errors.append(
                f"Stage-7 mirror pair missing: {source_rel} -> {mirror_rel}"
            )
            continue
        source_bytes = source.read_bytes()
        mirror_bytes = mirror.read_bytes()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        mirror_digest = hashlib.sha256(mirror_bytes).hexdigest()
        rows.append(
            {
                "source": source_rel,
                "mirror": mirror_rel,
                "source_digest": source_digest,
                "mirror_digest": mirror_digest,
            }
        )
        if source_bytes != mirror_bytes:
            errors.append(
                f"canonical AI mirror drift: {source_rel} != {mirror_rel}"
            )
    return rows


def _verify_machine_contracts(root: Path, errors: list[str]) -> dict[str, Any]:
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    entry = _find_entry(handoff, "gap", "gap-e2e-golden-journeys")
    if entry is None:
        errors.append("Stage-7 handoff entry is missing")
        return {}

    dependencies = entry.get("depends_on")
    if not isinstance(dependencies, list):
        errors.append("Stage-7 depends_on must be a list")
        dependencies = []
    actual_dependencies = {str(item) for item in dependencies}
    if actual_dependencies != EXPECTED_DEPENDENCIES:
        errors.append(
            "Stage-7 dependency graph mismatch: "
            + ", ".join(sorted(actual_dependencies))
        )

    if entry.get("implementation_status") not in {
        "implementation-complete",
        "closed",
    }:
        errors.append("Stage-7 handoff is not implementation-complete")

    evidence = entry.get("current_evidence")
    evidence_text = "\n".join(str(item) for item in evidence or [])
    for phrase in (
        "prompt-only",
        "multi-turn",
        "approval-write",
        "approval renewal",
        "governance",
        "engine outage",
        "browser session",
    ):
        if phrase not in evidence_text:
            errors.append(f"Stage-7 handoff evidence lost required phrase: {phrase}")

    construction = _load_json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    dependency_status: dict[str, str] = {}
    stage7_status = "missing"
    if not isinstance(gaps, list):
        errors.append("construction gap_register must be a list")
    else:
        for item in gaps:
            if not isinstance(item, dict):
                continue
            gap_id = str(item.get("id") or "")
            status = str(item.get("status") or "")
            if gap_id == "gap-e2e-golden-journeys":
                stage7_status = status
            if gap_id in EXPECTED_DEPENDENCIES:
                dependency_status[gap_id] = status

    missing = sorted(EXPECTED_DEPENDENCIES - set(dependency_status))
    if missing:
        errors.append(
            "Stage-7 dependency statuses missing: " + ", ".join(missing)
        )

    blueprint = construction.get("golden_journey_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("golden_journey_blueprint is missing")
    else:
        if blueprint.get("gap") != "gap-e2e-golden-journeys":
            errors.append("golden journey blueprint gap binding is invalid")
        if blueprint.get("status") not in {
            "implemented-pending-closure",
            "complete",
        }:
            errors.append(
                "golden journey blueprint is not implemented-pending-closure"
            )
        journeys = blueprint.get("journeys")
        ids = {
            str(item.get("id"))
            for item in journeys or []
            if isinstance(item, dict)
        }
        expected_journeys = {
            "prompt-only",
            "multi-turn",
            "retrieval-grounded",
            "read-tool",
            "write-tool-with-approval",
            "artifact",
            "cancel",
            "reconnect",
            "provider-outage",
            "engine-outage",
            "governance-delete-export",
        }
        missing_journeys = sorted(expected_journeys - ids)
        if missing_journeys:
            errors.append(
                "golden journey blueprint missing journeys: "
                + ", ".join(missing_journeys)
            )

    if stage7_status == "closed":
        open_dependencies = sorted(
            gap_id
            for gap_id in EXPECTED_DEPENDENCIES
            if dependency_status.get(gap_id) != "closed"
        )
        if open_dependencies:
            errors.append(
                "closed Stage-7 gap has non-closed dependencies: "
                + ", ".join(open_dependencies)
            )
        if not isinstance(blueprint, dict) or blueprint.get("status") != "complete":
            errors.append("closed Stage-7 gap requires complete blueprint")
        if entry.get("implementation_status") != "closed":
            errors.append("closed Stage-7 gap requires closed handoff")
    elif stage7_status != "open":
        errors.append("Stage-7 construction status is invalid")

    entry["_verified_dependency_status"] = {
        gap_id: dependency_status.get(gap_id, "missing")
        for gap_id in sorted(EXPECTED_DEPENDENCIES)
    }
    entry["_verified_stage7_status"] = stage7_status
    return entry


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundary_digests = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)
    handoff = _verify_machine_contracts(root, errors)
    handoff_digest = hashlib.sha256(
        json.dumps(
            handoff,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-stage7-golden-journeys-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "dependency_status": dict(
            handoff.get("_verified_dependency_status") or {}
        ),
        "stage7_status": handoff.get("_verified_stage7_status"),
        "handoff_digest": handoff_digest,
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"independent-stage7-golden-journeys: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-stage7-golden-journeys: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-stage7-golden-journeys: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
