"""Replay-derived original beacon rescue quest progression and earned rewards."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_beacons import (
    MAX_REPORT_BYTES as MAX_BEACON_REPORT_BYTES, verify_beacon_rescue,
)

BOARD_SCHEMA = "skeleton.game.harbor.beacon-quests.v1"
REPORT_SCHEMA = "skeleton.game.harbor.beacon-quest-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_BEACON_REPORT_BYTES + 131072
MAX_QUESTS = 24
BOARD_FIELDS = {"schema", "source_id", "beacon_board_digest", "quests"}
QUEST_FIELDS = {"id", "trigger", "target", "requires", "reward"}
REPORT_FIELDS = {
    "schema", "source_report", "board", "events", "state",
    "board_digest", "quest_digest",
}
TRIGGERS = {"repair", "signal", "deliver", "rescue"}


def validate_beacon_quests(board: Any, rescue_report: Any) -> dict[str, Any]:
    verify_beacon_rescue(rescue_report)
    _keys(board, BOARD_FIELDS, "beacon quest board")
    if (board["schema"] != BOARD_SCHEMA
            or board["source_id"] != rescue_report["source"]["id"]
            or board["beacon_board_digest"] != rescue_report["board_digest"]):
        raise HarborError("beacon quest source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("beacon quest board exceeds byte budget")
    quests = board["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= MAX_QUESTS:
        raise HarborError("invalid beacon quest count")
    beacon_ids = {item["id"] for item in rescue_report["board"]["beacons"]}
    seen: set[str] = set()
    for quest in quests:
        _keys(quest, QUEST_FIELDS, "beacon quest")
        name = _identifier(quest["id"], "beacon quest id")
        if name in seen:
            raise HarborError("duplicate beacon quest")
        if type(quest["trigger"]) is not str or quest["trigger"] not in TRIGGERS:
            raise HarborError("invalid beacon quest trigger")
        target = quest["target"]
        if quest["trigger"] in {"repair", "signal"}:
            if type(target) is not str or target not in beacon_ids:
                raise HarborError("unknown beacon quest target")
        elif target != "-":
            raise HarborError("delivery and rescue quest target must be '-'")
        requires = quest["requires"]
        if (not isinstance(requires, list) or len(requires) > MAX_QUESTS
                or any(type(item) is not str or item not in seen for item in requires)
                or len(set(requires)) != len(requires)):
            raise HarborError("beacon quest prerequisites must reference earlier quests")
        _integer(quest["reward"], 1, 100, "beacon quest reward")
        seen.add(name)
    return deepcopy(board)


def _matches(quest: dict[str, Any], action: dict[str, str]) -> bool:
    return (
        quest["trigger"] == action["op"]
        and (
            quest["trigger"] in {"deliver", "rescue"}
            or quest["target"] == action.get("beacon")
        )
    )


def build_beacon_quest_report(rescue_report: Any, board: Any, *,
                              require_complete: bool = False) -> dict[str, Any]:
    verify_beacon_rescue(rescue_report)
    authored = validate_beacon_quests(board, rescue_report)
    events: list[dict[str, Any]] = []
    completed: list[str] = []
    score = 0
    previous = digest({
        "rescue": rescue_report["report_digest"],
        "board": digest(authored), "genesis": True,
    })
    for index, action in enumerate(rescue_report["actions"]):
        for quest in authored["quests"]:
            name = quest["id"]
            if name in completed or not _matches(quest, action):
                continue
            if not set(quest["requires"]).issubset(completed):
                continue
            score += quest["reward"]
            completed.append(name)
            entry = {
                "sequence": len(events), "source_sequence": index,
                "quest": name, "reward": quest["reward"],
                "source_event_digest": rescue_report["events"][index]["digest"],
                "previous": previous,
            }
            entry["digest"] = digest(entry)
            events.append(entry)
            previous = entry["digest"]
    state = {
        "completed": completed, "score": score,
        "complete": (
            len(completed) == len(authored["quests"])
            and rescue_report["state"]["rescued"]
        ),
    }
    if require_complete and not state["complete"]:
        raise HarborError("beacon quest victory not earned")
    report = {
        "schema": REPORT_SCHEMA, "source_report": deepcopy(rescue_report),
        "board": authored, "events": events, "state": state,
        "board_digest": digest(authored),
    }
    report["quest_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("beacon quest report exceeds byte budget")
    return report


def verify_beacon_quest_report(report: Any, *,
                               require_complete: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "beacon quest report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized beacon quest report")
    if report["quest_digest"] != digest({
        key: value for key, value in report.items() if key != "quest_digest"
    }):
        raise HarborError("beacon quest report digest mismatch")
    rebuilt = build_beacon_quest_report(
        report["source_report"], report["board"], require_complete=require_complete,
    )
    if rebuilt != report:
        raise HarborError("beacon quest replay mismatch")
    return {
        "verified": True, "complete": rebuilt["state"]["complete"],
        "completed": list(rebuilt["state"]["completed"]),
        "score": rebuilt["state"]["score"],
        "quest_digest": rebuilt["quest_digest"],
    }
