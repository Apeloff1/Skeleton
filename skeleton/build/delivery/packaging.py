"""Deterministic, in-memory release packaging.

Archives produced here are byte-reproducible: entries are sorted, mtimes
are pinned to ``SOURCE_DATE_EPOCH`` semantics, owners are zeroed and file
modes are normalized. Packaging never reads the filesystem itself; callers
pass a mapping of relative path to bytes.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from dataclasses import dataclass
from typing import Mapping

from skeleton.build.delivery._util import DeliveryError, normalize_relpath, sha256_bytes
from skeleton.build.delivery.artifact_manifest import MAX_ARTIFACT_BYTES, ArtifactEntry

DEFAULT_EPOCH = 315532800  # 1980-01-01, the earliest timestamp zip supports
EXECUTABLE_SUFFIXES = (".sh",)
MAX_PACKAGE_FILES = 20000


@dataclass(frozen=True)
class PackageResult:
    name: str
    data: bytes
    sha256: str
    file_count: int

    def entry(self, kind: str, platform: str = "any") -> ArtifactEntry:
        return ArtifactEntry(self.name, kind, len(self.data), self.sha256, platform)


def _normalize_files(files: Mapping[str, bytes], prefix: str | None) -> list[tuple[str, bytes]]:
    if not isinstance(files, Mapping) or not files:
        raise DeliveryError("files mapping must be non-empty")
    if len(files) > MAX_PACKAGE_FILES:
        raise DeliveryError("too many files to package")
    out: dict[str, bytes] = {}
    root = normalize_relpath(prefix, field="prefix") if prefix else None
    for raw, data in files.items():
        if not isinstance(data, (bytes, bytearray)):
            raise DeliveryError(f"file {raw!r} must be bytes")
        path = normalize_relpath(raw)
        if root:
            path = f"{root}/{path}"
        if path in out:
            raise DeliveryError(f"duplicate path after normalization: {path}")
        out[path] = bytes(data)
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
    if not name.endswith(".tar.gz"):
        raise DeliveryError("tarball name must end with .tar.gz")
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
    if not name.endswith(".zip"):
        raise DeliveryError("zip name must end with .zip")
    if epoch < DEFAULT_EPOCH:
        raise DeliveryError("zip timestamps cannot precede 1980")
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


def list_tarball(data: bytes) -> dict[str, bytes]:
    """Read back a tarball produced by :func:`build_tarball` (for verification)."""
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                raise DeliveryError(f"non-file member {member.name}")
            normalize_relpath(member.name)
            handle = tar.extractfile(member)
            out[member.name] = handle.read() if handle else b""
    return out


def list_zip(data: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            normalize_relpath(info.filename)
            out[info.filename] = zf.read(info)
    return out
