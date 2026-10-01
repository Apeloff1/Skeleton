#!/usr/bin/env python3
"""Validate the canonical architecture rule registry and bounded waivers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/architecture_rule_registry.json")
ARCHITECTURE_PATH = Path("machine/architecture.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")

_RULE_ID = re.compile(r"^ARCH-[A-Z0-9-]+$")
_WAIVER_ID = re.compile(r"^ARCH-WAIVER-[0-9]{4,}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_SIGNATURE_METHODS = {
    "github_identity",
    "git_gpg",
    "git_ssh",
    "sigstore",
    "ci_oidc",
}


class ArchitectureRuleRegistryError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchitectureRuleRegistryError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ArchitectureRuleRegistryError(
            f"invalid JSON in {relative}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise ArchitectureRuleRegistryError(f"{relative} must contain a JSON object")
    return data


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ArchitectureRuleRegistryError("path must be a non-empty POSIX repository path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ArchitectureRuleRegistryError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise ArchitectureRuleRegistryError(f"non-canonical repository path: {value!r}")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ArchitectureRuleRegistryError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ArchitectureRuleRegistryError(f"{field} is invalid RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ArchitectureRuleRegistryError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _discover_validator_paths(root: Path) -> set[str]:
    scripts = root / "scripts"
    discovered = {
        path.relative_to(root).as_posix()
        for path in scripts.glob("check_architecture*.py")
        if path.is_file()
    }
    discovered.update(
        {
            "scripts/check_ai_file_tree.py",
            "scripts/check_ai_scope_freeze.py",
        }
    )
    return discovered


def validate(root: Path = ROOT, *, as_of: datetime | None = None, execute: bool = False) -> dict[str, Any]:
    root = root.resolve()
    registry = _load(root, REGISTRY_PATH)
    architecture = _load(root, ARCHITECTURE_PATH)
    master = _load(root, MASTER_PLAN_PATH)
    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if registry.get("status") != "active":
        raise ArchitectureRuleRegistryError("architecture rule registry must be active")

    canonical_roots = architecture.get("canonical_roots")
    zones = architecture.get("zones")
    if not isinstance(canonical_roots, list) or not canonical_roots:
        raise ArchitectureRuleRegistryError("machine/architecture.json has no canonical roots")
    if not isinstance(zones, list) or not zones:
        raise ArchitectureRuleRegistryError("machine/architecture.json has no zones")
    root_ids = {item.get("id") for item in canonical_roots if isinstance(item, dict)}
    zone_ids = {item.get("id") for item in zones if isinstance(item, dict)}

    volumes = {
        item.get("key"): item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    bindings = registry.get("masterplan_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ArchitectureRuleRegistryError("masterplan_bindings must be a non-empty list")
    binding_refs: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ArchitectureRuleRegistryError("masterplan binding must be an object")
        ref = binding.get("volume_ref")
        if ref in binding_refs:
            raise ArchitectureRuleRegistryError(f"duplicate masterplan binding: {ref}")
        binding_refs.add(ref)
        volume = volumes.get(ref)
        if not isinstance(volume, dict):
            raise ArchitectureRuleRegistryError(f"unknown masterplan volume binding: {ref}")
        if binding.get("title") != volume.get("title"):
            raise ArchitectureRuleRegistryError(f"masterplan title drift for {ref}")
        gap_texts = binding.get("required_gap_texts")
        if not isinstance(gap_texts, list) or not gap_texts:
            raise ArchitectureRuleRegistryError(f"{ref} required_gap_texts must be non-empty")
        canonical_gaps = volume.get("gaps", [])
        for gap in gap_texts:
            if gap not in canonical_gaps:
                raise ArchitectureRuleRegistryError(
                    f"registry no longer matches canonical masterplan gap {ref}: {gap!r}"
                )
    if binding_refs != {"VOL-055", "VOL-116"}:
        raise ArchitectureRuleRegistryError(
            "architecture rule registry must remain bound to VOL-055 and VOL-116"
        )

    rules = registry.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ArchitectureRuleRegistryError("rules must be a non-empty list")
    rule_ids: set[str] = set()
    validator_paths: set[str] = set()
    rules_by_id: dict[str, dict[str, Any]] = {}

    for raw in rules:
        if not isinstance(raw, dict):
            raise ArchitectureRuleRegistryError("rule must be an object")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
            raise ArchitectureRuleRegistryError(f"invalid architecture rule id: {rule_id!r}")
        if rule_id in rule_ids:
            raise ArchitectureRuleRegistryError(f"duplicate architecture rule id: {rule_id}")
        rule_ids.add(rule_id)
        rules_by_id[rule_id] = raw

        if not isinstance(raw.get("title"), str) or not raw["title"].strip():
            raise ArchitectureRuleRegistryError(f"{rule_id} requires a title")
        if raw.get("severity") != "blocking":
            raise ArchitectureRuleRegistryError(f"{rule_id} must remain blocking")
        if raw.get("change_requires_adr") is not True:
            raise ArchitectureRuleRegistryError(f"{rule_id} changes must require an ADR")

        validator_path = _repo_path(raw.get("validator_path"))
        if validator_path in validator_paths:
            raise ArchitectureRuleRegistryError(
                f"validator registered more than once: {validator_path}"
            )
        validator_paths.add(validator_path)
        if not (root / validator_path).is_file():
            raise ArchitectureRuleRegistryError(
                f"{rule_id} validator path does not exist: {validator_path}"
            )
        if raw.get("command") != ["python", validator_path]:
            raise ArchitectureRuleRegistryError(
                f"{rule_id} command must execute its registered validator directly"
            )

        owners = raw.get("owner_root_ids")
        if not isinstance(owners, list) or not owners:
            raise ArchitectureRuleRegistryError(f"{rule_id} requires canonical owner_root_ids")
        if len(owners) != len(set(owners)):
            raise ArchitectureRuleRegistryError(f"{rule_id} owner_root_ids contain duplicates")
        unknown_owners = sorted(set(owners) - root_ids)
        if unknown_owners:
            raise ArchitectureRuleRegistryError(
                f"{rule_id} references unknown canonical roots: {unknown_owners}"
            )

        affected = raw.get("affected_zone_ids")
        if not isinstance(affected, list) or not affected:
            raise ArchitectureRuleRegistryError(f"{rule_id} requires affected_zone_ids")
        if len(affected) != len(set(affected)):
            raise ArchitectureRuleRegistryError(f"{rule_id} affected_zone_ids contain duplicates")
        unknown_zones = sorted(set(affected) - zone_ids)
        if unknown_zones:
            raise ArchitectureRuleRegistryError(
                f"{rule_id} references unknown architecture zones: {unknown_zones}"
            )

        policy = raw.get("waiver_policy")
        if not isinstance(policy, dict):
            raise ArchitectureRuleRegistryError(f"{rule_id} requires waiver_policy")
        if policy.get("require_adr") is not True:
            raise ArchitectureRuleRegistryError(f"{rule_id} waiver policy must require ADR")
        allowed = policy.get("allowed")
        ttl = policy.get("max_ttl_days")
        if allowed is True:
            if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 90:
                raise ArchitectureRuleRegistryError(
                    f"{rule_id} allowed waiver requires max_ttl_days in 1..90"
                )
        elif allowed is False:
            if ttl is not None:
                raise ArchitectureRuleRegistryError(
                    f"{rule_id} non-waivable rule must have null max_ttl_days"
                )
        else:
            raise ArchitectureRuleRegistryError(f"{rule_id} waiver allowed must be boolean")

    discovered = _discover_validator_paths(root)
    if validator_paths != discovered:
        missing = sorted(discovered - validator_paths)
        stale = sorted(validator_paths - discovered)
        raise ArchitectureRuleRegistryError(
            f"architecture validator registry coverage drift; missing={missing}, stale={stale}"
        )

    waivers = registry.get("waivers")
    if not isinstance(waivers, list):
        raise ArchitectureRuleRegistryError("waivers must be a list")
    waiver_ids: set[str] = set()
    for waiver in waivers:
        if not isinstance(waiver, dict):
            raise ArchitectureRuleRegistryError("waiver must be an object")
        waiver_id = waiver.get("id")
        if not isinstance(waiver_id, str) or not _WAIVER_ID.fullmatch(waiver_id):
            raise ArchitectureRuleRegistryError(f"invalid waiver id: {waiver_id!r}")
        if waiver_id in waiver_ids:
            raise ArchitectureRuleRegistryError(f"duplicate waiver id: {waiver_id}")
        waiver_ids.add(waiver_id)

        rule_id = waiver.get("rule_id")
        rule = rules_by_id.get(rule_id)
        if rule is None:
            raise ArchitectureRuleRegistryError(
                f"{waiver_id} references unknown rule: {rule_id!r}"
            )
        policy = rule["waiver_policy"]
        if policy.get("allowed") is not True:
            raise ArchitectureRuleRegistryError(f"{waiver_id} targets non-waivable rule {rule_id}")

        created = _utc(waiver.get("created_at_utc"), f"{waiver_id}.created_at_utc")
        expires = _utc(waiver.get("expires_at_utc"), f"{waiver_id}.expires_at_utc")
        if expires <= created:
            raise ArchitectureRuleRegistryError(f"{waiver_id} must expire after creation")
        lifetime_seconds = (expires - created).total_seconds()
        if lifetime_seconds > policy["max_ttl_days"] * 86400:
            raise ArchitectureRuleRegistryError(
                f"{waiver_id} exceeds {rule_id} max waiver TTL"
            )
        if now >= expires:
            raise ArchitectureRuleRegistryError(f"{waiver_id} is expired")

        adr_path = _repo_path(waiver.get("adr_path"))
        if not adr_path.startswith("docs/"):
            raise ArchitectureRuleRegistryError(f"{waiver_id} ADR must live under docs/")
        if not (root / adr_path).is_file():
            raise ArchitectureRuleRegistryError(f"{waiver_id} ADR document is missing")
        if not isinstance(waiver.get("reason"), str) or not waiver["reason"].strip():
            raise ArchitectureRuleRegistryError(f"{waiver_id} requires a reason")
        if not isinstance(waiver.get("owner_id"), str) or not waiver["owner_id"].strip():
            raise ArchitectureRuleRegistryError(f"{waiver_id} requires owner_id")
        if not isinstance(waiver.get("approved_by"), str) or not waiver["approved_by"].strip():
            raise ArchitectureRuleRegistryError(f"{waiver_id} requires approved_by")
        if waiver.get("owner_id") == waiver.get("approved_by"):
            raise ArchitectureRuleRegistryError(
                f"{waiver_id} approval must be independent from waiver owner"
            )
        if not _SHA.fullmatch(str(waiver.get("git_sha", ""))):
            raise ArchitectureRuleRegistryError(f"{waiver_id} requires full git_sha")
        evidence = waiver.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            raise ArchitectureRuleRegistryError(f"{waiver_id} requires evidence_refs")
        if waiver.get("signature_method") not in _ALLOWED_SIGNATURE_METHODS:
            raise ArchitectureRuleRegistryError(
                f"{waiver_id} uses unsupported signature_method"
            )

    executed: list[str] = []
    if execute:
        for rule_id in sorted(rule_ids):
            rule = rules_by_id[rule_id]
            validator_path = rule["validator_path"]
            if validator_path == "scripts/check_architecture_rule_registry.py":
                continue
            command = list(rule["command"])
            if command and command[0] == "python":
                command[0] = sys.executable
            try:
                proc = subprocess.run(
                    command,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ArchitectureRuleRegistryError(
                    f"{rule_id} execution failed to start/finish: {exc}"
                ) from exc
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                if len(detail) > 4000:
                    detail = detail[-4000:]
                raise ArchitectureRuleRegistryError(
                    f"{rule_id} validator failed with exit {proc.returncode}: {detail}"
                )
            executed.append(rule_id)

    return {
        "status": "valid",
        "rule_count": len(rules),
        "waiver_count": len(waivers),
        "registered_validators": sorted(validator_paths),
        "masterplan_bindings": sorted(binding_refs),
        "executed_rule_ids": executed,
        "executed_rule_count": len(executed),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--as-of",
        help="Optional RFC3339 UTC validation time; defaults to current UTC.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    as_of = _utc(args.as_of, "--as-of") if args.as_of else None
    try:
        result = validate(Path(args.repo_root), as_of=as_of, execute=args.execute)
    except ArchitectureRuleRegistryError as exc:
        print(f"architecture rule registry: FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "architecture rule registry: OK "
            f"({result['rule_count']} rules, {result['waiver_count']} waivers, "
            f"{result['executed_rule_count']} executed)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
