"""Path normalization and matching for workspace transactions."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from typing import Iterable, Iterator

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE = re.compile(r"^[A-Za-z]:")


class WorkspacePathError(ValueError):
    pass


def normalize_relative_path(value: str | os.PathLike[str]) -> str:
    raw = os.fspath(value)
    if not isinstance(raw, str):
        raise WorkspacePathError("path must be text")
    if not raw:
        raise WorkspacePathError("path cannot be empty")
    text = raw.replace("\\", "/")
    if text.startswith("/") or _DRIVE.match(text):
        raise WorkspacePathError("workspace path must be relative")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise WorkspacePathError("workspace path escapes root")
            parts.pop()
            continue
        if _CONTROL.search(part):
            raise WorkspacePathError("workspace path contains control characters")
        parts.append(part)
    if not parts:
        raise WorkspacePathError("path normalizes to root")
    return "/".join(parts)


def root_fingerprint(root: Path) -> str:
    resolved = root.expanduser().resolve(strict=True)
    return hashlib.sha256(os.fsencode(str(resolved))).hexdigest()


def lexical_join_under_root(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    base = root.expanduser().resolve(strict=True)
    candidate = base.joinpath(*PurePosixPath(normalized).parts)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise WorkspacePathError("workspace path escapes root") from exc
    return candidate


def resolved_join_under_root(root: Path, relative: str, *, strict: bool = False) -> Path:
    candidate = lexical_join_under_root(root, relative)
    base = root.expanduser().resolve(strict=True)
    try:
        resolved = candidate.resolve(strict=strict)
    except (OSError, RuntimeError) as exc:
        raise WorkspacePathError("workspace path cannot be resolved") from exc
    if resolved != base and base not in resolved.parents:
        raise WorkspacePathError("resolved workspace path escapes root")
    return resolved


def path_depth(path: str) -> int:
    return len(PurePosixPath(normalize_relative_path(path)).parts)


def parent_paths(path: str) -> tuple[str, ...]:
    pure = PurePosixPath(normalize_relative_path(path))
    result: list[str] = []
    current = pure.parent
    while str(current) not in {"", "."}:
        result.append(current.as_posix())
        current = current.parent
    return tuple(reversed(result))


def validate_pattern(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise WorkspacePathError("pattern must be non-empty text")
    value = pattern.replace("\\", "/")
    if value.startswith("/") or _DRIVE.match(value) or _CONTROL.search(value):
        raise WorkspacePathError("pattern must be safe and workspace-relative")
    return value


@dataclass(frozen=True)
class PathMatcher:
    include: tuple[str, ...] = ("**",)
    exclude: tuple[str, ...] = ()
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        include = tuple(validate_pattern(p) for p in self.include)
        exclude = tuple(validate_pattern(p) for p in self.exclude)
        if not include:
            raise WorkspacePathError("at least one include pattern is required")
        object.__setattr__(self, "include", include)
        object.__setattr__(self, "exclude", exclude)

    def _match_one(self, path: str, pattern: str) -> bool:
        candidate = path if self.case_sensitive else path.casefold()
        wanted = pattern if self.case_sensitive else pattern.casefold()
        pure = PurePosixPath(candidate)
        return (
            pure.match(wanted)
            or (wanted.startswith("**/") and pure.match(wanted[3:]))
            or fnmatch.fnmatchcase(candidate, wanted)
        )

    def matches(self, path: str) -> bool:
        normalized = normalize_relative_path(path)
        return (
            any(self._match_one(normalized, p) for p in self.include)
            and not any(self._match_one(normalized, p) for p in self.exclude)
        )

    def excluded(self, path: str) -> bool:
        normalized = normalize_relative_path(path)
        return any(self._match_one(normalized, p) for p in self.exclude)

    def may_descend(self, directory: str) -> bool:
        return not self.excluded(normalize_relative_path(directory))

    def to_dict(self) -> dict[str, object]:
        return {
            "include": list(self.include),
            "exclude": list(self.exclude),
            "case_sensitive": self.case_sensitive,
        }


@dataclass(frozen=True)
class PathSet:
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "paths",
            tuple(sorted({normalize_relative_path(p) for p in self.paths})),
        )

    def contains(self, path: str) -> bool:
        return normalize_relative_path(path) in self.paths

    def contains_parent_of(self, path: str) -> bool:
        value = normalize_relative_path(path)
        return any(value == p or value.startswith(p.rstrip("/") + "/") for p in self.paths)

    def under(self, parent: str) -> tuple[str, ...]:
        value = normalize_relative_path(parent)
        prefix = value.rstrip("/") + "/"
        return tuple(p for p in self.paths if p == value or p.startswith(prefix))

    def __iter__(self) -> Iterator[str]:
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


def collapse_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized = sorted({normalize_relative_path(p) for p in paths})
    result: list[str] = []
    for path in normalized:
        if any(path == parent or path.startswith(parent + "/") for parent in result):
            continue
        result.append(path)
    return tuple(result)
