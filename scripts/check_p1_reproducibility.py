#!/usr/bin/env python3
"""Build and verify non-authoritative P1 reproducibility bundles."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.canonical import EvidenceRef, evidence_ref_identity
from skeleton.contracts.promotion_evidence import (
    PromotionEvidenceError,
    PromotionEvidenceReceipt,
)
from skeleton.contracts.reproducibility import (
    ReplayDisposition,
    ReplayObservation,
    ReproducibilityBundle,
    ReproducibilityError,
    bundle_from_receipt,
    canonical_digest,
    evaluate_replay,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/p1_reproducibility_policy.json")
EXPECTED_POLICY_ID = "skeleton.p1.reproducibility"
EXPECTED_TASK_ID = "P1-EVID-05"
EXPECTED_ACCOUNTABILITY = "ACC-P1-EVID-05"
EXPECTED_RUNNER_PATHS = {
    "promotion-evidence-emitter": "scripts/emit_p1_promotion_evidence.py",
    "provenance-pytest-manifest": "scripts/run_provenance_evidence.py",
    "p1-reproducibility-verifier": "scripts/check_p1_reproducibility.py",
}
EXPECTED_BUDGETS = {
    "focused-ci": {
        "id": "focused-ci",
        "wall_seconds": 900,
        "cpu_units": 1,
        "memory_mb": 4096,
        "retries": 0,
        "network_policy": "repository-declared",
    },
    "independent-replay": {
        "id": "independent-replay",
        "wall_seconds": 1200,
        "cpu_units": 2,
        "memory_mb": 8192,
        "retries": 0,
        "network_policy": "repository-declared",
    },
}
EXPECTED_COMPARISON = {
    "require_same_repository": True,
    "require_same_commit_sha": True,
    "require_same_task_id": True,
    "require_same_accountability_id": True,
    "require_same_configuration_digest": True,
    "require_same_environment_digest": True,
    "require_same_verifier_id": True,
    "require_same_verifier_digest": True,
    "require_same_test_manifest_digest": True,
    "require_same_runner_id_and_digest": True,
    "require_same_budget_id_and_digest": True,
    "require_same_source_date_epoch": True,
    "require_same_subject_digest": True,
    "require_same_evidence_digest": True,
    "run_id_may_differ": True,
    "run_attempt_may_differ": True,
    "observed_at_may_differ": True,
}
EXPECTED_TERMINAL_POLICY = {
    "reproduced_required_for_qualifying_evidence": True,
    "deterministic_incompatibility_is_not_success": True,
    "failed_replay_is_not_success": True,
    "bundle_cannot_self_promote": True,
}


class ReproducibilityCliError(RuntimeError):
    """Repository reproducibility input is malformed."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReproducibilityCliError(f"cannot read JSON: {path}") from exc


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ReproducibilityCliError(f"runner file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReproducibilityCliError(f"{field} must be RFC3339 text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReproducibilityCliError(f"{field} is invalid RFC3339") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ReproducibilityCliError(f"{field} must include timezone")
    return result


def _evidence_rows(rows: object) -> tuple[EvidenceRef, ...]:
    if not isinstance(rows, list):
        raise ReproducibilityCliError("evidence/input payload must be a JSON array")
    refs: list[EvidenceRef] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ReproducibilityCliError(f"evidence[{index}] must be an object")
        allowed = {"identity", "source", "digest", "category"}
        unknown = set(row) - allowed
        if unknown:
            raise ReproducibilityCliError(
                f"evidence[{index}] unknown fields: {sorted(unknown)}"
            )
        try:
            ref = EvidenceRef(
                source=row["source"],
                digest=row["digest"],
                category=row.get("category", "repository_state"),
            )
        except KeyError as exc:
            raise ReproducibilityCliError(
                f"evidence[{index}] is incomplete"
            ) from exc
        declared = row.get("identity")
        if declared is not None and declared != evidence_ref_identity(ref):
            raise ReproducibilityCliError(
                f"evidence[{index}] identity mismatch"
            )
        refs.append(ref)
    return tuple(refs)


def _receipt(payload: object) -> PromotionEvidenceReceipt:
    if not isinstance(payload, dict):
        raise ReproducibilityCliError("receipt must be an object")
    try:
        verifier = payload["verifier"]
        run = payload["run"]
        if not isinstance(verifier, dict) or not isinstance(run, dict):
            raise ReproducibilityCliError("receipt verifier/run must be objects")
        receipt = PromotionEvidenceReceipt(
            repository=payload["repository"],
            commit_sha=payload["commit_sha"],
            task_id=payload["task_id"],
            accountability_id=payload["accountability_id"],
            configuration_digest=payload["configuration_digest"],
            environment_digest=payload["environment_digest"],
            verifier_id=verifier["id"],
            verifier_digest=verifier["digest"],
            test_manifest_digest=verifier["test_manifest_digest"],
            run_id=str(run["id"]),
            run_attempt=run["attempt"],
            observed_at=_time(payload["observed_at"], "observed_at"),
            evidence=_evidence_rows(payload["evidence"]),
            schema_version=payload.get("schema_version", 1),
        )
    except (KeyError, PromotionEvidenceError) as exc:
        raise ReproducibilityCliError(f"invalid promotion receipt: {exc}") from exc
    declared = {
        "subject_digest": receipt.subject_digest,
        "evidence_digest": receipt.evidence_digest,
        "receipt_digest": receipt.receipt_digest,
    }
    for field, expected in declared.items():
        actual = payload.get(field)
        if actual is not None and actual != expected:
            raise ReproducibilityCliError(f"receipt {field} mismatch")
    return receipt


def _bundle(payload: object) -> ReproducibilityBundle:
    if not isinstance(payload, dict):
        raise ReproducibilityCliError("bundle must be an object")
    try:
        bundle = ReproducibilityBundle(
            repository=payload["repository"],
            commit_sha=payload["commit_sha"],
            task_id=payload["task_id"],
            accountability_id=payload["accountability_id"],
            configuration_digest=payload["configuration_digest"],
            environment_digest=payload["environment_digest"],
            verifier_id=payload["verifier_id"],
            verifier_digest=payload["verifier_digest"],
            test_manifest_digest=payload["test_manifest_digest"],
            runner_id=payload["runner_id"],
            runner_digest=payload["runner_digest"],
            budget_id=payload["budget_id"],
            budget_digest=payload["budget_digest"],
            source_date_epoch=payload["source_date_epoch"],
            expected_subject_digest=payload["expected_subject_digest"],
            expected_evidence_digest=payload["expected_evidence_digest"],
            inputs=_evidence_rows(payload["inputs"]),
            schema_version=payload.get("schema_version", 1),
        )
    except (KeyError, ReproducibilityError) as exc:
        raise ReproducibilityCliError(f"invalid reproducibility bundle: {exc}") from exc
    declared = payload.get("bundle_digest")
    if declared is not None and declared != bundle.bundle_digest:
        raise ReproducibilityCliError("bundle_digest mismatch")
    return bundle


def validate_policy(root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = _json(root / POLICY)
    if not isinstance(policy, dict):
        raise ReproducibilityCliError("reproducibility policy must be an object")
    expected = {
        "schema_version": 1,
        "policy_id": EXPECTED_POLICY_ID,
        "policy_version": "1.0.0",
        "task_id": EXPECTED_TASK_ID,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "non_authoritative": True,
        "exact_head_required": True,
        "source_date_epoch_required": True,
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            raise ReproducibilityCliError(f"reproducibility policy {key} drift")

    runners = policy.get("runners")
    budgets = policy.get("budgets")
    if not isinstance(runners, list) or not runners:
        raise ReproducibilityCliError("policy runners must be non-empty")
    if not isinstance(budgets, list) or not budgets:
        raise ReproducibilityCliError("policy budgets must be non-empty")

    runner_map: dict[str, dict[str, Any]] = {}
    for row in runners:
        if not isinstance(row, dict):
            raise ReproducibilityCliError("runner entries must be objects")
        runner_id = row.get("id")
        relative = row.get("path")
        if (
            not isinstance(runner_id, str)
            or not runner_id
            or runner_id in runner_map
        ):
            raise ReproducibilityCliError("runner IDs must be unique")
        if not isinstance(relative, str) or not relative:
            raise ReproducibilityCliError(f"{runner_id}: runner path is required")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ReproducibilityCliError(f"{runner_id}: runner path escapes repo")
        full = root / path
        digest = _sha256_file(full)
        runner_map[runner_id] = {
            **row,
            "digest": digest,
        }
    if {
        key: str(value["path"])
        for key, value in runner_map.items()
    } != EXPECTED_RUNNER_PATHS:
        raise ReproducibilityCliError("reproducibility runner inventory drift")

    budget_map: dict[str, dict[str, Any]] = {}
    for row in budgets:
        if not isinstance(row, dict):
            raise ReproducibilityCliError("budget entries must be objects")
        budget_id = row.get("id")
        if (
            not isinstance(budget_id, str)
            or not budget_id
            or budget_id in budget_map
        ):
            raise ReproducibilityCliError("budget IDs must be unique")
        for field in ("wall_seconds", "cpu_units", "memory_mb", "retries"):
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or (field != "retries" and value < 1)
            ):
                raise ReproducibilityCliError(
                    f"{budget_id}: invalid {field}"
                )
        budget_map[budget_id] = {
            **row,
            "digest": canonical_digest(row),
        }
    if {
        key: {k: v for k, v in value.items() if k != "digest"}
        for key, value in budget_map.items()
    } != EXPECTED_BUDGETS:
        raise ReproducibilityCliError("reproducibility budget policy drift")

    comparison = policy.get("comparison")
    terminal = policy.get("terminal_policy")
    if comparison != EXPECTED_COMPARISON:
        raise ReproducibilityCliError("reproducibility comparison policy drift")
    if terminal != EXPECTED_TERMINAL_POLICY:
        raise ReproducibilityCliError("reproducibility terminal policy drift")

    return runner_map, budget_map


def _policy_binding(
    root: Path,
    runner_id: str,
    budget_id: str,
) -> tuple[str, str]:
    runners, budgets = validate_policy(root)
    if runner_id not in runners:
        raise ReproducibilityCliError(f"runner is not policy-approved: {runner_id}")
    if budget_id not in budgets:
        raise ReproducibilityCliError(f"budget is not policy-approved: {budget_id}")
    return runners[runner_id]["digest"], budgets[budget_id]["digest"]


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def build(args: argparse.Namespace) -> int:
    receipt = _receipt(_json(args.receipt))
    inputs = _evidence_rows(_json(args.inputs))
    runner_digest, budget_digest = _policy_binding(
        ROOT, args.runner_id, args.budget_id
    )
    try:
        bundle = bundle_from_receipt(
            receipt,
            runner_id=args.runner_id,
            runner_digest=runner_digest,
            budget_id=args.budget_id,
            budget_digest=budget_digest,
            source_date_epoch=args.source_date_epoch,
            inputs=inputs,
        )
    except ReproducibilityError as exc:
        raise ReproducibilityCliError(str(exc)) from exc
    payload = {
        **bundle.as_dict(),
        "bundle_digest": bundle.bundle_digest,
    }
    _write(args.out, payload)
    return 0


def verify(args: argparse.Namespace) -> int:
    bundle = _bundle(_json(args.bundle))
    runner_digest, budget_digest = _policy_binding(
        ROOT, args.runner_id, args.budget_id
    )
    if args.receipt is not None:
        receipt = _receipt(_json(args.receipt))
        replay = ReplayObservation(
            runner_id=args.runner_id,
            runner_digest=runner_digest,
            budget_id=args.budget_id,
            budget_digest=budget_digest,
            source_date_epoch=args.source_date_epoch,
            receipt=receipt,
        )
    else:
        replay = ReplayObservation(
            runner_id=args.runner_id,
            runner_digest=runner_digest,
            budget_id=args.budget_id,
            budget_digest=budget_digest,
            source_date_epoch=args.source_date_epoch,
            failure_digest=args.failure_digest,
        )
    evaluation = evaluate_replay(bundle, replay)
    payload = {
        **evaluation.as_dict(),
        "evaluation_digest": evaluation.evaluation_digest,
    }
    _write(args.out, payload)
    return 0 if evaluation.disposition is ReplayDisposition.REPRODUCED else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subs = root.add_subparsers(dest="command", required=True)

    build_parser = subs.add_parser("build")
    build_parser.add_argument("--receipt", type=Path, required=True)
    build_parser.add_argument("--inputs", type=Path, required=True)
    build_parser.add_argument("--runner-id", required=True)
    build_parser.add_argument("--budget-id", required=True)
    build_parser.add_argument("--source-date-epoch", type=int, required=True)
    build_parser.add_argument("--out", type=Path)
    build_parser.set_defaults(func=build)

    verify_parser = subs.add_parser("verify")
    verify_parser.add_argument("--bundle", type=Path, required=True)
    verify_parser.add_argument("--receipt", type=Path)
    verify_parser.add_argument("--failure-digest")
    verify_parser.add_argument("--runner-id", required=True)
    verify_parser.add_argument("--budget-id", required=True)
    verify_parser.add_argument("--source-date-epoch", type=int, required=True)
    verify_parser.add_argument("--out", type=Path)
    verify_parser.set_defaults(func=verify)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (getattr(args, "receipt", None) is None) == (
        getattr(args, "failure_digest", None) is None
    ) and args.command == "verify":
        print(
            "p1-reproducibility: rejected: provide exactly one of "
            "--receipt or --failure-digest",
            file=sys.stderr,
        )
        return 2
    try:
        return args.func(args)
    except (ReproducibilityCliError, ReproducibilityError) as exc:
        print(f"p1-reproducibility: rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
