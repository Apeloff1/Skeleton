#!/usr/bin/env python3
"""Validate the non-empty owner-repository snapshot against the provenance manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = REPO_ROOT / "docs" / "lineage" / "source-repository-inventory.v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^Apeloff1/[A-Za-z0-9_.-]+$")
ROLES = {"canonical-receiver", "source-candidate"}
MANIFEST_STATUS = {"canonical", "curated", "uncharacterized"}
VISIBILITY = {"public", "private"}


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA1_RE.fullmatch(value) is not None


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"source inventory input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}") from exc


def validate_source_inventory(inventory: object, manifest: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(inventory, dict):
        return ["source inventory root must be an object"]
    if not isinstance(manifest, dict):
        return ["provenance manifest root must be an object"]

    expected_top = {
        "schema_version",
        "owner",
        "captured_date",
        "canonical_repository",
        "repository_count",
        "repositories",
    }
    missing = expected_top - set(inventory)
    unknown = set(inventory) - expected_top
    if missing:
        errors.append(f"source inventory missing fields: {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"source inventory has unknown fields: {', '.join(sorted(unknown))}")
    if inventory.get("schema_version") != 1:
        errors.append("source inventory schema_version must be exactly 1")
    if inventory.get("owner") != "Apeloff1":
        errors.append("source inventory owner must be Apeloff1")
    if inventory.get("canonical_repository") != "Apeloff1/Skeleton":
        errors.append("source inventory canonical_repository must be Apeloff1/Skeleton")
    if not isinstance(inventory.get("captured_date"), str) or not inventory.get("captured_date"):
        errors.append("source inventory captured_date must be non-empty")

    repositories = inventory.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        errors.append("source inventory repositories must be a non-empty list")
        repositories = []
    if inventory.get("repository_count") != len(repositories):
        errors.append("source inventory repository_count must equal repositories length")

    record_fields = {
        "repository",
        "default_branch",
        "size_kb",
        "visibility",
        "role",
        "manifest_status",
        "revision",
    }
    by_repo: dict[str, dict[str, Any]] = {}
    canonical_records: list[str] = []
    for index, record in enumerate(repositories):
        label = f"repositories[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(record) != record_fields:
            errors.append(f"{label} must contain exactly {sorted(record_fields)}")

        repository = record.get("repository")
        if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
            errors.append(f"{label}.repository must be an Apeloff1 owner/name repository")
            continue
        if repository in by_repo:
            errors.append(f"duplicate source inventory repository: {repository}")
        else:
            by_repo[repository] = record

        if record.get("default_branch") != "main":
            errors.append(f"{label}.default_branch must be main")
        size_kb = record.get("size_kb")
        if isinstance(size_kb, bool) or not isinstance(size_kb, int) or size_kb <= 0:
            errors.append(f"{label}.size_kb must be a positive integer; zero-size repositories stay outside this snapshot")
        if record.get("visibility") not in VISIBILITY:
            errors.append(f"{label}.visibility must be one of {sorted(VISIBILITY)}")
        if record.get("role") not in ROLES:
            errors.append(f"{label}.role must be one of {sorted(ROLES)}")
        if record.get("manifest_status") not in MANIFEST_STATUS:
            errors.append(f"{label}.manifest_status must be one of {sorted(MANIFEST_STATUS)}")
        revision = record.get("revision")
        if revision is not None and not _is_sha(revision):
            errors.append(f"{label}.revision must be null or an exact lowercase 40-character Git SHA")

        if record.get("role") == "canonical-receiver":
            canonical_records.append(repository)
            if repository != "Apeloff1/Skeleton" or record.get("manifest_status") != "canonical":
                errors.append(f"{label}: canonical receiver must be Apeloff1/Skeleton with manifest_status=canonical")
        elif record.get("manifest_status") == "canonical":
            errors.append(f"{label}: only the canonical receiver may have manifest_status=canonical")

    if canonical_records != ["Apeloff1/Skeleton"]:
        errors.append("source inventory must contain exactly one canonical receiver: Apeloff1/Skeleton")

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        errors.append("provenance manifest sources must be a list")
        sources = []

    manifest_sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not isinstance(source.get("repository"), str):
            errors.append(f"provenance manifest sources[{index}] is malformed")
            continue
        manifest_sources[source["repository"]] = source

    curated_inventory = {
        repository
        for repository, record in by_repo.items()
        if record.get("manifest_status") == "curated"
    }
    expected_curated = set(manifest_sources)
    if curated_inventory != expected_curated:
        missing_curated = sorted(expected_curated - curated_inventory)
        extra_curated = sorted(curated_inventory - expected_curated)
        if missing_curated:
            errors.append(f"manifest sources missing from source inventory curated set: {', '.join(missing_curated)}")
        if extra_curated:
            errors.append(f"source inventory marks repositories curated but manifest does not: {', '.join(extra_curated)}")

    for repository, source in manifest_sources.items():
        record = by_repo.get(repository)
        if record is None:
            continue
        manifest_revision = source.get("revision")
        if record.get("revision") != manifest_revision:
            errors.append(f"source inventory revision does not match manifest for {repository}")
        if record.get("role") != "source-candidate":
            errors.append(f"curated source must have role=source-candidate: {repository}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = _load(args.inventory)
    manifest = _load(args.manifest)
    errors = validate_source_inventory(inventory, manifest)
    if errors:
        print("provenance-source-inventory: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    repositories = inventory["repositories"]
    curated = sum(record["manifest_status"] == "curated" for record in repositories)
    uncharacterized = sum(record["manifest_status"] == "uncharacterized" for record in repositories)
    print(
        "provenance-source-inventory: OK "
        f"({len(repositories)} non-empty repositories, {curated} curated sources, "
        f"{uncharacterized} uncharacterized candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
