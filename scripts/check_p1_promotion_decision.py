#!/usr/bin/env python3
"""Validate the P1-PROM-03 independent signed promotion policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_promotion_decision_policy.json")
EXECUTION_MAP_PATH = Path("machine/ai_p1_execution_map.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
PROM02_POLICY_PATH = Path("machine/p1_terminal_failure_journeys.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")

EXPECTED_TASK = "P1-PROM-03"
EXPECTED_ACCOUNTABILITY = "ACC-P1-PROM-03"
EXPECTED_DEPENDENCIES = ["P1-PROM-02"]
EXPECTED_PHASES = ["implementation", "verification"]
EXPECTED_ROLES = {
    "implementation": "promotion-implementation",
    "verification": "independent-promotion-verification",
}
EXPECTED_SIGNER_TYPES = ["human", "agent", "ci", "service"]
EXPECTED_SIGNATURE_METHODS = [
    "github_identity",
    "git_gpg",
    "git_ssh",
    "sigstore",
    "ci_oidc",
]
EXPECTED_SIGNATURE_REF_METHODS = [
    "git_gpg",
    "git_ssh",
    "sigstore",
    "ci_oidc",
]
EXPECTED_IMPLEMENTATION_PATHS = {
    "machine/p1_promotion_decision_policy.json",
    "skeleton/contracts/p1_promotion_decision.py",
    "skeleton/ai/runtime/contracts/p1_promotion_decision.py",
    "scripts/check_p1_promotion_decision.py",
    "scripts/build_p1_promotion_decision.py",
    "scripts/emit_p1_promotion_attestation.py",
    ".github/workflows/p1-signed-promotion-decision.yml",
}
EXPECTED_TEST_TARGETS = {
    "skeleton/testing/test_p1_promotion_decision.py",
    "tests/test_p1_promotion_decision_policy.py",
}
_NUMERIC_DEFERRED_CLAIM = re.compile(r"\bdeferred\s+\d+[\s-]*volume", re.IGNORECASE)


class PromotionDecisionPolicyError(RuntimeError):
    """PROM-03 policy is malformed or inconsistent."""


def _load(root: Path, path: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionDecisionPolicyError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise PromotionDecisionPolicyError(f"{path} must contain an object")
    return value


def validate_repository(
    root: Path = ROOT,
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    policy = _load(root, policy_path)
    execution_map = _load(root, EXECUTION_MAP_PATH)
    backlog = _load(root, BACKLOG_PATH)
    prom02 = _load(root, PROM02_POLICY_PATH)
    master_plan = _load(root, MASTER_PLAN_PATH)

    errors: list[str] = []

    if policy.get("schema_version") != 1:
        errors.append("PROM-03 schema_version must equal 1")
    if policy.get("task_id") != EXPECTED_TASK:
        errors.append("PROM-03 policy task identity drift")
    if policy.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        errors.append("PROM-03 policy accountability drift")
    if policy.get("promotion_scope") != "bounded_p1_frontier":
        errors.append("PROM-03 promotion scope must remain bounded_p1_frontier")
    if policy.get("p1_promotion_authority") is not True:
        errors.append("PROM-03 must carry bounded P1 promotion authority")
    if policy.get("masterplan_maturity_authority") is not False:
        errors.append("PROM-03 must not carry masterplan maturity authority")

    for key in (
        "require_exact_head",
        "require_prom02_acceptance",
        "require_prom01_promotion_ready",
        "require_independent_signers",
        "require_distinct_verifier_digests",
        "require_identical_evidence_digest",
    ):
        if policy.get(key) is not True:
            errors.append(f"PROM-03 {key} must be true")

    if policy.get("required_signoff_phases") != EXPECTED_PHASES:
        errors.append("PROM-03 required signoff phases drift")
    if policy.get("required_roles") != EXPECTED_ROLES:
        errors.append("PROM-03 required signer roles drift")
    if policy.get("allowed_signer_types") != EXPECTED_SIGNER_TYPES:
        errors.append("PROM-03 signer type allowlist drift")
    if policy.get("allowed_signature_methods") != EXPECTED_SIGNATURE_METHODS:
        errors.append("PROM-03 signature method allowlist drift")
    if policy.get("signature_ref_required_for") != EXPECTED_SIGNATURE_REF_METHODS:
        errors.append("PROM-03 signature-ref requirement drift")

    rejection = policy.get("rejection_policy")
    if not isinstance(rejection, dict):
        errors.append("PROM-03 rejection_policy must be an object")
    else:
        for key in (
            "explicit_rejection_is_valid",
            "missing_or_invalid_signoff_rejects",
            "stale_head_rejects",
            "maturity_blocker_rejects",
            "scope_drift_rejects",
        ):
            if rejection.get(key) is not True:
                errors.append(f"PROM-03 rejection policy {key} must be true")
        if rejection.get("mutation_on_rejection") is not False:
            errors.append("PROM-03 rejection must not mutate maturity")

    scope = execution_map.get("scope_summary")
    if not isinstance(scope, dict):
        raise PromotionDecisionPolicyError("P1 execution map scope_summary missing")
    primary_count = scope.get("primary_p1_frontier_volume_count")
    deferred_count = scope.get("deferred_volume_count")
    masterplan_count = scope.get("masterplan_volume_count")
    deferred_refs = scope.get("deferred_volume_refs")
    if (
        isinstance(primary_count, bool)
        or not isinstance(primary_count, int)
        or primary_count < 1
    ):
        errors.append("P1 primary volume count must be positive integer")
    if (
        isinstance(deferred_count, bool)
        or not isinstance(deferred_count, int)
        or deferred_count < 1
    ):
        errors.append("P1 deferred volume count must be positive integer")
    if (
        isinstance(masterplan_count, bool)
        or not isinstance(masterplan_count, int)
        or masterplan_count < 1
    ):
        errors.append("masterplan volume count must be positive integer")
    if not isinstance(deferred_refs, list) or any(
        not isinstance(item, str) or not item for item in (deferred_refs or [])
    ):
        errors.append("deferred_volume_refs must be non-empty string list")
        deferred_refs = []
    if len(set(deferred_refs)) != len(deferred_refs):
        errors.append("deferred_volume_refs must be unique")
    if isinstance(deferred_count, int) and deferred_count != len(deferred_refs):
        errors.append("deferred volume count must equal deferred ref count")
    if (
        isinstance(primary_count, int)
        and isinstance(deferred_count, int)
        and isinstance(masterplan_count, int)
        and primary_count + deferred_count != masterplan_count
    ):
        errors.append("primary plus deferred count must equal masterplan count")

    volumes = master_plan.get("volumes")
    if not isinstance(volumes, list):
        errors.append("master plan volumes must be a list")
    elif isinstance(masterplan_count, int) and len(volumes) != masterplan_count:
        errors.append("execution-map masterplan count must equal master plan volume count")

    deferred_policy = policy.get("deferred_scope_contract")
    if not isinstance(deferred_policy, dict):
        errors.append("PROM-03 deferred_scope_contract must be an object")
    else:
        expected_sources = {
            "source": "machine/ai_p1_execution_map.json#scope_summary.deferred_volume_refs",
            "count_source": "machine/ai_p1_execution_map.json#scope_summary.deferred_volume_count",
            "masterplan_count_source": "machine/ai_p1_execution_map.json#scope_summary.masterplan_volume_count",
            "primary_count_source": "machine/ai_p1_execution_map.json#scope_summary.primary_p1_frontier_volume_count",
        }
        for key, expected in expected_sources.items():
            if deferred_policy.get(key) != expected:
                errors.append(f"PROM-03 deferred scope {key} drift")
        rule = deferred_policy.get("rule")
        if not isinstance(rule, str) or "hard-coded" not in rule:
            errors.append("PROM-03 deferred scope rule must forbid hard-coded promotion truth")

    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise PromotionDecisionPolicyError("P1 backlog tasks missing")
    terminal = next(
        (
            row
            for row in tasks
            if isinstance(row, dict) and row.get("task_id") == EXPECTED_TASK
        ),
        None,
    )
    if terminal is None:
        errors.append("P1-PROM-03 task missing from backlog")
    else:
        if terminal.get("depends_on") != EXPECTED_DEPENDENCIES:
            errors.append("P1-PROM-03 dependency identity drift")
        if terminal.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
            errors.append("P1-PROM-03 task accountability drift")
        if terminal.get("promotion_effect") != "terminal_candidate":
            errors.append("P1-PROM-03 promotion effect drift")
        acceptance = terminal.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            errors.append("P1-PROM-03 acceptance must be non-empty")
        else:
            joined = " ".join(str(item) for item in acceptance)
            if _NUMERIC_DEFERRED_CLAIM.search(joined):
                errors.append(
                    "P1-PROM-03 acceptance must not hard-code deferred volume count"
                )
            if "exact deferred-volume complement" not in joined:
                errors.append(
                    "P1-PROM-03 acceptance must bind exact deferred-volume complement"
                )
        if set(terminal.get("implementation_paths") or ()) != EXPECTED_IMPLEMENTATION_PATHS:
            errors.append("P1-PROM-03 implementation path inventory drift")
        if set(terminal.get("test_targets") or ()) != EXPECTED_TEST_TARGETS:
            errors.append("P1-PROM-03 test target inventory drift")

    if prom02.get("task_id") != "P1-PROM-02":
        errors.append("PROM-02 policy task identity drift")
    if prom02.get("accountability_ref") != "ACC-P1-PROM-02":
        errors.append("PROM-02 policy accountability drift")
    if prom02.get("promotion_authority") is not False:
        errors.append("PROM-02 unexpectedly carries promotion authority")
    if prom02.get("signed_promotion") is not False:
        errors.append("PROM-02 unexpectedly carries signed promotion")

    if errors:
        raise PromotionDecisionPolicyError("; ".join(errors))

    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "primary_volume_count": primary_count,
        "deferred_volume_count": deferred_count,
        "masterplan_volume_count": masterplan_count,
        "signoff_phase_count": len(EXPECTED_PHASES),
        "signature_method_count": len(EXPECTED_SIGNATURE_METHODS),
        "p1_promotion_authority": True,
        "masterplan_maturity_authority": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = validate_repository(ROOT, policy_path=args.policy)
    except PromotionDecisionPolicyError as exc:
        print(f"P1 promotion decision policy: rejected: {exc}", file=sys.stderr)
        return 1
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
