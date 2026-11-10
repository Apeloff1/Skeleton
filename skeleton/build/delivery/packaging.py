"""Deterministic, in-memory release packaging.

Archives produced here are byte-reproducible: entries are sorted, mtimes
are pinned to ``SOURCE_DATE_EPOCH`` semantics, owners are zeroed and file
modes are normalized. Packaging never reads the filesystem itself; callers
pass a mapping of relative path to bytes.
"""

from __future__ import annotations

import gzip
import io
import stat
import struct
import tarfile
import zipfile
from dataclasses import dataclass
from typing import Mapping

from skeleton.build.delivery._util import DeliveryError, normalize_relpath, sha256_bytes
from skeleton.build.delivery.artifact_manifest import MAX_ARTIFACT_BYTES, ArtifactEntry

DEFAULT_EPOCH = 315532800  # 1980-01-01, the earliest timestamp zip supports
EXECUTABLE_SUFFIXES = (".sh",)
MAX_PACKAGE_FILES = 20000
MAX_PACKAGE_EPOCH = (1 << 32) - 1  # portable gzip mtime field


def _validate_epoch(epoch: int, *, zip_format: bool) -> None:
    if type(epoch) is not int or not 0 <= epoch <= MAX_PACKAGE_EPOCH:
        raise DeliveryError("package epoch must be a bounded integer")
    if zip_format and epoch < DEFAULT_EPOCH:
        raise DeliveryError("zip timestamps cannot precede 1980")


@dataclass(frozen=True)
class PackageResult:
    name: str
    data: bytes
    sha256: str
    file_count: int

    def entry(self, kind: str, platform: str = "any") -> ArtifactEntry:
        return ArtifactEntry(self.name, kind, len(self.data), self.sha256, platform)


def _normalize_files(files: Mapping[str, bytes], prefix: str | None) -> list[tuple[str, bytes]]:
    if not isinstance(files, Mapping):
        raise DeliveryError("files mapping must be non-empty")
    # Mapping.__bool__/__len__ may lie about the actual items iterator. Do
    # not skip that iterator based on a falsy length or the bound is bypassed.
    if len(files) > MAX_PACKAGE_FILES:
        raise DeliveryError("too many files to package")
    out: dict[str, bytes] = {}
    total = 0
    root = normalize_relpath(prefix, field="prefix") if prefix else None
    for count, (raw, data) in enumerate(files.items(), 1):
        if count > MAX_PACKAGE_FILES:
            raise DeliveryError("too many files to package")
        if not isinstance(data, (bytes, bytearray)):
            raise DeliveryError(f"file {raw!r} must be bytes")
        size = len(data)
        if size > MAX_ARTIFACT_BYTES - total:
            raise DeliveryError("uncompressed package input exceeds byte limit")
        path = normalize_relpath(raw)
        if root:
            path = normalize_relpath(f"{root}/{path}")
        if path in out:
            raise DeliveryError(f"duplicate path after normalization: {path}")
        out[path] = bytes(data)
        total += size
    if not out:
        raise DeliveryError("files mapping must be non-empty")
    return sorted(out.items())


def _mode_for(path: str, executables: frozenset[str]) -> int:
    return 0o755 if path in executables or path.endswith(EXECUTABLE_SUFFIXES) else 0o644


def _check_size(name: str, data: bytes) -> None:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise DeliveryError(f"package {name} exceeds the 50 MB artifact limit")


def build_tarball(
    name: str,
    files: Mapping[str, bytes],
    *,
    prefix: str | None = None,
    epoch: int = DEFAULT_EPOCH,
    executables: frozenset[str] = frozenset(),
) -> PackageResult:
    if type(name) is not str or not name.endswith(".tar.gz"):
        raise DeliveryError("tarball name must end with .tar.gz")
    _validate_epoch(epoch, zip_format=False)
    entries = _normalize_files(files, prefix)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path, data in entries:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mtime = epoch
            info.mode = _mode_for(path, executables)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=epoch, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    data = compressed.getvalue()
    _check_size(name, data)
    return PackageResult(normalize_relpath(name), data, sha256_bytes(data), len(entries))


def build_zip(
    name: str,
    files: Mapping[str, bytes],
    *,
    prefix: str | None = None,
    epoch: int = DEFAULT_EPOCH,
    executables: frozenset[str] = frozenset(),
) -> PackageResult:
    if type(name) is not str or not name.endswith(".zip"):
        raise DeliveryError("zip name must end with .zip")
    _validate_epoch(epoch, zip_format=True)
    import time

    stamp = time.gmtime(epoch)[:6]
    entries = _normalize_files(files, prefix)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, data in entries:
            info = zipfile.ZipInfo(path, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (_mode_for(path, executables) | 0o100000) << 16
            info.create_system = 3
            zf.writestr(info, data)
    data = buf.getvalue()
    _check_size(name, data)
    return PackageResult(normalize_relpath(name), data, sha256_bytes(data), len(entries))


def _archive_input(data: bytes) -> io.BytesIO:
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_ARTIFACT_BYTES:
        raise DeliveryError("archive input exceeds byte limit")
    return io.BytesIO(data)


def list_tarball(data: bytes) -> dict[str, bytes]:
    """Inspect tar members one at a time with byte/count/path boundaries.

    This is a bounded *content* verifier, not a filesystem extractor. Never
    extract archive paths to disk or trust their Unix ownership/mode bits.
    """
    out: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=_archive_input(data), mode="r|gz") as tar:
        for count, member in enumerate(tar, 1):
            if count > MAX_PACKAGE_FILES:
                raise DeliveryError("tar member count exceeds bound")
            if not member.isfile():
                raise DeliveryError(f"non-file member {member.name}")
            path = normalize_relpath(member.name)
            if path != member.name or path in out:
                raise DeliveryError("tar member path is noncanonical or duplicated")
            if member.size < 0 or member.size > MAX_ARTIFACT_BYTES - total:
                raise DeliveryError("tar expanded bytes exceed bound")
            handle = tar.extractfile(member)
            if handle is None:
                raise DeliveryError("tar member lacks readable content")
            payload = handle.read(member.size + 1)
            if len(payload) != member.size:
                raise DeliveryError("tar member size mismatch")
            total += len(payload)
            out[path] = payload
    return out


def _preflight_zip_index(data: bytes | bytearray) -> None:
    """Bound and validate the central directory before ZipFile indexes it.

    ZipFile eagerly builds a list of every directory member at construction.
    Checking len(infolist()) afterward is too late for hostile entry counts.
    ZIP64 and multidisk archives are outside this bounded release format.
    """
    signature = bytes((80, 75, 5, 6))
    start = max(0, len(data) - 22 - 65535)
    eocd = data.rfind(signature, start)
    while eocd >= start:
        if eocd + 22 <= len(data):
            fields = struct.unpack_from("<HHHHIIH", data, eocd + 4)
            if eocd + 22 + fields[-1] == len(data):
                break
        eocd = data.rfind(signature, start, eocd)
    if eocd < start:
        raise DeliveryError("zip end-of-directory record invalid")
    disk, cd_disk, disk_count, count, size, offset, _ = fields
    if (disk or cd_disk or disk_count != count or count == 0xFFFF
            or size == 0xFFFFFFFF or offset == 0xFFFFFFFF):
        raise DeliveryError("zip central directory format unsupported")
    if count > MAX_PACKAGE_FILES:
        raise DeliveryError("zip member count exceeds bound")
    cursor = eocd - size
    if cursor < offset or cursor < 0:
        raise DeliveryError("zip central directory bounds invalid")
    for _ in range(count):
        if cursor + 46 > eocd or data[cursor:cursor + 4] != bytes((80, 75, 1, 2)):
            raise DeliveryError("zip central directory member framing invalid")
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", data, cursor + 28)
        cursor += 46 + name_len + extra_len + comment_len
        if cursor > eocd:
            raise DeliveryError("zip central directory member exceeds bounds")
    if cursor != eocd:
        raise DeliveryError("zip central directory member count mismatch")


def list_zip(data: bytes) -> dict[str, bytes]:
    """Reject duplicate, aliased, nonregular or oversized ZIP members."""
    out: dict[str, bytes] = {}
    total = 0
    archive = _archive_input(data)
    _preflight_zip_index(data)
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_PACKAGE_FILES:
            raise DeliveryError("zip member count exceeds bound")
        for info in infos:
            path = normalize_relpath(info.filename)
            if path != info.filename or path in out:
                raise DeliveryError("zip member path is noncanonical or duplicated")
            mode = info.external_attr >> 16
            # ZIP Unix metadata may encode FIFOs, sockets and device nodes,
            # not just symlinks. Never present them as ordinary file payloads.
            kind = stat.S_IFMT(mode)
            if info.is_dir() or (info.create_system == 3 and kind not in (0, stat.S_IFREG)):
                raise DeliveryError("zip nonregular member rejected")
            if info.flag_bits & 1:
                raise DeliveryError("zip encrypted member rejected")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise DeliveryError("zip compression method unsupported")
            if info.file_size < 0 or info.file_size > MAX_ARTIFACT_BYTES - total:
                raise DeliveryError("zip expanded bytes exceed bound")
            with zf.open(info) as handle:
                payload = handle.read(info.file_size + 1)
            if len(payload) != info.file_size:
                raise DeliveryError("zip member size mismatch")
            total += len(payload)
            out[path] = payload
    return out
