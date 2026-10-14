#!/usr/bin/env python3
"""Build/validate the compact source-bound masterplan parse index.

The index is navigation only. It never grants completion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "machine" / "ai_master_plan.json"
LEDGER = ROOT / "machine" / "ai_build_accountability.json"
INDEX = ROOT / "machine" / "ai_masterplan_parse_index.json"


class ParseIndexError(RuntimeError):
    pass


def _read_json(path: Path) -> tuple[bytes, dict]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseIndexError(f"cannot read {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseIndexError(f"{path.relative_to(ROOT)} root must be an object")
    return raw, data


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def build_index() -> dict:
    master_raw, master = _read_json(MASTER)
    ledger_raw, ledger = _read_json(LEDGER)

    volumes = master.get("volumes")
    records = ledger.get("records")
    if not isinstance(volumes, list) or not isinstance(records, list):
        raise ParseIndexError("master volumes and accountability records must be lists")

    record_by_id = {
        record.get("id"): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    pairs: list[tuple[dict, dict]] = []
    for volume in volumes:
        if not isinstance(volume, dict) or not isinstance(volume.get("key"), str):
            raise ParseIndexError("invalid volume record")
        record = record_by_id.get("ACC-" + volume["key"])
        if not isinstance(record, dict):
            raise ParseIndexError(f"missing accountability record for {volume['key']}")
        pairs.append((volume, record))

    def impl_signed(record: dict) -> bool:
        signoff = record.get("implementation_signoff")
        return isinstance(signoff, dict) and signoff.get("signed") is True

    def verify_signed(record: dict) -> bool:
        signoff = record.get("verification_signoff")
        return isinstance(signoff, dict) and signoff.get("signed") is True

    complete = [
        volume["key"]
        for volume, record in pairs
        if record.get("checkbox") is True and impl_signed(record) and verify_signed(record)
    ]
    implementation_signed_open = [
        volume["key"]
        for volume, record in pairs
        if impl_signed(record) and record.get("checkbox") is not True
    ]
    gap_free_waiting_verification = [
        volume["key"]
        for volume, record in pairs
        if (
            impl_signed(record)
            and not verify_signed(record)
            and record.get("checkbox") is not True
            and isinstance(volume.get("gaps"), list)
            and not volume["gaps"]
        )
    ]
    implementation_unsigned = [
        volume["key"] for volume, record in pairs if not impl_signed(record)
    ]

    by_depth_pass: dict[str, dict[str, int]] = {}
    for volume, record in pairs:
        depth = volume.get("depth_pass") or "UNASSIGNED"
        if not isinstance(depth, str):
            depth = "UNASSIGNED"
        summary = by_depth_pass.setdefault(
            depth,
            {
                "total": 0,
                "implementation_signed": 0,
                "complete": 0,
                "gap_free_waiting_verification": 0,
            },
        )
        summary["total"] += 1
        if impl_signed(record):
            summary["implementation_signed"] += 1
        if record.get("checkbox") is True:
            summary["complete"] += 1
        if (
            impl_signed(record)
            and not verify_signed(record)
            and record.get("checkbox") is not True
            and isinstance(volume.get("gaps"), list)
            and not volume["gaps"]
        ):
            summary["gap_free_waiting_verification"] += 1

    accountability_summary: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ParseIndexError("invalid accountability record")
        record_type = record.get("type")
        status = record.get("status")
        if not isinstance(record_type, str) or not isinstance(status, str):
            raise ParseIndexError("accountability record missing type/status")
        summary = accountability_summary.setdefault(
            record_type,
            {
                "total": 0,
                "implementation_signed": 0,
                "verification_signed": 0,
                "complete": 0,
                "status_counts": {},
            },
        )
        summary["total"] += 1
        if impl_signed(record):
            summary["implementation_signed"] += 1
        if verify_signed(record):
            summary["verification_signed"] += 1
        if record.get("checkbox") is True:
            summary["complete"] += 1
        status_counts = summary["status_counts"]
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "schema_version": 1,
        "kind": "ai-masterplan-parse-index",
        "sources": {
            "machine/ai_master_plan.json": {"git_blob_sha": _git_blob_sha(master_raw)},
            "machine/ai_build_accountability.json": {"git_blob_sha": _git_blob_sha(ledger_raw)},
        },
        "policy": {
            "freshness": "Reject this index if either source Git blob SHA differs from the current file.",
            "completion_authority": "Derived navigation only. Completion remains authoritative in machine/ai_build_accountability.json.",
            "skip_rule": "Fully complete records may be skipped for implementation/verification gap parsing while source identities match.",
            "implementation_skip_rule": "Implementation-signed open records may skip implementation-signature reconciliation while source identities match.",
        },
        "volume_summary": {
            "total": len(pairs),
            "implementation_signed": sum(impl_signed(record) for _, record in pairs),
            "verification_signed": sum(verify_signed(record) for _, record in pairs),
            "complete": len(complete),
            "implementation_signed_open": len(implementation_signed_open),
            "gap_free_waiting_verification": len(gap_free_waiting_verification),
            "implementation_unsigned": len(implementation_unsigned),
        },
        "fast_sets": {
            "fully_complete": complete,
            "gap_free_waiting_verification": gap_free_waiting_verification,
            "implementation_unsigned": implementation_unsigned,
        },
        "by_depth_pass": by_depth_pass,
        "accountability_summary": accountability_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate machine/ai_masterplan_parse_index.json",
    )
    args = parser.parse_args()
    expected = build_index()

    if args.write:
        INDEX.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {INDEX.relative_to(ROOT)}")
        return 0

    try:
        current = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"masterplan parse index missing/invalid: {exc}")

    if current != expected:
        raise SystemExit(
            "masterplan parse index is stale; run "
            "python scripts/check_ai_masterplan_parse_index.py --write"
        )

    summary = expected["volume_summary"]
    print(
        "masterplan parse index valid: "
        f"{summary['complete']} complete, "
        f"{summary['implementation_signed']} implementation-signed, "
        f"{summary['gap_free_waiting_verification']} gap-free awaiting verification"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
