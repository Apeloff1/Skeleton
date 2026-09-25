#!/usr/bin/env python3
"""Fail-closed closure gate for canonical state authority and recovery order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from scripts.check_state_topology import validate_state_topology


ROOT = Path(__file__).resolve().parents[1]

_EXPECTED_ENGINE_DOMAINS = {
    "cognitive-execution-ledger": "engine-execution-sqlite",
    "execution-usage-ledger": "engine-execution-sqlite",
    "final-ai-result-ledger": "engine-execution-sqlite",
    "verification-receipt-ledger": "engine-execution-sqlite",
    "human-approval-ledger": "engine-submission-sqlite",
    "tool-idempotency-ledger": "engine-tool-receipt-sqlite",
}
_EXPECTED_ENGINE_STORES = {
    "engine-execution-sqlite",
    "engine-submission-sqlite",
    "engine-tool-receipt-sqlite",
}
_EXPECTED_COMPOSE_PATHS = {
    "SKL_OPERATION_STATE_PATH=/app/data/operation_state.sqlite",
    "SKL_OPERATION_STREAM_PATH=/app/data/operation_stream.sqlite",
    "SKL_ENGINE_EXECUTION_STATE_PATH=/app/data/engine_execution.sqlite",
    "SKL_ENGINE_SUBMISSION_STATE_PATH=/app/data/engine_submissions.sqlite",
    "SKL_ENGINE_TOOL_RECEIPT_PATH=/app/data/engine_tool_receipts.sqlite",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON contract: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON contract must be an object: {path}")
    return payload


def topology_closure_errors(topology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    stores = {
        item.get("id"): item
        for item in topology.get("physical_stores", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    domains = {
        item.get("id"): item
        for item in topology.get("state_domains", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    unbound_stores = sorted(
        store_id
        for store_id, item in stores.items()
        if item.get("durability") == "unbound"
        or "unbound" in store_id
    )
    if unbound_stores:
        errors.append(
            "production state topology retains unbound physical stores: "
            + ", ".join(unbound_stores)
        )

    unbound_domains = sorted(
        domain_id
        for domain_id, item in domains.items()
        if item.get("authority") == "authoritative-unbound"
        or item.get("status") == "planned-contract"
    )
    if unbound_domains:
        errors.append(
            "production state topology retains authoritative-unbound domains: "
            + ", ".join(unbound_domains)
        )

    missing_stores = sorted(_EXPECTED_ENGINE_STORES - set(stores))
    if missing_stores:
        errors.append(
            "durable engine physical stores missing: "
            + ", ".join(missing_stores)
        )
    for store_id in sorted(_EXPECTED_ENGINE_STORES):
        store = stores.get(store_id)
        if store is None:
            continue
        if store.get("runtime_service") != "skeleton":
            errors.append(f"{store_id} must be owned by skeleton service")
        if store.get("durability") != "persistent-volume":
            errors.append(f"{store_id} must be persistent-volume")
        volumes = store.get("volumes")
        if not isinstance(volumes, list) or "skeleton_data" not in volumes:
            errors.append(f"{store_id} must be persisted on skeleton_data")

    for domain_id, store_id in _EXPECTED_ENGINE_DOMAINS.items():
        domain = domains.get(domain_id)
        if domain is None:
            errors.append(f"canonical state domain missing: {domain_id}")
            continue
        if domain.get("physical_store") != store_id:
            errors.append(
                f"{domain_id} must bind to {store_id}; "
                f"found={domain.get('physical_store')!r}"
            )
        if domain.get("authority") != "authoritative":
            errors.append(f"{domain_id} must be authoritative")
        if domain.get("source_of_truth") is not True:
            errors.append(f"{domain_id} must be source_of_truth")
        if domain.get("rebuildable") is not False:
            errors.append(f"{domain_id} must not be rebuildable")
        if domain.get("status") != "production-bound":
            errors.append(f"{domain_id} must be production-bound")

    rag = domains.get("backend-rag-local-chroma")
    if rag is None:
        errors.append("backend-rag-local-chroma domain missing")
    else:
        if rag.get("authority") != "derived":
            errors.append("backend RAG Chroma must be derived")
        if rag.get("source_of_truth") is not False:
            errors.append("backend RAG Chroma cannot be source_of_truth")
        if rag.get("rebuildable") is not True:
            errors.append("backend RAG Chroma must be rebuildable")
        derived_from = rag.get("derived_from")
        if (
            not isinstance(derived_from, list)
            or "backend-core-app-state" not in derived_from
        ):
            errors.append(
                "backend RAG Chroma must derive from backend-core-app-state"
            )

    operation = domains.get("canonical-operation-state")
    if operation is None:
        errors.append("canonical-operation-state domain missing")
    elif (
        operation.get("physical_store") != "operation-state-sqlite"
        or operation.get("authority") != "authoritative"
        or operation.get("status") != "production-bound"
    ):
        errors.append(
            "canonical operation state must be production-bound authoritative SQLite"
        )

    stream = domains.get("operation-event-stream")
    if stream is None:
        errors.append("operation-event-stream domain missing")
    elif (
        stream.get("physical_store") != "operation-stream-sqlite"
        or stream.get("authority") != "durable-projection"
        or stream.get("source_of_truth") is not False
    ):
        errors.append(
            "operation event stream must remain a non-authoritative durable projection"
        )

    recovery_order = topology.get("recovery_order")
    if not isinstance(recovery_order, list):
        errors.append("state recovery_order must be a list")
    else:
        joined = "\n".join(
            item for item in recovery_order if isinstance(item, str)
        )
        required_phrases = (
            "verify authoritative document counts",
            "restore engine execution/turn/checkpoint authority",
            "restore engine_tool_receipts.sqlite",
            "rebuild Chroma/vector",
            "enable traffic only after authoritative stores are healthy",
        )
        for phrase in required_phrases:
            if phrase not in joined:
                errors.append(
                    f"state recovery order missing required phase: {phrase}"
                )
        verify_index = next(
            (
                i
                for i, item in enumerate(recovery_order)
                if isinstance(item, str)
                and "verify authoritative document counts" in item
            ),
            None,
        )
        rebuild_index = next(
            (
                i
                for i, item in enumerate(recovery_order)
                if isinstance(item, str)
                and "rebuild Chroma/vector" in item
            ),
            None,
        )
        if (
            verify_index is not None
            and rebuild_index is not None
            and verify_index >= rebuild_index
        ):
            errors.append(
                "derived rebuild must occur after authoritative restore verification"
            )

    return errors


def compose_closure_errors(compose: str) -> list[str]:
    errors: list[str] = []
    skeleton_start = compose.find("\n  skeleton:\n")
    backend_start = compose.find("\n  backend:\n", skeleton_start + 1)
    if skeleton_start < 0 or backend_start < 0:
        return ["canonical compose is missing skeleton/backend service boundary"]
    skeleton_block = compose[skeleton_start:backend_start]

    for marker in sorted(_EXPECTED_COMPOSE_PATHS):
        if marker not in skeleton_block:
            errors.append(
                "Skeleton service missing durable state binding: " + marker
            )
    if "      - skeleton_data:/app/data" not in skeleton_block:
        errors.append("Skeleton service must mount skeleton_data at /app/data")
    for marker in (
        "SKL_OPERATION_STATE_PATH=:memory:",
        "SKL_OPERATION_STREAM_PATH=:memory:",
        "SKL_ENGINE_EXECUTION_STATE_PATH=:memory:",
        "SKL_ENGINE_SUBMISSION_STATE_PATH=:memory:",
        "SKL_ENGINE_TOOL_RECEIPT_PATH=:memory:",
    ):
        if marker in skeleton_block:
            errors.append(
                "canonical Compose must not use in-memory state binding: " + marker
            )
    if (
        'com.skeleton.state.role: '
        '"authoritative-operation-and-engine-state-plus-stream-projection"'
        not in compose
    ):
        errors.append(
            "skeleton_data volume role does not declare engine/operation authority"
        )
    return errors


def server_lifecycle_errors(source: str) -> list[str]:
    errors: list[str] = []
    required = {
        "DurableOperationRuntime.from_settings(": (
            "server does not bind DurableOperationRuntime"
        ),
        "runtime.dispatch_outbox()": (
            "server does not drain operation outbox before dispatcher start"
        ),
        "runtime.start_dispatcher()": (
            "server does not start operation outbox dispatcher"
        ),
        "state.bind_engine_execution_service()": (
            "server startup does not bind engine execution service"
        ),
        "await state.recover_engine_executions()": (
            "server startup does not recover durable engine executions"
        ),
        "await state.close_engine_execution_service()": (
            "server shutdown does not close engine execution service"
        ),
        "state.close_operation_runtime()": (
            "server shutdown does not close operation runtime"
        ),
        "SQLiteExecutionRepository(": (
            "server does not bind durable execution repository"
        ),
        "SQLiteEngineSubmissionStore(": (
            "server does not bind durable submission/approval repository"
        ),
        "SQLiteToolReceiptStore(": (
            "server does not bind durable tool receipt repository"
        ),
    }
    for token, message in required.items():
        if token not in source:
            errors.append(message)
    return errors


def recovery_drill_errors(source: str) -> list[str]:
    errors: list[str] = []
    required = {
        "capture_database(": "recovery drill does not capture Mongo authority",
        "restore_database(": "recovery drill does not restore Mongo authority",
        "verify_snapshot(": "recovery drill does not verify restored authority",
        "rebuild_derived_projection(": (
            "recovery drill does not rebuild derived projection"
        ),
        "derived rebuild forbidden before authoritative verification": (
            "recovery drill does not fence derived rebuild before verification"
        ),
        '"rag_user_progress"': (
            "recovery drill does not seed canonical RAG progress authority"
        ),
        '"rag_learning_sessions"': (
            "recovery drill does not seed canonical RAG learning authority"
        ),
    }
    for token, message in required.items():
        if token not in source:
            errors.append(message)
    return errors


def validate_state_authority_closure(
    repo_root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []
    topology_errors, _summary = validate_state_topology(repo_root)
    errors.extend(
        "state-topology: " + item
        for item in topology_errors
    )
    try:
        topology = _load_json(repo_root / "machine/state_topology.json")
    except ValueError as exc:
        return errors + [str(exc)]
    errors.extend(topology_closure_errors(topology))

    try:
        compose = (repo_root / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"cannot read docker-compose.yml: {exc}")
    else:
        errors.extend(compose_closure_errors(compose))

    try:
        server = (repo_root / "skeleton/api/server.py").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"cannot read skeleton/api/server.py: {exc}")
    else:
        errors.extend(server_lifecycle_errors(server))

    try:
        drill = (repo_root / "scripts/state_recovery_drill.py").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"cannot read state recovery drill: {exc}")
    else:
        errors.extend(recovery_drill_errors(drill))

    required_evidence = (
        "backend/services/rag_state_repository.py",
        "backend/tests/test_rag_state_repository.py",
        "backend/tests/test_rag_state_authority.py",
        "skeleton/persistence/operation_runtime.py",
        "skeleton/testing/test_operation_runtime.py",
        "skeleton/testing/test_operation_server_binding.py",
        "skeleton/persistence/execution_repository.py",
        "skeleton/testing/test_execution_repository.py",
        "skeleton/api/engine_service.py",
        "skeleton/testing/test_engine_execution_service.py",
        "skeleton/skills/tool_receipt_store.py",
        "skeleton/testing/test_tool_receipt_store.py",
        "skeleton/testing/test_state_recovery_drill.py",
    )
    for relative in required_evidence:
        if not (repo_root / relative).is_file():
            errors.append("state closure evidence path missing: " + relative)

    return errors


def build_state_closure_receipt(
    repo_root: Path = ROOT,
    *,
    head_sha: str | None = None,
) -> dict[str, Any]:
    errors = validate_state_authority_closure(repo_root)
    topology = _load_json(repo_root / "machine/state_topology.json")
    domains = {
        item["id"]: {
            "physical_store": item.get("physical_store"),
            "authority": item.get("authority"),
            "status": item.get("status"),
        }
        for item in topology.get("state_domains", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item.get("id") in (
            set(_EXPECTED_ENGINE_DOMAINS)
            | {
                "canonical-operation-state",
                "operation-event-stream",
                "backend-rag-local-chroma",
            }
        )
    }
    return {
        "schema_version": 1,
        "gap": "gap-state-authority-convergence",
        "head_sha": head_sha or "unknown",
        "topology_version": topology.get("topology_version"),
        "engine_domain_bindings": domains,
        "validation_errors": errors,
        "valid": not errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path, default=None)
    parser.add_argument("--print-evidence", action="store_true")
    parser.add_argument("--head-sha", default=None)
    args = parser.parse_args(argv)

    receipt = build_state_closure_receipt(
        ROOT,
        head_sha=args.head_sha,
    )
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        print("state-authority-closure: rejected", file=sys.stderr)
        for error in receipt["validation_errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "state-authority-closure: OK "
        "(Mongo-first RAG, durable operation/engine authority, "
        "outbox lifecycle, authoritative-first recovery)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
