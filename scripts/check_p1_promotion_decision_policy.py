#!/usr/bin/env python3
"""Validate the terminal P1-PROM-03 promotion-decision policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_promotion_decision_policy.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
MAP_PATH = Path("machine/ai_p1_execution_map.json")
PROM02_POLICY_PATH = Path("machine/p1_terminal_failure_journeys.json")

EXPECTED_TASK = "P1-PROM-03"
EXPECTED_ACCOUNTABILITY = "ACC-P1-PROM-03"


class PromotionDecisionPolicyError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionDecisionPolicyError(
            f"cannot read {path}"
        ) from exc


def _strict_keys(
    row: dict[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise PromotionDecisionPolicyError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def validate_repository(
    root: Path = ROOT,
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    policy = _load(root / policy_path)
    backlog = _load(root / BACKLOG_PATH)
    execution_map = _load(root / MAP_PATH)
    prom02 = _load(root / PROM02_POLICY_PATH)

    if not isinstance(policy, dict):
        raise PromotionDecisionPolicyError(
            "policy root must be object"
        )
    _strict_keys(
        policy,
        {
            "schema_version",
            "task_id",
            "accountability_ref",
            "authority",
            "task_backlog_authority",
            "execution_map_authority",
            "prom02_policy_authority",
            "require_exact_head",
            "require_independent_signature_verification_for_promotion",
            "signature_method",
            "allow_unsigned_explicit_rejection",
            "signer_verifier_must_differ",
            "deferred_scope_must_match_execution_map",
            "maturity_mutation",
            "promotion_effect"
        },
        "policy",
    )
    if policy.get("schema_version") != 1:
        raise PromotionDecisionPolicyError(
            "schema_version must equal 1"
        )
    if policy.get("task_id") != EXPECTED_TASK:
        raise PromotionDecisionPolicyError("task_id drift")
    if policy.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise PromotionDecisionPolicyError(
            "accountability_ref drift"
        )
    if policy.get("authority") != str(POLICY_PATH):
        raise PromotionDecisionPolicyError(
            "authority path drift"
        )
    if policy.get("task_backlog_authority") != str(BACKLOG_PATH):
        raise PromotionDecisionPolicyError(
            "task backlog authority drift"
        )
    if policy.get("execution_map_authority") != str(MAP_PATH):
        raise PromotionDecisionPolicyError(
            "execution map authority drift"
        )
    if policy.get("prom02_policy_authority") != str(
        PROM02_POLICY_PATH
    ):
        raise PromotionDecisionPolicyError(
            "PROM-02 policy authority drift"
        )
    if policy.get("require_exact_head") is not True:
        raise PromotionDecisionPolicyError(
            "exact-head verification required"
        )
    if (
        policy.get(
            "require_independent_signature_verification_for_promotion"
        )
        is not True
    ):
        raise PromotionDecisionPolicyError(
            "independent signature verification required"
        )
    if policy.get("signature_method") != "ed25519":
        raise PromotionDecisionPolicyError(
            "signature method must be ed25519"
        )
    if policy.get("allow_unsigned_explicit_rejection") is not True:
        raise PromotionDecisionPolicyError(
            "unsigned explicit rejection must remain allowed"
        )
    if policy.get("signer_verifier_must_differ") is not True:
        raise PromotionDecisionPolicyError(
            "signer/verifier independence required"
        )
    if (
        policy.get("deferred_scope_must_match_execution_map")
        is not True
    ):
        raise PromotionDecisionPolicyError(
            "deferred scope must bind execution map"
        )
    if policy.get("maturity_mutation") is not False:
        raise PromotionDecisionPolicyError(
            "PROM-03 must not mutate maturity"
        )
    if policy.get("promotion_effect") != "terminal_candidate":
        raise PromotionDecisionPolicyError(
            "promotion effect drift"
        )

    tasks = backlog.get("tasks") if isinstance(backlog, dict) else None
    if not isinstance(tasks, list):
        raise PromotionDecisionPolicyError(
            "task backlog tasks missing"
        )
    task = next(
        (
            row
            for row in tasks
            if isinstance(row, dict)
            and row.get("task_id") == EXPECTED_TASK
        ),
        None,
    )
    if task is None:
        raise PromotionDecisionPolicyError(
            "PROM-03 task missing"
        )
    if task.get("depends_on") != ["P1-PROM-02"]:
        raise PromotionDecisionPolicyError(
            "PROM-03 dependency identity drift"
        )
    if task.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise PromotionDecisionPolicyError(
            "PROM-03 accountability drift"
        )
    acceptance = task.get("acceptance")
    if not isinstance(acceptance, list) or any(
        not isinstance(item, str) or not item
        for item in acceptance
    ):
        raise PromotionDecisionPolicyError(
            "PROM-03 acceptance missing"
        )
    if any("357-volume" in item for item in acceptance):
        raise PromotionDecisionPolicyError(
            "stale deferred-volume count remains in PROM-03 acceptance"
        )

    if not isinstance(execution_map, dict):
        raise PromotionDecisionPolicyError(
            "execution map root must be object"
        )
    scope = execution_map.get("scope_summary")
    if not isinstance(scope, dict):
        raise PromotionDecisionPolicyError(
            "execution map scope_summary missing"
        )
    refs = scope.get("deferred_volume_refs")
    count = scope.get("deferred_volume_count")
    total = scope.get("masterplan_volume_count")
    primary = scope.get("primary_p1_frontier_volume_count")
    if not isinstance(refs, list) or not refs:
        raise PromotionDecisionPolicyError(
            "deferred_volume_refs must be non-empty list"
        )
    if len(refs) != len(set(refs)):
        raise PromotionDecisionPolicyError(
            "deferred_volume_refs contain duplicates"
        )
    if not isinstance(count, int) or isinstance(count, bool):
        raise PromotionDecisionPolicyError(
            "deferred_volume_count must be integer"
        )
    if count != len(refs):
        raise PromotionDecisionPolicyError(
            "deferred volume count/list mismatch"
        )
    if (
        not isinstance(total, int)
        or not isinstance(primary, int)
        or total - primary != count
    ):
        raise PromotionDecisionPolicyError(
            "masterplan/primary/deferred scope arithmetic mismatch"
        )

    if not isinstance(prom02, dict):
        raise PromotionDecisionPolicyError(
            "PROM-02 policy root must be object"
        )
    if prom02.get("task_id") != "P1-PROM-02":
        raise PromotionDecisionPolicyError(
            "PROM-02 policy task drift"
        )
    if prom02.get("promotion_authority") is not False:
        raise PromotionDecisionPolicyError(
            "PROM-02 unexpectedly carries promotion authority"
        )
    if prom02.get("signed_promotion") is not False:
        raise PromotionDecisionPolicyError(
            "PROM-02 unexpectedly signs promotion"
        )

    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "deferred_volume_count": count,
        "masterplan_volume_count": total,
        "primary_p1_frontier_volume_count": primary,
        "signature_method": "ed25519",
        "maturity_mutation": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=POLICY_PATH,
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = validate_repository(
            ROOT,
            policy_path=args.policy,
        )
        if args.out is not None:
            args.out.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            args.out.write_text(
                json.dumps(
                    summary,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(
                json.dumps(
                    summary,
                    indent=2,
                    sort_keys=True,
                )
            )
        return 0
    except PromotionDecisionPolicyError as exc:
        print(
            f"P1 promotion decision policy: rejected: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
