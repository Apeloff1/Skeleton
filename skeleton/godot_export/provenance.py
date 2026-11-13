"""Export provenance manifests.

After a certified export, record what was built, from what, by which engine:
sha256 of every artifact, the project tree digest, the git head, the Godot
version line and the certification verdict. Manifests are deterministic JSON
so two runs over identical inputs produce byte-identical output, and
:func:`verify` re-hashes artifacts to detect tampering or stale builds.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .project import IGNORED_DIRS

SCHEMA = "skeleton.godot_export.provenance/v1"


def _safe_identity(value: object, limit: int) -> bool:
    """Reject control characters that can forge provenance text/CI evidence."""
    return (
        type(value) is str and 1 <= len(value) <= limit
        and value == value.strip()
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
MAX_SOURCE_FILES = 100_000
MAX_SOURCE_BYTES = 4 * 1024 * 1024 * 1024


def _relative(path: str) -> tuple[str, ...]:
    """Reject non-canonical and platform-ambiguous manifest paths."""
    if (not isinstance(path, str) or not path or len(path) > 2048
            or "\\" in path or "\x00" in path):
        raise ValueError("unsafe artifact path")
    parts = PurePosixPath(path)
    if (parts.is_absolute() or parts.as_posix() != path
            or any(part in ("", ".", "..") or ":" in part for part in parts.parts)):
        raise ValueError("unsafe artifact path or non-canonical path")
    return parts.parts


def _safe_relative(path: object) -> PurePosixPath:
    return PurePosixPath(*_relative(path))


def _has_symlink(root: Path, rel: PurePosixPath) -> bool:
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _digest_beneath(
    root: Path, relative: str, *, max_bytes: int = MAX_ARTIFACT_BYTES,
) -> tuple[str, int]:
    """Read a bounded artifact via anchored descriptors, detecting path swaps.

    The parent directory descriptor remains open until digest publication so
    a same-size replacement at the file name cannot inherit the old digest.
    The trusted source root itself requires separate operator custody.
    """
    parts = _relative(relative)
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2 * 1024 * 1024 * 1024:
        raise ValueError("invalid bounded artifact digest limit")
    if not all(hasattr(os, k) for k in ("O_NOFOLLOW", "O_DIRECTORY")) or os.name != "posix":
        raise ValueError("secure artifact verification unavailable on this host")
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    # O_NONBLOCK prevents a malicious named pipe from hanging before fstat()
    # rejects it as non-regular. No symlink or hardlink is admitted.
    fflags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    raw_root = Path(root)
    if ".." in raw_root.parts:
        raise ValueError("unsafe artifact root traversal")
    absolute_root = Path(os.path.abspath(os.fspath(raw_root)))
    # Anchor every ancestor, not only the last source directory component.
    fd = os.open("/", dflags)
    try:
        for part in absolute_root.parts[1:] + parts[:-1]:
            nxt = os.open(part, dflags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(parts[-1], fflags, dir_fd=fd)
        try:
            before = os.fstat(file_fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > max_bytes):
                raise ValueError("artifact is not an allowed bounded regular file")
            digest = hashlib.sha256()
            size = 0
            while True:
                data = os.read(file_fd, min(1024 * 1024, max_bytes + 1 - size))
                if not data:
                    break
                size += len(data)
                if size > max_bytes:
                    raise ValueError("artifact exceeds bound")
                digest.update(data)
            after = os.fstat(file_fd)
            # Check both the opened inode and its original directory entry.
            # A digest from an unlinked old inode is not current path evidence.
            linked = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink",
                      "st_size", "st_mtime_ns", "st_ctime_ns")

            def identity(info: os.stat_result) -> tuple[int, ...]:
                return tuple(getattr(info, name) for name in fields)

            if (size != before.st_size or identity(before) != identity(after)
                    or identity(after) != identity(linked)
                    or not stat.S_ISREG(linked.st_mode) or linked.st_nlink != 1):
                raise ValueError("artifact changed or path replaced during digest")
            # The original parent fd can continue referencing a detached
            # directory after an ancestor path swap. Rewalk the complete
            # root/relative parent chain with O_NOFOLLOW and prove it still
            # reaches that same directory, then revalidate the leaf identity.
            # A digest of an orphaned inode is NOT proof of the current path.
            current_fd = os.open("/", dflags)
            try:
                try:
                    for component in absolute_root.parts[1:] + parts[:-1]:
                        nxt = os.open(component, dflags, dir_fd=current_fd)
                        os.close(current_fd)
                        current_fd = nxt
                    current_parent = os.fstat(current_fd)
                    held_parent = os.fstat(fd)
                    if (current_parent.st_dev, current_parent.st_ino) != (
                        held_parent.st_dev, held_parent.st_ino
                    ):
                        raise ValueError("artifact ancestor path replaced during digest")
                    current_leaf = os.stat(
                        parts[-1], dir_fd=current_fd, follow_symlinks=False,
                    )
                except OSError as exc:
                    raise ValueError("artifact ancestor path changed during digest") from exc
                if identity(after) != identity(current_leaf):
                    raise ValueError("artifact path replaced during digest")
            finally:
                os.close(current_fd)
            return digest.hexdigest(), size
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


MAX_MANIFEST_BYTES = 8 * 1024 * 1024

MAX_SOURCE_ENTRIES = 2 * MAX_SOURCE_FILES
MAX_SOURCE_DEPTH = 64


def _open_tree_directory(root_fd: int, relative: tuple[str, ...]) -> int:
    """Reopen a directory without following *any* changed path component.

    os.scandir(string_path) follows intermediate symlinks after a preceding
    is_dir() check. Instead, every iteration re-anchors directory traversal
    from the held root fd, with O_NOFOLLOW applied to each component.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.dup(root_fd)
    try:
        for part in relative:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def tree_digest(root: Path) -> str:
    """Bound source traversal with descriptor-anchored, no-follow directories.

    Enumerating sorted(root.rglob("*")) materialized arbitrary source trees
    before checking budgets. A path-based scandir still followed replaced
    intermediate directories. This scan uses bounded relative components
    and independently checks that even empty subdirectories remained stable
    before certifying a source snapshot.
    """
    root = Path(root)
    if root.is_symlink() or ".." in root.parts:
        raise ValueError("symlink or unsafe source root cannot be certified")
    if os.name != "posix" or not all(
        hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")
    ):
        raise ValueError("source tree descriptor custody unavailable")
    absolute = Path(os.path.abspath(os.fspath(root)))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open("/", flags)
    try:
        for component in absolute.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=root_fd)
            os.close(root_fd)
            root_fd = next_fd
        initial = os.fstat(root_fd)
        pending: list[tuple[str, ...]] = [()]
        observed: list[tuple[tuple[str, ...], tuple[int, ...]]] = []
        source_digests: list[tuple[str, str]] = []
        seen = count = total = 0

        def directory_identity(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev, info.st_ino,
                info.st_mtime_ns, info.st_ctime_ns,
            )

        while pending:
            relative_dir = pending.pop()
            try:
                dfd = _open_tree_directory(root_fd, relative_dir)
            except OSError as exc:
                raise ValueError("source directory changed during scan") from exc
            try:
                observed.append((relative_dir, directory_identity(os.fstat(dfd))))
                with os.scandir(dfd) as entries:
                    for item in entries:
                        name = item.name
                        if name in IGNORED_DIRS:
                            continue
                        # Ignore no path aliases. Names from a dirfd are single
                        # names, not attacker-supplied relative path expressions.
                        if not name or name in (".", "..") or "/" in name:
                            raise ValueError("noncanonical source tree entry")
                        seen += 1
                        if seen > MAX_SOURCE_ENTRIES:
                            raise ValueError("source tree entry budget exceeded")
                        rel = relative_dir + (name,)
                        if item.is_symlink():
                            raise ValueError("symlink or linked project source cannot be certified")
                        if item.is_dir(follow_symlinks=False):
                            if len(rel) > MAX_SOURCE_DEPTH:
                                raise ValueError("source directory depth exceeded")
                            pending.append(rel)
                            continue
                        if not item.is_file(follow_symlinks=False):
                            raise ValueError("special project source cannot be certified")
                        count += 1
                        if count > MAX_SOURCE_FILES:
                            raise ValueError("source file budget exceeded")
                        rel_path = "/".join(rel)
                        digest, size = _digest_beneath(root, rel_path)
                        total += size
                        if total > MAX_SOURCE_BYTES:
                            raise ValueError("source size budget exceeded")
                        source_digests.append((rel_path, digest))
            finally:
                os.close(dfd)

        # Verify that previously scanned directories (including empty ones)
        # still have the same identities and listing generations. Otherwise
        # an attacker can replace a directory after it was marked as empty.
        for relative_dir, fingerprint in observed:
            try:
                dfd = _open_tree_directory(root_fd, relative_dir)
            except OSError as exc:
                raise ValueError("source directory changed after scan") from exc
            try:
                if directory_identity(os.fstat(dfd)) != fingerprint:
                    if not relative_dir:
                        raise ValueError("source root changed during tree digest")
                    raise ValueError("source directory changed after scan")
            finally:
                os.close(dfd)

        # Source root itself must still be reachable from the identical path.
        check_fd = os.open("/", flags)
        try:
            try:
                for component in absolute.parts[1:]:
                    next_fd = os.open(component, flags, dir_fd=check_fd)
                    os.close(check_fd)
                    check_fd = next_fd
                current = os.fstat(check_fd)
            except OSError as exc:
                raise ValueError("source root changed during tree digest") from exc
            if directory_identity(current) != directory_identity(initial):
                raise ValueError("source root changed during tree digest")
        finally:
            os.close(check_fd)
        result = hashlib.sha256()
        for rel_path, digest in sorted(source_digests):
            result.update(rel_path.encode() + b"\0" + digest.encode() + b"\n")
        return result.hexdigest()
    finally:
        os.close(root_fd)


def git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and len(out) == 40 else None


@dataclass(frozen=True)
class Artifact:
    preset: str
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        if not _safe_identity(self.preset, 128):
            raise ValueError("invalid artifact preset")
        _relative(self.path)
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in self.sha256)):
            raise ValueError("invalid artifact sha256")
        if type(self.size) is not int or not 0 < self.size <= MAX_ARTIFACT_BYTES:
            raise ValueError("invalid artifact size")


@dataclass
class Manifest:
    project: str
    tree: str
    engine: str
    verdict: str
    git: str | None = None
    artifacts: list[Artifact] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _safe_identity(self.project, 256):
            raise ValueError("invalid project identity")
        if not _safe_identity(self.engine, 256):
            raise ValueError("invalid engine identity")
        if not isinstance(self.tree, str) or len(self.tree) != 64 or any(
                c not in "0123456789abcdef" for c in self.tree):
            raise ValueError("invalid project source tree digest")
        if self.verdict not in ("SHIP", "NO-SHIP"):
            raise ValueError("invalid certification verdict")
        if self.git is not None and (not isinstance(self.git, str) or len(self.git) != 40
                or any(c not in "0123456789abcdef" for c in self.git)):
            raise ValueError("invalid git source pin")
        if not isinstance(self.artifacts, list) or len(self.artifacts) > 256:
            raise ValueError("invalid artifact inventory")
        if any(not isinstance(a, Artifact) for a in self.artifacts):
            raise ValueError("untyped artifact")
        ids = [(a.preset, a.path) for a in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicated artifact inventory entry")
        # Distinct presets cannot independently attest one identical output
        # path as if they were different built artifacts.
        paths = [item.path for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("artifact path reused by multiple presets")

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        return {"schema": SCHEMA, "project": self.project, "tree": self.tree, "engine": self.engine,
                "verdict": self.verdict, "git": self.git,
                "artifacts": [a.__dict__ for a in sorted(self.artifacts, key=lambda a: (a.preset, a.path))]}

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Manifest":
        if type(text) is not str:
            raise ValueError("invalid provenance JSON")
        try:
            if len(text.encode("utf-8", "strict")) > MAX_MANIFEST_BYTES:
                raise ValueError("provenance manifest exceeds byte bound")
        except UnicodeError as exc:
            raise ValueError("invalid provenance JSON") from exc

        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate provenance JSON key")
                result[key] = value
            return result

        d = json.loads(text, object_pairs_hook=no_duplicates,
                       parse_constant=lambda value: (_ for _ in ()).throw(
                           ValueError("nonfinite provenance JSON")))
        if not isinstance(d, dict) or d.get("schema") != SCHEMA:
            raise ValueError("unknown provenance schema")
        allowed = {"schema", "project", "tree", "engine", "verdict", "git", "artifacts"}
        if set(d) - allowed or not {"project", "tree", "engine", "verdict"}.issubset(d):
            raise ValueError("invalid provenance fields")
        artifacts = d.get("artifacts")
        if type(artifacts) is not list or len(artifacts) > 256:
            raise ValueError("invalid artifact inventory")
        expected = {"preset", "path", "sha256", "size"}
        if any(not isinstance(a, dict) or set(a) != expected for a in artifacts):
            raise ValueError("invalid artifact fields")
        return cls(d["project"], d["tree"], d["engine"], d["verdict"], d.get("git"),
                   [Artifact(**a) for a in artifacts])


def _read_manifest_bytes(path: Path) -> bytes:
    """Read the real, current manifest through bounded no-follow descriptors.

    Path.read_text() previously loaded an unbounded file *before* Manifest.loads
    could enforce its byte limit, and could follow an intermediate symlink.
    Require regular single-link files, stable metadata and a reachable parent.
    A read fixture is not evidence of a verified Godot export.
    """
    raw = Path(path)
    if ".." in raw.parts or not raw.name:
        raise ValueError("unsafe provenance manifest path")
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")):
        raise ValueError("secure manifest reading unavailable on this host")
    absolute = Path(os.path.abspath(os.fspath(raw)))
    parts = absolute.parts
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    dfd = os.open("/", dir_flags)
    try:
        for component in parts[1:-1]:
            child = os.open(component, dir_flags, dir_fd=dfd)
            os.close(dfd)
            dfd = child
        file_fd = os.open(parts[-1], file_flags, dir_fd=dfd)
        try:
            before = os.fstat(file_fd)
            if (not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or before.st_size > MAX_MANIFEST_BYTES):
                raise ValueError("unsafe or oversized provenance manifest")
            data = bytearray()
            while True:
                chunk = os.read(
                    file_fd,
                    min(1024 * 1024, MAX_MANIFEST_BYTES + 1 - len(data)),
                )
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_MANIFEST_BYTES:
                    raise ValueError("provenance manifest exceeds byte bound")
            after = os.fstat(file_fd)
            linked = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
            def fingerprint(info: os.stat_result) -> tuple[int, ...]:
                return (
                    info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                    info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                )
            if (len(data) != before.st_size
                    or fingerprint(before) != fingerprint(after)
                    or fingerprint(after) != fingerprint(linked)):
                raise ValueError("provenance manifest changed during read")
            fresh = os.open("/", dir_flags)
            try:
                for component in parts[1:-1]:
                    child = os.open(component, dir_flags, dir_fd=fresh)
                    os.close(fresh)
                    fresh = child
                held_parent = os.fstat(dfd)
                current_parent = os.fstat(fresh)
                if (held_parent.st_dev, held_parent.st_ino) != (
                    current_parent.st_dev, current_parent.st_ino
                ):
                    raise ValueError("provenance manifest parent changed during read")
                current = os.stat(parts[-1], dir_fd=fresh, follow_symlinks=False)
                if fingerprint(current) != fingerprint(after):
                    raise ValueError("provenance manifest path changed during read")
            finally:
                os.close(fresh)
            return bytes(data)
        finally:
            os.close(file_fd)
    finally:
        os.close(dfd)


def read_manifest_file(path: Path) -> Manifest:
    """Reject unsafe manifest paths, then parse strictly bounded UTF-8 JSON."""
    data = _read_manifest_bytes(path)
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise ValueError("invalid provenance manifest UTF-8") from exc
    return Manifest.loads(text)


def write_manifest_file_new(path: Path, manifest: Manifest) -> None:
    """Write a new deterministic manifest with no-clobber descriptor custody.

    No symlink or existing entry can be replaced. Publication requires an
    exact byte-for-byte readback through the same bounded, ancestor-anchored
    reader as verification. Caller-owned output directories must already
    exist; this operation never creates arbitrary directory trees.
    """
    if not isinstance(manifest, Manifest):
        raise ValueError("provenance writer requires a typed manifest")
    data = manifest.dumps().encode("utf-8")
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("provenance manifest exceeds byte bound")
    raw = Path(path)
    if ".." in raw.parts or not raw.name:
        raise ValueError("unsafe provenance manifest output path")
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")):
        raise ValueError("secure manifest publication unavailable on this host")
    absolute = Path(os.path.abspath(os.fspath(raw)))
    parts = absolute.parts
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    dfd = os.open("/", dflags)
    created: os.stat_result | None = None
    completed = False
    try:
        for component in parts[1:-1]:
            child = os.open(component, dflags, dir_fd=dfd)
            os.close(dfd)
            dfd = child
        fd = os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=dfd,
        )
        created = os.fstat(fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(dfd)
        observed = _read_manifest_bytes(path)
        if observed != data:
            raise ValueError("provenance manifest contents changed during publication")
        linked = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
        if (not stat.S_ISREG(linked.st_mode)
                or linked.st_nlink != 1
                or (linked.st_dev, linked.st_ino) !=
                (created.st_dev, created.st_ino)):
            raise ValueError("provenance manifest path changed during publication")
        completed = True
    finally:
        try:
            if created is not None and not completed:
                try:
                    linked = os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False)
                    if (linked.st_dev, linked.st_ino) == (
                        created.st_dev, created.st_ino
                    ):
                        os.unlink(parts[-1], dir_fd=dfd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(dfd)


def build(root: Path, engine: str, verdict: str, artifacts: dict[str, Path], base: Path | None = None) -> Manifest:
    root = Path(root)
    base = Path(base) if base is not None else root
    m = Manifest(root.name, tree_digest(root), engine, verdict, git_head(root))
    for preset, path in artifacts.items():
        try:
            rel = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(base))).as_posix()
        except ValueError as exc:
            raise ValueError("artifact is outside approved base") from exc
        try:
            digest, size = _digest_beneath(base, rel)
        except OSError as exc:
            raise ValueError("symlink or unsafe artifact source") from exc
        m.artifacts.append(Artifact(preset, rel, digest, size))
    m.__post_init__()
    return m


def verify(manifest: Manifest, base: Path, root: Path | None = None) -> list[str]:
    manifest.__post_init__()
    problems: list[str] = []
    for a in manifest.artifacts:
        try:
            rel = _safe_relative(a.path)
        except ValueError:
            problems.append(f"{a.preset}: unsafe artifact path")
            continue
        if _has_symlink(Path(base), rel):
            problems.append(f"{a.preset}: unsafe symlink artifact path refused")
            continue
        try:
            digest, size = _digest_beneath(Path(base), a.path)
        except FileNotFoundError:
            problems.append(f"{a.preset}: missing {a.path}")
            continue
        except (OSError, ValueError):
            problems.append(f"{a.preset}: unsafe or unreadable {a.path}")
            continue
        if size != a.size:
            problems.append(f"{a.preset}: size mismatch for {a.path}")
        if digest != a.sha256:
            problems.append(f"{a.preset}: sha256 mismatch for {a.path}")
    if root is not None:
        source = Path(root)
        # A digest alone cannot distinguish two separately identified
        # projects with identical source files. This field is part of the
        # signed-off manifest identity, not descriptive UI metadata.
        if source.name != manifest.project:
            problems.append("project identity differs from manifest")
        try:
            same_tree = tree_digest(source) == manifest.tree
        except (OSError, ValueError):
            same_tree = False
        if not same_tree:
            problems.append("project tree changed since manifest")
        # A source-tree SHA does not attest the Git revision recorded in the
        # receipt. The field is optional for exported trees outside Git; if a
        # Git head was pinned, require the exact head on re-verification.
        if manifest.git is not None and git_head(source) != manifest.git:
            problems.append("git source pin differs from manifest")
    if manifest.verdict != "SHIP":
        problems.append(f"manifest verdict is {manifest.verdict}")
    if not manifest.artifacts and manifest.verdict == "SHIP":
        problems.append("no certified artifacts in manifest")
    return problems
