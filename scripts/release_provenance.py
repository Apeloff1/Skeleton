#!/usr/bin/env python3
"""Deterministic release metadata, checksums, SBOM, and rebuild verification.

The release workflow uses this module without third-party runtime dependencies so the
metadata path itself is small, auditable, and reproducible.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import sys
import tarfile
import tempfile
import tomllib
import types
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
_CYCLONEDX_SPEC = "1.6"
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
_OBSERVED_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._:-]*)=(.+)$")


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


def _normalized_member_mode(member: tarfile.TarInfo) -> int:
    """Return a deterministic mode without changing executable intent."""

    if member.isdir():
        return 0o755
    if member.isfile():
        return 0o755 if member.mode & 0o111 else 0o644
    if member.issym() or member.islnk():
        return 0o777
    return member.mode & 0o7777


def normalize_sdist(args: argparse.Namespace) -> int:
    """Rewrite a gzip-compressed source distribution with deterministic metadata."""

    source = Path(args.path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not source.name.endswith(".tar.gz"):
        raise ValueError("source distribution must use the .tar.gz format")
    epoch = _validate_epoch(args.source_date_epoch)

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source.name}.",
        suffix=".tmp",
        dir=source.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)

    try:
        with tarfile.open(source, mode="r:gz") as archive_in:
            members = sorted(archive_in.getmembers(), key=lambda item: item.name)
            with temporary.open("wb") as raw_output:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    compresslevel=9,
                    fileobj=raw_output,
                    mtime=epoch,
                ) as gzip_output:
                    with tarfile.open(
                        fileobj=gzip_output,
                        mode="w",
                        format=tarfile.PAX_FORMAT,
                    ) as archive_out:
                        for member in members:
                            member.mtime = epoch
                            member.uid = 0
                            member.gid = 0
                            member.uname = ""
                            member.gname = ""
                            member.mode = _normalized_member_mode(member)
                            member.pax_headers = {}
                            payload = archive_in.extractfile(member) if member.isfile() else None
                            archive_out.addfile(member, payload)
        os.replace(temporary, source)
        source.chmod(0o644)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


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


def _ensure_namespace(name: str, path: Path) -> None:
    """Register a package without executing its ``__init__`` (avoids pydantic)."""

    if name in sys.modules:
        return
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    module.__file__ = str(path / "__init__.py")
    module.__package__ = name
    sys.modules[name] = module


def _load_file_module(name: str, file_path: Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_release_evidence():
    """Import the evidence gate without loading ``skeleton.__init__``.

    Reproducible Release pytest has neither PYTHONPATH nor pydantic. A normal
    ``import skeleton.release.evidence`` executes the root package, which
    imports settings and fails. Load kernel.errors and evidence.py by path.
    """

    root = Path(__file__).resolve().parents[1]
    evidence_path = root / "skeleton" / "release" / "evidence.py"
    errors_path = root / "skeleton" / "kernel" / "errors.py"
    if not evidence_path.is_file() or not errors_path.is_file():
        raise ValueError(
            "release evidence commands require the skeleton.release.evidence package"
        )
    try:
        _ensure_namespace("skeleton", root / "skeleton")
        _ensure_namespace("skeleton.kernel", root / "skeleton" / "kernel")
        _ensure_namespace("skeleton.release", root / "skeleton" / "release")
        _load_file_module("skeleton.kernel.errors", errors_path)
        return _load_file_module("skeleton.release.evidence", evidence_path)
    except Exception as exc:
        raise ValueError(
            "release evidence commands require the skeleton.release.evidence package"
        ) from exc


def _load_json_records(paths: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in paths:
        payload = json.loads(Path(item).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records.extend(payload)
        elif isinstance(payload, dict):
            records.append(payload)
        else:
            raise ValueError(f"{item} must contain a JSON object or list of objects")
    return records


def _load_observed_artifacts(values: Iterable[str]) -> dict[str, bytes]:
    observed: dict[str, bytes] = {}
    for item in values:
        match = _OBSERVED_RE.fullmatch(item)
        if not match:
            raise ValueError("observed artifact must use artifact_id=path")
        artifact_id, raw_path = match.group(1), match.group(2)
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        observed[artifact_id] = path.read_bytes()
    return observed


def emit_release_evidence(args: argparse.Namespace) -> int:
    """Write a separate release-ready evidence document from v1 provenance."""

    release_evidence = _load_release_evidence()
    provenance = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
    if provenance.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("evidence adapter requires a SCHEMA_VERSION 1 provenance document")
    test_evidence = _load_json_records(args.test_evidence)
    eval_evidence = _load_json_records(args.eval_evidence)
    asset_provenance: list[dict[str, Any]] = []
    if args.asset_provenance:
        asset_payload = json.loads(Path(args.asset_provenance).read_text(encoding="utf-8"))
        if isinstance(asset_payload, dict) and "assets" in asset_payload:
            assets = asset_payload["assets"]
            if not isinstance(assets, list):
                raise ValueError("asset provenance assets must be a list")
            asset_provenance = assets
        elif isinstance(asset_payload, list):
            asset_provenance = asset_payload
        else:
            raise ValueError("asset provenance must be a list or an assets manifest object")

    try:
        evidence = release_evidence.from_v1_provenance(
            provenance,
            test_evidence=test_evidence,
            eval_evidence=eval_evidence,
            asset_provenance=asset_provenance,
        )
        serialized = release_evidence.serialize_evidence(evidence)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
        observed = _load_observed_artifacts(args.observed)
        result = release_evidence.evaluate_release_ready(
            evidence,
            expected_commit=args.source_commit,
            observed_artifacts=observed or None,
        )
    except release_evidence.ReleaseEvidenceError as exc:
        raise ValueError(str(exc)) from exc
    print(json.dumps(result.to_payload(), indent=2, sort_keys=True))
    if args.gate and not result.release_ready:
        print("release evidence is not release-ready", file=sys.stderr)
        for reason in result.reasons:
            print(reason, file=sys.stderr)
        return 1
    return 0


def gate_release_evidence(args: argparse.Namespace) -> int:
    """Fail closed unless the evidence document is release-ready."""

    release_evidence = _load_release_evidence()
    observed = _load_observed_artifacts(args.observed)
    try:
        result = release_evidence.evaluate_release_ready(
            Path(args.evidence).read_text(encoding="utf-8"),
            expected_commit=args.source_commit,
            observed_artifacts=observed or None,
        )
    except release_evidence.ReleaseEvidenceError as exc:
        raise ValueError(str(exc)) from exc
    print(json.dumps(result.to_payload(), indent=2, sort_keys=True))
    if not result.release_ready:
        print("release evidence is not release-ready", file=sys.stderr)
        for reason in result.reasons:
            print(reason, file=sys.stderr)
        return 1
    print("release-ready")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser(
        "normalize-sdist",
        help="rewrite a .tar.gz source distribution with deterministic archive metadata",
    )
    normalize.add_argument("--path", required=True)
    normalize.add_argument("--source-date-epoch", required=True)
    normalize.set_defaults(func=normalize_sdist)

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
    evidence = subparsers.add_parser(
        "evidence",
        help="write a separate release-ready evidence document from SCHEMA_VERSION 1 provenance",
    )
    evidence.add_argument("--provenance", required=True)
    evidence.add_argument("--output", required=True)
    evidence.add_argument("--source-commit", required=True)
    evidence.add_argument("--test-evidence", action="append", default=[])
    evidence.add_argument("--eval-evidence", action="append", default=[])
    evidence.add_argument("--asset-provenance", default=None)
    evidence.add_argument(
        "--observed",
        action="append",
        default=[],
        help="bind exact artifact bytes as artifact_id=path",
    )
    evidence.add_argument(
        "--gate",
        action="store_true",
        help="fail closed unless the adapted evidence is release-ready",
    )
    evidence.set_defaults(func=emit_release_evidence)

    gate = subparsers.add_parser(
        "gate",
        help="classify a release evidence document; missing evidence fails closed",
    )
    gate.add_argument("--evidence", required=True)
    gate.add_argument("--source-commit", required=True)
    gate.add_argument(
        "--observed",
        action="append",
        default=[],
        help="bind exact artifact bytes as artifact_id=path",
    )
    gate.set_defaults(func=gate_release_evidence)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError, tarfile.TarError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
