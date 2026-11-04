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

from .consumer_store import SlotStore, _safe_directory

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
    # ZIP readers tolerate executable prefixes, comments and trailing bytes.
    # A consumer archive must be exactly one canonical ZIP payload, never a
    # polyglot container whose unverified bytes differ from executed content.
    if not data.startswith(b"PK\\x03\\x04") or not data.endswith(b"PK\\x05\\x06" + b"\\x00" * 18):
        raise BundleError("noncanonical ZIP envelope")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.comment:
                raise BundleError("ZIP comments refused")
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > MAX_SOURCE_FILES + 1:
                raise BundleError("duplicate or excessive archive entries")
            # Windows filesystems may alias names by case or reserved device
            # components. Refuse ambiguous archives before consumer delivery.
            folded = set()
            reserved = {"CON", "PRN", "AUX", "NUL"}
            reserved.update(f"COM{i}" for i in range(1, 10))
            reserved.update(f"LPT{i}" for i in range(1, 10))
            for name in names:
                for part in name.split("/"):
                    if (not part.isascii() or part.endswith((".", " ")) or
                        any(ch in part for ch in ":<>|?*") or
                        part.split(".")[0].upper() in reserved):
                        raise BundleError("unsafe Windows archive member name")
                alias = name.casefold()
                if alias in folded:
                    raise BundleError("case-colliding archive members")
                folded.add(alias)
            if "__main__.py" not in names:
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
                # A valid CRC does not authorize noncanonical or executable
                # archive entries. Only deflated, regular source files qualify.
                parts = item.filename.split("/")
                if (item.flag_bits & 1 or
                    item.compress_type != zipfile.ZIP_DEFLATED or
                    any(part in {"", ".", ".."} for part in parts) or
                    item.filename.startswith("/") or chr(92) in item.filename):
                    raise BundleError("unsafe archive encoding or member path")
                mode = item.external_attr >> 16
                if item.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise BundleError("non-regular archive member")
                if item.filename == "__main__.py" and item.file_size != len(ENTRY):
                    raise BundleError("untrusted game entrypoint length")
                if item.file_size > MAX_SOURCE_FILE_BYTES:
                    raise BundleError("oversized archive member")
                total += item.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise BundleError("archive decompression budget exceeded")
            if archive.read("__main__.py") != ENTRY:
                raise BundleError("untrusted game entrypoint")
            if archive.testzip() is not None:
                raise BundleError("archive CRC mismatch")
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise BundleError("invalid portable game archive") from exc
    return {"schema": "ridge.rescue.consumer.zipapp.v1", "files": len(names),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "python_required": True, "windows_device_certified": False,
            "release_certified": False}



def _windows_launcher(filename: str) -> bytes:
    if not filename.startswith("cinder-ridge-") or not filename.endswith(".pyz"):
        raise BundleError("invalid portable launcher filename")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-." for ch in filename):
        raise BundleError("unsafe portable launcher filename")
    version = 'import sys;sys.exit(0 if sys.version_info >= (3, 11) else 1)'
    script = (
        "@echo off\r\n"
        "setlocal\r\n"
        "cd /d \"%~dp0\" || exit /b 2\r\n"
        "set \"PY=\"\r\n"
        "where py >nul 2>nul\r\n"
        "if not errorlevel 1 (\r\n"
        f"  py -3 -c \"{version}\" >nul 2>nul\r\n"
        "  if not errorlevel 1 set \"PY=py -3\"\r\n"
        ")\r\n"
        "if not defined PY (\r\n"
        "  where python >nul 2>nul\r\n"
        "  if not errorlevel 1 (\r\n"
        f"    python -c \"{version}\" >nul 2>nul\r\n"
        "    if not errorlevel 1 set \"PY=python\"\r\n"
        "  )\r\n"
        ")\r\n"
        "if not defined PY (\r\n"
        "  echo Python 3.11 or newer is required.\r\n"
        "  pause\r\n"
        "  exit /b 2\r\n"
        ")\r\n"
        f"%PY% -I \"%~dp0{filename}\" play --ascii\r\n"
        "set \"EXIT_CODE=%ERRORLEVEL%\"\r\n"
        "if not \"%EXIT_CODE%\"==\"0\" pause\r\n"
        "exit /b %EXIT_CODE%\r\n"
    )
    return script.encode("ascii")


def _publish(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = None
    owned_identity = None
    try:
        fd = os.open(path, flags, 0o600)
        opened = os.fstat(fd)
        owned_identity = (opened.st_dev, opened.st_ino)
        with os.fdopen(fd, "wb") as output:
            fd = None
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        # A failed write must not strand a partial archive or launcher.
        # Never unlink a replacement placed by another process.
        if owned_identity is not None:
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == owned_identity:
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # Preserve the original failure; a surviving file is still
                # create-only and will not be silently overwritten.
                pass
        raise BundleError("portable game create-only publication refused") from exc
    finally:
        if fd is not None:
            os.close(fd)


def build_bundle(store: SlotStore) -> dict:
    archive = build_bytes()
    checked = verify_bytes(archive)
    directory = _safe_directory(store.root / "exports")
    destination = directory / ("cinder-ridge-" + checked["sha256"][:16] + ".pyz")
    launcher = destination.with_suffix(".cmd")
    _publish(destination, archive)
    published = destination.lstat()
    try:
        _publish(launcher, _windows_launcher(destination.name))
    except BundleError:
        # Do not leave a seemingly usable orphaned zipapp when the paired
        # consumer launcher cannot be published. Refuse to remove a file
        # that another process replaced after our create-only publication.
        try:
            current = destination.lstat()
            if (current.st_dev, current.st_ino) == (published.st_dev, published.st_ino):
                destination.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        raise
    return {**checked, "path": str(destination), "windows_launcher": str(launcher)}
