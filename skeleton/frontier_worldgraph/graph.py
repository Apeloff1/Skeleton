"""World-family graph over the canonical scene graph.

Nodes live in :class:`skeleton.world.WorldState`. This module does not keep a
second node store. A transition is admitted only when identity is preserved,
the carried canon digest matches the destination's expected predecessor, the
destination biome climate bounds overlap the traveler's carried envelope, and
the physical-rule sets are explicitly declared compatible. A refusal returns
the same traveler, still in the source world, and does not revise the scene.

Edges are content-addressed with the canonical JSON digest. Coordinates are
fictional metres on a 2D or 3D layer. Geographic latitude and longitude are
rejected. The module does not read a clock and does not search at random.

Construction implications:

* Failure: the first broken constraint is a typed refusal. Travel does not
  mutate the scene, so a rejected transition needs no compensating write.
* Recovery: the operator repairs the canon link, climate envelope, rule
  declaration, or topology and retries. Dropping the graph object discards
  uncommitted operator additions.
* Observability: each admitted edge exposes its content address, both
  endpoints, and the four satisfied constraints. The scene digest covers the
  stored worlds, portals, and rule declarations.
* Economics: the only cost is the number of admitted hops. There is no
  external call, meter, or provider spend.
* Deployment: in-process library. No service, socket, or background task.
* Operator controls: ``add_world``, ``link``, and ``declare_compatible``.
* Evaluation: the same graph and traveler state yield the same edge addresses.
* Rollback: travel is a pure value. Operator edits advance the scene revision
  and are rolled back by discarding that graph, not by a clocked journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Mapping

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes
from skeleton.jeeves.game_frontier_worlds import WorldFamily
from skeleton.world import Transform, WorldSceneError, WorldState

EDGE_SCHEMA = "frontier.worldgraph.edge.v1"
RULE_SCHEMA = "frontier.worldgraph.rules.v1"
_METRE_LIMIT = 1e8
_WORLD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,23}$")
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
_RULE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
_BIOME = re.compile(r"^[a-z][a-z-]{0,31}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_GEOGRAPHIC = frozenset(
    {"latitude", "longitude", "lat", "lon", "lat_deg", "lon_deg", "lng"}
)
_POSITION_KEYS = frozenset({"layer", "x_m", "y_m", "z_m"})
_CONSTRAINTS = ("identity", "canon", "climate", "physics")


class WorldGraphError(ValueError):
    """The world-family graph rejected an input or found a broken invariant."""


class Constraint(str, Enum):
    """Admission checks, in the order a refusal reports the first failure."""

    IDENTITY = "identity"
    CANON = "canon"
    CLIMATE = "climate"
    PHYSICS = "physics"
    DISCONNECTED = "disconnected"


class MapLayer(str, Enum):
    """Traversal layers. Metres are fictional, never geographic degrees."""

    ISLAND = "island"
    CAVE = "cave"
    INVERSE = "inverse"
    ETHEREAL = "ethereal"
    MAP_2D = "map2d"


_LAYER_FAMILY = {
    MapLayer.ISLAND: WorldFamily.ORIGINAL,
    MapLayer.CAVE: WorldFamily.ORIGINAL,
    MapLayer.INVERSE: WorldFamily.INVERSE,
    MapLayer.ETHEREAL: WorldFamily.ETHEREAL,
    MapLayer.MAP_2D: WorldFamily.ORIGINAL,
}


def family_for(layer: MapLayer) -> WorldFamily:
    """Imported world-family taxonomy for a traversal layer."""

    if not isinstance(layer, MapLayer):
        raise WorldGraphError("layer must be a MapLayer")
    return _LAYER_FAMILY[layer]


def layer_is_planar(layer: MapLayer) -> bool:
    if not isinstance(layer, MapLayer):
        raise WorldGraphError("layer must be a MapLayer")
    return layer is MapLayer.MAP_2D


def canon_digest_of(document: str) -> str:
    """Content-address a canon document. The digest is lowercase SHA-256."""

    if not isinstance(document, str) or document == "":
        raise WorldGraphError("canon document must be a non-empty string")
    if any(ord(char) < 32 for char in document):
        raise WorldGraphError("canon document contains control characters")
    return sha256(document.encode("utf-8")).hexdigest()


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise WorldGraphError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise WorldGraphError(f"{field} must be a stable identifier")
    return value


def _world_id(value: object) -> str:
    if not isinstance(value, str) or _WORLD_ID.fullmatch(value) is None:
        raise WorldGraphError("world_id must be a short stable identifier")
    return value


def _rule_id(value: str) -> str:
    if _RULE_ID.fullmatch(value) is None:
        raise WorldGraphError("physical-rule id is not canonical")
    return value


def _quantize(value: object, field: str, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldGraphError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < low or number > high:
        raise WorldGraphError(f"{field} is out of range")
    quantized = round(number, 6)
    if quantized == 0:
        quantized = 0.0
    return quantized


def _rules(value: object) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise WorldGraphError("physical-rule ids must be a sequence of strings")
    if len(value) > 8:
        raise WorldGraphError("physical-rule set exceeds 8 ids")
    cleaned = tuple(_rule_id(item) if isinstance(item, str) else "" for item in value)
    if any(item == "" for item in cleaned):
        raise WorldGraphError("physical-rule ids must be strings")
    ordered = tuple(sorted(set(cleaned)))
    if len(ordered) != len(cleaned):
        raise WorldGraphError("physical-rule ids must be unique")
    if len(",".join(ordered)) > 128:
        raise WorldGraphError("physical-rule ids exceed the scene attribute bound")
    return ordered


def _join_rules(rules: tuple[str, ...]) -> str:
    return ",".join(rules)


def _split_rules(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise WorldGraphError("scene graph physical-rule attribute is not text")
    if value == "":
        return ()
    parts = tuple(value.split(","))
    parsed = _rules(parts)
    if _join_rules(parsed) != value:
        raise WorldGraphError("scene graph physical-rule attribute is not canonical")
    return parsed


def content_address(payload: Mapping[str, object]) -> str:
    """SHA-256 of the canonical JSON payload."""

    try:
        body = canonical_json_bytes(dict(payload))
    except CanonicalContractError as exc:
        raise WorldGraphError("edge payload is not canonical JSON") from exc
    return sha256(body).hexdigest()


@dataclass(frozen=True, slots=True)
class ClimateBounds:
    """Biome climate the world can sustain. Intervals are closed."""

    biome: str
    temperature_min_c: float
    temperature_max_c: float
    humidity_min: float
    humidity_max: float

    def __post_init__(self) -> None:
        if not isinstance(self.biome, str) or _BIOME.fullmatch(self.biome) is None:
            raise WorldGraphError("biome must be a short lowercase label")
        object.__setattr__(
            self,
            "temperature_min_c",
            _quantize(self.temperature_min_c, "temperature_min_c", low=-_METRE_LIMIT, high=_METRE_LIMIT),
        )
        object.__setattr__(
            self,
            "temperature_max_c",
            _quantize(self.temperature_max_c, "temperature_max_c", low=-_METRE_LIMIT, high=_METRE_LIMIT),
        )
        object.__setattr__(
            self,
            "humidity_min",
            _quantize(self.humidity_min, "humidity_min", low=0.0, high=1.0),
        )
        object.__setattr__(
            self,
            "humidity_max",
            _quantize(self.humidity_max, "humidity_max", low=0.0, high=1.0),
        )
        if self.temperature_min_c > self.temperature_max_c:
            raise WorldGraphError("temperature bounds are inverted")
        if self.humidity_min > self.humidity_max:
            raise WorldGraphError("humidity bounds are inverted")


@dataclass(frozen=True, slots=True)
class ClimateEnvelope:
    """Climate the traveler can carry across a transition. Intervals are closed."""

    temperature_min_c: float
    temperature_max_c: float
    humidity_min: float
    humidity_max: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "temperature_min_c",
            _quantize(self.temperature_min_c, "temperature_min_c", low=-_METRE_LIMIT, high=_METRE_LIMIT),
        )
        object.__setattr__(
            self,
            "temperature_max_c",
            _quantize(self.temperature_max_c, "temperature_max_c", low=-_METRE_LIMIT, high=_METRE_LIMIT),
        )
        object.__setattr__(
            self,
            "humidity_min",
            _quantize(self.humidity_min, "humidity_min", low=0.0, high=1.0),
        )
        object.__setattr__(
            self,
            "humidity_max",
            _quantize(self.humidity_max, "humidity_max", low=0.0, high=1.0),
        )
        if self.temperature_min_c > self.temperature_max_c:
            raise WorldGraphError("temperature envelope is inverted")
        if self.humidity_min > self.humidity_max:
            raise WorldGraphError("humidity envelope is inverted")


def climate_overlaps(bounds: ClimateBounds, envelope: ClimateEnvelope) -> bool:
    """True when both closed intervals share at least one value."""

    if not isinstance(bounds, ClimateBounds) or not isinstance(envelope, ClimateEnvelope):
        raise WorldGraphError("climate overlap requires bounds and an envelope")
    temperature = (
        bounds.temperature_min_c <= envelope.temperature_max_c
        and envelope.temperature_min_c <= bounds.temperature_max_c
    )
    humidity = (
        bounds.humidity_min <= envelope.humidity_max
        and envelope.humidity_min <= bounds.humidity_max
    )
    return temperature and humidity


@dataclass(frozen=True, slots=True)
class FictionalPosition:
    """Explicit fictional metres. ``z_m`` is absent on the 2D map layer."""

    layer: MapLayer
    x_m: float
    y_m: float
    z_m: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.layer, MapLayer):
            raise WorldGraphError("position layer must be a MapLayer")
        object.__setattr__(self, "x_m", _quantize(self.x_m, "x_m", low=-_METRE_LIMIT, high=_METRE_LIMIT))
        object.__setattr__(self, "y_m", _quantize(self.y_m, "y_m", low=-_METRE_LIMIT, high=_METRE_LIMIT))
        if layer_is_planar(self.layer):
            if self.z_m is not None:
                raise WorldGraphError("the 2D map layer has no vertical metre coordinate")
            return
        if self.z_m is None:
            raise WorldGraphError("a 3D layer requires a vertical metre coordinate")
        object.__setattr__(
            self,
            "z_m",
            _quantize(self.z_m, "z_m", low=-_METRE_LIMIT, high=_METRE_LIMIT),
        )

    def as_record(self) -> dict[str, object]:
        return {
            "layer": self.layer.value,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "z_m": self.z_m,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "FictionalPosition":
        if not isinstance(record, Mapping):
            raise WorldGraphError("position record must be a mapping")
        geographic = sorted(set(record) & _GEOGRAPHIC)
        if geographic:
            raise WorldGraphError(
                "coordinates are fictional metres, not geographic latitude or longitude"
            )
        unknown = sorted(set(record) - _POSITION_KEYS)
        if unknown:
            raise WorldGraphError("position record has unknown fields")
        missing = sorted({"layer", "x_m", "y_m"} - set(record))
        if missing:
            raise WorldGraphError("position record is missing fields")
        try:
            layer = MapLayer(str(record["layer"]))
        except ValueError as exc:
            raise WorldGraphError("position layer is unknown") from exc
        if layer_is_planar(layer):
            if "z_m" in record and record["z_m"] is not None:
                raise WorldGraphError("the 2D map layer has no vertical metre coordinate")
            return cls(layer, record["x_m"], record["y_m"], None)  # type: ignore[arg-type]
        if "z_m" not in record or record["z_m"] is None:
            raise WorldGraphError("a 3D layer requires a vertical metre coordinate")
        return cls(layer, record["x_m"], record["y_m"], record["z_m"])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class WorldNode:
    """One world in the family. Identity is the continuity the traveler keeps."""

    world_id: str
    identity: str
    canon_digest: str
    expected_predecessor: str
    climate: ClimateBounds
    rule_ids: tuple[str, ...]
    position: FictionalPosition
    family: WorldFamily

    def block(self) -> dict[str, object]:
        return {
            "biome": self.climate.biome,
            "canon_digest": self.canon_digest,
            "expected_predecessor": self.expected_predecessor,
            "family": self.family.value,
            "humidity_max": self.climate.humidity_max,
            "humidity_min": self.climate.humidity_min,
            "identity": self.identity,
            "layer": self.position.layer.value,
            "rule_ids": list(self.rule_ids),
            "temperature_max_c": self.climate.temperature_max_c,
            "temperature_min_c": self.climate.temperature_min_c,
            "world_id": self.world_id,
            "x_m": self.position.x_m,
            "y_m": self.position.y_m,
            "z_m": self.position.z_m,
        }


@dataclass(frozen=True, slots=True)
class Traveler:
    """Traveler state carried into admission. Travel returns a new value."""

    identity: str
    world_id: str
    canon_digest: str
    envelope: ClimateEnvelope
    rule_ids: tuple[str, ...]
    position: FictionalPosition

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _token(self.identity, "identity"))
        object.__setattr__(self, "world_id", _world_id(self.world_id))
        object.__setattr__(self, "canon_digest", _digest(self.canon_digest, "canon_digest"))
        if not isinstance(self.envelope, ClimateEnvelope):
            raise WorldGraphError("traveler envelope must be a ClimateEnvelope")
        if not isinstance(self.position, FictionalPosition):
            raise WorldGraphError("traveler position must be fictional metres")
        object.__setattr__(self, "rule_ids", _rules(self.rule_ids))


@dataclass(frozen=True, slots=True)
class ContentAddressedEdge:
    """A directed world transition whose id is the digest of its content."""

    address: str
    source_id: str
    destination_id: str
    canonical_json: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "address", _digest(self.address, "address"))
        object.__setattr__(self, "source_id", _world_id(self.source_id))
        object.__setattr__(self, "destination_id", _world_id(self.destination_id))
        if not isinstance(self.canonical_json, str):
            raise WorldGraphError("edge canonical JSON must be text")
        try:
            parsed = json.loads(self.canonical_json)
            rebuilt = canonical_json_bytes(parsed).decode("utf-8")
        except (UnicodeError, ValueError, CanonicalContractError) as exc:
            raise WorldGraphError("edge canonical JSON is not canonical") from exc
        if rebuilt != self.canonical_json:
            raise WorldGraphError("edge canonical JSON is not canonical")
        if sha256(self.canonical_json.encode("utf-8")).hexdigest() != self.address:
            raise WorldGraphError("edge address does not match its content")

    def payload(self) -> dict[str, object]:
        import json

        parsed = json.loads(self.canonical_json)
        if not isinstance(parsed, dict):
            raise WorldGraphError("edge payload must be an object")
        return parsed


@dataclass(frozen=True, slots=True)
class TransitionRefusal:
    """A transition that was not admitted. ``traveler`` is still at the source."""

    constraint: Constraint
    source_id: str
    destination_id: str
    traveler: Traveler
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.constraint, Constraint):
            raise WorldGraphError("refusal constraint is not typed")
        if not isinstance(self.traveler, Traveler):
            raise WorldGraphError("refusal must carry the traveler")
        if self.traveler.world_id != self.source_id:
            raise WorldGraphError("a rejected transition moved the traveler")
        if not isinstance(self.detail, str) or self.detail == "":
            raise WorldGraphError("refusal detail must be text")


@dataclass(frozen=True, slots=True)
class AdmittedTransition:
    """One admitted hop. ``traveler`` is the state after the hop."""

    edge: ContentAddressedEdge
    traveler: Traveler
    constraints_satisfied: tuple[str, ...] = _CONSTRAINTS

    def __post_init__(self) -> None:
        if not isinstance(self.edge, ContentAddressedEdge):
            raise WorldGraphError("admitted transition requires a content-addressed edge")
        if not isinstance(self.traveler, Traveler):
            raise WorldGraphError("admitted transition requires a traveler")
        if self.traveler.world_id != self.edge.destination_id:
            raise WorldGraphError("admitted traveler is not in the destination world")
        if self.constraints_satisfied != _CONSTRAINTS:
            raise WorldGraphError("admission must record every satisfied constraint")

    @property
    def address(self) -> str:
        return self.edge.address

    @property
    def source_id(self) -> str:
        return self.edge.source_id

    @property
    def destination_id(self) -> str:
        return self.edge.destination_id


def _edge_between(source: WorldNode, destination: WorldNode) -> ContentAddressedEdge:
    payload = {
        "destination": destination.block(),
        "schema": EDGE_SCHEMA,
        "source": source.block(),
    }
    try:
        body = canonical_json_bytes(payload)
    except CanonicalContractError as exc:
        raise WorldGraphError("edge payload is not canonical JSON") from exc
    text = body.decode("utf-8")
    return ContentAddressedEdge(
        address=sha256(body).hexdigest(),
        source_id=source.world_id,
        destination_id=destination.world_id,
        canonical_json=text,
    )


def _portal_id(source_id: str, destination_id: str) -> str:
    return f"p.{source_id}.{destination_id}"


def _compat_digest(left: tuple[str, ...], right: tuple[str, ...]) -> str:
    payload = {
        "left": list(left),
        "right": list(right),
        "schema": RULE_SCHEMA,
    }
    return content_address(payload)


def _compat_id(digest: str) -> str:
    return "compat" + digest[:58]


class WorldFamilyGraph:
    """Family graph whose nodes and portals are entities in one scene graph."""

    def __init__(self, family_id: str = "worldfamily") -> None:
        self.scene = WorldState(_token(family_id, "family_id"), tick=0)

    def add_world(
        self,
        world_id: str,
        *,
        identity: str,
        canon_digest: str,
        expected_predecessor: str,
        climate: ClimateBounds,
        rule_ids: tuple[str, ...] | list[str],
        position: FictionalPosition,
    ) -> WorldNode:
        node_id = _world_id(world_id)
        if self.scene.get(node_id) is not None:
            raise WorldGraphError(f"world already exists: {node_id}")
        identity_token = _token(identity, "identity")
        canon = _digest(canon_digest, "canon_digest")
        predecessor = _digest(expected_predecessor, "expected_predecessor")
        if not isinstance(climate, ClimateBounds):
            raise WorldGraphError("climate must be ClimateBounds")
        if not isinstance(position, FictionalPosition):
            raise WorldGraphError("position must be fictional metres")
        rules = _rules(rule_ids)
        family = family_for(position.layer)
        z_slot = 0.0 if position.z_m is None else position.z_m
        try:
            self.scene.spawn(
                node_id,
                kind="world",
                tick=self.scene.tick,
                name=node_id,
                transform=Transform(translation=(position.x_m, position.y_m, z_slot)),
                attributes={
                    "biome": climate.biome,
                    "canon": canon,
                    "family": family.value,
                    "h_max": climate.humidity_max,
                    "h_min": climate.humidity_min,
                    "identity": identity_token,
                    "layer": position.layer.value,
                    "planar": 1 if position.z_m is None else 0,
                    "predecessor": predecessor,
                    "rules": _join_rules(rules),
                    "t_max": climate.temperature_max_c,
                    "t_min": climate.temperature_min_c,
                },
            )
        except WorldSceneError as exc:
            raise WorldGraphError("scene graph rejected the world node") from exc
        return self.world(node_id)

    def link(self, source_id: str, destination_id: str) -> str:
        source = self.world(source_id)
        destination = self.world(destination_id)
        if source.world_id == destination.world_id:
            raise WorldGraphError("a world cannot transition to itself")
        portal = _portal_id(source.world_id, destination.world_id)
        existing = self.scene.get(portal)
        if existing is not None:
            if existing.kind != "portal" or existing.parent_id != source.world_id:
                raise WorldGraphError("portal id collided with another scene entity")
            return _edge_between(source, destination).address
        try:
            self.scene.spawn(
                portal,
                kind="portal",
                tick=self.scene.tick,
                parent_id=source.world_id,
                name=destination.world_id,
                attributes={"dest": destination.world_id},
            )
        except WorldSceneError as exc:
            raise WorldGraphError("scene graph rejected the portal") from exc
        return _edge_between(source, destination).address

    def declare_compatible(
        self,
        source_rules: tuple[str, ...] | list[str],
        destination_rules: tuple[str, ...] | list[str],
    ) -> str:
        left = _rules(source_rules)
        right = _rules(destination_rules)
        digest = _compat_digest(left, right)
        entity_id = _compat_id(digest)
        existing = self.scene.get(entity_id)
        if existing is not None:
            if existing.kind != "compat" or existing.attributes.get("pin") != digest:
                raise WorldGraphError("rule-compatibility id collided")
            return digest
        try:
            self.scene.spawn(
                entity_id,
                kind="compat",
                tick=self.scene.tick,
                name="rules",
                attributes={
                    "left": _join_rules(left),
                    "pin": digest,
                    "right": _join_rules(right),
                },
            )
        except WorldSceneError as exc:
            raise WorldGraphError("scene graph rejected the rule declaration") from exc
        return digest

    def world(self, world_id: str) -> WorldNode:
        node_id = _world_id(world_id)
        try:
            entity = self.scene.require(node_id)
        except WorldSceneError as exc:
            raise WorldGraphError(f"unknown world: {node_id}") from exc
        if entity.kind != "world":
            raise WorldGraphError(f"scene entity is not a world: {node_id}")
        attrs = entity.attributes
        try:
            layer = MapLayer(str(attrs["layer"]))
            family = WorldFamily(str(attrs["family"]))
        except (KeyError, ValueError) as exc:
            raise WorldGraphError("world scene attributes are incomplete") from exc
        if family is not family_for(layer):
            raise WorldGraphError("world family does not match its layer")
        planar = attrs.get("planar")
        translation = entity.transform.translation
        if planar == 1:
            if not layer_is_planar(layer) or translation[2] != 0.0:
                raise WorldGraphError("planar world stored a vertical coordinate")
            position = FictionalPosition(layer, translation[0], translation[1], None)
        elif planar == 0:
            if layer_is_planar(layer):
                raise WorldGraphError("vertical world is marked as a 2D map")
            position = FictionalPosition(layer, translation[0], translation[1], translation[2])
        else:
            raise WorldGraphError("world planar flag is invalid")
        climate = ClimateBounds(
            biome=str(attrs["biome"]),
            temperature_min_c=attrs["t_min"],  # type: ignore[arg-type]
            temperature_max_c=attrs["t_max"],  # type: ignore[arg-type]
            humidity_min=attrs["h_min"],  # type: ignore[arg-type]
            humidity_max=attrs["h_max"],  # type: ignore[arg-type]
        )
        return WorldNode(
            world_id=node_id,
            identity=_token(attrs.get("identity"), "identity"),
            canon_digest=_digest(attrs.get("canon"), "canon_digest"),
            expected_predecessor=_digest(attrs.get("predecessor"), "expected_predecessor"),
            climate=climate,
            rule_ids=_split_rules(attrs.get("rules")),
            position=position,
            family=family,
        )

    def worlds(self) -> tuple[WorldNode, ...]:
        nodes = []
        for entity_id in self.scene.roots():
            entity = self.scene.require(entity_id)
            if entity.kind == "world":
                nodes.append(self.world(entity_id))
        return tuple(sorted(nodes, key=lambda node: node.world_id))

    def destinations(self, world_id: str) -> tuple[str, ...]:
        source = self.world(world_id)
        found: list[str] = []
        for child_id in self.scene.children(source.world_id):
            child = self.scene.require(child_id)
            if child.kind != "portal":
                continue
            dest = child.attributes.get("dest")
            if not isinstance(dest, str):
                raise WorldGraphError("portal is missing its destination")
            found.append(self.world(dest).world_id)
        if len(found) != len(set(found)):
            raise WorldGraphError("duplicate portal from one world")
        return tuple(sorted(found))

    def edge(self, source_id: str, destination_id: str) -> ContentAddressedEdge:
        return _edge_between(self.world(source_id), self.world(destination_id))

    def edge_address(self, source_id: str, destination_id: str) -> str:
        return self.edge(source_id, destination_id).address

    def compatible(self, source_rules: tuple[str, ...], destination_rules: tuple[str, ...]) -> bool:
        left = _rules(source_rules)
        right = _rules(destination_rules)
        digest = _compat_digest(left, right)
        entity = self.scene.get(_compat_id(digest))
        if entity is None or entity.kind != "compat":
            return False
        if entity.attributes.get("pin") != digest:
            raise WorldGraphError("rule-compatibility pin drifted")
        stored_left = _split_rules(entity.attributes.get("left"))
        stored_right = _split_rules(entity.attributes.get("right"))
        return stored_left == left and stored_right == right

    def cross(
        self, traveler: Traveler, destination_id: str
    ) -> AdmittedTransition | TransitionRefusal:
        """Admit one transition. A refusal keeps ``traveler`` in the source world."""

        if not isinstance(traveler, Traveler):
            raise WorldGraphError("traveler must be a Traveler")
        source = self.world(traveler.world_id)
        destination = self.world(destination_id)
        if traveler.position.layer is not source.position.layer:
            raise WorldGraphError("traveler layer does not match the source world")
        if destination.world_id not in self.destinations(source.world_id):
            return self._refuse(
                Constraint.DISCONNECTED,
                source,
                destination,
                traveler,
                "no declared transition reaches the destination",
            )
        constraint = self._first_constraint(traveler, source, destination)
        if constraint is not None:
            return self._refuse(constraint, source, destination, traveler, _DETAIL[constraint])
        arrived = Traveler(
            identity=traveler.identity,
            world_id=destination.world_id,
            canon_digest=destination.canon_digest,
            envelope=traveler.envelope,
            rule_ids=destination.rule_ids,
            position=destination.position,
        )
        return AdmittedTransition(edge=self.edge(source.world_id, destination.world_id), traveler=arrived)

    def _first_constraint(
        self, traveler: Traveler, source: WorldNode, destination: WorldNode
    ) -> Constraint | None:
        if (
            traveler.identity != source.identity
            or source.identity != destination.identity
        ):
            return Constraint.IDENTITY
        if (
            traveler.canon_digest != source.canon_digest
            or source.canon_digest != destination.expected_predecessor
        ):
            return Constraint.CANON
        if not climate_overlaps(destination.climate, traveler.envelope):
            return Constraint.CLIMATE
        if traveler.rule_ids != source.rule_ids or not self.compatible(
            source.rule_ids, destination.rule_ids
        ):
            return Constraint.PHYSICS
        return None

    def _refuse(
        self,
        constraint: Constraint,
        source: WorldNode,
        destination: WorldNode,
        traveler: Traveler,
        detail: str,
    ) -> TransitionRefusal:
        return TransitionRefusal(
            constraint=constraint,
            source_id=source.world_id,
            destination_id=destination.world_id,
            traveler=traveler,
            detail=detail,
        )

    def synthesize(self, traveler: Traveler, goal_id: str):
        """Deterministic admitted route, or the first broken constraint."""

        from skeleton.frontier_worldgraph.route import synthesize_route

        return synthesize_route(self, traveler, goal_id)


_DETAIL = {
    Constraint.IDENTITY: "identity is not preserved",
    Constraint.CANON: "canon digest does not match the destination expected predecessor",
    Constraint.CLIMATE: "climate bounds do not overlap the carried envelope",
    Constraint.PHYSICS: "physical-rule set is not declared compatible",
    Constraint.DISCONNECTED: "no declared transition reaches the destination",
}
