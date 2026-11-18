#!/usr/bin/env python3
"""Opt-in, offline Jeeves model-artifact restore into a NEW private directory.

Never rewrites the active /app/local-ai mount, environment, Docker Compose,
Mongo/SQLite/Chroma state, or a source backup. A successful copy is not
application recovery, protected chat authority, physical GGUF inference or
release approval. Partial failed copies are preserved for investigation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from scripts.local_ai_model_backup import (
    MAX_ENTRIES, MANIFEST, ModelBackupError, _copy_one, _digest_receipt,
    _private_dir, _read_json, _relative, _safe_file, inventory, verify_backup,
)

SCHEMA = "skeleton.local-ai.model-restore.v1"
RECEIPT = "model-restore-receipt.json"


def _new_destination(source: Path, destination: Path) -> Path:
    """Admit a genuine parent and a never-before-existing fresh restore root."""
    path = Path(os.path.abspath(destination))
    if path.exists() or path.is_symlink():
        raise ModelBackupError("restore destination must be new and cannot overwrite data")
    parent = _private_dir(path.parent)
    if path == source or source.is_relative_to(path) or path.is_relative_to(source):
        raise ModelBackupError("restore target must not overlap the model backup")
    if path.name in ("", ".", "..") or path.parent != parent:
        raise ModelBackupError("restore destination is not a canonical private child")
    return path


def _write_restore_receipt(root: Path, payload: dict[str, Any]) -> str:
    sha256 = _digest_receipt(payload)
    content = json.dumps({**payload, "receipt_sha256": sha256},
                         sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    fd = os.open(root / RECEIPT,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        written = 0
        while written < len(content):
            part = os.write(fd, content[written:])
            if part <= 0:
                raise ModelBackupError("model restore receipt could not be written")
            written += part
        os.fsync(fd)
    finally:
        os.close(fd)
    return sha256


def _complete_file_inventory(root: Path, files: list[dict[str, Any]]) -> None:
    expected = {item["path"] for item in files} | {RECEIPT}
    expected_dirs: set[str] = set()
    for name in expected:
        for parent in Path(name).parents:
            if parent == Path("."):
                break
            expected_dirs.add(parent.as_posix())
    seen: set[str] = set()
    for directory, dirs, filenames in os.walk(root, followlinks=False):
        for name in dirs:
            candidate = Path(directory) / name
            if (candidate.is_symlink() or not candidate.is_dir()
                    or candidate.relative_to(root).as_posix() not in expected_dirs):
                raise ModelBackupError("restore contains an undeclared directory")
        for name in filenames:
            file = Path(directory) / name
            relative = file.relative_to(root).as_posix()
            info = file.lstat()
            if (relative not in expected or not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1):
                raise ModelBackupError("restore includes an undeclared or linked artifact")
            seen.add(relative)
            if len(seen) > MAX_ENTRIES + 1:
                raise ModelBackupError("restore exceeds pinned file inventory")
    if seen != expected:
        raise ModelBackupError("restore is missing a pinned artifact")


def verify_restore(destination: Path) -> dict[str, Any]:
    """Verify retained artifact pins; do not assert the runtime ever executed."""
    root = _private_dir(destination)
    record, _ = _read_json(_safe_file(root, Path(RECEIPT)), 256 * 1024)
    sha = record.pop("receipt_sha256", None)
    if (type(sha) is not str or sha != _digest_receipt(record)
            or set(record) != {
                "schema", "status", "model_id", "source_backup_receipt_sha256",
                "files", "file_count", "total_bytes", "application_state_restored",
                "inference_executed", "device_qualified", "chat_guard_qualified",
            } or record.get("schema") != SCHEMA
            or record.get("status") != "model_artifacts_restored_to_new_private_root"
            or record.get("model_id") != "jeeves"
            or record.get("application_state_restored") is not False
            or record.get("inference_executed") is not False
            or record.get("device_qualified") is not False
            or record.get("chat_guard_qualified") is not False):
        raise ModelBackupError("model restore receipt authority is invalid")
    files = inventory(root)
    if (files != record["files"] or len(files) != record["file_count"]
            or sum(row["bytes"] for row in files) != record["total_bytes"]):
        raise ModelBackupError("restored pinned bytes do not match the receipt")
    _complete_file_inventory(root, files)
    manifest, _ = _read_json(_safe_file(root, Path(MANIFEST)), 1024 * 1024)
    exe = _safe_file(root, _relative(manifest.get("executable_path")))
    if not (exe.stat().st_mode & stat.S_IXUSR):
        raise ModelBackupError("restored runtime executable lacks owner execution permission")
    return {
        "schema": SCHEMA, "verified": True, "model_id": "jeeves",
        "file_count": len(files), "total_bytes": record["total_bytes"],
        "receipt_sha256": sha,
        "source_backup_receipt_sha256": record["source_backup_receipt_sha256"],
        "application_state_restored": False,
        "inference_executed": False, "device_qualified": False,
        "chat_guard_qualified": False,
    }


def restore_model_backup(source: Path, destination: Path) -> dict[str, Any]:
    """Restore immutable pinned model bytes without touching the source or live app."""
    backup_root = _private_dir(source)
    before = verify_backup(backup_root)
    files = inventory(backup_root)
    target = _new_destination(backup_root, destination)
    os.mkdir(target, mode=0o700)
    try:
        for descriptor in files:
            relative = Path(descriptor["path"])
            source_file = _safe_file(backup_root, relative)
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _copy_one(source_file, dest, descriptor)
        # Do not accidentally turn runtime libraries/models into executables.
        manifest, _ = _read_json(_safe_file(target, Path(MANIFEST)), 1024 * 1024)
        binary = _safe_file(target, _relative(manifest.get("executable_path")))
        os.chmod(binary, 0o700, follow_symlinks=False)
        if inventory(target) != files:
            raise ModelBackupError("copied model bytes did not match pinned inventory")
        payload = {
            "schema": SCHEMA,
            "status": "model_artifacts_restored_to_new_private_root",
            "model_id": "jeeves",
            "source_backup_receipt_sha256": before["receipt_sha256"],
            "files": files, "file_count": len(files),
            "total_bytes": sum(row["bytes"] for row in files),
            "application_state_restored": False,
            "inference_executed": False, "device_qualified": False,
            "chat_guard_qualified": False,
        }
        _write_restore_receipt(target, payload)
        return verify_restore(target)
    except (OSError, ValueError, ModelBackupError, TypeError) as exc:
        # Never remove or rewrite a partially restored directory; an operator
        # can inspect it and choose a new destination for a clean retry.
        raise ModelBackupError("model restore incomplete; partial directory preserved") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    restore = action.add_parser("restore")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    verify = action.add_parser("verify")
    verify.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = (restore_model_backup(args.source, args.destination)
                   if args.action == "restore" else verify_restore(args.directory))
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ModelBackupError, ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"ok": False, "error": "local model restore custody rejected"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
