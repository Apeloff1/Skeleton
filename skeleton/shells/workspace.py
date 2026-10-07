"""Workspace confinement helpers for shell execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from skeleton.shells.errors import ShellErrorCode, ShellErrorContext, WorkspaceRejected


def _resolve_dir(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("workspace root does not exist") from exc
    if not resolved.is_dir():
        raise ValueError("workspace root must be a directory")
    return resolved


@dataclass(frozen=True)
class WorkspacePolicy:
    roots: tuple[Path, ...]
    deny_roots: tuple[Path, ...] = ()
    max_depth: int | None = None

    def __post_init__(self) -> None:
        roots = tuple(_resolve_dir(Path(root)) for root in self.roots)
        deny = tuple(_resolve_dir(Path(root)) for root in self.deny_roots)
        if not roots:
            raise ValueError("at least one workspace root is required")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "deny_roots", deny)

    @staticmethod
    def _contains(root: Path, path: Path) -> bool:
        return path == root or root in path.parents

    def resolve(self, command: str, path: Path | str | None = None) -> Path:
        selected = self.roots[0] if path is None else Path(path)
        try:
            resolved = selected.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WorkspaceRejected(
                ShellErrorContext(ShellErrorCode.WORKSPACE, command=command, detail="working directory does not exist")
            ) from exc
        if not resolved.is_dir():
            raise WorkspaceRejected(
                ShellErrorContext(ShellErrorCode.WORKSPACE, command=command, detail="working directory is not a directory")
            )
        matching = [root for root in self.roots if self._contains(root, resolved)]
        if not matching:
            raise WorkspaceRejected(
                ShellErrorContext(ShellErrorCode.WORKSPACE, command=command, detail="working directory is outside allowed roots")
            )
        if any(self._contains(root, resolved) for root in self.deny_roots):
            raise WorkspaceRejected(
                ShellErrorContext(ShellErrorCode.WORKSPACE, command=command, detail="working directory is under a denied root")
            )
        if self.max_depth is not None:
            nearest = max(matching, key=lambda root: len(root.parts))
            depth = len(resolved.relative_to(nearest).parts)
            if depth > self.max_depth:
                raise WorkspaceRejected(
                    ShellErrorContext(ShellErrorCode.WORKSPACE, command=command, detail="working directory exceeds depth limit")
                )
        return resolved

    def narrow(self, roots: Iterable[Path | str], *, max_depth: int | None = None) -> "WorkspacePolicy":
        child_roots = tuple(_resolve_dir(Path(root)) for root in roots)
        for child in child_roots:
            if not any(self._contains(parent, child) for parent in self.roots):
                raise ValueError("child workspace root would widen authority")
        child_depth = self.max_depth if max_depth is None else max_depth
        if self.max_depth is not None and child_depth is not None and child_depth > self.max_depth:
            raise ValueError("child max_depth would widen authority")
        return WorkspacePolicy(child_roots, deny_roots=self.deny_roots, max_depth=child_depth)
