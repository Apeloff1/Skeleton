"""Deterministic single-file bundle export/import.

The bundle is one JSON envelope: ``{manifest, sections, receipts}`` wrapped by
a save codec for integrity. ``skeleton`` does not import ``backend``, so the
codec and tenant namespace are injected through small Protocols; production
callers pass ``backend.core.save_envelope.SaveCodec(BUNDLE_SCHEMA_VERSION)``
and ``backend.core.tenant_storage_boundary.tenant_storage_namespace``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Protocol

from skeleton.ai.game_builder.game_project_workspace import PROJECT_MAX_FILES, SOURCE_MAX
from skeleton.kernel.game_save_plane import ChunkReceiptStore

from .manifest import BundleError, BundleManifest
from .project_save import BUNDLE_SECTIONS, ProjectSaver, build_state, files_from_state, manifest_for

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


def safe_member_path(path: str) -> str:
    """Reject zip-slip style member paths (absolute, traversal, backslash, hidden)."""
    if not isinstance(path, str) or not 1 <= len(path) <= 450 or "\\" in path or "\x00" in path:
        raise BundleError("unsafe bundle member path")
    pp = PurePosixPath(path)
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
    if len(raw.encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds size limit")
    return raw


def import_bundle(raw: str, codec: BundleCodec, saver: ProjectSaver, *,
                  sequence: int | None = None) -> BundleManifest:
    """Verify a bundle end to end, then save it as a new version in ``saver``."""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle missing or exceeds size limit")
    try:
        payload = codec.decode(raw).payload
    except ValueError as exc:  # SaveIntegrityError is a ValueError
        raise BundleError("bundle envelope failed integrity check") from exc
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
    receipts = ChunkReceiptStore.from_state(payload["receipts"])
    if receipts.root() != manifest.receipt_root:
        raise BundleError("receipt root mismatch")
    files = files_from_state(sections, receipts)
    if {p: e["sha256"] for p, e in sections["files"].items()} != manifest.file_map():
        raise BundleError("file digests disagree with manifest")
    check = manifest_for(sections, receipts, manifest.sequence, manifest.save_schema_version)
    if check.content_digest != manifest.content_digest:
        raise BundleError("manifest does not describe bundle content")
    extra = {k: v for k, v in sections.items() if k not in BUNDLE_SECTIONS}
    return saver.save_files(manifest.project_id, manifest.genre, files, sequence=sequence,
                            label=manifest.label, extra_sections=extra)


def bundle_path(base_dir: str | Path, tenant_id: str, project_id: str, namespace: NamespaceFn) -> Path:
    """``<base>/<tenant-fingerprint>/<purpose>/<project>.gfbundle.json``, contained in base."""
    ns = namespace(tenant_id, purpose="game_project_bundles")
    m = _NS.fullmatch(ns)
    if not m:
        raise BundleError("unexpected tenant namespace shape")
    base = Path(base_dir).resolve()
    rel = PurePosixPath(m.group(1), m.group(2).replace(":", "_"),
                        safe_member_path(project_id + BUNDLE_SUFFIX))
    target = (base / rel).resolve()
    if base not in target.parents:
        raise BundleError("bundle path escapes storage base")
    return target


def write_bundle(path: Path, raw: str) -> None:
    if len(raw.encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise BundleError("refusing to write through a symlink")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)


def read_bundle(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise BundleError("bundle must be a regular file")
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds size limit")
    return path.read_text(encoding="utf-8")


__all__ = ["MAX_BUNDLE_BYTES", "BUNDLE_SUFFIX", "BundleCodec", "safe_member_path", "export_bundle",
           "import_bundle", "bundle_path", "write_bundle", "read_bundle"]
