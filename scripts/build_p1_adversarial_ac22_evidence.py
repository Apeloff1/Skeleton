#!/usr/bin/env python3
"""Build exact-head evidence for AC-22 reproducibility and environment drift."""

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

ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
P1_MAP = Path("machine/ai_p1_execution_map.json")
ADVERSARIAL = Path("machine/ai_adversarial_closure.json")
POLICY = Path("machine/p1_risk_evidence_policy.json")
REGISTRY = Path("machine/p1_risk_evidence_bindings.json")

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
AXIS_ID = "AC-22"
BATCH_ID = "p1-adversarial-ac22-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "hermetic_build",
    "environment_replay",
    "cross_environment_reproduction",
    "dependency_lock_check",
)
EXPECTED_ARCHES = ("x86_64", "aarch64")

MANIFEST_ANCHORS = (
    "pyproject.toml",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/yarn.lock",
    "scripts/check_toolchain_contract.py",
    "scripts/check_quality_gate_parity.py",
    ".github/workflows/ci.yml",
    ".github/workflows/backend-quality.yml",
    ".github/workflows/dependency-security.yml",
    ".github/workflows/p1-adversarial-ac22-evidence.yml",
)

LOCK_ANCHORS = (
    "pyproject.toml",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/yarn.lock",
)

WORKFLOW_PATH = ".github/workflows/p1-adversarial-ac22-evidence.yml"
WORKFLOW_REQUIRED_TOKENS = (
    "runs-on: ubuntu-24.04",
    "runs-on: ubuntu-24.04-arm",
    "python scripts/check_toolchain_contract.py",
    "python scripts/check_quality_gate_parity.py",
    "manifest_digest",
    "replay_digest",
    "needs: [x64, arm64]",
)


class AC22EvidenceError(RuntimeError):
    """AC-22 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC22EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC22EvidenceError(f"{path} must contain an object")
    return value


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked_file(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    if not path.is_file():
        raise AC22EvidenceError(f"proof anchor is missing: {relative}")
    if path.is_symlink():
        raise AC22EvidenceError(f"proof anchor must not be symlinked: {relative}")
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AC22EvidenceError(f"proof anchor is not tracked: {relative}")
    return {"path": relative, "sha256": _file_digest(path)}


def build_environment_manifest(root: Path = ROOT) -> dict[str, Any]:
    anchors = [_tracked_file(root, relative) for relative in MANIFEST_ANCHORS]
    lock_anchors = [
        row for row in anchors if row["path"] in set(LOCK_ANCHORS)
    ]
    manifest = {
        "schema_version": 1,
        "anchors": anchors,
        "lock_anchors": lock_anchors,
    }
    manifest["manifest_digest"] = _canonical_digest(manifest)
    return manifest


def _validate_workflow_contract(root: Path) -> dict[str, Any]:
    path = root / WORKFLOW_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AC22EvidenceError("AC-22 workflow is missing") from exc
    missing = [token for token in WORKFLOW_REQUIRED_TOKENS if token not in text]
    if missing:
        raise AC22EvidenceError(
            "AC-22 workflow contract missing: " + ", ".join(missing)
        )
    return {
        "path": WORKFLOW_PATH,
        "sha256": _file_digest(path),
        "required_tokens": list(WORKFLOW_REQUIRED_TOKENS),
    }


def _require_digest(value: str, *, label: str) -> str:
    if not _HEX64_RE.fullmatch(value):
        raise AC22EvidenceError(f"{label} must be lowercase SHA-256 hex")
    return value


def build_ac22_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
    x64_manifest_digest: str,
    x64_replay_digest: str,
    arm64_manifest_digest: str,
    arm64_replay_digest: str,
    x64_arch: str,
    arm64_arch: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC22EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    from reconcile_p1_risk_evidence import RiskKind, derive_obligations

    supplied = {
        "x64_manifest_digest": _require_digest(
            x64_manifest_digest, label="x64_manifest_digest"
        ),
        "x64_replay_digest": _require_digest(
            x64_replay_digest, label="x64_replay_digest"
        ),
        "arm64_manifest_digest": _require_digest(
            arm64_manifest_digest, label="arm64_manifest_digest"
        ),
        "arm64_replay_digest": _require_digest(
            arm64_replay_digest, label="arm64_replay_digest"
        ),
    }
    if (x64_arch, arm64_arch) != EXPECTED_ARCHES:
        raise AC22EvidenceError(
            f"expected architectures {EXPECTED_ARCHES!r}, "
            f"got {(x64_arch, arm64_arch)!r}"
        )

    from reconcile_p1_risk_evidence import RiskKind, derive_obligations

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC22EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC22EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC22EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC22EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    records = registry.get("records")
    if not isinstance(records, list):
        raise AC22EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in records
    )

    manifest = build_environment_manifest(root)
    manifest_digest = manifest["manifest_digest"]
    for label, digest in supplied.items():
        if digest != manifest_digest:
            raise AC22EvidenceError(
                f"{label} does not match canonical manifest digest"
            )

    workflow_contract = _validate_workflow_contract(root)
    lock_paths = [row["path"] for row in manifest["lock_anchors"]]
    if lock_paths != list(LOCK_ANCHORS):
        raise AC22EvidenceError("dependency lock anchor order/content drift")

    proofs: dict[str, dict[str, Any]] = {
        "hermetic_build": {
            "axis_id": AXIS_ID,
            "mode": "hermetic_build",
            "expected_head": expected_head,
            "manifest_digest": manifest_digest,
            "toolchain_contract": next(
                row
                for row in manifest["anchors"]
                if row["path"] == "scripts/check_toolchain_contract.py"
            ),
            "quality_gate_parity": next(
                row
                for row in manifest["anchors"]
                if row["path"] == "scripts/check_quality_gate_parity.py"
            ),
            "workflow_contract": workflow_contract,
        },
        "environment_replay": {
            "axis_id": AXIS_ID,
            "mode": "environment_replay",
            "expected_head": expected_head,
            "x64_manifest_digest": x64_manifest_digest,
            "x64_replay_digest": x64_replay_digest,
            "arm64_manifest_digest": arm64_manifest_digest,
            "arm64_replay_digest": arm64_replay_digest,
            "replay_stable": len(set(supplied.values())) == 1,
        },
        "cross_environment_reproduction": {
            "axis_id": AXIS_ID,
            "mode": "cross_environment_reproduction",
            "expected_head": expected_head,
            "x64_arch": x64_arch,
            "arm64_arch": arm64_arch,
            "manifest_digest": manifest_digest,
            "cross_environment_digest_match": (
                x64_manifest_digest == arm64_manifest_digest == manifest_digest
            ),
        },
        "dependency_lock_check": {
            "axis_id": AXIS_ID,
            "mode": "dependency_lock_check",
            "expected_head": expected_head,
            "lock_anchors": manifest["lock_anchors"],
            "lock_anchor_count": len(manifest["lock_anchors"]),
            "manifest_digest": manifest_digest,
        },
    }

    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
        proof = proofs[mode]
        proof["proof_digest"] = _canonical_digest(proof)
        evidence.append(
            {
                "source": (
                    f"p1:adversarial-ac22-evidence:{AXIS_ID}:"
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
        "environment_manifest": manifest,
        "evidence": evidence,
        "proofs": proofs,
        "non_authoritative": True,
        "creates_binding": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "promotes_maturity": False,
    }
    candidate["candidate_digest"] = _canonical_digest(candidate)

    report = {
        "schema_version": 1,
        "engine": "p1-adversarial-ac22-evidence-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "axis_id": AXIS_ID,
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
    report["report_digest"] = _canonical_digest(report)
    return report


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--x64-manifest-digest", required=True)
    parser.add_argument("--x64-replay-digest", required=True)
    parser.add_argument("--arm64-manifest-digest", required=True)
    parser.add_argument("--arm64-replay-digest", required=True)
    parser.add_argument("--x64-arch", required=True)
    parser.add_argument("--arm64-arch", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_ac22_evidence(
            ROOT,
            expected_head=args.expected_head,
            x64_manifest_digest=args.x64_manifest_digest,
            x64_replay_digest=args.x64_replay_digest,
            arm64_manifest_digest=args.arm64_manifest_digest,
            arm64_replay_digest=args.arm64_replay_digest,
            x64_arch=args.x64_arch,
            arm64_arch=args.arm64_arch,
        )
    except AC22EvidenceError as exc:
        print(f"P1 AC-22 evidence: rejected: {exc}", file=sys.stderr)
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
                    "manifest_digest": report["candidate"][
                        "environment_manifest"
                    ]["manifest_digest"],
                    "report_digest": report["report_digest"],
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("P1 AC-22 evidence: OK (x64/ARM64 reproducibility proven)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
