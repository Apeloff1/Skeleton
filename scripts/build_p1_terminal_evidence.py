#!/usr/bin/env python3
"""Build a non-authoritative exact-head P1-PROM-01 evidence bundle."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_evidence import (
    P1_TERMINAL_REQUIRED_TASKS,
    P1TerminalEvidenceError,
    aggregate_p1_terminal_evidence,
)
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt
from scripts.check_p1_terminal_evidence_policy import (
    MAP_PATH,
    POLICY_PATH,
    ROOT,
    validate_repository,
)


class TerminalEvidenceBuildError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalEvidenceBuildError(f"cannot read {path}") from exc


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _digest_paths(paths: list[str]) -> str:
    h = hashlib.sha256()
    for raw in paths:
        path = ROOT / raw
        if not path.is_file():
            raise TerminalEvidenceBuildError(
                f"missing evidence path: {raw}"
            )
        h.update(raw.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _observed_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "observed-at must be RFC3339"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "observed-at must include timezone"
        )
    return parsed


def _primary_volumes(execution_map: dict[str, Any]) -> tuple[str, ...]:
    lanes = execution_map.get("lanes")
    if not isinstance(lanes, list):
        raise TerminalEvidenceBuildError(
            "execution map lanes must be a list"
        )
    values: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            raise TerminalEvidenceBuildError(
                "execution map lane must be object"
            )
        refs = lane.get("primary_volume_refs")
        if not isinstance(refs, list):
            raise TerminalEvidenceBuildError(
                "primary_volume_refs must be a list"
            )
        values.update(str(item) for item in refs)
    if not values:
        raise TerminalEvidenceBuildError(
            "primary volume scope is empty"
        )
    return tuple(sorted(values))


def build_bundle(
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
    run_attempt: int,
    observed_at: datetime,
    maturity_report_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    validate_repository(ROOT)
    policy = _load(ROOT / POLICY_PATH)
    execution_map = _load(ROOT / MAP_PATH)
    maturity_report = _load(maturity_report_path)
    if not isinstance(policy, dict):
        raise TerminalEvidenceBuildError(
            "terminal policy must be an object"
        )
    if not isinstance(execution_map, dict):
        raise TerminalEvidenceBuildError(
            "execution map must be an object"
        )
    if not isinstance(maturity_report, dict):
        raise TerminalEvidenceBuildError(
            "maturity report must be an object"
        )

    rows = policy["required_receipts"]
    row_by_task = {
        str(row["task_id"]): row for row in rows
    }
    receipts: list[PromotionEvidenceReceipt] = []
    serialized_receipts: list[dict[str, Any]] = []
    environment_digest = hashlib.sha256(
        b"github-actions|ubuntu-24.04|python-3.11.16|prom-01"
    ).hexdigest()
    shared_verifier_paths = [
        "skeleton/contracts/p1_terminal_evidence.py",
        "scripts/build_p1_terminal_evidence.py",
        "scripts/check_p1_terminal_evidence_policy.py",
        "machine/p1_terminal_evidence_policy.json",
        ".github/workflows/p1-terminal-evidence-bundle.yml",
    ]

    for task_id, accountability_id in P1_TERMINAL_REQUIRED_TASKS:
        row = row_by_task[task_id]
        test_paths = list(row["test_paths"])
        test_digest = _digest_paths(test_paths)
        verifier_digest = _digest_paths(
            [*shared_verifier_paths, *test_paths]
        )
        receipt = PromotionEvidenceReceipt(
            repository=repository,
            commit_sha=commit_sha,
            task_id=task_id,
            accountability_id=accountability_id,
            configuration_digest=_canonical_digest(row),
            environment_digest=environment_digest,
            verifier_id=f"github-actions:p1-prom-01:{task_id.lower()}",
            verifier_digest=verifier_digest,
            test_manifest_digest=test_digest,
            run_id=f"{run_id}-{task_id.lower()}",
            run_attempt=run_attempt,
            observed_at=observed_at,
            evidence=(
                EvidenceRef(
                    source=f"p1:prom-01:exact-head:{task_id}",
                    digest=test_digest,
                    category="exact_head_verification",
                ),
            ),
        )
        receipts.append(receipt)
        serialized_receipts.append(
            {
                **receipt.to_payload(),
                "receipt_digest": receipt.receipt_digest,
            }
        )

    decision = aggregate_p1_terminal_evidence(
        receipts=tuple(receipts),
        maturity_report=maturity_report,
        expected_repository=repository,
        expected_head=commit_sha,
        expected_primary_volumes=_primary_volumes(execution_map),
    )
    if not decision.accepted:
        raise TerminalEvidenceBuildError(
            "terminal evidence aggregation rejected: "
            + ",".join(decision.reasons)
        )
    evidence = decision.accepted_evidence_ref()
    payload = {
        **decision.payload(),
        "decision_digest": decision.decision_digest,
        "receipt_count": len(receipts),
        "receipts": serialized_receipts,
    }
    refs = [
        {
            "source": evidence.source,
            "digest": evidence.digest,
            "category": evidence.category,
        }
    ]
    return payload, refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--observed-at", type=_observed_at, required=True)
    parser.add_argument("--maturity-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refs-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload, refs = build_bundle(
            repository=args.repository,
            commit_sha=args.commit_sha,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            observed_at=args.observed_at,
            maturity_report_path=args.maturity_report,
        )
    except (
        TerminalEvidenceBuildError,
        P1TerminalEvidenceError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 terminal evidence build: rejected: {exc}",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.refs_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.refs_out.write_text(
        json.dumps(refs, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "P1 terminal evidence build: OK "
        f"(receipts={payload['receipt_count']}, "
        f"volumes={payload['primary_volume_count']}, "
        f"promotion_ready={payload['promotion_ready']}, "
        f"blockers={len(payload['promotion_blockers'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
