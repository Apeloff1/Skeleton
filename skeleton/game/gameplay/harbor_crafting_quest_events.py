"""Deterministic source-bound quest/event rewards over a real expedition replay.

Quest awards are computed from canonical movement, crafting, merchant
dialogue, survey visits and weather energy. No claimed score, event or
invented NPC interaction can satisfy a quest.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_expedition import verify_expedition

BOARD_SCHEMA = "skeleton.game.harbor.quest-events.v1"
REPORT_SCHEMA = "skeleton.game.harbor.quest-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_QUESTS = 16
TRIGGERS = {"move", "gather", "craft", "trade", "talk", "deliver", "choose", "wait"}
BOARD_FIELDS = {"schema", "source_id", "quests"}
QUEST_FIELDS = {
    "id", "trigger", "target", "requires_flags", "requires_sites",
    "requires_tokens", "min_energy", "reward", "grant_token", "required",
}
REPORT_FIELDS = {
    "schema", "expedition", "board", "board_digest", "awards",
    "tokens", "reputation", "complete", "report_digest",
}


def validate_quest_board(board: Any, expedition: Any) -> dict[str, Any]:
    verify_expedition(expedition)
    _keys(board, BOARD_FIELDS, "quest board")
    if (board["schema"] != BOARD_SCHEMA
            or board["source_id"] != expedition["source"]["id"]):
        raise HarborError("quest board source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("quest board exceeds byte limit")
    quests = board["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= MAX_QUESTS:
        raise HarborError("invalid quest count")
    sites = {site["id"] for site in expedition["survey_board"]["sites"]}
    flags = {
        choice["grant_flag"]
        for node in expedition["dialogue_board"]["nodes"]
        for choice in node["choices"]
    }
    resources = {r["id"] for r in expedition["source"]["resources"]}
    recipes = {r["id"] for r in expedition["source"]["recipes"]}
    merchant_items = set(expedition["source"]["npc"]["stock"])
    known_tokens: set[str] = set()
    ids: set[str] = set()
    required = 0
    for quest in quests:
        _keys(quest, QUEST_FIELDS, "quest")
        name = _identifier(quest["id"], "quest id")
        if name in ids:
            raise HarborError("duplicate quest id")
        ids.add(name)
        trigger = quest["trigger"]
        target = quest["target"]
        if type(trigger) is not str or trigger not in TRIGGERS:
            raise HarborError("unsupported quest trigger")
        _identifier(target, "quest target")
        if trigger in ("move", "wait", "deliver") and target != "any":
            raise HarborError("quest trigger requires any target")
        if trigger == "gather" and target not in resources:
            raise HarborError("quest resource not authored")
        if trigger == "craft" and target not in recipes:
            raise HarborError("quest recipe not authored")
        if trigger == "trade" and target not in merchant_items:
            raise HarborError("quest trade item not authored")
        if trigger == "choose" and target not in ("signal", "shelter"):
            raise HarborError("quest ending not authored")
        if trigger == "talk" and target not in {
            choice["id"] for node in expedition["dialogue_board"]["nodes"]
            for choice in node["choices"]
        }:
            raise HarborError("quest dialogue choice not authored")
        for field, allowed in (
            ("requires_flags", flags), ("requires_sites", sites),
            ("requires_tokens", known_tokens),
        ):
            values = quest[field]
            if (not isinstance(values, list) or len(values) > 8
                    or any(type(v) is not str for v in values)
                    or len(set(values)) != len(values)):
                raise HarborError("invalid quest prerequisites")
            for value in values:
                _identifier(value, "quest prerequisite")
                if value not in allowed:
                    raise HarborError("quest prerequisite is not source-bound")
        _integer(quest["min_energy"], 0, expedition["weather_board"]["max_energy"],
                 "quest minimum energy")
        _integer(quest["reward"], 0, 100, "quest reputation reward")
        token = _identifier(quest["grant_token"], "quest grant token")
        if token in known_tokens:
            raise HarborError("duplicate quest token")
        known_tokens.add(token)
        if type(quest["required"]) is not bool:
            raise HarborError("invalid quest required flag")
        required += quest["required"]
    if not required:
        raise HarborError("quest board needs a required objective")
    return deepcopy(board)


def _target(expedition: dict[str, Any], index: int) -> str:
    action = expedition["input_actions"][index]
    op = action["op"]
    if op == "gather":
        position = expedition["dialogue"]["events"][index]["position"]
        item = next((r["id"] for r in expedition["source"]["resources"]
                     if r["at"] == position), None)
        if item is None:
            raise HarborError("quest gather source mismatch")
        return item
    if op in ("craft", "trade", "choose", "talk"):
        return action[{"craft": "recipe", "trade": "item",
                       "choose": "choice", "talk": "choice"}[op]]
    return "any"


def build_quest_report(expedition: Any, board: Any, *,
                       require_all: bool = False) -> dict[str, Any]:
    verify_expedition(expedition)
    authored = validate_quest_board(board, expedition)
    awarded: set[str] = set()
    tokens: set[str] = set()
    reputation = 0
    awards: list[dict[str, Any]] = []
    previous = digest({
        "expedition": expedition["expedition_digest"],
        "board": digest(authored), "genesis": True,
    })
    for index, action in enumerate(expedition["input_actions"]):
        tick = index + 1
        target = _target(expedition, index)
        flags = set(expedition["dialogue"]["events"][index]["flags_after"])
        sites = {visit["id"] for visit in expedition["survey"]["visits"]
                 if visit["tick"] <= tick}
        energy = expedition["weather"]["events"][index]["energy_after"]
        for quest in authored["quests"]:
            if quest["id"] in awarded:
                continue
            if action["op"] != quest["trigger"] or target != quest["target"]:
                continue
            if (not set(quest["requires_flags"]).issubset(flags)
                    or not set(quest["requires_sites"]).issubset(sites)
                    or not set(quest["requires_tokens"]).issubset(tokens)
                    or energy < quest["min_energy"]):
                continue
            reputation += quest["reward"]
            awarded.add(quest["id"])
            tokens.add(quest["grant_token"])
            entry = {
                "tick": tick, "id": quest["id"],
                "token": quest["grant_token"], "reward": quest["reward"],
                "reputation": reputation, "action": deepcopy(action),
                "previous": previous,
            }
            entry["digest"] = digest(entry)
            awards.append(entry)
            previous = entry["digest"]
    complete = (
        expedition["complete"]
        and all(q["id"] in awarded for q in authored["quests"] if q["required"])
    )
    if require_all and not complete:
        raise HarborError("quest victory not earned")
    report = {
        "schema": REPORT_SCHEMA, "expedition": deepcopy(expedition),
        "board": authored, "board_digest": digest(authored),
        "awards": awards, "tokens": sorted(tokens),
        "reputation": reputation, "complete": complete,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("quest report exceeds byte limit")
    return report


def verify_quest_report(report: Any, *, require_all: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "quest report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized quest report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("quest report digest mismatch")
    rebuilt = build_quest_report(report["expedition"], report["board"],
                                 require_all=require_all)
    if rebuilt != report:
        raise HarborError("quest event replay mismatch")
    return {
        "complete": rebuilt["complete"], "reputation": rebuilt["reputation"],
        "tokens": deepcopy(rebuilt["tokens"]),
        "awards": len(rebuilt["awards"]),
        "report_digest": rebuilt["report_digest"],
    }


def quest_status(report: Any) -> dict[str, Any]:
    status = verify_quest_report(report)
    awarded = {entry["id"] for entry in report["awards"]}
    return {
        **status,
        "remaining": [q["id"] for q in report["board"]["quests"]
                      if q["required"] and q["id"] not in awarded],
        "next_tick": report["expedition"]["dialogue"]["bundle"]["state"]["tick"] + 1,
    }
