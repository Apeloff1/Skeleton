#!/usr/bin/env python3
"""Validate exact-head release attribution coverage and render notices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.release.attribution import (
    AttributionEntry,
    render_release_notice,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_release_attribution.json")
EXPECTED_TASK = "P1-REL-06"
EXPECTED_ACCOUNTABILITY = "ACC-P1-REL-06"
EXPECTED_POLICY = {
    "root_license_required": True,
    "all_vendored_license_files_must_be_registered": True,
    "exact_head_license_digest_required": True,
    "deterministic_notice_required": True,
    "production_authority": False,
}


class ReleaseAttributionValidationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseAttributionValidationError(
            f"cannot read attribution registry: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReleaseAttributionValidationError(
            "registry root must be an object"
        )
    return payload


def discover_license_paths(root: Path) -> tuple[str, ...]:
    paths = {"LICENSE"}
    external = root / "skeleton/ai/research/external"
    if external.exists():
        for path in external.rglob("LICENSE.upstream.txt"):
            paths.add(path.relative_to(root).as_posix())
    return tuple(sorted(paths))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_entries(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> tuple[
    dict[str, Any],
    tuple[AttributionEntry, ...],
    dict[str, str],
    tuple[str, ...],
]:
    payload = _load(root / registry_path)
    allowed_root = {
        "schema_version",
        "registry_version",
        "task_id",
        "accountability_ref",
        "authority",
        "policy",
        "components",
    }
    unknown_root = set(payload) - allowed_root
    if unknown_root:
        raise ReleaseAttributionValidationError(
            f"unknown registry fields: {sorted(unknown_root)}"
        )
    if payload.get("schema_version") != 1:
        raise ReleaseAttributionValidationError(
            "schema_version must equal 1"
        )
    if payload.get("task_id") != EXPECTED_TASK:
        raise ReleaseAttributionValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise ReleaseAttributionValidationError(
            "accountability_ref drift"
        )
    if payload.get("authority") != str(REGISTRY_PATH):
        raise ReleaseAttributionValidationError(
            "authority path drift"
        )
    if payload.get("policy") != EXPECTED_POLICY:
        raise ReleaseAttributionValidationError(
            "attribution policy drift"
        )

    rows = payload.get("components")
    if not isinstance(rows, list) or not rows:
        raise ReleaseAttributionValidationError(
            "components must be a non-empty list"
        )

    entries: list[AttributionEntry] = []
    observed: dict[str, str] = {}
    seen_components: set[str] = set()
    seen_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseAttributionValidationError(
                "component entries must be objects"
            )
        allowed = {
            "component_id",
            "source_ref",
            "license_path",
            "third_party",
        }
        unknown = set(row) - allowed
        if unknown:
            raise ReleaseAttributionValidationError(
                f"unknown component fields: {sorted(unknown)}"
            )
        component_id = row.get("component_id")
        license_path = row.get("license_path")
        if not isinstance(component_id, str):
            raise ReleaseAttributionValidationError(
                "component_id must be text"
            )
        if not isinstance(license_path, str):
            raise ReleaseAttributionValidationError(
                "license_path must be text"
            )
        if component_id in seen_components:
            raise ReleaseAttributionValidationError(
                f"duplicate component_id: {component_id}"
            )
        if license_path in seen_paths:
            raise ReleaseAttributionValidationError(
                f"duplicate license_path: {license_path}"
            )
        seen_components.add(component_id)
        seen_paths.add(license_path)

        absolute = root / license_path
        if not absolute.is_file():
            raise ReleaseAttributionValidationError(
                f"registered license does not exist: {license_path}"
            )
        digest = _sha256(absolute)
        observed[license_path] = digest
        entries.append(
            AttributionEntry(
                component_id=component_id,
                source_ref=row["source_ref"],
                license_path=license_path,
                license_digest=digest,
                third_party=row["third_party"],
            )
        )

    discovered = discover_license_paths(root)
    registered = tuple(sorted(seen_paths))
    if registered != discovered:
        missing = sorted(set(discovered) - set(registered))
        stale = sorted(set(registered) - set(discovered))
        raise ReleaseAttributionValidationError(
            "attribution registry coverage drift: "
            f"missing={missing}, stale={stale}"
        )

    return payload, tuple(entries), observed, discovered


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    payload, entries, _, discovered = load_entries(
        root,
        registry_path=registry_path,
    )
    notice = render_release_notice(entries)
    return {
        "schema_version": 1,
        "registry_version": payload["registry_version"],
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "component_count": len(entries),
        "discovered_license_count": len(discovered),
        "notice_digest": hashlib.sha256(
            notice.encode("utf-8")
        ).hexdigest(),
        "production_authority": False,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_PATH,
    )
    parser.add_argument("--notice-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = validate_repository(
            ROOT,
            registry_path=args.registry,
        )
        _, entries, _, _ = load_entries(
            ROOT,
            registry_path=args.registry,
        )
        notice = render_release_notice(entries)
        if args.notice_out is not None:
            args.notice_out.parent.mkdir(parents=True, exist_ok=True)
            args.notice_out.write_text(notice, encoding="utf-8")
        if args.report_out is not None:
            args.report_out.parent.mkdir(parents=True, exist_ok=True)
            args.report_out.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (
        ReleaseAttributionValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 release attribution: rejected: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
