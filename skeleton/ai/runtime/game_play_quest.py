"""Deterministic pickups, crafting and quest claims over real original-game replay.

The canonical platformer remains authoritative for movement and victory. This
source-bound overlay adds authored item placement and explicit per-frame craft
and quest decisions without altering or inventing the underlying game save.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .game_play_session import verify_play_session
from .gameplay_capabilities import compile_level, platformer_step

MANIFEST_SCHEMA = "skeleton.game.play_quest_manifest.v1"
OVERLAY_SCHEMA = "skeleton.game.play_quest_overlay.v1"
MAX_COLLECTIBLES = 64
MAX_RECIPES = 32
MAX_QUESTS = 32
MAX_ITEM_KINDS = 128
MAX_QUANTITY = 999
MAX_OVERLAY_BYTES = 160 * 1024
_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z", re.ASCII)
_MANIFEST_KEYS = frozenset((
    "schema_version", "capsule_sha256", "collectibles", "recipes", "quests",
))
_OVERLAY_KEYS = frozenset((
    "schema_version", "manifest", "session", "actions", "result", "body_sha256",
))
_COST_KEYS = frozenset(("item_id", "amount"))


class GameQuestError(ValueError):
    """A quest, craft, pickup or saved overlay violates source-bound rules."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameQuestError("quest overlay cannot be canonicalized") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _name(value: Any, label: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise GameQuestError("invalid " + label)
    return value


def _number(value: Any, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise GameQuestError("invalid " + label)
    return value


def _cost(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _COST_KEYS:
        raise GameQuestError("item cost must contain item_id and amount")
    return {
        "item_id": _name(value["item_id"], "item_id"),
        "amount": _number(value["amount"], 1, MAX_QUANTITY, "amount"),
    }


def _costs(values: Any, *, allow_empty: bool) -> list[dict[str, Any]]:
    if type(values) is not list or len(values) > MAX_ITEM_KINDS:
        raise GameQuestError("item costs exceed budget")
    if not allow_empty and not values:
        raise GameQuestError("item costs cannot be empty")
    admitted = [_cost(value) for value in values]
    names = [item["item_id"] for item in admitted]
    if len(set(names)) != len(names):
        raise GameQuestError("duplicate item cost")
    return sorted(admitted, key=lambda item: item["item_id"])


def validate_quest_manifest(capsule: Mapping[str, Any], manifest: Any) -> dict[str, Any]:
    """Validate original authored content against the actual capsule tilemap."""
    from .game_project_capsule import verify_game_capsule
    source = verify_game_capsule(capsule)
    if type(manifest) is not dict or set(manifest) != _MANIFEST_KEYS:
        raise GameQuestError("quest manifest schema mismatch")
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise GameQuestError("unsupported quest manifest version")
    digest = manifest["capsule_sha256"]
    if type(digest) is not str or digest != source["capsule_sha256"]:
        raise GameQuestError("quest manifest belongs to a different capsule")
    tiles = capsule["tilemap"]
    if (
        type(manifest["collectibles"]) is not list
        or len(manifest["collectibles"]) > MAX_COLLECTIBLES
        or type(manifest["recipes"]) is not list
        or len(manifest["recipes"]) > MAX_RECIPES
        or type(manifest["quests"]) is not list
        or len(manifest["quests"]) > MAX_QUESTS
    ):
        raise GameQuestError("quest content count exceeds budget")
    collectibles = []
    for item in manifest["collectibles"]:
        if type(item) is not dict or set(item) != {"id", "item_id", "x", "y", "amount"}:
            raise GameQuestError("collectible fields mismatch")
        x = _number(item["x"], 0, len(tiles[0]) - 1, "collectible x")
        y = _number(item["y"], 0, len(tiles) - 1, "collectible y")
        if tiles[y][x] == "#":
            raise GameQuestError("collectible cannot be placed in a wall")
        collectibles.append({
            "id": _name(item["id"], "collectible id"),
            "item_id": _name(item["item_id"], "item id"),
            "x": x, "y": y,
            "amount": _number(item["amount"], 1, MAX_QUANTITY, "collectible amount"),
        })
    if len({item["id"] for item in collectibles}) != len(collectibles):
        raise GameQuestError("duplicate collectible id")
    recipes = []
    for recipe in manifest["recipes"]:
        if type(recipe) is not dict or set(recipe) != {"id", "costs", "output"}:
            raise GameQuestError("recipe fields mismatch")
        recipes.append({
            "id": _name(recipe["id"], "recipe id"),
            "costs": _costs(recipe["costs"], allow_empty=False),
            "output": _cost(recipe["output"]),
        })
    if len({recipe["id"] for recipe in recipes}) != len(recipes):
        raise GameQuestError("duplicate recipe id")
    quests = []
    for quest in manifest["quests"]:
        if type(quest) is not dict or set(quest) != {"id", "requires", "costs", "reward"}:
            raise GameQuestError("quest fields mismatch")
        requires = quest["requires"]
        if type(requires) is not list or len(requires) > MAX_QUESTS:
            raise GameQuestError("quest prerequisite count exceeds budget")
        dependencies = [_name(item, "quest prerequisite") for item in requires]
        if len(set(dependencies)) != len(dependencies):
            raise GameQuestError("duplicate quest prerequisite")
        quests.append({
            "id": _name(quest["id"], "quest id"),
            "requires": sorted(dependencies),
            "costs": _costs(quest["costs"], allow_empty=False),
            "reward": _cost(quest["reward"]),
        })
    quest_ids = {quest["id"] for quest in quests}
    if len(quest_ids) != len(quests):
        raise GameQuestError("duplicate quest id")
    for quest in quests:
        if quest["id"] in quest["requires"] or not set(quest["requires"]) <= quest_ids:
            raise GameQuestError("unknown or self-dependent quest")
    by_id = {quest["id"]: quest for quest in quests}
    visited: set[str] = set()
    active: set[str] = set()
    def visit(quest_id: str) -> None:
        if quest_id in active:
            raise GameQuestError("quest prerequisite cycle")
        if quest_id in visited:
            return
        active.add(quest_id)
        for parent in by_id[quest_id]["requires"]:
            visit(parent)
        active.remove(quest_id)
        visited.add(quest_id)
    for quest_id in sorted(by_id):
        visit(quest_id)
    kinds = {
        item["item_id"] for item in collectibles
    } | {
        item["item_id"] for recipe in recipes
        for item in [*recipe["costs"], recipe["output"]]
    } | {
        item["item_id"] for quest in quests
        for item in [*quest["costs"], quest["reward"]]
    }
    if len(kinds) > MAX_ITEM_KINDS:
        raise GameQuestError("quest item-kind budget exceeded")
    return {
        "schema_version": MANIFEST_SCHEMA,
        "capsule_sha256": digest,
        "collectibles": sorted(collectibles, key=lambda item: item["id"]),
        "recipes": sorted(recipes, key=lambda item: item["id"]),
        "quests": sorted(quests, key=lambda item: item["id"]),
    }


def _admit_actions(actions: Any, frames: int) -> list[dict[str, str | None]]:
    if type(actions) is not list or len(actions) != frames:
        raise GameQuestError("quest action count must match verified gameplay frames")
    result = []
    for action in actions:
        if type(action) is not dict or set(action) != {"craft", "claim"}:
            raise GameQuestError("quest action requires craft and claim")
        for key in ("craft", "claim"):
            if action[key] is not None:
                _name(action[key], key)
        result.append({"craft": action["craft"], "claim": action["claim"]})
    return result


def _run(
    capsule: Mapping[str, Any], session: Any,
    manifest: dict[str, Any], actions: list[dict[str, str | None]],
) -> dict[str, Any]:
    verified = verify_play_session(capsule, session)
    if manifest["capsule_sha256"] != verified["capsule_sha256"]:
        raise GameQuestError("quest overlay source digest mismatch")
    compiled = compile_level({"tiles": capsule["tilemap"]})
    avatar = {**compiled["spawn"], "vx": 0, "vy": 0}
    inventory: dict[str, int] = {}
    picked: set[str] = set()
    claimed: set[str] = set()
    events: list[dict[str, Any]] = []
    recipes = {item["id"]: item for item in manifest["recipes"]}
    quests = {item["id"]: item for item in manifest["quests"]}

    def add(item: dict[str, Any]) -> None:
        key, amount = item["item_id"], item["amount"]
        value = inventory.get(key, 0) + amount
        if value > MAX_QUANTITY:
            raise GameQuestError("inventory quantity budget exceeded")
        inventory[key] = value

    def spend(costs: list[dict[str, Any]]) -> None:
        if any(inventory.get(item["item_id"], 0) < item["amount"] for item in costs):
            raise GameQuestError("craft or quest lacks required inventory")
        for item in costs:
            key = item["item_id"]
            inventory[key] -= item["amount"]
            if inventory[key] == 0:
                del inventory[key]

    for index, (control, action) in enumerate(zip(session["controls"], actions), 1):
        outcome = platformer_step({
            "tiles": capsule["tilemap"], "avatar": avatar, "control": control,
        })
        avatar = outcome["avatar"]
        for collectible in manifest["collectibles"]:
            if (
                collectible["id"] not in picked
                and avatar["x"] == collectible["x"]
                and avatar["y"] == collectible["y"]
            ):
                picked.add(collectible["id"])
                add({"item_id": collectible["item_id"], "amount": collectible["amount"]})
                events.append({
                    "frame": index, "type": "pickup", "id": collectible["id"],
                })
        if action["craft"] is not None:
            recipe = recipes.get(action["craft"])
            if recipe is None:
                raise GameQuestError("unknown craft recipe")
            spend(recipe["costs"])
            add(recipe["output"])
            events.append({"frame": index, "type": "craft", "id": recipe["id"]})
        if action["claim"] is not None:
            quest = quests.get(action["claim"])
            if quest is None or quest["id"] in claimed:
                raise GameQuestError("unknown or already claimed quest")
            if not set(quest["requires"]) <= claimed:
                raise GameQuestError("quest prerequisites are incomplete")
            spend(quest["costs"])
            add(quest["reward"])
            claimed.add(quest["id"])
            events.append({"frame": index, "type": "quest", "id": quest["id"]})
    return {
        "schema_version": "skeleton.game.play_quest_result.v1",
        "capsule_sha256": verified["capsule_sha256"],
        "session_sha256": verified["session_sha256"],
        "manifest_sha256": _hash(manifest),
        "frame_count": verified["frame_count"],
        "victory_frame": verified["victory_frame"],
        "inventory": dict(sorted(inventory.items())),
        "picked_collectibles": sorted(picked),
        "claimed_quests": sorted(claimed),
        "events": events,
        "events_sha256": _hash(events),
        "source_bound_replay_verified": True,
        "native_export_created": False,
    }


def pack_quest_overlay(
    capsule: Mapping[str, Any], session: Any, manifest: Any, actions: Any,
) -> dict[str, Any]:
    """Replay movement, pickups, crafting and quest claims; seal an offline save."""
    admitted = validate_quest_manifest(capsule, manifest)
    verified = verify_play_session(capsule, session)
    accepted_actions = _admit_actions(actions, verified["frame_count"])
    body = {
        "schema_version": OVERLAY_SCHEMA,
        "manifest": admitted,
        "session": session,
        "actions": accepted_actions,
        "result": _run(capsule, session, admitted, accepted_actions),
    }
    raw = _canonical(body)
    if len(raw) > MAX_OVERLAY_BYTES:
        raise GameQuestError("quest overlay exceeds portable byte budget")
    return {**body, "body_sha256": hashlib.sha256(raw).hexdigest()}


def verify_quest_overlay(capsule: Mapping[str, Any], overlay: Any) -> dict[str, Any]:
    """Rebuild a portable quest save from source, rejecting forged inventory."""
    if type(overlay) is not dict or set(overlay) != _OVERLAY_KEYS:
        raise GameQuestError("quest overlay schema mismatch")
    if overlay["schema_version"] != OVERLAY_SCHEMA:
        raise GameQuestError("unsupported quest overlay version")
    expected = pack_quest_overlay(
        capsule, overlay["session"], overlay["manifest"], overlay["actions"],
    )
    if _canonical(expected) != _canonical(overlay):
        raise GameQuestError("quest overlay differs from canonical gameplay replay")
    return {
        **expected["result"],
        "overlay_sha256": expected["body_sha256"],
        "overlay_replay_verified": True,
        "independent_rights_review_completed": False,
    }


__all__ = [
    "MANIFEST_SCHEMA", "OVERLAY_SCHEMA", "GameQuestError",
    "validate_quest_manifest", "pack_quest_overlay", "verify_quest_overlay",
]
