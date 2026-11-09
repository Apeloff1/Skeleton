#!/usr/bin/env python3
"""Fail closed when consolidation provenance is internally incomplete."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"
PROMOTION_RELEVANT_DISPOSITIONS = {
    "promote",
    "promote-unique-only",
    "adapt-unique-only",
    "characterize-and-deduplicate",
    "boundary-consumer",
}


def _license_identity(value: object) -> tuple[object, object] | None:
    if not isinstance(value, dict):
        return None
    return value.get("status"), value.get("spdx")


def _path_parts(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return PurePosixPath(value).parts


def _paths_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    shorter = min(len(left), len(right))
    return left[:shorter] == right[:shorter]


def validate_completeness(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["manifest root must be an object"]

    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    components = payload.get("components") if isinstance(payload.get("components"), list) else []
    source_by_repo: dict[str, dict[str, Any]] = {}
    for source in sources:
        if isinstance(source, dict) and isinstance(source.get("repository"), str):
            source_by_repo[source["repository"]] = source

    referenced_sources: set[str] = set()
    canonical_destinations: list[tuple[str, tuple[str, ...]]] = []

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        label = f"components[{index}]"
        source_repository = component.get("source_repository")
        declared = source_by_repo.get(source_repository) if isinstance(source_repository, str) else None
        if declared is not None:
            referenced_sources.add(source_repository)
            if component.get("source_revision") != declared.get("revision"):
                errors.append(f"{label}.source_revision must match declared source revision for {source_repository}")
            if _license_identity(component.get("license")) != _license_identity(declared.get("license")):
                errors.append(f"{label}.license must match declared source license for {source_repository}")

        source_path = component.get("source_path")
        source_blob = component.get("source_blob")
        if (source_path is None) != (source_blob is None):
            errors.append(f"{label}.source_path and source_blob must either both be set or both be null")

        maturity = component.get("maturity")
        canonical_status = component.get("canonical_status")
        test_status = component.get("test_status")
        if maturity == "promoted" and canonical_status != "canonical":
            errors.append(f"{label}: maturity=promoted requires canonical_status=canonical")
        if maturity == "promoted" and test_status != "passing":
            errors.append(f"{label}: maturity=promoted requires test_status=passing")
        if maturity == "rejected" and canonical_status != "rejected":
            errors.append(f"{label}: maturity=rejected requires canonical_status=rejected")

        if canonical_status == "canonical":
            parts = _path_parts(component.get("destination_path"))
            if parts is not None:
                canonical_destinations.append((label, parts))

        equivalents = component.get("equivalent_sources", [])
        if isinstance(equivalents, list):
            for equivalent_index, equivalent in enumerate(equivalents):
                if not isinstance(equivalent, dict):
                    continue
                equivalent_repository = equivalent.get("repository")
                declared_equivalent = source_by_repo.get(equivalent_repository) if isinstance(equivalent_repository, str) else None
                if declared_equivalent is None:
                    continue
                referenced_sources.add(equivalent_repository)
                if equivalent.get("revision") != declared_equivalent.get("revision"):
                    errors.append(
                        f"{label}.equivalent_sources[{equivalent_index}].revision must match declared source revision for {equivalent_repository}"
                    )

    for source in sources:
        if not isinstance(source, dict):
            continue
        repository = source.get("repository")
        disposition = source.get("disposition")
        if isinstance(repository, str) and disposition in PROMOTION_RELEVANT_DISPOSITIONS and repository not in referenced_sources:
            errors.append(f"source {repository} has disposition={disposition} but no component or equivalent-source decision")

    for index, (left_label, left_parts) in enumerate(canonical_destinations):
        for right_label, right_parts in canonical_destinations[index + 1 :]:
            if _paths_overlap(left_parts, right_parts):
                errors.append(f"canonical destination scopes overlap: {left_label} and {right_label}")

    return errors


def load_manifest(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"provenance manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid provenance manifest JSON at line {exc.lineno}, column {exc.colno}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    payload = load_manifest(args.manifest)
    errors = validate_completeness(payload)
    if errors:
        print("provenance-completeness: manifest rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    components = payload.get("components", []) if isinstance(payload, dict) else []
    print(f"provenance-completeness: OK ({len(sources)} sources, {len(components)} component decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
