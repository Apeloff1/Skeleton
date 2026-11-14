"""Native Godot quest integration for the recovered B028/B030/B037 game systems.

This is opt-in production-path code. It binds the exact *generated* Godot
room graph to reproducible mechanic packs and a proven quest-objective ledger,
then emits a Godot autoload that consumes real EventBus.room_entered events.
The runtime provides visible quest HUD, typed progression and checked
save/restore snapshots. No external provider, shell, asset download or file
system write is used during in-memory composition.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .constraint_quest_synthesis import ContentPolicy, WorldModel, validate_quest
from .genre_template_composition import PackRegistry
from .original_quest_slice import compose_verified_quest_slice, verify_original_slice

SCHEMA = "skeleton.gameforge.native_quest.v1"
SAVE_SCHEMA = "skeleton.gameforge.native_quest_save.v1"
QUEST_PATH = "data/quest_slice.json"
SCRIPT_PATH = "scripts/autoloads/quest_runtime.gd"
PROFILE_ENTRY = 'QuestRuntime="*res://scripts/autoloads/quest_runtime.gd"\n'
INPUT_ENTRY = 'InputBind="*res://scripts/autoloads/input_bind.gd"\n'
ROOM_PATH = "data/rooms.json"
_ROOM_ID = re.compile(r"^r[0-9]{2}$")
_PACKS = (
    {"id": "native.movement.v1", "provides": ("movement",)},
    {"id": "native.quest.v1", "provides": ("quests",), "requires": ("movement",)},
)
_POLICY = ContentPolicy(
    max_reward_per_step=10, max_total_reward=80,
    allowed_reward_kinds=("xp", "gold", "item"),
)


class NativeQuestError(ValueError):
    """Bad source graph, invalid proof or conflicting project attachment."""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _registry() -> PackRegistry:
    return PackRegistry(_PACKS)


def _room_world(raw: str) -> WorldModel:
    """Only accept the canonical bounded, undirected generated room graph."""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 256_000:
        raise NativeQuestError("missing or oversized generated room graph")
    try:
        graph = json.loads(raw)
        rooms = graph["rooms"]
        edges = graph["edges"]
        if type(rooms) is not list or not 3 <= len(rooms) <= 24:
            raise NativeQuestError("invalid Godot room count")
        if type(edges) is not list or len(edges) > 256:
            raise NativeQuestError("invalid Godot room edges")
        ids = [room["id"] for room in rooms]
        if any(type(i) is not str or not _ROOM_ID.fullmatch(i) for i in ids):
            raise NativeQuestError("invalid Godot room identifier")
        if len(set(ids)) != len(ids) or "r00" not in ids:
            raise NativeQuestError("duplicate or missing spawn")
        adjacency: dict[str, set[str]] = {room_id: set() for room_id in ids}
        for edge in edges:
            source, target = edge["from"], edge["to"]
            if source not in adjacency or target not in adjacency or source == target:
                raise NativeQuestError("out-of-graph or self-loop room edge")
            adjacency[source].add(target)
            adjacency[target].add(source)
        world = WorldModel(
            start="r00",
            edges={key: tuple(sorted(value)) for key, value in adjacency.items()},
            npcs={},
        )
        if world.reachable() != set(adjacency):
            raise NativeQuestError("quest world graph is disconnected")
        return world
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, AttributeError) as exc:
        raise NativeQuestError("invalid generated world graph") from exc


_GDSCRIPT = r'''extends Node
## QuestRuntime — native, event-driven progress from sealed generated room graph.
## No arbitrary script execution; data originates from a source-verified quest.
signal objective_completed(objective_id: String, room_id: String)
signal quest_completed()

const SOURCE_SHA256: String = "__SHA256__"
const QUEST_PATH: String = "res://data/quest_slice.json"
const SAVE_SCHEMA: String = "skeleton.gameforge.native_quest_save.v1"

var _loaded: bool = false
var _title: String = ""
var _steps: Array = []
var _next_step: int = 0
var _earned: Dictionary = {}
var _visits: Array[String] = []
var _hud: Label

func _ready() -> void:
	var raw: String = FileAccess.get_file_as_string(QUEST_PATH)
	if raw.is_empty() or raw.sha256_text() != SOURCE_SHA256:
		push_error("QuestRuntime source integrity failure")
		return
	var payload: Variant = JSON.parse_string(raw)
	if typeof(payload) != TYPE_DICTIONARY:
		push_error("QuestRuntime malformed JSON")
		return
	var doc: Dictionary = payload
	if doc.get("schema", "") != "skeleton.gameforge.native_quest.v1":
		push_error("QuestRuntime unsupported source schema")
		return
	var slice_doc: Dictionary = doc.get("slice", {})
	var generated: Dictionary = slice_doc.get("world_quest", {})
	var quest: Dictionary = generated.get("quest", {})
	var steps: Variant = quest.get("steps", [])
	if typeof(steps) != TYPE_ARRAY or steps.is_empty() or steps.size() > 8:
		push_error("QuestRuntime malformed step sequence")
		return
	_steps = steps
	_title = str(quest.get("title", "Explore"))
	_loaded = true
	EventBus.room_entered.connect(_on_room_entered)
	_mount_hud()
	_refresh_hud()

func _mount_hud() -> void:
	var layer: CanvasLayer = CanvasLayer.new()
	layer.layer = 8
	add_child(layer)
	_hud = Label.new()
	_hud.position = Vector2(16, 16)
	_hud.add_theme_font_size_override("font_size", 17)
	_hud.add_theme_color_override("font_color", Color(1.0, 0.96, 0.82))
	layer.add_child(_hud)

func _refresh_hud() -> void:
	if _hud == null:
		return
	if _next_step >= _steps.size():
		_hud.text = "Quest completed: " + _title
	else:
		var entry: Dictionary = _steps[_next_step]
		_hud.text = "Quest %d/%d: %s" % [
			_next_step + 1, _steps.size(),
			str(entry.get("text", "Visit target room")),
		]

func _reward_until(step_count: int) -> Dictionary:
	var totals: Dictionary = {}
	for i in range(step_count):
		var step: Dictionary = _steps[i]
		for reward in step.get("rewards", []):
			var kind: String = str(reward.get("kind", ""))
			var amount: int = int(reward.get("amount", 0))
			totals[kind] = int(totals.get(kind, 0)) + amount
	return totals

func _on_room_entered(room_id: String) -> void:
	if not _loaded or _next_step >= _steps.size():
		return
	var current: Dictionary = _steps[_next_step]
	if str(current.get("location", "")) != room_id:
		return
	_visits.append(room_id)
	_next_step += 1
	_earned = _reward_until(_next_step)
	objective_completed.emit(str(current.get("id", "")), room_id)
	_refresh_hud()
	if _next_step >= _steps.size():
		quest_completed.emit()

func snapshot() -> Dictionary:
	if not _loaded:
		return {}
	return {
		"schema": SAVE_SCHEMA,
		"source_sha256": SOURCE_SHA256,
		"next_step": _next_step,
		"visits": _visits.duplicate(),
		"earned": _earned.duplicate(true),
	}

func restore_snapshot(save: Dictionary) -> bool:
	if not _loaded or save.size() != 5:
		return false
	if save.get("schema") != SAVE_SCHEMA or save.get("source_sha256") != SOURCE_SHA256:
		return false
	var next: Variant = save.get("next_step")
	if typeof(next) != TYPE_INT or next < 0 or next > _steps.size():
		return false
	if typeof(save.get("earned")) != TYPE_DICTIONARY:
		return false
	var visits: Variant = save.get("visits")
	if typeof(visits) != TYPE_ARRAY or visits.size() != next:
		return false
	for i in range(next):
		if typeof(visits[i]) != TYPE_STRING or visits[i] != str(_steps[i].get("location", "")):
			return false
	var expected: Dictionary = _reward_until(next)
	if save.get("earned") != expected:
		return false
	_next_step = next
	_visits.clear()
	for visit in visits:
		_visits.append(visit)
	_earned = expected
	_refresh_hud()
	return true

func quest_status() -> Dictionary:
	return {
		"loaded": _loaded, "title": _title,
		"next_step": _next_step, "total_steps": _steps.size(),
		"visited_rooms": _visits.duplicate(),
		"completed": _loaded and _next_step == _steps.size(),
		"earned": _earned.duplicate(true),
	}
'''


def attach_native_quest(
    files: Mapping[str, str], *, length: int = 3,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Attach a real Godot room-triggered quest; leave caller's files untouched."""
    if type(length) is not int or not 1 <= length <= 8:
        raise NativeQuestError("native quest length must be 1..8")
    if not isinstance(files, Mapping):
        raise NativeQuestError("project files must be a mapping")
    if QUEST_PATH in files or SCRIPT_PATH in files:
        raise NativeQuestError("quest output conflicts with existing source")
    project = files.get("project.godot")
    world_text = files.get(ROOM_PATH)
    if (not isinstance(project, str) or project.count(INPUT_ENTRY) != 1
            or PROFILE_ENTRY in project or "QuestRuntime=" in project):
        raise NativeQuestError("unexpected project Godot autoload contract")
    world = _room_world(world_text)
    event_source = files.get("scripts/autoloads/game_state.gd", "")
    world_source = files.get("scripts/world/world_map.gd", "")
    if ("EventBus.room_entered.emit(rid)" not in event_source
            or "EventBus.room_entered.emit(rooms[0].id)" not in world_source):
        raise NativeQuestError("Godot room-entry event contract is missing")
    # Stable across Python processes, deliberately derived from the exact
    # source room graph rather than from process-randomized hash().
    world_hash = _hash(world_text)
    seed = int(world_hash[:16], 16)
    registry = _registry()
    doc = compose_verified_quest_slice(
        registry, ["native.movement.v1", "native.quest.v1"],
        slice_id="godot.room_quest.v1", world=world, policy=_POLICY,
        seed=seed, quest_length=length, quest_title="Explore the Forge World",
    )
    if not verify_original_slice(doc, registry):
        raise NativeQuestError("failed replay verification of quest source")
    if validate_quest(doc["world_quest"]["quest"], world, _POLICY):
        raise NativeQuestError("quest does not satisfy real emitted world")
    body = {
        "schema": SCHEMA,
        "source_world_sha256": world_hash,
        "slice": doc,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    quest_sha = _hash(raw)
    gdscript = _GDSCRIPT.replace("__SHA256__", quest_sha)
    result = dict(files)
    result["project.godot"] = project.replace(INPUT_ENTRY, INPUT_ENTRY + PROFILE_ENTRY)
    result[QUEST_PATH] = raw
    result[SCRIPT_PATH] = gdscript
    return result, {
        "schema": SCHEMA,
        "source_world_sha256": world_hash,
        "quest_sha256": quest_sha,
        "steps": len(doc["world_quest"]["quest"]["steps"]),
        "quest": QUEST_PATH,
        "runtime": SCRIPT_PATH,
        "autoload": "QuestRuntime",
        "replay_verified": True,
    }


def verify_native_quest(files: Mapping[str, str]) -> bool:
    """Verify exact source/world binding, registry composition and autoload."""
    try:
        raw = files[QUEST_PATH]
        source = json.loads(raw)
        if not isinstance(source, dict) or set(source) != {
            "schema", "source_world_sha256", "slice",
        } or source["schema"] != SCHEMA:
            return False
        if source["source_world_sha256"] != _hash(files[ROOM_PATH]):
            return False
        world = _room_world(files[ROOM_PATH])
        doc = source["slice"]
        if not verify_original_slice(doc, _registry()):
            return False
        if validate_quest(doc["world_quest"]["quest"], world, _POLICY):
            return False
        steps = doc["world_quest"]["quest"]["steps"]
        if type(steps) is not list or not 1 <= len(steps) <= 8:
            return False
        if raw != json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n":
            return False
        # Hashes alone are not authenticity: rebuild the seeded composition
        # from the *actual* emitted graph, then require exact equality.
        expected = compose_verified_quest_slice(
            _registry(), ["native.movement.v1", "native.quest.v1"],
            slice_id="godot.room_quest.v1", world=world, policy=_POLICY,
            seed=int(_hash(files[ROOM_PATH])[:16], 16),
            quest_length=len(steps), quest_title="Explore the Forge World",
        )
        if expected != doc:
            return False
        if files["project.godot"].count(PROFILE_ENTRY) != 1:
            return False
        if ("EventBus.room_entered.emit(rid)" not in files.get("scripts/autoloads/game_state.gd", "")
                or "EventBus.room_entered.emit(rooms[0].id)" not in files.get("scripts/world/world_map.gd", "")):
            return False
        return files[SCRIPT_PATH] == _GDSCRIPT.replace("__SHA256__", _hash(raw))
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, RecursionError):
        return False


__all__ = [
    "SCHEMA", "QUEST_PATH", "SCRIPT_PATH", "NativeQuestError",
    "attach_native_quest", "verify_native_quest",
]
