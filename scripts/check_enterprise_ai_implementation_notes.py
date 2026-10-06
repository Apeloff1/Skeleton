#!/usr/bin/env python3
"""Validate all October-2026 enterprise AI implementation dossiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("machine/enterprise_ai_implementation_notes_index.json")
MASTER = Path("machine/ai_master_plan.json")
SUPERIORITY = Path("machine/enterprise_ai_superiority.json")

GRADE_STATES = {
    "designed",
    "implemented",
    "hardened",
    "enterprise_qualified",
    "superior",
}
FORBIDDEN_PLACEHOLDERS = ("TODO", "TBD", "FILL LATER", "PLACEHOLDER")
SUMMARY_FIELDS = {
    "requirements": 4,
    "capabilities": 4,
    "contracts": 6,
    "canonical_paths": 8,
    "risks": 4,
    "gaps": 4,
    "tests": 8,
    "evaluations": 6,
    "existing_evidence": 8,
}


class ImplementationNotesError(RuntimeError):
    """Enterprise implementation dossier authority is invalid or stale."""


def _reject_constant(token: str) -> None:
    raise ImplementationNotesError(f"non-finite JSON token rejected: {token}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ImplementationNotesError(f"duplicate JSON object key: {key}")
        output[key] = value
    return output


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ImplementationNotesError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImplementationNotesError(f"{path} must contain an object")
    return payload


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ImplementationNotesError(f"{label} must be canonical non-empty text")
    upper = value.upper()
    if any(token in upper for token in FORBIDDEN_PLACEHOLDERS):
        raise ImplementationNotesError(f"{label} contains placeholder text")
    return value


def _text_list(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ImplementationNotesError(
            f"{label} must contain at least {minimum} entries"
        )
    rows = [_text(item, f"{label}[]") for item in value]
    if len(rows) != len(set(rows)):
        raise ImplementationNotesError(f"{label} must contain unique entries")
    return rows


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ImplementationNotesError(f"{label} must be an object")
    return value


def _master_volumes(master: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = master.get("volumes")
    if not isinstance(rows, list) or len(rows) != 421:
        raise ImplementationNotesError("master plan must contain 421 volumes")
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        item = _mapping(row, "master volume")
        ref = _text(item.get("key"), "master volume key")
        if ref in output:
            raise ImplementationNotesError(f"duplicate master volume: {ref}")
        output[ref] = item
    expected = {f"VOL-{index:03d}" for index in range(421)}
    if set(output) != expected:
        raise ImplementationNotesError("master volume set must equal VOL-000..VOL-420")
    return output


def _expected_summary(master: Mapping[str, Any], field: str) -> list[Any]:
    source_field = "implementation_paths" if field == "canonical_paths" else field
    value = master.get(source_field, [])
    if not isinstance(value, list):
        raise ImplementationNotesError(
            f"{master.get('key')} {source_field} must be a list"
        )
    return value[: SUMMARY_FIELDS[field]]


def _validate_dossier(
    dossier: Mapping[str, Any],
    *,
    master: Mapping[str, Any],
    required_levels: list[Mapping[str, Any]],
    standard_version: str,
) -> None:
    ref = _text(dossier.get("volume_ref"), "dossier.volume_ref")
    if ref != master.get("key"):
        raise ImplementationNotesError(f"{ref} dossier/master key mismatch")
    if dossier.get("title") != master.get("title"):
        raise ImplementationNotesError(f"{ref} title drift")
    if dossier.get("depth_pass") != master.get("depth_pass"):
        raise ImplementationNotesError(f"{ref} depth-pass drift")
    if dossier.get("october_2026_standard") != "skeleton.enterprise_ai.2026-10":
        raise ImplementationNotesError(f"{ref} October 2026 standard binding missing")
    if standard_version != "2026.10":
        raise ImplementationNotesError("implementation standard version drift")
    if dossier.get("legacy_implementation_status") != master.get("implementation_status"):
        raise ImplementationNotesError(f"{ref} legacy implementation status drift")
    state = dossier.get("enterprise_grade_state")
    if state not in GRADE_STATES or state != master.get("enterprise_grade_state"):
        raise ImplementationNotesError(f"{ref} enterprise grade state drift")
    if dossier.get("enterprise_grade_target") != master.get("enterprise_grade_target"):
        raise ImplementationNotesError(f"{ref} enterprise target drift")
    if dossier.get("enterprise_superiority_profile") != master.get(
        "enterprise_superiority_profile"
    ):
        raise ImplementationNotesError(f"{ref} superiority profile drift")

    summary = _mapping(dossier.get("implementation_summary"), f"{ref}.summary")
    if set(summary) != set(SUMMARY_FIELDS):
        raise ImplementationNotesError(f"{ref} implementation summary field drift")
    for field in SUMMARY_FIELDS:
        actual = summary.get(field)
        if not isinstance(actual, list):
            raise ImplementationNotesError(f"{ref}.{field} must be a list")
        expected = _expected_summary(master, field)
        if actual != expected:
            raise ImplementationNotesError(f"{ref}.{field} is stale versus masterplan")

    levels = dossier.get("implementation_levels")
    if not isinstance(levels, list) or len(levels) != len(required_levels):
        raise ImplementationNotesError(
            f"{ref} requires exactly {len(required_levels)} implementation levels"
        )
    seen: set[str] = set()
    for index, (raw, required) in enumerate(zip(levels, required_levels)):
        level = _mapping(raw, f"{ref}.level[{index}]")
        level_id = _text(level.get("id"), f"{ref}.level.id")
        level_name = _text(level.get("name"), f"{ref}.{level_id}.name")
        if level_id in seen:
            raise ImplementationNotesError(f"{ref} duplicate level {level_id}")
        seen.add(level_id)
        if level_id != required["id"] or level_name != required["name"]:
            raise ImplementationNotesError(
                f"{ref} level order/name drift at {level_id}"
            )
        notes = _text_list(
            level.get("implementation_notes"),
            f"{ref}.{level_id}.implementation_notes",
            minimum=2,
        )
        acceptance = _text_list(
            level.get("acceptance"),
            f"{ref}.{level_id}.acceptance",
            minimum=2,
        )
        if sum(len(item) for item in notes) < 120:
            raise ImplementationNotesError(
                f"{ref}.{level_id} implementation notes are too shallow"
            )
        if sum(len(item) for item in acceptance) < 80:
            raise ImplementationNotesError(
                f"{ref}.{level_id} acceptance criteria are too shallow"
            )

    _text_list(
        dossier.get("evidence_policy"),
        f"{ref}.evidence_policy",
        minimum=3,
    )
    _text(dossier.get("completion_rule"), f"{ref}.completion_rule")


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    index = _load(root / INDEX)
    master = _load(root / MASTER)
    superiority = _load(root / SUPERIORITY)

    if index.get("schema_version") != (
        "skeleton.enterprise_ai.implementation_notes_index.v1"
    ):
        raise ImplementationNotesError("unsupported implementation-note index schema")
    if index.get("standard_version") != "2026.10":
        raise ImplementationNotesError("October 2026 implementation standard required")
    if index.get("status") != "active_design_authority":
        raise ImplementationNotesError("implementation-note authority must be active")

    scope = _mapping(index.get("scope"), "scope")
    if scope.get("first_volume") != "VOL-000" or scope.get("last_volume") != "VOL-420":
        raise ImplementationNotesError("implementation-note scope drift")
    if scope.get("expected_volume_count") != 421:
        raise ImplementationNotesError("implementation-note volume count must be 421")

    authority = _mapping(index.get("authority"), "authority")
    expected_authority = {
        "master_plan": str(MASTER),
        "enterprise_superiority": str(SUPERIORITY),
        "validator": "scripts/check_enterprise_ai_implementation_notes.py",
        "tests": "tests/test_enterprise_ai_implementation_notes.py",
    }
    for key, expected in expected_authority.items():
        if authority.get(key) != expected:
            raise ImplementationNotesError(f"authority drift: {key}")

    required_levels_raw = index.get("required_levels")
    if not isinstance(required_levels_raw, list) or len(required_levels_raw) != 14:
        raise ImplementationNotesError("exactly 14 October 2026 levels are required")
    required_levels: list[Mapping[str, Any]] = []
    for position, raw in enumerate(required_levels_raw):
        level = _mapping(raw, f"required_levels[{position}]")
        expected_id = f"L{position:02d}"
        if level.get("id") != expected_id:
            raise ImplementationNotesError(
                f"required level order drift: expected {expected_id}"
            )
        _text(level.get("name"), f"{expected_id}.name")
        required_levels.append(level)

    non_negotiables = _text_list(
        index.get("october_2026_non_negotiables"),
        "october_2026_non_negotiables",
        minimum=16,
    )
    joined = "\n".join(non_negotiables).lower()
    for concept in (
        "canonical owner",
        "tenant",
        "idempotency",
        "p95/p99",
        "rollback",
        "exact-head",
        "421 volumes",
    ):
        if concept not in joined:
            raise ImplementationNotesError(
                f"October 2026 non-negotiable missing concept: {concept}"
            )

    master_volumes = _master_volumes(master)
    files = index.get("dossier_files")
    if not isinstance(files, list) or len(files) != 11:
        raise ImplementationNotesError("exactly 11 depth-pass dossier files required")

    seen_depth: set[str] = set()
    seen_volumes: set[str] = set()
    dossiers = 0
    for raw in files:
        file_entry = _mapping(raw, "dossier file")
        depth_pass = _text(file_entry.get("depth_pass"), "dossier file depth_pass")
        path = Path(_text(file_entry.get("path"), f"{depth_pass}.path"))
        _text(file_entry.get("human_path"), f"{depth_pass}.human_path")
        if depth_pass in seen_depth:
            raise ImplementationNotesError(f"duplicate depth-pass file: {depth_pass}")
        seen_depth.add(depth_pass)
        payload = _load(root / path)
        if payload.get("schema_version") != (
            "skeleton.enterprise_ai.implementation_notes.v1"
        ):
            raise ImplementationNotesError(f"{path} schema drift")
        if payload.get("standard_version") != index.get("standard_version"):
            raise ImplementationNotesError(f"{path} standard version drift")
        if payload.get("generated_from_master_plan") != master.get("plan_version"):
            raise ImplementationNotesError(f"{path} master-plan version drift")
        if payload.get("depth_pass") != depth_pass:
            raise ImplementationNotesError(f"{path} depth-pass payload drift")
        rows = payload.get("dossiers")
        if not isinstance(rows, list) or payload.get("volume_count") != len(rows):
            raise ImplementationNotesError(f"{path} volume count drift")
        for dossier_raw in rows:
            dossier = _mapping(dossier_raw, f"{path}.dossier")
            ref = _text(dossier.get("volume_ref"), "dossier.volume_ref")
            if ref in seen_volumes:
                raise ImplementationNotesError(f"duplicate dossier volume: {ref}")
            if ref not in master_volumes:
                raise ImplementationNotesError(f"unknown dossier volume: {ref}")
            if master_volumes[ref].get("depth_pass") != depth_pass:
                raise ImplementationNotesError(f"{ref} stored in wrong depth pass")
            _validate_dossier(
                dossier,
                master=master_volumes[ref],
                required_levels=required_levels,
                standard_version=str(index["standard_version"]),
            )
            seen_volumes.add(ref)
            dossiers += 1

    if seen_volumes != set(master_volumes):
        missing = sorted(set(master_volumes) - seen_volumes)
        extra = sorted(seen_volumes - set(master_volumes))
        raise ImplementationNotesError(
            f"dossier coverage mismatch missing={missing} extra={extra}"
        )

    master_authority = _mapping(master.get("authority"), "master.authority")
    if master_authority.get("enterprise_ai_implementation_notes") != str(INDEX):
        raise ImplementationNotesError("masterplan missing implementation-note authority")
    superiority_authority = _mapping(
        superiority.get("authority"),
        "superiority.authority",
    )
    if superiority_authority.get("enterprise_ai_implementation_notes") != str(INDEX):
        raise ImplementationNotesError(
            "superiority policy missing implementation-note authority"
        )
    coverage = _mapping(superiority.get("coverage"), "superiority.coverage")
    if coverage.get("implementation_dossier_required_for_all_volumes") is not True:
        raise ImplementationNotesError(
            "superiority policy must require dossiers for every volume"
        )

    return {
        "status": "valid",
        "standard_version": index["standard_version"],
        "master_plan_version": master["plan_version"],
        "volume_count": len(master_volumes),
        "dossier_count": dossiers,
        "depth_pass_count": len(seen_depth),
        "required_level_count": len(required_levels),
        "all_421_volumes_have_deep_implementation_notes": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.root))
    except ImplementationNotesError as exc:
        print(f"enterprise AI implementation notes: FAIL: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("enterprise AI implementation notes: PASS")
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
