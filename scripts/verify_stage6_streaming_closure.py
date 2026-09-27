#!/usr/bin/env python3
"""Independent Stage-6 streaming/realtime closure verifier.

The verifier intentionally does not import the streaming runtime. It inspects
source contracts, browser-session behavior, canonical AI-tree mirror parity,
and the declared closure dependency graph directly from repository bytes.
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
    "skeleton/contracts/operation.py": (
        "class OperationEnvelope",
        "class OperationState",
        "TERMINAL_OPERATION_STATES",
        "def transition(",
    ),
    "skeleton/frontier/operation_stream.py": (
        "class StreamEvent",
        "class ReplayCursor",
        "class OperationEventLog",
        "StreamReplayGapError",
        "StreamBackpressureError",
        "StreamTerminalError",
        "TERMINAL_EVENT_TYPES",
        "def compact_through(",
    ),
    "skeleton/frontier/operation_stream_store.py": (
        "class SQLiteOperationEventStore",
        "class StreamConsumerCheckpoint",
        "class StreamWorkerLease",
        "acquire_worker_lease",
        "renew_worker_lease",
        "release_worker_lease",
        "acknowledged_through",
        "compacted_through",
    ),
    "skeleton/persistence/operation_store_mongo.py": (
        "class MongoOperationStore",
        "pending_outbox",
        "expected_version",
        "find_one_and_update",
    ),
    "skeleton/frontier/operation_stream_store_mongo.py": (
        "class MongoOperationEventStore",
        "validate_transaction_capability",
        "acquire_worker_lease",
        "renew_worker_lease",
        "release_worker_lease",
        "transaction-capable deployment",
    ),
    "backend/core/operation_stream_transport.py": (
        "class OperationStateStore",
        "class OperationEventStore",
        "class OperationStreamTransport",
        "transport_from_env",
        "CODEDOCK_OPERATION_AUTHORITY_BACKEND",
        "acknowledge_and_compact",
        "resync",
    ),
    "backend/routes/operation_stream.py": (
        "OperationAckRequest",
        "operation_event_replay",
        "operation_event_resync",
        "acknowledge_operation_events",
        "stream.resync_required",
    ),
    "frontend/services/operationStreamReducer.ts": (
        "reduceOperationEvent",
        "reduceOperationReplay",
        "failOperationResync",
        "operationCursorStorageKey",
        "duplicate_event_id_conflict",
        "sequence_gap",
        "terminalResultRef",
    ),
    "frontend/services/operationStreamSession.ts": (
        "export class OperationBrowserSession",
        "async replayOnce(",
        "async resync(",
        "async resume(",
        "async follow(",
        "async cancel(",
        "cursor_ack_failed",
    ),
    "frontend/scripts/test-operation-stream-session.mjs": (
        "browser disconnect and reconnect resumes from persisted accepted cursor",
        "slow browser recovers from compacted replay gap through authoritative floor",
        "cancel-complete race exposes exactly one canonical terminal outcome per session",
        "terminal authoritative resync snapshot reconciles canonical output before fencing",
        "browser terminal artifact result linkage survives reconnect",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/contracts/operation.py",
        "skeleton/ai/runtime/contracts/operation.py",
    ),
    (
        "skeleton/frontier/operation_stream.py",
        "skeleton/ai/runtime/frontier/operation_stream.py",
    ),
    (
        "skeleton/frontier/operation_stream_store.py",
        "skeleton/ai/runtime/frontier/operation_stream_store.py",
    ),
    (
        "skeleton/persistence/operation_store_mongo.py",
        "skeleton/ai/runtime/persistence/operation_store_mongo.py",
    ),
    (
        "skeleton/frontier/operation_stream_store_mongo.py",
        "skeleton/ai/runtime/frontier/operation_stream_store_mongo.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-cognitive-execution-loop",
    "gap-engine-application-execution-boundary",
    "gap-state-authority-convergence",
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


def _entry(payload: dict[str, Any], gap_id: str) -> dict[str, Any] | None:
    entries = payload.get("entries")
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


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"Stage-6 boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost Stage-6 token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return digests


def _verify_mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file() or not mirror.is_file():
            errors.append(
                f"Stage-6 mirror pair missing: {source_rel} -> {mirror_rel}"
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
    gap_id = "gap-streaming-protocol"
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    item = _entry(handoff, gap_id)
    if item is None:
        errors.append("Stage-6 implementation handoff is missing")
        return {}

    deps = item.get("depends_on")
    actual = set(str(value) for value in deps) if isinstance(deps, list) else set()
    if actual != EXPECTED_DEPENDENCIES:
        errors.append(
            "Stage-6 dependency graph mismatch: "
            + ", ".join(sorted(actual))
        )

    if item.get("implementation_status") not in {
        "implemented_pending_closure",
        "implementation-complete",
        "closed",
    }:
        errors.append("Stage-6 handoff implementation status is invalid")

    gate = str(item.get("closure_gate") or "")
    for phrase in ("resume", "duplicating side effects", "terminal state"):
        if phrase not in gate:
            errors.append("Stage-6 closure gate lost invariant phrase: " + phrase)

    construction = _load_json(root / "machine/ai_app_construction.json")
    gaps = construction.get("gap_register")
    gap_status = "missing"
    dependency_status: dict[str, str] = {}
    if not isinstance(gaps, list):
        errors.append("construction gap_register must be a list")
    else:
        for row in gaps:
            if not isinstance(row, dict):
                continue
            current = str(row.get("id") or "")
            status = str(row.get("status") or "")
            if current == gap_id:
                gap_status = status
            if current in EXPECTED_DEPENDENCIES:
                dependency_status[current] = status

    missing = sorted(EXPECTED_DEPENDENCIES - set(dependency_status))
    if missing:
        errors.append(
            "Stage-6 dependency statuses missing: " + ", ".join(missing)
        )

    blueprint = construction.get("realtime_delivery_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("realtime_delivery_blueprint is missing")
    else:
        if blueprint.get("gap") != gap_id:
            errors.append("realtime delivery blueprint gap binding is invalid")
        if blueprint.get("status") not in {
            "implemented-pending-closure",
            "implemented",
            "complete",
        }:
            errors.append("realtime delivery blueprint status is invalid")
        tests = blueprint.get("tests")
        joined = "\n".join(str(value) for value in tests or [])
        for phrase in (
            "disconnect/reconnect replay",
            "slow-client bounded queue",
            "cancel/complete race",
            "multi-worker projection lease fencing/takeover",
            "browser-session disconnect/reconnect persisted cursor journey",
        ):
            if phrase not in joined:
                errors.append(
                    "realtime delivery blueprint lost journey: " + phrase
                )

    if gap_status == "closed":
        open_dependencies = sorted(
            dep
            for dep in EXPECTED_DEPENDENCIES
            if dependency_status.get(dep) != "closed"
        )
        if open_dependencies:
            errors.append(
                "closed Stage-6 gap has non-closed dependencies: "
                + ", ".join(open_dependencies)
            )
        if not isinstance(blueprint, dict) or blueprint.get("status") not in {
            "implemented",
            "complete",
        }:
            errors.append(
                "closed Stage-6 gap requires implemented/complete blueprint"
            )
    elif gap_status != "open":
        errors.append("Stage-6 construction status is invalid")

    closure = _load_json(root / "machine/ai_closure_evidence.json")
    closure_entry = _entry(closure, gap_id)
    if closure_entry is None:
        errors.append("Stage-6 closure evidence entry is missing")
    else:
        if closure_entry.get("gap_status") != gap_status:
            errors.append("Stage-6 closure evidence gap status drift")
        required = closure_entry.get("closure_evidence_required")
        gap_row = next(
            (
                row
                for row in gaps or []
                if isinstance(row, dict) and row.get("id") == gap_id
            ),
            {},
        )
        if required != gap_row.get("closure_evidence"):
            errors.append("Stage-6 closure evidence requirement drift")
        if gap_status == "closed":
            if closure_entry.get("closure_decision") != "closed":
                errors.append("closed Stage-6 gap lacks closed decision")
            if closure_entry.get("outstanding_evidence"):
                errors.append("closed Stage-6 gap retains outstanding evidence")
            if closure_entry.get("blockers"):
                errors.append("closed Stage-6 gap retains blockers")

    item["_verified_dependency_status"] = {
        dep: dependency_status.get(dep, "missing")
        for dep in sorted(EXPECTED_DEPENDENCIES)
    }
    item["_verified_gap_status"] = gap_status
    return item


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundaries = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)
    handoff = _verify_machine_contracts(root, errors)
    return {
        "schema_version": 1,
        "verifier": "independent-stage6-streaming-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "boundary_digests": boundaries,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "dependency_status": dict(
            handoff.get("_verified_dependency_status") or {}
        ),
        "gap_status": handoff.get("_verified_gap_status"),
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
        print(f"independent-stage6-streaming: rejected: {exc}", file=sys.stderr)
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
        print("independent-stage6-streaming: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print("  - " + error, file=sys.stderr)
        return 1

    print(
        "independent-stage6-streaming: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
