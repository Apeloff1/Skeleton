#!/usr/bin/env python3
"""Validate the canonical P1-PROM-03 terminal promotion policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_terminal_promotion_policy.json")
BACKLOG_PATH = Path("machine/ai_p1_task_backlog.json")
PROM01_POLICY_PATH = Path("machine/p1_terminal_evidence_policy.json")
PROM02_POLICY_PATH = Path("machine/p1_terminal_failure_journeys.json")
EXPECTED_TASK = "P1-PROM-03"
EXPECTED_ACCOUNTABILITY = "ACC-P1-PROM-03"
EXPECTED_DEPENDENCIES = ["P1-PROM-02"]
EXPECTED_SIGNER_TYPES = ["human", "ci", "service"]
EXPECTED_SIGNATURE_METHODS = [
    "ci_oidc",
    "git_gpg",
    "git_ssh",
    "github_identity",
    "sigstore",
]


class TerminalPromotionPolicyError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalPromotionPolicyError(f"cannot read {path}") from exc


def _strict_keys(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise TerminalPromotionPolicyError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def validate_repository(
    root: Path = ROOT,
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    policy = _load(root / policy_path)
    backlog = _load(root / BACKLOG_PATH)
    prom01 = _load(root / PROM01_POLICY_PATH)
    prom02 = _load(root / PROM02_POLICY_PATH)

    if not isinstance(policy, dict):
        raise TerminalPromotionPolicyError("policy root must be object")
    _strict_keys(
        policy,
        {
            "schema_version",
            "task_id",
            "accountability_ref",
            "authority",
            "task_backlog_authority",
            "prom01_policy_authority",
            "prom02_policy_authority",
            "require_exact_head",
            "require_independent_verifier",
            "external_signature_required_for_promotion",
            "allow_explicit_rejection_without_signature",
            "ci_may_generate_promotion_signature",
            "allowed_signer_types",
            "forbidden_signer_types",
            "allowed_signature_methods",
            "signature_ref_required_methods",
            "implementation_signer_id",
            "promotion_requires",
            "rejection_requires",
        },
        "policy",
    )
    if policy.get("schema_version") != 1:
        raise TerminalPromotionPolicyError("schema_version must equal 1")
    if policy.get("task_id") != EXPECTED_TASK:
        raise TerminalPromotionPolicyError("task_id drift")
    if policy.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise TerminalPromotionPolicyError("accountability_ref drift")
    if policy.get("authority") != str(POLICY_PATH):
        raise TerminalPromotionPolicyError("authority path drift")
    if policy.get("task_backlog_authority") != str(BACKLOG_PATH):
        raise TerminalPromotionPolicyError("task backlog authority drift")
    if policy.get("prom01_policy_authority") != str(PROM01_POLICY_PATH):
        raise TerminalPromotionPolicyError("PROM-01 policy authority drift")
    if policy.get("prom02_policy_authority") != str(PROM02_POLICY_PATH):
        raise TerminalPromotionPolicyError("PROM-02 policy authority drift")

    for key in (
        "require_exact_head",
        "require_independent_verifier",
        "external_signature_required_for_promotion",
        "allow_explicit_rejection_without_signature",
    ):
        if policy.get(key) is not True:
            raise TerminalPromotionPolicyError(f"{key} must remain true")
    if policy.get("ci_may_generate_promotion_signature") is not False:
        raise TerminalPromotionPolicyError(
            "CI must not generate a promotion signature"
        )
    if policy.get("allowed_signer_types") != EXPECTED_SIGNER_TYPES:
        raise TerminalPromotionPolicyError("allowed signer types drift")
    if policy.get("forbidden_signer_types") != ["agent"]:
        raise TerminalPromotionPolicyError("agent signer ban drift")
    if policy.get("allowed_signature_methods") != EXPECTED_SIGNATURE_METHODS:
        raise TerminalPromotionPolicyError("signature method set drift")
    required_refs = policy.get("signature_ref_required_methods")
    if required_refs != ["ci_oidc", "git_gpg", "git_ssh", "sigstore"]:
        raise TerminalPromotionPolicyError(
            "signature reference requirements drift"
        )
    implementation_signer = policy.get("implementation_signer_id")
    if (
        not isinstance(implementation_signer, str)
        or not implementation_signer
    ):
        raise TerminalPromotionPolicyError(
            "implementation_signer_id must be non-empty"
        )

    tasks = backlog.get("tasks") if isinstance(backlog, dict) else None
    if not isinstance(tasks, list):
        raise TerminalPromotionPolicyError("task backlog tasks missing")
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
        raise TerminalPromotionPolicyError("PROM-03 task missing")
    if task.get("depends_on") != EXPECTED_DEPENDENCIES:
        raise TerminalPromotionPolicyError(
            "PROM-03 dependency identity drift"
        )
    if task.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise TerminalPromotionPolicyError(
            "PROM-03 accountability identity drift"
        )

    if prom01.get("task_id") != "P1-PROM-01":
        raise TerminalPromotionPolicyError("PROM-01 task drift")
    if prom01.get("promotion_authority") is not False:
        raise TerminalPromotionPolicyError(
            "PROM-01 must remain non-authoritative"
        )
    if prom02.get("task_id") != "P1-PROM-02":
        raise TerminalPromotionPolicyError("PROM-02 task drift")
    if prom02.get("promotion_authority") is not False:
        raise TerminalPromotionPolicyError(
            "PROM-02 must remain non-authoritative"
        )
    if prom02.get("signed_promotion") is not False:
        raise TerminalPromotionPolicyError(
            "PROM-02 must not sign promotion"
        )

    promotion_requires = policy.get("promotion_requires")
    rejection_requires = policy.get("rejection_requires")
    if not isinstance(promotion_requires, list) or len(promotion_requires) < 6:
        raise TerminalPromotionPolicyError(
            "promotion requirements are incomplete"
        )
    if not isinstance(rejection_requires, list) or len(rejection_requires) < 3:
        raise TerminalPromotionPolicyError(
            "rejection requirements are incomplete"
        )

    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "external_signature_required_for_promotion": True,
        "allow_explicit_rejection_without_signature": True,
        "ci_may_generate_promotion_signature": False,
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
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except TerminalPromotionPolicyError as exc:
        print(f"P1 terminal promotion policy: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
