"""Bounded, read-only source-file atlas for Jeeves' whole-application awareness.

The application host explicitly refreshes this catalog. Jeeves can query
indexed paths/ownership/features without rescanning thousands of files or
loading source contents into its model context. No indexed path grants edit,
import, credential or execution privileges.

This is a filesystem observation index, not a claim that every discovered file
is implemented, usable or tested. Only non-symlink regular files within the
host-selected repository are indexed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

MAX_FILES = 250_000
MAX_DEPTH = 24
MAX_QUERY = 160
MAX_PAGE = 100
MAX_HASH_BYTES = 2 * 1024 * 1024
MAX_ROOTS = 512

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "build", "dist",
    "__pycache__", ".cache", ".pytest_cache", ".mypy_cache",
    ".tox", ".next", ".expo", ".turbo", "coverage", "vendor",
    ".gradle", "target", "out", "artifacts",
})
SKIP_SUFFIXES = (".pem", ".p12", ".pfx", ".key", ".crt", ".sqlite", ".db", ".pyc")


class RepositoryAtlasError(ValueError):
    """Untrusted path, oversized index, bad manifest or stale persisted atlas."""


@dataclass(frozen=True, slots=True)
class IndexedFile:
    path: str
    owner_root: str
    feature: str
    suffix: str
    bytes: int
    modified_ns: int
    content_sha256: str | None

    def row(self) -> tuple:
        return (
            self.path, self.owner_root, self.feature, self.suffix,
            self.bytes, self.modified_ns, self.content_sha256,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "owner_root": self.owner_root,
            "feature": self.feature,
            "suffix": self.suffix,
            "bytes": self.bytes,
            "modified_ns": self.modified_ns,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True, slots=True)
class AtlasRefresh:
    index_sha256: str
    observed_at_ns: int
    file_count: int
    added: int
    removed: int
    changed: int
    hashed: int


_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jeeves_atlas_files (
    path TEXT PRIMARY KEY,
    owner_root TEXT NOT NULL,
    feature TEXT NOT NULL,
    suffix TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    content_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS jeeves_atlas_owner_idx
    ON jeeves_atlas_files(owner_root, path);
CREATE INDEX IF NOT EXISTS jeeves_atlas_feature_idx
    ON jeeves_atlas_files(feature, path);
CREATE INDEX IF NOT EXISTS jeeves_atlas_hash_idx
    ON jeeves_atlas_files(content_sha256);
CREATE TABLE IF NOT EXISTS jeeves_atlas_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    schema TEXT NOT NULL,
    index_sha256 TEXT NOT NULL,
    observed_at_ns INTEGER NOT NULL,
    file_count INTEGER NOT NULL
);
"""


def _skip_file(name: str) -> bool:
    lower = name.casefold()
    if (name.startswith(".") and name not in {".gitignore", ".gitattributes"}):
        return True
    return (
        lower.startswith(".env") or lower in {"id_rsa", "id_ed25519"}
        or lower.endswith(SKIP_SUFFIXES)
        or lower.startswith("credentials.")
    )


def _canonical_sha(rows: list[IndexedFile]) -> str:
    digest = sha256()
    for row in rows:
        digest.update(json.dumps(
            row.row(), separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class JeevesRepositoryFileAtlas:
    """Host-rebuilt SQLite projection; model-facing methods are read-only."""

    def __init__(self, repo_root: str | Path, store_path: str | Path) -> None:
        from skeleton.jeeves.app_capability_bridge import _manifest, _root
        self.root = _root(repo_root)
        self.path = Path(store_path)
        if not self.path.is_absolute() or self.path.resolve().is_relative_to(self.root):
            raise RepositoryAtlasError("atlas database must be outside the source tree")
        arch = _manifest(self.root / "machine" / "architecture.json")
        roots = arch.get("canonical_roots")
        if not isinstance(roots, list) or not 1 <= len(roots) <= MAX_ROOTS:
            raise RepositoryAtlasError("canonical architecture root index is invalid")
        canonical_roots: set[str] = set()
        for node in roots:
            if not isinstance(node, dict):
                raise RepositoryAtlasError("invalid canonical root descriptor")
            prefix = node.get("path")
            if not isinstance(prefix, str) or not prefix or prefix.startswith("/"):
                raise RepositoryAtlasError("invalid canonical source root")
            parts = Path(prefix).parts
            if (".." in parts or "\\" in prefix or
                    any(part == "" for part in parts)):
                raise RepositoryAtlasError("unsafe architecture root")
            canonical_roots.add(prefix.rstrip("/"))
        self._owners = tuple(sorted(canonical_roots, key=lambda x: (-len(x), x)))
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), timeout=10, isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
        except BaseException:
            self._db.close()
            raise

    def _owner(self, path: str) -> str:
        for prefix in self._owners:
            if path == prefix or path.startswith(prefix + "/"):
                return prefix
        return "unresolved"

    @staticmethod
    def _feature(relative: str) -> str:
        parts = relative.split("/")
        if len(parts) >= 4 and parts[0] == "skeleton" and parts[1] == "ai":
            return "ai/" + parts[2]
        if len(parts) >= 3 and parts[0] == "skeleton":
            return "skeleton/" + parts[1]
        if len(parts) >= 2:
            return "/".join(parts[:2]) if parts[0] in (
                "frontend", "backend", "docs", "machine", "scripts",
            ) else parts[0]
        return parts[0]

    @staticmethod
    def _hash(path: Path, size: int) -> str | None:
        if size > MAX_HASH_BYTES:
            return None
        # Never follow a newly swapped source symlink when O_NOFOLLOW is
        # supported by the host. Bounded reads also reject mid-scan growth.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        digest = sha256()
        try:
            with os.fdopen(fd, "rb") as stream:
                current = os.fstat(stream.fileno())
                if not os.path.isfile(path) or current.st_size != size:
                    raise RepositoryAtlasError("source changed during content hashing")
                read_total = 0
                while chunk := stream.read(128 * 1024):
                    read_total += len(chunk)
                    if read_total > MAX_HASH_BYTES:
                        raise RepositoryAtlasError("hashed source exceeded byte cap")
                    digest.update(chunk)
        except BaseException:
            # fdopen owns the descriptor and closes it even on errors.
            raise
        return digest.hexdigest()

    def _walk(self, *, hash_contents: bool) -> list[IndexedFile]:
        queue: list[tuple[Path, int]] = [(self.root, 0)]
        rows: list[IndexedFile] = []
        while queue:
            directory, depth = queue.pop()
            if depth > MAX_DEPTH:
                raise RepositoryAtlasError("repository depth exceeds atlas policy")
            try:
                entries = sorted(os.scandir(directory), key=lambda x: x.name)
            except OSError as exc:
                raise RepositoryAtlasError("repository scan failed") from exc
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS:
                        queue.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False) and not _skip_file(entry.name):
                    relative = Path(entry.path).relative_to(self.root).as_posix()
                    if len(relative) > 2048:
                        raise RepositoryAtlasError("source path exceeds index bound")
                    if len(rows) >= MAX_FILES:
                        raise RepositoryAtlasError("file index exceeds capacity")
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        content_sha = (
                            self._hash(Path(entry.path), stat.st_size)
                            if hash_contents else None
                        )
                    except OSError as exc:
                        raise RepositoryAtlasError("source changed during observation") from exc
                    rows.append(IndexedFile(
                        path=relative, owner_root=self._owner(relative),
                        feature=self._feature(relative), suffix=Path(entry.name).suffix.lower(),
                        bytes=stat.st_size, modified_ns=stat.st_mtime_ns,
                        content_sha256=content_sha,
                    ))
        rows.sort(key=lambda x: x.path)
        return rows

    def refresh(self, *, observed_at_ns: int, hash_contents: bool = False) -> AtlasRefresh:
        """Host-only rebuild; bounded one-pass scan plus atomic index replacement."""
        if type(observed_at_ns) is not int or observed_at_ns < 0:
            raise RepositoryAtlasError("host timestamp must be non-negative")
        if type(hash_contents) is not bool:
            raise RepositoryAtlasError("hash_contents must be a boolean")
        with self._lock:
            rows = self._walk(hash_contents=hash_contents)
            digest = _canonical_sha(rows)
            current = {
                row[0]: tuple(row[1:]) for row in self._db.execute(
                    "SELECT path,owner_root,feature,suffix,bytes,modified_ns,"
                    "content_sha256 FROM jeeves_atlas_files"
                )
            }
            next_values = {row.path: row.row()[1:] for row in rows}
            added = len(set(next_values) - set(current))
            removed = len(set(current) - set(next_values))
            changed = sum(
                current[name] != data for name, data in next_values.items()
                if name in current
            )
            try:
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute("DELETE FROM jeeves_atlas_files")
                self._db.executemany(
                    "INSERT INTO jeeves_atlas_files VALUES (?,?,?,?,?,?,?)",
                    (row.row() for row in rows),
                )
                self._db.execute(
                    "INSERT INTO jeeves_atlas_meta VALUES (1, ?, ?, ?, ?) "
                    "ON CONFLICT(singleton) DO UPDATE SET "
                    "schema=excluded.schema, index_sha256=excluded.index_sha256, "
                    "observed_at_ns=excluded.observed_at_ns, file_count=excluded.file_count",
                    ("jeeves.repository_file_atlas.v1", digest, observed_at_ns, len(rows)),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return AtlasRefresh(
                index_sha256=digest, observed_at_ns=observed_at_ns,
                file_count=len(rows), added=added, removed=removed,
                changed=changed,
                hashed=sum(row.content_sha256 is not None for row in rows),
            )

    def apply_changes(self, changed_paths: list[str], *, observed_at_ns: int,
                      hash_contents: bool = False) -> AtlasRefresh:
        """Host-only, event-driven incremental reindex after file-tree changes.

        Paths must be canonical, relative and from a trusted repository event.
        A deleted file is removed; a changed regular file is re-statted. The
        index digest is recomputed from metadata, not from a full source walk.
        """
        if (not isinstance(changed_paths, list) or not 1 <= len(changed_paths) <= 8192
                or len(changed_paths) != len(set(changed_paths))):
            raise RepositoryAtlasError("incremental update needs 1..8192 unique paths")
        if type(observed_at_ns) is not int or observed_at_ns < 0:
            raise RepositoryAtlasError("invalid index observation timestamp")
        if type(hash_contents) is not bool:
            raise RepositoryAtlasError("hash_contents must be boolean")
        changed: dict[str, IndexedFile | None] = {}
        for path in changed_paths:
            if not isinstance(path, str) or not path or len(path) > 2048:
                raise RepositoryAtlasError("invalid indexed path")
            if "\\" in path or path.startswith("/") or any(
                part in ("", ".", "..") for part in path.split("/")
            ):
                raise RepositoryAtlasError("noncanonical source path")
            full = self.root / path
            if not full.resolve().is_relative_to(self.root):
                raise RepositoryAtlasError("event path escapes canonical repository")
            if any(part in SKIP_DIRS for part in path.split("/")[:-1]) or _skip_file(Path(path).name):
                changed[path] = None
                continue
            # Explicitly reject traversal via symlinks in any parent directory.
            if any(parent.is_symlink() for parent in (
                self.root / Path(*Path(path).parts[:i])
                for i in range(1, len(Path(path).parts))
            )):
                changed[path] = None
                continue
            if not full.is_file() or full.is_symlink():
                changed[path] = None
                continue
            try:
                stat = full.stat(follow_symlinks=False)
                content_sha = self._hash(full, stat.st_size) if hash_contents else None
            except OSError as exc:
                raise RepositoryAtlasError("source changed during incremental indexing") from exc
            changed[path] = IndexedFile(
                path=path, owner_root=self._owner(path),
                feature=self._feature(path), suffix=full.suffix.lower(),
                bytes=stat.st_size, modified_ns=stat.st_mtime_ns,
                content_sha256=content_sha,
            )
        with self._lock:
            self._meta()
            previous = {
                row[0]: tuple(row[1:]) for row in self._db.execute(
                    "SELECT path,owner_root,feature,suffix,bytes,modified_ns,"
                    "content_sha256 FROM jeeves_atlas_files"
                )
            }
            additions = removals = modifications = 0
            for path, item in changed.items():
                before = previous.get(path)
                if item is None:
                    if before is not None:
                        removals += 1
                    previous.pop(path, None)
                    continue
                after = item.row()[1:]
                if before is None:
                    additions += 1
                elif before != after:
                    modifications += 1
                previous[path] = after
            if len(previous) > MAX_FILES:
                raise RepositoryAtlasError("indexed file cap exceeded")
            rebuilt = [IndexedFile(path, *values) for path, values
                       in sorted(previous.items())]
            digest = _canonical_sha(rebuilt)
            try:
                self._db.execute("BEGIN IMMEDIATE")
                for path, item in changed.items():
                    if item is None:
                        self._db.execute(
                            "DELETE FROM jeeves_atlas_files WHERE path=?", (path,),
                        )
                    else:
                        self._db.execute(
                            "INSERT INTO jeeves_atlas_files VALUES (?,?,?,?,?,?,?) "
                            "ON CONFLICT(path) DO UPDATE SET "
                            "owner_root=excluded.owner_root, feature=excluded.feature, "
                            "suffix=excluded.suffix, bytes=excluded.bytes, "
                            "modified_ns=excluded.modified_ns, "
                            "content_sha256=excluded.content_sha256",
                            item.row(),
                        )
                self._db.execute(
                    "UPDATE jeeves_atlas_meta "
                    "SET index_sha256=?, observed_at_ns=?, file_count=? WHERE singleton=1",
                    (digest, observed_at_ns, len(rebuilt)),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return AtlasRefresh(
                index_sha256=digest, observed_at_ns=observed_at_ns,
                file_count=len(rebuilt), added=additions, removed=removals,
                changed=modifications,
                hashed=sum(row.content_sha256 is not None for row in rebuilt),
            )

    def _meta(self) -> dict[str, Any]:
        record = self._db.execute(
            "SELECT schema,index_sha256,observed_at_ns,file_count "
            "FROM jeeves_atlas_meta WHERE singleton=1"
        ).fetchone()
        if record is None or record[0] != "jeeves.repository_file_atlas.v1":
            raise RepositoryAtlasError("atlas has not been refreshed by the host")
        return {
            "schema": record[0], "index_sha256": record[1],
            "observed_at_ns": record[2], "file_count": record[3],
        }

    def lookup(self, path: str) -> IndexedFile | None:
        """Resolve only exact source paths previously observed by the host."""
        if not isinstance(path, str) or not 1 <= len(path) <= 2048:
            raise RepositoryAtlasError("invalid indexed path identity")
        with self._lock:
            self._meta()
            result = self._db.execute(
                "SELECT path,owner_root,feature,suffix,bytes,modified_ns,"
                "content_sha256 FROM jeeves_atlas_files WHERE path=?",
                (path,),
            ).fetchone()
            return IndexedFile(*result) if result is not None else None

    def search(self, *, query: str = "", limit: int = 30, offset: int = 0,
               owner_root: str | None = None,
               feature: str | None = None) -> dict[str, Any]:
        """Page only index metadata. No source file content is model-visible."""
        if not isinstance(query, str) or len(query) > MAX_QUERY:
            raise RepositoryAtlasError("invalid atlas search text")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise RepositoryAtlasError("invalid atlas page size")
        if type(offset) is not int or not 0 <= offset <= MAX_FILES:
            raise RepositoryAtlasError("atlas page offset exceeded")
        if owner_root is not None and (not isinstance(owner_root, str) or len(owner_root) > 192):
            raise RepositoryAtlasError("invalid owner filter")
        if feature is not None and (not isinstance(feature, str) or len(feature) > 192):
            raise RepositoryAtlasError("invalid feature filter")
        # Escape LIKE metacharacters; query remains a literal substring.
        needle = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where = ["lower(path) LIKE ? ESCAPE '\\'"]
        params: list[Any] = ["%" + needle + "%"]
        if owner_root is not None:
            where.append("owner_root=?")
            params.append(owner_root)
        if feature is not None:
            where.append("feature=?")
            params.append(feature)
        conditions = " AND ".join(where)
        with self._lock:
            meta = self._meta()
            total = self._db.execute(
                "SELECT COUNT(*) FROM jeeves_atlas_files WHERE " + conditions,
                params,
            ).fetchone()[0]
            data = self._db.execute(
                "SELECT path,owner_root,feature,suffix,bytes,modified_ns,"
                "content_sha256 FROM jeeves_atlas_files WHERE " + conditions +
                " ORDER BY path LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
            selected = [IndexedFile(*row).as_dict() for row in data]
            return {
                **meta, "query": query, "owner_root": owner_root,
                "feature": feature, "total_matched": total,
                "offset": offset, "limit": limit,
                "has_more": offset + len(selected) < total,
                "files": selected, "execution_authority": "none",
                "validation": "filesystem index only; live capability proof required",
            }

    def exact_duplicate_groups(self, *, limit: int = 20) -> dict[str, Any]:
        """Return content-hash duplicate groups only when hashing was enabled."""
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise RepositoryAtlasError("invalid duplicate page limit")
        with self._lock:
            meta = self._meta()
            hashed_files = self._db.execute(
                "SELECT COUNT(*) FROM jeeves_atlas_files WHERE content_sha256 IS NOT NULL"
            ).fetchone()[0]
            digests = self._db.execute(
                "SELECT content_sha256,COUNT(*),SUM(bytes) "
                "FROM jeeves_atlas_files WHERE content_sha256 IS NOT NULL "
                "GROUP BY content_sha256 HAVING COUNT(*) > 1 "
                "ORDER BY COUNT(*) DESC,content_sha256 LIMIT ?",
                (limit,),
            ).fetchall()
            return {
                **meta,
                "hashed_files": hashed_files,
                "hash_coverage": "partial" if hashed_files < meta["file_count"] else "complete",
                "duplicate_groups": [
                    {
                        "content_sha256": digest,
                        "copies": count,
                        "total_bytes": size,
                        "paths": [
                            row[0] for row in self._db.execute(
                                "SELECT path FROM jeeves_atlas_files "
                                "WHERE content_sha256=? ORDER BY path LIMIT 64",
                                (digest,),
                            )
                        ],
                    } for digest, count, size in digests
                ],
                "execution_authority": "none",
            }

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "JeevesRepositoryFileAtlas":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()



def register_repository_atlas_tools(
    registry: Any, *, atlas: JeevesRepositoryFileAtlas,
    read_authorize: Any,
) -> tuple[str, ...]:
    """Add two READ_ONLY, tenant-scoped tools to the existing Jeeves registry."""
    from skeleton.jeeves.agent.tools import (
        ArgumentRule, ToolDenied, ToolRegistry, ToolSpec,
    )
    from skeleton.jeeves.agent.types import RiskTier
    if not isinstance(registry, ToolRegistry) or not isinstance(atlas, JeevesRepositoryFileAtlas):
        raise TypeError("host registry and repository atlas required")
    if not callable(read_authorize):
        raise TypeError("host read authorizer required for repository atlas")

    def _permit(name: str, args: dict[str, Any], context: Any) -> None:
        payload = {"tool": name, "arguments": args}
        intent = sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            allow_nan=False, ensure_ascii=True,
        ).encode("utf-8")).hexdigest()
        if read_authorize(name, intent, context) is not True:
            raise ToolDenied("host denied source atlas access")

    def _search(args: dict[str, Any], context: Any) -> dict[str, Any]:
        _permit("app.files", args, context)
        return atlas.search(
            query=args.get("query", ""),
            limit=args.get("limit", 30),
            offset=args.get("offset", 0),
            owner_root=args.get("owner_root"),
            feature=args.get("feature"),
        )

    def _duplicates(args: dict[str, Any], context: Any) -> dict[str, Any]:
        _permit("app.exact_duplicates", args, context)
        return atlas.exact_duplicate_groups(limit=args.get("limit", 20))

    entries = (
        (ToolSpec(
            name="app.files",
            description="Query bounded indexed source paths, owners and feature families.",
            risk=RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("query", "string", required=False, max_length=MAX_QUERY),
                ArgumentRule("limit", "integer", required=False, minimum=1, maximum=MAX_PAGE),
                ArgumentRule("offset", "integer", required=False, minimum=0, maximum=MAX_FILES),
                ArgumentRule("owner_root", "string", required=False, max_length=192),
                ArgumentRule("feature", "string", required=False, max_length=192),
            ),
        ), _search),
        (ToolSpec(
            name="app.exact_duplicates",
            description="Find fingerprint-identical indexed source files; no file reads.",
            risk=RiskTier.READ_ONLY,
            arguments=(ArgumentRule(
                "limit", "integer", required=False, minimum=1, maximum=MAX_PAGE,
            ),),
        ), _duplicates),
    )
    for spec, handler in entries:
        registry.register(spec, handler)
    return tuple(spec.name for spec, _ in entries)


__all__ = [
    "RepositoryAtlasError", "IndexedFile", "AtlasRefresh",
    "JeevesRepositoryFileAtlas", "register_repository_atlas_tools",
]
