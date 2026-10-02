"""Filesystem jail: every path is confined to one root directory.

:class:`FsJail` resolves untrusted relative paths against its root and
refuses anything that would leave it — ``..`` traversal, absolute paths,
drive/UNC prefixes, NUL bytes, and symlinks (any component) pointing
outside.  Writes go through ``O_NOFOLLOW`` + atomic rename, are restricted
to regular files, and are charged against byte and file-count quotas.

The jail is a defence-in-depth layer for tools and generated code; it is
not a substitute for OS isolation (see :mod:`.process`).
"""
from __future__ import annotations

import os
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import FsPolicyError, PathEscapeError, QuotaExceededError

MAX_PATH_CHARS = 1024
MAX_COMPONENT_CHARS = 255
MAX_DEPTH = 32
_RESERVED_WIN = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})


@dataclass(frozen=True)
class JailPolicy:
    max_bytes: int = 64 * 1024 * 1024
    max_files: int = 4096
    max_file_bytes: int = 16 * 1024 * 1024
    allow_hidden: bool = False
    read_only: bool = False


def check_relative(path: str) -> PurePosixPath:
    """Lexically validate an untrusted relative path (no filesystem access)."""
    if not isinstance(path, str) or not path:
        raise FsPolicyError("path must be a non-empty string")
    if len(path) > MAX_PATH_CHARS:
        raise FsPolicyError("path too long", context={"maximum": MAX_PATH_CHARS})
    if "\x00" in path:
        raise PathEscapeError("path contains NUL")
    norm = unicodedata.normalize("NFKC", path).replace("\\", "/")
    if norm != path.replace("\\", "/"):
        # Fullwidth dots/slashes etc. normalise into traversal on some stacks.
        if ".." in norm or norm.startswith("/"):
            raise PathEscapeError("path uses lookalike traversal characters", context={"path": path[:120]})
    if norm.startswith("/") or norm.startswith("~") or (len(norm) > 1 and norm[1] == ":") or norm.startswith("//"):
        raise PathEscapeError("absolute paths are not allowed", context={"path": path[:120]})
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts:
        raise FsPolicyError("path resolves to the jail root")
    if len(parts) > MAX_DEPTH:
        raise FsPolicyError("path nests too deeply", context={"maximum": MAX_DEPTH})
    for part in parts:
        if part == "..":
            raise PathEscapeError("parent traversal is not allowed", context={"path": path[:120]})
        if len(part) > MAX_COMPONENT_CHARS:
            raise FsPolicyError("path component too long")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in part):
            raise FsPolicyError("path contains control characters")
        if part.split(".")[0].lower() in _RESERVED_WIN:
            raise FsPolicyError("reserved device name", context={"component": part})
        if part.endswith((" ", ".")):
            raise FsPolicyError("path components may not end with space or dot")
    return PurePosixPath(*parts)


class FsJail:
    """A directory-confined file API with quotas."""

    def __init__(self, root: str | os.PathLike[str], policy: JailPolicy | None = None, *, create: bool = True) -> None:
        root_path = Path(root)
        if create:
            root_path.mkdir(parents=True, exist_ok=True)
        if not root_path.is_dir():
            raise FsPolicyError("jail root must be a directory", context={"root": str(root_path)})
        self.root = root_path.resolve(strict=True)
        self.policy = policy or JailPolicy()

    @classmethod
    def temporary(cls, policy: JailPolicy | None = None, prefix: str = "sbx-") -> FsJail:
        return cls(tempfile.mkdtemp(prefix=prefix), policy)

    # -- resolution ---------------------------------------------------------
    def resolve(self, path: str, *, must_exist: bool = False) -> Path:
        rel = check_relative(path)
        if not self.policy.allow_hidden and any(p.startswith(".") for p in rel.parts):
            raise FsPolicyError("hidden paths are not allowed", context={"path": str(rel)})
        current = self.root
        for i, part in enumerate(rel.parts):
            current = current / part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                if must_exist:
                    raise FsPolicyError("path does not exist", context={"path": str(rel)}) from None
                # Remaining components do not exist yet: nothing to follow.
                return self.root.joinpath(*rel.parts)
            if stat.S_ISLNK(st.st_mode):
                target = Path(os.path.realpath(current))
                if not _within(target, self.root):
                    raise PathEscapeError("symlink escapes the jail", context={"path": str(PurePosixPath(*rel.parts[: i + 1]))})
                current = target
        final = Path(os.path.realpath(self.root.joinpath(*rel.parts)))
        if not _within(final, self.root):
            raise PathEscapeError("path escapes the jail", context={"path": str(rel)})
        return final

    def relative(self, absolute: Path) -> str:
        return absolute.resolve().relative_to(self.root).as_posix()

    # -- usage --------------------------------------------------------------
    def usage(self) -> tuple[int, int]:
        """(bytes, files) under the root, not following symlinks."""
        total = files = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            for name in filenames:
                try:
                    st = os.lstat(os.path.join(dirpath, name))
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(st.st_mode):
                    total += st.st_size
                files += 1
        return total, files

    # -- operations ---------------------------------------------------------
    def read_bytes(self, path: str, *, limit: int | None = None) -> bytes:
        target = self.resolve(path, must_exist=True)
        cap = self.policy.max_file_bytes if limit is None else limit
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise FsPolicyError("only regular files can be read", context={"path": path})
            if st.st_size > cap:
                raise QuotaExceededError("file larger than read limit", context={"size": st.st_size, "limit": cap})
            with os.fdopen(fd, "rb", closefd=False) as fh:
                return fh.read(cap + 1)[:cap]
        finally:
            os.close(fd)

    def read_text(self, path: str, *, limit: int | None = None) -> str:
        return self.read_bytes(path, limit=limit).decode("utf-8", errors="replace")

    def write_bytes(self, path: str, data: bytes) -> int:
        if self.policy.read_only:
            raise FsPolicyError("jail is read-only")
        if not isinstance(data, (bytes, bytearray)):
            raise FsPolicyError("data must be bytes")
        if len(data) > self.policy.max_file_bytes:
            raise QuotaExceededError("file exceeds per-file quota", context={"size": len(data), "limit": self.policy.max_file_bytes})
        target = self.resolve(path)
        used, files = self.usage()
        existing = target.stat().st_size if target.is_file() and not target.is_symlink() else 0
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise FsPolicyError("can only overwrite regular files", context={"path": path})
        if used - existing + len(data) > self.policy.max_bytes:
            raise QuotaExceededError("jail byte quota exceeded", context={"limit": self.policy.max_bytes})
        if not existing and not target.exists() and files + 1 > self.policy.max_files:
            raise QuotaExceededError("jail file quota exceeded", context={"limit": self.policy.max_files})
        target.parent.mkdir(parents=True, exist_ok=True)
        # Re-validate the parent after mkdir (a racing symlink would be caught here).
        if target.parent != self.root:
            self.resolve(self.relative(target.parent), must_exist=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".sbx-tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(bytes(data))
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
        return len(data)

    def write_text(self, path: str, text: str) -> int:
        return self.write_bytes(path, text.encode("utf-8"))

    def listdir(self, path: str | None = None) -> list[str]:
        base = self.root if not path else self.resolve(path, must_exist=True)
        if not base.is_dir():
            raise FsPolicyError("not a directory", context={"path": path})
        out = []
        for name in sorted(os.listdir(base)):
            if not self.policy.allow_hidden and name.startswith("."):
                continue
            out.append(name)
        return out

    def delete(self, path: str) -> None:
        if self.policy.read_only:
            raise FsPolicyError("jail is read-only")
        rel = check_relative(path)
        target = self.root.joinpath(*rel.parts)
        # Resolve the *parent* (the leaf itself may be a symlink we unlink, not follow).
        if len(rel.parts) > 1:
            parent = self.resolve(str(PurePosixPath(*rel.parts[:-1])), must_exist=True)
            target = parent / rel.parts[-1]
        st = os.lstat(target)
        if stat.S_ISDIR(st.st_mode):
            raise FsPolicyError("refusing to delete directories", context={"path": path})
        os.unlink(target)

    def exists(self, path: str) -> bool:
        try:
            return self.resolve(path).exists()
        except (PathEscapeError, FsPolicyError):
            return False


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = ["FsJail", "JailPolicy", "check_relative"]
