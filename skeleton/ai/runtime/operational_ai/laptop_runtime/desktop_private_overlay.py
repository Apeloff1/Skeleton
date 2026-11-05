"""Descriptor-anchored private preview overlay for reviewed local Jeeves code.

This is an operational bridge beyond inert Git patch export: an operator can
stage the ACTUAL final new/edited source files in a brand-new private directory
for standalone inspection, copying or a separately authorized review process.
It NEVER edits the original checkout, runs model-written code, uses Git, or
claims the overlay is an independently working whole repository.

An exact complete seal, written LAST, means every listed staged file was
verified against the reviewed original model output. Missing or partial stages
remain visibly incomplete; no rollback can delete an attacker replacement.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .desktop_patch_bundle import (
    PortablePatchPlan, PatchBundleHold,
    get_reviewed_patch, revalidate_live_sources,
)
from .desktop_patch_export import (
    PatchExportHold, _pinned_private_directory, _identical_parent, _read_exact,
)
from .desktop_source_qualification import (
    StaticSourceHold, require_parseable_patch,
)
from .desktop_workspace import _canonical, _relative

SCHEMA = "jeeves.workspace.private-source-overlay.v1"
SEAL_SCHEMA = "jeeves.workspace.private-source-overlay-seal.v1"
MAX_FILES = 24
MAX_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 16384
STAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


class SourceOverlayHold(ValueError):
    """Private change preview cannot be trusted or unambiguously published."""


def _sha(value: bytes) -> str:
    return sha256(value).hexdigest()


def _digest(value: object) -> bool:
    return (
        type(value) is str and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _stage_target(destination: str | Path, original_root: str) -> Path:
    if not isinstance(destination, (str, Path)):
        raise SourceOverlayHold("explicit absolute private overlay directory required")
    path = Path(destination)
    workspace = Path(original_root)
    if (
        not path.is_absolute() or ".." in path.parts
        or "\x00" in str(path) or not STAGE_NAME.fullmatch(path.name)
        or path.is_relative_to(workspace) or workspace.is_relative_to(path)
    ):
        raise SourceOverlayHold("stage must be a new private directory outside project")
    return path


def _trusted_directory(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_ino < 1
    ):
        raise SourceOverlayHold("stage directory is not a private owner-controlled inode")
    return info


def _open_directory(parent: int, name: str) -> int:
    fd = os.open(name, DIR_FLAGS, dir_fd=parent)
    try:
        info = _trusted_directory(fd)
        linked = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(linked.st_mode)
            or (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino)
        ):
            raise SourceOverlayHold("stage directory replaced during descriptor walk")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _stage_directory(root_fd: int, components: tuple[str, ...], *, create: bool) -> int:
    current = os.dup(root_fd)
    try:
        for component in components:
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
            following = _open_directory(current, component)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _write_private(directory_fd: int, leaf: str, content: bytes) -> None:
    if not 1 <= len(content) <= MAX_BYTES:
        raise SourceOverlayHold("staged source exceeds finite original byte envelope")
    handle = os.open(leaf, WRITE_FLAGS, 0o600, dir_fd=directory_fd)
    try:
        info = os.fstat(handle)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or info.st_nlink != 1
        ):
            raise SourceOverlayHold("new staged source has unsafe ownership/permissions")
        written = 0
        while written < len(content):
            amount = os.write(handle, content[written:written + 16384])
            if type(amount) is not int or amount <= 0:
                raise SourceOverlayHold("partial private preview source write")
            written += amount
        os.fsync(handle)
        # The file descriptor is opened write-only; reopen through its
        # immutable directory and compare exact bytes before acceptance.
        chk = os.open(leaf, READ_FLAGS, dir_fd=directory_fd)
        try:
            actual = _read_exact(chk, expected_bytes=len(content))
            if _sha(actual) != _sha(content):
                raise SourceOverlayHold("private preview file changed during staging")
            reopened = os.fstat(chk)
            if (reopened.st_dev, reopened.st_ino) != (info.st_dev, info.st_ino):
                raise SourceOverlayHold("staged preview file was replaced during write")
        finally:
            os.close(chk)
        os.fsync(directory_fd)
    finally:
        os.close(handle)


def _canonical_json(raw: bytes, ceiling: int) -> dict:
    if not 1 <= len(raw) <= ceiling:
        raise SourceOverlayHold("finite canonical source-overlay record required")
    def pairs(items):
        selected = {}
        for key, val in items:
            if key in selected:
                raise SourceOverlayHold("ambiguous duplicate preview manifest field")
            selected[key] = val
        return selected
    def reject_nonfinite(value):
        raise SourceOverlayHold("nonfinite private source manifest number")
    try:
        data = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs, parse_constant=reject_nonfinite,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SourceOverlayHold("invalid canonical private source overlay JSON") from exc
    if type(data) is not dict or _canonical(data) != raw:
        raise SourceOverlayHold("noncanonical private stage record")
    return data


def _record(plan: PortablePatchPlan, qualification) -> dict:
    from .desktop_source_graph import analyze_python_source_graph
    graph = analyze_python_source_graph(plan)
    if not graph.permits_inert_export:
        raise SourceOverlayHold("invalid original Python import graph cannot stage")
    return {
        "schema": SCHEMA,
        "manifest_sha256": plan.manifest_sha256,
        "patch_sha256": plan.patch_sha256,
        "static_source_status": qualification.status,
        "python_source_graph_sha256": graph.graph_sha256,
        "python_source_graph_status": graph.status,
        "linked_reviewed_python_imports": graph.linked_import_count,
        "unverified_python_imports": graph.unverified_import_count,
        "observed_python_cycles": len(graph.cycles),
        "file_count": len(plan.entries),
        "total_source_bytes": sum(x.replacement_bytes for x in plan.entries),
        "files": [{
            "path": item.path,
            "kind": item.kind,
            "original_sha256": item.original_sha256,
            "replacement_sha256": item.replacement_sha256,
            "bytes": item.replacement_bytes,
        } for item in plan.entries],
        "original_checkout_modified": False,
        "source_code_executed": False,
        "git_index_modified": False,
        "release_certified": False,
    }


def _seal(meta: bytes) -> bytes:
    return _canonical({
        "schema": SEAL_SCHEMA,
        "metadata_sha256": _sha(meta),
        "metadata_bytes": len(meta),
        "complete_private_source_snapshot": True,
        "original_checkout_modified": False,
        "source_code_executed": False,
        "release_certified": False,
    })


def _require_manifest(value: dict, manifest: str, patch: str) -> list[dict]:
    if type(value) is not dict or set(value) != {
        "schema", "manifest_sha256", "patch_sha256",
        "static_source_status", "file_count", "total_source_bytes",
        "python_source_graph_sha256", "python_source_graph_status",
        "linked_reviewed_python_imports", "unverified_python_imports",
        "observed_python_cycles",
        "files", "original_checkout_modified", "source_code_executed",
        "git_index_modified", "release_certified",
    }:
        raise SourceOverlayHold("source manifest has unexpected authority")
    if (
        value["schema"] != SCHEMA or value["manifest_sha256"] != manifest
        or value["patch_sha256"] != patch
        or value["static_source_status"] not in ("parse-clean", "mixed-unverified")
        or not _digest(value["python_source_graph_sha256"])
        or value["python_source_graph_status"] not in (
            "no-python-source", "observed-internal-imports",
            "partially-unverified-imports",
        )
        or any(
            type(value[name]) is not int or not 0 <= value[name] <= 1024
            for name in (
                "linked_reviewed_python_imports",
                "unverified_python_imports", "observed_python_cycles",
            )
        )
        or type(value["file_count"]) is not int
        or type(value["total_source_bytes"]) is not int
        or value["original_checkout_modified"] is not False
        or value["source_code_executed"] is not False
        or value["git_index_modified"] is not False
        or value["release_certified"] is not False
        or type(value["files"]) is not list
        or len(value["files"]) != value["file_count"]
        or not 1 <= len(value["files"]) <= MAX_FILES
    ):
        raise SourceOverlayHold("unverified private stage evidence")
    seen = set()
    total = 0
    for row in value["files"]:
        if type(row) is not dict or set(row) != {
            "path", "kind", "original_sha256", "replacement_sha256", "bytes",
        }:
            raise SourceOverlayHold("untrusted original source file inventory")
        try:
            _relative(row["path"])
        except (ValueError, TypeError, PatchBundleHold) as exc:
            raise SourceOverlayHold("invalid staged original source path") from exc
        if (
            row["kind"] not in ("new", "edit")
            or (row["kind"] == "new") != (row["original_sha256"] is None)
            or (row["original_sha256"] is not None and not _digest(row["original_sha256"]))
            or not _digest(row["replacement_sha256"])
            or type(row["bytes"]) is not int
            or not 1 <= row["bytes"] <= MAX_BYTES
            or row["path"].casefold() in seen
        ):
            raise SourceOverlayHold("staged original source receipt is not exact")
        seen.add(row["path"].casefold())
        total += row["bytes"]
    if total != value["total_source_bytes"] or not 1 <= total <= MAX_BYTES:
        raise SourceOverlayHold("private staged source aggregate bytes over bound")
    if [row["path"] for row in value["files"]] != sorted(
        [row["path"] for row in value["files"]], key=lambda x: (x.casefold(), x),
    ):
        raise SourceOverlayHold("original source manifest order differs")
    return value["files"]


def _read_private(dir_fd: int, leaf: str, length: int | None, *, ceiling: int = MAX_METADATA_BYTES) -> bytes:
    opened = os.open(leaf, READ_FLAGS, dir_fd=dir_fd)
    try:
        first = os.fstat(opened)
        if length is None:
            if (
                not stat.S_ISREG(first.st_mode)
                or not 1 <= first.st_size <= ceiling
            ):
                raise SourceOverlayHold("unbounded preview manifest/seal byte count")
            length = first.st_size
        try:
            return _read_exact(opened, expected_bytes=length)
        except PatchExportHold as exc:
            raise SourceOverlayHold(
                "stored source overlay has unsafe mode, hardlinks or changed bytes",
            ) from exc
    finally:
        os.close(opened)


def _entry_tree(root_fd: int, listed: list[dict]) -> None:
    """Verify all expected descriptors and reject unexpected extra files."""
    expected_dirs = {""}
    expected_files = {"manifest.json", "seal.json"}
    for row in listed:
        parts = _relative(row["path"])
        prefix = "changes"
        expected_dirs.add(prefix)
        for component in parts[:-1]:
            prefix += "/" + component
            expected_dirs.add(prefix)
        expected_files.add("changes/" + row["path"])
        parent = _stage_directory(root_fd, ("changes", *parts[:-1]), create=False)
        try:
            actual = _read_private(parent, parts[-1], row["bytes"])
            if _sha(actual) != row["replacement_sha256"]:
                raise SourceOverlayHold("staged replacement differs from reviewed source")
        finally:
            os.close(parent)
    pending = [(os.dup(root_fd), "")]
    actual_dirs = set()
    actual_files = set()
    try:
        visited = 0
        while pending:
            opened, prefix = pending.pop()
            try:
                _trusted_directory(opened)
                actual_dirs.add(prefix[:-1] if prefix else "")
                names = os.listdir(opened)
                if len(names) > 128:
                    raise SourceOverlayHold("stage contains unbounded extra entries")
                for leaf in names:
                    visited += 1
                    if visited > 256:
                        raise SourceOverlayHold("stage exceeds finite file inventory")
                    relative = prefix + leaf
                    info = os.stat(leaf, dir_fd=opened, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        if relative not in expected_dirs:
                            raise SourceOverlayHold("unapproved directory inside private preview")
                        child = _open_directory(opened, leaf)
                        pending.append((child, relative + "/"))
                    else:
                        if relative not in expected_files or not stat.S_ISREG(info.st_mode):
                            raise SourceOverlayHold("unapproved private preview payload")
                        actual_files.add(relative)
                        if (
                            info.st_uid != os.getuid()
                            or info.st_nlink != 1
                            or info.st_mode & 0o077
                        ):
                            raise SourceOverlayHold("unexpected private preview file mode/link")
            finally:
                os.close(opened)
        if actual_dirs != expected_dirs or actual_files != expected_files:
            raise SourceOverlayHold("incomplete private source overlay filetree")
    finally:
        for handle, _ in pending:
            os.close(handle)


def _stage_verify(
    stage_fd: int, *, expected_manifest_sha256: str,
    expected_patch_sha256: str,
) -> dict:
    _trusted_directory(stage_fd)
    # Read only the actual descriptor size, and enforce a finite upper
    # bound before allocating. A fixed-length read would spuriously reject
    # legitimate shorter canonical metadata.
    manifest_raw = _read_private(stage_fd, "manifest.json", None)
    metadata = _canonical_json(manifest_raw, MAX_METADATA_BYTES)
    listed = _require_manifest(
        metadata, expected_manifest_sha256, expected_patch_sha256,
    )
    seal_bytes = _seal(manifest_raw)
    actual_seal = _read_private(stage_fd, "seal.json", len(seal_bytes))
    if actual_seal != seal_bytes:
        raise SourceOverlayHold("private change tree is incomplete or seal mismatched")
    _entry_tree(stage_fd, listed)
    return {
        "schema": "jeeves.workspace.private-source-overlay-inspection.v1",
        "status": "complete-private-source-overlay-snapshot",
        "manifest_sha256": expected_manifest_sha256,
        "patch_sha256": expected_patch_sha256,
        "metadata_sha256": _sha(manifest_raw),
        "file_count": len(listed),
        "total_source_bytes": metadata["total_source_bytes"],
        "static_source_status": metadata["static_source_status"],
        "python_source_graph_sha256": metadata["python_source_graph_sha256"],
        "python_source_graph_status": metadata["python_source_graph_status"],
        "linked_reviewed_python_imports": metadata["linked_reviewed_python_imports"],
        "unverified_python_imports": metadata["unverified_python_imports"],
        "observed_python_cycles": metadata["observed_python_cycles"],
        "graph_reparsed_on_cold_reopen": False,
        "original_checkout_modified": False,
        "source_code_executed": False,
        "git_index_modified": False,
        "model_source_write_authorized": False,
        "release_certified": False,
    }


def verify_staged_overlay(
    stage: str | Path, *,
    expected_manifest_sha256: str,
    expected_patch_sha256: str,
    workspace_root: str | Path,
) -> dict[str, object]:
    """Cold-reopen exact private stage bytes; no original code execution."""
    if not _digest(expected_manifest_sha256) or not _digest(expected_patch_sha256):
        raise SourceOverlayHold("complete reviewed source/patch SHA-256 required")
    stage_path = _stage_target(stage, str(workspace_root))
    parent = _pinned_private_directory(stage_path)
    opened = None
    try:
        _identical_parent(stage_path, parent)
        opened = _open_directory(parent, stage_path.name)
        info = os.fstat(opened)
        linked = os.stat(stage_path, follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino):
            raise SourceOverlayHold("private preview stage replaced")
        verified = _stage_verify(
            opened,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_patch_sha256=expected_patch_sha256,
        )
        _identical_parent(stage_path, parent)
        return verified
    finally:
        if opened is not None:
            os.close(opened)
        os.close(parent)


def stage_reviewed_overlay(
    plan: PortablePatchPlan, stage: str | Path, *,
    expected_manifest_sha256: str,
    expected_patch_sha256: str,
    approve_staging: bool,
) -> dict[str, object]:
    """Explicit no-clobber, no-run preview of exact new and replaced source."""
    if (
        type(plan) is not PortablePatchPlan
        or approve_staging is not True
        or not _digest(expected_manifest_sha256)
        or not _digest(expected_patch_sha256)
        or expected_manifest_sha256 != plan.manifest_sha256
        or expected_patch_sha256 != plan.patch_sha256
    ):
        raise SourceOverlayHold("entire source manifest, patch SHA and consent required")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise SourceOverlayHold("private preview stage requires POSIX/WSL2 descriptors")
    stage_path = _stage_target(stage, plan.root)
    try:
        static = require_parseable_patch(plan)
        get_reviewed_patch(plan)
        revalidate_live_sources(plan)
    except (ValueError, PatchBundleHold, StaticSourceHold, OSError) as exc:
        raise SourceOverlayHold("source changed or contains invalid supported syntax") from exc
    source_total = sum(x.replacement_bytes for x in plan.entries)
    if not 1 <= source_total <= MAX_BYTES:
        raise SourceOverlayHold("source overlay size exceeds 1 MiB private cap")
    metadata = _canonical(_record(plan, static))
    if len(metadata) > MAX_METADATA_BYTES:
        raise SourceOverlayHold("finite metadata record exceeded")
    _require_manifest(
        _canonical_json(metadata, MAX_METADATA_BYTES),
        expected_manifest_sha256, expected_patch_sha256,
    )
    parent = _pinned_private_directory(stage_path)
    stage_fd = None
    try:
        _identical_parent(stage_path, parent)
        os.mkdir(stage_path.name, 0o700, dir_fd=parent)
        stage_fd = _open_directory(parent, stage_path.name)
        _trusted_directory(stage_fd)
        for entry in plan.entries:
            parts = _relative(entry.path)
            directory = _stage_directory(
                stage_fd, ("changes", *parts[:-1]), create=True,
            )
            try:
                raw = entry.replacement_text.encode("utf-8", "strict")
                if _sha(raw) != entry.replacement_sha256:
                    raise SourceOverlayHold("staged proposed source differs from review")
                _write_private(directory, parts[-1], raw)
            finally:
                os.close(directory)
        _write_private(stage_fd, "manifest.json", metadata)
        revalidate_live_sources(plan)
        _identical_parent(stage_path, parent)
        # Seal is written LAST: an interrupted or stale source run can never
        # accidentally qualify a partial stage as a complete source package.
        _write_private(stage_fd, "seal.json", _seal(metadata))
        os.fsync(stage_fd)
        os.fsync(parent)
        result = _stage_verify(
            stage_fd, expected_manifest_sha256=plan.manifest_sha256,
            expected_patch_sha256=plan.patch_sha256,
        )
        _identical_parent(stage_path, parent)
        return {
            **result,
            "status": "new-private-overlay-staged-without-source-writes",
            "stage_created": True,
            "source_files_staged": len(plan.entries),
            "complete_marker_verified": True,
            "automatic_project_activation": False,
            "manual_operator_checkout_review_required": True,
        }
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent)


__all__ = [
    "SCHEMA", "SEAL_SCHEMA", "MAX_FILES", "MAX_BYTES",
    "SourceOverlayHold", "stage_reviewed_overlay", "verify_staged_overlay",
]
