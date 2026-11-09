#!/usr/bin/env python3
"""Materialize P1 primary-volume metadata from canonical task evidence.

This reconciler is intentionally non-authoritative. It may refresh only:
- implementation_paths
- tests
- evaluations
- evidence

It must never change maturity status, implementation status, gaps, completion
checkboxes, accountability records, or signoffs.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
BACKLOG = Path("machine/ai_p1_task_backlog.json")
EXECUTION_MAP = Path("machine/ai_p1_execution_map.json")

PROJECTED_FIELDS = (
    "implementation_paths",
    "tests",
    "evaluations",
    "evidence",
)


class VolumeMetadataError(RuntimeError):
    """P1 volume metadata projection is malformed or unsafe."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VolumeMetadataError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VolumeMetadataError(f"{path} must contain an object")
    return payload


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _is_materialized(reference: object) -> bool:
    return (
        isinstance(reference, str)
        and bool(reference.strip())
        and not reference.startswith("planned:")
    )


def _repository_reference_exists(root: Path, reference: str) -> bool:
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if glob.has_magic(reference):
        return any(root.glob(reference))
    path = root / candidate
    return path.is_file() or path.is_dir()


def _materialized_repository_refs(
    root: Path,
    values: object,
) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(
        str(value)
        for value in values
        if _is_materialized(value)
        and _repository_reference_exists(root, str(value))
    )


def _materialized_refs(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(
        str(value)
        for value in values
        if _is_materialized(value)
    )


def _primary_owners(execution_map: dict[str, Any]) -> dict[str, str]:
    lanes = execution_map.get("lanes")
    if not isinstance(lanes, list):
        raise VolumeMetadataError("P1 execution map lanes must be a list")

    owners: dict[str, str] = {}
    for lane in lanes:
        if not isinstance(lane, dict):
            raise VolumeMetadataError("P1 lane entries must be objects")
        lane_id = lane.get("id")
        refs = lane.get("primary_volume_refs")
        if not isinstance(lane_id, str) or not lane_id:
            raise VolumeMetadataError("P1 lane id is required")
        if not isinstance(refs, list):
            raise VolumeMetadataError(
                f"{lane_id}: primary_volume_refs must be a list"
            )
        for raw_ref in refs:
            ref = str(raw_ref)
            if ref in owners:
                raise VolumeMetadataError(
                    f"duplicate primary-volume owner: {ref}"
                )
            owners[ref] = lane_id
    return owners


def _tasks_by_volume(backlog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tasks = backlog.get("tasks")
    if not isinstance(tasks, list):
        raise VolumeMetadataError("P1 task backlog tasks must be a list")

    by_volume: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise VolumeMetadataError("P1 task entries must be objects")
        task_id = task.get("task_id")
        refs = task.get("volume_refs")
        if not isinstance(task_id, str) or not task_id:
            raise VolumeMetadataError("P1 task_id is required")
        if not isinstance(refs, list):
            raise VolumeMetadataError(
                f"{task_id}: volume_refs must be a list"
            )
        for raw_ref in refs:
            by_volume.setdefault(str(raw_ref), []).append(task)
    return by_volume


def _protected_snapshot(volume: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in volume.items()
        if key not in PROJECTED_FIELDS
    }


def _projection_for_volume(
    root: Path,
    volume: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> dict[str, list[str]]:
    if not tasks:
        raise VolumeMetadataError(
            f"{volume.get('key', '?')}: no mapped P1 tasks"
        )

    implementation_paths = _dedupe(
        _materialized_repository_refs(root, volume.get("implementation_paths"))
        + [
            reference
            for task in tasks
            for reference in _materialized_repository_refs(
                root,
                task.get("implementation_paths"),
            )
        ]
    )
    tests = _dedupe(
        _materialized_repository_refs(root, volume.get("tests"))
        + [
            reference
            for task in tasks
            for reference in _materialized_repository_refs(
                root,
                task.get("test_targets"),
            )
        ]
    )

    task_workflows = _dedupe(
        reference
        for task in tasks
        for reference in _materialized_repository_refs(
            root,
            task.get("implementation_paths"),
        )
        if reference.startswith(".github/workflows/")
    )
    evaluations = _dedupe(
        _materialized_refs(volume.get("evaluations"))
        + task_workflows
    )
    if not evaluations:
        evaluations = tests[:3]

    evidence = _dedupe(
        _materialized_refs(volume.get("evidence"))
        + [
            reference
            for task in tasks
            for reference in _materialized_refs(task.get("evidence_refs"))
        ]
    )

    projected = {
        "implementation_paths": implementation_paths,
        "tests": tests,
        "evaluations": evaluations,
        "evidence": evidence,
    }
    for field, values in projected.items():
        if not values:
            raise VolumeMetadataError(
                f"{volume.get('key', '?')}: projected {field} is empty"
            )
        if any(not _is_materialized(value) for value in values):
            raise VolumeMetadataError(
                f"{volume.get('key', '?')}: projected {field} is not materialized"
            )
    return projected


def project_repository(
    root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    master = _load(root / MASTER)
    backlog = _load(root / BACKLOG)
    execution_map = _load(root / EXECUTION_MAP)

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise VolumeMetadataError("master plan volumes must be a list")

    owners = _primary_owners(execution_map)
    by_volume = _tasks_by_volume(backlog)
    volume_by_key = {
        str(volume.get("key")): volume
        for volume in volumes
        if isinstance(volume, dict) and volume.get("key")
    }
    missing = sorted(set(owners) - set(volume_by_key))
    if missing:
        raise VolumeMetadataError(
            "missing P1 primary masterplan volumes: " + ",".join(missing)
        )

    changed: list[str] = []
    task_bindings: dict[str, list[str]] = {}

    for key in sorted(owners):
        volume = volume_by_key[key]
        before = _protected_snapshot(volume)
        tasks = by_volume.get(key, [])
        task_bindings[key] = [
            str(task["task_id"])
            for task in tasks
        ]
        projection = _projection_for_volume(root, volume, tasks)
        for field in PROJECTED_FIELDS:
            if volume.get(field) != projection[field]:
                volume[field] = projection[field]
        if _protected_snapshot(volume) != before:
            raise VolumeMetadataError(
                f"{key}: protected masterplan fields changed"
            )
        if any(
            volume[field] != projection[field]
            for field in PROJECTED_FIELDS
        ):
            raise VolumeMetadataError(
                f"{key}: projection was not applied deterministically"
            )
        changed.append(key)

    report = {
        "schema_version": 1,
        "engine": "p1-volume-metadata-projection-v1",
        "primary_volume_count": len(owners),
        "projected_volume_count": len(changed),
        "projected_fields": list(PROJECTED_FIELDS),
        "task_bindings": task_bindings,
        "non_authoritative": True,
        "mutates_maturity": False,
        "mutates_accountability": False,
    }
    return master, report


def _canonical_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the deterministic projection to machine/ai_master_plan.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the canonical masterplan differs from the projection.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path for a deterministic projection report.",
    )
    args = parser.parse_args(argv)

    if args.apply and args.check:
        parser.error("--apply and --check are mutually exclusive")

    try:
        original = _load(ROOT / MASTER)
        projected, report = project_repository(ROOT)
    except VolumeMetadataError as exc:
        print(f"P1 volume metadata projection: rejected: {exc}", file=sys.stderr)
        return 2

    expected_text = _canonical_text(projected)
    original_text = _canonical_text(original)

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.check:
        if original_text != expected_text:
            print(
                "P1 volume metadata projection: drift detected",
                file=sys.stderr,
            )
            return 1
    elif args.apply:
        (ROOT / MASTER).write_text(expected_text, encoding="utf-8")

    print(
        "P1 volume metadata projection: OK "
        f"({report['primary_volume_count']} primary volumes, "
        f"{report['projected_volume_count']} projected)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
