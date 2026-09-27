#!/usr/bin/env python3
"""Independent Stage-7 golden-journey closure verifier.

This verifier does not import application runtimes. It binds the machine
masterplan to executable journey surfaces by inspecting source text, required
test coverage, exact dependency declarations, and exact-head evidence identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

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

JOURNEY_SURFACES: dict[str, tuple[str, ...]] = {
    "frontend/scripts/test-operation-stream-session.mjs": (
        "disconnect and reconnect",
        "slow browser recovers",
        "cancel-complete race",
        "browser terminal artifact result linkage survives reconnect",
    ),
    "frontend/scripts/test-conversation-projection.mjs": (
        "refresh/reconnect reconstructs deterministic canonical order",
        "projection cannot outrun canonical thread authority",
    ),
    "frontend/services/operationStreamSession.ts": (
        "class OperationBrowserSession",
        "async replayOnce(",
        "async resync(",
        "async follow(",
        "async cancel(",
    ),
    "backend/tests/test_engine_cross_service_closure.py": (
        "test_http_golden_journey_preserves_provider_tool_verification_lineage",
        "test_cross_service_cancel_fences_late_provider_result",
    ),
    "backend/tests/test_ai_chat_engine_cutover.py": (
        "test_configured_engine_outage_never_falls_back_to_backend_provider",
        "engine_unavailable",
    ),
    "skeleton/testing/test_ai_golden_journeys.py": (
        "retrieval_tool_provider_journey",
        "provider",
        "artifact",
        "outage",
    ),
    "skeleton/testing/test_engine_execution_service.py": (
        "test_expired_persisted_approval_can_be_safely_reauthorized",
        "test_expired_persisted_approval_is_not_replayed_into_resume",
    ),
    "skeleton/testing/test_engine_execution_coordinator.py": (
        "test_coordinator_durable_approval_resumes_effect_once_after_restart",
        "test_coordinator_provider_unavailable_becomes_durable_failure",
    ),
    "backend/tests/test_conversation_governance.py": (
        "test_governed_export_reads_only_conversation_records_for_tenant",
        "test_governed_deletion_removes_message_before_thread_and_acks",
    ),
}

REQUIRED_CLOSURE_EVIDENCE = {
    "browser E2E suite",
    "API trace continuity",
    "artifact/result assertions",
    "degraded-mode assertions",
}


class VerificationError(RuntimeError):
    pass


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
        raise VerificationError(f"{path} must contain a JSON object")
    return payload


def _entry(payload: dict[str, Any], gap: str) -> dict[str, Any] | None:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    for item in entries:
        if isinstance(item, dict) and item.get("gap") == gap:
            return item
    return None


def _verify_surfaces(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in JOURNEY_SURFACES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"golden journey surface is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost golden-journey token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return digests


def _verify_machine_contracts(root: Path, errors: list[str]) -> dict[str, Any]:
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    row = _entry(handoff, "gap-e2e-golden-journeys")
    if row is None:
        errors.append("Stage-7 implementation handoff entry is missing")
        return {}

    dependencies = row.get("depends_on")
    actual = (
        {str(item) for item in dependencies}
        if isinstance(dependencies, list)
        else set()
    )
    if actual != EXPECTED_DEPENDENCIES:
        errors.append(
            "Stage-7 dependency graph mismatch: " + ", ".join(sorted(actual))
        )

    status = str(row.get("implementation_status") or "")
    if status not in {"implemented_pending_closure", "closed"}:
        errors.append("Stage-7 handoff is not implementation-complete")

    construction = _load_json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    stage7 = None
    dependency_status: dict[str, str] = {}
    if isinstance(gaps, list):
        for item in gaps:
            if not isinstance(item, dict):
                continue
            gap_id = str(item.get("id") or "")
            if gap_id == "gap-e2e-golden-journeys":
                stage7 = item
            if gap_id in EXPECTED_DEPENDENCIES:
                dependency_status[gap_id] = str(item.get("status") or "")
    else:
        errors.append("construction gap_register must be a list")

    if stage7 is None:
        errors.append("Stage-7 construction gap is missing")
    else:
        if stage7.get("status") not in {"open", "closed"}:
            errors.append("Stage-7 construction status is invalid")
        evidence = stage7.get("closure_evidence")
        evidence_set = (
            {str(item) for item in evidence}
            if isinstance(evidence, list)
            else set()
        )
        if not REQUIRED_CLOSURE_EVIDENCE.issubset(evidence_set):
            errors.append("Stage-7 closure evidence contract is incomplete")
        if stage7.get("status") == "closed":
            still_open = sorted(
                gap
                for gap in EXPECTED_DEPENDENCIES
                if dependency_status.get(gap) != "closed"
            )
            if still_open:
                errors.append(
                    "closed Stage-7 gap has non-closed dependencies: "
                    + ", ".join(still_open)
                )

    closure = _load_json(root / "machine/ai_closure_evidence.json")
    closure_row = _entry(closure, "gap-e2e-golden-journeys")
    if closure_row is None:
        errors.append("Stage-7 closure evidence entry is missing")
    elif closure_row.get("implementation_state") not in {
        "implemented_pending_closure",
        "closed",
    }:
        errors.append("Stage-7 closure evidence is not implementation-complete")

    row["_verified_dependency_status"] = {
        gap: dependency_status.get(gap, "missing")
        for gap in sorted(EXPECTED_DEPENDENCIES)
    }
    return row


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests = _verify_surfaces(root, errors)
    handoff = _verify_machine_contracts(root, errors)
    return {
        "schema_version": 1,
        "verifier": "independent-golden-journeys-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "valid": not errors,
        "errors": errors,
        "journey_digests": digests,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "handoff_digest": hashlib.sha256(
            json.dumps(
                handoff,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()

    receipt = verify_repository()
    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
