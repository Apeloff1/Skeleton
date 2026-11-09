"""Composable deterministic mutation rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable, Protocol

from skeleton.shells.workspace_txn.pathing import PathMatcher, path_depth
from skeleton.shells.workspace_txn.types import (
    ChangeSet,
    PolicyViolation,
    WorkspaceChangeKind,
    WorkspaceEntryKind,
)


class MutationRule(Protocol):
    code: str

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]: ...
    def to_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class MaxChangesRule:
    maximum: int
    code: str = "max_changes"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        if changes.statistics.total_changes <= self.maximum:
            return ()
        return (PolicyViolation(self.code, "", f"change count exceeds {self.maximum}"),)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "maximum": self.maximum, "code": self.code}


@dataclass(frozen=True)
class MaxKindRule:
    kind: WorkspaceChangeKind
    maximum: int
    code: str = "max_kind"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        count = sum(1 for item in changes.changes if item.kind is self.kind)
        if count <= self.maximum:
            return ()
        return (PolicyViolation(self.code, "", f"{self.kind.value} count exceeds {self.maximum}"),)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": type(self).__name__,
            "kind": self.kind.value,
            "maximum": self.maximum,
            "code": self.code,
        }


@dataclass(frozen=True)
class MaxBytesRule:
    added: int | None = None
    removed: int | None = None
    code: str = "max_bytes"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result: list[PolicyViolation] = []
        if self.added is not None and changes.statistics.bytes_added > self.added:
            result.append(PolicyViolation(self.code, "", f"added bytes exceed {self.added}"))
        if self.removed is not None and changes.statistics.bytes_removed > self.removed:
            result.append(PolicyViolation(self.code, "", f"removed bytes exceed {self.removed}"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "added": self.added, "removed": self.removed, "code": self.code}


@dataclass(frozen=True)
class MaxFileSizeRule:
    maximum: int
    code: str = "max_file_size"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        return tuple(
            PolicyViolation(self.code, item.path, f"file size exceeds {self.maximum}")
            for item in changes.changes
            if item.after is not None
            and item.after.kind is WorkspaceEntryKind.FILE
            and item.after.size > self.maximum
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "maximum": self.maximum, "code": self.code}


@dataclass(frozen=True)
class PathAllowRule:
    matcher: PathMatcher
    code: str = "path_not_allowed"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result: list[PolicyViolation] = []
        for item in changes.changes:
            for path in filter(None, (item.path, item.old_path)):
                if not self.matcher.matches(path):
                    result.append(PolicyViolation(self.code, path, "changed path is outside mutation allowlist"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "matcher": self.matcher.to_dict(), "code": self.code}


@dataclass(frozen=True)
class PathDenyRule:
    matcher: PathMatcher
    code: str = "path_denied"
    severity: str = "critical"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result: list[PolicyViolation] = []
        for item in changes.changes:
            for path in filter(None, (item.path, item.old_path)):
                if self.matcher.matches(path):
                    result.append(PolicyViolation(self.code, path, "changed path is protected", self.severity))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": type(self).__name__,
            "matcher": self.matcher.to_dict(),
            "code": self.code,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ExtensionDenyRule:
    extensions: frozenset[str]
    code: str = "extension_denied"
    severity: str = "error"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "extensions",
            frozenset(ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in self.extensions),
        )

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result = []
        for item in changes.changes:
            suffix = PurePosixPath(item.path).suffix.lower()
            if suffix in self.extensions:
                result.append(PolicyViolation(self.code, item.path, f"extension {suffix} is denied", self.severity))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "extensions": sorted(self.extensions), "code": self.code}


@dataclass(frozen=True)
class FilenameDenyRule:
    names: frozenset[str]
    case_sensitive: bool = False
    code: str = "filename_denied"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        wanted = self.names if self.case_sensitive else frozenset(name.casefold() for name in self.names)
        result = []
        for item in changes.changes:
            name = PurePosixPath(item.path).name
            candidate = name if self.case_sensitive else name.casefold()
            if candidate in wanted:
                result.append(PolicyViolation(self.code, item.path, "filename is protected", "critical"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "names": sorted(self.names), "code": self.code}


@dataclass(frozen=True)
class RegexPathDenyRule:
    patterns: tuple[str, ...]
    code: str = "path_pattern_denied"

    def __post_init__(self) -> None:
        for pattern in self.patterns:
            re.compile(pattern)

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result = []
        for item in changes.changes:
            for pattern in self.patterns:
                if re.search(pattern, item.path):
                    result.append(PolicyViolation(self.code, item.path, "path matched protected pattern", "critical"))
                    break
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "patterns": list(self.patterns), "code": self.code}


@dataclass(frozen=True)
class MaxDepthRule:
    maximum: int
    code: str = "max_path_depth"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        return tuple(
            PolicyViolation(self.code, item.path, f"path depth exceeds {self.maximum}")
            for item in changes.changes
            if path_depth(item.path) > self.maximum
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "maximum": self.maximum, "code": self.code}


@dataclass(frozen=True)
class SymlinkMutationRule:
    allow_create: bool = False
    allow_modify: bool = False
    allow_delete: bool = False
    code: str = "symlink_mutation"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result: list[PolicyViolation] = []
        for item in changes.changes:
            before_link = item.before is not None and item.before.kind is WorkspaceEntryKind.SYMLINK
            after_link = item.after is not None and item.after.kind is WorkspaceEntryKind.SYMLINK
            denied = (
                item.kind is WorkspaceChangeKind.CREATED and after_link and not self.allow_create
                or item.kind is WorkspaceChangeKind.DELETED and before_link and not self.allow_delete
                or item.kind not in {WorkspaceChangeKind.CREATED, WorkspaceChangeKind.DELETED}
                and (before_link or after_link)
                and not self.allow_modify
            )
            if denied:
                result.append(PolicyViolation(self.code, item.path, "symlink mutation is not allowed", "critical"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": type(self).__name__,
            "allow_create": self.allow_create,
            "allow_modify": self.allow_modify,
            "allow_delete": self.allow_delete,
            "code": self.code,
        }


@dataclass(frozen=True)
class ExecutableBitRule:
    allow_new_executable: bool = False
    allow_mode_change: bool = True
    code: str = "executable_bit"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        result = []
        for item in changes.changes:
            before_exec = bool(item.before and item.before.mode & 0o111)
            after_exec = bool(item.after and item.after.mode & 0o111)
            if not before_exec and after_exec and not self.allow_new_executable:
                result.append(PolicyViolation(self.code, item.path, "new executable bit is not allowed"))
            elif before_exec != after_exec and not self.allow_mode_change:
                result.append(PolicyViolation(self.code, item.path, "executable mode change is not allowed"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": type(self).__name__,
            "allow_new_executable": self.allow_new_executable,
            "allow_mode_change": self.allow_mode_change,
            "code": self.code,
        }


@dataclass(frozen=True)
class DeleteRule:
    allow: bool = True
    matcher: PathMatcher | None = None
    code: str = "delete_denied"

    def evaluate(self, changes: ChangeSet) -> tuple[PolicyViolation, ...]:
        if self.allow and self.matcher is None:
            return ()
        result = []
        for item in changes.changes:
            if item.kind is not WorkspaceChangeKind.DELETED:
                continue
            if not self.allow or (self.matcher is not None and self.matcher.matches(item.path)):
                result.append(PolicyViolation(self.code, item.path, "deletion is not permitted"))
        return tuple(result)

    def to_dict(self) -> dict[str, object]:
        return {"type": type(self).__name__, "allow": self.allow, "code": self.code}


def evaluate_rules(rules: Iterable[MutationRule], changes: ChangeSet) -> tuple[PolicyViolation, ...]:
    violations: list[PolicyViolation] = []
    for rule in rules:
        violations.extend(rule.evaluate(changes))
    severity_rank = {"critical": 0, "error": 1, "warning": 2}
    violations.sort(key=lambda v: (severity_rank[v.severity], v.code, v.path, v.detail))
    return tuple(violations)
