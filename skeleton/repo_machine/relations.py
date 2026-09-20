"""File-level internal dependency relations and reachability."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class Relation:
    source_path: str
    target_path: str
    source_zone: str
    target_zone: str
    imported_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_path": self.source_path,
            "target_path": self.target_path,
            "source_zone": self.source_zone,
            "target_zone": self.target_zone,
            "imported_name": self.imported_name,
        }


def _module_candidates(imported: str) -> tuple[str, ...]:
    name = imported.lstrip(".")
    if not name:
        return ()
    path = name.replace(".", "/")
    return (
        path + ".py",
        path + "/__init__.py",
        path + ".ts",
        path + ".tsx",
        path + ".js",
        path + ".jsx",
        path + ".java",
    )


def build_relations(model: RepositoryModel) -> tuple[Relation, ...]:
    by_path = {item.path: item for item in model.files}
    result: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for source in model.files:
        for imported in source.imports:
            for candidate in _module_candidates(imported):
                target = by_path.get(candidate)
                if target is None:
                    continue
                key = (source.path, target.path, imported)
                if key in seen:
                    break
                seen.add(key)
                result.append(Relation(
                    source_path=source.path,
                    target_path=target.path,
                    source_zone=source.zone,
                    target_zone=target.zone,
                    imported_name=imported,
                ))
                break
    return tuple(sorted(
        result,
        key=lambda item: (item.source_path, item.target_path, item.imported_name),
    ))


def reachable_files(
    model: RepositoryModel,
    start_path: str,
    *,
    reverse: bool = False,
    max_depth: int = 4,
    limit: int = 500,
) -> tuple[str, ...]:
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 32:
        raise ValueError("max_depth must be in [0,32]")
    relations = build_relations(model)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        source = relation.target_path if reverse else relation.source_path
        target = relation.source_path if reverse else relation.target_path
        adjacency[source].add(target)

    visited = {start_path}
    queue = deque([(start_path, 0)])
    result: list[str] = []
    while queue and len(result) < limit:
        path, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in sorted(adjacency.get(path, ())):
            if target in visited:
                continue
            visited.add(target)
            result.append(target)
            queue.append((target, depth + 1))
            if len(result) >= limit:
                break
    return tuple(result)
