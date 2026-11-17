#!/usr/bin/env python3
"""Copy and verify a pinned Jeeves model *without* changing the live Docker tree.

Backup is model-artifact custody only. It cannot establish Mongo/SQLite/Chroma
consistency, writer quiescence, physical GPU readiness, or a guarded chat turn.
Never restores, overwrites, downloads, removes, or runs a model executable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any

SCHEMA = "skeleton.local-ai.model-backup.v1"
RECEIPT = "model-backup-receipt.json"
MANIFEST = "jeeves.json"
ROOT = PurePosixPath("/app/local-ai")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_LIBRARY = re.compile(r"lib[A-Za-z0-9_+.-]{1,120}\.so(?:\.[A-Za-z0-9_+.-]+)?\Z")
MAX_ENTRIES = 131
MAX_TOTAL_BYTES = 1024 ** 4
MAX_MANIFEST = 1024 * 1024
MAX_RECEIPT = 256 * 1024
CHUNK = 1024 * 1024


class ModelBackupError(RuntimeError):
    """A backup source, target or identity fails closed."""


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ModelBackupError("duplicate JSON keys in model custody metadata")
        out[key] = value
    return out


def _reject_constant(_: str) -> None:
    raise ModelBackupError("non-finite model custody metadata")


def _read_json(path: Path, limit: int) -> tuple[dict[str, Any], bytes]:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if not data or len(data) > limit:
        raise ModelBackupError("model custody metadata violates byte limit")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ModelBackupError("model custody metadata is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ModelBackupError("model custody metadata must be a JSON object")
    return value, data


def _private_dir(path: Path) -> Path:
    candidate = Path(os.path.abspath(path))
    if candidate.resolve(strict=True) != candidate or not stat.S_ISDIR(candidate.lstat().st_mode):
        raise ModelBackupError("backup root must be a genuine directory, not a symlink")
    return candidate


def _relative(path: str) -> Path:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path or len(path) > 512:
        raise ModelBackupError("invalid pinned model path")
    p = PurePosixPath(path)
    if (not p.is_absolute() or p == ROOT or not p.is_relative_to(ROOT)
            or any(part in ("", ".", "..") for part in path[1:].split("/"))
            or len(p.parts) > 18):
        raise ModelBackupError("pinned model path escapes local model root")
    return Path(*p.relative_to(ROOT).parts)


def _safe_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or len(relative.parts) > 16:
        raise ModelBackupError("invalid model artifact relative path")
    cursor = root
    for part in relative.parts:
        if part in ("", ".", ".."):
            raise ModelBackupError("model path contains traversal")
        cursor /= part
        metadata = cursor.lstat()
        if stat.S_ISLNK(metadata.st_mode) or (
            not stat.S_ISREG(metadata.st_mode) if cursor == root / relative
            else not stat.S_ISDIR(metadata.st_mode)
        ):
            raise ModelBackupError("model path has a non-regular or linked component")
    info = cursor.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size <= 0:
        raise ModelBackupError("model artifact must be a private regular file")
    return cursor


def _digest(source: Path) -> tuple[str, int]:
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= MAX_TOTAL_BYTES:
            raise ModelBackupError("artifact not an acceptable private regular file")
        value = hashlib.sha256()
        while True:
            data = os.read(fd, CHUNK)
            if not data:
                break
            value.update(data)
        after = os.fstat(fd)
        current = source.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
            raise ModelBackupError("model artifact changed while checking custody")
        return value.hexdigest(), before.st_size
    finally:
        os.close(fd)


def inventory(source: Path) -> list[dict[str, Any]]:
    root = _private_dir(source)
    manifest_file = _safe_file(root, Path(MANIFEST))
    payload, raw = _read_json(manifest_file, MAX_MANIFEST)
    if payload.get("schema_version") != "skeleton.local_model.deployment.v1":
        raise ModelBackupError("unsupported pinned deployment manifest")
    if payload.get("runtime_kind") != "llama.cpp-cli" or payload.get("model_id") != "jeeves":
        raise ModelBackupError("backup must have one canonical local Jeeves model")
    entries: dict[Path, str] = {Path(MANIFEST): hashlib.sha256(raw).hexdigest()}
    for prefix in ("model", "executable"):
        target = _relative(payload.get(prefix + "_path"))
        digest = payload.get(prefix + "_sha256")
        if not isinstance(digest, str) or not _HEX.fullmatch(digest) or target in entries:
            raise ModelBackupError("model or executable pin is invalid or duplicated")
        entries[target] = digest

    libraries = payload.get("runtime_libraries", {})
    if not isinstance(libraries, dict) or len(libraries) > 128:
        raise ModelBackupError("runtime library pin list is invalid")
    executable = _relative(payload["executable_path"])
    library_root = root / executable.parent
    observed = set()
    for path in library_root.iterdir():
        if path.name.startswith("lib") and ".so" in path.name:
            observed.add(path.name)
    if observed != set(libraries):
        raise ModelBackupError("runtime adjacent library inventory is not fully pinned")
    for name, digest in libraries.items():
        if not isinstance(name, str) or not _LIB.fullmatch(name):
            raise ModelBackupError("unsafe runtime library name")
        relative = executable.parent / name
        if relative in entries or not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise ModelBackupError("invalid or duplicate runtime library digest")
        entries[relative] = digest

    if len(entries) > MAX_ENTRIES:
        raise ModelBackupError("model backup exceeds artifact count")
    total = 0
    files: list[dict[str, Any]] = []
    for relative, expected in sorted(entries.items(), key=lambda item: item[0].as_posix()):
        path = _safe_file(root, relative)
        observed, size = _digest(path)
        if observed != expected:
            raise ModelBackupError("model artifact differs from manifest digest")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ModelBackupError("model backup exceeds aggregate byte budget")
        files.append({"path": relative.as_posix(), "sha256": observed, "bytes": size})
    return files


def _digest_receipt(receipt: dict[str, Any]) -> str:
    value = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _copy_one(source: Path, target: Path, expected: dict[str, Any]) -> None:
    before_hash, size = _digest(source)
    if before_hash != expected["sha256"] or size != expected["bytes"]:
        raise ModelBackupError("model source identity changed before snapshot")
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        original = os.fstat(source_fd)
        if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
            raise ModelBackupError("model source was replaced before copy")
        dest_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            copied = 0
            hash_value = hashlib.sha256()
            while True:
                chunk = os.read(source_fd, CHUNK)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > size:
                    raise ModelBackupError("model source grew during backup")
                hash_value.update(chunk)
                offset = 0
                while offset < len(chunk):
                    offset += os.write(dest_fd, chunk[offset:])
            os.fsync(dest_fd)
        finally:
            os.close(dest_fd)
        after = os.fstat(source_fd)
        current = source.lstat()
        if (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
            raise ModelBackupError("model source changed during backup")
        if copied != size or hash_value.hexdigest() != expected["sha256"]:
            raise ModelBackupError("model copy digest or size differs")
        readback, readback_size = _digest(target)
        if readback != expected["sha256"] or readback_size != size:
            raise ModelBackupError("backup readback digest mismatch")
        os.chmod(target, 0o400)
    finally:
        os.close(source_fd)


def _write_receipt(target: Path, fields: dict[str, Any]) -> None:
    sealed = {**fields, "receipt_sha256": _digest_receipt(fields)}
    data = json.dumps(sealed, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    if len(data) > MAX_RECEIPT:
        raise ModelBackupError("backup receipt exceeds byte budget")
    fd = os.open(target / RECEIPT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        if os.write(fd, data) != len(data):
            raise ModelBackupError("backup receipt write incomplete")
        os.fsync(fd)
    finally:
        os.close(fd)


def backup_model(source: Path, destination: Path) -> dict[str, Any]:
    root = _private_dir(source)
    files = inventory(root)  # All source hashes checked BEFORE creating destination.
    parent = _private_dir(destination.parent)
    target = parent / destination.name
    if target.exists() or target.is_symlink() or destination.name in ("", ".", ".."):
        raise ModelBackupError("backup destination must be new; existing data cannot be overwritten")
    if target == root or root.is_relative_to(target) or target.is_relative_to(root):
        raise ModelBackupError("model backup must be outside the live model directory")
    os.mkdir(target, mode=0o700)
    try:
        total = 0
        for item in files:
            relative = Path(item["path"])
            artifact = _safe_file(root, relative)
            folder = target / relative.parent
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            _copy_one(artifact, target / relative, item)
            total += item["bytes"]
        receipt = {
            "schema": SCHEMA, "status": "model_artifacts_copied_not_application_recovered",
            "model_id": "jeeves", "files": files, "total_bytes": total,
            "archive_kind": "offline_model_only", "application_state_included": False,
            "inference_executed": False, "device_qualified": False,
        }
        _write_receipt(target, receipt)  # Last: no receipt for partial copy.
        verify_backup(target)
        return {**receipt, "receipt_sha256": _digest_receipt(receipt)}
    except (ModelBackupError, OSError, ValueError, TypeError) as exc:
        # Never delete or overwrite a partial destination: an operator must
        # investigate it; absence of the receipt means it is not qualified.
        raise ModelBackupError("model artifact backup incomplete; partial directory preserved") from exc


def verify_backup(destination: Path) -> dict[str, Any]:
    target = _private_dir(destination)
    metadata = _safe_file(target, Path(RECEIPT))
    receipt, _ = _read_json(metadata, MAX_RECEIPT)
    digest = receipt.pop("receipt_sha256", None)
    if not isinstance(digest, str) or digest != _digest_receipt(receipt):
        raise ModelBackupError("backup receipt identity mismatch")
    if (set(receipt) != {
            "schema", "status", "model_id", "files", "total_bytes",
            "archive_kind", "application_state_included",
            "inference_executed", "device_qualified",
        } or receipt.get("schema") != SCHEMA
            or receipt.get("status") != "model_artifacts_copied_not_application_recovered"
            or receipt.get("model_id") != "jeeves"
            or receipt.get("archive_kind") != "offline_model_only"
            or receipt.get("application_state_included") is not False
            or receipt.get("inference_executed") is not False
            or receipt.get("device_qualified") is not False):
        raise ModelBackupError("unsupported backup receipt authority")
    files = receipt.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_ENTRIES:
        raise ModelBackupError("invalid backup file list")
    expected = {RECEIPT}
    total = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
            raise ModelBackupError("invalid backup file descriptor")
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            raise ModelBackupError("backup artifact path must be a non-empty string")
        relative = Path(entry["path"])
        if (relative.is_absolute() or ".." in relative.parts
                or entry["path"] != relative.as_posix()
                or relative.as_posix() in expected
                or not isinstance(entry["sha256"], str)
                or not _HEX.fullmatch(entry["sha256"])
                or type(entry["bytes"]) is not int or entry["bytes"] < 1):
            raise ModelBackupError("backup file descriptor violates custody")
        expected.add(relative.as_posix())
        path = _safe_file(target, relative)
        observed, size = _digest(path)
        if observed != entry["sha256"] or size != entry["bytes"]:
            raise ModelBackupError("backup artifact byte identity mismatch")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ModelBackupError("backup bytes exceed bound")
    if total != receipt.get("total_bytes"):
        raise ModelBackupError("backup total bytes differ")
    observed = set()
    for directory, dirs, filenames in os.walk(target, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ModelBackupError("backup directory symlink refused")
        for name in filenames:
            observed.add((Path(directory) / name).relative_to(target).as_posix())
            if len(observed) > MAX_ENTRIES + 1:
                raise ModelBackupError("backup contains undeclared files")
    if observed != expected:
        raise ModelBackupError("backup has undeclared or missing artifacts")
    return {
        "schema": SCHEMA, "verified": True, "model_id": "jeeves",
        "file_count": len(files), "total_bytes": total,
        "receipt_sha256": digest, "application_state_included": False,
        "inference_executed": False, "device_qualified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    plan = actions.add_parser("inventory")
    plan.add_argument("--model-directory", type=Path, required=True)
    backup = actions.add_parser("backup")
    backup.add_argument("--model-directory", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "inventory":
            files = inventory(args.model_directory)
            receipt: dict[str, Any] = {
                "schema": SCHEMA, "file_count": len(files),
                "total_bytes": sum(item["bytes"] for item in files),
                "artifact_hashes_verified": True, "copied": False,
            }
        elif args.action == "backup":
            receipt = backup_model(args.model_directory, args.destination)
        else:
            receipt = verify_backup(args.directory)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ModelBackupError, ValueError, OSError, TypeError, KeyError):
        # No underlying file paths or model contents are printed to CI logs.
        print(json.dumps({"ok": False, "error": "local AI model backup custody rejected"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
