#!/usr/bin/env python3
"""Independent VOL-129/130/131/132 contract-consistency verifier."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
RUNTIME_SCHEMAS = Path("machine/ai_runtime_schemas.json")
CONFORMANCE = Path("machine/contract_conformance.json")
SCHEMA_REGISTRY = Path("machine/schema_registry.json")
COMPATIBILITY = Path("machine/compatibility_model.json")
STATE_TOPOLOGY = Path("machine/state_topology.json")
CONSISTENCY_PROFILES = Path("machine/consistency_profiles.json")
SCHEMA_GUARD = Path("skeleton/data/schema_evolution.py")
SCHEMA_GUARD_MIRROR = Path("skeleton/ai/runtime/data/schema_evolution.py")
CONSISTENCY_RUNTIME = Path("skeleton/persistence/consistency.py")
CONSISTENCY_MIRROR = Path("skeleton/ai/runtime/persistence/consistency.py")
PROTOCOL_CONTRACT = Path("skeleton/contracts/protocol.py")
PROTOCOL_CONTRACT_MIRROR = Path("skeleton/ai/runtime/contracts/protocol.py")
PROTOCOL_EXECUTION = Path("skeleton/distributed/network/internal_protocol.py")
PROTOCOL_EXECUTION_MIRROR = Path(
    "skeleton/ai/runtime/distributed/network/internal_protocol.py"
)
EXPECTED_VOLUMES = {
    "VOL-129": (
        "Schema Registry",
        {"inventory serialized contracts", "materialize compatibility checker"},
    ),
    "VOL-130": (
        "Compatibility Model",
        {"bind schema/API versions to matrix", "define support window policy"},
    ),
    "VOL-131": (
        "Internal Protocols",
        {"unify protocol envelopes", "bind protocols to tracing"},
    ),
    "VOL-132": (
        "Consistency Model",
        {"classify state domains", "bind guarantees to stores"},
    ),
}
REQUIRED_NEW_SCHEMAS = {
    "ProtocolEnvelope": "foundation",
    "ProtocolExecutionEnvelope": "orchestration",
    "ProtocolReceipt": "observability",
    "ConsistencyProfile": "data-persistence",
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _receipt_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _verify_masterplan(
    master: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    by_key = {
        row.get("key"): row
        for row in master.get("volumes", [])
        if isinstance(row, dict)
    }
    result: dict[str, Any] = {}
    for key, (title, gaps) in EXPECTED_VOLUMES.items():
        volume = by_key.get(key)
        if not isinstance(volume, dict):
            errors.append(f"masterplan missing {key}")
            continue
        if volume.get("title") != title:
            errors.append(f"{key} title drift")
        if volume.get("scope") != "canonical-plan":
            errors.append(f"{key} scope drift")
        if volume.get("completion_checkbox") is True:
            errors.append(f"{key} cannot self-sign from implementation evidence")
        if not gaps <= set(volume.get("gaps") or []):
            errors.append(f"{key} implementation gap binding drift")
        result[key] = {
            "title": volume.get("title"),
            "implementation_status": volume.get("implementation_status"),
            "completion_checkbox": volume.get("completion_checkbox"),
            "gaps": list(volume.get("gaps") or []),
        }
    return result


def _verify_schemas(
    runtime: Mapping[str, Any],
    conformance: Mapping[str, Any],
    registry: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    records = runtime.get("records")
    schemas = registry.get("schemas")
    entries = conformance.get("entries")
    if not isinstance(records, dict) or not isinstance(schemas, list):
        errors.append("schema catalog/registry structure missing")
        return {}
    if not isinstance(entries, list):
        errors.append("contract conformance entries missing")
        return {}
    if len(records) != 40 or len(schemas) != 40:
        errors.append(
            f"expected 40 registered runtime schemas, got {len(records)}/{len(schemas)}"
        )
    if [row.get("record_name") for row in schemas] != list(records):
        errors.append("schema registry order/coverage drift")

    conformance_by_name = {
        row.get("contract"): row for row in entries if isinstance(row, dict)
    }
    if set(conformance_by_name) != set(records):
        errors.append("contract conformance does not exactly cover runtime schemas")

    by_name = {
        row.get("record_name"): row for row in schemas if isinstance(row, dict)
    }
    for name, owner in REQUIRED_NEW_SCHEMAS.items():
        record = records.get(name)
        registered = by_name.get(name)
        lineage = conformance_by_name.get(name)
        if not isinstance(record, dict):
            errors.append(f"runtime schema missing {name}")
            continue
        if record.get("owner_plane") != owner:
            errors.append(f"{name} owner plane drift")
        if not isinstance(registered, dict):
            errors.append(f"schema registry missing {name}")
            continue
        if registered.get("schema_id") != f"SCHEMA-{name}":
            errors.append(f"{name} stable schema identity drift")
        if registered.get("migration_required_for_breaking_change") is not True:
            errors.append(f"{name} lost breaking-change migration requirement")
        if not isinstance(lineage, dict):
            errors.append(f"{name} conformance lineage missing")
        elif lineage.get("producer_plane") != owner:
            errors.append(f"{name} producer/owner lineage drift")

    return {
        "runtime_schema_count": len(records),
        "registered_schema_count": len(schemas),
        "new_schema_ids": sorted(
            by_name[name]["schema_id"]
            for name in REQUIRED_NEW_SCHEMAS
            if name in by_name
        ),
    }


def _verify_compatibility(
    registry: Mapping[str, Any],
    model: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    policy = model.get("support_window_policy")
    if not isinstance(policy, dict):
        errors.append("compatibility support window missing")
        return {}
    if policy.get("default_supported_versions") != 2:
        errors.append("default compatibility support window drift")
    for key in ("rule", "breaking_change_rule", "rollback_rule"):
        if not isinstance(policy.get(key), str) or not policy[key]:
            errors.append(f"compatibility policy lacks {key}")

    sources = model.get("sources")
    if not isinstance(sources, dict) or sources.get("executable_guard") != SCHEMA_GUARD.as_posix():
        errors.append("compatibility model lost executable schema guard binding")

    expected = [
        {
            "schema_id": row["schema_id"],
            "current_version": row["version"],
            "supported_versions": [row["version"]],
            "reader_writer_mode": row["compatibility_mode"],
            "producer_plane": row["producer_plane"],
            "consumer_planes": list(row["consumer_planes"]),
            "migration_required_for_breaking_change": True,
        }
        for row in registry.get("schemas", [])
    ]
    if model.get("schema_matrix") != expected:
        errors.append("compatibility schema matrix is not exact registry projection")

    guard = root / SCHEMA_GUARD
    guard_mirror = root / SCHEMA_GUARD_MIRROR
    if not guard.is_file() or not guard_mirror.is_file():
        errors.append("schema evolution runtime/mirror missing")
        return {}
    if guard.read_bytes() != guard_mirror.read_bytes():
        errors.append("schema evolution AI mirror drift")
    source = guard.read_text(encoding="utf-8")
    for token in (
        "class VersionWindow",
        "class EvolutionPlan",
        "class SchemaEvolutionGuard",
        "unsupported compatibility mode",
        "requiredness_tightened",
        "enum_narrowed",
        "constraint_tightened",
        "schema transition is not eligible for promotion",
        "eligible_for_promotion",
        "rollback_required",
    ):
        if token not in source:
            errors.append(f"compatibility runtime invariant missing: {token}")

    return {
        "schema_matrix_count": len(expected),
        "interface_matrix_count": len(model.get("interface_matrix") or []),
        "guard_digest": _sha256(guard),
        "guard_mirror_parity": guard.read_bytes() == guard_mirror.read_bytes(),
    }


def _verify_consistency(
    topology: Mapping[str, Any],
    registry: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    domains = topology.get("state_domains")
    profiles = registry.get("profiles")
    if not isinstance(domains, list) or not isinstance(profiles, list):
        errors.append("state topology/consistency profile structure missing")
        return {}
    if len(domains) != len(profiles):
        errors.append("consistency profile domain coverage drift")
    if registry.get("profile_count") != len(domains):
        errors.append("consistency profile_count drift")
    if [row.get("domain_id") for row in profiles] != [
        row.get("id") for row in domains
    ]:
        errors.append("consistency profile order/identity drift")
    source = registry.get("sources")
    if not isinstance(source, dict):
        errors.append("consistency sources missing")
    else:
        topology_source = source.get("state_topology")
        if not isinstance(topology_source, dict):
            errors.append("consistency topology source missing")
        elif topology_source.get("git_blob_sha") != _git_blob_sha(root / STATE_TOPOLOGY):
            errors.append("consistency profile topology identity is stale")

    for profile in profiles:
        if not isinstance(profile, dict):
            errors.append("consistency profile must be an object")
            continue
        authority = profile.get("authority")
        if profile.get("unknown_policy") != "reject":
            errors.append(f"{profile.get('domain_id')} permits unknown state")
        if authority in {"authoritative", "conditional-authoritative"}:
            if profile.get("stale_policy") != "reject":
                errors.append(f"{profile.get('domain_id')} permits stale authoritative reads")
            if profile.get("write_guarantee") != "durable_commit_ack":
                errors.append(f"{profile.get('domain_id')} lacks durable write acknowledgement")
        if authority in {"derived", "durable-projection"}:
            if profile.get("stale_policy") != "explicit_only":
                errors.append(f"{profile.get('domain_id')} projection staleness is implicit")
            if profile.get("write_guarantee") != "source_first_then_project":
                errors.append(f"{profile.get('domain_id')} projection is not source-first")
            if not profile.get("source_refs"):
                errors.append(f"{profile.get('domain_id')} projection lacks source refs")

    runtime = root / CONSISTENCY_RUNTIME
    mirror = root / CONSISTENCY_MIRROR
    if not runtime.is_file() or not mirror.is_file():
        errors.append("consistency runtime/mirror missing")
        return {}
    if runtime.read_bytes() != mirror.read_bytes():
        errors.append("consistency runtime AI mirror drift")
    source_text = runtime.read_text(encoding="utf-8")
    for token in (
        "class ConsistencyProfile",
        "class ReadObservation",
        "class ConsistencyDecision",
        "class FreshnessState",
        "state freshness is unknown; fail closed",
        "stale state requires an explicit projection policy and caller opt-in",
        "authoritative profile cannot serve stale reads",
        "def evaluate_read(",
        "def require_readable(",
    ):
        if token not in source_text:
            errors.append(f"consistency runtime invariant missing: {token}")

    return {
        "profile_count": len(profiles),
        "runtime_digest": _sha256(runtime),
        "runtime_mirror_parity": runtime.read_bytes() == mirror.read_bytes(),
    }


def _verify_protocol(root: Path, errors: list[str]) -> dict[str, Any]:
    contract = root / PROTOCOL_CONTRACT
    contract_mirror = root / PROTOCOL_CONTRACT_MIRROR
    execution = root / PROTOCOL_EXECUTION
    execution_mirror = root / PROTOCOL_EXECUTION_MIRROR
    for path in (contract, contract_mirror, execution, execution_mirror):
        if not path.is_file():
            errors.append(f"protocol surface missing: {path.relative_to(root)}")
            return {}
    if contract.read_bytes() != contract_mirror.read_bytes():
        errors.append("canonical protocol contract mirror drift")
    if execution.read_bytes() != execution_mirror.read_bytes():
        errors.append("protocol execution mirror drift")
    contract_text = contract.read_text(encoding="utf-8")
    execution_text = execution.read_text(encoding="utf-8")
    if contract_text.count("class ProtocolEnvelope") != 1:
        errors.append("canonical protocol contract must define one ProtocolEnvelope")
    if "class ProtocolEnvelope" in execution_text:
        errors.append("network execution layer defines shadow ProtocolEnvelope")
    if "from skeleton.contracts.protocol import (" not in execution_text:
        errors.append("network execution layer is not bound to canonical protocol")
    if "class ProtocolExecutionEnvelope" not in execution_text:
        errors.append("protocol execution wrapper missing")
    return {
        "contract_digest": _sha256(contract),
        "execution_digest": _sha256(execution),
        "single_envelope_authority": (
            contract_text.count("class ProtocolEnvelope") == 1
            and "class ProtocolEnvelope" not in execution_text
        ),
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    runtime = _load(root / RUNTIME_SCHEMAS)
    conformance = _load(root / CONFORMANCE)
    schema_registry = _load(root / SCHEMA_REGISTRY)
    compatibility = _load(root / COMPATIBILITY)
    topology = _load(root / STATE_TOPOLOGY)
    consistency = _load(root / CONSISTENCY_PROFILES)

    volume_binding = _verify_masterplan(master, errors)
    schemas = _verify_schemas(runtime, conformance, schema_registry, errors)
    compatibility_result = _verify_compatibility(
        schema_registry, compatibility, root, errors
    )
    consistency_result = _verify_consistency(
        topology, consistency, root, errors
    )
    protocol_result = _verify_protocol(root, errors)

    unique_errors = sorted(set(errors))
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol129-132-contract-consistency-v1",
        "volumes": ["VOL-129", "VOL-130", "VOL-131", "VOL-132"],
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "schemas": schemas,
        "compatibility": compatibility_result,
        "consistency": consistency_result,
        "protocol": protocol_result,
        "source_digests": {
            path.as_posix(): _sha256(root / path)
            for path in (
                RUNTIME_SCHEMAS,
                CONFORMANCE,
                SCHEMA_REGISTRY,
                COMPATIBILITY,
                STATE_TOPOLOGY,
                CONSISTENCY_PROFILES,
            )
        },
        "errors": unique_errors,
        "valid": not unique_errors,
    }
    receipt["receipt_digest"] = _receipt_digest(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol129-132-contract-consistency-v1",
            "volumes": ["VOL-129", "VOL-130", "VOL-131", "VOL-132"],
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _receipt_digest(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-129/130/131/132 independent verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-129/130/131/132 independent verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
