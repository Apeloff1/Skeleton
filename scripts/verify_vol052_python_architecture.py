#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-052 Internal Python Architecture.

This verifier does not import the canonical package-layer validator. It binds
VOL-052 to the machine package-layer manifest and architecture rule registry,
then independently checks layer ordering, dependency permissions, path
ownership, validator/test surfaces, and the fail-closed import-graph contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
LAYERS = Path("machine/python_package_layers.json")
REGISTRY = Path("machine/architecture_rule_registry.json")
VALIDATOR = Path("scripts/check_architecture_package_layers.py")
TESTS = Path("tests/test_architecture_package_layers.py")
VOLUME = "VOL-052"
TITLE = "Internal Python Architecture"
REQUIRED_GAPS = {
    "define package layer manifest",
    "add import graph fitness test",
}
REQUIRED_RULE_ID = "ARCH-PYTHON-LAYERS"
REQUIRED_LAYER_NAMES = (
    "foundation",
    "contracts",
    "runtime-services",
    "orchestration",
    "adapters",
)


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


def _find_volume(master: Mapping[str, Any]) -> Mapping[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise VerificationError("masterplan volumes must be a list")
    for volume in volumes:
        if isinstance(volume, dict) and volume.get("key") == VOLUME:
            return volume
    raise VerificationError(f"masterplan missing {VOLUME}")


def _normalize_path(value: object, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: path must be non-empty")
        return None
    if "\\" in value:
        errors.append(f"{label}: path must use POSIX separators")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        errors.append(f"{label}: path must be canonical and relative")
        return None
    if pure.as_posix() != value:
        errors.append(f"{label}: path normalization drift")
        return None
    return value


def _verify_volume(
    master: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    volume = _find_volume(master)
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
        "Separate contracts/domain/runtime/adapters/testing concerns",
        "Ban hidden import-time registration or environment mutation",
        "Keep provider/framework dependencies behind adapters",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"{VOLUME} requirement invariant lost: {phrase}")
    return {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "scope": volume.get("scope"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "gaps": sorted(gaps),
    }


def _verify_layers(
    manifest: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    if manifest.get("schema_version") != "skeleton.architecture.python_package_layers.v1":
        errors.append("package-layer schema drift")
    if manifest.get("status") != "active":
        errors.append("package-layer manifest must remain active")

    bindings = manifest.get("masterplan_bindings")
    if not isinstance(bindings, list):
        errors.append("masterplan_bindings must be a list")
        bindings = []
    binding = next(
        (
            item
            for item in bindings
            if isinstance(item, dict) and item.get("volume_ref") == VOLUME
        ),
        None,
    )
    if not isinstance(binding, dict):
        errors.append(f"package-layer manifest missing {VOLUME} binding")
    else:
        if binding.get("title") != TITLE:
            errors.append(f"{VOLUME} package-layer title binding drift")
        if set(binding.get("required_gap_texts") or []) != REQUIRED_GAPS:
            errors.append(f"{VOLUME} package-layer gap binding drift")

    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        errors.append("package-layer policy missing")
        policy = {}
    if policy.get("unclassified_internal_imports") != "allowed_but_reported":
        errors.append("unclassified internal imports must remain report-only")
    if policy.get("same_layer_imports") is not True:
        errors.append("same-layer import policy drift")
    if "lower-numbered layer only" not in str(policy.get("rule", "")):
        errors.append("dependency-direction policy lost")
    if "sys.path or PYTHONPATH" not in str(policy.get("path_hack_rule", "")):
        errors.append("runtime path-mutation policy lost")
    if "longest matching path" not in str(policy.get("package_rule", "")):
        errors.append("longest-prefix classification policy lost")

    layers = manifest.get("layers")
    if not isinstance(layers, list) or len(layers) != 5:
        errors.append("VOL-052 requires exactly five declared package layers")
        layers = []

    ids: dict[str, int] = {}
    path_owners: dict[str, str] = {}
    names: list[str] = []
    path_count = 0
    for layer in layers:
        if not isinstance(layer, dict):
            errors.append("package layer must be an object")
            continue
        layer_id = layer.get("id")
        order = layer.get("order")
        name = layer.get("name")
        if not isinstance(layer_id, str) or not layer_id:
            errors.append("package layer id missing")
            continue
        if layer_id in ids:
            errors.append(f"duplicate package layer id: {layer_id}")
            continue
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            errors.append(f"{layer_id}: invalid layer order")
            continue
        ids[layer_id] = order
        names.append(str(name))

        raw_paths = layer.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            errors.append(f"{layer_id}: paths must be non-empty")
            continue
        for raw in raw_paths:
            normalized = _normalize_path(
                raw,
                label=f"{layer_id}.path",
                errors=errors,
            )
            if normalized is None:
                continue
            if not normalized.startswith("skeleton/"):
                errors.append(f"{layer_id}: classified path escapes skeleton/")
            if normalized in path_owners:
                errors.append(
                    f"classified path has multiple direct owners: {normalized}"
                )
            path_owners[normalized] = layer_id
            path_count += 1
            if not (root / normalized).exists():
                errors.append(f"{layer_id}: classified path missing: {normalized}")

    if tuple(names) != REQUIRED_LAYER_NAMES:
        errors.append("package-layer semantic order drift")
    if sorted(ids.values()) != list(range(5)):
        errors.append("package-layer numeric order must remain contiguous 0..4")

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_id = layer.get("id")
        if layer_id not in ids:
            continue
        allowed = layer.get("allowed_layer_ids")
        if not isinstance(allowed, list) or layer_id not in allowed:
            errors.append(f"{layer_id}: layer must allow itself")
            continue
        if len(allowed) != len(set(allowed)):
            errors.append(f"{layer_id}: duplicate allowed layer")
        for dependency in allowed:
            if dependency not in ids:
                errors.append(f"{layer_id}: unknown allowed layer {dependency}")
            elif ids[dependency] > ids[layer_id]:
                errors.append(
                    f"{layer_id}: upward dependency permission to {dependency}"
                )

    return {
        "layer_count": len(layers),
        "classified_path_count": path_count,
        "layer_ids": sorted(ids, key=ids.get),
        "layer_names": names,
    }


def _verify_rule_registry(
    registry: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    rules = registry.get("rules")
    if not isinstance(rules, list):
        errors.append("architecture rule registry rules must be a list")
        rules = []
    matches = [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("id") == REQUIRED_RULE_ID
    ]
    if len(matches) != 1:
        errors.append(f"{REQUIRED_RULE_ID} must appear exactly once")
        return {}
    rule = matches[0]
    if rule.get("validator_path") != VALIDATOR.as_posix():
        errors.append(f"{REQUIRED_RULE_ID}: validator path drift")
    if rule.get("severity") != "blocking":
        errors.append(f"{REQUIRED_RULE_ID}: severity must remain blocking")
    if rule.get("change_requires_adr") is not True:
        errors.append(f"{REQUIRED_RULE_ID}: ADR change control lost")
    command = rule.get("command")
    if command != ["python", VALIDATOR.as_posix()]:
        errors.append(f"{REQUIRED_RULE_ID}: execution command drift")
    return {
        "rule_id": rule.get("id"),
        "severity": rule.get("severity"),
        "validator_path": rule.get("validator_path"),
    }


def _verify_source_contract(root: Path, errors: list[str]) -> dict[str, str]:
    required_paths = (VALIDATOR, TESTS)
    digests: dict[str, str] = {}
    for relative in required_paths:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing VOL-052 surface: {relative}")
            continue
        digests[relative.as_posix()] = _sha256(path)

    if (root / VALIDATOR).is_file():
        source = (root / VALIDATOR).read_text(encoding="utf-8")
        for token in (
            "import ast",
            "def _classify_module",
            "def _absolute_imports",
            "def _has_path_hack",
            "upward import",
            "runtime sys.path/PYTHONPATH mutation is forbidden",
            "unclassified_internal_imports",
            "longest module-prefix classification wins",
        ):
            if token not in source:
                errors.append(f"VOL-052 validator invariant missing: {token}")
    if (root / TESTS).is_file():
        tests = (root / TESTS).read_text(encoding="utf-8")
        for token in (
            "test_rejects_upward_import",
            "test_rejects_path_hack",
            "test_longest_path_override_classifies_composition_module",
            "test_rejects_layer_allowing_higher_layer",
        ):
            if token not in tests:
                errors.append(f"VOL-052 regression missing: {token}")
    return digests


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    manifest = _load(root / LAYERS)
    registry = _load(root / REGISTRY)

    volume_binding = _verify_volume(master, errors)
    layer_binding = _verify_layers(manifest, root, errors)
    registry_binding = _verify_rule_registry(registry, errors)
    source_digests = _verify_source_contract(root, errors)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol052-python-architecture-v1",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "layer_binding": layer_binding,
        "registry_binding": registry_binding,
        "source_digests": source_digests,
        "manifest_digest": _sha256(root / LAYERS),
        "registry_digest": _sha256(root / REGISTRY),
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
            "verifier": "independent-vol052-python-architecture-v1",
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
            "VOL-052 independent Python architecture verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-052 independent Python architecture verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
