#!/usr/bin/env python3
"""Independent Stage-7 golden-journey closure verifier.

This verifier does not import the engine, browser session runtime, governance
runtime, or golden test suite. It verifies source-level journey coverage,
canonical mirror parity, machine-contract dependency integrity, and exact-head
evidence binding independently of the implementation under test.
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

GAP_ID = "gap-e2e-golden-journeys"

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

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/testing/test_ai_golden_journeys.py": (
        "test_stage7_prompt_only_journey_preserves_operation_context_and_terminal_lineage",
        "test_stage7_multi_turn_journey_preserves_canonical_history_and_trace",
        "test_stage7_retrieval_tool_provider_journey_binds_durable_lineage",
        "test_stage7_approval_write_survives_restart_and_executes_effect_once",
        "test_stage7_expired_approval_can_be_renewed_without_widening_identity",
        "test_stage7_artifact_action_is_receipted_once",
        "test_stage7_provider_outage_is_durable_degraded_result_without_tool_io",
        "test_stage7_cancel_race_fences_late_provider_success",
        "test_stage7_restart_ambiguity_never_replays_uncommitted_tool_effect",
        "test_stage7_governance_export_delete_spans_artifact_and_retrieval_planes",
    ),
    "frontend/services/operationStreamSession.ts": (
        "class OperationBrowserSession",
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
    ),
    "backend/tests/test_ai_chat_engine_cutover.py": (
        "test_configured_engine_outage_never_falls_back_to_backend_provider",
        "engine_unavailable",
    ),
    "skeleton/api/engine_service.py": (
        "active approval cannot be widened or renewed",
        "renewed approval must extend an expired approval window",
        "def active_approval_refs(",
    ),
}

MIRROR_PAIRS = (
    (
        "skeleton/api/engine_service.py",
        "skeleton/ai/runtime/api/engine_service.py",
    ),
)


class VerificationError(RuntimeError):
    """Independent Stage-7 verification could not be completed."""


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_text(path))
    except json.JSONDecodeError as exc:
        raise VerificationError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative, tokens in BOUNDARIES.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"Stage-7 boundary is missing: {relative}")
            continue
        source = _text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{relative} lost Stage-7 token: {token}")
        digests[relative] = hashlib.sha256(
            source.encode("utf-8")
        ).hexdigest()
    return digests


def _mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file() or not mirror.is_file():
            errors.append(
                f"Stage-7 mirror pair is missing: {source_rel} -> {mirror_rel}"
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


def _find(entries: object, gap_id: str) -> dict[str, Any] | None:
    if not isinstance(entries, list):
        return None
    return next(
        (
            item
            for item in entries
            if isinstance(item, dict) and item.get("gap") == gap_id
        ),
        None,
    )


def _machine(root: Path, errors: list[str]) -> dict[str, Any]:
    handoff = _json(root / "machine/ai_implementation_handoff.json")
    entry = _find(handoff.get("entries"), GAP_ID)
    if entry is None:
        errors.append("Stage-7 implementation handoff entry is missing")
        return {}

    dependencies = entry.get("depends_on")
    actual = (
        {str(item) for item in dependencies}
        if isinstance(dependencies, list)
        else set()
    )
    if actual != EXPECTED_DEPENDENCIES:
        errors.append(
            "Stage-7 dependency graph mismatch: "
            + ", ".join(sorted(actual))
        )

    if entry.get("implementation_status") not in {
        "implementation-complete",
        "implemented_pending_closure",
        "closed",
    }:
        errors.append("Stage-7 handoff is not implementation-complete")

    construction = _json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    gap_status = "missing"
    dependency_status: dict[str, str] = {}
    if isinstance(gaps, list):
        for item in gaps:
            if not isinstance(item, dict):
                continue
            gap_id = str(item.get("id") or "")
            status = str(item.get("status") or "")
            if gap_id == GAP_ID:
                gap_status = status
            if gap_id in EXPECTED_DEPENDENCIES:
                dependency_status[gap_id] = status
    else:
        errors.append("construction gap_register must be a list")

    missing = sorted(EXPECTED_DEPENDENCIES - set(dependency_status))
    if missing:
        errors.append(
            "Stage-7 dependency statuses missing: " + ", ".join(missing)
        )

    blueprint = construction.get("golden_journey_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("golden_journey_blueprint is missing")
    else:
        if blueprint.get("gap") != GAP_ID:
            errors.append("golden journey blueprint gap binding is invalid")
        if blueprint.get("status") not in {
            "implementation-complete-pending-closure",
            "implemented-pending-closure",
            "closed",
        }:
            errors.append(
                "golden journey blueprint is not implementation-complete"
            )
        journey_ids = {
            str(item.get("id"))
            for item in blueprint.get("journeys", [])
            if isinstance(item, dict)
        }
        required_journeys = {
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
        missing_journeys = sorted(required_journeys - journey_ids)
        if missing_journeys:
            errors.append(
                "golden journey blueprint lost mandatory journeys: "
                + ", ".join(missing_journeys)
            )

    if gap_status == "closed":
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
    elif gap_status != "open":
        errors.append("Stage-7 construction status is invalid")

    return {
        "gap_status": gap_status,
        "implementation_status": entry.get("implementation_status"),
        "dependency_status": {
            key: dependency_status.get(key, "missing")
            for key in sorted(EXPECTED_DEPENDENCIES)
        },
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests = _boundaries(root, errors)
    mirrors = _mirrors(root, errors)
    machine = _machine(root, errors)
    machine_digest = hashlib.sha256(
        json.dumps(
            machine,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "verifier": "independent-stage7-golden-journeys-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "boundary_digests": digests,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "machine": machine,
        "machine_digest": machine_digest,
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
        print(f"independent-stage7-golden: rejected: {exc}", file=sys.stderr)
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
        print("independent-stage7-golden: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print("  - " + error, file=sys.stderr)
        return 1

    print(
        "independent-stage7-golden: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
