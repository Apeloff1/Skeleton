#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-053 Import Architecture.

The canonical packaged-wheel validator performs the expensive isolated build and
import probe. This verifier independently binds that behavior to VOL-053,
checks the package-layer path-hack contract, validates the blocking architecture
registry entries, and verifies that the canonical wheel probe retains its
isolation and source-leakage protections.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
LAYERS = Path("machine/python_package_layers.json")
REGISTRY = Path("machine/architecture_rule_registry.json")
LAYER_VALIDATOR = Path("scripts/check_architecture_package_layers.py")
WHEEL_VALIDATOR = Path("scripts/check_architecture_packaged_wheel.py")
LAYER_TESTS = Path("tests/test_architecture_package_layers.py")
WHEEL_TESTS = Path("tests/test_architecture_packaged_wheel.py")
VOLUME = "VOL-053"
TITLE = "Import Architecture"
REQUIRED_GAPS = {
    "remove remaining path hacks",
    "materialize packaged-wheel import test",
}
REQUIRED_RULES = {
    "ARCH-PYTHON-LAYERS": LAYER_VALIDATOR.as_posix(),
    "ARCH-PACKAGED-WHEEL": WHEEL_VALIDATOR.as_posix(),
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


def _verify_volume(master: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
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
        "canonical package paths without sys.path surgery",
        "Detect shadowed modules and ambiguous import roots",
        "optional/plugin imports as declared capability dependencies",
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


def _verify_manifest(
    manifest: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    if manifest.get("schema_version") != "skeleton.architecture.python_package_layers.v1":
        errors.append("package-layer schema drift")
    if manifest.get("status") != "active":
        errors.append("package-layer manifest must remain active")
    bindings = manifest.get("masterplan_bindings")
    if not isinstance(bindings, list):
        errors.append("package-layer masterplan_bindings must be a list")
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
        errors.append("package-layer manifest missing VOL-053 binding")
    else:
        if binding.get("title") != TITLE:
            errors.append("VOL-053 package-layer title binding drift")
        if set(binding.get("required_gap_texts") or []) != REQUIRED_GAPS:
            errors.append("VOL-053 package-layer gap binding drift")

    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        errors.append("package-layer policy missing")
        policy = {}
    path_hack_rule = str(policy.get("path_hack_rule", ""))
    if "sys.path" not in path_hack_rule or "PYTHONPATH" not in path_hack_rule:
        errors.append("VOL-053 path-hack prohibition weakened")
    package_rule = str(policy.get("package_rule", ""))
    if "Every declared package/path must exist" not in package_rule:
        errors.append("VOL-053 package existence rule lost")
    return {
        "status": manifest.get("status"),
        "manifest_version": manifest.get("manifest_version"),
        "path_hack_rule": path_hack_rule,
    }


def _verify_registry(
    registry: Mapping[str, Any],
    errors: list[str],
) -> list[dict[str, Any]]:
    rules = registry.get("rules")
    if not isinstance(rules, list):
        errors.append("architecture rule registry rules must be a list")
        rules = []
    result: list[dict[str, Any]] = []
    for rule_id, validator in REQUIRED_RULES.items():
        matches = [
            rule
            for rule in rules
            if isinstance(rule, dict) and rule.get("id") == rule_id
        ]
        if len(matches) != 1:
            errors.append(f"{rule_id} must appear exactly once")
            continue
        rule = matches[0]
        if rule.get("validator_path") != validator:
            errors.append(f"{rule_id}: validator path drift")
        if rule.get("severity") != "blocking":
            errors.append(f"{rule_id}: severity must remain blocking")
        if rule.get("change_requires_adr") is not True:
            errors.append(f"{rule_id}: ADR change control lost")
        command = rule.get("command")
        if command != ["python", validator]:
            errors.append(f"{rule_id}: command drift")
        result.append(
            {
                "rule_id": rule_id,
                "validator_path": rule.get("validator_path"),
                "severity": rule.get("severity"),
            }
        )
    return result


def _extract_probe_names(source: str, errors: list[str]) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        errors.append("packaged-wheel validator no longer parses")
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "probes"
            for target in node.targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            errors.append("packaged-wheel probe list is no longer literal/deterministic")
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.startswith("skeleton")
            for item in value
        ):
            errors.append("packaged-wheel probe list is invalid")
            return []
        return value
    errors.append("packaged-wheel probe list is missing")
    return []


def _verify_source_contract(root: Path, errors: list[str]) -> dict[str, Any]:
    paths = (
        LAYER_VALIDATOR,
        WHEEL_VALIDATOR,
        LAYER_TESTS,
        WHEEL_TESTS,
    )
    digests: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing VOL-053 surface: {relative}")
            continue
        digests[relative.as_posix()] = _sha256(path)

    probes: list[str] = []
    if (root / WHEEL_VALIDATOR).is_file():
        source = (root / WHEEL_VALIDATOR).read_text(encoding="utf-8")
        probes = _extract_probe_names(source, errors)
        for token in (
            '"--no-deps"',
            '"--no-build-isolation"',
            "sys.executable",
            '"-m", "venv"',
            '"-m", "pip",',
            '"install"',
            '"-I"',
            'env.pop("PYTHONPATH", None)',
            'env.pop("PYTHONHOME", None)',
            "wheel imports leaked to source tree",
            "skeleton-*.dist-info",
            "expected exactly one skeleton wheel",
        ):
            if token not in source:
                errors.append(f"VOL-053 wheel isolation invariant missing: {token}")
        if len(probes) < 15:
            errors.append("VOL-053 packaged-wheel probe surface is too small")
        for module in (
            "skeleton",
            "skeleton.kernel",
            "skeleton.contracts.operation",
            "skeleton.providers.contract",
            "skeleton.persistence",
            "skeleton.intelligence",
            "skeleton.jeeves",
            "skeleton.api",
        ):
            if module not in probes:
                errors.append(f"VOL-053 critical wheel probe missing: {module}")

    if (root / LAYER_VALIDATOR).is_file():
        source = (root / LAYER_VALIDATOR).read_text(encoding="utf-8")
        for token in (
            "def _has_path_hack",
            'value.value.id == "sys"',
            'value.attr == "path"',
            'sl.value == "PYTHONPATH"',
            "runtime sys.path/PYTHONPATH mutation is forbidden",
        ):
            if token not in source:
                errors.append(f"VOL-053 path-hack invariant missing: {token}")

    if (root / WHEEL_TESTS).is_file():
        tests = (root / WHEEL_TESTS).read_text(encoding="utf-8")
        if "test_masterplan_and_probe_contract_is_present" not in tests:
            errors.append("VOL-053 wheel regression binding missing")
    if (root / LAYER_TESTS).is_file():
        tests = (root / LAYER_TESTS).read_text(encoding="utf-8")
        if "test_rejects_path_hack" not in tests:
            errors.append("VOL-053 path-hack regression missing")

    return {
        "digests": digests,
        "probe_count": len(probes),
        "probes": probes,
    }


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    manifest = _load(root / LAYERS)
    registry = _load(root / REGISTRY)

    volume_binding = _verify_volume(master, errors)
    manifest_binding = _verify_manifest(manifest, errors)
    registry_bindings = _verify_registry(registry, errors)
    source_contract = _verify_source_contract(root, errors)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol053-import-architecture-v1",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "manifest_binding": manifest_binding,
        "registry_bindings": registry_bindings,
        "source_contract": source_contract,
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
            "verifier": "independent-vol053-import-architecture-v1",
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
            "VOL-053 independent import architecture verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-053 independent import architecture verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
