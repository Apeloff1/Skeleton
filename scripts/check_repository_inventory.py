#!/usr/bin/env python3
"""Validate the account repository inventory and bind promoted sources to it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = REPO_ROOT / "docs" / "lineage" / "repository-inventory.v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^Apeloff1/[A-Za-z0-9_.-]+$")
MATRIX_DISPOSITIONS = {
    "canonical",
    "promote",
    "characterize",
    "quarantine",
    "inspect",
    "archive",
}
CONTENT_STATUS = {"non-empty", "empty"}
REVISION_STATUS = {"verified", "pending", "not-applicable"}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA1_RE.fullmatch(value) is not None


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"invalid {label} JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc


def validate_inventory(
    inventory: object,
    manifest: object,
) -> list[str]:
    """Return validation errors for the inventory/manifest pair."""

    errors: list[str] = []
    if not isinstance(inventory, dict):
        return ["inventory root must be an object"]

    required_top = {
        "schema_version",
        "owner",
        "captured_date",
        "capture_method",
        "repository_count",
        "non_empty_count",
        "empty_count",
        "repositories",
    }
    missing = required_top - set(inventory)
    unknown = set(inventory) - required_top
    if missing:
        errors.append(f"inventory missing fields: {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"inventory has unknown fields: {', '.join(sorted(unknown))}")

    if inventory.get("schema_version") != 1:
        errors.append("schema_version must be exactly 1")
    if inventory.get("owner") != "Apeloff1":
        errors.append("owner must be Apeloff1")
    if not _nonempty_string(inventory.get("captured_date")):
        errors.append("captured_date must be non-empty")
    if not _nonempty_string(inventory.get("capture_method")):
        errors.append("capture_method must be non-empty")

    repositories = inventory.get("repositories")
    if not isinstance(repositories, list):
        errors.append("repositories must be a list")
        repositories = []

    fields = {
        "repository",
        "default_branch",
        "size_kb",
        "content_status",
        "matrix_disposition",
        "head_revision",
        "revision_status",
    }
    by_repository: dict[str, dict[str, Any]] = {}
    computed_non_empty = 0
    computed_empty = 0

    for index, entry in enumerate(repositories):
        label = f"repositories[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue

        entry_missing = fields - set(entry)
        entry_unknown = set(entry) - fields
        if entry_missing:
            errors.append(f"{label} missing fields: {', '.join(sorted(entry_missing))}")
        if entry_unknown:
            errors.append(f"{label} has unknown fields: {', '.join(sorted(entry_unknown))}")

        repository = entry.get("repository")
        if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
            errors.append(f"{label}.repository must be an Apeloff1/name repository")
        elif repository in by_repository:
            errors.append(f"duplicate repository inventory entry: {repository}")
        else:
            by_repository[repository] = entry

        if not _nonempty_string(entry.get("default_branch")):
            errors.append(f"{label}.default_branch must be non-empty")

        size_kb = entry.get("size_kb")
        if isinstance(size_kb, bool) or not isinstance(size_kb, int):
            errors.append(f"{label}.size_kb must be an integer")
        elif size_kb < 0:
            errors.append(f"{label}.size_kb must not be negative")

        content_status = entry.get("content_status")
        revision_status = entry.get("revision_status")
        head_revision = entry.get("head_revision")
        if content_status not in CONTENT_STATUS:
            errors.append(f"{label}.content_status must be one of {sorted(CONTENT_STATUS)}")
        if revision_status not in REVISION_STATUS:
            errors.append(f"{label}.revision_status must be one of {sorted(REVISION_STATUS)}")
        if entry.get("matrix_disposition") not in MATRIX_DISPOSITIONS:
            errors.append(
                f"{label}.matrix_disposition must be one of {sorted(MATRIX_DISPOSITIONS)}"
            )

        if content_status == "empty":
            computed_empty += 1
            if size_kb != 0:
                errors.append(f"{label}: empty repositories must have size_kb=0")
            if revision_status != "not-applicable":
                errors.append(
                    f"{label}: empty repositories must use revision_status=not-applicable"
                )
            if head_revision is not None:
                errors.append(f"{label}: empty repositories must have head_revision=null")
        elif content_status == "non-empty":
            computed_non_empty += 1
            if isinstance(size_kb, int) and not isinstance(size_kb, bool) and size_kb <= 0:
                errors.append(f"{label}: non-empty repositories must have size_kb>0")
            if revision_status not in {"verified", "pending"}:
                errors.append(
                    f"{label}: non-empty repositories must be verified or pending"
                )
            if revision_status == "verified" and not _is_sha(head_revision):
                errors.append(
                    f"{label}: verified repositories require an exact lowercase 40-character head_revision"
                )
            if revision_status == "pending" and head_revision is not None:
                errors.append(f"{label}: pending repositories must have head_revision=null")

    def _declared_count(name: str) -> int | None:
        value = inventory.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{name} must be a non-negative integer")
            return None
        return value

    repository_count = _declared_count("repository_count")
    non_empty_count = _declared_count("non_empty_count")
    empty_count = _declared_count("empty_count")
    if repository_count is not None and repository_count != len(repositories):
        errors.append(
            f"repository_count mismatch: declared {repository_count}, observed {len(repositories)}"
        )
    if non_empty_count is not None and non_empty_count != computed_non_empty:
        errors.append(
            f"non_empty_count mismatch: declared {non_empty_count}, observed {computed_non_empty}"
        )
    if empty_count is not None and empty_count != computed_empty:
        errors.append(
            f"empty_count mismatch: declared {empty_count}, observed {computed_empty}"
        )
    if repository_count is not None and non_empty_count is not None and empty_count is not None:
        if repository_count != non_empty_count + empty_count:
            errors.append("repository_count must equal non_empty_count + empty_count")

    if not isinstance(manifest, dict):
        errors.append("provenance manifest root must be an object")
        return errors
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        errors.append("provenance manifest sources must be a list")
        return errors

    for index, source in enumerate(sources):
        label = f"manifest.sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        repository = source.get("repository")
        revision = source.get("revision")
        if not isinstance(repository, str):
            errors.append(f"{label}.repository must be a string")
            continue
        inventory_entry = by_repository.get(repository)
        if inventory_entry is None:
            errors.append(f"{label}: source repository missing from inventory: {repository}")
            continue
        if inventory_entry.get("content_status") != "non-empty":
            errors.append(f"{label}: promoted source must be non-empty: {repository}")
        if inventory_entry.get("revision_status") != "verified":
            errors.append(f"{label}: promoted source must be revision-verified: {repository}")
        if inventory_entry.get("head_revision") != revision:
            errors.append(
                f"{label}: inventory head_revision does not match manifest revision for {repository}"
            )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = _load_json(args.inventory, "repository inventory")
    manifest = _load_json(args.manifest, "provenance manifest")
    errors = validate_inventory(inventory, manifest)
    if errors:
        print("repository-inventory-policy: inventory rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    assert isinstance(inventory, dict)
    repositories = inventory.get("repositories", [])
    pending = sum(
        1
        for entry in repositories
        if isinstance(entry, dict) and entry.get("revision_status") == "pending"
    )
    print(
        "repository-inventory-policy: OK "
        f"({inventory.get('repository_count')} repositories, "
        f"{inventory.get('non_empty_count')} non-empty, "
        f"{inventory.get('empty_count')} empty, {pending} pending revision verification)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
