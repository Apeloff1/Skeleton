"""Deterministic, independently pinned, no-clobber offline game source archives.

Archives are reproducible ZIP_STORED source snapshots, not executable installers,
signed packages, native Godot builds, rights proofs, or consumer certification.
The canonical source verifier must pass before any archive is published.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Mapping
from zipfile import ZipFile, ZipInfo, ZIP_STORED, BadZipFile, LargeZipFile

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, _MAX_BYTES, _MAX_FILES, _MAX_MANIFEST,
    _REQUIRED, _assert_original_root, _json, _parts, _read, _root_fd,
    verify_exported_package,
)

SCHEMA = "skeleton.app.offline_game_source_archive.v1"
INSPECTION_SCHEMA = "skeleton.app.offline_game_source_archive_inspection.v1"
_ARCHIVE_MAX_BYTES = 2_500_000
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,126}\.zip\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DATE = (1980, 1, 1, 0, 0, 0)


class OfflineGameArchiveError(ValueError):
    """Source archive custody, contents, or independent pin failed."""


def _parent(path: str | Path) -> tuple[Path, int]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OfflineGameArchiveError("descriptor-safe offline archives unavailable")
    target = Path(path).expanduser().absolute()
    if not _NAME.fullmatch(target.name):
        raise OfflineGameArchiveError("archive must have bounded .zip filename")
    try:
        fd = _root_fd(target.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise OfflineGameArchiveError("unsafe archive parent") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise OfflineGameArchiveError("archive parent must be owner-controlled")
        _assert_original_root(target.parent, fd)
    except BaseException:
        os.close(fd)
        raise
    return target, fd


def _canonical_zip(files: Mapping[str, bytes]) -> bytes:
    """Construct byte-stable, uncompressed ZIP with no directory or extra entries."""
    if (not 1 <= len(files) <= _MAX_FILES + 1
            or any(type(path) is not str or type(data) is not bytes
                   for path, data in files.items())):
        raise OfflineGameArchiveError("invalid archive file inventory")
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_STORED, allowZip64=False) as archive:
        for path in sorted(files):
            _parts(path)
            info = ZipInfo(path, date_time=_DATE)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = ZIP_STORED
            archive.writestr(info, files[path])
    raw = output.getvalue()
    if not 0 < len(raw) <= _ARCHIVE_MAX_BYTES:
        raise OfflineGameArchiveError("offline archive exceeds byte budget")
    return raw


def _source_payloads(source: str | Path, pin: str) -> tuple[dict[str, bytes], dict[str, object]]:
    verified = verify_exported_package(
        source, expected_manifest_sha256=pin, authorized=True,
    )
    fd = _root_fd(source)
    try:
        release = _read(fd, "release.json", _MAX_MANIFEST)
        if not hmac.compare_digest(sha256(release).hexdigest(), pin):
            raise OfflineGameArchiveError("source release changed after verification")
        manifest = _json(release, _MAX_MANIFEST)
        declared = manifest["files"]
        if type(declared) is not dict or len(declared) > _MAX_FILES:
            raise OfflineGameArchiveError("source file inventory invalid")
        files = {"release.json": release}
        total = len(release)
        for path, digest in sorted(declared.items()):
            _parts(path)
            payload = _read(fd, path, _MAX_BYTES - total)
            total += len(payload)
            if sha256(payload).hexdigest() != digest:
                raise OfflineGameArchiveError("source changed during archive snapshot")
            files[path] = payload
        _assert_original_root(source, fd)
    finally:
        os.close(fd)
    after = verify_exported_package(
        source, expected_manifest_sha256=pin, authorized=True,
    )
    if (after.get("world_digest") != verified.get("world_digest")
            or after.get("verified_files") != len(files)):
        raise OfflineGameArchiveError("source changed during archive snapshot")
    return files, verified


def _publish_private_archive(data: bytes, destination: str | Path) -> None:
    """Durably link a new owner-private archive without replacing an existing path."""
    target, fd = _parent(destination)
    temporary = ".offline-archive-" + secrets.token_hex(16)
    identity: tuple[int, int] | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        handle = os.open(temporary, flags, 0o600, dir_fd=fd)
        try:
            before = os.fstat(handle)
            identity = (before.st_dev, before.st_ino)
            offset = 0
            while offset < len(data):
                written = os.write(handle, data[offset:])
                if written <= 0:
                    raise OfflineGameArchiveError("archive write made no progress")
                offset += written
            os.fsync(handle)
        finally:
            os.close(handle)
        _assert_original_root(target.parent, fd)
        os.link(temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        final = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(final.st_mode) or final.st_nlink != 2
                or (final.st_dev, final.st_ino) != identity
                or final.st_size != len(data) or final.st_mode & 0o077):
            raise OfflineGameArchiveError("archive publication identity changed")
        os.fsync(fd)
        _assert_original_root(target.parent, fd)
        os.unlink(temporary, dir_fd=fd)
        identity = None
        os.fsync(fd)
    except BaseException as exc:
        # Never unlink the final destination by a stale path check: another
        # local writer may have replaced it. An uncertain publication is
        # reported as failure and left for owner-controlled quarantine.
        if isinstance(exc, (OfflineGameArchiveError, PermissionError)):
            raise
        if isinstance(exc, (OSError, DualRuntimeVerificationError)):
            raise OfflineGameArchiveError("archive publication failed") from exc
        raise
    finally:
        if identity is not None:
            try:
                current = os.stat(temporary, dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    os.unlink(temporary, dir_fd=fd)
            except OSError:
                pass
        os.close(fd)


def publish_offline_game_archive(
    source: str | Path, destination: str | Path, *,
    expected_manifest_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Build a deterministic ZIP only from a fully verified original game."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if type(expected_manifest_sha256) is not str or not _HEX.fullmatch(expected_manifest_sha256):
        raise OfflineGameArchiveError("independent source manifest pin required")
    # Collapse lexical '..' before source/output overlap validation. Path.absolute()
    # preserves these components, and descriptor-relative nofollow alone does
    # not prevent a writable archive name inside the original source tree.
    # Do not resolve symlinks: the owner-controlled descriptor openers reject them.
    target = Path(os.path.abspath(os.fspath(Path(destination).expanduser())))
    source_path = Path(os.path.abspath(os.fspath(Path(source).expanduser())))
    if os.path.commonpath((str(source_path), str(target))) == str(source_path):
        raise OfflineGameArchiveError("archive cannot be placed inside game source")
    # Validate destination ownership and collision before reading source.
    _, fd = _parent(target)
    try:
        try:
            os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineGameArchiveError("archive destination already occupied")
    finally:
        os.close(fd)
    files, verified = _source_payloads(source, expected_manifest_sha256)
    raw = _canonical_zip(files)
    _publish_private_archive(raw, target)
    # Publication itself is not proof of durable byte custody. Read the
    # independently named, owner-private file back through a nofollow
    # descriptor and compare its complete digest before reporting success.
    # Reverify the source once more: a source mutation after the snapshot
    # must not be misreported as a successful handoff. If either check fails,
    # preserve the published inode for explicit operator quarantine rather
    # than attempting an unsafe pathname-based rollback.
    published = _read_private_archive(target)
    if not hmac.compare_digest(sha256(published).digest(), sha256(raw).digest()):
        raise OfflineGameArchiveError("archive changed after publication")
    final = verify_exported_package(
        source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (final.get("world_digest") != verified.get("world_digest")
            or final.get("verified_files") != len(files)):
        raise OfflineGameArchiveError("source changed after archive publication")
    return {
        "schema": SCHEMA,
        "status": "source_archive_published_release_blocked",
        "project_id": verified["project_id"],
        "archive_file": str(target),
        "independent_archive_sha256": sha256(raw).hexdigest(),
        "manifest_sha256": expected_manifest_sha256,
        "world_digest": verified["world_digest"],
        "archived_files": len(files),
        "archive_bytes": len(raw),
        "source_gameplay_reexecuted": True,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def _read_private_archive(path: str | Path) -> bytes:
    target, fd = _parent(path)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        handle = os.open(target.name, flags, dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid() or before.st_mode & 0o077
                    or not 0 < before.st_size <= _ARCHIVE_MAX_BYTES):
                raise OfflineGameArchiveError("archive is not an owner-private regular file")
            chunks = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(handle, min(remaining, 64 * 1024))
                if not chunk:
                    raise OfflineGameArchiveError("archive truncated during inspection")
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(handle)
            identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mode,
                                   st.st_nlink, st.st_mtime_ns, st.st_ctime_ns)
            if identity(before) != identity(after):
                raise OfflineGameArchiveError("archive changed during inspection")
        finally:
            os.close(handle)
        reopened = os.open(target.name, flags, dir_fd=fd)
        try:
            if identity(os.fstat(reopened)) != identity(before):
                raise OfflineGameArchiveError("archive replaced during inspection")
        finally:
            os.close(reopened)
        _assert_original_root(target.parent, fd)
        return b"".join(chunks)
    finally:
        os.close(fd)


def inspect_offline_game_archive(
    archive: str | Path, *, expected_archive_sha256: str,
    expected_manifest_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Inspect an archive without extracting or executing any of its members.

    A successful inspection proves byte integrity and source inventory
    consistency only. It does NOT reexecute the original gameplay from ZIP.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (type(expected_archive_sha256) is not str
            or not _HEX.fullmatch(expected_archive_sha256)
            or type(expected_manifest_sha256) is not str
            or not _HEX.fullmatch(expected_manifest_sha256)):
        raise OfflineGameArchiveError("two independent archive inspection pins required")
    try:
        raw = _read_private_archive(archive)
        if not hmac.compare_digest(sha256(raw).hexdigest(), expected_archive_sha256):
            raise OfflineGameArchiveError("archive differs from independent pin")
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as bundle:
            names = bundle.infolist()
            if not 1 <= len(names) <= _MAX_FILES + 1:
                raise OfflineGameArchiveError("archive inventory exceeds bounds")
            files = {}
            total = 0
            for info in names:
                _parts(info.filename)
                if (info.filename in files or info.is_dir()
                        or info.compress_type != ZIP_STORED or info.flag_bits & 1
                        or info.file_size < 0 or info.file_size > _MAX_BYTES
                        or info.extra or info.comment):
                    raise OfflineGameArchiveError("unsafe archive entry")
                total += info.file_size
                if total > _MAX_BYTES:
                    raise OfflineGameArchiveError("archive source bytes exceed budget")
                files[info.filename] = bundle.read(info, pwd=None)
            release = files.get("release.json")
            if release is None or len(release) > _MAX_MANIFEST:
                raise OfflineGameArchiveError("archive release manifest missing")
            if sha256(release).hexdigest() != expected_manifest_sha256:
                raise OfflineGameArchiveError("archive release differs from independent pin")
            manifest = _json(release, _MAX_MANIFEST)
            digest = manifest.get("manifest_digest")
            body = {key: value for key, value in manifest.items()
                    if key != "manifest_digest"}
            if (manifest.get("schema") != "skeleton.game_builder.dual_runtime_package.v1"
                    or type(digest) is not str or digest != canonical_digest(body)
                    or manifest.get("automatic_publication") is not False
                    or manifest.get("godot_hardware_tested") is not False):
                raise OfflineGameArchiveError("unsupported archived release authority")
            declared = manifest.get("files")
            if (type(declared) is not dict or not 1 <= len(declared) <= _MAX_FILES
                    or "release.json" in declared
                    or set(files) != set(declared) | {"release.json"}
                    or not _REQUIRED <= set(files)
                    or manifest.get("proof_status") != "python-simulated-winning-actions"):
                raise OfflineGameArchiveError("archived source inventory mismatch")
            for name, expected_digest in declared.items():
                if (type(expected_digest) is not str or not _HEX.fullmatch(expected_digest)
                        or sha256(files[name]).hexdigest() != expected_digest):
                    raise OfflineGameArchiveError("archived source digest mismatch")
        if not hmac.compare_digest(_canonical_zip(files), raw):
            raise OfflineGameArchiveError("noncanonical or ambiguous source archive")
    except (OSError, BadZipFile, LargeZipFile, KeyError, TypeError,
            ValueError, UnicodeError, RuntimeError) as exc:
        if isinstance(exc, OfflineGameArchiveError):
            raise
        raise OfflineGameArchiveError("invalid or inaccessible offline archive") from exc
    return {
        "schema": INSPECTION_SCHEMA,
        "status": "source_archive_integrity_verified_release_blocked",
        "manifest_sha256": expected_manifest_sha256,
        "archive_sha256": expected_archive_sha256,
        "archived_files": len(files),
        "archive_bytes": len(raw),
        "archive_integrity_verified": True,
        "source_gameplay_reexecuted_now": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "INSPECTION_SCHEMA", "OfflineGameArchiveError",
    "publish_offline_game_archive", "inspect_offline_game_archive",
]
