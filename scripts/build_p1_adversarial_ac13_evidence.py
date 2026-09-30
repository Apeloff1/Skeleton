#!/usr/bin/env python3
"""Build exact-head evidence for AC-13 hostile parser/resource-bomb closure."""

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
AXIS_ID = "AC-13"
BATCH_ID = "p1-adversarial-ac13-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = ("fuzz", "parser_limits", "decompression_bomb", "complexity_budget")

IMPLEMENTATION = "skeleton/security/archive_sandbox.py"
REGRESSIONS = "skeleton/testing/test_security_archive_sandbox.py"

MODE_TEST_TOKENS: dict[str, tuple[str, ...]] = {
    "fuzz": (
        "test_zip_rejects_traversal_absolute_or_ambiguous_paths",
        "test_tar_rejects_traversal_absolute_or_ambiguous_paths",
        "test_duplicate_zip_member_path_is_rejected",
        "test_casefold_zip_collision_is_rejected",
        "test_casefold_tar_collision_is_rejected",
    ),
    "parser_limits": (
        "test_archive_byte_bound_is_enforced",
        "test_member_count_bound_is_enforced",
        "test_member_size_bound_is_enforced",
        "test_total_expanded_size_bound_is_enforced",
        "test_path_depth_bound_is_enforced",
        "test_path_byte_bound_is_enforced",
    ),
    "decompression_bomb": (
        "test_zip_compression_ratio_bound_is_enforced",
        "test_archive_expansion_ratio_bound_is_enforced",
    ),
    "complexity_budget": (
        "test_limits_fail_closed_on_invalid_values",
        "max_stream_chunks_per_member",
        "max_members",
        "max_total_bytes",
        "max_depth",
    ),
}

IMPLEMENTATION_TOKENS = (
    "max_archive_bytes",
    "max_members",
    "max_member_bytes",
    "max_total_bytes",
    "max_path_bytes",
    "max_depth",
    "max_compression_ratio",
    "max_archive_expansion_ratio",
    "max_stream_chunks_per_member",
    "archive member compression-ratio bound exceeded",
    "archive expansion-ratio bound exceeded",
)


class AC13EvidenceError(RuntimeError):
    """AC-13 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC13EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC13EvidenceError(f"{path} must contain an object")
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


def _tracked_source(root: Path, relative: str) -> tuple[str, str]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AC13EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC13EvidenceError(f"proof anchor is not tracked: {relative}")
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(path.read_bytes()).hexdigest()


def build_ac13_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC13EvidenceError("expected_head must be lowercase 40-character git SHA")

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC13EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (row for row in axes if isinstance(row, dict) and row.get("id") == AXIS_ID),
        None,
    )
    if axis is None:
        raise AC13EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC13EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC13EvidenceError(f"expected exactly one {AXIS_ID} obligation, got {len(matches)}")
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC13EvidenceError("risk registry records must be a list")
    if any(
        isinstance(row, dict) and row.get("obligation_id") == obligation.obligation_id
        for row in records
    ):
        raise AC13EvidenceError(f"{AXIS_ID} is already governed")

    implementation_text, implementation_digest = _tracked_source(root, IMPLEMENTATION)
    regression_text, regression_digest = _tracked_source(root, REGRESSIONS)

    missing_impl = [token for token in IMPLEMENTATION_TOKENS if token not in implementation_text]
    if missing_impl:
        raise AC13EvidenceError(
            "archive sandbox implementation markers missing: " + ", ".join(missing_impl)
        )

    proofs: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        tokens = MODE_TEST_TOKENS[mode]
        missing = [token for token in tokens if token not in regression_text]
        if missing:
            raise AC13EvidenceError(
                f"{mode} regression markers missing: " + ", ".join(missing)
            )
        proof = {
            "axis_id": AXIS_ID,
            "mode": mode,
            "expected_head": expected_head,
            "implementation": {
                "path": IMPLEMENTATION,
                "sha256": implementation_digest,
            },
            "regression": {
                "path": REGRESSIONS,
                "sha256": regression_digest,
                "required_tokens": list(tokens),
            },
        }
        proof["proof_digest"] = _digest(proof)
        proofs[mode] = proof
        evidence.append(
            {
                "source": f"p1:adversarial-ac13-evidence:{AXIS_ID}:{mode}:{expected_head}",
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
        "engine": "p1-adversarial-ac13-evidence-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "axis_id": AXIS_ID,
        "candidate_count": 1,
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
        report = build_ac13_evidence(ROOT, expected_head=args.expected_head)
    except AC13EvidenceError as exc:
        print(f"P1 AC-13 evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(json.dumps({
            "axis_id": report["axis_id"],
            "candidate_count": report["candidate_count"],
            "required_evidence_mode_count": report["required_evidence_mode_count"],
            "expected_head": report["expected_head"],
            "report_digest": report["report_digest"],
        }, indent=2, sort_keys=True))

    print("P1 AC-13 evidence: OK (hostile parser/resource limits proven)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
