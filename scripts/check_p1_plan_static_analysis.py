#!/usr/bin/env python3
"""Validate the P1-INTEL-05 plan-static-analysis authority and mirror."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_plan_static_analysis_policy.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
EXPECTED_TASK = "P1-INTEL-05"
EXPECTED_ACCOUNTABILITY = "ACC-P1-INTEL-05"
EXPECTED_DEPENDENCIES = {"P1-INTEL-03", "P1-EVID-04"}
EXPECTED_SEMANTICS = {
    "exact_reasoning_policy_digest_required": True,
    "capability_subset_required": True,
    "preconditions_required": True,
    "postconditions_required": True,
    "all_sinks_terminal": True,
    "terminal_steps_have_no_dependents": True,
    "cycle_free_dag_required": True,
    "aggregate_token_budget_required": True,
    "aggregate_cost_budget_required": True,
    "critical_path_wall_budget_required": True,
    "side_effect_compensation_required": True,
    "retries_require_idempotency": True,
    "rejected_decisions_cannot_emit_promotion_evidence": True,
}
EXPECTED_HARD_LIMITS = {
    "max_plan_steps": 1024,
    "max_retries_per_step": 32,
}


class PlanAnalysisPolicyError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanAnalysisPolicyError(f"cannot read {path}") from exc


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PlanAnalysisPolicyError(f"cannot read {path}") from exc


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    policy = _load(root / POLICY_PATH)
    backlog = _load(root / BACKLOG_PATH)
    if not isinstance(policy, dict) or not isinstance(backlog, dict):
        raise PlanAnalysisPolicyError("policy/backlog roots must be objects")

    if policy.get("schema_version") != 1:
        raise PlanAnalysisPolicyError("policy schema_version must equal 1")
    if policy.get("task_id") != EXPECTED_TASK:
        raise PlanAnalysisPolicyError("policy task_id drift")
    if policy.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise PlanAnalysisPolicyError("policy accountability_ref drift")
    if policy.get("semantics") != EXPECTED_SEMANTICS:
        raise PlanAnalysisPolicyError("plan analysis semantics drift")
    if policy.get("hard_limits") != EXPECTED_HARD_LIMITS:
        raise PlanAnalysisPolicyError("plan analysis hard limits drift")

    architecture = policy.get("architecture")
    expected_architecture = {
        "canonical_source_root": "skeleton/intelligence",
        "canonical_ai_mirror_root": "skeleton/ai/runtime/intelligence",
        "parallel_planning_root_allowed": False,
        "forbidden_parallel_root": "skeleton/planning",
    }
    if architecture != expected_architecture:
        raise PlanAnalysisPolicyError("plan analysis architecture policy drift")
    if (root / "skeleton/planning").exists():
        raise PlanAnalysisPolicyError(
            "parallel skeleton/planning authority appeared without architecture cutover"
        )

    source = root / str(policy.get("analyzer", ""))
    mirror = root / str(policy.get("mirror", ""))
    reasoning = root / str(policy.get("reasoning_policy_authority", ""))
    reasoning_mirror = root / "skeleton/ai/runtime/intelligence/strategy_registry.py"
    for path in (source, mirror, reasoning, reasoning_mirror):
        if not path.is_file():
            raise PlanAnalysisPolicyError(f"required authority file missing: {path}")
    source_digest = _sha256(source)
    mirror_digest = _sha256(mirror)
    if source_digest != mirror_digest:
        raise PlanAnalysisPolicyError("plan analyzer source/mirror parity drift")
    if _sha256(reasoning) != _sha256(reasoning_mirror):
        raise PlanAnalysisPolicyError("reasoning-policy source/mirror parity drift")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise PlanAnalysisPolicyError("P1 backlog tasks must be a list")
    matches = [
        row for row in tasks
        if isinstance(row, dict) and row.get("task_id") == EXPECTED_TASK
    ]
    if len(matches) != 1:
        raise PlanAnalysisPolicyError("P1-INTEL-05 backlog identity drift")
    task = matches[0]
    if task.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise PlanAnalysisPolicyError("P1-INTEL-05 backlog accountability drift")
    dependencies = task.get("depends_on")
    if not isinstance(dependencies, list) or set(dependencies) != EXPECTED_DEPENDENCIES:
        raise PlanAnalysisPolicyError("P1-INTEL-05 dependency drift")

    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "dependency_count": len(EXPECTED_DEPENDENCIES),
        "analyzer_digest": source_digest,
        "reasoning_policy_digest": _sha256(reasoning),
        "parallel_planning_root_present": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = validate_repository(ROOT)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except PlanAnalysisPolicyError as exc:
        print(f"P1 plan analysis: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
