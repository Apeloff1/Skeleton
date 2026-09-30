#!/usr/bin/env python3
"""Build exact-head evidence for AC-09 time, expiry, and lease semantics."""

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

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
AXIS_ID = "AC-09"
BATCH_ID = "p1-adversarial-ac09-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "clock_skew",
    "suspend_resume",
    "lease_fencing",
    "expiry_property",
)

PROOFS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "clock_skew": (
        (
            "skeleton/kernel/clocks.py",
            (
                "wall-clock time, which is meaningless across",
                "def happens_before",
                "def is_concurrent_with",
            ),
        ),
        (
            "skeleton/testing/test_swarm_exact_lease_atomicity.py",
            (
                "test_exact_lease_uses_one_clock_sample_for_commit",
                "test_exact_lease_rejects_non_finite_clock_without_mutation",
            ),
        ),
        (
            "skeleton/testing/test_swarm_lease_rollback.py",
            (
                "test_exact_lease_commit_uses_one_clock_sample",
                "test_exact_lease_rollback_commit_uses_one_clock_sample",
            ),
        ),
    ),
    "suspend_resume": (
        (
            "skeleton/kernel/leases.py",
            (
                "get paused by",
                "wake up after expiry",
                "time.monotonic",
            ),
        ),
        (
            "skeleton/testing/test_shell_leases_queue_rate.py",
            (
                "test_lease_expiry_allows_reacquire",
                "test_lease_renew_requires_current_lease",
            ),
        ),
        (
            "skeleton/testing/test_shell_ai_execution_fence.py",
            (
                "test_execution_fence_expiry_rejects_stale_owner",
                "test_execution_fence_reacquire_after_expiry_increments_token",
            ),
        ),
    ),
    "lease_fencing": (
        (
            "skeleton/kernel/leases.py",
            (
                "class FencingGate",
                "stale fencing token",
                "def steal",
            ),
        ),
        (
            "skeleton/testing/test_shell_ai_execution_fence.py",
            (
                "test_execution_fence_old_owner_is_stale_after_reacquire",
                "test_execution_fence_reacquire_after_expiry_increments_token",
                "test_execution_fence_old_instance_is_stale_after_renew",
            ),
        ),
        (
            "skeleton/testing/test_swarm_lease_rollback.py",
            (
                "test_exact_lease_rollback_rejects_wrong_owner_without_mutation",
                "test_exact_lease_rollback_clock_failure_does_not_partially_commit",
            ),
        ),
    ),
    "expiry_property": (
        (
            "skeleton/kernel/leases.py",
            (
                "def is_expired",
                "now >= self.expires_at",
                "def current",
            ),
        ),
        (
            "skeleton/testing/test_shell_leases_queue_rate.py",
            (
                "test_lease_expiry_allows_reacquire",
                "test_lease_renew_requires_current_lease",
            ),
        ),
        (
            "skeleton/testing/test_shell_ai_execution_fence.py",
            (
                "test_execution_fence_expiry_rejects_stale_owner",
                "test_execution_fence_ttl_must_cover_plan_budget",
                "test_execution_fence_ttl_may_equal_plan_budget",
            ),
        ),
    ),
}

ANCHORS: dict[str, tuple[str, ...]] = {
    mode: tuple(path for path, _tokens in entries)
    for mode, entries in PROOFS.items()
}
TOKENS: dict[str, tuple[str, ...]] = {
    mode: tuple(token for _path, tokens in entries for token in tokens)
    for mode, entries in PROOFS.items()
}


class AC09EvidenceError(RuntimeError):
    """AC-09 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC09EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC09EvidenceError(f"{path} must contain an object")
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


def _tracked_contract(
    root: Path,
    relative: str,
    required_tokens: tuple[str, ...],
) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC09EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC09EvidenceError(f"proof anchor is not tracked: {relative}")

    text = path.read_text(encoding="utf-8")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise AC09EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(required_tokens),
    }


def build_ac09_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC09EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC09EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (row for row in axes if isinstance(row, dict) and row.get("id") == AXIS_ID),
        None,
    )
    if axis is None:
        raise AC09EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC09EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC09EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise AC09EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
    if binding_present:
        raise AC09EvidenceError(f"{AXIS_ID} is already governed")

    proofs: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        anchors = [
            _tracked_contract(root, relative, tokens)
            for relative, tokens in PROOFS[mode]
        ]
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "anchors": anchors,
            "required_tokens": list(TOKENS[mode]),
        }
        proof["proof_digest"] = _digest(proof)
        proofs[mode] = proof
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-ac09-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof["proof_digest"],
                "category": mode,
            }
        )

    candidate = {
        "batch_id": BATCH_ID,
        "axis_id": AXIS_ID,
        "axis_name": axis.get("name"),
        "statement": obligation.statement,
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
        "engine": "p1-adversarial-ac09-evidence-v1",
        "batch_id": BATCH_ID,
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


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac09_evidence(ROOT, expected_head=args.expected_head)
    except AC09EvidenceError as exc:
        print(f"P1 AC-09 evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(
            json.dumps(
                {
                    "axis_id": report["axis_id"],
                    "candidate_count": report["candidate_count"],
                    "required_evidence_mode_count": report[
                        "required_evidence_mode_count"
                    ],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("P1 AC-09 evidence: OK (time/expiry/lease semantics)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
