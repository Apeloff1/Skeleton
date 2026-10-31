"""B041 scene graph contract: typed, diffable, serializable scenes.

Engine adapters consume ``SceneDocument.to_dict`` and ``SceneDiff`` ops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._digest import digest

SCHEMA = "skeleton.worldsim.scene/v1"


class SceneContractError(ValueError):
    pass


@dataclass(frozen=True)
class SceneEntity:
    entity_id: str
    kind: str
    parent_id: str | None = None
    transform: tuple[float, float, float] = (0.0, 0.0, 0.0)
    props: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entity_id or not self.kind:
            raise SceneContractError("entity_id and kind are required")
        if len(self.transform) != 3:
            raise SceneContractError("transform must be xyz")
        object.__setattr__(self, "transform", tuple(float(v) for v in self.transform))

    def to_dict(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "kind": self.kind, "parent_id": self.parent_id,
                "transform": list(self.transform), "props": dict(sorted(self.props.items()))}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SceneEntity":
        return cls(str(d["entity_id"]), str(d["kind"]), d.get("parent_id"),
                   tuple(float(v) for v in d.get("transform", (0, 0, 0))), dict(d.get("props", {})))


@dataclass(frozen=True)
class SceneDocument:
    scene_id: str
    entities: tuple[SceneEntity, ...]

    def __post_init__(self) -> None:
        ids = [e.entity_id for e in self.entities]
        if len(set(ids)) != len(ids):
            raise SceneContractError("duplicate entity ids")
        known = set(ids)
        for e in self.entities:
            if e.parent_id is not None and e.parent_id not in known:
                raise SceneContractError(f"unknown parent {e.parent_id}")
        parents = {e.entity_id: e.parent_id for e in self.entities}
        for start in ids:
            seen, cur = set(), start
            while cur is not None:
                if cur in seen:
                    raise SceneContractError("parent cycle")
                seen.add(cur)
                cur = parents[cur]

    def by_id(self) -> dict[str, SceneEntity]:
        return {e.entity_id: e for e in self.entities}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "scene_id": self.scene_id,
                "entities": [e.to_dict() for e in sorted(self.entities, key=lambda e: e.entity_id)]}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SceneDocument":
        if d.get("schema") != SCHEMA:
            raise SceneContractError("schema mismatch")
        return cls(str(d["scene_id"]), tuple(SceneEntity.from_dict(e) for e in d["entities"]))

    def digest(self) -> str:
        return digest(self.to_dict())


def diff_scenes(before: SceneDocument, after: SceneDocument) -> list[dict[str, Any]]:
    """Deterministic op list: add / remove / update (sorted by entity id)."""
    a, b = before.by_id(), after.by_id()
    ops: list[dict[str, Any]] = []
    for eid in sorted(set(a) | set(b)):
        if eid not in b:
            ops.append({"op": "remove", "entity_id": eid})
        elif eid not in a:
            ops.append({"op": "add", "entity": b[eid].to_dict()})
        elif a[eid].to_dict() != b[eid].to_dict():
            ops.append({"op": "update", "entity": b[eid].to_dict()})
    return ops


def apply_diff(scene: SceneDocument, ops: list[Mapping[str, Any]]) -> SceneDocument:
    ents = scene.by_id()
    for op in ops:
        kind = op.get("op")
        if kind == "remove":
            ents.pop(str(op["entity_id"]), None)
        elif kind in ("add", "update"):
            e = SceneEntity.from_dict(op["entity"])
            ents[e.entity_id] = e
        else:
            raise SceneContractError(f"unknown op {kind}")
    return SceneDocument(scene.scene_id, tuple(ents[k] for k in sorted(ents)))


def from_flgb_scene_graph(scene_id: str, graph: Any) -> SceneDocument:
    """Adapter from the existing ``flgb_editor_runtime.SceneGraph``."""
    out = []
    for n in getattr(graph, "nodes", ()):
        d = dict(n.__dict__)
        eid = str(d.pop("node_id", d.pop("id", "")))
        parent = d.pop("parent_id", None) or None
        kind = str(d.pop("kind", d.pop("node_type", "node")))
        out.append(SceneEntity(eid, kind, parent, props={k: v for k, v in d.items() if isinstance(v, (str, int, float, bool))}))
    return SceneDocument(scene_id, tuple(out))
