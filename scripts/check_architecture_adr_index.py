#!/usr/bin/env python3
"""Validate the canonical architecture ADR index and governed-path coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("machine/adr_index.json")
MASTER = Path("machine/ai_master_plan.json")
_ID = re.compile(r"^ADR-[0-9]{4,}$")


class ADRIndexError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ADRIndexError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ADRIndexError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise ADRIndexError(f"{relative} must contain an object")
    return data


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ADRIndexError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ADRIndexError(f"invalid repository path: {value!r}")
    return pure.as_posix()


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    index = _load(root, INDEX)
    master = _load(root, MASTER)

    if index.get("status") != "active":
        raise ADRIndexError("ADR index must be active")

    binding = index.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise ADRIndexError("masterplan_binding must be an object")
    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    volume = volumes.get(binding.get("volume_ref"))
    if not isinstance(volume, dict):
        raise ADRIndexError("ADR index references unknown masterplan volume")
    if binding.get("volume_ref") != "VOL-058" or binding.get("title") != volume.get("title"):
        raise ADRIndexError("ADR index must remain bound to VOL-058")
    gaps = binding.get("required_gap_texts")
    if not isinstance(gaps, list) or not gaps:
        raise ADRIndexError("ADR index masterplan gaps must be non-empty")
    for gap in gaps:
        if gap not in volume.get("gaps", []):
            raise ADRIndexError(f"ADR index masterplan gap drift: {gap!r}")

    policy = index.get("policy")
    if not isinstance(policy, dict):
        raise ADRIndexError("policy must be an object")
    allowed_statuses = policy.get("statuses")
    active_statuses = policy.get("active_statuses")
    if not isinstance(allowed_statuses, list) or not allowed_statuses:
        raise ADRIndexError("policy statuses must be non-empty")
    if not isinstance(active_statuses, list) or not active_statuses:
        raise ADRIndexError("policy active_statuses must be non-empty")
    if not set(active_statuses) <= set(allowed_statuses):
        raise ADRIndexError("active_statuses must be a subset of statuses")

    governed = index.get("governed_path_patterns")
    if not isinstance(governed, list) or not governed:
        raise ADRIndexError("governed_path_patterns must be non-empty")
    if len(governed) != len(set(governed)):
        raise ADRIndexError("governed_path_patterns contains duplicates")
    for pattern in governed:
        _path(pattern.replace("**", "x").replace("*", "x"))

    records = index.get("records")
    if not isinstance(records, list) or not records:
        raise ADRIndexError("records must be non-empty")

    ids: set[str] = set()
    paths: set[str] = set()
    active_impact: set[str] = set()
    record_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ADRIndexError("ADR record must be an object")
        adr_id = record.get("id")
        if not isinstance(adr_id, str) or not _ID.fullmatch(adr_id):
            raise ADRIndexError(f"invalid ADR id: {adr_id!r}")
        if adr_id in ids:
            raise ADRIndexError(f"duplicate ADR id: {adr_id}")
        ids.add(adr_id)
        record_by_id[adr_id] = record

        status = record.get("status")
        if status not in allowed_statuses:
            raise ADRIndexError(f"{adr_id} has unsupported status {status!r}")
        rel = _path(record.get("path"))
        if not rel.startswith("docs/adr/ADR-") or not rel.endswith(".md"):
            raise ADRIndexError(f"{adr_id} path must be docs/adr/ADR-*.md")
        if rel in paths:
            raise ADRIndexError(f"duplicate ADR path: {rel}")
        paths.add(rel)
        if not (root / rel).is_file():
            raise ADRIndexError(f"{adr_id} document is missing: {rel}")

        refs = record.get("masterplan_refs")
        if not isinstance(refs, list) or not refs:
            raise ADRIndexError(f"{adr_id} must name masterplan_refs")
        unknown = sorted(set(refs) - set(volumes))
        if unknown:
            raise ADRIndexError(f"{adr_id} references unknown masterplan volumes: {unknown}")

        impact = record.get("impacted_paths")
        if not isinstance(impact, list) or not impact:
            raise ADRIndexError(f"{adr_id} must name impacted_paths")
        if len(impact) != len(set(impact)):
            raise ADRIndexError(f"{adr_id} impacted_paths contains duplicates")
        for pattern in impact:
            if pattern not in governed:
                raise ADRIndexError(
                    f"{adr_id} impact {pattern!r} is not a governed architecture pattern"
                )
        if status in active_statuses:
            active_impact.update(impact)

        supersedes = record.get("supersedes")
        if not isinstance(supersedes, list):
            raise ADRIndexError(f"{adr_id} supersedes must be a list")
        if adr_id in supersedes:
            raise ADRIndexError(f"{adr_id} cannot supersede itself")
        if status == "superseded":
            replacement = record.get("superseded_by")
            if not isinstance(replacement, str) or not replacement:
                raise ADRIndexError(f"{adr_id} superseded record needs superseded_by")
        elif record.get("superseded_by") is not None:
            raise ADRIndexError(f"{adr_id} active/non-superseded record cannot name superseded_by")

    for adr_id, record in record_by_id.items():
        for prior in record.get("supersedes", []):
            if prior not in record_by_id:
                raise ADRIndexError(f"{adr_id} supersedes unknown ADR {prior}")
        replacement = record.get("superseded_by")
        if replacement is not None and replacement not in record_by_id:
            raise ADRIndexError(f"{adr_id} superseded_by references unknown ADR {replacement}")

    doc_dir = root / policy.get("adr_directory", "docs/adr")
    discovered = {
        path.relative_to(root).as_posix()
        for path in doc_dir.glob("ADR-*.md")
        if path.is_file()
    }
    if discovered != paths:
        missing_index = sorted(discovered - paths)
        stale_index = sorted(paths - discovered)
        raise ADRIndexError(
            f"ADR document/index coverage drift; unindexed={missing_index}, missing={stale_index}"
        )

    uncovered = sorted(set(governed) - active_impact)
    if uncovered:
        raise ADRIndexError(f"governed architecture paths lack active ADR coverage: {uncovered}")

    return {
        "status": "valid",
        "record_count": len(records),
        "active_record_count": sum(r.get("status") in active_statuses for r in records),
        "governed_pattern_count": len(governed),
        "masterplan_binding": "VOL-058",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ADRIndexError as exc:
        print(f"architecture ADR index: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "architecture ADR index: OK "
            f"({result['record_count']} records, "
            f"{result['governed_pattern_count']} governed patterns)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
