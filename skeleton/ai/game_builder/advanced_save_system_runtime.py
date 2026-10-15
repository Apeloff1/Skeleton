"""Finite in-memory versioned game save slots with integrity-checked replay.

Simulates atomic revision commits, source-version upgrades, autosave intervals
and rollback-safe load. Storage *durability on disk* is owned by the existing
game save authority; no file I/O or symlink assumptions are made here.
"""
from __future__ import annotations

from hashlib import sha256
import json

_PRIMARY_ACTIONS = ("inspect", "advance", "advance:10", "damage", "heal",
                    "save:0", "save:1", "save:2", "load:0", "load:1", "load:2",
                    "delete:0", "delete:1", "delete:2", "autosave",
                    "migrate", "verify", "retire")
# The source-bound actions cover all 1000 finite editor slots.
ACTIONS = _PRIMARY_ACTIONS + tuple(
    operation + ":" + str(slot)
    for slot in range(3, 1000)
    for operation in ("save", "load", "delete")
)


class SaveSystemActionError(ValueError):
    """Uncommitted save, invalid revision, impossible migration or corruption."""


def _int(x, low, high, name):
    if type(x) is not int or not low <= x <= high:
        raise SaveSystemActionError("invalid save system " + name)
    return x


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    return {
        "title": "Original Checkpoint Realm " + str(seed % 10000),
        "starting_health": 30 + seed % 71,
        "starting_resource": 2 + seed % 7,
        "starting_position": seed % 100,
        "source_schema": 1,
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "starting_health", "starting_resource",
        "starting_position", "source_schema",
    }:
        raise SaveSystemActionError("exact save-world initial source required")
    name = layout["title"]
    if type(name) is not str or not 1 <= len(name) <= 100 or any(ord(c) < 32 for c in name):
        raise SaveSystemActionError("invalid save world title")
    return {
        "title": name,
        "starting_health": _int(layout["starting_health"], 1, 100, "health"),
        "starting_resource": _int(layout["starting_resource"], 0, 1000, "resources"),
        "starting_position": _int(layout["starting_position"], 0, 999, "position"),
        "source_schema": _int(layout["source_schema"], 1, 5, "schema"),
    }


def _payload(state):
    return {
        "schema": state["schema"], "hp": state["health"],
        "resources": state["resources"], "position": state["position"],
        "world_clock": state["clock"],
    }


def start(config, seed):
    layout = normalize_layout(config, default_layout(config, seed))
    return {
        "title": layout["title"], "schema": layout["source_schema"],
        "health": layout["starting_health"],
        "resources": layout["starting_resource"],
        "position": layout["starting_position"], "clock": 0,
        "last_autosave": 0, "slots": {}, "revision": 0,
        "saved": 0, "loaded": 0, "migrations": 0,
        "latest_recovered_digest": None, "score": 0,
        "turn": 0, "finished": False, "failed": False, "events": [],
        "simulated_disk_durability": False,
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise SaveSystemActionError("cannot rewrite original save source after play")
    source = normalize_layout(config, layout)
    state["title"], state["schema"] = source["title"], source["source_schema"]
    state["health"] = source["starting_health"]
    state["resources"] = source["starting_resource"]
    state["position"] = source["starting_position"]


def _write(state, config, slot, events):
    if slot < 0 or slot >= config["save_slots"]:
        raise SaveSystemActionError("slot outside player-created save capacity")
    payload = _payload(state)
    digest = _digest(payload)
    entry = {"revision": state["revision"]+1, "payload": payload, "digest": digest}
    # Newest whole validated record replaces the head; bounded earlier
    # revisions remain available as local history, not partial writes.
    history = state["slots"].setdefault(str(slot), [])
    history.append(entry)
    del history[:-config["history_depth"]]
    state["revision"] += 1
    state["saved"] += 1
    events.append("new_whole_checksum_bound_save_revision_committed")


def _load(state, config, slot, events):
    if slot >= config["save_slots"]:
        raise SaveSystemActionError("unavailable save slot")
    history = state["slots"].get(str(slot))
    if not history:
        raise SaveSystemActionError("load requires an actual previously saved revision")
    record = history[-1]
    if config["checksum_verify"] and _digest(record["payload"]) != record["digest"]:
        raise SaveSystemActionError("saved payload checksum mismatch")
    if record["payload"]["schema"] > state["schema"]:
        raise SaveSystemActionError("unknown future schema cannot be downgraded")
    payload = record["payload"]
    if payload["schema"] < state["schema"]:
        payload = dict(payload)
        payload["schema"] = state["schema"]
        state["migrations"] += 1
        events.append("source_version_upgraded_after_checksum_verification")
    state["health"] = payload["hp"]
    state["resources"] = payload["resources"]
    state["position"] = payload["position"]
    state["clock"] = payload["world_clock"]
    state["loaded"] += 1
    state["latest_recovered_digest"] = record["digest"]
    state["score"] += 2
    events.append("actual_in_memory_world_restored_from_verified_revision")


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise SaveSystemActionError("undeclared or postterminal save operation")
    events = []
    if action == "advance" or action == "advance:10":
        amount = 10 if action == "advance:10" else 1
        state["clock"] += amount
        state["position"] = (state["position"] + amount) % 1000
        state["resources"] += amount
        events.append("source_world_advanced_and_changed")
    elif action == "damage":
        state["health"] = max(1, state["health"] - 7)
        events.append("original_world_health_changed")
    elif action == "heal":
        if not state["resources"]:
            raise SaveSystemActionError("healing requires actual stored resource")
        state["resources"] -= 1
        state["health"] = min(100, state["health"] + 12)
        events.append("resource_conserved_healing")
    elif action.startswith("save:"):
        _write(state, config, int(action.partition(":")[2]), events)
    elif action.startswith("load:"):
        _load(state, config, int(action.partition(":")[2]), events)
    elif action.startswith("delete:"):
        slot = str(int(action.partition(":")[2]))
        if slot not in state["slots"]:
            raise SaveSystemActionError("cannot delete a nonexistent save")
        del state["slots"][slot]
        events.append("source_slot_deleted_without_forged_undo")
    elif action == "autosave":
        if (config["autosave_minutes"] == 0 or
                state["clock"] - state["last_autosave"] < config["autosave_minutes"]):
            raise SaveSystemActionError("autosave is not due under authored schedule")
        _write(state, config, 0, events)
        state["last_autosave"] = state["clock"]
        events.append("time_based_autosave_scheduled_and_committed")
    elif action == "migrate":
        if state["schema"] >= 5:
            raise SaveSystemActionError("maximum declared source schema reached")
        state["schema"] += 1
        state["migrations"] += 1
        events.append("bounded_forward_schema_migration_applied")
    elif action == "verify":
        for history in state["slots"].values():
            for entry in history:
                if _digest(entry["payload"]) != entry["digest"]:
                    raise SaveSystemActionError("whole save revision failed independent checksum")
        state["score"] += len(state["slots"])
        events.append("in_memory_slot_revisions_independently_validated")
    elif action == "retire":
        if state["saved"] == 0 or state["loaded"] == 0:
            raise SaveSystemActionError("verification exercise requires actual save and restore")
        state["finished"] = True
        events.append("earned_persistence_protocol_trial_complete")
    else:
        events.append("saved_game_inventory_inspected")
    state["turn"] += 1
    state["events"] = events
    return events


__all__ = ["ACTIONS", "SaveSystemActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
