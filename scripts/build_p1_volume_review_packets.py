#!/usr/bin/env python3
"""Build exact-head P1 volume review packets without signing anything.

Each blocked P1 primary volume receives one deterministic packet containing:
- the exact commit and reconciliation identity;
- mapped task/evidence identity;
- current target-floor blockers and unresolved gaps;
- an implementation-owner review request;
- an independent-verifier review request.

The packet is evidence transport only. It has no approval, signing, maturity,
completion, or promotion authority and cannot be applied to accountability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_p1_maturity_closure_ledger import build_ledger


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class ReviewPacketError(RuntimeError):
    """Review-packet inputs are malformed or violate the unsigned boundary."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewPacketError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise ReviewPacketError(f"{path} must contain an object")
    return payload


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha40(value: str) -> str:
    if not _SHA40_RE.fullmatch(value):
        raise ReviewPacketError(
            "commit_sha must be lowercase 40-character git SHA"
        )
    return value


def _review_request(
    *,
    review_type: str,
    role: str,
    independence_required: bool,
    prerequisite_actions: list[str],
) -> dict[str, Any]:
    if review_type not in {
        "implementation_signoff",
        "independent_verification_signoff",
    }:
        raise ReviewPacketError(f"unsupported review type: {review_type}")
    if role not in {"implementation_owner", "independent_verifier"}:
        raise ReviewPacketError(f"unsupported reviewer role: {role}")
    if (
        review_type == "independent_verification_signoff"
        and independence_required is not True
    ):
        raise ReviewPacketError(
            "independent verification must require independence"
        )
    return {
        "review_type": review_type,
        "required_role": role,
        "independence_required": independence_required,
        "prerequisite_actions": prerequisite_actions,
        "review_state": "unsigned",
        "signature_method": None,
        "signature_ref": None,
        "reviewer_id": None,
        "reviewed_at_utc": None,
        "application_authority": False,
    }


def build_packets(
    *,
    root: Path = ROOT,
    commit_sha: str,
) -> dict[str, Any]:
    exact_head = _sha40(commit_sha)
    closure = build_ledger(root)
    master = _load(root / MASTER)
    volume_by_key = {
        str(row.get("key")): row
        for row in master.get("volumes", [])
        if isinstance(row, dict) and row.get("key")
    }

    packets: list[dict[str, Any]] = []
    for row in closure["records"]:
        if row["target_floor_eligible"] is True:
            continue

        key = row["volume_key"]
        volume = volume_by_key.get(key)
        if volume is None:
            raise ReviewPacketError(f"{key}: missing masterplan volume")

        required_actions = list(row["required_actions"])
        if "implementation_signoff" not in required_actions:
            raise ReviewPacketError(
                f"{key}: blocked packet lacks implementation signoff action"
            )
        if "independent_verification_signoff" not in required_actions:
            raise ReviewPacketError(
                f"{key}: blocked packet lacks independent verification action"
            )

        unresolved_gaps = list(volume.get("gaps") or [])
        if any(
            not isinstance(gap, str) or not gap.strip()
            for gap in unresolved_gaps
        ):
            raise ReviewPacketError(f"{key}: malformed unresolved gaps")

        evidence_refs = list(row["mapped_task_evidence_refs"])
        evidence_digest = _canonical_digest(evidence_refs)
        volume_metadata_digest = _canonical_digest(
            {
                "volume_key": key,
                "target_floor": row["target_floor"],
                "implementation_paths": volume.get("implementation_paths", []),
                "tests": volume.get("tests", []),
                "evaluations": volume.get("evaluations", []),
                "evidence": volume.get("evidence", []),
                "gaps": unresolved_gaps,
            }
        )

        implementation_prerequisites: list[str] = []
        verification_prerequisites = [
            action
            for action in required_actions
            if action != "independent_verification_signoff"
        ]

        packet: dict[str, Any] = {
            "schema_version": 1,
            "packet_kind": "p1_volume_external_review",
            "source_commit": exact_head,
            "closure_ledger_digest": closure["ledger_digest"],
            "volume_key": key,
            "lane_id": row["lane_id"],
            "target_floor": row["target_floor"],
            "accountability_id": row["accountability_id"],
            "current_status": row["current_status"],
            "current_implementation_status": row[
                "current_implementation_status"
            ],
            "accountability_status": row["accountability_status"],
            "target_floor_blockers": row["target_floor_blockers"],
            "required_actions": required_actions,
            "unresolved_gaps": unresolved_gaps,
            "mapped_task_ids": row["mapped_task_ids"],
            "mapped_task_evidence_refs": evidence_refs,
            "evidence_digest": evidence_digest,
            "volume_metadata_digest": volume_metadata_digest,
            "implementation_review": _review_request(
                review_type="implementation_signoff",
                role="implementation_owner",
                independence_required=False,
                prerequisite_actions=implementation_prerequisites,
            ),
            "verification_review": _review_request(
                review_type="independent_verification_signoff",
                role="independent_verifier",
                independence_required=True,
                prerequisite_actions=verification_prerequisites,
            ),
            "signed": False,
            "applicable": False,
            "accountability_mutation_authority": False,
            "maturity_mutation_authority": False,
            "promotion_authority": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packets.append(packet)

    packets.sort(key=lambda item: item["volume_key"])
    blocked = closure["blocked_volume_keys"]
    if [packet["volume_key"] for packet in packets] != blocked:
        raise ReviewPacketError(
            "review packet set differs from blocked volume set"
        )

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-volume-review-packets-v1",
        "source_commit": exact_head,
        "closure_ledger_digest": closure["ledger_digest"],
        "primary_volume_count": closure["primary_volume_count"],
        "target_floor_eligible_count": closure[
            "target_floor_eligible_count"
        ],
        "review_packet_count": len(packets),
        "eligible_volume_keys": closure[
            "target_floor_eligible_volume_keys"
        ],
        "packet_volume_keys": [packet["volume_key"] for packet in packets],
        "non_authoritative": True,
        "signed": False,
        "applicable": False,
        "accountability_mutation_authority": False,
        "maturity_mutation_authority": False,
        "promotion_authority": False,
        "packets": packets,
    }
    manifest["manifest_digest"] = _canonical_digest(manifest)
    return manifest


def _canonical_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        manifest = build_packets(
            root=ROOT,
            commit_sha=args.commit_sha,
        )
    except ReviewPacketError as exc:
        print(f"P1 volume review packets: rejected: {exc}", file=sys.stderr)
        return 2

    output = args.out
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_canonical_text(manifest), encoding="utf-8")

    print(
        "P1 volume review packets: OK "
        f"({manifest['review_packet_count']} unsigned packets; "
        f"{manifest['target_floor_eligible_count']} already floor-eligible)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
