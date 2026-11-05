"""Authored patrol mission quests derived only from replayed player transitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_patrol import MAX_REPORT_BYTES, verify_patrol

BOARD_SCHEMA = "skeleton.game.harbor.patrol-quest-board.v1"
LEDGER_SCHEMA = "skeleton.game.harbor.patrol-quest-ledger.v1"
MAX_BOARD_BYTES = 32768
MAX_LEDGER_BYTES = MAX_REPORT_BYTES * 2
MAX_QUESTS = 16
TRIGGERS = {"collect", "craft", "deliver", "extract", "hide", "smoke"}
BOARD_KEYS = {"schema", "source_id", "patrol_board_digest", "quests"}
QUEST_KEYS = {"id", "requires", "trigger", "target", "reward"}
LEDGER_KEYS = {"schema", "patrol", "board", "events", "completed",
               "reward", "patrol_digest", "board_digest", "ledger_digest"}


def validate_patrol_quest_board(board: Any, patrol: Any) -> dict[str, Any]:
    verify_patrol(patrol)
    _keys(board, BOARD_KEYS, "patrol quest board")
    if (board["schema"] != BOARD_SCHEMA
            or board["source_id"] != patrol["source"]["id"]
            or board["patrol_board_digest"] != patrol["board_digest"]):
        raise HarborError("patrol quest source or board mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("patrol quest board exceeds byte budget")
    quests = board["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= MAX_QUESTS:
        raise HarborError("invalid patrol quest count")
    earlier: set[str] = set()
    objectives = {obj["id"] for obj in patrol["board"]["objectives"]}
    recipes = {recipe["id"] for recipe in patrol["source"]["recipes"]}
    for quest in quests:
        _keys(quest, QUEST_KEYS, "patrol quest")
        name = _identifier(quest["id"], "patrol quest id")
        if name in earlier:
            raise HarborError("duplicate patrol quest")
        prerequisites = quest["requires"]
        if not isinstance(prerequisites, list) or len(prerequisites) > MAX_QUESTS:
            raise HarborError("invalid patrol quest prerequisites")
        if len(set(map(str, prerequisites))) != len(prerequisites):
            raise HarborError("duplicate patrol quest prerequisite")
        if any(type(p) is not str or p not in earlier for p in prerequisites):
            raise HarborError("patrol quest prerequisite must precede quest")
        trigger = quest["trigger"]
        if type(trigger) is not str or trigger not in TRIGGERS:
            raise HarborError("unsupported patrol quest trigger")
        target = quest["target"]
        if trigger in {"collect", "craft"}:
            _identifier(target, "patrol quest target")
            if target not in (objectives if trigger == "collect" else recipes):
                raise HarborError("patrol quest target not authored")
        elif target != "":
            raise HarborError("untargeted patrol quest has unexpected target")
        _integer(quest["reward"], 1, 100, "patrol quest reward")
        earlier.add(name)
    return deepcopy(board)


def _matches(quest: dict[str, Any], action: dict[str, str]) -> bool:
    if action["op"] != quest["trigger"]:
        return False
    if action["op"] == "collect":
        return action["objective"] == quest["target"]
    if action["op"] == "craft":
        return action["recipe"] == quest["target"]
    return True


def build_patrol_quests(patrol: Any, board: Any, *,
                        require_all: bool = False) -> dict[str, Any]:
    verify_patrol(patrol)
    authored = validate_patrol_quest_board(board, patrol)
    completed: list[str] = []
    events: list[dict[str, Any]] = []
    previous = digest({"patrol": patrol["report_digest"],
                       "board": digest(authored), "genesis": True})
    total = 0
    for tick, action in enumerate(patrol["actions"], 1):
        for quest in authored["quests"]:
            if quest["id"] in completed:
                continue
            if not all(prerequisite in completed for prerequisite in quest["requires"]):
                continue
            if not _matches(quest, action):
                continue
            event = {"sequence": len(events), "tick": tick, "quest": quest["id"],
                     "trigger": quest["trigger"], "reward": quest["reward"],
                     "previous": previous}
            event["digest"] = digest(event)
            events.append(event)
            previous = event["digest"]
            completed.append(quest["id"])
            total += quest["reward"]
    if require_all and len(completed) != len(authored["quests"]):
        raise HarborError("patrol authored quest chain not earned")
    ledger = {"schema": LEDGER_SCHEMA, "patrol": deepcopy(patrol),
              "board": authored, "events": events, "completed": completed,
              "reward": total, "patrol_digest": patrol["report_digest"],
              "board_digest": digest(authored)}
    ledger["ledger_digest"] = digest(ledger)
    if len(canonical(ledger)) > MAX_LEDGER_BYTES:
        raise HarborError("patrol quest ledger exceeds byte budget")
    return ledger


def verify_patrol_quests(ledger: Any, *,
                         require_all: bool = False) -> dict[str, Any]:
    _keys(ledger, LEDGER_KEYS, "patrol quest ledger")
    if ledger["schema"] != LEDGER_SCHEMA or len(canonical(ledger)) > MAX_LEDGER_BYTES:
        raise HarborError("unsupported or oversized patrol quest ledger")
    if ledger["ledger_digest"] != digest({k: v for k, v in ledger.items()
                                           if k != "ledger_digest"}):
        raise HarborError("patrol quest ledger digest mismatch")
    rebuilt = build_patrol_quests(ledger["patrol"], ledger["board"],
                                  require_all=require_all)
    if rebuilt != ledger:
        raise HarborError("patrol quest event chain replay mismatch")
    return {"completed": list(rebuilt["completed"]), "reward": rebuilt["reward"],
            "patrol_digest": rebuilt["patrol_digest"],
            "ledger_digest": rebuilt["ledger_digest"]}
