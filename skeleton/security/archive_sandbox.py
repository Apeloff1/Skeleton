"""Bounded archive inspection and extraction sandbox.

This module is the extraction counterpart to skeleton.shells.toolchains.archive.
The shell toolchain intentionally exposes archive listing, testing, and creation
but no raw extraction operation. Extraction here is performed member-by-member
through RootedFilesystem after a complete preflight proves that the archive is
within policy.

Security properties:
- ZIP and TAR only, detected from content rather than suffix.
- Absolute paths, parent traversal, Windows drive paths, backslashes, control
  characters, overlong/deep paths, duplicate normalized names, and case-fold
  collisions are rejected.
- ZIP symlinks, encryption, special Unix types, and suspicious compression
  ratios are rejected.
- TAR symlinks, hard links, devices, FIFOs, sparse files, and unsupported member
  types are rejected.
- Member count, archive bytes, member bytes, total expanded bytes, path depth,
  expansion ratio, and streamed byte counts are bounded.
- Extraction happens in a private sibling staging directory and is published
  with one atomic directory rename only after all evidence is written.

The code never calls extract(), extractall(), or shutil.unpack_archive().
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import tarfile
from typing import BinaryIO, Iterable, Iterator, Literal
import zipfile

from skeleton.security.rooted_fs import (
    FileReceipt,
    FilesystemLimits,
    RootedFilesystem,
    receipts_digest,
)

ArchiveKind = Literal["zip", "tar"]
MemberKind = Literal["file", "directory"]

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_MANIFEST_NAME = ".skeleton-extraction-manifest.json"
_CHUNK_SIZE = 1024 * 1024


class ArchiveSandboxError(RuntimeError):
    """Base class for fail-closed archive sandbox errors."""


class ArchivePolicyError(ArchiveSandboxError, ValueError):
    """Raised when archive metadata violates extraction policy."""


class ArchiveFormatError(ArchiveSandboxError, ValueError):
    """Raised when the input is not a supported ZIP or TAR archive."""


class ArchiveIntegrityError(ArchiveSandboxError):
    """Raised when streamed content disagrees with preflight metadata."""


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_archive_bytes: int = 512 * 1024 * 1024
    max_members: int = 50_000
    max_member_bytes: int = 128 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_path_bytes: int = 1_024
    max_depth: int = 64
    max_compression_ratio: float = 200.0
    max_archive_expansion_ratio: float = 100.0
    max_stream_chunks_per_member: int = 131_072

    def __post_init__(self) -> None:
        integer_fields = (
            "max_archive_bytes",
            "max_members",
            "max_member_bytes",
            "max_total_bytes",
            "max_path_bytes",
            "max_depth",
            "max_stream_chunks_per_member",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_compression_ratio", "max_archive_expansion_ratio"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    raw_name: str
    path: str
    kind: MemberKind
    size: int
    compressed_size: int | None
    mode: int

    def __post_init__(self) -> None:
        if self.kind not in {"file", "directory"}:
            raise ValueError("unsupported member kind")
        if self.size < 0:
            raise ValueError("member size must be non-negative")
        if self.compressed_size is not None and self.compressed_size < 0:
            raise ValueError("compressed size must be non-negative")
        if not 0 <= self.mode <= 0o777:
            raise ValueError("member mode outside permission range")


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    archive: str
    kind: ArchiveKind
    archive_size: int
    members: tuple[ArchiveMember, ...]
    total_file_bytes: int
    manifest_digest: str

    @property
    def file_count(self) -> int:
        return sum(member.kind == "file" for member in self.members)

    @property
    def directory_count(self) -> int:
        return sum(member.kind == "directory" for member in self.members)


@dataclass(frozen=True, slots=True)
class ExtractionReceipt:
    destination: str
    archive_kind: ArchiveKind
    archive_size: int
    member_count: int
    file_count: int
    total_file_bytes: int
    plan_digest: str
    content_digest: str
    manifest_path: str = _MANIFEST_NAME


def _safe_archive_path(path: str | os.PathLike[str], limits: ArchiveLimits) -> Path:
    candidate = Path(path)
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise ArchiveFormatError("archive is unavailable") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ArchivePolicyError("archive path must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise ArchivePolicyError("archive path must be a regular file")
    if info.st_size <= 0:
        raise ArchiveFormatError("archive is empty")
    if info.st_size > limits.max_archive_bytes:
        raise ArchivePolicyError("archive exceeds byte bound")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise ArchiveFormatError("archive cannot be resolved") from exc


def _normalize_member_name(raw_name: str, limits: ArchiveLimits) -> str:
    if not isinstance(raw_name, str) or not raw_name:
        raise ArchivePolicyError("archive member name must be non-empty text")
    if "\\" in raw_name:
        raise ArchivePolicyError("archive member contains backslash path syntax")
    if _CONTROL.search(raw_name):
        raise ArchivePolicyError("archive member contains control characters")
    if raw_name.startswith("/") or _WINDOWS_DRIVE.match(raw_name):
        raise ArchivePolicyError("archive member path must be relative")
    if len(raw_name.encode("utf-8")) > limits.max_path_bytes:
        raise ArchivePolicyError("archive member path exceeds byte bound")

    parts: list[str] = []
    for part in PurePosixPath(raw_name).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ArchivePolicyError("archive member attempts parent traversal")
        if _CONTROL.search(part):
            raise ArchivePolicyError("archive member contains control characters")
        parts.append(part)
    if not parts:
        raise ArchivePolicyError("archive member normalizes to root")
    if len(parts) > limits.max_depth:
        raise ArchivePolicyError("archive member exceeds path depth bound")
    normalized = "/".join(parts)
    if len(normalized.encode("utf-8")) > limits.max_path_bytes:
        raise ArchivePolicyError("normalized archive path exceeds byte bound")
    if normalized == _MANIFEST_NAME:
        raise ArchivePolicyError("archive member collides with reserved evidence manifest")
    return normalized


def _safe_mode(raw_mode: int, *, directory: bool) -> int:
    mode = stat.S_IMODE(raw_mode)
    mode &= 0o755 if directory else 0o744
    mode |= 0o700 if directory else 0o600
    return mode


def _manifest_digest(
    kind: ArchiveKind,
    archive_size: int,
    members: Iterable[ArchiveMember],
) -> str:
    rows = [
        {
            "path": member.path,
            "kind": member.kind,
            "size": member.size,
            "compressed_size": member.compressed_size,
            "mode": member.mode,
        }
        for member in members
    ]
    payload = json.dumps(
        {"kind": kind, "archive_size": archive_size, "members": rows},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_member_set(
    members: list[ArchiveMember],
    archive_size: int,
    limits: ArchiveLimits,
) -> None:
    if not members:
        raise ArchivePolicyError("archive contains no extractable members")
    if len(members) > limits.max_members:
        raise ArchivePolicyError("archive member-count bound exceeded")

    by_path: dict[str, ArchiveMember] = {}
    casefolded: dict[str, str] = {}
    total = 0
    file_count = 0

    for member in members:
        if member.path in by_path:
            raise ArchivePolicyError("archive contains duplicate normalized path")
        folded = member.path.casefold()
        previous = casefolded.get(folded)
        if previous is not None and previous != member.path:
            raise ArchivePolicyError("archive contains case-fold path collision")

        parent = PurePosixPath(member.path).parent
        while str(parent) not in {"", "."}:
            prior = by_path.get(parent.as_posix())
            if prior is not None and prior.kind == "file":
                raise ArchivePolicyError("archive file shadows child path")
            parent = parent.parent

        by_path[member.path] = member
        casefolded[folded] = member.path

        if member.kind != "file":
            continue
        file_count += 1
        if member.size > limits.max_member_bytes:
            raise ArchivePolicyError("archive member exceeds byte bound")
        total += member.size
        if total > limits.max_total_bytes:
            raise ArchivePolicyError("archive expanded-size bound exceeded")
        if member.compressed_size is not None:
            compressed = member.compressed_size
            if member.size > 0 and compressed == 0:
                raise ArchivePolicyError("archive member has impossible compression ratio")
            if compressed > 0 and member.size / compressed > limits.max_compression_ratio:
                raise ArchivePolicyError("archive member compression-ratio bound exceeded")

    # Catch a later file that becomes the parent of an earlier member.
    for member in members:
        if member.kind != "file":
            continue
        prefix = member.path.rstrip("/") + "/"
        if any(other.path.startswith(prefix) for other in members if other is not member):
            raise ArchivePolicyError("archive file shadows child path")

    if file_count == 0:
        raise ArchivePolicyError("archive contains no regular files")
    if archive_size and total / archive_size > limits.max_archive_expansion_ratio:
        raise ArchivePolicyError("archive expansion-ratio bound exceeded")


def _zip_member(info: zipfile.ZipInfo, limits: ArchiveLimits) -> ArchiveMember:
    # ZipInfo.filename truncates at the first NUL for compatibility, while
    # orig_filename retains the archive-provided name. Security policy must
    # validate the original evidence or a raw NUL can bypass path checks.
    raw_name = info.orig_filename
    normalized = _normalize_member_name(raw_name, limits)
    if info.flag_bits & 0x1:
        raise ArchivePolicyError("encrypted ZIP members are forbidden")

    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type == stat.S_IFLNK:
        raise ArchivePolicyError("ZIP symlink members are forbidden")
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArchivePolicyError("ZIP special file member is forbidden")

    directory = info.is_dir() or file_type == stat.S_IFDIR
    kind: MemberKind = "directory" if directory else "file"
    size = 0 if directory else info.file_size
    compressed = 0 if directory else info.compress_size
    if size < 0 or compressed < 0:
        raise ArchivePolicyError("ZIP member has invalid size metadata")
    return ArchiveMember(
        raw_name=raw_name,
        path=normalized,
        kind=kind,
        size=size,
        compressed_size=compressed,
        mode=_safe_mode(unix_mode or (0o755 if directory else 0o644), directory=directory),
    )


def _tar_member(info: tarfile.TarInfo, limits: ArchiveLimits) -> ArchiveMember:
    normalized = _normalize_member_name(info.name, limits)
    if info.issym():
        raise ArchivePolicyError("TAR symlink members are forbidden")
    if info.islnk():
        raise ArchivePolicyError("TAR hard-link members are forbidden")
    if info.ischr() or info.isblk() or info.isfifo():
        raise ArchivePolicyError("TAR device/FIFO members are forbidden")
    if getattr(info, "sparse", None):
        raise ArchivePolicyError("TAR sparse members are forbidden")

    if info.isdir():
        kind: MemberKind = "directory"
        size = 0
    elif info.isfile():
        kind = "file"
        size = info.size
    else:
        raise ArchivePolicyError("unsupported TAR member type")
    if size < 0:
        raise ArchivePolicyError("TAR member has invalid size metadata")
    return ArchiveMember(
        raw_name=info.name,
        path=normalized,
        kind=kind,
        size=size,
        compressed_size=None,
        mode=_safe_mode(info.mode, directory=kind == "directory"),
    )


def plan_archive(
    archive: str | os.PathLike[str],
    *,
    limits: ArchiveLimits | None = None,
) -> ExtractionPlan:
    """Inspect an archive completely before creating a destination."""
    policy = limits or ArchiveLimits()
    path = _safe_archive_path(archive, policy)
    archive_size = path.stat().st_size

    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as handle:
                infos = handle.infolist()
                if len(infos) > policy.max_members:
                    raise ArchivePolicyError("archive member-count bound exceeded")
                members = [_zip_member(info, policy) for info in infos]
            kind: ArchiveKind = "zip"
        elif tarfile.is_tarfile(path):
            with tarfile.open(path, mode="r:*") as handle:
                infos = handle.getmembers()
                if len(infos) > policy.max_members:
                    raise ArchivePolicyError("archive member-count bound exceeded")
                members = [_tar_member(info, policy) for info in infos]
            kind = "tar"
        else:
            raise ArchiveFormatError("unsupported archive format")
    except ArchiveSandboxError:
        raise
    except (OSError, EOFError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ArchiveFormatError("archive metadata cannot be parsed") from exc

    _validate_member_set(members, archive_size, policy)
    total = sum(member.size for member in members if member.kind == "file")
    return ExtractionPlan(
        archive=str(path),
        kind=kind,
        archive_size=archive_size,
        members=tuple(members),
        total_file_bytes=total,
        manifest_digest=_manifest_digest(kind, archive_size, members),
    )


def _stream_chunks(
    stream: BinaryIO,
    *,
    member: ArchiveMember,
    limits: ArchiveLimits,
) -> Iterator[bytes]:
    total = 0
    chunks = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        chunks += 1
        if chunks > limits.max_stream_chunks_per_member:
            raise ArchiveIntegrityError("archive member exceeded stream chunk bound")
        total += len(chunk)
        if total > member.size or total > limits.max_member_bytes:
            raise ArchiveIntegrityError("archive member exceeded declared size")
        yield chunk
    if total != member.size:
        raise ArchiveIntegrityError("archive member size differs from preflight metadata")


def _stage_filesystem(stage: Path, limits: ArchiveLimits) -> RootedFilesystem:
    return RootedFilesystem(
        stage,
        limits=FilesystemLimits(
            max_read_bytes=limits.max_member_bytes,
            max_write_bytes=limits.max_member_bytes,
            max_stream_chunks=limits.max_stream_chunks_per_member,
            max_path_bytes=limits.max_path_bytes,
            max_depth=limits.max_depth,
            max_directory_entries=limits.max_members + 1,
        ),
    )


def _extract_zip(
    plan: ExtractionPlan,
    boundary: RootedFilesystem,
    limits: ArchiveLimits,
) -> list[FileReceipt]:
    receipts: list[FileReceipt] = []
    with zipfile.ZipFile(plan.archive, "r") as handle:
        infos = handle.infolist()
        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            if info.filename in by_name:
                raise ArchiveIntegrityError("ZIP member identity changed after preflight")
            by_name[info.filename] = info

        for member in plan.members:
            info = by_name.get(member.raw_name)
            if info is None:
                raise ArchiveIntegrityError("ZIP member disappeared after preflight")
            if _zip_member(info, limits) != member:
                raise ArchiveIntegrityError("ZIP member metadata changed after preflight")
            if member.kind == "directory":
                boundary.mkdir(member.path, parents=True, mode=member.mode)
                continue
            try:
                stream = handle.open(info, mode="r")
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ArchiveIntegrityError("ZIP member cannot be opened") from exc
            with stream:
                receipts.append(
                    boundary.write_stream(
                        member.path,
                        _stream_chunks(stream, member=member, limits=limits),
                        expected_size=member.size,
                        mode=member.mode,
                        create_parents=True,
                    )
                )
    return receipts


def _extract_tar(
    plan: ExtractionPlan,
    boundary: RootedFilesystem,
    limits: ArchiveLimits,
) -> list[FileReceipt]:
    receipts: list[FileReceipt] = []
    with tarfile.open(plan.archive, mode="r:*") as handle:
        infos = handle.getmembers()
        by_name: dict[str, tarfile.TarInfo] = {}
        for info in infos:
            if info.name in by_name:
                raise ArchiveIntegrityError("TAR member identity changed after preflight")
            by_name[info.name] = info

        for member in plan.members:
            info = by_name.get(member.raw_name)
            if info is None:
                raise ArchiveIntegrityError("TAR member disappeared after preflight")
            if _tar_member(info, limits) != member:
                raise ArchiveIntegrityError("TAR member metadata changed after preflight")
            if member.kind == "directory":
                boundary.mkdir(member.path, parents=True, mode=member.mode)
                continue
            stream = handle.extractfile(info)
            if stream is None:
                raise ArchiveIntegrityError("TAR regular member has no data stream")
            with stream:
                receipts.append(
                    boundary.write_stream(
                        member.path,
                        _stream_chunks(stream, member=member, limits=limits),
                        expected_size=member.size,
                        mode=member.mode,
                        create_parents=True,
                    )
                )
    return receipts


def _manifest_payload(
    plan: ExtractionPlan,
    content_digest: str,
    receipts: Iterable[FileReceipt],
) -> str:
    data = {
        "schema_version": 1,
        "archive_kind": plan.kind,
        "archive_size": plan.archive_size,
        "member_count": len(plan.members),
        "file_count": plan.file_count,
        "total_file_bytes": plan.total_file_bytes,
        "plan_digest": plan.manifest_digest,
        "content_digest": content_digest,
        "files": [
            {
                "path": receipt.path,
                "size": receipt.size,
                "sha256": receipt.sha256,
                "mode": receipt.mode,
            }
            for receipt in sorted(receipts, key=lambda item: item.path)
        ],
    }
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def extract_archive(
    archive: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    limits: ArchiveLimits | None = None,
) -> ExtractionReceipt:
    """Extract to a previously absent directory with atomic publication.

    The destination parent is pinned by descriptor for the entire staging and
    publication transaction.  This prevents a concurrent parent rename or
    symlink substitution from redirecting the final rename outside the parent
    directory that passed policy validation.
    """
    policy = limits or ArchiveLimits()
    plan = plan_archive(archive, limits=policy)
    destination_path = Path(destination)
    if not destination_path.name or destination_path.name in {".", ".."}:
        raise ArchivePolicyError("invalid extraction destination")

    try:
        parent_info = destination_path.parent.lstat()
    except OSError as exc:
        raise ArchivePolicyError("extraction destination parent is unavailable") from exc
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise ArchivePolicyError("extraction destination parent must be a real directory")
    try:
        parent = destination_path.parent.resolve(strict=True)
        resolved_parent_info = parent.stat()
    except OSError as exc:
        raise ArchivePolicyError("extraction destination parent cannot be resolved") from exc

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        parent_fd = os.open(parent, flags)
    except OSError as exc:
        raise ArchiveSandboxError("extraction destination parent cannot be pinned") from exc

    stage_name = ""
    published = False
    original_error: BaseException | None = None
    try:
        pinned = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(pinned.st_mode)
            or (pinned.st_dev, pinned.st_ino)
            != (resolved_parent_info.st_dev, resolved_parent_info.st_ino)
        ):
            raise ArchiveSandboxError("extraction destination parent identity changed")

        final_name = destination_path.name
        try:
            os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except (OSError, TypeError) as exc:
            raise ArchivePolicyError("extraction destination cannot be inspected") from exc
        else:
            raise ArchivePolicyError("extraction destination must not already exist")

        for _ in range(64):
            candidate = f".{final_name}.extract-{secrets.token_hex(12)}"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=parent_fd)
                stage_name = candidate
                break
            except FileExistsError:
                continue
            except (OSError, TypeError) as exc:
                raise ArchiveSandboxError(
                    "unable to create extraction staging directory"
                ) from exc
        if not stage_name:
            raise ArchiveSandboxError("extraction staging name retry budget exhausted")

        stage = parent / stage_name
        boundary = _stage_filesystem(stage, policy)
        receipts = (
            _extract_zip(plan, boundary, policy)
            if plan.kind == "zip"
            else _extract_tar(plan, boundary, policy)
        )
        if sum(receipt.size for receipt in receipts) != plan.total_file_bytes:
            raise ArchiveIntegrityError("extracted total differs from preflight metadata")

        content_digest = receipts_digest(receipts)
        boundary.write_text(
            _MANIFEST_NAME,
            _manifest_payload(plan, content_digest, receipts),
            mode=0o600,
        )

        # Re-check the pathname immediately before publication.  The rename
        # itself remains descriptor-relative, so a subsequent path swap cannot
        # redirect the operation to a different parent inode.
        try:
            observed_parent = parent.lstat()
        except OSError as exc:
            raise ArchiveSandboxError(
                "extraction destination parent became unavailable"
            ) from exc
        if (
            stat.S_ISLNK(observed_parent.st_mode)
            or (observed_parent.st_dev, observed_parent.st_ino)
            != (pinned.st_dev, pinned.st_ino)
        ):
            raise ArchiveSandboxError("extraction destination parent identity changed")
        try:
            os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except (OSError, TypeError) as exc:
            raise ArchivePolicyError("extraction destination cannot be inspected") from exc
        else:
            raise ArchivePolicyError("extraction destination appeared during extraction")

        try:
            os.replace(
                stage_name,
                final_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except (OSError, TypeError) as exc:
            raise ArchiveSandboxError("unable to publish extracted directory") from exc
        published = True
        final = parent / final_name
        return ExtractionReceipt(
            destination=str(final),
            archive_kind=plan.kind,
            archive_size=plan.archive_size,
            member_count=len(plan.members),
            file_count=plan.file_count,
            total_file_bytes=plan.total_file_bytes,
            plan_digest=plan.manifest_digest,
            content_digest=content_digest,
        )
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        if not published and stage_name:
            try:
                shutil.rmtree(stage_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except (OSError, TypeError) as cleanup_exc:
                if original_error is None:
                    raise ArchiveSandboxError(
                        "extraction staging cleanup failed"
                    ) from cleanup_exc
        os.close(parent_fd)


def load_extraction_manifest(
    destination: str | os.PathLike[str],
) -> dict[str, object]:
    """Load and minimally validate extraction evidence."""
    boundary = RootedFilesystem(
        destination,
        limits=FilesystemLimits(max_read_bytes=8 * 1024 * 1024),
    )
    raw = boundary.read_text(_MANIFEST_NAME, max_bytes=8 * 1024 * 1024)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ArchiveIntegrityError("extraction manifest is invalid JSON") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ArchiveIntegrityError("extraction manifest schema is invalid")
    required = {
        "archive_kind",
        "archive_size",
        "member_count",
        "file_count",
        "total_file_bytes",
        "plan_digest",
        "content_digest",
        "files",
    }
    if not required.issubset(value):
        raise ArchiveIntegrityError("extraction manifest is incomplete")
    return value


__all__ = [
    "ArchiveFormatError",
    "ArchiveIntegrityError",
    "ArchiveLimits",
    "ArchiveMember",
    "ArchivePolicyError",
    "ArchiveSandboxError",
    "ExtractionPlan",
    "ExtractionReceipt",
    "extract_archive",
    "load_extraction_manifest",
    "plan_archive",
]
