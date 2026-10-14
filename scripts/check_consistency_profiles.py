#!/usr/bin/env python3
"""Validate VOL-132 state consistency profiles against canonical topology."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = Path("machine/state_topology.json")
PROFILES = Path("machine/consistency_profiles.json")
RUNTIME = Path("skeleton/persistence/consistency.py")
MIRROR = Path("skeleton/ai/runtime/persistence/consistency.py")


class ConsistencyProfileError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsistencyProfileError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise ConsistencyProfileError(f"{path} must contain an object")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _guarantees(authority: str) -> dict[str, str]:
    if authority in {"authoritative", "conditional-authoritative"}:
        return {
            "read_guarantee": "authoritative_committed",
            "write_guarantee": "durable_commit_ack",
            "stale_policy": "reject",
            "unknown_policy": "reject",
        }
    if authority in {"derived", "durable-projection"}:
        return {
            "read_guarantee": "eventual_projection",
            "write_guarantee": "source_first_then_project",
            "stale_policy": "explicit_only",
            "unknown_policy": "reject",
        }
    if authority == "scratch":
        return {
            "read_guarantee": "best_effort_scratch",
            "write_guarantee": "non_authoritative_recomputable",
            "stale_policy": "explicit_only",
            "unknown_policy": "reject",
        }
    if authority == "recovery-aid":
        return {
            "read_guarantee": "recovery_aid_only",
            "write_guarantee": "recovery_aid_no_authority",
            "stale_policy": "reject",
            "unknown_policy": "reject",
        }
    raise ConsistencyProfileError(f"unsupported state authority: {authority}")


def _expected(domain: Mapping[str, Any]) -> dict[str, Any]:
    authority = domain.get("authority")
    if not isinstance(authority, str):
        raise ConsistencyProfileError("state domain lacks authority")
    derived_from = domain.get("derived_from", [])
    evidence = domain.get("evidence", [])
    if not isinstance(derived_from, list) or not all(
        isinstance(item, str) and item for item in derived_from
    ):
        raise ConsistencyProfileError(
            f"{domain.get('id')} has malformed derived_from"
        )
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) and item for item in evidence
    ):
        raise ConsistencyProfileError(
            f"{domain.get('id')} has malformed evidence"
        )
    return {
        "schema_version": 1,
        "domain_id": domain.get("id"),
        "owner_plane": domain.get("owner_plane"),
        "physical_store": domain.get("physical_store"),
        "authority": authority,
        "source_of_truth": domain.get("source_of_truth"),
        **_guarantees(authority),
        "source_refs": list(derived_from),
        "max_staleness_ms": None,
        "consistency_statement": domain.get("consistency"),
        "evidence": list(evidence),
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    topology = _load(root / TOPOLOGY)
    registry = _load(root / PROFILES)

    if registry.get("schema_version") != "skeleton.state.consistency_profiles.v1":
        raise ConsistencyProfileError("consistency profile schema drift")
    if registry.get("status") != "active":
        raise ConsistencyProfileError("consistency profile registry must be active")
    binding = registry.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise ConsistencyProfileError("VOL-132 masterplan binding missing")
    if binding.get("volume_ref") != "VOL-132":
        raise ConsistencyProfileError("consistency profile volume binding drift")
    if set(binding.get("required_gap_texts") or []) != {
        "classify state domains",
        "bind guarantees to stores",
    }:
        raise ConsistencyProfileError("VOL-132 gap binding drift")

    source = registry.get("sources")
    if not isinstance(source, dict):
        raise ConsistencyProfileError("consistency profile sources missing")
    topology_source = source.get("state_topology")
    if not isinstance(topology_source, dict):
        raise ConsistencyProfileError("state-topology source binding missing")
    if topology_source.get("path") != TOPOLOGY.as_posix():
        raise ConsistencyProfileError("state-topology path binding drift")
    expected_sha = _git_blob_sha(root / TOPOLOGY)
    if topology_source.get("git_blob_sha") != expected_sha:
        raise ConsistencyProfileError(
            "consistency profiles bind stale state-topology Git blob"
        )

    runtime = root / RUNTIME
    mirror = root / MIRROR
    if not runtime.is_file() or not mirror.is_file():
        raise ConsistencyProfileError("consistency runtime/mirror missing")
    if runtime.read_bytes() != mirror.read_bytes():
        raise ConsistencyProfileError("consistency runtime AI mirror drift")
    source_text = runtime.read_text(encoding="utf-8")
    for token in (
        "class ConsistencyProfile",
        "class ReadObservation",
        "class ConsistencyDecision",
        "class ReadGuarantee",
        "class WriteGuarantee",
        "class FreshnessState",
        "def evaluate_read(",
        "def require_readable(",
        "state freshness is unknown; fail closed",
        "stale state requires an explicit projection policy and caller opt-in",
        "authoritative profile cannot serve stale reads",
        "projection writes must be source-first",
    ):
        if token not in source_text:
            raise ConsistencyProfileError(
                f"consistency runtime invariant missing: {token}"
            )

    domains = topology.get("state_domains")
    stores = topology.get("physical_stores")
    if not isinstance(domains, list) or not domains:
        raise ConsistencyProfileError("state topology domains missing")
    if not isinstance(stores, list) or not stores:
        raise ConsistencyProfileError("state topology stores missing")
    store_ids = {
        item.get("id")
        for item in stores
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    ids = [
        item.get("id")
        for item in domains
        if isinstance(item, dict)
    ]
    if len(ids) != len(set(ids)):
        raise ConsistencyProfileError("duplicate state domain ID")
    for domain in domains:
        if not isinstance(domain, dict):
            raise ConsistencyProfileError("state domain must be an object")
        if domain.get("physical_store") not in store_ids:
            raise ConsistencyProfileError(
                f"{domain.get('id')} references unknown physical store"
            )

    expected = [_expected(domain) for domain in domains]
    actual = registry.get("profiles")
    if actual != expected:
        expected_by_id = {item["domain_id"]: item for item in expected}
        actual_by_id = {
            item.get("domain_id"): item
            for item in actual or []
            if isinstance(item, dict)
        }
        first = next(
            (
                domain_id
                for domain_id, profile in expected_by_id.items()
                if actual_by_id.get(domain_id) != profile
            ),
            None,
        )
        raise ConsistencyProfileError(
            f"consistency profile derivation drift at {first}"
        )
    if registry.get("profile_count") != len(expected):
        raise ConsistencyProfileError("consistency profile_count drift")

    authoritative = sum(
        1 for item in expected
        if item["authority"] in {"authoritative", "conditional-authoritative"}
    )
    projections = sum(
        1 for item in expected
        if item["authority"] in {"derived", "durable-projection"}
    )
    scratch = sum(1 for item in expected if item["authority"] == "scratch")
    recovery = sum(1 for item in expected if item["authority"] == "recovery-aid")
    if authoritative <= 0 or projections <= 0:
        raise ConsistencyProfileError(
            "consistency registry lacks authority/projection coverage"
        )

    return {
        "status": "valid",
        "profile_count": len(expected),
        "authoritative_profile_count": authoritative,
        "projection_profile_count": projections,
        "scratch_profile_count": scratch,
        "recovery_aid_profile_count": recovery,
        "state_topology_git_blob_sha": expected_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ConsistencyProfileError as exc:
        print(f"consistency profiles: FAIL: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "consistency profiles: OK "
            f"({result['profile_count']} domains; "
            f"{result['authoritative_profile_count']} authoritative; "
            f"{result['projection_profile_count']} projections)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
