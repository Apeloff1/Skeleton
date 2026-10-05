#!/usr/bin/env python3
"""Independent repository verifier for VOL-074 Education & Teaching."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/ai_education_contract.json"
RUNTIME = ROOT / "skeleton/education/learning.py"
PACKAGE = ROOT / "skeleton/education/__init__.py"
TESTS = ROOT / "tests/test_vol074_education_intelligence.py"
WORKFLOW = ROOT / ".github/workflows/vol074-education-intelligence.yml"


def _load():
    spec = importlib.util.spec_from_file_location("vol074_learning_verify", RUNTIME)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load VOL-074 runtime")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate() -> list[str]:
    errors: list[str] = []
    for path in (MANIFEST, RUNTIME, PACKAGE, TESTS, WORKFLOW):
        if not path.is_file():
            errors.append(f"required VOL-074 surface missing: {path.relative_to(ROOT)}")
    if errors:
        return errors

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("education contract schema_version must be 1")
    if payload.get("volume") != "VOL-074":
        errors.append("education contract must bind VOL-074")
    if payload.get("status") != "implementation_contract":
        errors.append("education contract must remain implementation_contract before promotion")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("education policy must be an object")
    else:
        for key in ("evidence_rule", "planning_rule", "outcome_rule"):
            if not isinstance(policy.get(key), str) or not policy[key].strip():
                errors.append(f"education policy missing {key}")

    objectives = payload.get("objectives")
    if not isinstance(objectives, list) or len(objectives) < 2:
        errors.append("education contract requires a nontrivial objective graph")

    forbidden = payload.get("forbidden_promotion_signals")
    required_forbidden = {
        "click-count",
        "dwell-time",
        "message-count",
        "session-length",
    }
    if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
        errors.append("engagement-only promotion signals are not fully forbidden")

    module = _load()
    required_exports = {
        "EDUCATION_SCHEMA",
        "EducationContractError",
        "EvidenceKind",
        "InstructionKind",
        "InstructionPlan",
        "InstructionPlanner",
        "InstructionStep",
        "LearnerEvidence",
        "LearnerState",
        "LearningObjective",
        "LearningObjectiveGraph",
        "LearningOutcomeEvaluation",
        "ObjectiveBelief",
        "OutcomeBinding",
        "OutcomeDecision",
        "OutcomeEvaluator",
        "OutcomeVerdict",
    }
    if set(module.__all__) != required_exports:
        errors.append("VOL-074 public export contract drift")

    try:
        graph = module.LearningObjectiveGraph(
            tuple(
                module.LearningObjective(
                    objective_id=item["objective_id"],
                    description=item["description"],
                    prerequisites=tuple(item["prerequisites"]),
                    mastery_threshold=item["mastery_threshold"],
                    uncertainty_ceiling=item["uncertainty_ceiling"],
                )
                for item in objectives
            )
        )
        state = graph.estimate(
            learner_id="verifier-learner",
            evidence=(),
            generated_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        )
        if any(belief.record_class != "inference" for belief in state.beliefs):
            errors.append("learner-state beliefs escaped inference class")
        if any(belief.can_masquerade_as_observed_evidence for belief in state.beliefs):
            errors.append("inferred learner state can masquerade as observed evidence")

        binding_payload = payload["outcome_binding"]
        binding = module.OutcomeBinding(**binding_payload)
        planner = module.InstructionPlanner(graph, outcome_binding=binding)
        target = objectives[-1]["objective_id"]
        plan = planner.plan(
            plan_id="verifier-plan",
            state=state,
            target_objective_id=target,
        )
        planner.verify(plan)
        if not any(step.kind is module.InstructionKind.ASSESSMENT for step in plan.steps):
            errors.append("instruction plan lacks outcome assessment step")

        outcome_fields = set(module.LearningOutcomeEvaluation.__dataclass_fields__)
        if {"click_count", "dwell_time", "message_count", "session_length"} & outcome_fields:
            errors.append("engagement metric leaked into outcome contract")
    except Exception as exc:
        errors.append(f"education smoke contract failed: {exc}")

    implementation = payload.get("implementation", {})
    expected = {
        "runtime": "skeleton/education/learning.py",
        "package": "skeleton/education/__init__.py",
        "tests": "tests/test_vol074_education_intelligence.py",
        "verifier": "scripts/check_vol074_education_intelligence.py",
        "workflow": ".github/workflows/vol074-education-intelligence.yml",
    }
    if implementation != expected:
        errors.append("education implementation path binding drift")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-074 ERROR: {error}")
        return 1
    print(
        "VOL-074 OK: observed/inferred separation, objective DAG, uncertainty-aware "
        "planning, independent outcome ownership, and anti-engagement promotion policy verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
