"""Inspect or reopen a portable GameForge source ZIP without executing it.

Use: python -m scripts.verify_gameforge_source_zip game.zip --expected-sha256 FULL_DIGEST
Add --output NEW_DIRECTORY to write verified sources, never overwrite a project.
The expected digest must come from the original Forge run through a trusted
channel. Neither ZIP metadata nor the truncated filename authenticates it.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

from skeleton.forge.source_manifest import source_manifest

MAX_ZIP_BYTES = 9 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_FILES = 256
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SEGMENT = re.compile(r"[a-zA-Z0-9_.-]{1,120}")
_DEVICES = {"con", "nul", "aux", "prn"} | {
    f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in range(1, 10)
}


class PortableSourceError(ValueError):
    """A ZIP or destination fails the portable-source contract."""


def _safe_path(name: str) -> bool:
    return (type(name) is str and 0 < len(name) <= 240
            and all(part and not part.startswith(".") and not part.endswith(".")
                    and _SEGMENT.fullmatch(part) is not None
                    and part.split(".")[0].lower() not in _DEVICES
                    for part in name.split("/")))


def _read_zip(path: Path) -> bytes:
    # The bounded in-memory snapshot prevents subsequent path replacement
    # from changing the bytes inspected by the ZIP reader.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if path.is_symlink():
        raise PortableSourceError("archive must be a regular file")
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 22 <= info.st_size <= MAX_ZIP_BYTES:
            raise PortableSourceError("archive exceeds portable ZIP budget or is not a file")
        raw = handle.read(MAX_ZIP_BYTES + 1)
    if len(raw) != info.st_size or len(raw) > MAX_ZIP_BYTES:
        raise PortableSourceError("archive changed size during bounded read")
    return raw


def inspect_archive(raw: bytes, expected_sha256: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Return verified source strings and a detached inspection receipt.

    The ZIP is restricted to the stored-text format emitted by GameForge.
    A correct full source manifest digest proves source identity only.
    """
    if type(expected_sha256) is not str or _DIGEST.fullmatch(expected_sha256) is None:
        raise PortableSourceError("a full lowercase SHA-256 source manifest digest is required")
    if type(raw) is not bytes or not 22 <= len(raw) <= MAX_ZIP_BYTES:
        raise PortableSourceError("archive exceeds portable ZIP budget")
    files: dict[str, str] = {}
    leaves: set[str] = set()
    directories: dict[str, str] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            members = archive.infolist()
            if archive.comment or not 0 < len(members) <= MAX_FILES:
                raise PortableSourceError("invalid ZIP member inventory")
            for member in members:
                name = member.filename
                kind = stat.S_IFMT(member.external_attr >> 16)
                if (not _safe_path(name) or member.orig_filename != name
                        or member.is_dir() or kind not in (0, stat.S_IFREG)
                        or member.flag_bits not in (0, 0x800)
                        or member.compress_type != zipfile.ZIP_STORED
                        or member.compress_size != member.file_size
                        or member.extra or member.comment
                        or not 0 <= member.file_size <= MAX_SOURCE_BYTES - total):
                    raise PortableSourceError("unsafe or over-budget ZIP member")
                folded = name.lower()
                if folded in leaves or folded in directories:
                    raise PortableSourceError("duplicate or file-directory ZIP member")
                parts = name.split("/")
                for depth in range(1, len(parts)):
                    prefix = "/".join(parts[:depth])
                    alias = prefix.lower()
                    if alias in leaves or (alias in directories and directories[alias] != prefix):
                        raise PortableSourceError("ambiguous ZIP directory")
                    directories[alias] = prefix
                leaves.add(folded)
                with archive.open(member, "r") as stream:
                    data = stream.read(member.file_size + 1)
                if len(data) != member.file_size:
                    raise PortableSourceError("ZIP member size mismatch")
                total += len(data)
                files[name] = data.decode("utf-8", errors="strict")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError, EOFError) as exc:
        raise PortableSourceError("invalid portable ZIP data") from exc
    try:
        manifest = source_manifest(files)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PortableSourceError("invalid Godot project source inventory") from exc
    digest = str(manifest["sha256"])
    if not hmac.compare_digest(digest, expected_sha256):
        raise PortableSourceError("source manifest SHA-256 mismatch")
    return files, {
        "schema": "skeleton.gameforge.portable_source_inspection.v1",
        "source_manifest": manifest,
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": total,
        "archive_bytes": len(raw),
        "source_verified": True,
        "native_execution_qualified": False,
    }


def reopen_archive(path: Path, expected_sha256: str, output: Path | None = None) -> dict[str, Any]:
    files, receipt = inspect_archive(_read_zip(path), expected_sha256)
    if output is not None:
        # Deliberately require an absent named directory below an existing,
        # trusted local parent. Never merge with or overwrite existing sources.
        # A write failure may leave partial new files; do not recursively
        # delete a destination that might have been modified by another process.
        if output.name in ("", ".", "..") or not output.parent.is_dir():
            raise PortableSourceError("output must be a named new directory under an existing parent")
        if output.parent.is_symlink() or output.is_symlink():
            raise PortableSourceError("symlink destination is not allowed")
        try:
            output.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise PortableSourceError("output already exists; choose a new directory") from exc
        for name, body in sorted(files.items()):
            target = output.joinpath(*name.split("/"))
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(body.encode("utf-8", errors="strict"))
        receipt["reopened"] = True
    else:
        receipt["reopened"] = False
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, help="New directory under a trusted local parent")
    args = parser.parse_args(argv)
    try:
        result = reopen_archive(args.archive, args.expected_sha256, args.output)
    except PortableSourceError as exc:
        print(f"Portable source refused: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("Portable source I/O failed; an attempted new output may be incomplete", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
