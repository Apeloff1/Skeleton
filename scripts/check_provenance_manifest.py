#!/usr/bin/env python3
"""Validate the consolidation provenance manifest without network access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

SOURCE_DISPOSITIONS = {
    "promote",
    "promote-unique-only",
    "adapt-unique-only",
    "characterize-and-deduplicate",
    "boundary-consumer",
    "reject",
}
MATURITY = {"candidate", "characterized", "promoted", "rejected"}
TEST_STATUS = {"not-run", "characterized", "passing"}
CANONICAL_STATUS = {"candidate", "canonical", "rejected"}
LICENSE_STATUS = {"owner-controlled", "spdx", "unknown", "unlicensed"}


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA1_RE.fullmatch(value) is not None


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_license(
    license_data: object,
    *,
    label: str,
    repository: str,
    release_eligible: bool,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(license_data, dict):
        return [f"{label}.license must be an object"]

    unknown = set(license_data) - {"status", "spdx"}
    if unknown:
        errors.append(f"{label}.license has unknown fields: {', '.join(sorted(unknown))}")

    status = license_data.get("status")
    spdx = license_data.get("spdx")
    if status not in LICENSE_STATUS:
        errors.append(f"{label}.license.status must be one of {sorted(LICENSE_STATUS)}")
        return errors

    if status == "owner-controlled":
        if not repository.startswith("Apeloff1/"):
            errors.append(f"{label}: owner-controlled is only valid for the owner-controlled repository namespace")
        if spdx is not None:
            errors.append(f"{label}.license.spdx must be null for owner-controlled licensing")
    elif status == "spdx":
        if not _nonempty_string(spdx):
            errors.append(f"{label}.license.spdx is required when status is spdx")
    elif spdx is not None:
        errors.append(f"{label}.license.spdx must be null when license status is {status}")

    if release_eligible and status in {"unknown", "unlicensed"}:
        errors.append(f"{label}: canonical/release-eligible content cannot have {status} licensing")
    return errors


def _validate_path_value(value: object, *, label: str, nullable: bool = False) -> list[str]:
    if value is None and nullable:
        return []
    if not _nonempty_string(value):
        return [f"{label} must be a non-empty repository-relative path"]
    text = str(value)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        return [f"{label} must stay inside the repository"]
    return []


def validate_manifest(payload: object, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["manifest root must be an object"]

    required_top = {
        "schema_version",
        "canonical_repository",
        "inventory_scope",
        "inventory_date",
        "license_policy",
        "sources",
        "components",
    }
    allowed_top = required_top
    missing_top = required_top - set(payload)
    unknown_top = set(payload) - allowed_top
    if missing_top:
        errors.append(f"manifest missing fields: {', '.join(sorted(missing_top))}")
    if unknown_top:
        errors.append(f"manifest has unknown fields: {', '.join(sorted(unknown_top))}")

    if payload.get("schema_version") != 1:
        errors.append("schema_version must be exactly 1")
    if payload.get("canonical_repository") != "Apeloff1/Skeleton":
        errors.append("canonical_repository must be Apeloff1/Skeleton")
    if not _nonempty_string(payload.get("inventory_scope")):
        errors.append("inventory_scope must be non-empty")
    if not _nonempty_string(payload.get("inventory_date")):
        errors.append("inventory_date must be non-empty")

    policy = payload.get("license_policy")
    if not isinstance(policy, dict):
        errors.append("license_policy must be an object")
    else:
        if policy.get("owner_controlled_status") != "owner-controlled":
            errors.append("license_policy.owner_controlled_status must be owner-controlled")
        if policy.get("unknown_blocks_canonical_release") is not True:
            errors.append("license_policy.unknown_blocks_canonical_release must be true")
        if policy.get("third_party_requires_spdx") is not True:
            errors.append("license_policy.third_party_requires_spdx must be true")

    sources = payload.get("sources")
    source_by_repo: dict[str, dict[str, Any]] = {}
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        sources = []

    source_fields = {
        "repository",
        "default_branch",
        "revision",
        "ownership",
        "license",
        "disposition",
        "capabilities",
    }
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = source_fields - set(source)
        unknown = set(source) - source_fields
        if missing:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")

        repository = source.get("repository")
        if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
            errors.append(f"{label}.repository must be owner/name")
            continue
        if repository in source_by_repo:
            errors.append(f"duplicate source repository: {repository}")
        else:
            source_by_repo[repository] = source

        if not _nonempty_string(source.get("default_branch")):
            errors.append(f"{label}.default_branch must be non-empty")
        if not _is_sha(source.get("revision")):
            errors.append(f"{label}.revision must be an exact 40-character lowercase Git SHA")
        if source.get("ownership") not in {"owner-controlled", "third-party"}:
            errors.append(f"{label}.ownership must be owner-controlled or third-party")
        if source.get("disposition") not in SOURCE_DISPOSITIONS:
            errors.append(f"{label}.disposition must be one of {sorted(SOURCE_DISPOSITIONS)}")
        capabilities = source.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or not all(_nonempty_string(v) for v in capabilities):
            errors.append(f"{label}.capabilities must be a non-empty string list")
        errors.extend(
            _validate_license(
                source.get("license"),
                label=label,
                repository=repository,
                release_eligible=False,
            )
        )

    components = payload.get("components")
    if not isinstance(components, list):
        errors.append("components must be a list")
        components = []

    ids: set[str] = set()
    canonical_destinations: set[str] = set()
    component_fields = {
        "id",
        "source_repository",
        "source_revision",
        "source_path",
        "source_blob",
        "equivalent_sources",
        "destination_path",
        "license",
        "maturity",
        "test_status",
        "canonical_status",
        "evidence",
    }
    required_component_fields = component_fields - {"equivalent_sources"}

    for index, component in enumerate(components):
        label = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{label} must be an object")
            continue

        missing = required_component_fields - set(component)
        unknown = set(component) - component_fields
        if missing:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")

        component_id = component.get("id")
        if not _nonempty_string(component_id):
            errors.append(f"{label}.id must be non-empty")
        elif component_id in ids:
            errors.append(f"duplicate component id: {component_id}")
        else:
            ids.add(str(component_id))

        source_repository = component.get("source_repository")
        if source_repository not in source_by_repo:
            errors.append(f"{label}.source_repository is not declared in sources: {source_repository!r}")
        if not _is_sha(component.get("source_revision")):
            errors.append(f"{label}.source_revision must be an exact 40-character lowercase Git SHA")

        errors.extend(_validate_path_value(component.get("source_path"), label=f"{label}.source_path", nullable=True))
        source_blob = component.get("source_blob")
        if source_blob is not None and not _is_sha(source_blob):
            errors.append(f"{label}.source_blob must be null or an exact 40-character lowercase Git blob SHA")
        errors.extend(
            _validate_path_value(
                component.get("destination_path"),
                label=f"{label}.destination_path",
                nullable=True,
            )
        )

        maturity = component.get("maturity")
        test_status = component.get("test_status")
        canonical_status = component.get("canonical_status")
        if maturity not in MATURITY:
            errors.append(f"{label}.maturity must be one of {sorted(MATURITY)}")
        if test_status not in TEST_STATUS:
            errors.append(f"{label}.test_status must be one of {sorted(TEST_STATUS)}")
        if canonical_status not in CANONICAL_STATUS:
            errors.append(f"{label}.canonical_status must be one of {sorted(CANONICAL_STATUS)}")

        repository_for_license = source_repository if isinstance(source_repository, str) else ""
        release_eligible = canonical_status == "canonical"
        errors.extend(
            _validate_license(
                component.get("license"),
                label=label,
                repository=repository_for_license,
                release_eligible=release_eligible,
            )
        )

        evidence = component.get("evidence")
        if not isinstance(evidence, list) or not all(_nonempty_string(v) for v in evidence):
            errors.append(f"{label}.evidence must be a string list")
            evidence = []
        for evidence_index, evidence_path in enumerate(evidence):
            errors.extend(
                _validate_path_value(
                    evidence_path,
                    label=f"{label}.evidence[{evidence_index}]",
                )
            )

        equivalents = component.get("equivalent_sources", [])
        if not isinstance(equivalents, list):
            errors.append(f"{label}.equivalent_sources must be a list")
            equivalents = []
        for equivalent_index, equivalent in enumerate(equivalents):
            equivalent_label = f"{label}.equivalent_sources[{equivalent_index}]"
            if not isinstance(equivalent, dict):
                errors.append(f"{equivalent_label} must be an object")
                continue
            required_equivalent = {"repository", "revision", "source_path", "source_blob"}
            if set(equivalent) != required_equivalent:
                errors.append(f"{equivalent_label} must contain exactly {sorted(required_equivalent)}")
            equivalent_repository = equivalent.get("repository")
            if equivalent_repository not in source_by_repo:
                errors.append(f"{equivalent_label}.repository is not declared in sources")
            if not _is_sha(equivalent.get("revision")):
                errors.append(f"{equivalent_label}.revision must be an exact Git SHA")
            errors.extend(
                _validate_path_value(
                    equivalent.get("source_path"),
                    label=f"{equivalent_label}.source_path",
                )
            )
            if not _is_sha(equivalent.get("source_blob")):
                errors.append(f"{equivalent_label}.source_blob must be an exact Git blob SHA")

        if canonical_status == "canonical":
            if maturity != "promoted":
                errors.append(f"{label}: canonical components must have maturity=promoted")
            if test_status != "passing":
                errors.append(f"{label}: canonical components must have test_status=passing")
            if component.get("source_path") is None or component.get("source_blob") is None:
                errors.append(f"{label}: canonical components require source_path and source_blob")
            destination = component.get("destination_path")
            if not _nonempty_string(destination):
                errors.append(f"{label}: canonical components require destination_path")
            else:
                destination_text = str(destination)
                if destination_text in canonical_destinations:
                    errors.append(f"duplicate canonical destination_path: {destination_text}")
                canonical_destinations.add(destination_text)
                if not (repo_root / destination_text).exists():
                    errors.append(f"{label}: canonical destination does not exist: {destination_text}")
            if not evidence:
                errors.append(f"{label}: canonical components require at least one test/evidence path")
            for evidence_path in evidence:
                if _nonempty_string(evidence_path) and not (repo_root / str(evidence_path)).exists():
                    errors.append(f"{label}: evidence path does not exist: {evidence_path}")
        elif canonical_status == "rejected" and maturity != "rejected":
            errors.append(f"{label}: rejected components must have maturity=rejected")

    return errors


def load_manifest(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"provenance manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid provenance manifest JSON at line {exc.lineno}, column {exc.colno}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_manifest(args.manifest)
    errors = validate_manifest(payload, args.repo_root)
    if errors:
        print("provenance-policy: manifest rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    source_count = len(payload.get("sources", [])) if isinstance(payload, dict) else 0
    components = payload.get("components", []) if isinstance(payload, dict) else []
    canonical_count = sum(
        1 for component in components if isinstance(component, dict) and component.get("canonical_status") == "canonical"
    )
    print(
        f"provenance-policy: OK ({source_count} sources, {len(components)} component records, "
        f"{canonical_count} canonical promotions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
