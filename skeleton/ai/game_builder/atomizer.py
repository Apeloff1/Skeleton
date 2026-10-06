"""Pixel-to-project artifact atom lineage for the AI game builder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import canonical_digest


class AtomGraphError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactAtom:
    atom_id: str
    kind: str
    content_digest: str
    artifact_id: str
    canon_digest: str
    parent_id: str | None = None
    dependency_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("atom_id", "kind", "artifact_id"):
            if not getattr(self, label).strip():
                raise ValueError(f"{label} must be non-empty")
        if len(self.content_digest) < 16 or len(self.canon_digest) < 16:
            raise ValueError("content/canon digests must be stable")
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("dependency_ids must be unique")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("source_ids must be unique")
        if self.atom_id in self.dependency_ids:
            raise ValueError("atom cannot depend on itself")

    def to_payload(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "atom_id": self.atom_id,
            "canon_digest": self.canon_digest,
            "content_digest": self.content_digest,
            "dependency_ids": list(self.dependency_ids),
            "kind": self.kind,
            "parent_id": self.parent_id,
            "source_ids": list(self.source_ids),
        }


class AtomGraph:
    """Append-only lineage graph with deterministic blast-radius traversal."""

    def __init__(self) -> None:
        self._atoms: dict[str, ArtifactAtom] = {}
        self._children: dict[str, list[str]] = {}
        self._dependents: dict[str, set[str]] = {}

    def add(self, atom: ArtifactAtom) -> None:
        if atom.atom_id in self._atoms:
            raise AtomGraphError(f"atom already exists: {atom.atom_id}")
        if atom.parent_id is not None and atom.parent_id not in self._atoms:
            raise AtomGraphError(f"parent atom does not exist: {atom.parent_id}")
        missing = [item for item in atom.dependency_ids if item not in self._atoms]
        if missing:
            raise AtomGraphError(f"dependency atoms do not exist: {sorted(missing)}")
        if atom.parent_id is not None:
            self._children.setdefault(atom.parent_id, []).append(atom.atom_id)
        for dependency in atom.dependency_ids:
            self._dependents.setdefault(dependency, set()).add(atom.atom_id)
        self._atoms[atom.atom_id] = atom

    def require(self, atom_id: str) -> ArtifactAtom:
        try:
            return self._atoms[atom_id]
        except KeyError as exc:
            raise AtomGraphError(f"unknown atom: {atom_id}") from exc

    def trace_to_root(self, atom_id: str) -> tuple[str, ...]:
        current = self.require(atom_id)
        chain = [current.atom_id]
        seen = {current.atom_id}
        while current.parent_id is not None:
            if current.parent_id in seen:
                raise AtomGraphError("parent cycle detected")
            seen.add(current.parent_id)
            current = self.require(current.parent_id)
            chain.append(current.atom_id)
        return tuple(reversed(chain))

    def descendants(self, atom_id: str) -> tuple[str, ...]:
        self.require(atom_id)
        ordered: list[str] = []
        stack = list(reversed(self._children.get(atom_id, ())))
        while stack:
            current = stack.pop()
            ordered.append(current)
            stack.extend(reversed(self._children.get(current, ())))
        return tuple(ordered)

    def dependency_closure(self, atom_id: str) -> tuple[str, ...]:
        self.require(atom_id)
        seen: set[str] = set()
        stack = list(self.require(atom_id).dependency_ids)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.require(current).dependency_ids)
        return tuple(sorted(seen))

    def blast_radius(self, changed_atom_ids: Iterable[str]) -> tuple[str, ...]:
        roots = tuple(changed_atom_ids)
        for atom_id in roots:
            self.require(atom_id)
        seen = set(roots)
        stack = list(roots)
        while stack:
            current = stack.pop()
            next_ids = set(self._children.get(current, ()))
            next_ids.update(self._dependents.get(current, ()))
            for dependent in sorted(next_ids):
                if dependent not in seen:
                    seen.add(dependent)
                    stack.append(dependent)
        return tuple(sorted(seen))

    def sources_for(self, atom_id: str, *, include_dependencies: bool = True) -> tuple[str, ...]:
        atom = self.require(atom_id)
        source_ids = set(atom.source_ids)
        if include_dependencies:
            for dependency in self.dependency_closure(atom_id):
                source_ids.update(self.require(dependency).source_ids)
        return tuple(sorted(source_ids))

    def assert_parent_context(self, atom_id: str) -> None:
        atom = self.require(atom_id)
        if atom.parent_id is None:
            return
        lineage = self.trace_to_root(atom_id)
        if len(lineage) < 2:
            raise AtomGraphError("non-root atom lost parent context")
        if self.require(lineage[-1]).artifact_id != atom.artifact_id:
            raise AtomGraphError("atom lineage crossed artifact identity")

    def snapshot(self) -> dict[str, object]:
        rows = [self._atoms[key].to_payload() for key in sorted(self._atoms)]
        core: dict[str, object] = {
            "atom_count": len(rows),
            "atoms": rows,
            "roots": sorted(
                atom.atom_id for atom in self._atoms.values() if atom.parent_id is None
            ),
        }
        return {**core, "digest": canonical_digest(core)}
