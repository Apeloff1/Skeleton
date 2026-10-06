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

INTEGRATION_FILES = (
    "machine/architecture.json",
    "docs/ARCHITECTURE_MAP.md",
    "docs/AI_APP_CONSTRUCTION_MANUAL.md",
    "docs/plan/AI_CHAT_MASTERPLAN_2026-10-06.md",
    "docs/ENTERPRISE_SYSTEM_ARCHITECTURE.md",
)


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

    summary = construction.get("advanced_ai_structure")
    if not isinstance(summary, dict):
        errors.append("AI construction contract is missing advanced_ai_structure")
        summary = {}
    expected_summary = {
        "contract": CONTRACT.as_posix(),
        "human_plan": EVIDENCE_PATHS["human_plan"],
        "validator": EVIDENCE_PATHS["validator"],
        "independent_verifier": EVIDENCE_PATHS["independent_verifier"],
        "workflow": EVIDENCE_PATHS["workflow"],
        "levels": 100,
        "strata": 10,
        "enterprise_baseline": ENTERPRISE.as_posix(),
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"construction advanced_ai_structure.{key} drifted")

    release_evidence = construction.get("release_evidence_bundle")
    if (
        not isinstance(release_evidence, list)
        or "100-level advanced AI structure exact-head validator and independent receipt"
        not in release_evidence
    ):
        errors.append("AI construction release bundle is missing 100-level evidence")

    architecture_path = repo_root / "machine" / "architecture.json"
    try:
        architecture = _load(architecture_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"cannot load machine architecture for advanced AI binding: {exc}")
        architecture = {}
    sources = architecture.get("sources")
    if not isinstance(sources, dict):
        errors.append("machine architecture sources missing for advanced AI binding")
        sources = {}
    expected_sources = {
        "advanced_ai_structure": CONTRACT.as_posix(),
        "advanced_ai_structure_manual": EVIDENCE_PATHS["human_plan"],
        "advanced_ai_structure_validator": EVIDENCE_PATHS["validator"],
        "advanced_ai_structure_independent_verifier": EVIDENCE_PATHS[
            "independent_verifier"
        ],
    }
    for key, expected in expected_sources.items():
        if sources.get(key) != expected:
            errors.append(f"machine architecture source {key} drifted")

    for raw in INTEGRATION_FILES:
        if not (repo_root / raw).is_file():
            errors.append(f"advanced AI integration file missing: {raw}")

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

        if level.get("implementation_contract_required") is not True:
            errors.append(f"{expected_id} must require implementation contract")
        if level.get("operational_readiness_required") is not True:
            errors.append(f"{expected_id} must require operational readiness")
        if level.get("deprecation_state") != "ACTIVE_PLAN":
            errors.append(f"{expected_id}.deprecation_state must be ACTIVE_PLAN")
        control_profile = level.get("control_profile")
        expected_profile = profiles.get(expected_stratum)
        if not isinstance(control_profile, dict):
            errors.append(f"{expected_id}.control_profile must be an object")
        elif control_profile != expected_profile:
            errors.append(
                f"{expected_id}.control_profile must match {expected_stratum}"
            )

        risk_class = level.get("risk_class")
        if risk_class not in {"standard", "high", "critical"}:
            errors.append(f"{expected_id}.risk_class invalid")
        expected_risk = defaults.get(expected_stratum)
        if risk_class != expected_risk:
            errors.append(
                f"{expected_id}.risk_class must equal stratum default "
                f"{expected_risk}"
            )
        expected_age = expected_ages.get(risk_class)
        if level.get("maximum_evidence_age_days") != expected_age:
            errors.append(
                f"{expected_id}.maximum_evidence_age_days must be {expected_age}"
            )
        _strings(
            level.get("requalification_triggers"),
            label=f"{expected_id}.requalification_triggers",
            errors=errors,
            minimum=3,
        )

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

    model_lifecycle = contract.get("model_and_runtime_lifecycle")
    if not isinstance(model_lifecycle, dict):
        errors.append("model_and_runtime_lifecycle must be an object")
        model_lifecycle = {}
    _strings(
        model_lifecycle.get("identity_fields"),
        label="model_and_runtime_lifecycle.identity_fields",
        errors=errors,
        minimum=10,
    )
    _strings(
        model_lifecycle.get("model_fleet"),
        label="model_and_runtime_lifecycle.model_fleet",
        errors=errors,
        minimum=6,
    )
    for field in (
        "rule",
        "provider_independence",
        "compatibility_matrix",
        "fallback_rule",
    ):
        value = model_lifecycle.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"model_and_runtime_lifecycle.{field} must be non-empty")

    data_lifecycle = contract.get("data_and_evaluation_lifecycle")
    if not isinstance(data_lifecycle, dict):
        errors.append("data_and_evaluation_lifecycle must be an object")
        data_lifecycle = {}
    _strings(
        data_lifecycle.get("dataset_identity"),
        label="data_and_evaluation_lifecycle.dataset_identity",
        errors=errors,
        minimum=10,
    )
    _strings(
        data_lifecycle.get("evaluation_identity"),
        label="data_and_evaluation_lifecycle.evaluation_identity",
        errors=errors,
        minimum=8,
    )
    _strings(
        data_lifecycle.get("partition_rules"),
        label="data_and_evaluation_lifecycle.partition_rules",
        errors=errors,
        minimum=6,
    )
    _strings(
        data_lifecycle.get("lifecycle"),
        label="data_and_evaluation_lifecycle.lifecycle",
        errors=errors,
        minimum=10,
    )

    portability = contract.get("compatibility_and_portability")
    if not isinstance(portability, dict):
        errors.append("compatibility_and_portability must be an object")
        portability = {}
    _strings(
        portability.get("dimensions"),
        label="compatibility_and_portability.dimensions",
        errors=errors,
        minimum=8,
    )
    if portability.get("portability_states") != [
        "PORTABLE",
        "CONDITIONAL",
        "NON_PORTABLE",
        "UNKNOWN",
    ]:
        errors.append("compatibility portability state model drifted")
    if portability.get("default") != "UNKNOWN":
        errors.append("compatibility portability default must be UNKNOWN")
    for field in ("rule", "hardware_rule", "os_arch_rule", "downgrade_rule"):
        value = portability.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"compatibility_and_portability.{field} must be non-empty")

    prompt_supply = contract.get("policy_and_prompt_supply_chain")
    if not isinstance(prompt_supply, dict):
        errors.append("policy_and_prompt_supply_chain must be an object")
        prompt_supply = {}
    _strings(
        prompt_supply.get("governed_artifacts"),
        label="policy_and_prompt_supply_chain.governed_artifacts",
        errors=errors,
        minimum=8,
    )
    _strings(
        prompt_supply.get("requirements"),
        label="policy_and_prompt_supply_chain.requirements",
        errors=errors,
        minimum=8,
    )
    for field in ("dynamic_generation_rule", "rollback_rule"):
        value = prompt_supply.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"policy_and_prompt_supply_chain.{field} must be non-empty")

    hardware = contract.get("hardware_aware_execution")
    if not isinstance(hardware, dict):
        errors.append("hardware_aware_execution must be an object")
        hardware = {}
    _strings(
        hardware.get("targets"),
        label="hardware_aware_execution.targets",
        errors=errors,
        minimum=4,
    )
    _strings(
        hardware.get("scheduler_inputs"),
        label="hardware_aware_execution.scheduler_inputs",
        errors=errors,
        minimum=8,
    )
    for field in (
        "discovery_rule",
        "memory_rule",
        "fallback_rule",
        "evidence_rule",
    ):
        value = hardware.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"hardware_aware_execution.{field} must be non-empty")

    evaluator = contract.get("evaluator_independence")
    if not isinstance(evaluator, dict):
        errors.append("evaluator_independence must be an object")
        evaluator = {}
    evaluator_tiers = _objects(
        evaluator.get("tiers"),
        label="evaluator_independence.tiers",
        errors=errors,
        minimum=4,
    )
    tier_map = _ids(
        evaluator_tiers,
        label="evaluator_independence.tiers",
        errors=errors,
    )
    if set(tier_map) != {"E0", "E1", "E2", "E3"}:
        errors.append("evaluator independence tier set drifted")
    for tier_id, tier in tier_map.items():
        for field in ("meaning", "use"):
            value = tier.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"evaluator_independence.tiers[{tier_id}].{field} "
                    "must be non-empty"
                )
    for field in ("rule", "conflict_rule", "calibration_rule"):
        value = evaluator.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"evaluator_independence.{field} must be non-empty")

    implementation_contract = contract.get("level_implementation_contract")
    if not isinstance(implementation_contract, dict):
        errors.append("level_implementation_contract must be an object")
        implementation_contract = {}
    _strings(
        implementation_contract.get("required_fields"),
        label="level_implementation_contract.required_fields",
        errors=errors,
        minimum=15,
    )
    for field in (
        "owner_rule",
        "runtime_rule",
        "state_rule",
        "authority_rule",
        "disable_rule",
        "deprecation_rule",
    ):
        value = implementation_contract.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"level_implementation_contract.{field} must be non-empty"
            )

    operational = contract.get("operational_readiness")
    if not isinstance(operational, dict):
        errors.append("operational_readiness must be an object")
        operational = {}
    _strings(
        operational.get("per_level_required"),
        label="operational_readiness.per_level_required",
        errors=errors,
        minimum=10,
    )
    _strings(
        operational.get("stratum_gate_required"),
        label="operational_readiness.stratum_gate_required",
        errors=errors,
        minimum=7,
    )
    value = operational.get("production_rule")
    if not isinstance(value, str) or not value.strip():
        errors.append("operational_readiness.production_rule must be non-empty")

    deprecation = contract.get("deprecation_and_migration")
    if not isinstance(deprecation, dict):
        errors.append("deprecation_and_migration must be an object")
        deprecation = {}
    if deprecation.get("states") != [
        "ACTIVE",
        "DEPRECATED",
        "MIGRATING",
        "RETIRED",
    ]:
        errors.append("deprecation/migration state model drifted")
    _strings(
        deprecation.get("rules"),
        label="deprecation_and_migration.rules",
        errors=errors,
        minimum=6,
    )
    value = deprecation.get("evidence_rule")
    if not isinstance(value, str) or not value.strip():
        errors.append("deprecation_and_migration.evidence_rule must be non-empty")

    dependency_integrity = contract.get("dependency_integrity")
    if not isinstance(dependency_integrity, dict):
        errors.append("dependency_integrity must be an object")
        dependency_integrity = {}
    _strings(
        dependency_integrity.get("rules"),
        label="dependency_integrity.rules",
        errors=errors,
        minimum=6,
    )
    for field in ("shadow_authority_detector", "circularity_rule"):
        value = dependency_integrity.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"dependency_integrity.{field} must be non-empty")

    profiles = contract.get("level_control_profiles")
    if not isinstance(profiles, dict):
        errors.append("level_control_profiles must be an object")
        profiles = {}
    if set(profiles) != EXPECTED_STRATA:
        errors.append("level control profile set must be S01 through S10")
    for sid in EXPECTED_STRATA:
        profile = profiles.get(sid, {})
        if not isinstance(profile, dict):
            errors.append(f"{sid} control profile must be an object")
            continue
        for field in ("runtime_posture", "default_disable", "operator_priority"):
            value = profile.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{sid} control profile {field} must be non-empty")

    blueprints = _objects(
        contract.get("level_blueprints"),
        label="level_blueprints",
        errors=errors,
        minimum=100,
    )
    if len(blueprints) != 100:
        errors.append("advanced AI structure must contain exactly 100 level blueprints")
    blueprint_map = _ids(
        blueprints,
        label="level_blueprints",
        errors=errors,
    )
    expected_blueprint_ids = {f"ADV-L{i:03d}" for i in range(1, 101)}
    if set(blueprint_map) != expected_blueprint_ids:
        errors.append("level blueprint IDs must be exactly ADV-L001 through ADV-L100")
    for index in range(1, 101):
        level_id = f"L{index:03d}"
        blueprint_id = f"ADV-{level_id}"
        blueprint = blueprint_map.get(blueprint_id, {})
        level = level_map.get(level_id, {})
        if blueprint.get("level_id") != level_id:
            errors.append(f"{blueprint_id}.level_id must be {level_id}")
        if blueprint.get("ordinal") != index:
            errors.append(f"{blueprint_id}.ordinal must be {index}")
        if blueprint.get("stratum") != level.get("stratum"):
            errors.append(f"{blueprint_id}.stratum must match {level_id}")
        if blueprint.get("title") != level.get("title"):
            errors.append(f"{blueprint_id}.title must match {level_id}")
        owner = blueprint.get("primary_owner_plane")
        if owner not in set(level.get("required_planes") or []):
            errors.append(
                f"{blueprint_id}.primary_owner_plane must be in level required planes"
            )
        collaborators = _strings(
            blueprint.get("collaborating_planes"),
            label=f"{blueprint_id}.collaborating_planes",
            errors=errors,
            minimum=0,
        )
        if owner in collaborators:
            errors.append(
                f"{blueprint_id}.primary_owner_plane cannot also be collaborator"
            )
        if set(collaborators) | ({owner} if isinstance(owner, str) else set()) != set(
            level.get("required_planes") or []
        ):
            errors.append(
                f"{blueprint_id} owner/collaborator planes must cover the level plane set"
            )
        for field in (
            "implementation_mode",
            "entry_gate",
            "rollout_mode",
            "rollback_mode",
            "promotion_result",
        ):
            value = blueprint.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{blueprint_id}.{field} must be non-empty")
        _strings(
            blueprint.get("build_contract"),
            label=f"{blueprint_id}.build_contract",
            errors=errors,
            minimum=5,
        )
        _strings(
            blueprint.get("adversarial_focus"),
            label=f"{blueprint_id}.adversarial_focus",
            errors=errors,
            minimum=5,
        )
        _strings(
            blueprint.get("exit_gate"),
            label=f"{blueprint_id}.exit_gate",
            errors=errors,
            minimum=7,
        )

    blueprint_rules = contract.get("blueprint_rules")
    if not isinstance(blueprint_rules, dict):
        errors.append("blueprint_rules must be an object")
        blueprint_rules = {}
    for field in (
        "count_rule",
        "owner_rule",
        "collaboration_rule",
        "build_rule",
        "rollout_rule",
        "adversarial_rule",
        "closure_rule",
    ):
        value = blueprint_rules.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"blueprint_rules.{field} must be non-empty")

    risk_policy = contract.get("risk_and_freshness_policy")
    if not isinstance(risk_policy, dict):
        errors.append("risk_and_freshness_policy must be an object")
        risk_policy = {}
    risk_classes = _objects(
        risk_policy.get("classes"),
        label="risk_and_freshness_policy.classes",
        errors=errors,
        minimum=3,
    )
    risk_map = _ids(
        risk_classes,
        label="risk_and_freshness_policy.classes",
        errors=errors,
    )
    if set(risk_map) != {"standard", "high", "critical"}:
        errors.append("risk class set must be standard/high/critical")
    expected_ages = {"standard": 30, "high": 14, "critical": 7}
    for risk_id, expected_age in expected_ages.items():
        risk = risk_map.get(risk_id, {})
        if risk.get("maximum_evidence_age_days") != expected_age:
            errors.append(
                f"{risk_id} maximum_evidence_age_days must be {expected_age}"
            )
        _strings(
            risk.get("required_evidence"),
            label=f"risk classes[{risk_id}].required_evidence",
            errors=errors,
            minimum=3 if risk_id == "standard" else 6,
        )
        _strings(
            risk.get("change_requalification"),
            label=f"risk classes[{risk_id}].change_requalification",
            errors=errors,
            minimum=3,
        )
    defaults = risk_policy.get("stratum_defaults")
    if not isinstance(defaults, dict):
        errors.append("risk_and_freshness_policy.stratum_defaults must be object")
        defaults = {}
    if set(defaults) != EXPECTED_STRATA:
        errors.append("risk stratum defaults must cover S01 through S10")
    for sid, risk_id in defaults.items():
        if risk_id not in {"standard", "high", "critical"}:
            errors.append(f"{sid} has invalid risk class {risk_id}")
    for field in ("gate_rule", "freshness_rule", "change_rule"):
        value = risk_policy.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"risk_and_freshness_policy.{field} must be non-empty")

    evidence_profiles = contract.get("promotion_evidence_profiles")
    if not isinstance(evidence_profiles, dict):
        errors.append("promotion_evidence_profiles must be an object")
        evidence_profiles = {}
    if set(evidence_profiles) != {"standard", "high", "critical"}:
        errors.append("promotion evidence profiles must match risk classes")
    for risk_id in ("standard", "high", "critical"):
        profile = evidence_profiles.get(risk_id, {})
        if not isinstance(profile, dict):
            errors.append(f"promotion evidence profile {risk_id} must be object")
            continue
        _strings(
            profile.get("requires"),
            label=f"promotion_evidence_profiles.{risk_id}.requires",
            errors=errors,
            minimum=4,
        )
        if not isinstance(profile.get("independent_review"), bool):
            errors.append(
                f"promotion_evidence_profiles.{risk_id}.independent_review "
                "must be boolean"
            )
        value = profile.get("fault_injection")
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"promotion_evidence_profiles.{risk_id}.fault_injection "
                "must be non-empty"
            )

    evidence_status = contract.get("evidence_status_model")
    if not isinstance(evidence_status, dict):
        errors.append("evidence_status_model must be an object")
        evidence_status = {}
    if evidence_status.get("statuses") != [
        "CURRENT",
        "STALE",
        "INVALIDATED",
        "MISSING",
        "SUPERSEDED",
    ]:
        errors.append("evidence status model drifted")
    for field in (
        "current_rule",
        "stale_rule",
        "invalidated_rule",
        "superseded_rule",
        "missing_rule",
    ):
        value = evidence_status.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"evidence_status_model.{field} must be non-empty")

    dimensions = _objects(
        contract.get("maturity_dimensions"),
        label="maturity_dimensions",
        errors=errors,
        minimum=15,
    )
    dimension_map = _ids(
        dimensions,
        label="maturity_dimensions",
        errors=errors,
    )
    expected_dimensions = {
        "correctness",
        "calibration",
        "safety",
        "security",
        "authority_integrity",
        "provenance",
        "reliability",
        "recoverability",
        "efficiency",
        "adaptation",
        "autonomy_control",
        "human_control",
        "observability",
        "governance",
        "generalization",
    }
    if set(dimension_map) != expected_dimensions:
        errors.append("advanced AI maturity dimension set drifted")
    for dimension_id, dimension in dimension_map.items():
        for field in ("description", "measurement"):
            value = dimension.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"maturity_dimensions[{dimension_id}].{field} must be non-empty"
                )

    maturity_requirements = _objects(
        contract.get("stratum_maturity_requirements"),
        label="stratum_maturity_requirements",
        errors=errors,
        minimum=10,
    )
    if len(maturity_requirements) != 10:
        errors.append("exactly 10 stratum maturity requirement entries are required")
    seen_maturity_strata: set[str] = set()
    for index, requirement in enumerate(maturity_requirements, start=1):
        expected_stratum = f"S{index:02d}"
        expected_gate = f"L{index * 10:03d}"
        if requirement.get("stratum") != expected_stratum:
            errors.append(
                f"stratum_maturity_requirements[{index - 1}].stratum "
                f"must be {expected_stratum}"
            )
        else:
            seen_maturity_strata.add(expected_stratum)
        if requirement.get("gate_level") != expected_gate:
            errors.append(
                f"{expected_stratum} maturity gate must be {expected_gate}"
            )
        required_dimensions = set(
            _strings(
                requirement.get("required_dimensions"),
                label=f"{expected_stratum}.required_dimensions",
                errors=errors,
                minimum=10,
            )
        )
        if required_dimensions - expected_dimensions:
            errors.append(
                f"{expected_stratum} references unknown maturity dimensions"
            )
        for mandatory in (
            "correctness",
            "safety",
            "security",
            "authority_integrity",
            "provenance",
            "reliability",
            "recoverability",
            "efficiency",
            "observability",
            "governance",
        ):
            if mandatory not in required_dimensions:
                errors.append(
                    f"{expected_stratum} missing mandatory maturity dimension {mandatory}"
                )
        for field in ("promotion_evidence_rule", "aggregation_rule"):
            value = requirement.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{expected_stratum}.{field} must be non-empty"
                )
        _strings(
            requirement.get("critical_zero_tolerance"),
            label=f"{expected_stratum}.critical_zero_tolerance",
            errors=errors,
            minimum=5,
        )
    if seen_maturity_strata != EXPECTED_STRATA:
        errors.append("stratum maturity coverage must be S01 through S10")

    inheritance = contract.get("evidence_inheritance")
    if not isinstance(inheritance, dict):
        errors.append("evidence_inheritance must be an object")
        inheritance = {}
    for field in ("rule", "reuse_rule"):
        value = inheritance.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"evidence_inheritance.{field} must be non-empty")
    _strings(
        inheritance.get("immutable_links"),
        label="evidence_inheritance.immutable_links",
        errors=errors,
        minimum=7,
    )
    _strings(
        inheritance.get("invalidators"),
        label="evidence_inheritance.invalidators",
        errors=errors,
        minimum=6,
    )

    ceiling = contract.get("capability_ceiling_control")
    if not isinstance(ceiling, dict):
        errors.append("capability_ceiling_control must be an object")
        ceiling = {}
    _strings(
        ceiling.get("sources"),
        label="capability_ceiling_control.sources",
        errors=errors,
        minimum=6,
    )
    _strings(
        ceiling.get("enforcement_points"),
        label="capability_ceiling_control.enforcement_points",
        errors=errors,
        minimum=6,
    )
    for field in ("effective_ceiling", "downgrade_rule", "reporting_rule"):
        value = ceiling.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"capability_ceiling_control.{field} must be non-empty")

    kill_controls = contract.get("kill_and_suspend_controls")
    if not isinstance(kill_controls, dict):
        errors.append("kill_and_suspend_controls must be an object")
        kill_controls = {}
    control_levels = _objects(
        kill_controls.get("levels"),
        label="kill_and_suspend_controls.levels",
        errors=errors,
        minimum=6,
    )
    expected_scopes = {
        "operation",
        "tenant",
        "capability",
        "provider-or-tool",
        "release",
        "global-frontier",
    }
    observed_scopes = {
        item.get("scope")
        for item in control_levels
        if isinstance(item.get("scope"), str)
    }
    if observed_scopes != expected_scopes:
        errors.append("kill/suspend scope set drifted")
    for index, item in enumerate(control_levels):
        value = item.get("effect")
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"kill_and_suspend_controls.levels[{index}].effect must be non-empty"
            )
    _strings(
        kill_controls.get("invariants"),
        label="kill_and_suspend_controls.invariants",
        errors=errors,
        minimum=5,
    )

    _strings(
        contract.get("anti_gaming_rules"),
        label="anti_gaming_rules",
        errors=errors,
        minimum=8,
    )

    experiment = contract.get("frontier_experiment_boundary")
    if not isinstance(experiment, dict):
        errors.append("frontier_experiment_boundary must be an object")
        experiment = {}
    for field in ("isolation", "recursion_rule"):
        value = experiment.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"frontier_experiment_boundary.{field} must be non-empty")
    _strings(
        experiment.get("allowed"),
        label="frontier_experiment_boundary.allowed",
        errors=errors,
        minimum=5,
    )
    _strings(
        experiment.get("prohibited_without_external_authority"),
        label="frontier_experiment_boundary.prohibited_without_external_authority",
        errors=errors,
        minimum=6,
    )
    promotion_chain = _strings(
        experiment.get("promotion_chain"),
        label="frontier_experiment_boundary.promotion_chain",
        errors=errors,
        minimum=6,
    )
    if promotion_chain and promotion_chain[-1] != "rollback-ready deployment":
        errors.append(
            "frontier experiment promotion chain must end in rollback-ready deployment"
        )

    state_machine = contract.get("promotion_state_machine")
    if not isinstance(state_machine, dict):
        errors.append("promotion_state_machine must be an object")
        state_machine = {}
    expected_states = [
        "PLANNED",
        "CONTRACT_READY",
        "IMPLEMENTED_CANDIDATE",
        "QUALIFIED",
        "PROMOTED",
        "SUSPENDED",
        "ROLLED_BACK",
    ]
    if state_machine.get("states") != expected_states:
        errors.append("advanced AI promotion states drifted")
    if state_machine.get("initial") != "PLANNED":
        errors.append("advanced AI promotion initial state must be PLANNED")
    transitions = _objects(
        state_machine.get("transitions"),
        label="promotion_state_machine.transitions",
        errors=errors,
        minimum=8,
    )
    known_states = set(expected_states)
    for index, transition in enumerate(transitions):
        source = transition.get("from")
        target = transition.get("to")
        if source not in known_states or target not in known_states:
            errors.append(
                f"promotion_state_machine.transitions[{index}] references unknown state"
            )
        _strings(
            transition.get("requires"),
            label=f"promotion_state_machine.transitions[{index}].requires",
            errors=errors,
            minimum=1,
        )
    for field in ("contiguous_rule", "invalidation_rule", "production_rule"):
        value = state_machine.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"promotion_state_machine.{field} must be non-empty")

    bridges = _objects(
        contract.get("cross_stratum_bridges"),
        label="cross_stratum_bridges",
        errors=errors,
        minimum=10,
    )
    bridge_map = _ids(bridges, label="cross_stratum_bridges", errors=errors)
    expected_bridge_ids = {f"B{i:02d}" for i in range(1, 11)}
    if set(bridge_map) != expected_bridge_ids:
        errors.append("cross-stratum bridge set must be B01 through B10")
    for index in range(1, 11):
        bridge = bridge_map.get(f"B{index:02d}", {})
        expected_from = f"S{index:02d}"
        expected_to = "S01" if index == 10 else f"S{index + 1:02d}"
        if bridge.get("from") != expected_from:
            errors.append(f"B{index:02d}.from must be {expected_from}")
        if bridge.get("to") != expected_to:
            errors.append(f"B{index:02d}.to must be {expected_to}")
        contract_text = bridge.get("contract")
        if not isinstance(contract_text, str) or not contract_text.strip():
            errors.append(f"B{index:02d}.contract must be non-empty")

    profiles = _objects(
        contract.get("activation_profiles"),
        label="activation_profiles",
        errors=errors,
        minimum=4,
    )
    profile_map = _ids(
        profiles,
        label="activation_profiles",
        errors=errors,
    )
    expected_profiles = {
        "advanced-assistant": "L050",
        "enterprise-agent-system": "L080",
        "scientific-intelligence": "L090",
        "frontier-governed-system": "L100",
    }
    if set(profile_map) != set(expected_profiles):
        errors.append("advanced AI activation profile set drifted")
    for profile_id, ceiling in expected_profiles.items():
        profile = profile_map.get(profile_id, {})
        if profile.get("target_ceiling") != ceiling:
            errors.append(
                f"activation profile {profile_id} target ceiling must be {ceiling}"
            )
        for field in ("description", "rule"):
            value = profile.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"activation profile {profile_id}.{field} must be non-empty"
                )

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
        *INTEGRATION_FILES,
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
