"""Godot adapter conformance boundary.

Maps engine-neutral project/game/world documents into Godot-facing views
without moving core semantics into engine-specific code.

This module is the versioned ``platform.godot_adapter.v1`` surface. It wraps
``skeleton.forge.godot_emit.emit_godot`` for pack materialisation and does not
replace that materialiser or relocate ``backend/godot``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping, Protocol, Sequence

from skeleton.frontier.world import WorldBounds, WorldRegion, region_from_record
from skeleton.game.mechanics import CombatStyle, CombatSystemSpec, MechanicType
from skeleton.kernel.errors import SkeletonError
from skeleton.organism.gamespec import SCHEMA as GAMESPEC_SCHEMA

ADAPTER_SCHEMA: Final = "platform.godot_adapter.v1"
ADAPTER_INPUT_SCHEMA: Final = "platform.godot_adapter.input.v1"
ADAPTER_VERSION: Final = 1
GODOT_CONFIG_VERSION: Final = 5
GODOT_FEATURES: Final = ("4.3",)
GODOT_ENGINE: Final = "godot"
DEFAULT_RENDERER: Final = "gl_compatibility"
DEFAULT_MAIN_SCENE: Final = "res://scenes/levels/run_level.tscn"
FOOTPRINT_POLICY: Final = "leave_in_place"
FOOTPRINT_ISSUE: Final = "#1008 / GB-9"

REPO_GODOT_BINARY: Final = "backend/godot"
REPO_GODOT_ENGINE_PACKAGE: Final = "backend/gameforge/godot_engine"
REPO_GODOT_EMIT: Final = "skeleton/forge/godot_emit.py"
REPO_GODOT_ROUTE: Final = "backend/routes/godot_engine.py"

_DOCUMENT_KEYS: Final = frozenset({"schema", "schema_version", "project", "game", "world", "creator"})
_PROJECT_KEYS: Final = frozenset(
    {"title", "viewport_width", "viewport_height", "renderer", "features", "main_scene"}
)
_GAME_KEYS: Final = frozenset({"combat_style", "mechanic_types", "combat", "currencies"})
_ROOM_KEYS: Final = frozenset({"id", "kind", "x", "y", "occupants", "index"})
_EDGE_KEYS: Final = frozenset({"from", "to"})
_ROOM_GRAPH_KEYS: Final = frozenset(
    {
        "kind",
        "rooms",
        "edges",
        "era",
        "seed",
        "bias",
        "count",
        "doors",
        "occupancy",
        "reachable",
        "spawn_weapon",
        "extract_late",
    }
)
_SCENE_STATE_SCHEMA: Final = "world.scene_state.v1"
_GAMESPEC_KIND: Final = "game-spec"
_ROOM_GRAPH_KIND: Final = "forge.room_graph"
_ENGINE_GLOBAL_KEYS: Final = frozenset(
    {"autoload", "autoloads", "singleton", "singletons", "Engine", "engine_global"}
)
_SUPPORTED_RENDERERS: Final = frozenset({"gl_compatibility", "forward_plus", "mobile"})
_SUPPORTED_ROOM_KINDS: Final = frozenset({"spawn", "combat", "loot", "heat", "extract"})
_SUPPORTED_OCCUPANT_KINDS: Final = frozenset({"player", "enemy", "extract", "heat", "loot"})
_SUPPORTED_ENEMY_TIERS: Final = frozenset({"trash", "elite", "boss"})
_SUPPORTED_SCENE_KINDS: Final = _SUPPORTED_OCCUPANT_KINDS | frozenset({"room", "region"})
_SUPPORTED_COMBAT_STYLES: Final = frozenset({CombatStyle.REAL_TIME, CombatStyle.ACTION})
_SUPPORTED_MECHANIC_TYPES: Final = frozenset(
    {MechanicType.COMBAT, MechanicType.MOVEMENT, MechanicType.INVENTORY, MechanicType.AI_BEHAVIOR}
)
_OCCUPANT_NODE_TYPES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "player": "CharacterBody2D",
        "enemy": "CharacterBody2D",
        "extract": "Area2D",
        "heat": "Area2D",
        "loot": "Marker2D",
    }
)
_NODE_TYPE_TO_OCCUPANT: Final[Mapping[str, str]] = MappingProxyType(
    {
        "CharacterBody2D:player": "player",
        "CharacterBody2D:enemy": "enemy",
        "Area2D:extract": "extract",
        "Area2D:heat": "heat",
        "Marker2D:loot": "loot",
    }
)
_ROOM_NODE_TYPE: Final = "Node2D"
_REGION_NODE_TYPE: Final = "Node2D"
_CONTROLLER_FAMILY: Final = "continuous_2d"
_MAX_TITLE_CHARS: Final = 120
_MAX_ID_CHARS: Final = 64
_MAX_NODES: Final = 1024
_MAX_CURRENCIES: Final = 16


class GodotAdapterError(SkeletonError):
    """Malformed adapter input or mapping failure."""

    code = "PLT.GODOT_ADAPTER"
    http_status = 422


class GodotUnsupportedFeatureError(GodotAdapterError):
    """A requested primitive has no Godot mapping in this adapter version."""

    code = "PLT.GODOT_UNSUPPORTED"
    http_status = 422


class GodotVersionError(GodotAdapterError):
    """Adapter or consumed-contract schema version is not this boundary."""

    code = "PLT.GODOT_VERSION"
    http_status = 422


class GodotConformanceAdapter(Protocol):
    """Explicit versioned mapping from engine-neutral documents to Godot views."""

    schema: str
    schema_version: int

    def adapt(self, document: Mapping[str, Any]) -> "GodotAdapterView": ...

    def project(self, view: "GodotAdapterView") -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class GodotNodeSpec:
    """One Godot-facing node derived from a supported engine-neutral primitive."""

    node_id: str
    node_type: str
    name: str
    parent_id: str | None
    position: tuple[float, float]
    primitive: str
    size: tuple[float, float] | None = None
    attributes: Mapping[str, Any] = MappingProxyType({})

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attributes": {key: self.attributes[key] for key in sorted(self.attributes)},
            "name": self.name,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "parent_id": self.parent_id,
            "position": [self.position[0], self.position[1]],
            "primitive": self.primitive,
        }
        if self.size is not None:
            payload["size"] = [self.size[0], self.size[1]]
        return payload


@dataclass(frozen=True, slots=True)
class GodotProjectView:
    title: str
    config_version: int
    features: tuple[str, ...]
    viewport_width: int
    viewport_height: int
    renderer: str
    main_scene: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "features": list(self.features),
            "main_scene": self.main_scene,
            "renderer": self.renderer,
            "title": self.title,
            "viewport_height": self.viewport_height,
            "viewport_width": self.viewport_width,
        }


@dataclass(frozen=True, slots=True)
class GodotGameView:
    combat_style: str
    controller_family: str
    mechanic_types: tuple[str, ...]
    resource_labels: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "combat_style": self.combat_style,
            "controller_family": self.controller_family,
            "mechanic_types": list(self.mechanic_types),
            "resource_labels": list(self.resource_labels),
        }


@dataclass(frozen=True, slots=True)
class GodotAdapterView:
    """Deterministic Godot-facing representation of a supported document."""

    schema: str
    schema_version: int
    engine: str
    project: GodotProjectView | None
    game: GodotGameView | None
    nodes: tuple[GodotNodeSpec, ...]
    provenance: tuple[str, ...]
    creator_title: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "creator_title": self.creator_title,
            "engine": self.engine,
            "game": None if self.game is None else self.game.to_payload(),
            "nodes": [node.to_payload() for node in self.nodes],
            "project": None if self.project is None else self.project.to_payload(),
            "provenance": list(self.provenance),
            "schema": self.schema,
            "schema_version": self.schema_version,
        }
        return payload

    def canonical_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class GodotFootprintEntry:
    path: str
    kind: str
    exists: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GodotFootprintInventory:
    adapter_schema: str
    packaging_recommendation: str
    relocate_binaries: bool
    packaging_owner: str
    entries: tuple[GodotFootprintEntry, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "adapter_schema": self.adapter_schema,
            "entries": [
                {
                    "exists": entry.exists,
                    "kind": entry.kind,
                    "path": entry.path,
                    "size_bytes": entry.size_bytes,
                }
                for entry in self.entries
            ],
            "packaging_owner": self.packaging_owner,
            "packaging_recommendation": self.packaging_recommendation,
            "relocate_binaries": self.relocate_binaries,
        }


@dataclass(frozen=True, slots=True)
class GodotMaterialisation:
    view: GodotAdapterView
    files: Mapping[str, str]
    emitter: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "emitter": self.emitter,
            "file_count": len(self.files),
            "files": sorted(self.files),
            "view": self.view.to_payload(),
        }


def _token(name: str, value: object, *, maximum: int = _MAX_ID_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GodotAdapterError(f"{name} must be a non-empty string")
    token = value.strip()
    if len(token) > maximum:
        raise GodotAdapterError(f"{name} is too long", context={"max_chars": maximum})
    return token


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GodotAdapterError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise GodotAdapterError(
            f"{name} is outside the accepted range",
            context={"minimum": minimum, "maximum": maximum},
        )
    return value


def _strict_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GodotAdapterError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise GodotAdapterError(f"{name} must be finite")
    return number


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GodotAdapterError(f"{name} must be a mapping")
    return value


def _reject_unknown(name: str, payload: Mapping[str, Any], allowed: frozenset[str]) -> None:
    extra = tuple(sorted(str(key) for key in payload if key not in allowed))
    if extra:
        raise GodotUnsupportedFeatureError(
            f"{name} has unsupported fields",
            context={"fields": extra, "feature": "unknown_fields"},
        )


def _reject_engine_globals(name: str, payload: Mapping[str, Any]) -> None:
    present = tuple(sorted(key for key in payload if key in _ENGINE_GLOBAL_KEYS))
    if present:
        raise GodotUnsupportedFeatureError(
            "engine-global state is not a core contract",
            context={"path": name, "fields": present, "feature": "engine_global"},
        )


def map_occupant_kind(kind: object) -> str:
    """Map a supported world occupant kind onto a Godot node type."""

    token = _token("occupant.kind", kind).lower()
    try:
        return _OCCUPANT_NODE_TYPES[token]
    except KeyError as exc:
        raise GodotUnsupportedFeatureError(
            "unsupported occupant kind",
            context={"kind": token, "feature": "occupant_kind"},
        ) from exc


def map_node_type_to_occupant(*, node_type: str, primitive: str) -> str:
    """Inverse of :func:`map_occupant_kind` for supported primitives."""

    key = f"{_token('node_type', node_type)}:{_token('primitive', primitive).lower()}"
    try:
        return _NODE_TYPE_TO_OCCUPANT[key]
    except KeyError as exc:
        raise GodotUnsupportedFeatureError(
            "unsupported Godot occupant projection",
            context={"node_type": node_type, "primitive": primitive, "feature": "occupant_roundtrip"},
        ) from exc


def _coerce_combat_style(style: object) -> CombatStyle:
    if isinstance(style, CombatStyle):
        return style
    if isinstance(style, str):
        try:
            return CombatStyle(style.strip().lower())
        except ValueError as exc:
            raise GodotUnsupportedFeatureError(
                "unsupported combat style",
                context={"style": style, "feature": "combat_style"},
            ) from exc
    raise GodotAdapterError("combat_style must be a CombatStyle or string")


def map_combat_style(style: object) -> str:
    """Map a live-playable combat style onto the Godot controller family."""

    combat = _coerce_combat_style(style)
    if combat not in _SUPPORTED_COMBAT_STYLES:
        raise GodotUnsupportedFeatureError(
            "combat style has no Godot live-play mapping",
            context={
                "style": combat.value,
                "feature": "combat_style",
                "supported": tuple(sorted(item.value for item in _SUPPORTED_COMBAT_STYLES)),
            },
        )
    return _CONTROLLER_FAMILY


def _mechanic_type(value: object) -> MechanicType:
    if isinstance(value, MechanicType):
        return value
    if isinstance(value, str):
        try:
            return MechanicType(value.strip().lower())
        except ValueError as exc:
            raise GodotUnsupportedFeatureError(
                "unsupported mechanic type",
                context={"mechanic_type": value, "feature": "mechanic_type"},
            ) from exc
    raise GodotAdapterError("mechanic_types entries must be MechanicType or string")


def _map_project(payload: Mapping[str, Any]) -> GodotProjectView:
    _reject_engine_globals("project", payload)
    _reject_unknown("project", payload, _PROJECT_KEYS)
    features_raw = payload.get("features", list(GODOT_FEATURES))
    if isinstance(features_raw, str):
        raise GodotAdapterError("project.features must be a sequence of strings")
    if not isinstance(features_raw, Sequence) or isinstance(features_raw, (bytes, bytearray)):
        raise GodotAdapterError("project.features must be a sequence of strings")
    features = tuple(_token("project.features[]", item, maximum=16) for item in features_raw)
    if features != GODOT_FEATURES:
        raise GodotUnsupportedFeatureError(
            "Godot feature set is not this adapter version",
            context={"features": features, "supported": GODOT_FEATURES, "feature": "godot_features"},
        )
    renderer = _token("project.renderer", payload.get("renderer", DEFAULT_RENDERER), maximum=32)
    if renderer not in _SUPPORTED_RENDERERS:
        raise GodotUnsupportedFeatureError(
            "unsupported renderer",
            context={"renderer": renderer, "feature": "renderer"},
        )
    return GodotProjectView(
        title=_token("project.title", payload.get("title"), maximum=_MAX_TITLE_CHARS),
        config_version=GODOT_CONFIG_VERSION,
        features=features,
        viewport_width=_strict_int("project.viewport_width", payload.get("viewport_width"), minimum=160, maximum=7680),
        viewport_height=_strict_int(
            "project.viewport_height", payload.get("viewport_height"), minimum=144, maximum=4320
        ),
        renderer=renderer,
        main_scene=_token("project.main_scene", payload.get("main_scene", DEFAULT_MAIN_SCENE), maximum=256),
    )


def _map_game(payload: object) -> GodotGameView:
    if isinstance(payload, CombatSystemSpec):
        return GodotGameView(
            combat_style=payload.style.value,
            controller_family=map_combat_style(payload.style),
            mechanic_types=(MechanicType.COMBAT.value,),
            resource_labels=(),
        )
    game = _mapping("game", payload)
    _reject_engine_globals("game", game)
    _reject_unknown("game", game, _GAME_KEYS)
    style_source: object = game.get("combat_style")
    combat_payload = game.get("combat")
    if combat_payload is not None:
        if isinstance(combat_payload, CombatSystemSpec):
            style_source = combat_payload.style if style_source is None else style_source
        else:
            combat_map = _mapping("game.combat", combat_payload)
            _reject_unknown("game.combat", combat_map, frozenset({"style"}))
            if "style" in combat_map and style_source is None:
                style_source = combat_map["style"]
    if style_source is None:
        raise GodotAdapterError("game.combat_style is required")
    mechanic_values = game.get("mechanic_types", (MechanicType.COMBAT.value,))
    if isinstance(mechanic_values, (str, bytes)) or not isinstance(mechanic_values, Sequence):
        raise GodotAdapterError("game.mechanic_types must be a sequence")
    mechanics: list[str] = []
    seen: set[str] = set()
    for item in mechanic_values:
        mechanic = _mechanic_type(item)
        if mechanic not in _SUPPORTED_MECHANIC_TYPES:
            raise GodotUnsupportedFeatureError(
                "mechanic type has no Godot mapping",
                context={"mechanic_type": mechanic.value, "feature": "mechanic_type"},
            )
        if mechanic.value not in seen:
            seen.add(mechanic.value)
            mechanics.append(mechanic.value)
    currencies_raw = game.get("currencies", ())
    if isinstance(currencies_raw, (str, bytes)) or not isinstance(currencies_raw, Sequence):
        raise GodotAdapterError("game.currencies must be a sequence")
    if len(currencies_raw) > _MAX_CURRENCIES:
        raise GodotAdapterError(
            "game.currencies exceeds the adapter bound",
            context={"maximum": _MAX_CURRENCIES},
        )
    labels = tuple(_token("game.currencies[]", item) for item in currencies_raw)
    if len(set(labels)) != len(labels):
        raise GodotAdapterError("game.currencies must be unique")
    combat = _coerce_combat_style(style_source)
    return GodotGameView(
        combat_style=combat.value,
        controller_family=map_combat_style(combat),
        mechanic_types=tuple(mechanics),
        resource_labels=labels,
    )


def _occupant_attributes(occupant: Mapping[str, Any]) -> Mapping[str, Any]:
    extra = {key: occupant[key] for key in occupant if key not in {"kind", "tier"}}
    if extra:
        raise GodotUnsupportedFeatureError(
            "occupant has unsupported fields",
            context={"fields": tuple(sorted(extra)), "feature": "occupant_fields"},
        )
    kind = _token("occupant.kind", occupant.get("kind")).lower()
    map_occupant_kind(kind)
    attributes: dict[str, Any] = {}
    if "tier" in occupant and occupant["tier"] is not None:
        tier = _token("occupant.tier", occupant["tier"]).lower()
        if kind != "enemy":
            raise GodotUnsupportedFeatureError(
                "occupant tier is only valid on enemy primitives",
                context={"kind": kind, "feature": "occupant_tier"},
            )
        if tier not in _SUPPORTED_ENEMY_TIERS:
            raise GodotUnsupportedFeatureError(
                "unsupported enemy tier",
                context={"tier": tier, "feature": "enemy_tier"},
            )
        attributes["tier"] = tier
    elif kind == "enemy":
        attributes["tier"] = "trash"
    return MappingProxyType(attributes)


def _map_room_graph(payload: Mapping[str, Any]) -> tuple[GodotNodeSpec, ...]:
    _reject_engine_globals("world", payload)
    extra = tuple(sorted(str(key) for key in payload if key not in _ROOM_GRAPH_KEYS and key != "kind"))
    if extra:
        raise GodotUnsupportedFeatureError(
            "room graph has unsupported fields",
            context={"fields": extra, "feature": "room_graph_fields"},
        )
    rooms = payload.get("rooms")
    if not isinstance(rooms, Sequence) or isinstance(rooms, (str, bytes)):
        raise GodotAdapterError("world.rooms must be a sequence")
    nodes: list[GodotNodeSpec] = []
    seen_rooms: set[str] = set()
    for index, raw_room in enumerate(rooms):
        room = _mapping(f"world.rooms[{index}]", raw_room)
        _reject_unknown(f"world.rooms[{index}]", room, _ROOM_KEYS)
        room_id = _token(f"world.rooms[{index}].id", room.get("id"))
        if room_id in seen_rooms:
            raise GodotAdapterError("duplicate room id", context={"id": room_id})
        seen_rooms.add(room_id)
        kind = _token(f"world.rooms[{index}].kind", room.get("kind")).lower()
        if kind not in _SUPPORTED_ROOM_KINDS:
            raise GodotUnsupportedFeatureError(
                "unsupported room kind",
                context={"kind": kind, "feature": "room_kind"},
            )
        position = (
            _strict_float(f"world.rooms[{index}].x", room.get("x", 0)),
            _strict_float(f"world.rooms[{index}].y", room.get("y", 0)),
        )
        nodes.append(
            GodotNodeSpec(
                node_id=room_id,
                node_type=_ROOM_NODE_TYPE,
                name=room_id,
                parent_id=None,
                position=position,
                primitive=kind,
                attributes=MappingProxyType({"role": "room"}),
            )
        )
        occupants = room.get("occupants") or ()
        if not isinstance(occupants, Sequence) or isinstance(occupants, (str, bytes)):
            raise GodotAdapterError(f"world.rooms[{index}].occupants must be a sequence")
        for occupant_index, raw_occupant in enumerate(occupants):
            occupant = _mapping(f"world.rooms[{index}].occupants[{occupant_index}]", raw_occupant)
            occupant_kind = _token("occupant.kind", occupant.get("kind")).lower()
            attributes = _occupant_attributes(occupant)
            nodes.append(
                GodotNodeSpec(
                    node_id=f"{room_id}:{occupant_index}:{occupant_kind}",
                    node_type=map_occupant_kind(occupant_kind),
                    name=occupant_kind,
                    parent_id=room_id,
                    position=position,
                    primitive=occupant_kind,
                    attributes=attributes,
                )
            )
        if len(nodes) > _MAX_NODES:
            raise GodotAdapterError("world exceeds the adapter node bound", context={"maximum": _MAX_NODES})
    edges = payload.get("edges") or ()
    if not isinstance(edges, Sequence) or isinstance(edges, (str, bytes)):
        raise GodotAdapterError("world.edges must be a sequence")
    for edge_index, raw_edge in enumerate(edges):
        edge = _mapping(f"world.edges[{edge_index}]", raw_edge)
        _reject_unknown(f"world.edges[{edge_index}]", edge, _EDGE_KEYS)
        source = _token("edge.from", edge.get("from"))
        target = _token("edge.to", edge.get("to"))
        if source not in seen_rooms or target not in seen_rooms:
            raise GodotAdapterError(
                "room graph edge references an unknown room",
                context={"from": source, "to": target},
            )
    return tuple(nodes)


def map_world_region(region: WorldRegion) -> GodotNodeSpec:
    """Map one frontier ``WorldRegion`` onto a Godot ``Node2D`` with a Rect2 size."""

    if not isinstance(region, WorldRegion):
        raise GodotAdapterError("region must be WorldRegion")
    if region.points_of_interest:
        raise GodotUnsupportedFeatureError(
            "world region points_of_interest have no Godot mapping",
            context={"feature": "region_points_of_interest"},
        )
    if region.metadata:
        raise GodotUnsupportedFeatureError(
            "world region metadata has no Godot mapping",
            context={"fields": tuple(sorted(region.metadata)), "feature": "region_metadata"},
        )
    return GodotNodeSpec(
        node_id=region.id,
        node_type=_REGION_NODE_TYPE,
        name=region.name,
        parent_id=None,
        position=(float(region.bounds.x), float(region.bounds.y)),
        size=(float(region.bounds.width), float(region.bounds.height)),
        primitive="region",
        attributes=MappingProxyType(
            {
                "difficulty": region.difficulty,
                "dangers": list(region.dangers),
            }
        ),
    )


def map_godot_region_to_world(node: GodotNodeSpec) -> WorldRegion:
    """Inverse of :func:`map_world_region` for supported region primitives."""

    if node.primitive != "region" or node.node_type != _REGION_NODE_TYPE:
        raise GodotUnsupportedFeatureError(
            "node is not a region projection",
            context={"primitive": node.primitive, "node_type": node.node_type, "feature": "region_roundtrip"},
        )
    if node.size is None:
        raise GodotAdapterError("region node is missing size")
    dangers = node.attributes.get("dangers", ())
    if not isinstance(dangers, Sequence) or isinstance(dangers, (str, bytes)):
        raise GodotAdapterError("region dangers must be a sequence")
    return WorldRegion(
        id=node.node_id,
        name=node.name,
        difficulty=_strict_int("region.difficulty", node.attributes.get("difficulty", 1), minimum=0, maximum=99),
        bounds=WorldBounds(
            x=int(node.position[0]),
            y=int(node.position[1]),
            width=int(node.size[0]),
            height=int(node.size[1]),
        ),
        dangers=tuple(str(item) for item in dangers),
    )


def _map_world_regions(value: object) -> tuple[GodotNodeSpec, ...]:
    if isinstance(value, WorldRegion):
        sequence: Sequence[Any] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        sequence = value
    else:
        raise GodotAdapterError("world regions must be a sequence")
    nodes = []
    seen: set[str] = set()
    for index, item in enumerate(sequence):
        if isinstance(item, WorldRegion):
            region = item
        else:
            try:
                region = region_from_record(_mapping(f"world[{index}]", item))
            except (TypeError, ValueError) as exc:
                raise GodotAdapterError(str(exc), context={"index": index}) from exc
        if region.id in seen:
            raise GodotAdapterError("duplicate world region id", context={"id": region.id})
        seen.add(region.id)
        nodes.append(map_world_region(region))
    return tuple(nodes)


def _translation_2d(path: str, payload: Mapping[str, Any]) -> tuple[float, float]:
    transform = _mapping(f"{path}.transform", payload.get("transform"))
    translation = transform.get("translation")
    if not isinstance(translation, Sequence) or isinstance(translation, (str, bytes)) or len(translation) != 3:
        raise GodotAdapterError(f"{path}.transform.translation must contain three coordinates")
    x = _strict_float(f"{path}.translation[0]", translation[0])
    y = _strict_float(f"{path}.translation[1]", translation[1])
    z = _strict_float(f"{path}.translation[2]", translation[2])
    if z != 0.0:
        raise GodotUnsupportedFeatureError(
            "3D translation is unsupported",
            context={"path": path, "z": z, "feature": "translation_3d"},
        )
    rotation = transform.get("rotation", (0.0, 0.0, 0.0))
    if isinstance(rotation, Sequence) and not isinstance(rotation, (str, bytes)) and len(rotation) == 3:
        rx = _strict_float(f"{path}.rotation[0]", rotation[0])
        ry = _strict_float(f"{path}.rotation[1]", rotation[1])
        if rx != 0.0 or ry != 0.0:
            raise GodotUnsupportedFeatureError(
                "3D rotation is unsupported",
                context={"path": path, "feature": "rotation_3d"},
            )
    return (x, y)


def _map_scene_state(payload: Mapping[str, Any]) -> tuple[GodotNodeSpec, ...]:
    schema = payload.get("schema")
    version = payload.get("schema_version")
    if schema != _SCENE_STATE_SCHEMA:
        raise GodotVersionError(
            "world scene schema is not supported",
            context={"schema": schema, "supported": _SCENE_STATE_SCHEMA},
        )
    if isinstance(version, bool) or version != 1:
        raise GodotVersionError(
            "world scene schema_version is not supported",
            context={"schema_version": version, "supported": 1},
        )
    entities = payload.get("entities")
    if not isinstance(entities, Mapping):
        raise GodotAdapterError("world.entities must be a mapping")
    nodes: list[GodotNodeSpec] = []
    for entity_id, raw_entity in sorted(entities.items(), key=lambda item: str(item[0])):
        entity = _mapping(f"world.entities[{entity_id}]", raw_entity)
        kind = _token("entity.kind", entity.get("kind")).lower()
        if kind not in _SUPPORTED_SCENE_KINDS:
            raise GodotUnsupportedFeatureError(
                "unsupported scene entity kind",
                context={"kind": kind, "feature": "scene_entity_kind"},
            )
        node_type = _ROOM_NODE_TYPE if kind in {"room", "region"} else map_occupant_kind(kind)
        parent_id = entity.get("parent_id")
        nodes.append(
            GodotNodeSpec(
                node_id=_token("entity.entity_id", entity.get("entity_id", entity_id)),
                node_type=node_type,
                name=_token("entity.name", entity.get("name") or entity_id, maximum=128),
                parent_id=None if parent_id is None else _token("entity.parent_id", parent_id),
                position=_translation_2d(f"world.entities[{entity_id}]", entity),
                primitive=kind if kind in {"room", "region"} else kind,
                attributes=MappingProxyType({"role": "scene_entity"}),
            )
        )
    return tuple(nodes)


def _map_world(payload: object) -> tuple[GodotNodeSpec, ...]:
    if isinstance(payload, WorldRegion) or (
        isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, Mapping))
    ):
        return _map_world_regions(payload)
    world = _mapping("world", payload)
    _reject_engine_globals("world", world)
    if world.get("schema") == _SCENE_STATE_SCHEMA or "entities" in world:
        return _map_scene_state(world)
    if "rooms" in world or world.get("kind") == _ROOM_GRAPH_KIND:
        return _map_room_graph(world)
    if "id" in world and "bounds" in world:
        return _map_world_regions((world,))
    raise GodotUnsupportedFeatureError(
        "world document shape is unsupported",
        context={"keys": tuple(sorted(world)), "feature": "world_shape"},
    )


def _map_creator(payload: Mapping[str, Any]) -> str:
    _reject_engine_globals("creator", payload)
    kind = payload.get("kind")
    schema = payload.get("schema")
    if kind == _GAMESPEC_KIND:
        if schema != GAMESPEC_SCHEMA:
            raise GodotVersionError(
                "creator game-spec schema is not supported",
                context={"schema": schema, "supported": GAMESPEC_SCHEMA},
            )
        platform = _token("creator.platform", payload.get("platform", GODOT_ENGINE), maximum=32).lower()
        if platform != GODOT_ENGINE:
            raise GodotUnsupportedFeatureError(
                "creator platform is not Godot",
                context={"platform": platform, "feature": "creator_platform"},
            )
        title_source = payload.get("vision") or payload.get("genre") or payload.get("cue") or "game-spec"
        return _token("creator.title", title_source, maximum=_MAX_TITLE_CHARS)
    if isinstance(kind, str) and kind.startswith("creator.intent"):
        raise GodotUnsupportedFeatureError(
            "creator intent compiler is not on this adapter version",
            context={"kind": kind, "feature": "creator_intent"},
        )
    raise GodotUnsupportedFeatureError(
        "unsupported creator document",
        context={"kind": kind, "schema": schema, "feature": "creator_kind"},
    )


@dataclass(frozen=True, slots=True)
class GodotAdapter:
    """Stateless Godot conformance adapter. Construct per call; no engine globals."""

    schema: str = ADAPTER_SCHEMA
    schema_version: int = ADAPTER_VERSION

    def __post_init__(self) -> None:
        if self.schema != ADAPTER_SCHEMA or self.schema_version != ADAPTER_VERSION:
            raise GodotVersionError(
                "adapter instance version is not this boundary",
                context={"schema": self.schema, "schema_version": self.schema_version},
            )

    def adapt(self, document: Mapping[str, Any]) -> GodotAdapterView:
        payload = _mapping("document", document)
        _reject_engine_globals("document", payload)
        _reject_unknown("document", payload, _DOCUMENT_KEYS)
        schema = payload.get("schema", ADAPTER_INPUT_SCHEMA)
        if schema != ADAPTER_INPUT_SCHEMA:
            raise GodotVersionError(
                "adapter input schema is not supported",
                context={"schema": schema, "supported": ADAPTER_INPUT_SCHEMA},
            )
        version = payload.get("schema_version", ADAPTER_VERSION)
        if isinstance(version, bool) or version != ADAPTER_VERSION:
            raise GodotVersionError(
                "adapter input schema_version is not supported",
                context={"schema_version": version, "supported": ADAPTER_VERSION},
            )
        if not any(key in payload for key in ("project", "game", "world", "creator")):
            raise GodotAdapterError("document must include project, game, world, or creator")
        provenance: list[str] = []
        project = None
        if "project" in payload and payload["project"] is not None:
            project = _map_project(_mapping("project", payload["project"]))
            provenance.append("project")
        game = None
        if "game" in payload and payload["game"] is not None:
            game = _map_game(payload["game"])
            provenance.append("game.mechanics")
        nodes: tuple[GodotNodeSpec, ...] = ()
        if "world" in payload and payload["world"] is not None:
            nodes = _map_world(payload["world"])
            provenance.append("world")
        creator_title = None
        if "creator" in payload and payload["creator"] is not None:
            creator_title = _map_creator(_mapping("creator", payload["creator"]))
            provenance.append("creator.gamespec")
            if project is None:
                project = GodotProjectView(
                    title=creator_title,
                    config_version=GODOT_CONFIG_VERSION,
                    features=GODOT_FEATURES,
                    viewport_width=1280,
                    viewport_height=720,
                    renderer=DEFAULT_RENDERER,
                    main_scene=DEFAULT_MAIN_SCENE,
                )
        return GodotAdapterView(
            schema=self.schema,
            schema_version=self.schema_version,
            engine=GODOT_ENGINE,
            project=project,
            game=game,
            nodes=nodes,
            provenance=tuple(provenance),
            creator_title=creator_title,
        )

    def project(self, view: GodotAdapterView) -> dict[str, Any]:
        if not isinstance(view, GodotAdapterView):
            raise GodotAdapterError("view must be GodotAdapterView")
        if view.schema != ADAPTER_SCHEMA or view.schema_version != ADAPTER_VERSION:
            raise GodotVersionError(
                "adapter view version is not supported",
                context={"schema": view.schema, "schema_version": view.schema_version},
            )
        if view.engine != GODOT_ENGINE:
            raise GodotUnsupportedFeatureError(
                "view engine is not Godot",
                context={"engine": view.engine, "feature": "engine"},
            )
        document: dict[str, Any] = {
            "schema": ADAPTER_INPUT_SCHEMA,
            "schema_version": ADAPTER_VERSION,
        }
        if view.project is not None:
            document["project"] = {
                "features": list(view.project.features),
                "main_scene": view.project.main_scene,
                "renderer": view.project.renderer,
                "title": view.project.title,
                "viewport_height": view.project.viewport_height,
                "viewport_width": view.project.viewport_width,
            }
        if view.game is not None:
            document["game"] = {
                "combat_style": view.game.combat_style,
                "currencies": list(view.game.resource_labels),
                "mechanic_types": list(view.game.mechanic_types),
            }
        if view.nodes:
            document["world"] = _project_world(view.nodes)
        if view.creator_title is not None:
            document["creator"] = {
                "kind": _GAMESPEC_KIND,
                "platform": GODOT_ENGINE,
                "schema": GAMESPEC_SCHEMA,
                "vision": view.creator_title,
            }
        return document


def _project_world(nodes: tuple[GodotNodeSpec, ...]) -> dict[str, Any]:
    if nodes and all(node.primitive == "region" for node in nodes):
        regions = []
        for node in nodes:
            region = map_godot_region_to_world(node)
            regions.append(
                {
                    "bounds": {
                        "height": region.bounds.height,
                        "width": region.bounds.width,
                        "x": region.bounds.x,
                        "y": region.bounds.y,
                    },
                    "dangers": list(region.dangers),
                    "difficulty": region.difficulty,
                    "id": region.id,
                    "name": region.name,
                }
            )
        return {"kind": "frontier.world_regions", "regions": regions}

    rooms: dict[str, dict[str, Any]] = {}
    occupants: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if node.parent_id is None and node.node_type == _ROOM_NODE_TYPE and node.primitive in _SUPPORTED_ROOM_KINDS:
            rooms[node.node_id] = {
                "id": node.node_id,
                "kind": node.primitive,
                "occupants": [],
                "x": node.position[0],
                "y": node.position[1],
            }
            occupants[node.node_id] = rooms[node.node_id]["occupants"]
        elif node.parent_id is not None and node.primitive in _SUPPORTED_OCCUPANT_KINDS:
            occupant: dict[str, Any] = {
                "kind": map_node_type_to_occupant(node_type=node.node_type, primitive=node.primitive)
            }
            if "tier" in node.attributes:
                occupant["tier"] = node.attributes["tier"]
            occupants.setdefault(node.parent_id, []).append(occupant)
        else:
            raise GodotUnsupportedFeatureError(
                "Godot node cannot round-trip into a supported world primitive",
                context={"node_id": node.node_id, "primitive": node.primitive, "feature": "world_roundtrip"},
            )
    missing = tuple(sorted(room_id for room_id in occupants if room_id not in rooms))
    if missing:
        raise GodotAdapterError("occupant parent room is missing", context={"rooms": missing})
    return {
        "kind": _ROOM_GRAPH_KIND,
        "rooms": [rooms[key] for key in rooms],
    }


def adapt_document(document: Mapping[str, Any]) -> GodotAdapterView:
    return GodotAdapter().adapt(document)


def project_document(view: GodotAdapterView) -> dict[str, Any]:
    return GodotAdapter().project(view)


def _validate_pack(pack: Mapping[str, Any]) -> GodotAdapterView:
    payload = _mapping("pack", pack)
    _reject_engine_globals("pack", payload)
    hardware = payload.get("hardware") or {}
    if hardware:
        hardware_map = _mapping("pack.hardware", hardware)
        _reject_engine_globals("pack.hardware", hardware_map)
        viewport = hardware_map.get("viewport")
        if viewport is not None:
            if (
                not isinstance(viewport, Sequence)
                or isinstance(viewport, (str, bytes))
                or len(viewport) != 2
            ):
                raise GodotAdapterError("pack.hardware.viewport must contain exactly two integers")
            project = {
                "title": "FORGE-RUN",
                "viewport_width": _strict_int(
                    "pack.hardware.viewport[0]", viewport[0], minimum=160, maximum=7680
                ),
                "viewport_height": _strict_int(
                    "pack.hardware.viewport[1]", viewport[1], minimum=144, maximum=4320
                ),
            }
        else:
            project = {"title": "FORGE-RUN", "viewport_width": 1280, "viewport_height": 720}
    else:
        project = {"title": "FORGE-RUN", "viewport_width": 1280, "viewport_height": 720}
    enemies = payload.get("enemies") or ()
    if enemies:
        if not isinstance(enemies, Sequence) or isinstance(enemies, (str, bytes)):
            raise GodotAdapterError("pack.enemies must be a sequence")
        for index, raw_enemy in enumerate(enemies):
            enemy = _mapping(f"pack.enemies[{index}]", raw_enemy)
            enemy_id = _token(f"pack.enemies[{index}].id", enemy.get("id")).lower()
            if enemy_id not in _SUPPORTED_ENEMY_TIERS:
                raise GodotUnsupportedFeatureError(
                    "unsupported pack enemy id",
                    context={"id": enemy_id, "feature": "enemy_tier"},
                )
    return GodotAdapter().adapt(
        {
            "schema": ADAPTER_INPUT_SCHEMA,
            "schema_version": ADAPTER_VERSION,
            "project": project,
            "game": {"combat_style": CombatStyle.ACTION.value, "mechanic_types": ["combat", "movement"]},
        }
    )


def materialise_pack(
    pack: Mapping[str, Any],
    *,
    title: str = "FORGE-RUN",
    build_plan: Mapping[str, Any] | None = None,
) -> GodotMaterialisation:
    """Validate a forge pack through the adapter, then wrap ``emit_godot``.

    The pack materialiser stays canonical for era dumps. This function adds the
    conformance boundary beside it and does not rewrite that module.
    """

    view = _validate_pack(pack)
    title_token = _token("title", title, maximum=_MAX_TITLE_CHARS)
    project = view.project
    if project is None:
        raise GodotAdapterError("pack materialisation requires a project view")
    bounded_view = GodotAdapterView(
        schema=view.schema,
        schema_version=view.schema_version,
        engine=view.engine,
        project=GodotProjectView(
            title=title_token,
            config_version=project.config_version,
            features=project.features,
            viewport_width=project.viewport_width,
            viewport_height=project.viewport_height,
            renderer=project.renderer,
            main_scene=project.main_scene,
        ),
        game=view.game,
        nodes=view.nodes,
        provenance=view.provenance + ("forge.godot_emit",),
        creator_title=view.creator_title,
    )
    from skeleton.forge.godot_emit import emit_godot

    files = emit_godot(dict(pack), title=title_token, build_plan=None if build_plan is None else dict(build_plan))
    if not isinstance(files, dict) or "project.godot" not in files:
        raise GodotAdapterError("emit_godot did not produce a Godot project")
    return GodotMaterialisation(
        view=bounded_view,
        files=MappingProxyType(dict(files)),
        emitter="skeleton.forge.godot_emit.emit_godot",
    )


def inventory_godot_footprint(repo_root: Path | None = None) -> GodotFootprintInventory:
    """Measure the in-tree Godot surfaces without proposing a packaging move.

    Binary relocation is owned by ``#1008`` / GB-9. This inventory is evidence
    for leaving ``backend/godot`` and ``godot_emit.py`` where they are.
    """

    root = Path(repo_root) if repo_root is not None else Path.cwd()
    specs = (
        (REPO_GODOT_BINARY, "binary"),
        (REPO_GODOT_ENGINE_PACKAGE, "package"),
        (REPO_GODOT_EMIT, "module"),
        (REPO_GODOT_ROUTE, "module"),
    )
    entries: list[GodotFootprintEntry] = []
    for relative, kind in specs:
        path = root / relative
        exists = path.exists()
        if not exists:
            size = 0
        elif path.is_dir():
            size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        else:
            size = path.stat().st_size
        entries.append(GodotFootprintEntry(path=relative, kind=kind, exists=exists, size_bytes=size))
    return GodotFootprintInventory(
        adapter_schema=ADAPTER_SCHEMA,
        packaging_recommendation=FOOTPRINT_POLICY,
        relocate_binaries=False,
        packaging_owner=FOOTPRINT_ISSUE,
        entries=tuple(entries),
    )
