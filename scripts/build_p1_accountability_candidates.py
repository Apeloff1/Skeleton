#!/usr/bin/env python3
"""Build non-authoritative P1 accountability review candidates.

The output is a review queue, not a signing mechanism. It never mutates the
canonical accountability ledger, masterplan, task backlog, execution map, or
any signoff. Candidate packets summarize materialized evidence and the next
governed action required by scripts/ai_accountability.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
ACCOUNTABILITY = Path("machine/ai_build_accountability.json")
BACKLOG = Path("machine/ai_p1_task_backlog.json")
EXECUTION_MAP = Path("machine/ai_p1_execution_map.json")
DEFAULT_OUT = Path("machine/p1_accountability_review_candidates.json")

MATURITY_ORDER = (
    "specified",
    "scaffolded",
    "implemented",
    "integrated",
    "verified",
    "hardened",
    "production",
)
MATURITY_INDEX = {value: index for index, value in enumerate(MATURITY_ORDER)}


class CandidateError(RuntimeError):
    """Candidate packet generation failed closed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise CandidateError(f"{path} must contain an object")
    return payload


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _materialized(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(
        str(value)
        for value in values
        if isinstance(value, str)
        and value.strip()
        and not value.startswith("planned:")
    )


def _signed(value: object) -> bool:
    return isinstance(value, dict) and value.get("signed") is True


def _owner_map(execution_map: dict[str, Any]) -> dict[str, dict[str, str]]:
    lanes = execution_map.get("lanes")
    if not isinstance(lanes, list):
        raise CandidateError("P1 execution map lanes must be a list")

    owner: dict[str, dict[str, str]] = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise CandidateError("P1 lane entries must be objects")
        lane_id = lane.get("id")
        target = lane.get("target_maturity")
        refs = lane.get("primary_volume_refs")
        if not isinstance(lane_id, str) or not lane_id:
            raise CandidateError("lane id is required")
        if target not in MATURITY_INDEX:
            raise CandidateError(f"{lane_id}: invalid target maturity {target!r}")
        if not isinstance(refs, list):
            raise CandidateError(f"{lane_id}: primary_volume_refs must be a list")
        for raw_ref in refs:
            ref = str(raw_ref)
            if ref in owner:
                raise CandidateError(f"duplicate primary-volume owner: {ref}")
            owner[ref] = {
                "lane_id": lane_id,
                "target_floor": str(target),
            }
    return owner


def _tasks_by_volume(backlog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise CandidateError("P1 task backlog tasks must be a list")

    by_volume: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise CandidateError("P1 task entries must be objects")
        task_id = task.get("task_id")
        refs = task.get("volume_refs")
        if not isinstance(task_id, str) or not task_id:
            raise CandidateError("P1 task_id is required")
        if not isinstance(refs, list):
            raise CandidateError(f"{task_id}: volume_refs must be a list")
        for raw_ref in refs:
            by_volume.setdefault(str(raw_ref), []).append(task)
    return by_volume


def _accountability_rank(status: object) -> int:
    if not isinstance(status, str):
        return -1
    return MATURITY_INDEX.get(status.lower(), -1)


def _classify(
    *,
    record: dict[str, Any],
    target_floor: str,
    gaps: list[str],
) -> tuple[str, list[str]]:
    implementation_signed = _signed(record.get("implementation_signoff"))
    verification_signed = _signed(record.get("verification_signoff"))
    current_rank = _accountability_rank(record.get("status"))
    target_rank = MATURITY_INDEX[target_floor]

    blockers: list[str] = []
    if not implementation_signed:
        blockers.append("implementation_signoff_required")
    if not verification_signed:
        blockers.append("independent_verification_signoff_required")
    if current_rank < target_rank:
        blockers.append("accountability_status_below_target_floor")
    if target_rank >= MATURITY_INDEX["hardened"] and gaps:
        blockers.append("unresolved_hardening_gaps")

    if (
        implementation_signed
        and verification_signed
        and current_rank >= target_rank
        and not (
            target_rank >= MATURITY_INDEX["hardened"] and gaps
        )
    ):
        return "already_target_floor_eligible", blockers
    if not implementation_signed:
        return "implementation_review_ready", blockers
    if not verification_signed:
        return "independent_verification_review_ready", blockers
    if target_rank >= MATURITY_INDEX["hardened"] and gaps:
        return "gap_resolution_required", blockers
    return "accountability_status_review_required", blockers


def build_candidates(root: Path = ROOT) -> dict[str, Any]:
    paths = {
        "master_plan": root / MASTER,
        "accountability": root / ACCOUNTABILITY,
        "p1_task_backlog": root / BACKLOG,
        "p1_execution_map": root / EXECUTION_MAP,
    }
    before = {name: _digest(path) for name, path in paths.items()}

    master = _load(paths["master_plan"])
    accountability = _load(paths["accountability"])
    backlog = _load(paths["p1_task_backlog"])
    execution_map = _load(paths["p1_execution_map"])

    volumes = master.get("volumes")
    records = accountability.get("records")
    if not isinstance(volumes, list):
        raise CandidateError("masterplan volumes must be a list")
    if not isinstance(records, list):
        raise CandidateError("accountability records must be a list")

    owner = _owner_map(execution_map)
    if len(owner) != 107:
        raise CandidateError(
            f"expected 107 P1 primary volumes, got {len(owner)}"
        )

    volume_by_key = {
        str(volume.get("key")): volume
        for volume in volumes
        if isinstance(volume, dict) and volume.get("key")
    }
    record_by_id = {
        str(record.get("id")): record
        for record in records
        if isinstance(record, dict) and record.get("id")
    }
    tasks_by_volume = _tasks_by_volume(backlog)

    packets: list[dict[str, Any]] = []
    for key in sorted(owner):
        volume = volume_by_key.get(key)
        if volume is None:
            raise CandidateError(f"missing masterplan volume: {key}")

        accountability_id = volume.get("accountability_id")
        record = record_by_id.get(str(accountability_id))
        if record is None:
            raise CandidateError(
                f"{key}: missing accountability record {accountability_id}"
            )

        tasks = tasks_by_volume.get(key, [])
        if not tasks:
            raise CandidateError(f"{key}: no mapped P1 tasks")

        implementation_paths = _materialized(
            volume.get("implementation_paths")
        )
        tests = _materialized(volume.get("tests"))
        evaluations = _materialized(volume.get("evaluations"))
        volume_evidence = _materialized(volume.get("evidence"))
        task_evidence = _dedupe(
            reference
            for task in tasks
            for reference in _materialized(task.get("evidence_refs"))
        )
        evidence = _dedupe(volume_evidence + task_evidence)
        if not all(
            (implementation_paths, tests, evaluations, evidence)
        ):
            raise CandidateError(
                f"{key}: materialized volume evidence is incomplete"
            )

        gaps = [
            str(item)
            for item in volume.get("gaps", [])
            if isinstance(item, str) and item.strip()
        ]
        state, blockers = _classify(
            record=record,
            target_floor=owner[key]["target_floor"],
            gaps=gaps,
        )

        packet = {
            "volume_key": key,
            "title": volume.get("title"),
            "lane_id": owner[key]["lane_id"],
            "target_floor": owner[key]["target_floor"],
            "accountability_id": str(accountability_id),
            "accountability_status": record.get("status"),
            "implementation_signed": _signed(
                record.get("implementation_signoff")
            ),
            "verification_signed": _signed(
                record.get("verification_signoff")
            ),
            "review_state": state,
            "governance_blockers": blockers,
            "mapped_task_ids": [
                str(task["task_id"])
                for task in tasks
            ],
            "implementation_paths": implementation_paths,
            "tests": tests,
            "evaluations": evaluations,
            "evidence_refs": evidence,
            "unresolved_gaps": gaps,
            "signing_required": record.get("signing_required") is True,
            "authoritative": False,
            "may_apply": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packets.append(packet)

    after = {name: _digest(path) for name, path in paths.items()}
    if before != after:
        raise CandidateError(
            "canonical source files changed during candidate generation"
        )

    counts: dict[str, int] = {}
    for packet in packets:
        state = packet["review_state"]
        counts[state] = counts.get(state, 0) + 1

    result: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-accountability-review-candidates-v1",
        "authoritative": False,
        "may_apply": False,
        "signatures_created": 0,
        "source_digests": before,
        "primary_volume_count": len(packets),
        "review_state_counts": dict(sorted(counts.items())),
        "packets": packets,
    }
    result["report_digest"] = _canonical_digest(result)
    return result


def _canonical_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed review queue differs from derivation.",
    )
    args = parser.parse_args(argv)

    try:
        payload = build_candidates(ROOT)
    except CandidateError as exc:
        print(f"P1 accountability candidates: rejected: {exc}", file=sys.stderr)
        return 2

    destination = ROOT / args.out
    expected = _canonical_text(payload)
    if args.check:
        try:
            current = destination.read_text(encoding="utf-8")
        except OSError:
            print(
                f"P1 accountability candidates: missing {args.out}",
                file=sys.stderr,
            )
            return 1
        if current != expected:
            print(
                "P1 accountability candidates: drift detected",
                file=sys.stderr,
            )
            return 1
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(expected, encoding="utf-8")

    print(
        "P1 accountability candidates: OK "
        f"({payload['primary_volume_count']} volumes; "
        f"{payload['review_state_counts']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
