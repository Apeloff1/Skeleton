"""Explicit no-overwrite private export for an operator-approved Jeeves Git patch.

The model never calls this API. A human reviews the COMPLETE patch and
approves its 64-character SHA-256 before publication to a new 0600 regular
file under a separate, preexisting, owner-private 0700 directory.

The original project tree remains read-only. The export does not call Git,
execute generated code, alter permissions, stage the index, create a branch,
or apply a patch. Failed source revalidation cannot silently produce a
success receipt or auto-reissue a patch.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    SpineError,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import (
    open_private_root,
)
from .desktop_patch_bundle import (
    MAX_PATCH_BYTES, PatchBundleHold, PortablePatchPlan,
    get_reviewed_patch, revalidate_live_sources,
)

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.patch\Z")
_PRIVATE_FILE_MODE = 0o600
_PRIVATE_DIR_MODE = 0o700


class PatchExportHold(ValueError):
    """A source patch cannot be exported without exact private operator consent."""


def _is_sha(digest: object) -> bool:
    return (
        type(digest) is str and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest)
    )


def _selected_target(value: str | Path, *, source_root: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise PatchExportHold("explicit absolute patch path required")
    path = Path(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or "\x00" in str(path)
        or not _NAME.fullmatch(path.name)
    ):
        raise PatchExportHold("private patch name/path untrusted")
    workspace = Path(source_root)
    if (
        path.is_relative_to(workspace)
        or workspace.is_relative_to(path.parent)
    ):
        raise PatchExportHold(
            "Git patch export must be outside original source project tree",
        )
    return path


def _pinned_private_directory(path: Path) -> int:
    try:
        fd = open_private_root(path.parent)
    except (SpineError, OSError, ValueError) as exc:
        raise PatchExportHold("private patch parent is not owner-controlled 0700") from exc
    try:
        st = os.fstat(fd)
        selected = os.stat(path.parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != os.getuid()
            or st.st_mode & 0o077
            or st.st_nlink < 1
            or (selected.st_dev, selected.st_ino) != (st.st_dev, st.st_ino)
        ):
            raise PatchExportHold("private patch parent changed or became shared")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _identical_parent(path: Path, fd: int) -> None:
    st = os.fstat(fd)
    current = os.stat(path.parent, follow_symlinks=False)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (st.st_dev, st.st_ino) != (current.st_dev, current.st_ino)
        or st.st_uid != current.st_uid
        or current.st_mode & 0o077
    ):
        raise PatchExportHold("operator private export parent replaced")


def _trusted_file(st: os.stat_result, *, byte_count: int) -> None:
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_uid != os.getuid()
        or st.st_mode & 0o077
        or st.st_nlink != 1
        or st.st_size != byte_count
        or not 1 <= st.st_size <= MAX_PATCH_BYTES
    ):
        raise PatchExportHold("exported patch is not a private bounded source file")


def _read_exact(fd: int, *, expected_bytes: int) -> bytes:
    before = os.fstat(fd)
    _trusted_file(before, byte_count=expected_bytes)
    os.lseek(fd, 0, os.SEEK_SET)
    read = bytearray()
    while len(read) < expected_bytes + 1:
        part = os.read(fd, min(16384, expected_bytes + 1 - len(read)))
        if not part:
            break
        read.extend(part)
    after = os.fstat(fd)
    if (
        len(read) != expected_bytes
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or (before.st_size, before.st_mtime_ns)
        != (after.st_size, after.st_mtime_ns)
    ):
        raise PatchExportHold("patch bytes changed during private readback")
    return bytes(read)


def export_reviewed_patch(
    plan: PortablePatchPlan,
    target: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_patch_sha256: str,
    approve_export: bool,
) -> dict[str, object]:
    """One explicit no-clobber publication of already reviewed Git patch bytes."""
    if (
        type(plan) is not PortablePatchPlan
        or approve_export is not True
        or not _is_sha(expected_manifest_sha256)
        or not _is_sha(expected_patch_sha256)
        or expected_manifest_sha256 != plan.manifest_sha256
        or expected_patch_sha256 != plan.patch_sha256
    ):
        raise PatchExportHold("exact reviewed manifest/patch digests and consent required")
    path = _selected_target(target, source_root=plan.root)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PatchExportHold("POSIX/WSL2 descriptor-rooted patch export required")
    # A supported format with malformed Python/JSON/TOML is a build
    # blocker, not a legitimate patch that should reach Git. Unsupported
    # languages remain clearly labeled UNVERIFIED and never become passes.
    from .desktop_source_qualification import (
        StaticSourceHold, require_parseable_patch,
    )
    try:
        static = require_parseable_patch(plan)
        from .desktop_source_graph import analyze_python_source_graph
        graph = analyze_python_source_graph(plan)
        patch = get_reviewed_patch(plan)
    except (OSError, ValueError, PatchBundleHold, StaticSourceHold) as exc:
        raise PatchExportHold("original source changed since operator review") from exc
    if (
        len(patch) != plan.patch_bytes
        or sha256(patch).hexdigest() != expected_patch_sha256
    ):
        raise PatchExportHold("patch bytes changed before publication")
    root_fd = _pinned_private_directory(path)
    file_fd = None
    created_identity = None
    try:
        _identical_parent(path, root_fd)
        file_fd = os.open(
            path.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=root_fd,
        )
        created = os.fstat(file_fd)
        created_identity = (created.st_dev, created.st_ino)
        # Source bytes are inert data; never give the exported patch an
        # executable bit, even if the extension in a proposed file is .sh.
        if (
            not stat.S_ISREG(created.st_mode)
            or created.st_uid != os.getuid()
            or created.st_mode & 0o077
            or created.st_nlink != 1
        ):
            raise PatchExportHold("new patch is not owner-private 0600")
        written = 0
        while written < len(patch):
            count = os.write(file_fd, patch[written:written + 16384])
            if type(count) is not int or count <= 0:
                raise PatchExportHold("short private patch publication")
            written += count
        os.fsync(file_fd)
        verify = _read_exact(file_fd, expected_bytes=len(patch))
        if sha256(verify).hexdigest() != expected_patch_sha256:
            raise PatchExportHold("private patch differs from reviewed source bytes")
        final = os.fstat(file_fd)
        check = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        if (
            (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
            != (check.st_dev, check.st_ino, check.st_size, check.st_mtime_ns)
        ):
            raise PatchExportHold("private patch path changed during publication")
        _identical_parent(path, root_fd)
        # Reinspect the exact source project again after writing the private
        # patch, before reporting it as a current reviewed source snapshot.
        revalidate_live_sources(plan)
        os.fsync(root_fd)
        return {
            "schema": "jeeves.workspace.private-git-patch-export.v1",
            "status": "new-private-patch-published-no-source-changes",
            "manifest_sha256": plan.manifest_sha256,
            "patch_sha256": expected_patch_sha256,
            "bytes": len(patch),
            "file_count": len(plan.entries),
            "new_files": sum(e.kind == "new" for e in plan.entries),
            "existing_edits": sum(e.kind == "edit" for e in plan.entries),
            "private_file_mode": "0600",
            "project_files_modified": False,
            "git_index_modified": False,
            "patch_applied": False,
            "static_source_status": static.status,
            "python_source_graph_sha256": graph.graph_sha256,
            "python_source_graph_status": graph.status,
            "linked_reviewed_python_imports": graph.linked_import_count,
            "unverified_python_imports": graph.unverified_import_count,
            "observed_python_cycles": len(graph.cycles),
            "parse_clean_count": sum(
                f.status == "parse-clean" for f in static.files
            ),
            "unverified_source_count": sum(
                f.status == "unverified" for f in static.files
            ),
            "source_code_executed": False,
            "model_authorized_file_write": False,
            "release_certified": False,
        }
    except BaseException:
        # If any publication stage failed, only delete the exact file inode
        # created by this operation. Never unlink an unrelated replacement.
        if created_identity is not None:
            try:
                st = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
                if (st.st_dev, st.st_ino) == created_identity:
                    os.unlink(path.name, dir_fd=root_fd)
                    os.fsync(root_fd)
            except OSError:
                pass
        raise
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(root_fd)


def verify_saved_patch(
    source: str | Path,
    *,
    expected_patch_sha256: str,
    expected_bytes: int,
    workspace_root: str | Path,
) -> dict[str, object]:
    """Verify exact previously exported private patch without applying it."""
    if (
        not _is_sha(expected_patch_sha256)
        or type(expected_bytes) is not int
        or not 1 <= expected_bytes <= MAX_PATCH_BYTES
    ):
        raise PatchExportHold("explicit finite patch hash/byte count required")
    workspace = Path(workspace_root)
    if not workspace.is_absolute() or ".." in workspace.parts:
        raise PatchExportHold("canonical original workspace required")
    path = _selected_target(source, source_root=str(workspace))
    root_fd = _pinned_private_directory(path)
    opened = None
    try:
        _identical_parent(path, root_fd)
        opened = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd,
        )
        payload = _read_exact(opened, expected_bytes=expected_bytes)
        fstat = os.fstat(opened)
        current = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        if (fstat.st_dev, fstat.st_ino) != (current.st_dev, current.st_ino):
            raise PatchExportHold("private saved source patch replaced")
        _identical_parent(path, root_fd)
        digest = sha256(payload).hexdigest()
        if digest != expected_patch_sha256:
            raise PatchExportHold("saved patch differs from explicitly approved bytes")
        return {
            "schema": "jeeves.workspace.private-git-patch-inspection.v1",
            "status": "verified-inert-source-patch",
            "patch_sha256": digest,
            "bytes": expected_bytes,
            "private_file_mode": "0600",
            "patch_applied": False,
            "project_files_modified": False,
            "release_certified": False,
        }
    finally:
        if opened is not None:
            os.close(opened)
        os.close(root_fd)


__all__ = [
    "PatchExportHold", "export_reviewed_patch", "verify_saved_patch",
]
