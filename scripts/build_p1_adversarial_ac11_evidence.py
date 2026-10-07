#!/usr/bin/env python3
"""Build exact-head evidence for AC-11 semantic drift without version change."""

from __future__ import annotations

import argparse
import copy
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

from check_ai_master_plan import validate as validate_master_plan  # noqa: E402
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
AXIS_ID = "AC-11"
BATCH_ID = "p1-adversarial-ac11-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "semantic_canary",
    "contract_probe",
    "drift_eval",
    "evidence_invalidation",
)

CANARY_SCRIPTS = (
    "scripts/check_ai_master_plan.py",
    "scripts/check_ai_adversarial_closure.py",
)
PROBE_SCRIPTS = (
    "scripts/check_architecture_map.py",
    "scripts/check_state_topology.py",
    "scripts/check_capability_interfaces.py",
)


class AC11EvidenceError(RuntimeError):
    """AC-11 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC11EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC11EvidenceError(f"{path} must contain an object")
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


def _run_script(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC11EvidenceError(f"validator anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC11EvidenceError(f"validator anchor is not tracked: {relative}")

    run = subprocess.run(
        [sys.executable, relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    receipt = {
        "path": relative,
        "returncode": run.returncode,
        "stdout_digest": hashlib.sha256(run.stdout.encode("utf-8")).hexdigest(),
        "stderr_digest": hashlib.sha256(run.stderr.encode("utf-8")).hexdigest(),
    }
    if run.returncode != 0:
        raise AC11EvidenceError(
            f"validator failed for {relative}: {run.stderr[-400:]}"
        )
    return receipt


def _semantic_drift_receipt(master: dict[str, Any]) -> dict[str, Any]:
    baseline_errors = validate_master_plan(master)
    if baseline_errors:
        raise AC11EvidenceError(
            "live master plan is invalid: " + "; ".join(baseline_errors[:5])
        )

    mutated = copy.deepcopy(master)
    before_schema = mutated.get("schema_version")
    freeze = mutated.get("breadth_freeze")
    if not isinstance(freeze, dict):
        raise AC11EvidenceError("breadth_freeze missing from master plan")
    original_policy = freeze.get("p1_application_policy")
    if original_policy != "forbid":
        raise AC11EvidenceError("unexpected live P1 application policy")
    freeze["p1_application_policy"] = "allow"

    if mutated.get("schema_version") != before_schema:
        raise AC11EvidenceError("semantic mutation changed schema version")

    drift_errors = validate_master_plan(mutated)
    expected = "breadth_freeze.p1_application_policy must equal forbid"
    if expected not in drift_errors:
        raise AC11EvidenceError(
            "version-preserving semantic drift was not rejected"
        )

    original_digest = _digest(master)
    mutated_digest = _digest(mutated)
    if original_digest == mutated_digest:
        raise AC11EvidenceError("semantic mutation did not invalidate digest")

    return {
        "schema_version_before": before_schema,
        "schema_version_after": mutated.get("schema_version"),
        "field": "breadth_freeze.p1_application_policy",
        "before": original_policy,
        "after": freeze["p1_application_policy"],
        "expected_error": expected,
        "observed_errors": drift_errors,
        "baseline_digest": original_digest,
        "mutated_digest": mutated_digest,
    }


def build_ac11_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC11EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC11EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC11EvidenceError(f"{AXIS_ID} is missing from adversarial closure")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC11EvidenceError(f"{AXIS_ID} evidence mode drift")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC11EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC11EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in records
    )
    semantic_canary = {
        "axis_id": AXIS_ID,
        "mode": "semantic_canary",
        "expected_head": expected_head,
        "validators": [_run_script(root, item) for item in CANARY_SCRIPTS],
    }
    contract_probe = {
        "axis_id": AXIS_ID,
        "mode": "contract_probe",
        "expected_head": expected_head,
        "validators": [_run_script(root, item) for item in PROBE_SCRIPTS],
    }
    drift = _semantic_drift_receipt(master)
    drift_eval = {
        "axis_id": AXIS_ID,
        "mode": "drift_eval",
        "expected_head": expected_head,
        "mutation": {
            key: drift[key]
            for key in (
                "field",
                "before",
                "after",
                "expected_error",
                "observed_errors",
            )
        },
    }
    evidence_invalidation = {
        "axis_id": AXIS_ID,
        "mode": "evidence_invalidation",
        "expected_head": expected_head,
        "schema_version_before": drift["schema_version_before"],
        "schema_version_after": drift["schema_version_after"],
        "baseline_digest": drift["baseline_digest"],
        "mutated_digest": drift["mutated_digest"],
        "digest_changed": drift["baseline_digest"] != drift["mutated_digest"],
    }

    proofs = {
        "semantic_canary": semantic_canary,
        "contract_probe": contract_probe,
        "drift_eval": drift_eval,
        "evidence_invalidation": evidence_invalidation,
    }
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        proof = proofs[mode]
        proof_digest = _digest(proof)
        proof["proof_digest"] = proof_digest
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-ac11-evidence:{AXIS_ID}:"
                    f"{mode}:{expected_head}"
                ),
                "digest": proof_digest,
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

    return {
        "schema_version": 1,
        "engine": "p1-adversarial-ac11-evidence-v1",
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
        "report_digest": _digest(candidate),
    }


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac11_evidence(ROOT, expected_head=args.expected_head)
    except AC11EvidenceError as exc:
        print(f"P1 AC-11 evidence: rejected: {exc}", file=sys.stderr)
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

    print("P1 AC-11 evidence: OK (1 candidate, 4 semantic-drift modes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
