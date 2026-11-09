#!/usr/bin/env python3
"""Fail-closed validator for the P2 quality/formal/metrics/final-assembly authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REFS = {"VOL-070", "VOL-081", "VOL-117", "VOL-120"}


class P2QualityControlError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P2QualityControlError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise P2QualityControlError(f"{path} must contain an object")
    return data


def _contains_forbidden_score_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in {"weight", "weighted_score", "overall_score"}:
                return True
            if _contains_forbidden_score_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_score_key(x) for x in value)
    return False


def validate_payload(
    control: dict[str, Any],
    master: dict[str, Any],
    engineering: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    if control.get("status") != "active":
        raise P2QualityControlError("P2 quality control must be active")
    if _contains_forbidden_score_key(control.get("quality_vector")):
        raise P2QualityControlError("weighted/overall quality score is forbidden")

    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    bindings = {
        item.get("volume_ref"): item
        for item in control.get("masterplan_bindings", [])
        if isinstance(item, dict)
    }
    if set(bindings) != REFS:
        raise P2QualityControlError("masterplan binding coverage drift")
    for ref in sorted(REFS):
        volume = volumes.get(ref)
        binding = bindings[ref]
        if not isinstance(volume, dict):
            raise P2QualityControlError(f"masterplan volume missing: {ref}")
        expected = {
            "title": volume.get("title"),
            "accountability_id": volume.get("accountability_id"),
            "required_gap_texts": volume.get("gaps"),
            "risks": volume.get("risks"),
            "contracts": volume.get("contracts"),
        }
        for field, value in expected.items():
            if binding.get(field) != value:
                raise P2QualityControlError(f"{ref}.{field} drift")

    sources = control.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise P2QualityControlError("quality control sources missing")
    for name, relative in sources.items():
        if not isinstance(relative, str) or not relative or not (root / relative).is_file():
            raise P2QualityControlError(f"quality source missing {name}: {relative!r}")

    expected_dimensions = sorted(
        {
            dimension
            for profile in engineering.get("work_package_profiles", [])
            if isinstance(profile, dict)
            for dimension in profile.get("required_dimensions", [])
        }
    )
    dimensions = control.get("quality_vector", {}).get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise P2QualityControlError("quality dimensions missing")
    by_dimension = {
        item.get("dimension_id"): item
        for item in dimensions
        if isinstance(item, dict)
    }
    if len(by_dimension) != len(dimensions):
        raise P2QualityControlError("duplicate/invalid quality dimension")
    if sorted(by_dimension) != expected_dimensions:
        raise P2QualityControlError("quality dimension coverage drift")
    for dimension_id, item in by_dimension.items():
        if item.get("non_compensable") is not True:
            raise P2QualityControlError(f"{dimension_id} became compensable")
        refs = item.get("evaluation_refs")
        if not isinstance(refs, list) or not refs:
            raise P2QualityControlError(f"{dimension_id} lacks evaluation refs")
        for relative in refs:
            if (
                not isinstance(relative, str)
                or relative.startswith("planned:")
                or not (root / relative).is_file()
            ):
                raise P2QualityControlError(
                    f"{dimension_id} evaluation ref is not executable: {relative!r}"
                )

    quality = control.get("quality_vector", {})
    if "No weighted or averaged overall score" not in str(quality.get("aggregation_rule")):
        raise P2QualityControlError("quality aggregation anti-compensation rule drift")
    if "All applicable required dimensions must pass independently" not in str(
        quality.get("promotion_rule")
    ):
        raise P2QualityControlError("quality promotion rule drift")

    formal = control.get("formal_methods")
    if not isinstance(formal, dict):
        raise P2QualityControlError("formal methods authority missing")
    targets = formal.get("targets")
    if not isinstance(targets, list) or len(targets) != 2:
        raise P2QualityControlError("formal target coverage drift")
    target_ids: set[str] = set()
    expected_req = {
        f"REQ:VOL-081:{i:03d}"
        for i, _ in enumerate(volumes["VOL-081"].get("requirements", []), 1)
    }
    for target in targets:
        target_id = target.get("target_id")
        if not isinstance(target_id, str) or not target_id or target_id in target_ids:
            raise P2QualityControlError("duplicate/invalid formal target ID")
        target_ids.add(target_id)
        source = target.get("source")
        if not isinstance(source, str) or not (root / source).is_file():
            raise P2QualityControlError(f"{target_id} source missing")
        if set(target.get("requirement_refs", [])) != expected_req:
            raise P2QualityControlError(f"{target_id} requirement trace drift")
        tests = target.get("test_refs")
        if not isinstance(tests, list) or not tests:
            raise P2QualityControlError(f"{target_id} lacks test refs")
        for relative in tests:
            if not isinstance(relative, str) or relative.startswith("planned:") or not (root / relative).is_file():
                raise P2QualityControlError(f"{target_id} test ref is not executable")
        properties = target.get("properties")
        required_properties = {
            "complete_transition_domain",
            "declared_targets_only",
            "terminal_absorbing",
            "terminal_reachable_from_every_state",
            "all_states_reachable_from_initial",
        }
        if set(properties or []) != required_properties:
            raise P2QualityControlError(f"{target_id} formal property coverage drift")

    metrics = control.get("project_metrics")
    if not isinstance(metrics, dict):
        raise P2QualityControlError("project metric authority missing")
    policy = metrics.get("policy", {})
    if policy.get("categories") != ["activity", "throughput", "quality", "risk", "outcome"]:
        raise P2QualityControlError("metric category policy drift")
    if "zero completion or maturity authority" not in str(policy.get("completion_rule")):
        raise P2QualityControlError("metrics gained completion authority")
    definitions = metrics.get("definitions")
    if not isinstance(definitions, list) or len(definitions) != 5:
        raise P2QualityControlError("metric definition coverage drift")
    if len({x.get("metric_id") for x in definitions if isinstance(x, dict)}) != 5:
        raise P2QualityControlError("metric IDs are not unique")
    if {x.get("category") for x in definitions} != {
        "activity",
        "throughput",
        "quality",
        "risk",
        "outcome",
    }:
        raise P2QualityControlError("metric categories incomplete")
    for item in definitions:
        for relative in item.get("sources", []):
            if not isinstance(relative, str) or not (root / relative).is_file():
                raise P2QualityControlError(
                    f"{item.get('metric_id')} metric source missing"
                )

    assembly = control.get("final_assembly")
    if not isinstance(assembly, dict):
        raise P2QualityControlError("final assembly plan missing")
    if assembly.get("source_binding") != "exact_git_head":
        raise P2QualityControlError("final assembly source binding must be exact head")
    if assembly.get("environment") != {
        "os": "ubuntu-24.04",
        "python": "3.11.16",
        "architecture": "x86_64",
    }:
        raise P2QualityControlError("release-like environment contract drift")
    dependency_inputs = assembly.get("dependency_inputs")
    if dependency_inputs != [
        "pyproject.toml",
        "requirements-dev.txt",
        "requirements-build.txt",
    ]:
        raise P2QualityControlError("final assembly dependency input authority drift")
    for relative in dependency_inputs:
        if not (root / relative).is_file():
            raise P2QualityControlError(
                f"final assembly dependency input missing: {relative}"
            )

    gates = assembly.get("gates")
    if not isinstance(gates, list) or len(gates) != 6:
        raise P2QualityControlError("final assembly gate coverage drift")
    gate_ids = [x.get("gate_id") for x in gates if isinstance(x, dict)]
    if len(gate_ids) != len(set(gate_ids)):
        raise P2QualityControlError("duplicate final assembly gate")
    for gate in gates:
        argv = gate.get("argv")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(x, str) and x for x in argv
        ):
            raise P2QualityControlError(f"invalid final assembly argv: {gate!r}")
        if argv[0] == "python" and len(argv) >= 2 and argv[1].endswith(".py"):
            if not (root / argv[1]).is_file():
                raise P2QualityControlError(
                    f"final assembly gate script missing: {argv[1]}"
                )
    release_gate = next(
        (gate for gate in gates if gate.get("gate_id") == "FA-RELEASE-EVIDENCE"),
        None,
    )
    if not isinstance(release_gate, dict) or release_gate.get("argv") != [
        "python",
        "-m",
        "pytest",
        "-q",
        "skeleton/testing/test_release_evidence.py",
    ]:
        raise P2QualityControlError(
            "release-evidence gate must execute the pytest suite"
        )

    promotion = assembly.get("promotion_binding", {})
    if promotion.get("digest_algorithm") != "sha256":
        raise P2QualityControlError("final assembly digest algorithm drift")
    if promotion.get("independent_verification_required") is not True:
        raise P2QualityControlError("independent final verification was weakened")
    if "exactly match" not in str(promotion.get("rule")):
        raise P2QualityControlError("release promotion digest binding drift")

    return {
        "status": "valid",
        "masterplan_bindings": len(bindings),
        "quality_dimensions": len(dimensions),
        "formal_targets": len(targets),
        "project_metrics": len(definitions),
        "final_assembly_gates": len(gates),
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    return validate_payload(
        _load(root / "machine/p2_quality_control.json"),
        _load(root / "machine/ai_master_plan.json"),
        _load(root / "machine/ai_engineering_pass.json"),
        root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except P2QualityControlError as exc:
        print(f"p2 quality control: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
