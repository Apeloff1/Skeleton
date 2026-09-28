#!/usr/bin/env python3
"""Validate the canonical P1-PROM-02 failure-journey policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.p1_failure_journeys import (
    P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID,
    P1_FAILURE_JOURNEY_ASSERTIONS,
    P1_FAILURE_JOURNEY_TASK_ID,
    P1_RECOVERY_REQUIRED_JOURNEYS,
    P1_REQUIRED_FAILURE_JOURNEYS,
    FailureJourneyFamily,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("machine/p1_failure_journey_policy.json")


class FailureJourneyPolicyError(RuntimeError):
    pass


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(root: Path, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureJourneyPolicyError(
            f"cannot read failure journey policy: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise FailureJourneyPolicyError(
            "failure journey policy root must be object"
        )
    return payload


def validate_policy(
    root: Path = ROOT,
    *,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    payload = _load(root, policy_path)
    expected_top = {
        "schema_version",
        "task_id",
        "accountability_ref",
        "authority",
        "terminal_dependency",
        "promotion_authority",
        "signed_promotion",
        "require_exact_head",
        "require_independent_verifier",
        "forbid_production_mutation",
        "journeys",
    }
    unknown = set(payload) - expected_top
    if unknown:
        raise FailureJourneyPolicyError(
            f"unknown top-level fields: {sorted(unknown)}"
        )
    if payload.get("schema_version") != 1:
        raise FailureJourneyPolicyError("schema_version must equal 1")
    if payload.get("task_id") != P1_FAILURE_JOURNEY_TASK_ID:
        raise FailureJourneyPolicyError("task_id drift")
    if (
        payload.get("accountability_ref")
        != P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID
    ):
        raise FailureJourneyPolicyError("accountability_ref drift")
    if payload.get("authority") != str(POLICY_PATH):
        raise FailureJourneyPolicyError("authority path drift")
    if payload.get("terminal_dependency") != "P1-PROM-01":
        raise FailureJourneyPolicyError("terminal dependency drift")
    if payload.get("promotion_authority") is not False:
        raise FailureJourneyPolicyError(
            "failure journeys cannot have promotion authority"
        )
    if payload.get("signed_promotion") is not False:
        raise FailureJourneyPolicyError(
            "PROM-02 cannot sign promotion"
        )
    for field in (
        "require_exact_head",
        "require_independent_verifier",
        "forbid_production_mutation",
    ):
        if payload.get(field) is not True:
            raise FailureJourneyPolicyError(f"{field} must remain true")

    rows = payload.get("journeys")
    if not isinstance(rows, list):
        raise FailureJourneyPolicyError("journeys must be a list")
    by_family: dict[FailureJourneyFamily, dict[str, Any]] = {}
    expected_row_keys = {
        "family",
        "recovery_required",
        "required_assertions",
        "test_paths",
    }
    for raw in rows:
        if not isinstance(raw, dict):
            raise FailureJourneyPolicyError(
                "journey entries must be objects"
            )
        row_unknown = set(raw) - expected_row_keys
        if row_unknown:
            raise FailureJourneyPolicyError(
                f"journey has unknown fields: {sorted(row_unknown)}"
            )
        try:
            family = FailureJourneyFamily(raw.get("family"))
        except ValueError as exc:
            raise FailureJourneyPolicyError(
                f"unknown failure family: {raw.get('family')!r}"
            ) from exc
        if family in by_family:
            raise FailureJourneyPolicyError(
                f"duplicate failure family: {family.value}"
            )
        by_family[family] = raw

    expected_families = set(P1_REQUIRED_FAILURE_JOURNEYS)
    if set(by_family) != expected_families:
        missing = sorted(
            item.value for item in expected_families - set(by_family)
        )
        extra = sorted(
            item.value for item in set(by_family) - expected_families
        )
        raise FailureJourneyPolicyError(
            f"failure family set drift: missing={missing} extra={extra}"
        )

    test_paths: list[str] = []
    for family in P1_REQUIRED_FAILURE_JOURNEYS:
        row = by_family[family]
        recovery_expected = family in P1_RECOVERY_REQUIRED_JOURNEYS
        if row.get("recovery_required") is not recovery_expected:
            raise FailureJourneyPolicyError(
                f"{family.value}: recovery policy drift"
            )
        assertions = row.get("required_assertions")
        if (
            not isinstance(assertions, list)
            or tuple(assertions)
            != P1_FAILURE_JOURNEY_ASSERTIONS[family]
        ):
            raise FailureJourneyPolicyError(
                f"{family.value}: assertion policy drift"
            )
        paths = row.get("test_paths")
        if not isinstance(paths, list) or not paths:
            raise FailureJourneyPolicyError(
                f"{family.value}: test_paths must be non-empty"
            )
        for value in paths:
            if (
                not isinstance(value, str)
                or not value
                or value.startswith("/")
                or ".." in Path(value).parts
            ):
                raise FailureJourneyPolicyError(
                    f"{family.value}: invalid test path"
                )
            if not (root / value).is_file():
                raise FailureJourneyPolicyError(
                    f"{family.value}: missing test path {value}"
                )
            test_paths.append(value)

    if len(test_paths) != len(set(test_paths)):
        raise FailureJourneyPolicyError(
            "failure journey test paths must be unique"
        )

    return {
        "schema_version": 1,
        "task_id": P1_FAILURE_JOURNEY_TASK_ID,
        "accountability_ref": P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID,
        "family_count": len(by_family),
        "test_path_count": len(test_paths),
        "policy_digest": _canonical_digest(payload),
        "promotion_authority": False,
        "signed_promotion": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_policy(ROOT, policy_path=args.policy)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (FailureJourneyPolicyError, TypeError, ValueError) as exc:
        print(f"P1 failure journey policy: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
