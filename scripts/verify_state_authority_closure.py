#!/usr/bin/env python3
"""Independent state-authority closure verifier.

This verifier intentionally does not import the primary state-topology
validator or recovery drill. It independently reconstructs the production
authority map from machine/state_topology.json, cross-checks the durable SQLite
backup policy, verifies deployment persistence bindings, and rejects
authoritative state that drifts onto volatile/derived storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = Path("machine/state_topology.json")
BACKUP_POLICY_PATH = Path("machine/state_backup_policy.json")
COMPOSE_PATH = Path("docker-compose.yml")
RECOVERY_WORKFLOW_PATH = Path(".github/workflows/state-recovery-drill.yml")

REQUIRED_AUTHORITIES = {
    "backend-core-app-state": "mongo",
    "engine-mongo-state": "mongo",
    "canonical-operation-state": "operation-state-sqlite",
    "cognitive-execution-ledger": "engine-cognitive-sqlite",
    "tool-idempotency-ledger": "engine-cognitive-sqlite",
    "human-approval-ledger": "engine-cognitive-sqlite",
    "execution-usage-ledger": "engine-cognitive-sqlite",
    "final-ai-result-ledger": "engine-cognitive-sqlite",
    "conversation-thread-state": "mongo",
    "conversation-message-state": "mongo",
    "governance-lifecycle-registry": "governance-lifecycle-sqlite",
    "canonical-ai-memory-records": "mongo",
}

REQUIRED_DERIVED = {
    "backend-rag-local-chroma": "backend-data-volume",
    "optional-vector-index": "chroma-service",
    "in-process-retrieval-memory": "process-memory",
}

REQUIRED_BACKUP_FILES = {
    "operation_state.sqlite",
    "engine_execution.sqlite",
    "engine_submissions.sqlite",
    "engine_tool_receipts.sqlite",
    "engine_quota.sqlite",
    "engine_pressure.sqlite",
    "governance_lifecycle.sqlite",
}

OPTIONAL_BACKUP_FILES = {"operation_stream.sqlite"}

COMPOSE_BINDINGS = {
    "SKL_OPERATION_STATE_PATH": "/app/data/operation_state.sqlite",
    "SKL_OPERATION_STREAM_PATH": "/app/data/operation_stream.sqlite",
    "SKL_ENGINE_EXECUTION_STATE_PATH": "/app/data/engine_execution.sqlite",
    "SKL_ENGINE_SUBMISSION_STATE_PATH": "/app/data/engine_submissions.sqlite",
    "SKL_ENGINE_TOOL_RECEIPT_PATH": "/app/data/engine_tool_receipts.sqlite",
    "SKL_ENGINE_QUOTA_STATE_PATH": "/app/data/engine_quota.sqlite",
    "SKL_ENGINE_PRESSURE_STATE_PATH": "/app/data/engine_pressure.sqlite",
    "SKL_GOVERNANCE_LIFECYCLE_PATH": "/app/data/governance_lifecycle.sqlite",
}

NON_DURABLE_AUTHORITATIVE_STORES = {
    "process-memory",
    "snapshot-files",
    "backend-data-volume",
    "chroma-service",
}


class VerificationError(RuntimeError):
    """Independent state-authority verification failed."""


def _load_json(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(
            f"{relative.as_posix()} is unavailable or invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise VerificationError(
            f"{relative.as_posix()} must contain a JSON object"
        )
    return payload


def _objects_by_id(
    raw: object,
    *,
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        errors.append(f"{label} must be a non-empty list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        prefix = f"{label}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identity = item.get("id")
        if not isinstance(identity, str) or not identity.strip():
            errors.append(f"{prefix}.id must be non-empty")
            continue
        if identity in result:
            errors.append(f"duplicate {label} id: {identity}")
            continue
        result[identity] = dict(item)
    return result


def _verify_evidence_paths(
    root: Path,
    domain_id: str,
    domain: Mapping[str, Any],
    errors: list[str],
) -> None:
    evidence = domain.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{domain_id} must declare non-empty evidence")
        return
    for value in evidence:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{domain_id} has invalid evidence path")
            continue
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{domain_id} has unsafe evidence path: {value}")
            continue
        if not (root / path).exists():
            errors.append(f"{domain_id} evidence path is missing: {value}")


def _verify_authorities(
    root: Path,
    stores: Mapping[str, Mapping[str, Any]],
    domains: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    declared: list[dict[str, Any]] = []

    for domain_id, expected_store in REQUIRED_AUTHORITIES.items():
        domain = domains.get(domain_id)
        if domain is None:
            errors.append(f"required authoritative domain is missing: {domain_id}")
            continue
        if domain.get("physical_store") != expected_store:
            errors.append(
                f"{domain_id} must use {expected_store}, got "
                f"{domain.get('physical_store')!r}"
            )
        if domain.get("authority") != "authoritative":
            errors.append(f"{domain_id} must be authoritative")
        if domain.get("source_of_truth") is not True:
            errors.append(f"{domain_id} must be source_of_truth")
        if domain.get("rebuildable") is not False:
            errors.append(f"{domain_id} must not claim rebuildability")
        _verify_evidence_paths(root, domain_id, domain, errors)
        declared.append(
            {
                "id": domain_id,
                "store": domain.get("physical_store"),
                "authority": domain.get("authority"),
                "source_of_truth": domain.get("source_of_truth"),
            }
        )

    for domain_id, domain in domains.items():
        authority = domain.get("authority")
        store_id = domain.get("physical_store")
        if authority == "authoritative":
            if domain.get("source_of_truth") is not True:
                errors.append(
                    f"authoritative domain {domain_id} must be source_of_truth"
                )
            if domain.get("rebuildable") is not False:
                errors.append(
                    f"authoritative domain {domain_id} must not be rebuildable"
                )
            if store_id in NON_DURABLE_AUTHORITATIVE_STORES:
                errors.append(
                    f"authoritative domain {domain_id} uses non-authoritative "
                    f"store class {store_id}"
                )
            store = stores.get(str(store_id))
            if store is None:
                errors.append(
                    f"authoritative domain {domain_id} references missing store "
                    f"{store_id!r}"
                )
            elif store.get("durability") in {
                "volatile",
                "unbound",
                "operator-local-opt-in",
            }:
                errors.append(
                    f"authoritative domain {domain_id} uses non-durable store "
                    f"{store_id}"
                )
        elif authority == "authoritative-unbound":
            store = stores.get(str(store_id))
            if store is None or store.get("durability") != "unbound":
                errors.append(
                    f"authoritative-unbound domain {domain_id} must use an "
                    "unbound physical store"
                )
            if domain.get("gap") == "gap-state-authority-convergence":
                errors.append(
                    f"state-authority gap still owns unbound domain {domain_id}"
                )

    return declared


def _verify_derived(
    domains: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    declared: list[dict[str, Any]] = []
    for domain_id, expected_store in REQUIRED_DERIVED.items():
        domain = domains.get(domain_id)
        if domain is None:
            errors.append(f"required derived domain is missing: {domain_id}")
            continue
        if domain.get("physical_store") != expected_store:
            errors.append(
                f"{domain_id} must use {expected_store}, got "
                f"{domain.get('physical_store')!r}"
            )
        if domain.get("authority") != "derived":
            errors.append(f"{domain_id} must remain derived")
        if domain.get("source_of_truth") is not False:
            errors.append(f"{domain_id} must not be source_of_truth")
        if domain.get("rebuildable") is not True:
            errors.append(f"{domain_id} must be rebuildable")
        upstream = domain.get("derived_from")
        if not isinstance(upstream, list) or not upstream:
            errors.append(f"{domain_id} must declare upstream authority")
        else:
            for source in upstream:
                if not isinstance(source, str) or source not in domains:
                    errors.append(
                        f"{domain_id} references unknown upstream {source!r}"
                    )
        declared.append(
            {
                "id": domain_id,
                "store": domain.get("physical_store"),
                "derived_from": list(upstream or []),
            }
        )
    return declared


def _verify_backup_policy(
    policy: Mapping[str, Any],
    errors: list[str],
) -> list[dict[str, Any]]:
    if policy.get("schema_version") != 1:
        errors.append("backup policy schema_version must be 1")
    if policy.get("status") != "active":
        errors.append("backup policy must be active")
    if policy.get("topology_contract") != TOPOLOGY_PATH.as_posix():
        errors.append("backup policy must bind machine/state_topology.json")

    raw = policy.get("stores")
    if not isinstance(raw, list) or not raw:
        errors.append("backup policy stores must be non-empty")
        return []

    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    orders: list[int] = []
    receipt: list[dict[str, Any]] = []
    required_files: set[str] = set()
    optional_files: set[str] = set()

    for index, item in enumerate(raw):
        prefix = f"backup stores[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        store_id = item.get("id")
        filename = item.get("file")
        required = item.get("required")
        order = item.get("restore_order")
        if not isinstance(store_id, str) or not store_id:
            errors.append(f"{prefix}.id must be non-empty")
            continue
        if store_id in seen_ids:
            errors.append(f"duplicate backup store id: {store_id}")
        seen_ids.add(store_id)
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
        ):
            errors.append(f"{prefix}.file must be a basename")
            continue
        if filename in seen_files:
            errors.append(f"duplicate backup file: {filename}")
        seen_files.add(filename)
        if not isinstance(required, bool):
            errors.append(f"{prefix}.required must be boolean")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            errors.append(f"{prefix}.restore_order must be positive integer")
        else:
            orders.append(order)
        if required is True:
            required_files.add(filename)
        elif required is False:
            optional_files.add(filename)
        receipt.append(
            {
                "id": store_id,
                "file": filename,
                "required": required,
                "restore_order": order,
                "authority": item.get("authority"),
            }
        )

    if required_files != REQUIRED_BACKUP_FILES:
        errors.append(
            "required backup files drifted: expected "
            + ",".join(sorted(REQUIRED_BACKUP_FILES))
            + " got "
            + ",".join(sorted(required_files))
        )
    if optional_files != OPTIONAL_BACKUP_FILES:
        errors.append(
            "optional backup files drifted: expected "
            + ",".join(sorted(OPTIONAL_BACKUP_FILES))
            + " got "
            + ",".join(sorted(optional_files))
        )
    if len(orders) != len(set(orders)):
        errors.append("backup restore_order values must be unique")
    if orders != sorted(orders):
        errors.append("backup stores must be declared in restore order")

    retention = policy.get("retention")
    if not isinstance(retention, dict):
        errors.append("backup retention policy must be an object")
    else:
        snapshots = retention.get("minimum_verified_snapshots")
        if isinstance(snapshots, bool) or not isinstance(snapshots, int) or snapshots < 2:
            errors.append("backup retention must keep at least two verified snapshots")
        if retention.get("prune_requires_newer_verified_snapshot") is not True:
            errors.append(
                "backup pruning must require a newer verified snapshot"
            )

    return receipt


def _verify_deployment(root: Path, errors: list[str]) -> None:
    try:
        compose = (root / COMPOSE_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError("docker-compose.yml is unavailable") from exc
    if "skeleton_data:/app/data" not in compose:
        errors.append("skeleton service must mount skeleton_data:/app/data")
    for name, value in COMPOSE_BINDINGS.items():
        token = f"{name}={value}"
        if token not in compose:
            errors.append(f"Compose lost durable binding: {token}")

    try:
        workflow = (root / RECOVERY_WORKFLOW_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(
            ".github/workflows/state-recovery-drill.yml is unavailable"
        ) from exc
    for token in (
        "scripts/state_recovery_drill.py live-mongo",
        "scripts/state_recovery_drill.py live-sqlite",
        "scripts/state_recovery_drill.py live-engine-sqlite",
        "scripts/verify_state_authority_closure.py",
    ):
        if token not in workflow:
            errors.append(
                f"State Recovery Drill lost required closure step: {token}"
            )


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    topology = _load_json(root, TOPOLOGY_PATH)
    policy = _load_json(root, BACKUP_POLICY_PATH)
    errors: list[str] = []

    if topology.get("schema_version") != 1:
        errors.append("state topology schema_version must be 1")
    if topology.get("status") != "active":
        errors.append("state topology must be active")

    stores = _objects_by_id(
        topology.get("physical_stores"),
        label="physical_stores",
        errors=errors,
    )
    domains = _objects_by_id(
        topology.get("state_domains"),
        label="state_domains",
        errors=errors,
    )

    authorities = _verify_authorities(root, stores, domains, errors)
    derived = _verify_derived(domains, errors)
    backup = _verify_backup_policy(policy, errors)
    _verify_deployment(root, errors)

    topology_backup = topology.get("backup_policy")
    if not isinstance(topology_backup, dict):
        errors.append("state topology must link backup_policy")
    else:
        expected = {
            "contract": BACKUP_POLICY_PATH.as_posix(),
            "tool": "scripts/state_backup_bundle.py",
            "recovery_drill": "scripts/state_recovery_drill.py",
            "workflow": RECOVERY_WORKFLOW_PATH.as_posix(),
        }
        for key, value in expected.items():
            if topology_backup.get(key) != value:
                errors.append(
                    f"state topology backup_policy.{key} must be {value}"
                )
            if not (root / value).exists():
                errors.append(
                    f"state topology backup_policy path is missing: {value}"
                )

    digest_payload = {
        "authorities": sorted(authorities, key=lambda item: item["id"]),
        "derived": sorted(derived, key=lambda item: item["id"]),
        "backup": backup,
    }
    digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-state-authority-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "topology_version": topology.get("topology_version"),
        "authority_digest": digest,
        "authoritative_domains": authorities,
        "derived_domains": derived,
        "backup_stores": backup,
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
        print(
            f"independent-state-authority: rejected: {exc}",
            file=sys.stderr,
        )
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
        print("independent-state-authority: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-state-authority: OK "
        f"(authorities={len(receipt['authoritative_domains'])}, "
        f"derived={len(receipt['derived_domains'])}, "
        f"backup_stores={len(receipt['backup_stores'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
