"""Finite descriptor-anchored search of an operator-selected local code tree.

The model gets no filesystem authority. Only the human chooses a trusted
workspace root and search terms, then explicitly promotes selected immutable
UTF-8 excerpts into the existing private local GGUF prompt attachments.
No shell, regex engine, network request, mmap or recursive path.resolve is
used on untrusted source packages.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
import time

MAX_SOURCE_DIRS = 128
MAX_FILES_SCANNED = 2048
MAX_TOTAL_SCAN_BYTES = 24 * 1024 * 1024
MAX_FILE_BYTES = 65536
MAX_DIR_ITEMS = 4096
MAX_DEPTH = 8
MAX_RESULTS = 50
MAX_EXCERPT_BYTES = 8192
MAX_QUERY_BYTES = 256
MAX_TERMS = 8

_ALLOWED_SUFFIXES = frozenset((
    ".py", ".pyi", ".md", ".rst", ".txt", ".json", ".toml", ".yaml",
    ".yml", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".sql",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".sh", ".ps1", ".ini", ".cfg", ".xml",
))
_DENY_PARTS = frozenset((
    ".git", ".hg", ".svn", ".github", ".ssh", ".gnupg",
    ".vscode", ".idea", ".devcontainer", "node_modules",
    "__pycache__", ".venv", "venv", "dist", "build", "target",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
))
_DENY_WORDS = (
    "secret", "password", "credential", "private_key",
    "api_key", "access_token", "id_rsa", "id_ed25519",
)


class DesktopSearchHold(ValueError):
    """Workspace search cannot establish finite trusted source bounds."""


@dataclass(frozen=True, slots=True)
class SearchLimits:
    maximum_directories: int = 96
    maximum_files: int = 1024
    maximum_total_bytes: int = 16 * 1024 * 1024
    maximum_file_bytes: int = 65536
    maximum_depth: int = 6
    maximum_results: int = 30
    maximum_wall_seconds: int = 15

    def __post_init__(self):
        for name, low, high in (
            ("maximum_directories", 1, MAX_SOURCE_DIRS),
            ("maximum_files", 1, MAX_FILES_SCANNED),
            ("maximum_total_bytes", 1024, MAX_TOTAL_SCAN_BYTES),
            ("maximum_file_bytes", 128, MAX_FILE_BYTES),
            ("maximum_depth", 0, MAX_DEPTH),
            ("maximum_results", 1, MAX_RESULTS),
            ("maximum_wall_seconds", 1, 60),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise DesktopSearchHold("invalid bounded workspace search " + name)


@dataclass(frozen=True, slots=True)
class SearchHit:
    relative_path: str
    file_sha256: str
    file_bytes: int
    start_byte: int
    end_byte: int
    line_start: int
    line_end: int
    score: int
    excerpt: str
    excerpt_sha256: str

    def __post_init__(self):
        if (
            type(self.relative_path) is not str
            or not self.relative_path
            or self.relative_path.startswith("/")
            or ".." in self.relative_path.split("/")
            or "\x00" in self.relative_path
        ):
            raise DesktopSearchHold("invalid searched source path")
        for name in ("file_sha256", "excerpt_sha256"):
            digest = getattr(self, name)
            if (
                type(digest) is not str or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise DesktopSearchHold("unverifiable source content hash")
        if (
            type(self.file_bytes) is not int or not 1 <= self.file_bytes <= MAX_FILE_BYTES
            or type(self.start_byte) is not int or self.start_byte < 0
            or type(self.end_byte) is not int or not self.start_byte < self.end_byte <= self.file_bytes
            or type(self.line_start) is not int or self.line_start < 1
            or type(self.line_end) is not int or self.line_end < self.line_start
            or type(self.score) is not int or self.score < 1
            or type(self.excerpt) is not str
        ):
            raise DesktopSearchHold("unbounded source excerpt witness")
        try:
            raw = self.excerpt.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise DesktopSearchHold("source excerpt has invalid Unicode") from exc
        if (
            not 1 <= len(raw) <= MAX_EXCERPT_BYTES
            or self.end_byte - self.start_byte != len(raw)
            or sha256(raw).hexdigest() != self.excerpt_sha256
        ):
            raise DesktopSearchHold("source excerpt hash/byte offsets differ")


@dataclass(frozen=True, slots=True)
class SearchReport:
    query: str
    root_dev: int
    root_inode: int
    scanned_files: int
    scanned_directories: int
    scanned_bytes: int
    denied_entries: int
    complete: bool
    hits: tuple[SearchHit, ...]

    def __post_init__(self):
        if (
            type(self.query) is not str
            or type(self.root_dev) is not int or self.root_dev < 0
            or type(self.root_inode) is not int or self.root_inode < 1
            or type(self.complete) is not bool
            or type(self.hits) is not tuple
            or len(self.hits) > MAX_RESULTS
        ):
            raise DesktopSearchHold("invalid finite searched-source report")
        for name, ceiling in (
            ("scanned_files", MAX_FILES_SCANNED),
            ("scanned_directories", MAX_SOURCE_DIRS),
            ("scanned_bytes", MAX_TOTAL_SCAN_BYTES),
            ("denied_entries", MAX_FILES_SCANNED * MAX_DIR_ITEMS),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= ceiling:
                raise DesktopSearchHold("out-of-bounds workspace search evidence")
        if any(type(h) is not SearchHit for h in self.hits):
            raise DesktopSearchHold("source report contains unverified hit")

    @property
    def status(self):
        return "complete-bounded-search" if self.complete else "partial-bounded-search"


def _terms(raw: object) -> tuple[str, ...]:
    if type(raw) is not str or "\x00" in raw:
        raise DesktopSearchHold("operator search query must be Unicode text")
    try:
        encoded = raw.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise DesktopSearchHold("search query contains invalid Unicode") from exc
    if not 2 <= len(encoded) <= MAX_QUERY_BYTES:
        raise DesktopSearchHold("search query exceeds finite original-byte bound")
    terms = tuple(dict.fromkeys(piece.casefold() for piece in raw.split()))
    if (
        not 1 <= len(terms) <= MAX_TERMS
        or any(not 2 <= len(t.encode("utf-8", "strict")) <= 64 for t in terms)
    ):
        raise DesktopSearchHold("search query has unsafe token lengths")
    return terms


def _allowed_name(name: object, *, directory: bool) -> bool:
    if type(name) is not str or not name or name.startswith("."):
        return False
    if name.lower() in _DENY_PARTS:
        return False
    if any(blocked in name.lower() for blocked in _DENY_WORDS):
        return False
    try:
        if not 1 <= len(name.encode("utf-8", "strict")) <= 180:
            return False
    except UnicodeError:
        return False
    if "/" in name or "\\" in name or chr(0) in name:
        return False
    return directory or Path(name).suffix.lower() in _ALLOWED_SUFFIXES


def _source_meta(stat_result) -> tuple[int, int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_mode,
    )


def _trusted_stat(info, *, directory: bool) -> bool:
    is_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not is_type or info.st_ino < 1:
        return False
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        return False
    if info.st_mode & 0o022:
        return False
    if not directory and info.st_nlink != 1:
        return False
    return True


def _open_read(parent_fd: int, name: str, expected) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        first = os.fstat(descriptor)
        if not _trusted_stat(first, directory=False) or _source_meta(first) != _source_meta(expected):
            raise DesktopSearchHold("changed or unowned source file")
        if not 1 <= first.st_size <= MAX_FILE_BYTES:
            raise DesktopSearchHold("file exceeds finite original-byte ceiling")
        data = bytearray()
        while len(data) < first.st_size + 1:
            part = os.read(descriptor, min(4096, first.st_size + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        second = os.fstat(descriptor)
        if (
            _source_meta(second) != _source_meta(first)
            or len(data) != first.st_size
            or not _trusted_stat(second, directory=False)
        ):
            raise DesktopSearchHold("original source changed during bounded scan")
        return bytes(data)
    finally:
        os.close(descriptor)


def _clip_utf8(text: str, ceiling: int) -> str:
    if type(ceiling) is not int or not 1 <= ceiling <= MAX_EXCERPT_BYTES:
        raise DesktopSearchHold("invalid source excerpt ceiling")
    total = 0
    acc = []
    for codepoint in text:
        n = len(codepoint.encode("utf-8", "strict"))
        if total + n > ceiling:
            break
        acc.append(codepoint)
        total += n
    return "".join(acc)


def _hits_for_file(
    relative_path: str, raw: bytes, terms: tuple[str, ...],
    *, maximum_per_file: int = 3,
) -> tuple[SearchHit, ...]:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError:
        return ()
    if "\x00" in text or not text.strip():
        return ()
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8", "strict")))
    if offsets[-1] != len(raw):
        raise DesktopSearchHold("source line indexing lost original UTF-8 bytes")
    path_rank = sum(3 for term in terms if term in relative_path.casefold())
    matches = []
    for i, line in enumerate(lines):
        normalized = line.casefold()
        found = sum(1 for token in terms if token in normalized)
        if found == 0:
            continue
        score = found * 8 + path_rank + (12 if found == len(terms) else 0)
        left, right = max(0, i - 1), min(len(lines), i + 2)
        excerpt = _clip_utf8("".join(lines[left:right]), MAX_EXCERPT_BYTES)
        if not excerpt:
            continue
        start = offsets[left]
        raw_excerpt = excerpt.encode("utf-8", "strict")
        # The excerpt is an exact contiguous source byte slice, not a
        # normalized or model-rewritten copy.
        if raw[start:start + len(raw_excerpt)] != raw_excerpt:
            raise DesktopSearchHold("search excerpt differs from original bytes")
        hit = SearchHit(
            relative_path=relative_path,
            file_sha256=sha256(raw).hexdigest(),
            file_bytes=len(raw),
            start_byte=start,
            end_byte=start + len(raw_excerpt),
            line_start=left + 1,
            line_end=min(right, left + max(1, excerpt.count("\n") + 1)),
            score=score,
            excerpt=excerpt,
            excerpt_sha256=sha256(raw_excerpt).hexdigest(),
        )
        matches.append(hit)
    # File-name discovery is useful for the first local coding task even
    # when the searched symbol does not occur in that file's body. Expose
    # only bounded beginning-of-file source as an exact-byte snapshot.
    if not matches and path_rank:
        excerpt = _clip_utf8(text, MAX_EXCERPT_BYTES)
        encoded = excerpt.encode("utf-8", "strict")
        if encoded and raw[:len(encoded)] == encoded:
            matches.append(SearchHit(
                relative_path=relative_path,
                file_sha256=sha256(raw).hexdigest(),
                file_bytes=len(raw),
                start_byte=0,
                end_byte=len(encoded),
                line_start=1,
                line_end=max(1, excerpt.count("\n") + 1),
                score=path_rank,
                excerpt=excerpt,
                excerpt_sha256=sha256(encoded).hexdigest(),
            ))
    matches.sort(
        key=lambda item: (-item.score, item.start_byte, item.end_byte)
    )
    return tuple(matches[:maximum_per_file])


def search_workspace(
    root: str | Path, query: str, *,
    limits: SearchLimits | None = None,
) -> SearchReport:
    """Return source-exact excerpts, bounded and read-only by construction.

    A report marked partial is never described as an exhaustive workspace
    search. The caller must explicitly select any excerpt to send to GGUF.
    """
    from skeleton.ai.runtime.operational_ai.model.gguf.file_guard import (
        open_trusted_root,
    )

    cfg = SearchLimits() if limits is None else limits
    if type(cfg) is not SearchLimits:
        raise DesktopSearchHold("typed finite code search limits required")
    terms = _terms(query)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DesktopSearchHold("trusted descriptor workspace search unavailable")
    if not isinstance(root, (str, Path)):
        raise DesktopSearchHold("explicit absolute source root required")
    root_path = Path(root)
    if (
        not root_path.is_absolute() or ".." in root_path.parts
        or "\x00" in str(root_path)
    ):
        raise DesktopSearchHold("noncanonical explicit project source root")
    anchor = open_trusted_root(root_path)
    pending: list[tuple[int, str, int]] = [(anchor, "", 0)]
    seen: set[tuple[int, int]] = set()
    files = 0
    directories = 0
    read_bytes = 0
    denied = 0
    complete = True
    matches: list[SearchHit] = []
    deadline = time.monotonic() + cfg.maximum_wall_seconds
    initial = os.fstat(anchor)
    if not _trusted_stat(initial, directory=True):
        os.close(anchor)
        raise DesktopSearchHold("untrusted root owner or unsafe workspace mode")
    try:
        while pending:
            if time.monotonic() >= deadline:
                complete = False
                break
            directory_fd, prefix, depth = pending.pop()
            try:
                info = os.fstat(directory_fd)
                marker = (info.st_dev, info.st_ino)
                if marker in seen:
                    denied += 1
                    continue
                seen.add(marker)
                if directories >= cfg.maximum_directories:
                    complete = False
                    break
                directories += 1
                if not _trusted_stat(info, directory=True):
                    denied += 1
                    complete = False
                    continue
                names = []
                # scandir on the pinned directory FD bounds allocation even
                # against directories with millions of entries.
                with os.scandir(directory_fd) as entries:
                    for entry in entries:
                        if time.monotonic() >= deadline:
                            complete = False
                            break
                        if len(names) >= MAX_DIR_ITEMS:
                            complete = False
                            break
                        names.append(entry.name)
                for name in sorted(names, key=str.casefold):
                    if time.monotonic() >= deadline:
                        complete = False
                        break
                    is_hidden = not _allowed_name(name, directory=True)
                    if is_hidden:
                        denied += 1
                        continue
                    relative = name if not prefix else prefix + "/" + name
                    try:
                        before = os.stat(
                            name, dir_fd=directory_fd, follow_symlinks=False,
                        )
                    except OSError:
                        denied += 1
                        complete = False
                        continue
                    if stat.S_ISDIR(before.st_mode):
                        if depth >= cfg.maximum_depth:
                            complete = False
                            continue
                        try:
                            child = os.open(
                                name,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                | getattr(os, "O_CLOEXEC", 0),
                                dir_fd=directory_fd,
                            )
                        except OSError:
                            denied += 1
                            complete = False
                            continue
                        after = os.fstat(child)
                        if (
                            _source_meta(after) != _source_meta(before)
                            or not _trusted_stat(after, directory=True)
                        ):
                            os.close(child)
                            denied += 1
                            complete = False
                            continue
                        if directories + len(pending) >= cfg.maximum_directories:
                            os.close(child)
                            complete = False
                            continue
                        pending.append((child, relative, depth + 1))
                        continue
                    if not _allowed_name(name, directory=False):
                        denied += 1
                        continue
                    if (
                        not _trusted_stat(before, directory=False)
                        or not 1 <= before.st_size <= cfg.maximum_file_bytes
                    ):
                        denied += 1
                        continue
                    if files >= cfg.maximum_files:
                        complete = False
                        break
                    if read_bytes + before.st_size > cfg.maximum_total_bytes:
                        complete = False
                        break
                    try:
                        raw = _open_read(directory_fd, name, before)
                        hits = _hits_for_file(relative, raw, terms)
                    except (OSError, UnicodeError, DesktopSearchHold):
                        denied += 1
                        complete = False
                        continue
                    files += 1
                    read_bytes += len(raw)
                    matches.extend(hits)
                    if len(matches) > cfg.maximum_results * 4:
                        matches.sort(
                            key=lambda h: (-h.score, h.relative_path, h.start_byte)
                        )
                        del matches[cfg.maximum_results:]
                # A source quota is a *hard* stop, not a silent claim that
                # the remaining directory tree was scanned exhaustively.
                if files >= cfg.maximum_files or read_bytes >= cfg.maximum_total_bytes:
                    complete = False
                    break
            finally:
                os.close(directory_fd)
        # Root, descendant directories and files are pinned by descriptors.
        # Never reopen a potentially swapped absolute path during a scan.
        matches.sort(key=lambda h: (-h.score, h.relative_path, h.start_byte))
        return SearchReport(
            query=query, root_dev=initial.st_dev, root_inode=initial.st_ino,
            scanned_files=files, scanned_directories=directories,
            scanned_bytes=read_bytes, denied_entries=denied,
            complete=complete,
            hits=tuple(matches[:cfg.maximum_results]),
        )
    finally:
        for directory_fd, _, _ in pending:
            try:
                os.close(directory_fd)
            except OSError:
                pass


__all__ = [
    "DesktopSearchHold", "SearchLimits", "SearchHit", "SearchReport",
    "search_workspace",
]
