#!/usr/bin/env python3
"""Fail closed on repository artifact-placement violations.

The policy is incremental: CI inspects files changed by a PR/push, while the
pre-commit hook inspects staged files. Existing legacy blobs are therefore
migration debt, not an excuse for new repository growth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGULAR_GIT_MAX_BYTES = 10 * 1024 * 1024
FIXTURE_MAX_BYTES = 1 * 1024 * 1024

NEVER_GIT_SUFFIXES = {".apk", ".aab", ".ipa", ".whl", ".zip", ".7z", ".tar", ".tgz"}
LFS_REQUIRED_SUFFIXES = {
    ".pt", ".pth", ".ckpt", ".onnx", ".safetensors", ".h5", ".hdf5",
    ".npy", ".npz", ".parquet", ".arrow", ".bin",
}
FORBIDDEN_PATH_FRAGMENTS = (
    "backend/data/builds_vault/", "backend/data/galaxy_vault/",
    "backend/data/build_artifacts/", "/node_modules/", "/__pycache__/",
    "/.pytest_cache/", "/.mypy_cache/", "/.ruff_cache/",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
LFS_OID_RE = re.compile(rb"^oid sha256:([0-9a-f]{64})$", re.MULTILINE)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _decode_paths(raw: bytes) -> list[Path]:
    return [Path(part.decode("utf-8", errors="surrogateescape")) for part in raw.split(b"\0") if part]


def changed_paths(*, base: str | None, staged: bool, all_tracked: bool) -> list[Path]:
    if all_tracked:
        return _decode_paths(_git("ls-files", "-z").stdout)
    if staged:
        return _decode_paths(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").stdout)
    if base:
        if set(base) == {"0"}:
            probe = _git("rev-parse", "HEAD^", check=False)
            if probe.returncode != 0:
                return changed_paths(base=None, staged=False, all_tracked=True)
            base = probe.stdout.decode().strip()
        return _decode_paths(_git("diff", "--name-only", "--diff-filter=ACMR", "-z", f"{base}...HEAD").stdout)
    return _decode_paths(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").stdout)


def is_lfs_tracked(path: Path) -> bool:
    result = _git("check-attr", "filter", "--", path.as_posix(), check=False)
    return result.returncode == 0 and result.stdout.decode("utf-8", errors="replace").rstrip().endswith(": lfs")


def is_small_test_fixture(path: Path, size: int) -> bool:
    parts = set(path.parts)
    return size <= FIXTURE_MAX_BYTES and "fixtures" in parts and bool({"tests", "testing"} & parts)


def artifact_digest(path: Path) -> str:
    with path.open("rb") as handle:
        prefix = handle.read(512)
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            match = LFS_OID_RE.search(prefix)
            if not match:
                raise ValueError("malformed Git LFS pointer")
            return match.group(1).decode("ascii")
        digest = hashlib.sha256()
        digest.update(prefix)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def validate_sidecar(path: Path) -> list[str]:
    errors: list[str] = []
    sidecar = path.with_name(path.name + ".artifact.json")
    if not sidecar.is_file():
        return [f"{path}: Git LFS asset requires provenance sidecar {sidecar.name}"]
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid provenance sidecar {sidecar.name}: {exc}"]
    declared, source, license_name = payload.get("sha256"), payload.get("source"), payload.get("license")
    if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
        errors.append(f"{sidecar}: sha256 must be exactly 64 lowercase hex characters")
    if not isinstance(source, str) or not source.strip():
        errors.append(f"{sidecar}: source must be a non-empty provenance locator or generated:<command>")
    if not isinstance(license_name, str) or not license_name.strip():
        errors.append(f"{sidecar}: license must be explicit")
    if not errors:
        try:
            observed = artifact_digest(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: cannot calculate artifact digest: {exc}")
        else:
            if observed != declared:
                errors.append(f"{path}: provenance sha256 mismatch (sidecar={declared}, observed={observed})")
    return errors


def validate_path(relative_path: Path) -> list[str]:
    path = REPO_ROOT / relative_path
    if not path.is_file():
        return []
    rel, size, suffix = relative_path.as_posix(), path.stat().st_size, path.suffix.lower()
    padded, lfs = f"/{rel}", is_lfs_tracked(relative_path)
    errors: list[str] = []
    if any(fragment in padded for fragment in FORBIDDEN_PATH_FRAGMENTS):
        errors.append(f"{rel}: generated/cache path is forbidden in source Git")
    if suffix in NEVER_GIT_SUFFIXES:
        errors.append(f"{rel}: build/archive output belongs in CI/release artifacts, not source Git")
    if suffix in LFS_REQUIRED_SUFFIXES and not lfs and not is_small_test_fixture(relative_path, size):
        errors.append(f"{rel}: {suffix} assets must use Git LFS (small test fixtures <=1 MiB are exempt)")
    if size > REGULAR_GIT_MAX_BYTES and not lfs:
        errors.append(f"{rel}: {size} bytes exceeds the 10 MiB regular-Git limit; use LFS or external artifact storage")
    if lfs:
        errors.extend(validate_sidecar(path))
    return errors


def validate(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for path in paths:
        key = path.as_posix()
        if key not in seen:
            seen.add(key)
            errors.extend(validate_path(path))
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--base")
    group.add_argument("--staged", action="store_true")
    group.add_argument("--all", action="store_true", dest="all_tracked")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = changed_paths(base=args.base, staged=args.staged or (not args.base and not args.all_tracked), all_tracked=args.all_tracked)
    errors = validate(paths)
    if errors:
        print("artifact-policy: rejected repository artifacts:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("See docs/ARTIFACT_POLICY.md for placement and provenance rules.", file=sys.stderr)
        return 1
    print(f"artifact-policy: OK ({len(paths)} changed/tracked path(s) inspected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
