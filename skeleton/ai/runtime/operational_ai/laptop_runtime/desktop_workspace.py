"""No-clobber source delivery from a reviewed Jeeves answer into a local tree.

The GGUF model proposes *data*. A human selects a private workspace root,
reviews a finite manifest and explicitly approves ONE new source file at a
time. The model cannot invoke this module, gain a shell, overwrite existing
files, follow symlinks, traverse parent directories or install executables.

Only POSIX/WSL2 descriptor-anchored creation is currently supported.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import difflib
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

SCHEMA = "jeeves.workspace.new-files.v1"
MAX_MANIFEST_BYTES = 262144
MAX_FILES = 16
MAX_FILE_BYTES = 99000
MAX_AGGREGATE_BYTES = 196608
MAX_PREVIEW_BYTES = 65536
_ALLOWED = frozenset({
    ".py", ".pyi", ".md", ".rst", ".txt", ".json", ".toml", ".yaml", ".yml",
    ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".sql", ".go", ".rs",
    ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".rb", ".sh",
    ".ps1", ".xml", ".ini", ".cfg",
})
_BLOCK_PARTS = frozenset({
    ".git", ".github", ".hg", ".svn", ".ssh", ".gnupg",
    ".vscode", ".idea", ".devcontainer", "node_modules",
    "__pycache__", ".venv", "venv", "secrets", "credentials",
})


class WorkspaceDeliveryHold(ValueError):
    """Source proposal is not a safe explicit no-overwrite file creation."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise WorkspaceDeliveryHold("invalid UTF-8 source manifest") from exc


def _unique(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise WorkspaceDeliveryHold("duplicate source proposal key")
        result[key] = value
    return result


def _constant(_):
    raise WorkspaceDeliveryHold("nonfinite source proposal number")


def _relative(name: object) -> tuple[str, ...]:
    if type(name) is not str or not 1 <= len(name) <= 256 or "\\" in name:
        raise WorkspaceDeliveryHold("invalid relative source destination")
    if name.startswith("/") or "\x00" in name:
        raise WorkspaceDeliveryHold("absolute or NUL source destination")
    parts = name.split("/")
    if any(
        not item or item in (".", "..") or item.lower() in _BLOCK_PARTS
        or item.startswith(".jeeves-stage-")
        or not item.isascii()
        or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for ch in item)
        for item in parts
    ):
        raise WorkspaceDeliveryHold("untrusted source path component")
    if Path(parts[-1]).suffix.lower() not in _ALLOWED:
        raise WorkspaceDeliveryHold("unsupported source-only file extension")
    if parts[:2] == [".github", "workflows"]:
        raise WorkspaceDeliveryHold("model text cannot publish workflow authority")
    return tuple(parts)


def _source(content: object) -> bytes:
    if type(content) is not str or "\x00" in content:
        raise WorkspaceDeliveryHold("source text must be exact UTF-8")
    try:
        raw = content.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise WorkspaceDeliveryHold("invalid source text Unicode") from exc
    if not 1 <= len(raw) <= MAX_FILE_BYTES:
        raise WorkspaceDeliveryHold("proposed source file exceeds byte ceiling")
    return raw


@dataclass(frozen=True, slots=True)
class ProposedFile:
    path: str
    text: str
    sha256: str
    bytes: int

    def __post_init__(self):
        _relative(self.path)
        raw = _source(self.text)
        if (
            type(self.bytes) is not int or self.bytes != len(raw)
            or type(self.sha256) is not str
            or self.sha256 != sha256(raw).hexdigest()
        ):
            raise WorkspaceDeliveryHold("unverified source proposal byte identity")


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    root: str
    root_device: int
    root_inode: int
    manifest_sha256: str
    entries: tuple[ProposedFile, ...]

    def __post_init__(self):
        if (type(self.root) is not str or not Path(self.root).is_absolute()
                or ".." in Path(self.root).parts or "\x00" in self.root):
            raise WorkspaceDeliveryHold("workspace root path not canonical")
        if (
            type(self.root_device) is not int or self.root_device < 0
            or type(self.root_inode) is not int or self.root_inode < 1
        ):
            raise WorkspaceDeliveryHold("workspace root descriptor identity required")
        if type(self.entries) is not tuple or not 1 <= len(self.entries) <= MAX_FILES:
            raise WorkspaceDeliveryHold("finite typed source plan required")
        if any(type(item) is not ProposedFile for item in self.entries):
            raise WorkspaceDeliveryHold("source plan must contain verified files")
        if sum(item.bytes for item in self.entries) > MAX_AGGREGATE_BYTES:
            raise WorkspaceDeliveryHold("aggregated proposed source exceeds bound")
        if len({item.path.casefold() for item in self.entries}) != len(self.entries):
            raise WorkspaceDeliveryHold("duplicate or case-clashing source destinations")
        if self.manifest_sha256 != _plan_digest(self.entries):
            raise WorkspaceDeliveryHold("reviewed source manifest digest changed")


def _plan_digest(entries: tuple[ProposedFile, ...]) -> str:
    return sha256(_canonical({
        "schema": SCHEMA,
        "files": [{"path": e.path, "content": e.text} for e in entries],
    })).hexdigest()


def _open_root(root: str) -> int:
    from skeleton.ai.runtime.operational_ai.model.gguf.file_guard import open_trusted_root

    if os.name != "posix" or not hasattr(os, "getuid"):
        raise WorkspaceDeliveryHold("POSIX nofollow workspace publication required")
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts or "\x00" in root:
        raise WorkspaceDeliveryHold("absolute canonical private workspace required")
    fd = open_trusted_root(path)
    info = os.fstat(fd)
    if (info.st_uid != os.getuid() or info.st_mode & 0o022
            or not stat.S_ISDIR(info.st_mode)):
        os.close(fd)
        raise WorkspaceDeliveryHold("untrusted workspace owner or permissions")
    return fd


def _parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative(relative)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0), dir_fd=fd,
            )
            os.close(fd)
            fd = next_fd
            st = os.fstat(fd)
            if st.st_uid != os.getuid() or st.st_mode & 0o022:
                raise WorkspaceDeliveryHold("untrusted or writable source parent")
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _absent(parent_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise WorkspaceDeliveryHold("proposed destination already exists; overwrite forbidden")


def parse_plan(raw: str | bytes, root: str | Path) -> WorkspacePlan:
    """Review model-generated bytes as untrusted data; no writes occur here."""
    if type(raw) is str:
        data = raw.encode("utf-8", "strict")
    elif type(raw) is bytes:
        data = raw
    else:
        raise WorkspaceDeliveryHold("bounded JSON source proposal required")
    if not 2 <= len(data) <= MAX_MANIFEST_BYTES:
        raise WorkspaceDeliveryHold("source proposal outside finite byte limit")
    try:
        doc = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_unique,
            parse_constant=_constant,
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise WorkspaceDeliveryHold("invalid strict source proposal JSON") from exc
    if type(doc) is not dict or set(doc) != {"schema", "files"} or doc["schema"] != SCHEMA:
        raise WorkspaceDeliveryHold("unknown or unapproved source proposal schema")
    rows = doc["files"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILES:
        raise WorkspaceDeliveryHold("bounded nonempty proposed file list required")
    entries = []
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "content"}:
            raise WorkspaceDeliveryHold("unexpected proposed source file fields")
        name = row["path"]
        text = row["content"]
        _relative(name)
        encoded = _source(text)
        entries.append(ProposedFile(name, text, sha256(encoded).hexdigest(), len(encoded)))
    files = tuple(entries)
    if len({f.path.casefold() for f in files}) != len(files):
        raise WorkspaceDeliveryHold("source proposal path collision")
    root_path = Path(root)
    if not root_path.is_absolute() or ".." in root_path.parts:
        raise WorkspaceDeliveryHold("absolute workspace root required")
    anchored = _open_root(str(root_path))
    try:
        root_stat = os.fstat(anchored)
        for item in files:
            directory, name = _parent(anchored, item.path)
            try:
                _absent(directory, name)
            finally:
                os.close(directory)
        return WorkspacePlan(
            root=str(root_path), root_device=root_stat.st_dev,
            root_inode=root_stat.st_ino,
            manifest_sha256=_plan_digest(files), entries=files,
        )
    finally:
        os.close(anchored)


def preview_file(plan: WorkspacePlan, index: int) -> dict[str, object]:
    if not isinstance(plan, WorkspacePlan) or type(index) is not int:
        raise WorkspaceDeliveryHold("verified source plan and index required")
    if not 0 <= index < len(plan.entries):
        raise WorkspaceDeliveryHold("source file index outside reviewed proposal")
    item = plan.entries[index]
    lines = list(difflib.unified_diff(
        [], item.text.splitlines(keepends=True),
        fromfile="/dev/null", tofile=item.path,
        lineterm="\n",
    ))
    patch = "".join(lines)
    if len(patch.encode("utf-8", "strict")) > MAX_PREVIEW_BYTES:
        patch = "[Diff too large for preview; source bytes remain bounded]\n"
    return {
        "schema": "jeeves.workspace.review.v1",
        "path": item.path,
        "bytes": item.bytes,
        "sha256": item.sha256,
        "manifest_sha256": plan.manifest_sha256,
        "diff": patch,
        "review_required": True,
        "model_authorized_write": False,
    }


def _rename_no_replace(parent_fd: int, temporary: str, destination: str) -> None:
    """Linux/WSL2 renameat2 NOREPLACE: never fall back to os.replace."""
    library = ctypes.CDLL(None, use_errno=True)
    try:
        operation = library.renameat2
    except AttributeError as exc:
        raise WorkspaceDeliveryHold("atomic no-overwrite publication unsupported") from exc
    operation.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    if operation(
        parent_fd, os.fsencode(temporary),
        parent_fd, os.fsencode(destination), 1,
    ):
        raise WorkspaceDeliveryHold("atomic no-overwrite publication refused")


def publish_file(
    plan: WorkspacePlan, index: int, *,
    expected_manifest_sha256: str, expected_file_sha256: str,
    approved: bool,
) -> dict[str, object]:
    """Exactly one explicit human-approved new source file, no overwrite.

    A checked-out source tree may contain unrelated mutable files. We never
    run source code, modify other files, try to repair partial transactions
    or promise repository-wide atomicity. Every file needs a separate approval.
    """
    if approved is not True:
        raise WorkspaceDeliveryHold("operator approval required to publish source")
    if (not isinstance(plan, WorkspacePlan) or type(index) is not int
            or not 0 <= index < len(plan.entries)):
        raise WorkspaceDeliveryHold("reviewed finite source plan required")
    if (
        type(expected_manifest_sha256) is not str
        or expected_manifest_sha256 != plan.manifest_sha256
        or type(expected_file_sha256) is not str
        or expected_file_sha256 != plan.entries[index].sha256
    ):
        raise WorkspaceDeliveryHold("approved source digest differs from reviewed bytes")
    file = plan.entries[index]
    # Prove immutable plan identity again even if untrusted callers constructed
    # a dataclass rather than taking parse_plan's descriptor-checked output.
    plan.__post_init__()
    root_fd = _open_root(plan.root)
    try:
        root_info = os.fstat(root_fd)
        if (root_info.st_dev, root_info.st_ino) != (
            plan.root_device, plan.root_inode,
        ):
            raise WorkspaceDeliveryHold("workspace root changed since preview")
        parent_fd, name = _parent(root_fd, file.path)
        try:
            _absent(parent_fd, name)
            temporary = ".jeeves-stage-" + secrets.token_hex(16)
            staged = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600, dir_fd=parent_fd,
            )
            try:
                try:
                    payload = _source(file.text)
                    position = 0
                    while position < len(payload):
                        count = os.write(staged, payload[position:])
                        if count <= 0:
                            raise WorkspaceDeliveryHold("incomplete private source staging write")
                        position += count
                    os.fsync(staged)
                    info = os.fstat(staged)
                    if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                            or info.st_nlink != 1 or info.st_size != len(payload)):
                        raise WorkspaceDeliveryHold("staged file changed ownership or mode")
                finally:
                    os.close(staged)
                _absent(parent_fd, name)
                _rename_no_replace(parent_fd, temporary, name)
                os.fsync(parent_fd)
            finally:
                # Both a short staging write and an unsuccessful publication
                # must clean ONLY our random temporary file. Never unlink an
                # existing destination or roll back an uncertain prior write.
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            # Receipt is only for this exact new source file. A later external
            # mutation is outside this operation's ownership or guarantee.
            published = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd,
            )
            try:
                info = os.fstat(published)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_size != len(payload)
                    or info.st_nlink != 1 or info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                ):
                    raise WorkspaceDeliveryHold("published source final identity changed")
                raw = bytearray()
                while len(raw) < len(payload):
                    chunk = os.read(published, len(payload) - len(raw))
                    if not chunk:
                        break
                    raw.extend(chunk)
                if sha256(raw).hexdigest() != file.sha256:
                    raise WorkspaceDeliveryHold("published source differs from approved bytes")
            finally:
                os.close(published)
            return {
                "schema": "jeeves.workspace.publication.v1",
                "status": "one-new-file-atomically-published",
                "path": file.path,
                "bytes": file.bytes,
                "sha256": file.sha256,
                "manifest_sha256": plan.manifest_sha256,
                "other_files_modified": False,
                "native_model_performed_file_write": False,
                "release_certified": False,
            }
        finally:
            os.close(parent_fd)
    finally:
        os.close(root_fd)


__all__ = [
    "WorkspaceDeliveryHold", "ProposedFile", "WorkspacePlan",
    "parse_plan", "preview_file", "publish_file",
]
