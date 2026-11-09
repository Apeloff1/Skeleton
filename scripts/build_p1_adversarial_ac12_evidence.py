#!/usr/bin/env python3
"""Build exact-head evidence for AC-12 canonicalization/TOCTOU closure."""

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
AXIS_ID = "AC-12"
BATCH_ID = "p1-adversarial-ac12-evidence"
OWNER_ID = "ACC-P1-EVID-04"
EXPECTED_MODES = (
    "canonicalization_fuzz",
    "toctou_race",
    "resource_binding",
    "path_network_adversarial",
)

PROOFS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "canonicalization_fuzz": (
        (
            "skeleton/security/rooted_fs.py",
            ("def _safe_relative", "normalize_relative_path"),
        ),
        (
            "skeleton/testing/test_security_rooted_fs.py",
            (
                "test_normalization_rejects_escape_or_ambiguous_paths",
                "test_normalization_is_deterministic",
            ),
        ),
        (
            "skeleton/testing/test_security_archive_sandbox.py",
            (
                "test_zip_rejects_traversal_absolute_or_ambiguous_paths",
                "test_tar_rejects_traversal_absolute_or_ambiguous_paths",
                "test_dot_canonicalization_collision_is_rejected",
            ),
        ),
    ),
    "toctou_race": (
        (
            "skeleton/security/rooted_fs.py",
            ("_open_directory_fd", "dir_fd=", "FilesystemRaceError"),
        ),
        (
            "skeleton/testing/test_security_rooted_fs.py",
            (
                "test_read_remains_bound_when_parent_path_is_swapped",
                "test_stream_write_cannot_escape_after_parent_path_swap",
                "test_mkdir_remains_bound_when_parent_path_is_swapped",
                "test_list_remains_bound_when_parent_path_is_swapped",
                "test_remove_remains_bound_when_parent_path_is_swapped",
            ),
        ),
        (
            "skeleton/testing/test_security_archive_sandbox.py",
            (
                "test_archive_publication_uses_pinned_parent_dirfds",
                "test_parent_identity_swap_before_publish_fails_closed",
            ),
        ),
    ),
    "resource_binding": (
        (
            "skeleton/security/rooted_fs.py",
            ("root_fingerprint", "_stat_identity", "O_NOFOLLOW"),
        ),
        (
            "skeleton/security/outbound_url.py",
            (
                "ResolvedDestination",
                "resolve_public_https_url",
                "validate_connected_peer",
            ),
        ),
        (
            "skeleton/testing/test_outbound_url_resolution_security.py",
            (
                "test_connect_time_peer_must_match_approved_resolution_snapshot",
                "test_connect_time_peer_can_never_be_private",
            ),
        ),
        (
            "skeleton/distributed/network/remote_execution.py",
            (
                "request_digest",
                "fence_digest",
                "worker_identity_digest",
                "decision_digest",
            ),
        ),
        (
            "skeleton/testing/test_remote_execution_protocol.py",
            (
                "test_replaced_worker_generation_cannot_use_old_grant",
                "test_newer_fence_invalidates_old_worker_commit",
                "test_completion_payload_substitution_blocks_commit",
            ),
        ),
        (
            "skeleton/security/outbound_url.py",
            (
                "ResolvedDestination",
                "resolve_public_https_url",
                "validate_connected_peer",
            ),
        ),
        (
            "skeleton/security/outbound_http.py",
            (
                "validate_connected_peer",
                "response.peer_address",
                "connected peer evidence rejected",
            ),
        ),
    ),
    "path_network_adversarial": (
        (
            "skeleton/testing/test_security_rooted_fs.py",
            (
                "test_existing_symlink_file_is_never_read",
                "test_symlink_parent_is_never_traversed_for_write",
            ),
        ),
        (
            "skeleton/testing/test_security_archive_sandbox.py",
            (
                "test_zip_symlink_member_is_rejected",
                "test_destination_parent_symlink_is_rejected",
            ),
        ),
        (
            "skeleton/testing/test_outbound_url_resolution_security.py",
            (
                "test_mixed_dns_answer_with_any_private_address_fails_closed",
                "test_redirect_revalidates_and_rejects_origin_or_security_change",
            ),
        ),
        (
            "skeleton/testing/test_security_outbound_http.py",
            (
                "test_redirect_cannot_change_security_boundary_by_default",
                "test_get_requires_connected_peer_to_match_dns_snapshot",
            ),
        ),
        (
            "skeleton/testing/test_remote_execution_protocol.py",
            (
                "test_partition_stales_worker_and_blocks_commit",
                "test_late_worker_is_not_commit_authority",
                "test_unattested_identity_digest_blocks_grant",
                "test_protocol_guard_rejects_completion_replay",
            ),
        ),
        (
            ".github/workflows/p1-remote-worker-trust.yml",
            (
                "Validate remote worker trust and fencing",
                "test_remote_execution_protocol.py",
                "Emit exact-head DIST-01 evidence receipt",
            ),
        ),
        (
            "skeleton/testing/test_outbound_url_resolution_security.py",
            (
                "test_mixed_dns_answer_with_any_private_address_fails_closed",
                "test_connect_time_peer_must_match_approved_resolution_snapshot",
                "test_redirect_revalidates_and_rejects_origin_or_security_change",
            ),
        ),
        (
            "skeleton/testing/test_security_outbound_http.py",
            (
                "test_mixed_public_private_dns_evidence_is_rejected_before_transport",
                "test_redirect_cannot_change_security_boundary_by_default",
                "test_body_is_not_consumed_when_peer_evidence_fails",
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


class AC12EvidenceError(RuntimeError):
    """AC-12 evidence inputs are malformed, stale, or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AC12EvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise AC12EvidenceError(f"{path} must contain an object")
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
        raise AC12EvidenceError(f"proof anchor missing or unsafe: {relative}")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise AC12EvidenceError(f"proof anchor is not tracked: {relative}")

    text = path.read_text(encoding="utf-8")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise AC12EvidenceError(
            f"{relative} missing required proof tokens: {', '.join(missing)}"
        )

    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_tokens": list(required_tokens),
    }


def build_ac12_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise AC12EvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    master = _load(root / MASTER)
    p1_map = _load(root / P1_MAP)
    adversarial = _load(root / ADVERSARIAL)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    axes = adversarial.get("closure_axes")
    if not isinstance(axes, list):
        raise AC12EvidenceError("adversarial closure axes must be a list")
    axis = next(
        (
            row
            for row in axes
            if isinstance(row, dict) and row.get("id") == AXIS_ID
        ),
        None,
    )
    if axis is None:
        raise AC12EvidenceError(f"{AXIS_ID} is missing")
    if tuple(axis.get("required_evidence_modes") or ()) != EXPECTED_MODES:
        raise AC12EvidenceError(f"{AXIS_ID} evidence modes drifted")

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    matches = [
        item
        for item in obligations
        if item.kind is RiskKind.ADVERSARIAL and item.source_ref == AXIS_ID
    ]
    if len(matches) != 1:
        raise AC12EvidenceError(
            f"expected exactly one {AXIS_ID} obligation, got {len(matches)}"
        )
    obligation = matches[0]

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise AC12EvidenceError("risk registry records must be a list")
    binding_present = any(
        isinstance(row, dict)
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
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
                    f"p1:adversarial-ac12-evidence:{AXIS_ID}:"
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
        "engine": "p1-adversarial-ac12-evidence-v1",
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
        report = build_ac12_evidence(ROOT, expected_head=args.expected_head)
    except AC12EvidenceError as exc:
        print(f"P1 AC-12 evidence: rejected: {exc}", file=sys.stderr)
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

    print("P1 AC-12 evidence: OK (canonicalization/TOCTOU/resource binding)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
