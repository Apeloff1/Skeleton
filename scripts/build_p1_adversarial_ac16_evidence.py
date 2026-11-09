#!/usr/bin/env python3
"""Build exact-head evidence for AC-16 observability failure and telemetry pressure."""

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

AXIS_ID = "AC-16"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "telemetry_outage",
    "cardinality_bomb",
    "redaction_test",
    "reconstruction_without_full_telemetry",
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

PROOFS = {
    "telemetry_outage": (
        (
            "skeleton/observability/resilient_telemetry.py",
            (
                "class ResilientTelemetry",
                "except Exception:",
                "self._sink_failures += 1",
            ),
        ),
        (
            "skeleton/testing/test_resilient_telemetry.py",
            ("test_sink_outage_never_breaks_core_event_path",),
        ),
    ),
    "cardinality_bomb": (
        (
            "skeleton/observability/resilient_telemetry.py",
            (
                "max_series",
                "overflow_events",
                'f"overflow:{kind}"',
            ),
        ),
        (
            "skeleton/testing/test_resilient_telemetry.py",
            (
                "test_cardinality_bomb_collapses_new_series_after_bound",
                "test_existing_series_remains_usable_after_cardinality_saturation",
                "test_label_count_is_bounded_before_series_allocation",
            ),
        ),
    ),
    "redaction_test": (
        (
            "skeleton/observability/resilient_telemetry.py",
            (
                "redact_payload",
                "safe_labels",
                "safe_payload",
            ),
        ),
        (
            "skeleton/testing/test_resilient_telemetry.py",
            ("test_sensitive_values_are_redacted_before_sink_and_digest_ledger",),
        ),
    ),
    "reconstruction_without_full_telemetry": (
        (
            "skeleton/observability/resilient_telemetry.py",
            (
                "class ReconstructionReceipt",
                "def reconstruct",
                "receipt_digests",
            ),
        ),
        (
            "skeleton/testing/test_resilient_telemetry.py",
            (
                "test_reconstruction_survives_complete_sink_failure_without_payload_prose",
                "test_reconstruction_ledger_is_bounded_and_preserves_sequence_window",
            ),
        ),
    ),
}


class AC16EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC16EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC16EvidenceError(f"{path} must contain an object")
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
        raise AC16EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC16EvidenceError(f"proof anchor is not tracked: {relative}")
    text = path.read_text(encoding="utf-8")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AC16EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(tokens),
    }


def build_ac16_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40.fullmatch(expected_head):
        raise AC16EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    adversarial = _load(root / ADVERSARIAL)
    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC16EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (row for row in axes if isinstance(row, dict) and row.get("id") == AXIS_ID),
        None,
    )
    if axis is None:
        raise AC16EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC16EvidenceError(f"{AXIS_ID} evidence modes drifted")

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
        raise AC16EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    registry = _load(root / REGISTRY)
    records = registry.get("records")
    if not isinstance(records, list):
        raise AC16EvidenceError("risk registry records must be a list")
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
                    f"p1:adversarial-ac16-evidence:{AXIS_ID}:"
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
        "engine": "p1-adversarial-ac16-evidence-v1",
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
        report = build_ac16_evidence(ROOT, expected_head=args.expected_head)
    except AC16EvidenceError as exc:
        print(f"P1 AC-16 evidence: rejected: {exc}", file=sys.stderr)
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
                    "candidate_binding_count": report["candidate_binding_count"],
                    "expected_head": report["expected_head"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    if args.print_candidate:
        row = report["candidate"]
        print(
            "P1_AC16_BINDING_SEED="
            + json.dumps(
                {
                    "obligation_id": row["obligation_id"],
                    "obligation_digest": row["obligation_digest"],
                    "owner_id": row["owner_id"],
                    "severity": row["recommended_severity"],
                    "disposition": row["recommended_disposition"],
                    "evidence": row["evidence"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    print("P1 AC-16 evidence: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
