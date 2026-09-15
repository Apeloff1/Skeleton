#!/usr/bin/env python3
"""Deterministic release metadata, checksums, SBOM, and rebuild verification.

The release workflow uses this module without third-party runtime dependencies so the
metadata path itself is small, auditable, and reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
_CYCLONEDX_SPEC = "1.6"
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_commit(value: str) -> str:
    if not _COMMIT_RE.fullmatch(value):
        raise ValueError("source commit must be a 40-64 character hexadecimal Git object ID")
    return value.lower()


def _validate_epoch(value: str | int) -> int:
    try:
        epoch = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("source date epoch must be an integer") from exc
    if epoch < 0:
        raise ValueError("source date epoch cannot be negative")
    return epoch


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _file_record(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(path)
    if root is None:
        name = path.as_posix()
    else:
        name = resolved.relative_to(root.resolve()).as_posix()
    return {"name": name, "sha256": _sha256(resolved), "size": resolved.stat().st_size}


def _artifact_records(directory: Path) -> list[dict[str, Any]]:
    root = directory.resolve()
    if not root.is_dir():
        raise FileNotFoundError(directory)
    return [
        _file_record(path, root=root)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _input_records(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records = [_file_record(path) for path in paths]
    return sorted(records, key=lambda record: record["name"])


def _write_checksums(path: Path, records: Iterable[dict[str, Any]]) -> None:
    lines = [f"{record['sha256']}  {record['name']}" for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_provenance(args: argparse.Namespace) -> int:
    source_commit = _validate_commit(args.source_commit)
    source_date_epoch = _validate_epoch(args.source_date_epoch)
    artifacts_dir = Path(args.artifacts_dir)
    artifact_records = _artifact_records(artifacts_dir)
    inputs = _input_records(Path(item) for item in args.input)

    sbom_refs: list[dict[str, Any]] = []
    for item in args.sbom_ref:
        sbom = Path(item)
        record = _file_record(sbom, root=artifacts_dir)
        sbom_refs.append(record)
    sbom_refs.sort(key=lambda record: record["name"])

    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "commit": source_commit,
            "source_date_epoch": source_date_epoch,
        },
        "toolchain": {
            "implementation": sys.implementation.name,
            "python": platform.python_version(),
            "build": _package_version("build"),
            "setuptools": _package_version("setuptools"),
            "wheel": _package_version("wheel"),
        },
        "inputs": inputs,
        "sbom_refs": sbom_refs,
        "artifacts": artifact_records,
    }
    _json_dump(Path(args.output), payload)
    _write_checksums(Path(args.checksums), artifact_records)
    return 0


def _dependency_name(requirement: str) -> str:
    match = _DEP_NAME_RE.match(requirement.strip())
    if not match:
        raise ValueError(f"cannot parse dependency name from {requirement!r}")
    return match.group(0)


def write_sbom(args: argparse.Namespace) -> int:
    pyproject = Path(args.pyproject)
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml is missing [project]")

    name = project.get("name")
    version = project.get("version")
    dependencies = project.get("dependencies", [])
    if not isinstance(name, str) or not name:
        raise ValueError("project.name must be a non-empty string")
    if not isinstance(version, str) or not version:
        raise ValueError("project.version must be a non-empty string")
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise ValueError("project.dependencies must be a list of strings")

    source_commit = _validate_commit(args.source_commit)
    components = []
    for requirement in sorted(dependencies, key=str.lower):
        dep_name = _dependency_name(requirement)
        components.append(
            {
                "type": "library",
                "name": dep_name,
                "properties": [
                    {"name": "skeleton:declared-requirement", "value": requirement},
                ],
            }
        )

    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": _CYCLONEDX_SPEC,
        "serialNumber": f"urn:uuid:{source_commit[:8]}-{source_commit[8:12]}-{source_commit[12:16]}-{source_commit[16:20]}-{source_commit[20:32]}",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": name, "version": version},
            "properties": [
                {"name": "skeleton:source-commit", "value": source_commit},
                {"name": "skeleton:dependency-scope", "value": "declared-runtime"},
            ],
        },
        "components": components,
    }
    _json_dump(Path(args.output), payload)
    return 0


def compare_provenance(args: argparse.Namespace) -> int:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    keys = ("source", "toolchain", "inputs", "sbom_refs", "artifacts")
    mismatches = [key for key in keys if left.get(key) != right.get(key)]
    if mismatches:
        print("reproducibility mismatch: " + ", ".join(mismatches), file=sys.stderr)
        return 1
    print("reproducible release metadata matches")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit = subparsers.add_parser("emit", help="write provenance and SHA-256 checksums")
    emit.add_argument("--artifacts-dir", required=True)
    emit.add_argument("--output", required=True)
    emit.add_argument("--checksums", required=True)
    emit.add_argument("--source-commit", required=True)
    emit.add_argument("--source-date-epoch", required=True)
    emit.add_argument("--input", action="append", default=[])
    emit.add_argument("--sbom-ref", action="append", default=[])
    emit.set_defaults(func=emit_provenance)

    sbom = subparsers.add_parser("sbom", help="write a deterministic CycloneDX declaration SBOM")
    sbom.add_argument("--pyproject", default="pyproject.toml")
    sbom.add_argument("--output", required=True)
    sbom.add_argument("--source-commit", required=True)
    sbom.set_defaults(func=write_sbom)

    compare = subparsers.add_parser("compare", help="compare two release provenance documents")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.set_defaults(func=compare_provenance)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
