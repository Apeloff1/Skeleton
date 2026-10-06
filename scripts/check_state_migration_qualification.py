#!/usr/bin/env python3
"""Fail-closed VOL-005 migration/release qualification validator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = Path("machine/state_migration_qualification.json")
TOPOLOGY = Path("machine/state_topology.json")
CONSTRUCTION = Path("machine/ai_app_construction.json")
BACKUP_POLICY = Path("machine/state_backup_policy.json")


class StateMigrationQualificationError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    try:
        raw = (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        raise StateMigrationQualificationError(
            f"missing required contract: {relative}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateMigrationQualificationError(
            f"invalid JSON in {relative}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise StateMigrationQualificationError(f"{relative} must be an object")
    return payload


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise StateMigrationQualificationError("path must be normalized repository text")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise StateMigrationQualificationError("path must be repository relative")
    if pure.as_posix() != value:
        raise StateMigrationQualificationError("path must use canonical POSIX spelling")
    return value


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _require_materialized_refs(
    root: Path,
    refs: object,
    *,
    label: str,
) -> tuple[str, ...]:
    if not isinstance(refs, list) or not refs:
        raise StateMigrationQualificationError(f"{label} must be non-empty")
    normalized: list[str] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            raise StateMigrationQualificationError(
                f"{label}[{index}] must be non-empty text"
            )
        if ref.startswith("planned:"):
            raise StateMigrationQualificationError(
                f"{label}[{index}] cannot be planned evidence"
            )
        path = _path(ref)
        if not (root / path).exists():
            raise StateMigrationQualificationError(
                f"{label}[{index}] does not materialize: {path}"
            )
        normalized.append(path)
    if len(normalized) != len(set(normalized)):
        raise StateMigrationQualificationError(f"{label} contains duplicates")
    return tuple(normalized)


def _validate_runtime(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    runtime = _path(manifest.get("runtime"))
    mirror = _path(manifest.get("governed_runtime_mirror"))
    runtime_path = root / runtime
    mirror_path = root / mirror
    if not runtime_path.is_file() or not mirror_path.is_file():
        raise StateMigrationQualificationError(
            "migration runtime canonical/mirror path is missing"
        )
    if runtime_path.read_bytes() != mirror_path.read_bytes():
        raise StateMigrationQualificationError(
            "migration compatibility governed mirror drifted"
        )

    # Import only after source parity is established.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from skeleton.persistence.migration_compatibility import reference_rehearsal

    receipt = reference_rehearsal()
    if not receipt.qualified:
        raise StateMigrationQualificationError(
            "reference migration rehearsal did not qualify"
        )
    if len(receipt.receipt_digest) != 64:
        raise StateMigrationQualificationError(
            "reference migration receipt digest is invalid"
        )
    return receipt.as_dict()


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load(root, QUALIFICATION)
    topology = _load(root, TOPOLOGY)
    construction = _load(root, CONSTRUCTION)
    _load(root, BACKUP_POLICY)

    if manifest.get("schema_version") != 1:
        raise StateMigrationQualificationError("qualification schema_version must equal 1")
    if manifest.get("status") != "active":
        raise StateMigrationQualificationError("qualification contract must be active")
    if manifest.get("topology_contract") != TOPOLOGY.as_posix():
        raise StateMigrationQualificationError("topology contract path drifted")
    if manifest.get("backup_policy") != BACKUP_POLICY.as_posix():
        raise StateMigrationQualificationError("backup policy path drifted")
    if manifest.get("construction_contract") != CONSTRUCTION.as_posix():
        raise StateMigrationQualificationError("construction contract path drifted")
    if manifest.get("validator") != "scripts/check_state_migration_qualification.py":
        raise StateMigrationQualificationError("qualification validator path drifted")

    topology_bytes = (root / TOPOLOGY).read_bytes()
    actual_topology_blob = _git_blob_sha(topology_bytes)
    if manifest.get("topology_blob_sha") != actual_topology_blob:
        raise StateMigrationQualificationError(
            "migration qualification is stale for the current state topology "
            f"(declared={manifest.get('topology_blob_sha')!r}, "
            f"actual={actual_topology_blob!r})"
        )

    policies = manifest.get("policies")
    if not isinstance(policies, dict) or not policies:
        raise StateMigrationQualificationError("qualification policies must be non-empty")
    false_policies = sorted(
        key for key, value in policies.items() if value is not True
    )
    if false_policies:
        raise StateMigrationQualificationError(
            "all migration qualification policies must be true: "
            + ", ".join(false_policies)
        )

    domains_raw = topology.get("state_domains")
    if not isinstance(domains_raw, list) or not domains_raw:
        raise StateMigrationQualificationError("state topology domains are missing")
    domains = {
        item["id"]: item
        for item in domains_raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(domains) != len(domains_raw):
        raise StateMigrationQualificationError(
            "state topology domains must have unique stable ids"
        )

    entries = manifest.get("domain_qualification")
    if not isinstance(entries, list) or not entries:
        raise StateMigrationQualificationError(
            "domain_qualification must be non-empty"
        )
    by_domain: dict[str, dict[str, Any]] = {}
    mode_counts: dict[str, int] = {}
    for index, entry in enumerate(entries):
        label = f"domain_qualification[{index}]"
        if not isinstance(entry, dict):
            raise StateMigrationQualificationError(f"{label} must be an object")
        domain_id = entry.get("domain_id")
        if (
            not isinstance(domain_id, str)
            or domain_id not in domains
            or domain_id in by_domain
        ):
            raise StateMigrationQualificationError(
                f"{label} has unknown/duplicate domain {domain_id!r}"
            )
        by_domain[domain_id] = entry
        domain = domains[domain_id]
        for field in ("authority", "source_of_truth", "physical_store"):
            if entry.get(field) != domain.get(field):
                raise StateMigrationQualificationError(
                    f"{domain_id} qualification {field} drifted from topology"
                )
        if entry.get("migration_contract") != domain.get("migration"):
            raise StateMigrationQualificationError(
                f"{domain_id} migration contract drifted from topology"
            )
        if entry.get("backup_restore_contract") != domain.get("backup_restore"):
            raise StateMigrationQualificationError(
                f"{domain_id} backup/restore contract drifted from topology"
            )
        if entry.get("release_required") is not True:
            raise StateMigrationQualificationError(
                f"{domain_id} must be release-qualified"
            )
        mode = entry.get("qualification_mode")
        if not isinstance(mode, str) or not mode:
            raise StateMigrationQualificationError(
                f"{domain_id} qualification mode must be non-empty"
            )
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        for field in ("mixed_version_policy", "rollback_policy"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise StateMigrationQualificationError(
                    f"{domain_id}.{field} must be non-empty"
                )
        refs = _require_materialized_refs(
            root,
            entry.get("evidence_refs"),
            label=f"{domain_id}.evidence_refs",
        )
        topology_refs = domain.get("evidence")
        if set(refs) != set(topology_refs or []):
            raise StateMigrationQualificationError(
                f"{domain_id} evidence set must exactly match state topology"
            )

        if domain.get("source_of_truth") is True:
            if mode != "authoritative-migrate-rollback-restore":
                raise StateMigrationQualificationError(
                    f"{domain_id} source-of-truth requires authoritative migration mode"
                )
            if "exact rollback" not in entry.get("rollback_policy", ""):
                raise StateMigrationQualificationError(
                    f"{domain_id} source-of-truth must require exact rollback/compensation"
                )
        elif mode == "authoritative-migrate-rollback-restore":
            raise StateMigrationQualificationError(
                f"{domain_id} non-authoritative state cannot claim authoritative mode"
            )

    if set(by_domain) != set(domains):
        missing = sorted(set(domains) - set(by_domain))
        extra = sorted(set(by_domain) - set(domains))
        raise StateMigrationQualificationError(
            f"domain qualification coverage mismatch missing={missing} extra={extra}"
        )

    retired = manifest.get("retired_legacy_authorities")
    if not isinstance(retired, list) or not retired:
        raise StateMigrationQualificationError(
            "retired_legacy_authorities must be non-empty"
        )
    store_ids = {
        item.get("id")
        for item in topology.get("physical_stores", [])
        if isinstance(item, dict)
    }
    for item in retired:
        if not isinstance(item, dict):
            raise StateMigrationQualificationError(
                "retired legacy authority entry must be an object"
            )
        retired_id = item.get("id")
        replacement = item.get("replacement_domain")
        if retired_id in domains or retired_id in store_ids:
            raise StateMigrationQualificationError(
                f"retired legacy authority {retired_id} remains active"
            )
        if replacement not in domains:
            raise StateMigrationQualificationError(
                f"retired authority {retired_id} replacement is missing"
            )
        if item.get("disposition") != "retired":
            raise StateMigrationQualificationError(
                f"retired authority {retired_id} disposition must be retired"
            )

    scenarios = manifest.get("executable_scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise StateMigrationQualificationError(
            "executable_scenarios must be non-empty"
        )
    scenario_ids: set[str] = set()
    authoritative_scenario_domains: set[str] = set()
    for index, scenario in enumerate(scenarios):
        label = f"executable_scenarios[{index}]"
        if not isinstance(scenario, dict):
            raise StateMigrationQualificationError(f"{label} must be an object")
        scenario_id = scenario.get("id")
        if (
            not isinstance(scenario_id, str)
            or not scenario_id
            or scenario_id in scenario_ids
        ):
            raise StateMigrationQualificationError(
                f"{label}.id is invalid/duplicate"
            )
        scenario_ids.add(scenario_id)
        scenario_domains = scenario.get("domains")
        if not isinstance(scenario_domains, list) or not scenario_domains:
            raise StateMigrationQualificationError(
                f"{scenario_id}.domains must be non-empty"
            )
        for domain_id in scenario_domains:
            if domain_id not in domains:
                raise StateMigrationQualificationError(
                    f"{scenario_id} references unknown domain {domain_id!r}"
                )
            if domains[domain_id].get("source_of_truth") is True:
                authoritative_scenario_domains.add(domain_id)
        if not isinstance(scenario.get("kind"), str) or not scenario["kind"]:
            raise StateMigrationQualificationError(
                f"{scenario_id}.kind must be non-empty"
            )
        if not isinstance(scenario.get("command"), str) or not scenario["command"]:
            raise StateMigrationQualificationError(
                f"{scenario_id}.command must be non-empty"
            )
        _require_materialized_refs(
            root,
            scenario.get("evidence_refs"),
            label=f"{scenario_id}.evidence_refs",
        )

    source_domains = {
        domain_id
        for domain_id, item in domains.items()
        if item.get("source_of_truth") is True
    }
    if authoritative_scenario_domains != source_domains:
        missing = sorted(source_domains - authoritative_scenario_domains)
        extra = sorted(authoritative_scenario_domains - source_domains)
        raise StateMigrationQualificationError(
            "executable scenario coverage for source-of-truth domains is incomplete "
            f"missing={missing} extra={extra}"
        )

    release_gate = manifest.get("release_gate")
    if not isinstance(release_gate, dict):
        raise StateMigrationQualificationError("release_gate must be an object")
    gates = construction.get("acceptance_gates")
    if not isinstance(gates, list):
        raise StateMigrationQualificationError(
            "construction acceptance_gates must be a list"
        )
    matches = [
        gate for gate in gates
        if isinstance(gate, dict) and gate.get("id") == release_gate.get("id")
    ]
    if len(matches) != 1 or matches[0] != {
        "id": release_gate.get("id"),
        "kind": release_gate.get("kind"),
        "command": release_gate.get("command"),
        "required": release_gate.get("required"),
    }:
        raise StateMigrationQualificationError(
            "construction acceptance gate does not exactly bind migration qualification"
        )
    if release_gate.get("failure_policy") != "fail-closed":
        raise StateMigrationQualificationError(
            "migration release gate failure policy must be fail-closed"
        )

    required_tests = _require_materialized_refs(
        root,
        manifest.get("required_release_tests"),
        label="required_release_tests",
    )
    receipt = _validate_runtime(root, manifest)

    return {
        "status": "valid",
        "topology_blob_sha": actual_topology_blob,
        "domain_count": len(domains),
        "source_of_truth_domain_count": len(source_domains),
        "scenario_count": len(scenarios),
        "qualification_modes": dict(sorted(mode_counts.items())),
        "required_release_tests": list(required_tests),
        "reference_rehearsal": receipt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(Path(args.repo_root))
    except StateMigrationQualificationError as exc:
        print(f"state-migration-qualification: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "state-migration-qualification: OK "
            f"(domains={result['domain_count']}; "
            f"authoritative={result['source_of_truth_domain_count']}; "
            f"scenarios={result['scenario_count']}; "
            f"topology={result['topology_blob_sha']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
