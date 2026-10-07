#!/usr/bin/env python3
"""Build exact-head evidence for AC-23 long-horizon entropy and aging."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)

AXIS_ID = "AC-23"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "soak",
    "accelerated_time",
    "aging_simulation",
    "retirement_migration",
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

PROOFS = {
    "soak": (
        (
            "skeleton/reliability/long_horizon_aging.py",
            (
                "class SoakWindow",
                "growth_per_hour",
                "soak evaluation requires at least two samples",
            ),
        ),
        (
            "skeleton/testing/test_long_horizon_aging.py",
            (
                "test_soak_window_accepts_bounded_stable_growth",
                "test_soak_window_detects_slow_leak_before_absolute_exhaustion",
                "test_soak_window_detects_missing_samples_and_absolute_bound",
            ),
        ),
    ),
    "accelerated_time": (
        (
            "skeleton/reliability/long_horizon_aging.py",
            (
                "def accelerated_times",
                "accelerated-time horizon and step must be positive",
            ),
        ),
        (
            "skeleton/testing/test_long_horizon_aging.py",
            (
                "test_accelerated_time_schedule_is_deterministic_and_includes_horizon",
                "test_accelerated_time_rejects_zero_step_or_horizon",
            ),
        ),
    ),
    "aging_simulation": (
        (
            "skeleton/reliability/long_horizon_aging.py",
            (
                "class LongHorizonAgingGuard",
                "revalidation_due",
                "bounds_exceeded",
            ),
        ),
        (
            "skeleton/testing/test_long_horizon_aging.py",
            (
                "test_future_expiry_and_revalidation_are_detected",
                "test_resource_growth_bounds_cover_queue_cache_log_and_identifier",
                "test_revalidation_timestamp_cannot_be_from_future",
            ),
        ),
    ),
    "retirement_migration": (
        (
            "skeleton/reliability/long_horizon_aging.py",
            (
                "migration_blocked",
                "replacement requires an explicit retirement time",
                "long-horizon aging safety violation",
            ),
        ),
        (
            "skeleton/testing/test_long_horizon_aging.py",
            (
                "test_retirement_requires_ready_replacement",
                "test_model_retirement_mid_lifecycle_is_fail_closed_until_migrated",
                "test_replacement_without_retirement_contract_is_rejected",
            ),
        ),
    ),
}


class AC23EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC23EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC23EvidenceError(f"{path} must contain an object")
    return value


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _anchor(root: Path, relative: str, tokens: tuple[str, ...]) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC23EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC23EvidenceError(f"proof anchor is not tracked: {relative}")
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AC23EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(tokens),
    }


def build_ac23_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40.fullmatch(expected_head):
        raise AC23EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    adversarial = _load(root / ADVERSARIAL)
    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC23EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (row for row in axes if isinstance(row, dict) and row.get("id") == AXIS_ID),
        None,
    )
    if axis is None:
        raise AC23EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC23EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(
        _load(root / MASTER),
        _load(root / P1_MAP),
        adversarial,
        _load(root / POLICY),
    )
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC23EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    registry = _load(root / REGISTRY)
    records = registry.get("records")
    if not isinstance(records, list):
        raise AC23EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in records
    )

    proofs: dict[str, Any] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        anchors = [_anchor(root, path, tokens) for path, tokens in PROOFS[mode]]
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": anchors,
        }
        proof["proof_digest"] = _digest(proof)
        proofs[mode] = proof
        evidence.append(
            {
                "category": mode,
                "digest": proof["proof_digest"],
                "source": (
                    f"p1:adversarial-ac23-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
            }
        )

    candidate = {
        "axis_id": AXIS_ID,
        "axis_name": axis.get("name"),
        "obligation_id": obligation.obligation_id,
        "obligation_digest": obligation.obligation_digest,
        "owner_id": OWNER_ID,
        "recommended_severity": "high",
        "recommended_disposition": "evidence",
        "expected_head": expected_head,
        "binding_present": binding_present,
        "required_evidence_modes": list(EXPECTED_MODES),
        "evidence": evidence,
        "proofs": proofs,
        "non_authoritative": True,
        "creates_binding": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
    }
    candidate["candidate_digest"] = _digest(candidate)
    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac23-evidence-v1",
        "axis_id": AXIS_ID,
        "expected_head": expected_head,
        "candidate_count": 1,
        "already_bound_count": int(binding_present),
        "candidate_binding_count": 0 if binding_present else 1,
        "required_evidence_mode_count": len(EXPECTED_MODES),
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
        "candidate": candidate,
    }
    report["report_digest"] = _digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidate", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac23_evidence(ROOT, expected_head=args.expected_head)
    except AC23EvidenceError as exc:
        print(f"P1 AC-23 evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_summary:
        print(
            json.dumps(
                {
                    "axis_id": report["axis_id"],
                    "candidate_count": report["candidate_count"],
                    "candidate_binding_count": report["candidate_binding_count"],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    if args.print_candidate:
        candidate = report["candidate"]
        print(
            "P1_AC23_BINDING_SEED="
            + json.dumps(
                {
                    "obligation_id": candidate["obligation_id"],
                    "obligation_digest": candidate["obligation_digest"],
                    "owner_id": candidate["owner_id"],
                    "severity": candidate["recommended_severity"],
                    "disposition": candidate["recommended_disposition"],
                    "evidence": candidate["evidence"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    print("P1 AC-23 evidence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
