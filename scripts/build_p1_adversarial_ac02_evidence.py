#!/usr/bin/env python3
"""Build exact-head evidence for AC-02 quiescence, shutdown, and restart."""

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
AXIS_ID = "AC-02"
BATCH_ID = "p1-adversarial-ac02-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "shutdown_race",
    "restart_replay",
    "fault_injection",
    "state_machine_property",
)

PROOFS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "shutdown_race": (
        (
            "skeleton/shells/worker_shutdown.py",
            (
                "class ShutdownPhase",
                "class WorkerShutdownCoordinator",
                "deadline_seconds",
                "ShutdownPhase.FORCED",
            ),
        ),
        (
            "skeleton/testing/test_worker_fairness_failover_shutdown.py",
            (
                "test_shutdown_drains_queue_and_stops_workers",
                "test_shutdown_no_drain_leaves_queued_but_stops",
                "test_shutdown_failed_worker_can_abort",
            ),
        ),
    ),
    "restart_replay": (
        (
            "scripts/state_recovery_drill.py",
            (
                "class RecoveryJournal",
                "verify_authority",
                "rebuild_derived",
                "derived rebuild is not deterministic",
            ),
        ),
        (
            "skeleton/testing/test_state_recovery_drill.py",
            (
                "test_recovery_journal_requires_authority_verification_before_rebuild",
                "test_operation_sqlite_restore_preserves_authority_and_outbox_order",
                "test_engine_sqlite_bundle_restore_preserves_authoritative_ledgers",
            ),
        ),
        (
            "tests/test_runtime_replay_terminal_contract.py",
            (
                "test_complete_snapshot_requires_terminal_complete_event",
                "test_events_after_complete_are_rejected",
            ),
        ),
    ),
    "fault_injection": (
        (
            "skeleton/testing/test_worker_fairness_failover_shutdown.py",
            (
                "test_shutdown_failed_worker_can_abort",
                "test_failover_no_healthy_standby_does_not_change",
            ),
        ),
        (
            "skeleton/testing/test_state_recovery_drill.py",
            (
                "test_failed_phase_stops_recovery_journal",
                "test_verify_snapshot_rejects_document_or_index_drift",
                "test_sqlite_snapshot_verification_rejects_restore_drift",
            ),
        ),
        (
            "skeleton/testing/test_swarm_runtime_recovery.py",
            (
                "test_unknown_worker_heartbeat_fails_closed",
                "test_live_task_cannot_be_revived",
                "test_runtime_rejects_duplicate_worker_without_orphaning_original",
            ),
        ),
    ),
    "state_machine_property": (
        (
            "skeleton/shells/worker_shutdown.py",
            (
                'REQUESTED = "requested"',
                'DRAINING = "draining"',
                'STOPPED = "stopped"',
                'INCOMPLETE = "incomplete"',
            ),
        ),
        (
            "scripts/state_recovery_drill.py",
            (
                "recovery order violation",
                "recovery journal is already terminal",
                "derived rebuild forbidden before authoritative verification",
            ),
        ),
        (
            "tests/test_runtime_replay_terminal_contract.py",
            (
                "test_complete_snapshot_requires_terminal_complete_event",
                "test_causal_predecessor_must_be_earlier_than_decision",
            ),
        ),
    ),
}

ANCHORS = {
    mode: tuple(path for path, _tokens in entries)
    for mode, entries in PROOFS.items()
}
TOKENS = {
    mode: tuple(token for _path, tokens in entries for token in tokens)
    for mode, entries in PROOFS.items()
}


class AC02EvidenceError(RuntimeError):
    """AC-02 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC02EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC02EvidenceError(f"{path} must contain an object")
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
        raise AC02EvidenceError(f"proof anchor missing or unsafe: {relative}")

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC02EvidenceError(f"proof anchor is not tracked: {relative}")

    text = path.read_text(encoding="utf-8")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        joined = ", ".join(missing)
        raise AC02EvidenceError(
            f"{relative} missing required proof tokens: {joined}"
        )

    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(required_tokens),
    }


def build_ac02_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC02EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC02EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC02EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC02EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC02EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise AC02EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
    if binding_present:
        raise AC02EvidenceError(f"{AXIS_ID} is already governed")

    proofs: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        anchors = [
            _tracked_contract(root, relative, tokens)
            for relative, tokens in PROOFS[mode]
        ]
        proof: dict[str, Any] = {
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
                    f"p1:adversarial-ac02-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof["proof_digest"],
                "category": mode,
            }
        )

    candidate: dict[str, Any] = {
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

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac02-evidence-v1",
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
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac02_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except AC02EvidenceError as exc:
        print(f"P1 AC-02 evidence: rejected: {exc}", file=sys.stderr)
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

    print("P1 AC-02 evidence: OK (shutdown/restart state machine)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
