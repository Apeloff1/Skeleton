"""Deterministic assurance evaluation for the converged product runtime.

Assurance is invariant-driven, not a vanity average. Hard failures block the
posture; warnings degrade it. Convergence uses evidence-backed readiness, while
durability requires a cross-process coherent journal with persistent sequencing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class AssuranceInvariant:
    id: str
    severity: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AssuranceReport:
    posture: str
    hard_failures: int
    warnings: int
    native_coverage_pct: float
    readiness_pct: float
    invariants: tuple[AssuranceInvariant, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def evaluate_assurance(
    *,
    lifecycle: Iterable[dict[str, Any]],
    operations: dict[str, Any],
    executor_bindings: Iterable[dict[str, Any]],
    executor_coverage: dict[str, Any],
    receipt_stats: dict[str, Any],
    readiness: dict[str, Any] | None = None,
) -> AssuranceReport:
    ledger = list(lifecycle)
    bindings = list(executor_bindings)
    invariants: list[AssuranceInvariant] = []

    evidence_gaps = [item for item in ledger if item.get("state") in {"evidence_gap", "receipt_unattested"}]
    anomalies = sum(len(item.get("anomalies", ())) for item in ledger)
    invariants += [
        AssuranceInvariant("lifecycle.evidence-complete", "hard", not evidence_gaps, f"{len(evidence_gaps)} lifecycle evidence gap(s)"),
        AssuranceInvariant("lifecycle.no-anomalies", "hard", anomalies == 0, f"{anomalies} lifecycle anomaly signal(s)"),
    ]

    audit_sequence = int(operations.get("audit_sequence", 0) or 0)
    audit_head = operations.get("audit_head")
    audit_ok = audit_sequence == 0 or isinstance(audit_head, str) and len(audit_head) == 64
    invariants.append(AssuranceInvariant(
        "audit.head-continuity", "hard", bool(audit_ok),
        f"sequence={audit_sequence}, head={'present' if audit_head else 'missing'}",
    ))

    capacity = int(operations.get("outbox_capacity_remaining", 0) or 0)
    invariants += [
        AssuranceInvariant("queue.capacity", "hard", capacity > 0, f"{capacity} operation slots remaining"),
        AssuranceInvariant("queue.headroom", "warning", capacity >= 32, f"{capacity} operation slots remaining; target >=32"),
    ]
    outbox_health = operations.get("outbox_health") if isinstance(operations.get("outbox_health"), dict) else {}
    process_safe = outbox_health.get("cross_process_locking") is True
    meta_version = int(outbox_health.get("sequence_meta_version", 0) or 0)
    next_sequence = int(outbox_health.get("next_sequence", 0) or 0)
    invariants += [
        AssuranceInvariant(
            "queue.cross-process-coherence", "hard", process_safe,
            f"locking={outbox_health.get('lock_backend', 'missing')}",
        ),
        AssuranceInvariant(
            "queue.monotonic-sequence", "hard", meta_version >= 1 and next_sequence > 0,
            f"metadata=v{meta_version}, next_sequence={next_sequence}",
        ),
    ]

    unsafe = [binding for binding in bindings if binding.get("effect_class") in {"state", "external"} and not binding.get("replay_safe")]
    invariants.append(AssuranceInvariant(
        "executors.replay-safe-effects", "hard", not unsafe,
        f"{len(unsafe)} state/external executor(s) lack replay safety",
    ))

    receipt_version = int(receipt_stats.get("version", 0) or 0)
    invariants.append(AssuranceInvariant(
        "receipts.provenance-generation", "hard", receipt_version >= 2,
        f"receipt schema generation v{receipt_version}",
    ))

    coverage = float(executor_coverage.get("coverage_pct", 0.0) or 0.0)
    readiness_pct = float((readiness or {}).get("ready_pct", coverage) or 0.0)
    policy_gaps = int((readiness or {}).get("policy_gaps", 0) or 0)
    unsafe_actions = int((readiness or {}).get("unsafe_actions", 0) or 0)
    invariants += [
        AssuranceInvariant("convergence.policy-complete", "hard", policy_gaps == 0, f"{policy_gaps} canonical policy gap(s)"),
        AssuranceInvariant("convergence.no-unsafe-actions", "hard", unsafe_actions == 0, f"{unsafe_actions} canonical action(s) violate readiness safety contracts"),
        AssuranceInvariant("convergence.native-ready-majority", "warning", readiness_pct >= 50.0, f"{readiness_pct:.1f}% canonical actions are evidence-backed native-ready"),
    ]

    hard_failures = sum(not item.passed for item in invariants if item.severity == "hard")
    warnings = sum(not item.passed for item in invariants if item.severity == "warning")
    posture = "blocked" if hard_failures else ("degraded" if warnings else "healthy")
    payload = {
        "posture": posture, "hard_failures": hard_failures, "warnings": warnings,
        "native_coverage_pct": coverage, "readiness_pct": readiness_pct,
        "invariants": [asdict(item) for item in invariants],
    }
    return AssuranceReport(
        posture=posture, hard_failures=hard_failures, warnings=warnings,
        native_coverage_pct=coverage, readiness_pct=readiness_pct,
        invariants=tuple(invariants), attestation_sha256=_digest(payload),
    )


def verify_assurance(report: AssuranceReport) -> bool:
    payload = {
        "posture": report.posture, "hard_failures": report.hard_failures,
        "warnings": report.warnings, "native_coverage_pct": report.native_coverage_pct,
        "readiness_pct": report.readiness_pct,
        "invariants": [asdict(item) for item in report.invariants],
    }
    return _digest(payload) == report.attestation_sha256
