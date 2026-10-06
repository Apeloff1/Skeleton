#!/usr/bin/env python3
"""Independent source-only verifier for VOL-005 state/migration closure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise VerificationError("invalid repository path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise VerificationError("invalid repository path")
    if pure.as_posix() != value:
        raise VerificationError("non-canonical repository path")
    return value


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify(root: Path, *, head_sha: str) -> dict[str, Any]:
    root = root.resolve()
    if not SHA40.fullmatch(head_sha):
        raise VerificationError("head_sha must be a full lowercase git SHA")

    topology_path = root / "machine/state_topology.json"
    qualification_path = root / "machine/state_migration_qualification.json"
    construction_path = root / "machine/ai_app_construction.json"
    master_path = root / "machine/ai_master_plan.json"

    topology = _json(topology_path)
    qualification = _json(qualification_path)
    construction = _json(construction_path)
    master = _json(master_path)

    topology_blob = _blob_sha(topology_path.read_bytes())
    if qualification.get("topology_blob_sha") != topology_blob:
        raise VerificationError("qualification topology blob is stale")

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
    if len(stores) != len(topology.get("physical_stores", [])):
        raise VerificationError("physical store identities are not unique")
    if len(domains) != len(topology.get("state_domains", [])):
        raise VerificationError("state domain identities are not unique")

    retired = {
        "verification-evidence-unbound": "verification-receipt-ledger",
        "engine-mongo-state": "canonical-ai-memory-records",
    }
    for retired_id, replacement in retired.items():
        if retired_id in stores or retired_id in domains:
            raise VerificationError(f"retired authority remains active: {retired_id}")
        if replacement not in domains:
            raise VerificationError(
                f"retired authority replacement is absent: {replacement}"
            )

    store_consumers = {store_id: [] for store_id in stores}
    placeholder_tokens = (
        "declared-partial",
        "partial",
        "planned",
        "future",
        "unbound",
        "placeholder",
        "transitional",
    )
    source_domains: set[str] = set()
    for domain_id, domain in domains.items():
        store_id = domain.get("physical_store")
        if store_id not in stores:
            raise VerificationError(
                f"{domain_id} references unknown physical store {store_id!r}"
            )
        store_consumers[store_id].append(domain_id)
        if domain.get("source_of_truth") is True:
            source_domains.add(domain_id)
            status = str(domain.get("status", "")).casefold()
            if any(token in status for token in placeholder_tokens):
                raise VerificationError(
                    f"{domain_id} retains placeholder source-of-truth status"
                )
            refs = domain.get("evidence")
            if not isinstance(refs, list) or len(refs) < 2:
                raise VerificationError(
                    f"{domain_id} lacks materialized authority evidence"
                )
            for ref in refs:
                path = _path(ref)
                if ref.startswith("planned:") or not (root / path).exists():
                    raise VerificationError(
                        f"{domain_id} authority evidence is not materialized: {ref}"
                    )

    unused = sorted(
        store_id for store_id, consumers in store_consumers.items() if not consumers
    )
    if unused:
        raise VerificationError(
            "ghost physical stores remain: " + ", ".join(unused)
        )

    entries = qualification.get("domain_qualification")
    if not isinstance(entries, list):
        raise VerificationError("domain qualification matrix is missing")
    coverage: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise VerificationError("domain qualification entry is not an object")
        domain_id = entry.get("domain_id")
        if (
            not isinstance(domain_id, str)
            or domain_id not in domains
            or domain_id in coverage
        ):
            raise VerificationError(
                f"unknown/duplicate qualification domain: {domain_id!r}"
            )
        coverage[domain_id] = entry
        domain = domains[domain_id]
        for field in ("authority", "source_of_truth", "physical_store"):
            if entry.get(field) != domain.get(field):
                raise VerificationError(
                    f"{domain_id} qualification drifts on {field}"
                )
        if entry.get("migration_contract") != domain.get("migration"):
            raise VerificationError(
                f"{domain_id} migration contract is not source-bound"
            )
        if entry.get("backup_restore_contract") != domain.get("backup_restore"):
            raise VerificationError(
                f"{domain_id} restore contract is not source-bound"
            )
        refs = entry.get("evidence_refs")
        if refs != domain.get("evidence"):
            raise VerificationError(
                f"{domain_id} qualification evidence does not exactly match topology"
            )
    if set(coverage) != set(domains):
        raise VerificationError("domain qualification coverage is not exact")

    scenarios = qualification.get("executable_scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise VerificationError("executable scenarios are missing")
    scenario_ids: set[str] = set()
    scenario_source_domains: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise VerificationError("scenario must be an object")
        scenario_id = scenario.get("id")
        if (
            not isinstance(scenario_id, str)
            or not scenario_id
            or scenario_id in scenario_ids
        ):
            raise VerificationError("scenario identity is invalid/duplicate")
        scenario_ids.add(scenario_id)
        refs = scenario.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise VerificationError(f"{scenario_id} evidence is missing")
        for ref in refs:
            path = _path(ref)
            if ref.startswith("planned:") or not (root / path).exists():
                raise VerificationError(
                    f"{scenario_id} evidence does not materialize: {ref}"
                )
        for domain_id in scenario.get("domains", []):
            if domain_id not in domains:
                raise VerificationError(
                    f"{scenario_id} references unknown domain {domain_id}"
                )
            if domain_id in source_domains:
                scenario_source_domains.add(domain_id)
    if scenario_source_domains != source_domains:
        raise VerificationError(
            "source-of-truth scenario coverage is incomplete: "
            + ", ".join(sorted(source_domains - scenario_source_domains))
        )

    gate = qualification.get("release_gate")
    if not isinstance(gate, dict):
        raise VerificationError("release gate is missing")
    construction_gates = [
        item
        for item in construction.get("acceptance_gates", [])
        if isinstance(item, dict) and item.get("id") == "state-migration-qualification"
    ]
    expected_gate = {
        "id": "state-migration-qualification",
        "kind": "release",
        "command": "python scripts/check_state_migration_qualification.py --json",
        "required": True,
    }
    if len(construction_gates) != 1 or construction_gates[0] != expected_gate:
        raise VerificationError(
            "construction does not require exact state migration qualification gate"
        )
    if gate.get("failure_policy") != "fail-closed":
        raise VerificationError("release gate is not fail-closed")

    runtime = root / _path(qualification.get("runtime"))
    mirror = root / _path(qualification.get("governed_runtime_mirror"))
    if not runtime.is_file() or not mirror.is_file():
        raise VerificationError("migration runtime/mirror is missing")
    if runtime.read_bytes() != mirror.read_bytes():
        raise VerificationError("migration runtime mirror is not byte-identical")

    required_tests = qualification.get("required_release_tests")
    if not isinstance(required_tests, list) or not required_tests:
        raise VerificationError("required release test inventory is missing")
    for ref in required_tests:
        path = _path(ref)
        if not (root / path).is_file():
            raise VerificationError(f"required release test is missing: {path}")

    volume = next(
        (
            item
            for item in master.get("volumes", [])
            if isinstance(item, dict) and item.get("key") == "VOL-005"
        ),
        None,
    )
    if not isinstance(volume, dict):
        raise VerificationError("VOL-005 is absent from masterplan")
    if volume.get("completion_checkbox") is True:
        raise VerificationError(
            "independent verifier refuses pre-signed VOL-005 completion"
        )

    evidence_payload = {
        "head_sha": head_sha,
        "topology_blob_sha": topology_blob,
        "physical_stores": sorted(stores),
        "state_domains": sorted(domains),
        "source_of_truth_domains": sorted(source_domains),
        "retired": retired,
        "scenario_ids": sorted(scenario_ids),
        "release_gate": expected_gate,
        "runtime_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
        "required_tests": sorted(required_tests),
    }
    return {
        "schema_version": 1,
        "verifier": "independent-vol005-state-migration-v1",
        "head_sha": head_sha,
        "valid": True,
        "physical_store_count": len(stores),
        "state_domain_count": len(domains),
        "source_of_truth_domain_count": len(source_domains),
        "scenario_count": len(scenario_ids),
        "topology_blob_sha": topology_blob,
        "authority_digest": _digest(evidence_payload),
        "evidence": evidence_payload,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify(Path(args.repo_root), head_sha=args.head_sha)
    except VerificationError as exc:
        print(f"independent-vol005-state-migration: FAIL: {exc}", file=sys.stderr)
        return 1
    serialized = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.evidence_out:
        Path(args.evidence_out).write_text(serialized, encoding="utf-8")
    if args.print_evidence:
        print(serialized, end="")
    else:
        print(
            "independent-vol005-state-migration: OK "
            f"(head={receipt['head_sha'][:12]}; "
            f"domains={receipt['state_domain_count']}; "
            f"authority={receipt['authority_digest']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
