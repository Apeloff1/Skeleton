#!/usr/bin/env python3
"""Independent Stage-6 streaming protocol closure verifier.

The verifier inspects source and machine contracts directly. It does not import
the production stream runtime, so closure cannot be self-certified by the code
under test.
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
GAP_ID = "gap-streaming-protocol"
DEPENDENCIES = {
    "gap-cognitive-execution-loop",
    "gap-engine-application-execution-boundary",
    "gap-state-authority-convergence",
}

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/frontier/operation_stream.py": (
        "class StreamEvent",
        "class ReplayCursor",
        "class OperationEventLog",
        "StreamBackpressureError",
        "StreamReplayGapError",
        "StreamTerminalError",
    ),
    "skeleton/frontier/operation_stream_store.py": (
        "class SQLiteOperationEventStore",
        "class StreamConsumerCheckpoint",
        "class StreamWorkerLease",
        "acquire_worker_lease",
        "compact_acknowledged",
    ),
    "skeleton/frontier/operation_stream_store_mongo.py": (
        "class MongoOperationEventStore",
        "validate_transaction_capability",
        "acquire_worker_lease",
        "compact_acknowledged",
    ),
    "backend/core/operation_stream_transport.py": (
        "class OperationStateStore",
        "class OperationEventStore",
        "class OperationStreamTransport",
        "transport_from_env",
        "acknowledge_and_compact",
    ),
    "backend/routes/operation_stream.py": (
        "router",
        "Last-Event-ID",
        "consumer_id",
        "resync",
    ),
    "frontend/services/operationStreamSession.ts": (
        "export class OperationBrowserSession",
        "async replayOnce(",
        "async resync(",
        "async resume(",
        "async follow(",
        "async cancel(",
    ),
    "frontend/services/operationStream.ts": (
        "createOperationBrowserSession",
        "browserSessionTransport",
        "browserSessionCursorStore",
    ),
    "frontend/scripts/test-operation-stream-reducer.mjs": (
        "duplicate",
        "sequence",
        "terminal",
    ),
    "frontend/scripts/test-operation-stream-session.mjs": (
        "browser disconnect and reconnect resumes from persisted accepted cursor",
        "slow browser recovers from compacted replay gap through authoritative floor",
        "cancel-complete race exposes exactly one canonical terminal outcome per session",
        "terminal authoritative resync snapshot reconciles canonical output before fencing",
    ),
    "backend/tests/test_operation_stream_multiworker.py": (
        "test_multiworker_concurrent_outbox_projection_is_exactly_once",
        "test_disconnect_reconnect_hands_cursor_to_another_worker_without_duplicates",
        "test_multiworker_cancel_complete_race_emits_one_terminal_event",
    ),
}

MIRROR_PAIRS = (
    (
        "skeleton/frontier/operation_stream.py",
        "skeleton/ai/runtime/frontier/operation_stream.py",
    ),
    (
        "skeleton/frontier/operation_stream_store.py",
        "skeleton/ai/runtime/frontier/operation_stream_store.py",
    ),
    (
        "skeleton/frontier/operation_stream_store_mongo.py",
        "skeleton/ai/runtime/frontier/operation_stream_store_mongo.py",
    ),
)


class VerificationError(RuntimeError):
    pass


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain a JSON object")
    return value


def _entry(payload: dict[str, Any], gap_id: str) -> dict[str, Any] | None:
    rows = payload.get("entries")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("gap") == gap_id:
            return row
    return None


def _boundary_receipts(root: Path, errors: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"stream boundary missing: {rel}")
            continue
        source = _text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost Stage-6 token: {token}")
        result[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return result


def _mirror_receipts(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file() or not mirror.is_file():
            errors.append(f"stream mirror missing: {source_rel} -> {mirror_rel}")
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
            errors.append(f"stream canonical mirror drift: {source_rel} != {mirror_rel}")
    return rows


def _machine_receipt(root: Path, errors: list[str]) -> dict[str, Any]:
    construction = _json(root / "machine/ai_app_construction.json")
    handoff = _json(root / "machine/ai_implementation_handoff.json")
    closure = _json(root / "machine/ai_closure_evidence.json")

    gap_rows = construction.get("gap_register")
    if not isinstance(gap_rows, list):
        errors.append("construction gap_register must be a list")
        gap_rows = []

    gap = next(
        (row for row in gap_rows if isinstance(row, dict) and row.get("id") == GAP_ID),
        None,
    )
    if gap is None:
        errors.append("Stage-6 construction gap is missing")
        gap = {}

    blueprint = construction.get("realtime_delivery_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("realtime_delivery_blueprint is missing")
        blueprint = {}

    handoff_entry = _entry(handoff, GAP_ID)
    closure_entry = _entry(closure, GAP_ID)
    if handoff_entry is None:
        errors.append("Stage-6 handoff entry is missing")
        handoff_entry = {}
    if closure_entry is None:
        errors.append("Stage-6 closure entry is missing")
        closure_entry = {}

    if blueprint.get("gap") != GAP_ID:
        errors.append("Stage-6 blueprint gap binding is invalid")
    if blueprint.get("status") not in {"implemented-pending-closure", "complete"}:
        errors.append("Stage-6 blueprint status is invalid")

    if handoff_entry.get("implementation_status") not in {
        "implemented_pending_closure",
        "implementation-complete",
        "closed",
    }:
        errors.append("Stage-6 handoff implementation status is invalid")

    depends_on = set(handoff_entry.get("depends_on") or [])
    if depends_on != DEPENDENCIES:
        errors.append(
            "Stage-6 dependency graph mismatch: " + ", ".join(sorted(depends_on))
        )

    dependency_status = {
        str(row.get("id")): str(row.get("status"))
        for row in gap_rows
        if isinstance(row, dict) and row.get("id") in DEPENDENCIES
    }
    if set(dependency_status) != DEPENDENCIES:
        errors.append("Stage-6 dependency status inventory is incomplete")

    gap_status = str(gap.get("status") or "missing")
    if gap_status not in {"open", "closed"}:
        errors.append("Stage-6 construction status is invalid")

    if gap_status == "closed":
        open_dependencies = sorted(
            dep for dep in DEPENDENCIES if dependency_status.get(dep) != "closed"
        )
        if open_dependencies:
            errors.append(
                "closed Stage-6 gap has non-closed dependencies: "
                + ", ".join(open_dependencies)
            )
        if blueprint.get("status") != "complete":
            errors.append("closed Stage-6 gap requires complete blueprint")
        if handoff_entry.get("implementation_status") != "closed":
            errors.append("closed Stage-6 gap requires closed handoff")
        if closure_entry.get("closure_decision") != "closed":
            errors.append("closed Stage-6 gap requires closed closure decision")
        if closure_entry.get("implementation_state") != "closed":
            errors.append("closed Stage-6 gap requires closed implementation state")
        if closure_entry.get("outstanding_evidence"):
            errors.append("closed Stage-6 gap has outstanding evidence")
        if closure_entry.get("blockers"):
            errors.append("closed Stage-6 gap has blockers")

    evidence = "\n".join(str(x) for x in closure_entry.get("evidence_present") or [])
    for phrase in (
        "browser-session reconnect",
        "Mongo",
        "cancel-complete",
        "shared-network",
    ):
        if phrase not in evidence:
            errors.append(f"Stage-6 closure evidence lost phrase: {phrase}")

    return {
        "gap_status": gap_status,
        "blueprint_status": blueprint.get("status"),
        "handoff_status": handoff_entry.get("implementation_status"),
        "closure_decision": closure_entry.get("closure_decision"),
        "dependency_status": dependency_status,
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundaries = _boundary_receipts(root, errors)
    mirrors = _mirror_receipts(root, errors)
    machine = _machine_receipt(root, errors)
    return {
        "schema_version": 1,
        "verifier": "independent-streaming-protocol-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "boundary_digests": boundaries,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(DEPENDENCIES),
        "machine": machine,
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
        print(f"independent-streaming-protocol: rejected: {exc}", file=sys.stderr)
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
        print("independent-streaming-protocol: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-streaming-protocol: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
