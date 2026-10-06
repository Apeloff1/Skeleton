#!/usr/bin/env python3
"""Fail-closed validator for Skeleton's 100-level advanced AI structure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/advanced_ai_structure_100.json")
CONSTRUCTION = Path("machine/ai_app_construction.json")
ENTERPRISE = Path("machine/enterprise_system_architecture.json")

EXPECTED_SCHEMA = "advanced-ai-structure/v1"
EXPECTED_LEVEL_IDS = {f"L{i:03d}" for i in range(1, 101)}
EXPECTED_STRATA = {f"S{i:02d}" for i in range(1, 11)}
EXPECTED_WORK_PACKAGES = {f"ADV-S{i:02d}" for i in range(1, 11)}
EVIDENCE_PATHS = {
    "human_plan": "docs/plan/ADVANCED_AI_100_LEVELS.md",
    "validator": "scripts/check_advanced_ai_structure.py",
    "independent_verifier": "scripts/verify_advanced_ai_structure.py",
    "tests": "tests/test_advanced_ai_structure.py",
    "workflow": ".github/workflows/advanced-ai-structure.yml",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strings(
    value: object,
    *,
    label: str,
    errors: list[str],
    minimum: int = 1,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be non-empty text")
            continue
        result.append(item.strip())
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicates")
    if len(result) < minimum:
        errors.append(f"{label} must contain at least {minimum} items")
    return result


def _objects(
    value: object,
    *,
    label: str,
    errors: list[str],
    minimum: int = 1,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        result.append(item)
    if len(result) < minimum:
        errors.append(f"{label} must contain at least {minimum} objects")
    return result


def _ids(
    items: list[dict[str, Any]],
    *,
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{label}[{index}].id must be non-empty")
            continue
        if item_id in out:
            errors.append(f"{label} duplicate id: {item_id}")
        out[item_id] = item
    return out


def validate_payloads(
    contract: dict[str, Any],
    construction: dict[str, Any],
    enterprise: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("advanced AI schema_version drifted")
    if contract.get("status") != "active_plan":
        errors.append("advanced AI status must be active_plan")
    if contract.get("completion", {}).get("plan_complete") is not True:
        errors.append("advanced AI plan_complete must be true")
    if contract.get("completion", {}).get("implementation_claim") is not False:
        errors.append("planning contract must not claim implementation")

    base = contract.get("base_requirement")
    if not isinstance(base, dict):
        errors.append("base_requirement must be an object")
        base = {}
    expected_base = {
        "enterprise_contract": ENTERPRISE.as_posix(),
        "ai_construction_contract": CONSTRUCTION.as_posix(),
        "architecture_contract": "machine/architecture.json",
    }
    for key, expected in expected_base.items():
        if base.get(key) != expected:
            errors.append(f"base_requirement.{key} drifted")
    if enterprise.get("plan_complete") is not True:
        errors.append("enterprise architecture baseline must be plan_complete")

    construction_planes = _objects(
        construction.get("planes"),
        label="construction.planes",
        errors=errors,
        minimum=1,
    )
    plane_ids = {
        item["id"]
        for item in construction_planes
        if isinstance(item.get("id"), str)
    }
    if len(plane_ids) != 27:
        errors.append("advanced ladder expects 27 canonical AI construction planes")

    strata = _objects(
        contract.get("strata"),
        label="strata",
        errors=errors,
        minimum=10,
    )
    strata_map = _ids(strata, label="strata", errors=errors)
    if set(strata_map) != EXPECTED_STRATA:
        errors.append("advanced AI stratum set must be S01 through S10")
    if len(strata) != 10:
        errors.append("advanced AI structure must contain exactly 10 strata")

    covered_planes: set[str] = set()
    for index, stratum in enumerate(strata, start=1):
        sid = f"S{index:02d}"
        if stratum.get("id") != sid:
            errors.append(f"stratum order drift at index {index}")
            continue
        expected_start = (index - 1) * 10 + 1
        expected_end = index * 10
        if stratum.get("start") != expected_start:
            errors.append(f"{sid}.start must be {expected_start}")
        if stratum.get("end") != expected_end:
            errors.append(f"{sid}.end must be {expected_end}")
        if stratum.get("gate_level") != f"L{expected_end:03d}":
            errors.append(f"{sid}.gate_level must be L{expected_end:03d}")
        planes = set(
            _strings(
                stratum.get("planes"),
                label=f"{sid}.planes",
                errors=errors,
                minimum=1,
            )
        )
        unknown = planes - plane_ids
        if unknown:
            errors.append(f"{sid} references unknown planes: {sorted(unknown)}")
        covered_planes.update(planes)
        for field in ("title", "purpose", "authority", "failure"):
            value = stratum.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{sid}.{field} must be non-empty text")

    if covered_planes != plane_ids:
        missing = sorted(plane_ids - covered_planes)
        extra = sorted(covered_planes - plane_ids)
        if missing:
            errors.append(
                "advanced strata do not cover every canonical plane: "
                + ", ".join(missing)
            )
        if extra:
            errors.append(
                "advanced strata reference unexpected planes: "
                + ", ".join(extra)
            )

    levels = _objects(
        contract.get("levels"),
        label="levels",
        errors=errors,
        minimum=100,
    )
    if len(levels) != 100:
        errors.append("advanced AI structure must contain exactly 100 levels")
    level_map = _ids(levels, label="levels", errors=errors)
    if set(level_map) != EXPECTED_LEVEL_IDS:
        errors.append("advanced level IDs must be exactly L001 through L100")

    ordinals: list[int] = []
    for index, level in enumerate(levels, start=1):
        expected_id = f"L{index:03d}"
        if level.get("id") != expected_id:
            errors.append(f"level order drift at ordinal {index}")
        ordinal = level.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int):
            errors.append(f"{expected_id}.ordinal must be integer")
            continue
        ordinals.append(ordinal)
        if ordinal != index:
            errors.append(f"{expected_id}.ordinal must equal {index}")

        expected_stratum = f"S{((index - 1) // 10) + 1:02d}"
        if level.get("stratum") != expected_stratum:
            errors.append(f"{expected_id}.stratum must be {expected_stratum}")

        expected_gate = index % 10 == 0
        if level.get("gate") is not expected_gate:
            errors.append(f"{expected_id}.gate drift")

        for field in (
            "title",
            "objective",
            "state",
            "authority_rule",
            "failure_mode",
        ):
            value = level.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{expected_id}.{field} must be non-empty text")
        if level.get("state") != "planned_target":
            errors.append(f"{expected_id}.state must remain planned_target")

        prereqs = _strings(
            level.get("promotion_prerequisites"),
            label=f"{expected_id}.promotion_prerequisites",
            errors=errors,
            minimum=1,
        )
        if index == 1:
            if prereqs != ["ENTERPRISE-BASELINE"]:
                errors.append("L001 must depend only on ENTERPRISE-BASELINE")
        else:
            expected_prev = f"L{index - 1:03d}"
            if prereqs != [expected_prev]:
                errors.append(
                    f"{expected_id} must promote from exactly {expected_prev}"
                )
        for prereq in prereqs:
            if prereq == "ENTERPRISE-BASELINE":
                continue
            if prereq not in EXPECTED_LEVEL_IDS:
                errors.append(f"{expected_id} unknown prerequisite {prereq}")
                continue
            prereq_ordinal = int(prereq[1:])
            if prereq_ordinal >= index:
                errors.append(
                    f"{expected_id} prerequisite must point backward: {prereq}"
                )

        required_planes = set(
            _strings(
                level.get("required_planes"),
                label=f"{expected_id}.required_planes",
                errors=errors,
                minimum=1,
            )
        )
        stratum_planes = set(strata_map.get(expected_stratum, {}).get("planes", []))
        if required_planes != stratum_planes:
            errors.append(
                f"{expected_id}.required_planes must equal its stratum plane set"
            )
        if required_planes - plane_ids:
            errors.append(f"{expected_id} references unknown canonical plane")

        _strings(
            level.get("deliverables"),
            label=f"{expected_id}.deliverables",
            errors=errors,
            minimum=6,
        )
        _strings(
            level.get("acceptance_evidence"),
            label=f"{expected_id}.acceptance_evidence",
            errors=errors,
            minimum=4,
        )

    if ordinals and ordinals != list(range(1, 101)):
        errors.append("advanced level ordinals must be contiguous 1 through 100")

    maturity = _objects(
        contract.get("maturity_bands"),
        label="maturity_bands",
        errors=errors,
        minimum=10,
    )
    if len(maturity) != 10:
        errors.append("exactly 10 maturity bands are required")
    for index, band in enumerate(maturity, start=1):
        if band.get("band") != f"A{index}":
            errors.append(f"maturity band {index} identity drifted")

    cross_cutting = contract.get("cross_cutting_requirements")
    if not isinstance(cross_cutting, dict):
        errors.append("cross_cutting_requirements must be an object")
        cross_cutting = {}
    for key, minimum in (
        ("every_level", 8),
        ("high_impact_levels", 5),
        ("frontier_levels", 6),
    ):
        _strings(
            cross_cutting.get(key),
            label=f"cross_cutting_requirements.{key}",
            errors=errors,
            minimum=minimum,
        )

    program = contract.get("implementation_program")
    if not isinstance(program, dict):
        errors.append("implementation_program must be an object")
        program = {}
    packages = _objects(
        program.get("work_packages"),
        label="implementation_program.work_packages",
        errors=errors,
        minimum=10,
    )
    package_map = _ids(
        packages,
        label="implementation_program.work_packages",
        errors=errors,
    )
    if set(package_map) != EXPECTED_WORK_PACKAGES:
        errors.append("advanced work packages must be ADV-S01 through ADV-S10")
    for index in range(1, 11):
        package = package_map.get(f"ADV-S{index:02d}", {})
        if package.get("levels") != f"{(index-1)*10+1:03d}-{index*10:03d}":
            errors.append(f"ADV-S{index:02d}.levels drifted")
        if package.get("priority") not in {"P0", "P1", "P2"}:
            errors.append(f"ADV-S{index:02d}.priority invalid")
        if not isinstance(package.get("exit"), str) or not package.get("exit"):
            errors.append(f"ADV-S{index:02d}.exit must be non-empty")

    evidence = contract.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
        evidence = {}
    if evidence != EVIDENCE_PATHS:
        errors.append("advanced AI evidence path registry drifted")
    for path in EVIDENCE_PATHS.values():
        if not (repo_root / path).is_file():
            errors.append(f"advanced AI evidence path missing: {path}")

    completion = contract.get("completion")
    if not isinstance(completion, dict):
        errors.append("completion must be an object")
        completion = {}
    if completion.get("plan_complete") is not True:
        errors.append("completion.plan_complete must be true")
    if completion.get("implementation_claim") is not False:
        errors.append("completion.implementation_claim must be false")
    if completion.get("promoted_levels") != []:
        errors.append("planning change must not pre-promote levels")
    if completion.get("signed_levels") != []:
        errors.append("planning change must not pre-sign levels")

    if level_map.get("L100", {}).get("title") != "Frontier System Acceptance":
        errors.append("L100 must remain Frontier System Acceptance")
    if level_map.get("L099", {}).get("title") != "Bounded Self-Evolution Governance":
        errors.append("L099 must preserve bounded self-evolution governance")

    return errors


def validate(repo_root: Path = ROOT) -> list[str]:
    try:
        return validate_payloads(
            _load(repo_root / CONTRACT),
            _load(repo_root / CONSTRUCTION),
            _load(repo_root / ENTERPRISE),
            repo_root=repo_root,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load advanced AI structure sources: {exc}"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence(head_sha: str, repo_root: Path = ROOT) -> dict[str, Any]:
    errors = validate(repo_root)
    contract = _load(repo_root / CONTRACT)
    files = [
        CONTRACT.as_posix(),
        CONSTRUCTION.as_posix(),
        ENTERPRISE.as_posix(),
        *sorted(EVIDENCE_PATHS.values()),
    ]
    digests = {
        path: _sha(repo_root / path)
        for path in files
        if (repo_root / path).is_file()
    }
    payload: dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "advanced-ai-structure-structural-v1",
        "head_sha": head_sha.strip(),
        "valid": not errors,
        "errors": errors,
        "level_count": len(contract.get("levels") or []),
        "stratum_count": len(contract.get("strata") or []),
        "plan_complete": contract.get("completion", {}).get("plan_complete"),
        "implementation_claim": contract.get("completion", {}).get(
            "implementation_claim"
        ),
        "contract_digest": _sha(repo_root / CONTRACT),
        "file_digests": digests,
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    if args.head_sha:
        result = evidence(args.head_sha)
        if args.evidence_out:
            Path(args.evidence_out).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_evidence or args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1

    errors = validate()
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": EXPECTED_SCHEMA,
                    "valid": not errors,
                    "errors": errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif errors:
        print("advanced-ai-structure: rejected")
        for error in errors:
            print("  -", error)
    else:
        print(
            "advanced-ai-structure: OK "
            "(100 levels; 10 strata; plan complete; implementation not claimed)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
