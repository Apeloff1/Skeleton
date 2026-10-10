#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-055 Architecture Linter.

The canonical registry validator owns execution. This verifier does not import
it; it independently binds the registry to VOL-055, checks complete validator
inventory and rule governance, and inspects the canonical waiver implementation
for bounded TTL, expiry, independent approval, evidence, and identity binding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
REGISTRY = Path("machine/architecture_rule_registry.json")
ARCHITECTURE = Path("machine/architecture.json")
VALIDATOR = Path("scripts/check_architecture_rule_registry.py")
TESTS = Path("tests/test_architecture_rule_registry.py")
VOLUME = "VOL-055"
TITLE = "Architecture Linter"
REQUIRED_GAPS = {
    "define rule registry",
    "add waiver expiry enforcement",
}
RULE_ID = re.compile(r"^ARCH-[A-Z0-9-]+$")


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


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _repo_path(value: object, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        errors.append(f"{label}: invalid repository path")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        errors.append(f"{label}: repository path must be normalized and relative")
        return None
    if pure.as_posix() != value:
        errors.append(f"{label}: repository path normalization drift")
        return None
    return value


def _volume(master: Mapping[str, Any]) -> Mapping[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise VerificationError("masterplan volumes must be a list")
    for volume in volumes:
        if isinstance(volume, dict) and volume.get("key") == VOLUME:
            return volume
    raise VerificationError(f"masterplan missing {VOLUME}")


def _verify_volume(master: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    volume = _volume(master)
    if volume.get("title") != TITLE:
        errors.append(f"{VOLUME} title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append(f"{VOLUME} scope drift")
    if volume.get("completion_checkbox") is True:
        errors.append(f"{VOLUME} cannot self-sign from implementation evidence")
    gaps = set(volume.get("gaps") or [])
    missing = sorted(REQUIRED_GAPS - gaps)
    if missing:
        errors.append(f"{VOLUME} gap binding drift: {missing}")
    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "Validate ownership zones, dependency direction, forbidden imports and manifest/path parity",
        "Emit actionable, stable diagnostics suitable for CI and local use",
        "Version rules and require explicit waivers with owner/expiry",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"{VOLUME} requirement invariant lost: {phrase}")
    return {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "gaps": sorted(gaps),
    }


def _discover_validators(root: Path) -> set[str]:
    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / "scripts").glob("check_architecture*.py")
        if path.is_file()
    }
    discovered.update(
        {
            "scripts/check_ai_file_tree.py",
            "scripts/check_ai_scope_freeze.py",
        }
    )
    return discovered


def _verify_registry(
    registry: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    if registry.get("schema_version") != "skeleton.architecture.rule_registry.v1":
        errors.append("architecture rule registry schema drift")
    if registry.get("status") != "active":
        errors.append("architecture rule registry must remain active")

    bindings = registry.get("masterplan_bindings")
    if not isinstance(bindings, list):
        errors.append("registry masterplan_bindings must be a list")
        bindings = []
    refs = {
        item.get("volume_ref")
        for item in bindings
        if isinstance(item, dict)
    }
    if refs != {"VOL-055", "VOL-116"}:
        errors.append("architecture registry volume binding set drift")
    binding = next(
        (
            item
            for item in bindings
            if isinstance(item, dict) and item.get("volume_ref") == VOLUME
        ),
        None,
    )
    if not isinstance(binding, dict):
        errors.append("registry missing VOL-055 binding")
    else:
        if binding.get("title") != TITLE:
            errors.append("VOL-055 registry title binding drift")
        if set(binding.get("required_gap_texts") or []) != REQUIRED_GAPS:
            errors.append("VOL-055 registry gap binding drift")

    rules = registry.get("rules")
    if not isinstance(rules, list) or len(rules) < 10:
        errors.append("architecture registry rule set is unexpectedly small")
        rules = []

    seen_ids: set[str] = set()
    validator_paths: set[str] = set()
    allowed_waiver_rules = 0
    nonwaivable_rules = 0
    for raw in rules:
        if not isinstance(raw, dict):
            errors.append("architecture rule must be an object")
            continue
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id):
            errors.append(f"invalid architecture rule id: {rule_id!r}")
            continue
        if rule_id in seen_ids:
            errors.append(f"duplicate architecture rule id: {rule_id}")
        seen_ids.add(rule_id)

        if raw.get("severity") != "blocking":
            errors.append(f"{rule_id}: severity must remain blocking")
        if raw.get("change_requires_adr") is not True:
            errors.append(f"{rule_id}: rule changes must require ADR")

        validator = _repo_path(
            raw.get("validator_path"),
            label=f"{rule_id}.validator_path",
            errors=errors,
        )
        if validator is not None:
            if validator in validator_paths:
                errors.append(f"validator registered more than once: {validator}")
            validator_paths.add(validator)
            if not (root / validator).is_file():
                errors.append(f"{rule_id}: validator is missing: {validator}")
            if raw.get("command") != ["python", validator]:
                errors.append(f"{rule_id}: command must execute validator directly")

        owners = raw.get("owner_root_ids")
        zones = raw.get("affected_zone_ids")
        if not isinstance(owners, list) or not owners or len(owners) != len(set(owners)):
            errors.append(f"{rule_id}: owner_root_ids invalid")
        if not isinstance(zones, list) or not zones or len(zones) != len(set(zones)):
            errors.append(f"{rule_id}: affected_zone_ids invalid")

        policy = raw.get("waiver_policy")
        if not isinstance(policy, dict):
            errors.append(f"{rule_id}: waiver_policy missing")
            continue
        if policy.get("require_adr") is not True:
            errors.append(f"{rule_id}: waiver policy must require ADR")
        allowed = policy.get("allowed")
        ttl = policy.get("max_ttl_days")
        if allowed is True:
            allowed_waiver_rules += 1
            if (
                not isinstance(ttl, int)
                or isinstance(ttl, bool)
                or not 1 <= ttl <= 90
            ):
                errors.append(f"{rule_id}: invalid bounded waiver TTL")
        elif allowed is False:
            nonwaivable_rules += 1
            if ttl is not None:
                errors.append(f"{rule_id}: non-waivable rule must have null TTL")
        else:
            errors.append(f"{rule_id}: waiver allowed flag must be boolean")

    discovered = _discover_validators(root)
    if validator_paths != discovered:
        errors.append(
            "architecture validator inventory drift: "
            f"missing={sorted(discovered - validator_paths)} "
            f"stale={sorted(validator_paths - discovered)}"
        )

    waivers = registry.get("waivers")
    if not isinstance(waivers, list):
        errors.append("registry waivers must be a list")
        waivers = []

    return {
        "rule_count": len(rules),
        "registered_validator_count": len(validator_paths),
        "discovered_validator_count": len(discovered),
        "allowed_waiver_rule_count": allowed_waiver_rules,
        "nonwaivable_rule_count": nonwaivable_rules,
        "waiver_count": len(waivers),
    }


def _verify_source_contract(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in (VALIDATOR, TESTS):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing VOL-055 surface: {relative}")
            continue
        digests[relative.as_posix()] = _sha256(path)

    if (root / VALIDATOR).is_file():
        source = (root / VALIDATOR).read_text(encoding="utf-8")
        for token in (
            "def _discover_validator_paths",
            "architecture validator registry coverage drift",
            "waiver policy must require ADR",
            "max waiver TTL",
            "is expired",
            "approval must be independent from waiver owner",
            "requires full git_sha",
            "requires evidence_refs",
            "unsupported signature_method",
            "for rule_id in sorted(rule_ids)",
        ):
            if token not in source:
                errors.append(f"VOL-055 linter invariant missing: {token}")
    if (root / TESTS).is_file():
        tests = (root / TESTS).read_text(encoding="utf-8")
        for token in (
            "test_rejects_unregistered_architecture_validator",
            "test_rejects_waiver_without_existing_adr",
            "test_rejects_waiver_past_rule_ttl",
            "test_rejects_expired_waiver",
        ):
            if token not in tests:
                errors.append(f"VOL-055 linter regression missing: {token}")
    return digests


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    registry = _load(root / REGISTRY)
    architecture = _load(root / ARCHITECTURE)

    volume_binding = _verify_volume(master, errors)
    registry_binding = _verify_registry(registry, root, errors)
    source_digests = _verify_source_contract(root, errors)

    roots = architecture.get("canonical_roots")
    zones = architecture.get("zones")
    if not isinstance(roots, list) or not roots:
        errors.append("architecture canonical root authority missing")
    if not isinstance(zones, list) or not zones:
        errors.append("architecture zone authority missing")

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol055-architecture-linter-v1",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "registry_binding": registry_binding,
        "source_digests": source_digests,
        "registry_digest": _sha256(root / REGISTRY),
        "architecture_digest": _sha256(root / ARCHITECTURE),
        "errors": sorted(set(errors)),
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
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
            "verifier": "independent-vol055-architecture-linter-v1",
            "volume": VOLUME,
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-055 independent architecture-linter verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-055 independent architecture-linter verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
