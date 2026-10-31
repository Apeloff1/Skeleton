"""Deterministic, offline, source-bound grid campaign within the canonical game plane.

This is a text-grid adapter, not a claim of native 3D, audio, or device support.
All actions return new immutable sessions; a caller owns durable atomic storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    GameplayContractError, QuestNode, dig, quest_order, req_id,
)

MAX_MAP = 64
MAX_OBJECTS = 128
MAX_EVENTS = 4096
MAX_SOURCE_BYTES = 65536
DIRECTIONS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}


def _fail(message: str) -> None:
    raise GameplayContractError(message)


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - optional:
        _fail("invalid campaign object fields")
    return value


def _ids(value: Any, name: str, maximum: int = MAX_OBJECTS) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(f"invalid {name} list")
    result = tuple(req_id(item, name) for item in value)
    if len(set(result)) != len(result):
        _fail(f"duplicate {name}")
    return result


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GameplayContractError("invalid canonical campaign JSON") from exc


@dataclass(frozen=True)
class Campaign:
    """Validated immutable source identity and original text-grid content."""

    source_json: str
    source_digest: str

    @classmethod
    def load(cls, raw: Mapping[str, Any]) -> "Campaign":
        if not isinstance(raw, dict):
            _fail("campaign must be an object")
        encoded = _canonical(raw)
        if len(encoded.encode("utf-8")) > MAX_SOURCE_BYTES:
            _fail("campaign exceeds source budget")
        source = json.loads(encoded)
        _keys(source, {"version", "game_id", "title", "license", "author", "rows", "objects", "quests", "endings"})
        if type(source["version"]) is not int or source["version"] != 1:
            _fail("unsupported campaign version")
        for field in ("game_id", "title", "author"):
            req_id(source[field], field)
        if source["license"] not in ("CC0-1.0", "CC-BY-4.0"):
            _fail("original content license required")
        rows = source["rows"]
        if not isinstance(rows, list) or not 3 <= len(rows) <= MAX_MAP:
            _fail("invalid grid height")
        if not all(isinstance(row, str) for row in rows):
            _fail("invalid grid row")
        width = len(rows[0])
        if not 3 <= width <= MAX_MAP or any(len(row) != width for row in rows):
            _fail("invalid grid width")
        if any(set(row) - set("#.SG") for row in rows):
            _fail("invalid grid character")
        if sum(row.count("S") for row in rows) != 1 or sum(row.count("G") for row in rows) != 1:
            _fail("campaign needs exactly one start and goal")
        objects = source["objects"]
        if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
            _fail("invalid objects")
        object_ids = set()
        item_ids = set()
        npc_ids = set()
        occupied = set()
        for obj in objects:
            _keys(obj, {"id", "kind", "x", "y"})
            identifier = req_id(obj["id"], "object id")
            if identifier in object_ids:
                _fail("duplicate object")
            object_ids.add(identifier)
            if obj["kind"] not in ("item", "npc"):
                _fail("invalid object kind")
            x, y = obj["x"], obj["y"]
            if type(x) is not int or type(y) is not int or not (0 <= x < width and 0 <= y < len(rows)):
                _fail("object outside grid")
            if rows[y][x] == "#" or (x, y) in occupied:
                _fail("object on wall or overlapping")
            occupied.add((x, y))
            (item_ids if obj["kind"] == "item" else npc_ids).add(identifier)
        quests = source["quests"]
        if not isinstance(quests, list) or len(quests) > MAX_OBJECTS:
            _fail("invalid quests")
        quest_nodes = []
        for quest in quests:
            _keys(quest, {"id", "requires_items", "requires_npcs", "requires_quests"})
            identifier = req_id(quest["id"], "quest id")
            items = _ids(quest["requires_items"], "item")
            npcs = _ids(quest["requires_npcs"], "npc")
            dependencies = _ids(quest["requires_quests"], "quest")
            if not set(items) <= item_ids or not set(npcs) <= npc_ids:
                _fail("quest references missing object")
            quest_nodes.append(QuestNode(identifier, dependencies, dig(quest)))
        quest_order(quest_nodes)
        quest_ids = {node.node_id for node in quest_nodes}
        endings = source["endings"]
        if not isinstance(endings, list) or not 1 <= len(endings) <= MAX_OBJECTS:
            _fail("invalid endings")
        ending_ids = set()
        for ending in endings:
            _keys(ending, {"id", "requires_quests", "outcome"})
            identifier = req_id(ending["id"], "ending id")
            if identifier in ending_ids or ending["outcome"] not in ("victory", "alternate"):
                _fail("duplicate or invalid ending")
            ending_ids.add(identifier)
            if not set(_ids(ending["requires_quests"], "quest")) <= quest_ids:
                _fail("ending references missing quest")
        return cls(encoded, sha256(encoded.encode("utf-8")).hexdigest())

    @property
    def spec(self) -> dict:
        return json.loads(self.source_json)

    @property
    def start(self) -> tuple[int, int]:
        rows = self.spec["rows"]
        return next((row.index("S"), y) for y, row in enumerate(rows) if "S" in row)


@dataclass(frozen=True)
class Command:
    command_id: str
    kind: str
    target: str = ""

    def __post_init__(self) -> None:
        req_id(self.command_id, "command_id")
        if self.kind not in ("move", "collect", "talk", "finish", "wait"):
            _fail("unknown command")
        if self.kind == "move" and self.target not in DIRECTIONS:
            _fail("unknown direction")
        if self.kind in ("collect", "talk", "finish"):
            req_id(self.target, "target")
        if self.kind == "wait" and self.target:
            _fail("wait cannot have target")


@dataclass(frozen=True)
class Session:
    """Immutable game state; events are source-bound and replay-verified."""

    campaign: Campaign
    x: int
    y: int
    tick: int = 0
    inventory: tuple[str, ...] = ()
    spoken: tuple[str, ...] = ()
    quests: tuple[str, ...] = ()
    ending: str | None = None
    events: tuple[dict, ...] = ()

    @classmethod
    def new(cls, campaign: Campaign) -> "Session":
        x, y = campaign.start
        return cls(campaign, x, y)

    def _completed(self, inventory: tuple[str, ...], spoken: tuple[str, ...]) -> tuple[str, ...]:
        completed: set[str] = set()
        quests = {q["id"]: q for q in self.campaign.spec["quests"]}
        nodes = [QuestNode(q["id"], tuple(q["requires_quests"]), dig(q)) for q in quests.values()]
        for identifier in quest_order(nodes):
            quest = quests[identifier]
            if (set(quest["requires_items"]) <= set(inventory)
                and set(quest["requires_npcs"]) <= set(spoken)
                and set(quest["requires_quests"]) <= completed):
                completed.add(identifier)
        return tuple(sorted(completed))

    def step(self, command: Command) -> "Session":
        if self.ending is not None:
            _fail("terminal game state")
        if len(self.events) >= MAX_EVENTS:
            _fail("event budget exhausted")
        if command.command_id in {event["command_id"] for event in self.events}:
            _fail("replayed command identity")
        x, y = self.x, self.y
        inventory = self.inventory
        spoken = self.spoken
        ending = None
        spec = self.campaign.spec
        if command.kind == "move":
            dx, dy = DIRECTIONS[command.target]
            nx, ny = x + dx, y + dy
            rows = spec["rows"]
            if not (0 <= ny < len(rows) and 0 <= nx < len(rows[0])) or rows[ny][nx] == "#":
                _fail("collision with wall or boundary")
            x, y = nx, ny
        elif command.kind in ("collect", "talk"):
            expected_kind = "item" if command.kind == "collect" else "npc"
            matched = next((obj for obj in spec["objects"] if obj["id"] == command.target), None)
            if matched is None or matched["kind"] != expected_kind or (matched["x"], matched["y"]) != (x, y):
                _fail("interaction target unavailable")
            if command.kind == "collect":
                if command.target in inventory:
                    _fail("item already collected")
                inventory = tuple(sorted((*inventory, command.target)))
            else:
                if command.target in spoken:
                    _fail("NPC already contacted")
                spoken = tuple(sorted((*spoken, command.target)))
        elif command.kind == "finish":
            if spec["rows"][y][x] != "G":
                _fail("finish requires goal tile")
            selected = next((item for item in spec["endings"] if item["id"] == command.target), None)
            if selected is None or not set(selected["requires_quests"]) <= set(self.quests):
                _fail("ending requirements unmet")
            ending = command.target
        quests = self._completed(inventory, spoken)
        event = {
            "command_id": command.command_id,
            "kind": command.kind,
            "target": command.target,
            "tick": self.tick + 1,
            "previous_digest": self.events[-1]["digest"] if self.events else self.campaign.source_digest,
        }
        event["digest"] = dig({
            "event": event, "source": self.campaign.source_digest, "position": [x, y],
            "inventory": inventory, "spoken": spoken, "quests": quests, "ending": ending,
        })
        return Session(self.campaign, x, y, self.tick + 1, inventory, spoken, quests, ending,
                       (*self.events, event))

    @property
    def state_digest(self) -> str:
        return dig(self._state())

    def _state(self) -> dict:
        return {
            "x": self.x, "y": self.y, "tick": self.tick,
            "inventory": list(self.inventory), "spoken": list(self.spoken),
            "quests": list(self.quests), "ending": self.ending,
        }

    def snapshot(self) -> dict:
        return {
            "schema_version": 1, "source_digest": self.campaign.source_digest,
            "state": self._state(), "state_digest": self.state_digest,
            "events": [dict(event) for event in self.events],
        }

    @classmethod
    def restore(cls, campaign: Campaign, payload: Any) -> "Session":
        _keys(payload, {"schema_version", "source_digest", "state", "state_digest", "events"})
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            _fail("unsupported save version")
        if payload["source_digest"] != campaign.source_digest:
            _fail("save source mismatch")
        events = payload["events"]
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            _fail("invalid event ledger")
        session = cls.new(campaign)
        for event in events:
            _keys(event, {"command_id", "kind", "target", "tick", "previous_digest", "digest"})
            session = session.step(Command(event["command_id"], event["kind"], event["target"]))
            if session.events[-1] != event:
                _fail("save event integrity mismatch")
        if payload["state"] != session._state() or payload["state_digest"] != session.state_digest:
            _fail("save state integrity mismatch")
        return session

    def render(self) -> str:
        rows = [list(row) for row in self.campaign.spec["rows"]]
        for obj in self.campaign.spec["objects"]:
            if obj["kind"] == "item" and obj["id"] in self.inventory:
                continue
            rows[obj["y"]][obj["x"]] = "*" if obj["kind"] == "item" else "N"
        rows[self.y][self.x] = "@"
        return "\n".join("".join(row) for row in rows)
