"""Bounded, deterministic, self-contained Python zipapp for Cinder Ridge.

A .pyz is runnable with an installed Python 3 interpreter, not a native
Windows executable or signed consumer installer. The archive includes only
the canonical original game package and its JSON source, not vendored code.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import stat
import zipfile

from .consumer_store import SlotStore, StoreError, _safe_directory

MAX_SOURCE_FILES = 128
MAX_SOURCE_FILE_BYTES = 192_000
MAX_UNCOMPRESSED_BYTES = 4_000_000
MAX_ARCHIVE_BYTES = 2_000_000
ENTRY = b"from ridge_rescue.consumer_cli import main\nraise SystemExit(main())\n"


class BundleError(ValueError):
    """Invalid original game archive or unsafe package publication."""


def _entry(name: str, data: bytes, archive: zipfile.ZipFile) -> None:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    info.create_system = 3
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_bytes() -> bytes:
    source = Path(__file__).parent
    if not source.is_dir() or source.is_symlink():
        raise BundleError("original source directory unavailable outside checkout")
    entries = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise BundleError("linked source file or directory refused")
        if path.is_dir():
            continue
        if path.suffix not in {".py", ".json"}:
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_FILE_BYTES:
            raise BundleError("unsafe or oversized source file")
        relative = path.relative_to(source).as_posix()
        if ".." in Path(relative).parts or relative.startswith("/"):
            raise BundleError("unsafe archive path")
        entries.append((relative, path.read_bytes()))
    if not 4 <= len(entries) <= MAX_SOURCE_FILES:
        raise BundleError("original game source inventory outside bounds")
    required = {"__init__.py", "consumer_cli.py", "consumer_store.py", "cinder_ridge_campaign.json"}
    if not required.issubset({name for name, _ in entries}):
        raise BundleError("portable game is missing critical source")
    if sum(len(data) for _, data in entries) + len(ENTRY) > MAX_UNCOMPRESSED_BYTES:
        raise BundleError("portable game source exceeds byte budget")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", allowZip64=False) as archive:
        _entry("__main__.py", ENTRY, archive)
        for name, data in entries:
            _entry("ridge_rescue/" + name, data, archive)
    result = buffer.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES:
        raise BundleError("portable game archive exceeds byte budget")
    verify_bytes(result)
    return result


def verify_bytes(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_ARCHIVE_BYTES:
        raise BundleError("invalid archive byte budget")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > MAX_SOURCE_FILES + 1:
                raise BundleError("duplicate or excessive archive entries")
            if "__main__.py" not in names or archive.read("__main__.py") != ENTRY:
                raise BundleError("untrusted game entrypoint")
            if not {"ridge_rescue/__init__.py", "ridge_rescue/consumer_cli.py",
                    "ridge_rescue/consumer_store.py", "ridge_rescue/cinder_ridge_campaign.json"}.issubset(names):
                raise BundleError("critical original game source missing")
            total = 0
            for item in archive.infolist():
                if item.filename != "__main__.py" and (
                    not item.filename.startswith("ridge_rescue/") or
                    not item.filename.endswith((".py", ".json"))
                ):
                    raise BundleError("unexpected archive member")
                if ".." in item.filename.split("/") or item.is_dir():
                    raise BundleError("unsafe archive member")
                if item.file_size > MAX_SOURCE_FILE_BYTES:
                    raise BundleError("oversized archive member")
                total += item.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise BundleError("archive decompression budget exceeded")
            if archive.testzip() is not None:
                raise BundleError("archive CRC mismatch")
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise BundleError("invalid portable game archive") from exc
    return {"schema": "ridge.rescue.consumer.zipapp.v1", "files": len(names),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "python_required": True, "windows_device_certified": False,
            "release_certified": False}


def build_bundle(store: SlotStore) -> dict:
    archive = build_bytes()
    checked = verify_bytes(archive)
    directory = _safe_directory(store.root / "exports")
    destination = directory / ("cinder-ridge-" + checked["sha256"][:16] + ".pyz")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(destination, flags, 0o600)
        with os.fdopen(fd, "wb") as output:
            fd = None
            output.write(archive)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise BundleError("portable game create-only publication refused") from exc
    finally:
        if fd is not None:
            os.close(fd)
    return {**checked, "path": str(destination)}
