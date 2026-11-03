"""Deterministic single-file bundle export/import.

The bundle is one JSON envelope: ``{manifest, sections, receipts}`` wrapped by
a save codec for integrity. ``skeleton`` does not import ``backend``, so the
codec and tenant namespace are injected through small Protocols; production
callers pass ``backend.core.save_envelope.SaveCodec(BUNDLE_SCHEMA_VERSION)``
and ``backend.core.tenant_storage_boundary.tenant_storage_namespace``.
"""
from __future__ import annotations

import os
import secrets
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Protocol

from skeleton.ai.game_builder.game_project_workspace import PROJECT_MAX_FILES, SOURCE_MAX
from skeleton.kernel.game_save_plane import ChunkReceiptStore

from .manifest import BundleError, BundleManifest
from .project_save import CHUNK_CHARS, BUNDLE_SECTIONS, ProjectSaver, build_state, files_from_state, manifest_for

MAX_BUNDLE_BYTES = 64_000_000
BUNDLE_SUFFIX = ".gfbundle.json"
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_NS = re.compile(r"^tenant:([a-f0-9]{24}):([A-Za-z0-9_.:-]{1,96})$")


class EnvelopeLike(Protocol):
    payload: dict[str, Any]


class BundleCodec(Protocol):
    def encode(self, payload: dict[str, Any]) -> str: ...
    def decode(self, raw: str) -> EnvelopeLike: ...


NamespaceFn = Callable[..., str]  # (tenant_id, *, purpose) -> "tenant:<fp>:<purpose>"


def _bounded_bundle_bytes(raw: str) -> bytes:
    if type(raw) is not str:
        raise BundleError("bundle must be UTF-8 text")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError:
        raise BundleError("bundle must be valid UTF-8") from None
    if len(encoded) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds size limit")
    return encoded


def safe_member_path(path: str) -> str:
    """Reject zip-slip style member paths (absolute, traversal, backslash, hidden)."""
    if not isinstance(path, str) or not 1 <= len(path) <= 450 or "\\" in path or "\x00" in path:
        raise BundleError("unsafe bundle member path")
    pp = PurePosixPath(path)
    # PurePosixPath normalizes repeated separators and dot components; aliases
    # must not be accepted as distinct signed bundle member identities.
    if path != pp.as_posix():
        raise BundleError("noncanonical bundle member path")
    if pp.is_absolute() or len(pp.parts) > 12 or any(
            p in (".", "..") or p.startswith(".") or not _SEGMENT.fullmatch(p) for p in pp.parts):
        raise BundleError(f"unsafe bundle member path: {path!r}")
    return pp.as_posix()


def export_bundle(saver: ProjectSaver, project_id: str, codec: BundleCodec, *,
                  sequence: int | None = None) -> str:
    v = saver.load(project_id, sequence=sequence)
    sections, receipts = build_state(v.manifest.project_id, v.manifest.genre, v.files,
                                     label=v.manifest.label)
    if receipts.root() != v.manifest.receipt_root:
        raise BundleError("re-chunked content does not match saved receipt root")
    for name, body in v.sections.items():
        if name not in BUNDLE_SECTIONS:
            sections[name] = body
    raw = codec.encode({"manifest": v.manifest.payload(), "sections": sections,
                        "receipts": receipts.to_state()})
    _bounded_bundle_bytes(raw)
    return raw



def _validate_receipt_state(state: Any, manifest: BundleManifest,
                            index: dict[str, Any]) -> None:
    """Bound receipt allocation and prove canonical chunk identities first.

    A valid envelope signature does not make its receipt inventory small or
    internally consistent. Reject hostile shapes before from_state() creates
    digest-indexed Python objects, and never trust a caller-provided chunk ID
    as authority for a different file or position.
    """
    if type(state) is not dict or set(state) != {"receipts"} or type(state["receipts"]) is not list:
        raise BundleError("invalid bundle receipt state")
    expected: dict[str, tuple[str, int]] = {}
    for entry in manifest.files:
        item = index[entry.path]
        if type(item) is not dict or set(item) != {"sha256", "bytes", "chunks"}:
            raise BundleError("invalid bundle file index")
        chunks = item["chunks"]
        # UTF-8 bytes >= Unicode code points. This bounds the number of
        # CHUNK_CHARS-sized pieces even for multibyte source text.
        maximum = max(1, (entry.bytes + CHUNK_CHARS - 1) // CHUNK_CHARS)
        if (type(item["bytes"]) is not int or item["bytes"] != entry.bytes
                or item["sha256"] != entry.sha256 or type(chunks) is not list
                or not 1 <= len(chunks) <= maximum):
            raise BundleError("invalid bundle file index")
        for number, chunk_id in enumerate(chunks):
            canonical = f"{entry.path}#{number}"
            if type(chunk_id) is not str or chunk_id != canonical:
                raise BundleError("noncanonical bundle chunk identity")
            expected[canonical] = (entry.path, number)
    records = state["receipts"]
    if len(records) != len(expected):
        raise BundleError("bundle receipt count mismatch")
    seen: set[str] = set()
    for record in records:
        if type(record) is not dict or set(record) != {"chunk_id", "body"}:
            raise BundleError("invalid bundle receipt record")
        chunk_id = record["chunk_id"]
        if type(chunk_id) is not str or chunk_id not in expected or chunk_id in seen:
            raise BundleError("duplicate or unknown bundle receipt")
        path, number = expected[chunk_id]
        body = record["body"]
        if (type(body) is not dict or set(body) != {"path", "index", "text"}
                or body["path"] != path or type(body["index"]) is not int
                or body["index"] != number or type(body["text"]) is not str
                or len(body["text"]) > CHUNK_CHARS):
            raise BundleError("bundle receipt identity or size mismatch")
        seen.add(chunk_id)


def import_bundle(raw: str, codec: BundleCodec, saver: ProjectSaver, *,
                  sequence: int | None = None) -> BundleManifest:
    """Verify a bundle end to end, then save it as a new version in ``saver``."""
    _bounded_bundle_bytes(raw)
    try:
        payload = codec.decode(raw).payload
    except ValueError as exc:  # SaveIntegrityError is a ValueError
        raise BundleError("bundle envelope failed integrity check") from exc
    if (type(payload) is not dict or set(payload) != {"manifest", "sections", "receipts"}
            or type(payload["sections"]) is not dict
            or type(payload["sections"].get("files")) is not dict):
        raise BundleError("invalid bundle payload shape")
    manifest = BundleManifest.from_payload(payload["manifest"])
    if len(manifest.files) > PROJECT_MAX_FILES:
        raise BundleError("bundle has too many files")
    for f in manifest.files:
        safe_member_path(f.path)
        if f.bytes > SOURCE_MAX:
            raise BundleError(f"{f.path} exceeds per-file size limit")
    sections = payload["sections"]
    if set(sections["files"]) != set(manifest.file_map()):
        raise BundleError("file index disagrees with manifest")
    _validate_receipt_state(payload["receipts"], manifest, sections["files"])
    receipts = ChunkReceiptStore.from_state(payload["receipts"])
    if receipts.root() != manifest.receipt_root:
        raise BundleError("receipt root mismatch")
    files = files_from_state(sections, receipts)
    for entry in manifest.files:
        if len(files[entry.path].encode("utf-8")) != entry.bytes:
            raise BundleError("bundle file byte count mismatch")
    if {p: e["sha256"] for p, e in sections["files"].items()} != manifest.file_map():
        raise BundleError("file digests disagree with manifest")
    check = manifest_for(sections, receipts, manifest.sequence, manifest.save_schema_version)
    if check.content_digest != manifest.content_digest:
        raise BundleError("manifest does not describe bundle content")
    extra = {k: v for k, v in sections.items() if k not in BUNDLE_SECTIONS}
    return saver.save_files(manifest.project_id, manifest.genre, files, sequence=sequence,
                            label=manifest.label, extra_sections=extra)


def bundle_path(base_dir: str | Path, tenant_id: str, project_id: str, namespace: NamespaceFn) -> Path:
    """Build a lexical tenant path; I/O verifies every ancestor by descriptor.

    Resolving the path here would follow attacker-controlled ancestors before
    the later open. Neither this path value nor a preflight check grants trust.
    """
    ns = namespace(tenant_id, purpose="game_project_bundles")
    m = _NS.fullmatch(ns)
    if not m:
        raise BundleError("unexpected tenant namespace shape")
    base = os.fspath(base_dir)
    if not isinstance(base, str) or not base or "\x00" in base or ".." in Path(base).parts:
        raise BundleError("unsafe bundle storage base")
    rel = PurePosixPath(m.group(1), m.group(2).replace(":", "_"),
                        safe_member_path(project_id + BUNDLE_SUFFIX))
    return Path(os.path.abspath(base)) / rel


def _held_bundle_parent(path: Path, *, create: bool) -> tuple[int, str]:
    """Walk the absolute path one component at a time without following links.

    The returned directory descriptor is used for both leaf opening and
    atomic publication, so renaming/replacing its pathname cannot redirect I/O.
    Windows must use a separate native handle backend, never path preflight.
    """
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_NONBLOCK") and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd and os.rename in os.supports_dir_fd
            and os.stat in os.supports_dir_fd and os.unlink in os.supports_dir_fd):
        raise BundleError("descriptor-anchored bundle I/O unavailable")
    raw = os.fspath(path)
    if (not isinstance(raw, str) or not raw.startswith(os.sep) or "\x00" in raw
            or len(raw) > 4096):
        raise BundleError("bundle path must be a bounded absolute path")
    parts = raw.split(os.sep)[1:]
    if not parts or len(parts) > 128 or any(part in ("", ".", "..") for part in parts):
        raise BundleError("unsafe bundle path component")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = os.open(os.sep, flags)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current, parts[-1]
    except BaseException:
        os.close(current)
        raise


def write_bundle(path: Path, raw: str) -> None:
    data = _bounded_bundle_bytes(raw)
    try:
        parent, leaf = _held_bundle_parent(path, create=True)
    except OSError as exc:
        raise BundleError("unsafe bundle directory ancestor") from exc
    temporary: str | None = None
    try:
        try:
            existing = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise BundleError("bundle target must be a regular file")
        # Exclusive, unpredictable name within the *held* parent. No pathname
        # reopening between staging, fsync and rename.
        for _ in range(4):
            candidate = "." + secrets.token_hex(16) + ".gfbundle.tmp"
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=parent)
                temporary = candidate
                break
            except FileExistsError:
                continue
        else:
            raise BundleError("could not allocate private bundle staging file")
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.rename(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent)
        temporary = None
        os.fsync(parent)
    except OSError as exc:
        raise BundleError("bundle publication failed closed") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def read_bundle(path: Path) -> str:
    """Read through held ancestor/leaf descriptors with bounded integrity."""
    try:
        parent, leaf = _held_bundle_parent(path, create=False)
    except OSError as exc:
        raise BundleError("unsafe bundle directory ancestor") from exc
    try:
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
        except OSError as exc:
            raise BundleError("bundle cannot be opened without following links") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise BundleError("bundle must be a regular file")
            # A second directory entry can alias an unrelated tenant's inode.
            # The signed envelope does not authorize that filesystem alias.
            if before.st_nlink != 1:
                raise BundleError("hard-linked bundle source is not trusted")
            if before.st_size > MAX_BUNDLE_BYTES:
                raise BundleError("bundle exceeds size limit")
            blocks: list[bytes] = []
            count = 0
            while count <= MAX_BUNDLE_BYTES:
                block = os.read(fd, min(1024 * 1024, MAX_BUNDLE_BYTES + 1 - count))
                if not block:
                    break
                count += len(block)
                blocks.append(block)
            after = os.fstat(fd)
            if count > MAX_BUNDLE_BYTES:
                raise BundleError("bundle exceeds size limit")
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ) or count != before.st_size:
                raise BundleError("bundle changed during descriptor read")
            try:
                return b"".join(blocks).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BundleError("bundle must contain UTF-8") from exc
        finally:
            os.close(fd)
    finally:
        os.close(parent)


__all__ = ["MAX_BUNDLE_BYTES", "BUNDLE_SUFFIX", "BundleCodec", "safe_member_path", "export_bundle",
           "import_bundle", "bundle_path", "write_bundle", "read_bundle"]
