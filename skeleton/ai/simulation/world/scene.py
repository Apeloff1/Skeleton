"""Engine-neutral world/scene state graph.

This module is the persistence and hierarchy boundary for later terrain,
streaming, ecology, and replay consumers. It has no renderer, Godot, gameplay
mechanics, networking, or procedural-terrain dependency.

Time is an explicit integer tick supplied by the caller. Traversal,
serialization, and digests are deterministic. Graph operations are bounded
and fail closed on cycles, orphans, invalid references, and schema mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any, Final, Iterable, Mapping

from skeleton.kernel.errors import KernelError

SCHEMA_NAME: Final = "world.scene_state.v1"
SCHEMA_VERSION: Final = 1

MAX_ENTITIES: Final = 1024
MAX_CHILDREN: Final = 128
MAX_DEPTH: Final = 32
MAX_ID_CHARS: Final = 64
MAX_KIND_CHARS: Final = 64
MAX_NAME_CHARS: Final = 128
MAX_ATTRIBUTE_KEYS: Final = 16
MAX_ATTRIBUTE_BYTES: Final = 2048
MAX_PAYLOAD_BYTES: Final = 1_048_576
MAX_TICK: Final = 2**53 - 1

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
_PAYLOAD_KEYS = frozenset(
    {"schema", "schema_version", "world_id", "tick", "revision", "roots", "entities"}
)
_ENTITY_KEYS = frozenset(
    {
        "entity_id",
        "kind",
        "parent_id",
        "name",
        "child_ids",
        "transform",
        "attributes",
        "created_tick",
        "revised_tick",
    }
)
_TRANSFORM_KEYS = frozenset({"translation", "rotation", "scale"})


class WorldSceneError(KernelError):
    code = "WLD.SCENE"
    http_status = 422


class WorldBoundError(WorldSceneError):
    code = "WLD.BOUND"
    http_status = 400


class WorldReferenceError(WorldSceneError):
    code = "WLD.INVALID_REF"
    http_status = 400


class WorldCycleError(WorldSceneError):
    code = "WLD.CYCLE"
    http_status = 409


class WorldOrphanError(WorldSceneError):
    code = "WLD.ORPHAN"
    http_status = 409


class WorldSchemaError(WorldSceneError):
    code = "WLD.SCHEMA"
    http_status = 422


class WorldTimeError(WorldSceneError):
    code = "WLD.TIME"
    http_status = 400


@dataclass(frozen=True, slots=True)
class GraphDiagnosis:
    """Deterministic inspection result for a payload or live graph."""

    cycles: tuple[tuple[str, ...], ...] = ()
    orphans: tuple[str, ...] = ()
    invalid_references: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class Transform:
    """Engine-neutral spatial pose. Euler components are caller-defined units."""

    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "translation", _vec3("translation", self.translation))
        object.__setattr__(self, "rotation", _vec3("rotation", self.rotation))
        object.__setattr__(self, "scale", _vec3("scale", self.scale))

    def to_payload(self) -> dict[str, list[float]]:
        return {
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "translation": list(self.translation),
        }

    @classmethod
    def from_payload(cls, payload: object) -> "Transform":
        if not isinstance(payload, Mapping):
            raise WorldSceneError("transform must be a mapping")
        extra = set(payload) - _TRANSFORM_KEYS
        if extra:
            raise WorldSchemaError(
                "transform has unknown fields",
                context={"fields": tuple(sorted(extra))},
            )
        missing = _TRANSFORM_KEYS - set(payload)
        if missing:
            raise WorldSchemaError(
                "transform is missing fields",
                context={"fields": tuple(sorted(missing))},
            )
        return cls(
            translation=_vec3("translation", payload["translation"]),
            rotation=_vec3("rotation", payload["rotation"]),
            scale=_vec3("scale", payload["scale"]),
        )


@dataclass(frozen=True, slots=True)
class SceneEntity:
    """One node in the world/scene forest. Child order lives on the graph."""

    entity_id: str
    kind: str
    parent_id: str | None
    name: str
    transform: Transform
    attributes: Mapping[str, Any]
    created_tick: int
    revised_tick: int

    def to_payload(self, child_ids: tuple[str, ...]) -> dict[str, Any]:
        return {
            "attributes": {key: self.attributes[key] for key in sorted(self.attributes)},
            "child_ids": list(child_ids),
            "created_tick": self.created_tick,
            "entity_id": self.entity_id,
            "kind": self.kind,
            "name": self.name,
            "parent_id": self.parent_id,
            "revised_tick": self.revised_tick,
            "transform": self.transform.to_payload(),
        }


class WorldState:
    """Deterministic, bounded scene graph with explicit time and stable IDs."""

    def __init__(
        self,
        world_id: str,
        *,
        tick: int = 0,
        max_entities: int = MAX_ENTITIES,
        max_children: int = MAX_CHILDREN,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        self._world_id = _identifier("world_id", world_id)
        self._tick = _absolute_tick(tick)
        self._revision = 0
        self._max_entities = _bound_limit("max_entities", max_entities, MAX_ENTITIES)
        self._max_children = _bound_limit("max_children", max_children, MAX_CHILDREN)
        self._max_depth = _bound_limit("max_depth", max_depth, MAX_DEPTH)
        self._entities: dict[str, SceneEntity] = {}
        self._roots: list[str] = []
        self._children: dict[str, list[str]] = {}

    @property
    def world_id(self) -> str:
        return self._world_id

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def schema(self) -> str:
        return SCHEMA_NAME

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    def spawn(
        self,
        entity_id: str,
        *,
        kind: str,
        tick: int,
        parent_id: str | None = None,
        name: str = "",
        transform: Transform | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> SceneEntity:
        entity_id = _identifier("entity_id", entity_id)
        if entity_id in self._entities:
            raise WorldSceneError(
                "entity already exists",
                context={"entity_id": entity_id},
            )
        if self.entity_count >= self._max_entities:
            raise WorldBoundError(
                "entity bound exceeded",
                context={"maximum": self._max_entities},
            )
        applied = _monotonic_tick(tick, current=self._tick)
        parent = self._require_parent(parent_id)
        siblings = self._sibling_list(parent)
        if len(siblings) >= self._max_children:
            raise WorldBoundError(
                "child bound exceeded",
                context={"parent_id": parent, "maximum": self._max_children},
            )
        depth = 0 if parent is None else self._depth(parent) + 1
        if depth > self._max_depth:
            raise WorldBoundError(
                "depth bound exceeded",
                context={"entity_id": entity_id, "maximum": self._max_depth},
            )
        entity = SceneEntity(
            entity_id=entity_id,
            kind=_identifier("kind", kind, maximum=MAX_KIND_CHARS),
            parent_id=parent,
            name=_name(name, default=entity_id),
            transform=transform if transform is not None else Transform(),
            attributes=_attributes(attributes),
            created_tick=applied,
            revised_tick=applied,
        )
        self._entities[entity_id] = entity
        siblings.append(entity_id)
        self._tick = applied
        self._revision += 1
        return entity

    def reparent(self, entity_id: str, parent_id: str | None, *, tick: int) -> SceneEntity:
        entity = self.require(entity_id)
        applied = _monotonic_tick(tick, current=self._tick)
        parent = self._require_parent(parent_id)
        if parent == entity.entity_id:
            raise WorldCycleError(
                "entity cannot parent itself",
                context={"entity_id": entity.entity_id},
            )
        if parent is not None and self._is_ancestor(entity.entity_id, parent):
            raise WorldCycleError(
                "reparent would create a cycle",
                context={"entity_id": entity.entity_id, "parent_id": parent},
            )
        if parent == entity.parent_id:
            self._tick = applied
            updated = replace(entity, revised_tick=applied)
            self._entities[entity.entity_id] = updated
            self._revision += 1
            return updated
        siblings = self._sibling_list(parent)
        if len(siblings) >= self._max_children:
            raise WorldBoundError(
                "child bound exceeded",
                context={"parent_id": parent, "maximum": self._max_children},
            )
        new_depth = 0 if parent is None else self._depth(parent) + 1
        if new_depth + self._height(entity.entity_id) > self._max_depth:
            raise WorldBoundError(
                "depth bound exceeded",
                context={"entity_id": entity.entity_id, "maximum": self._max_depth},
            )
        self._unlink(entity)
        siblings.append(entity.entity_id)
        updated = replace(entity, parent_id=parent, revised_tick=applied)
        self._entities[entity.entity_id] = updated
        self._tick = applied
        self._revision += 1
        return updated

    def set_sibling_index(self, entity_id: str, index: int, *, tick: int) -> SceneEntity:
        entity = self.require(entity_id)
        applied = _monotonic_tick(tick, current=self._tick)
        if isinstance(index, bool) or not isinstance(index, int):
            raise WorldSceneError("sibling index must be an integer")
        siblings = self._sibling_list(entity.parent_id)
        if index < 0 or index >= len(siblings):
            raise WorldBoundError(
                "sibling index is out of range",
                context={"index": index, "count": len(siblings)},
            )
        siblings.remove(entity.entity_id)
        siblings.insert(index, entity.entity_id)
        updated = replace(entity, revised_tick=applied)
        self._entities[entity.entity_id] = updated
        self._tick = applied
        self._revision += 1
        return updated

    def remove(self, entity_id: str, *, tick: int, cascade: bool = False) -> tuple[str, ...]:
        entity = self.require(entity_id)
        applied = _monotonic_tick(tick, current=self._tick)
        child_ids = tuple(self._children.get(entity.entity_id, ()))
        if child_ids and not cascade:
            raise WorldOrphanError(
                "remove would orphan children",
                context={"entity_id": entity.entity_id, "children": child_ids},
            )
        removed = (entity.entity_id,) + self.descendants(entity.entity_id) if cascade else (entity.entity_id,)
        for node_id in reversed(removed):
            node = self._entities[node_id]
            self._unlink(node)
            self._children.pop(node_id, None)
            del self._entities[node_id]
        self._tick = applied
        self._revision += 1
        return removed

    def set_transform(self, entity_id: str, transform: Transform, *, tick: int) -> SceneEntity:
        if not isinstance(transform, Transform):
            raise WorldSceneError("transform must be Transform")
        return self._revise(entity_id, tick, transform=transform)

    def set_attributes(
        self, entity_id: str, attributes: Mapping[str, Any], *, tick: int
    ) -> SceneEntity:
        return self._revise(entity_id, tick, attributes=_attributes(attributes))

    def get(self, entity_id: str) -> SceneEntity | None:
        return self._entities.get(_identifier("entity_id", entity_id))

    def require(self, entity_id: str) -> SceneEntity:
        entity = self.get(entity_id)
        if entity is None:
            raise WorldReferenceError(
                "unknown entity",
                context={"entity_id": _identifier("entity_id", entity_id)},
            )
        return entity

    def roots(self) -> tuple[str, ...]:
        return tuple(self._roots)

    def children(self, entity_id: str) -> tuple[str, ...]:
        self.require(entity_id)
        return tuple(self._children.get(entity_id, ()))

    def parent(self, entity_id: str) -> str | None:
        return self.require(entity_id).parent_id

    def ancestors(self, entity_id: str) -> tuple[str, ...]:
        entity = self.require(entity_id)
        chain: list[str] = []
        current = entity.parent_id
        seen: set[str] = set()
        while current is not None:
            if current in seen:
                raise WorldCycleError(
                    "ancestor walk encountered a cycle",
                    context={"entity_id": entity_id, "cycle_at": current},
                )
            seen.add(current)
            chain.append(current)
            current = self.require(current).parent_id
        return tuple(reversed(chain))

    def descendants(self, entity_id: str) -> tuple[str, ...]:
        self.require(entity_id)
        ordered: list[str] = []
        stack = list(reversed(self._children.get(entity_id, ())))
        while stack:
            node_id = stack.pop()
            ordered.append(node_id)
            stack.extend(reversed(self._children.get(node_id, ())))
        return tuple(ordered)

    def traverse(self) -> tuple[str, ...]:
        """Deterministic pre-order walk: root sibling order, then child sibling order."""

        ordered: list[str] = []
        for root_id in self._roots:
            ordered.append(root_id)
            ordered.extend(self.descendants(root_id))
        return tuple(ordered)

    def detect_cycles(self) -> tuple[tuple[str, ...], ...]:
        return _parent_cycles({node.entity_id: node.parent_id for node in self._entities.values()})

    def detect_orphans(self) -> tuple[str, ...]:
        reachable = set(self.traverse())
        dangling = [
            entity_id
            for entity_id, entity in self._entities.items()
            if entity.parent_id is not None and entity.parent_id not in self._entities
        ]
        unreachable = [entity_id for entity_id in self._entities if entity_id not in reachable]
        return tuple(sorted(set(dangling) | set(unreachable)))

    def diagnose(self) -> GraphDiagnosis:
        return diagnose_payload(self.to_payload())

    def validate(self) -> None:
        _raise_diagnosis(self.diagnose())

    def to_payload(self) -> dict[str, Any]:
        entities = [
            self._entities[entity_id].to_payload(tuple(self._children.get(entity_id, ())))
            for entity_id in sorted(self._entities)
        ]
        return {
            "entities": entities,
            "revision": self._revision,
            "roots": list(self._roots),
            "schema": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "tick": self._tick,
            "world_id": self._world_id,
        }

    def to_bytes(self) -> bytes:
        encoded = json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise WorldBoundError(
                "serialized graph exceeds payload bound",
                context={"size": len(encoded), "maximum": MAX_PAYLOAD_BYTES},
            )
        return encoded

    def digest(self) -> str:
        return sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_payload(cls, payload: object, **limits: int) -> "WorldState":
        diagnosis = diagnose_payload(payload)
        _raise_diagnosis(diagnosis)
        if not isinstance(payload, Mapping):
            raise WorldSchemaError("payload must be a mapping")
        world = cls(str(payload["world_id"]), tick=int(payload["tick"]), **limits)
        records = {str(item["entity_id"]): item for item in payload["entities"]}
        if len(records) > world._max_entities:
            raise WorldBoundError(
                "entity bound exceeded",
                context={"maximum": world._max_entities, "count": len(records)},
            )
        world._revision = int(payload["revision"])
        for entity_id in _load_order(payload["roots"], records):
            record = records[entity_id]
            world._entities[entity_id] = SceneEntity(
                entity_id=entity_id,
                kind=str(record["kind"]),
                parent_id=record["parent_id"],
                name=str(record["name"]),
                transform=Transform.from_payload(record["transform"]),
                attributes=_attributes(record["attributes"]),
                created_tick=int(record["created_tick"]),
                revised_tick=int(record["revised_tick"]),
            )
        world._roots = [str(item) for item in payload["roots"]]
        for entity_id, record in records.items():
            child_ids = [str(child) for child in record["child_ids"]]
            if len(child_ids) > world._max_children:
                raise WorldBoundError(
                    "child bound exceeded",
                    context={"parent_id": entity_id, "maximum": world._max_children},
                )
            world._children[entity_id] = child_ids
        for entity_id in world._entities:
            if world._depth(entity_id) > world._max_depth:
                raise WorldBoundError(
                    "depth bound exceeded",
                    context={"entity_id": entity_id, "maximum": world._max_depth},
                )
        world.validate()
        return world

    @classmethod
    def from_bytes(cls, blob: bytes | str | bytearray, **limits: int) -> "WorldState":
        if isinstance(blob, str):
            encoded = blob.encode("ascii")
        else:
            encoded = bytes(blob)
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise WorldBoundError(
                "serialized graph exceeds payload bound",
                context={"size": len(encoded), "maximum": MAX_PAYLOAD_BYTES},
            )
        try:
            payload = json.loads(encoded.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorldSchemaError("payload is not valid JSON") from exc
        return cls.from_payload(payload, **limits)

    def _revise(self, entity_id: str, tick: int, **changes: Any) -> SceneEntity:
        entity = self.require(entity_id)
        applied = _monotonic_tick(tick, current=self._tick)
        updated = replace(entity, revised_tick=applied, **changes)
        self._entities[entity.entity_id] = updated
        self._tick = applied
        self._revision += 1
        return updated

    def _require_parent(self, parent_id: str | None) -> str | None:
        if parent_id is None:
            return None
        parent = _identifier("parent_id", parent_id)
        if parent not in self._entities:
            raise WorldReferenceError("unknown parent", context={"parent_id": parent})
        return parent

    def _sibling_list(self, parent_id: str | None) -> list[str]:
        if parent_id is None:
            return self._roots
        return self._children.setdefault(parent_id, [])

    def _unlink(self, entity: SceneEntity) -> None:
        siblings = self._sibling_list(entity.parent_id)
        if entity.entity_id in siblings:
            siblings.remove(entity.entity_id)
        if entity.parent_id is not None and not siblings:
            self._children.pop(entity.parent_id, None)

    def _is_ancestor(self, ancestor_id: str, node_id: str) -> bool:
        current: str | None = node_id
        seen: set[str] = set()
        while current is not None:
            if current == ancestor_id:
                return True
            if current in seen:
                return True
            seen.add(current)
            current = self.require(current).parent_id
        return False

    def _depth(self, entity_id: str) -> int:
        return len(self.ancestors(entity_id))

    def _height(self, entity_id: str) -> int:
        kids = self._children.get(entity_id, ())
        if not kids:
            return 0
        return 1 + max(self._height(child_id) for child_id in kids)


def diagnose_payload(payload: object) -> GraphDiagnosis:
    """Inspect a serialized graph without mutating world state."""

    issues: list[str] = []
    cycles: tuple[tuple[str, ...], ...] = ()
    orphans: tuple[str, ...] = ()
    invalid: list[str] = []
    if not isinstance(payload, Mapping):
        return GraphDiagnosis(issues=("payload_not_mapping",))
    extra = tuple(sorted(set(payload) - _PAYLOAD_KEYS))
    missing = tuple(sorted(_PAYLOAD_KEYS - set(payload)))
    if extra:
        issues.append("unknown_fields")
    if missing:
        issues.append("missing_fields")
    if payload.get("schema") != SCHEMA_NAME or payload.get("schema_version") != SCHEMA_VERSION:
        issues.append("schema_mismatch")
    if not _is_identifier(payload.get("world_id")):
        issues.append("invalid_world_id")
    if not _is_tick(payload.get("tick")) or not _is_tick(payload.get("revision"), allow_zero=True):
        issues.append("invalid_time")
    entities = payload.get("entities")
    roots = payload.get("roots")
    if not isinstance(entities, list) or not isinstance(roots, list):
        issues.append("malformed_graph")
        return GraphDiagnosis(issues=tuple(dict.fromkeys(issues)))
    if len(entities) > MAX_ENTITIES:
        issues.append("entity_bound")
    records, record_issues, invalid_ids = _entity_records(entities)
    issues.extend(record_issues)
    invalid.extend(invalid_ids)
    root_ids, root_issues, root_invalid = _id_list(roots, records, field="roots")
    issues.extend(root_issues)
    invalid.extend(root_invalid)
    expected_roots = tuple(
        entity_id for entity_id, record in records.items() if record["parent_id"] is None
    )
    if tuple(sorted(root_ids)) != tuple(sorted(expected_roots)) or len(root_ids) != len(set(root_ids)):
        issues.append("root_mismatch")
    child_owner: dict[str, str] = {}
    for entity_id, record in records.items():
        child_ids, child_issues, child_invalid = _id_list(
            record["child_ids"], records, field="child_ids"
        )
        issues.extend(child_issues)
        invalid.extend(child_invalid)
        for child_id in child_ids:
            if child_id in child_owner:
                issues.append("duplicate_child")
            child_owner[child_id] = entity_id
            parent_id = records[child_id]["parent_id"]
            if parent_id != entity_id:
                issues.append("parent_child_mismatch")
                invalid.append(child_id)
    for entity_id, record in records.items():
        parent_id = record["parent_id"]
        if parent_id is None:
            if entity_id in child_owner:
                issues.append("root_listed_as_child")
            continue
        if parent_id not in records:
            issues.append("dangling_parent")
            invalid.append(parent_id)
            continue
        if child_owner.get(entity_id) != parent_id:
            issues.append("parent_child_mismatch")
            invalid.append(entity_id)
    parents = {entity_id: record["parent_id"] for entity_id, record in records.items()}
    cycles = _parent_cycles(parents)
    if cycles:
        issues.append("cycle")
    for entity_id in records:
        depth = 0
        current = parents[entity_id]
        walked: set[str] = set()
        while current is not None and current not in walked:
            walked.add(current)
            depth += 1
            if depth > MAX_DEPTH:
                issues.append("depth_bound")
                break
            current = parents.get(current)
    reachable = _reachable(root_ids, {entity_id: record["child_ids"] for entity_id, record in records.items()})
    orphans = tuple(sorted(set(records) - reachable))
    if orphans:
        issues.append("orphan")
    return GraphDiagnosis(
        cycles=cycles,
        orphans=orphans,
        invalid_references=tuple(dict.fromkeys(invalid)),
        issues=tuple(dict.fromkeys(issues)),
    )


def _raise_diagnosis(diagnosis: GraphDiagnosis) -> None:
    if diagnosis.ok:
        return
    context = {
        "issues": diagnosis.issues,
        "cycles": diagnosis.cycles,
        "orphans": diagnosis.orphans,
        "invalid_references": diagnosis.invalid_references,
    }
    if "schema_mismatch" in diagnosis.issues or "unknown_fields" in diagnosis.issues:
        raise WorldSchemaError("world scene schema mismatch", context=context)
    if "cycle" in diagnosis.issues:
        raise WorldCycleError("world scene contains a cycle", context=context)
    if "orphan" in diagnosis.issues:
        raise WorldOrphanError("world scene contains orphans", context=context)
    if diagnosis.invalid_references or "dangling_parent" in diagnosis.issues:
        raise WorldReferenceError("world scene has invalid references", context=context)
    if "entity_bound" in diagnosis.issues or "depth_bound" in diagnosis.issues:
        raise WorldBoundError("world scene exceeds a graph bound", context=context)
    raise WorldSceneError("world scene is invalid", context=context)


def _entity_records(
    entities: list[Any],
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    records: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    invalid: list[str] = []
    for item in entities:
        if not isinstance(item, Mapping):
            issues.append("malformed_entity")
            continue
        extra = set(item) - _ENTITY_KEYS
        missing = _ENTITY_KEYS - set(item)
        if extra or missing:
            issues.append("malformed_entity")
        entity_id = item.get("entity_id")
        if not _is_identifier(entity_id):
            issues.append("invalid_entity_id")
            invalid.append(str(entity_id))
            continue
        if entity_id in records:
            issues.append("duplicate_entity")
            invalid.append(str(entity_id))
            continue
        parent_id = item.get("parent_id")
        if parent_id is not None and not _is_identifier(parent_id):
            issues.append("invalid_parent_id")
            invalid.append(str(parent_id))
        kind = item.get("kind")
        if not _is_identifier(kind, maximum=MAX_KIND_CHARS):
            issues.append("invalid_kind")
        if not isinstance(item.get("name"), str) or len(str(item.get("name"))) > MAX_NAME_CHARS:
            issues.append("invalid_name")
        if not _is_tick(item.get("created_tick"), allow_zero=True):
            issues.append("invalid_time")
        if not _is_tick(item.get("revised_tick"), allow_zero=True):
            issues.append("invalid_time")
        if not isinstance(item.get("child_ids"), list):
            issues.append("malformed_entity")
            child_ids: list[str] = []
        else:
            child_ids = [str(child) for child in item["child_ids"]]
        records[str(entity_id)] = {
            "parent_id": parent_id,
            "child_ids": child_ids,
            "kind": kind,
            "name": item.get("name"),
            "transform": item.get("transform"),
            "attributes": item.get("attributes"),
            "created_tick": item.get("created_tick"),
            "revised_tick": item.get("revised_tick"),
        }
    return records, issues, invalid


def _id_list(
    values: object, records: Mapping[str, Any], *, field: str
) -> tuple[tuple[str, ...], list[str], list[str]]:
    if not isinstance(values, list):
        return (), [f"malformed_{field}"], []
    ordered: list[str] = []
    issues: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not _is_identifier(item):
            issues.append(f"invalid_{field}")
            invalid.append(str(item))
            continue
        entity_id = str(item)
        if entity_id in seen:
            issues.append(f"duplicate_{field}")
            continue
        seen.add(entity_id)
        if entity_id not in records:
            issues.append("invalid_reference")
            invalid.append(entity_id)
            continue
        ordered.append(entity_id)
    return tuple(ordered), issues, invalid


def _parent_cycles(parents: Mapping[str, str | None]) -> tuple[tuple[str, ...], ...]:
    cycles: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for start in sorted(parents):
        if start in seen:
            continue
        chain: list[str] = []
        current: str | None = start
        visiting: dict[str, int] = {}
        while current is not None:
            if current in visiting:
                cycles.append(tuple(chain[visiting[current] :]))
                break
            if current in seen or current not in parents:
                break
            visiting[current] = len(chain)
            chain.append(current)
            current = parents[current]
        seen.update(chain)
    unique: list[tuple[str, ...]] = []
    fingerprints: set[tuple[str, ...]] = set()
    for cycle in cycles:
        if not cycle:
            continue
        pivot = cycle.index(min(cycle))
        rotated = cycle[pivot:] + cycle[:pivot]
        if rotated not in fingerprints:
            fingerprints.add(rotated)
            unique.append(rotated)
    return tuple(unique)


def _reachable(roots: Iterable[str], children: Mapping[str, Iterable[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(reversed(list(roots)))
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(reversed(list(children.get(node_id, ()))))
    return seen


def _load_order(roots: Iterable[Any], records: Mapping[str, Mapping[str, Any]]) -> list[str]:
    ordered: list[str] = []
    stack = list(reversed([str(item) for item in roots]))
    seen: set[str] = set()
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id not in records:
            continue
        seen.add(node_id)
        ordered.append(node_id)
        stack.extend(reversed([str(child) for child in records[node_id]["child_ids"]]))
    for entity_id in records:
        if entity_id not in seen:
            ordered.append(entity_id)
    return ordered


def _identifier(field: str, value: object, *, maximum: int = MAX_ID_CHARS) -> str:
    if not isinstance(value, str) or not value:
        raise WorldSceneError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise WorldBoundError(
            f"{field} is too long",
            context={"maximum": maximum, "field": field},
        )
    if _IDENTIFIER.fullmatch(value) is None:
        raise WorldSceneError(f"{field} is not a stable identifier", context={"value": value})
    return value


def _is_identifier(value: object, *, maximum: int = MAX_ID_CHARS) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maximum and _IDENTIFIER.fullmatch(value) is not None


def _name(value: object, *, default: str) -> str:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        raise WorldSceneError("name must be a string")
    if len(value) > MAX_NAME_CHARS:
        raise WorldBoundError("name is too long", context={"maximum": MAX_NAME_CHARS})
    if any(ord(char) < 32 for char in value):
        raise WorldSceneError("name contains control characters")
    return value


def _absolute_tick(value: object) -> int:
    if not _is_tick(value, allow_zero=True):
        raise WorldTimeError("tick must be a non-negative integer")
    return int(value)


def _monotonic_tick(value: object, *, current: int) -> int:
    tick = _absolute_tick(value)
    if tick < current:
        raise WorldTimeError(
            "tick must be monotonic",
            context={"tick": tick, "current": current},
        )
    return tick


def _is_tick(value: object, *, allow_zero: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    minimum = 0 if allow_zero else 0
    return minimum <= value <= MAX_TICK


def _bound_limit(field: str, value: int, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > ceiling:
        raise WorldBoundError(
            f"{field} is outside the accepted range",
            context={"minimum": 1, "maximum": ceiling},
        )
    return value


def _vec3(field: str, value: object) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise WorldSceneError(f"{field} must contain three numbers")
    components: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise WorldSceneError(f"{field} must contain three numbers")
        number = float(item)
        if not math.isfinite(number):
            raise WorldSceneError(f"{field} must be finite")
        components.append(number)
    return components[0], components[1], components[2]


def _attributes(value: object) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise WorldSceneError("attributes must be a mapping")
    if len(value) > MAX_ATTRIBUTE_KEYS:
        raise WorldBoundError(
            "too many attributes",
            context={"maximum": MAX_ATTRIBUTE_KEYS},
        )
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not _is_identifier(key):
            raise WorldSceneError("attribute keys must be stable identifiers", context={"key": key})
        normalized[key] = _attribute_value(item)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(encoded.encode("ascii")) > MAX_ATTRIBUTE_BYTES:
        raise WorldBoundError(
            "attributes exceed byte bound",
            context={"maximum": MAX_ATTRIBUTE_BYTES},
        )
    return MappingProxyType(normalized)


def _attribute_value(value: object) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) <= MAX_TICK:
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str):
        if len(value) > MAX_NAME_CHARS or any(ord(char) < 32 for char in value):
            raise WorldBoundError("attribute string is invalid")
        return value
    raise WorldSceneError("attribute values must be JSON scalars")
