"""Original ordered salvage story quests: earned transitions and deterministic events.

Story beats observe the actual canonical game and salvage overlay. Prerequisites
are authored as an acyclic forward chain; no mission or ending is fabricated.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _integer, _keys, canonical, digest, initial_state, step,
)
from .harbor_crafting_salvage import (
    MAX_REPORT_BYTES, SPECIAL, _transition, initial_salvage_state,
    normalize_salvage_action, resume_salvage, verify_salvage,
)

BOARD_SCHEMA = "skeleton.game.harbor.salvage-story-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.salvage-story-report.v1"
MAX_BOARD_BYTES = 32768
MAX_STORY_REPORT_BYTES = MAX_REPORT_BYTES * 2
MAX_QUESTS = 16
BOARD_KEYS = {"schema", "source_id", "quests"}
QUEST_KEYS = {"id", "kind", "target", "requires", "reward", "story"}
REPORT_KEYS = {"schema", "report", "board", "events", "state",
               "board_digest", "story_digest"}
KINDS = {"recover", "secure", "deliver", "rescue", "reward"}


def validate_story_board(board: Any, report: Any) -> dict[str, Any]:
    verify_salvage(report)
    _keys(board, BOARD_KEYS, "salvage story board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != report["source"]["id"]:
        raise HarborError("salvage story source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("salvage story board oversized")
    quests = board["quests"]
    if not isinstance(quests, list) or not 1 <= len(quests) <= MAX_QUESTS:
        raise HarborError("invalid salvage story quest count")
    seen: set[str] = set()
    stories: set[str] = set()
    sites = {s["id"] for s in report["board"]["sites"]}
    for quest in quests:
        _keys(quest, QUEST_KEYS, "salvage story quest")
        name = _identifier(quest["id"], "salvage quest id")
        story = _identifier(quest["story"], "salvage story beat")
        kind = quest["kind"]
        if name in seen or story in stories:
            raise HarborError("duplicate salvage quest or story beat")
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("invalid salvage quest trigger")
        target = quest["target"]
        if kind in {"recover", "secure"}:
            if type(target) is not str or target not in sites:
                raise HarborError("salvage story references unknown site")
        elif kind == "reward":
            _integer(target, 1, 1600, "salvage story reward threshold")
        elif target is not None:
            raise HarborError("salvage story trigger target must be null")
        requires = quest["requires"]
        if (not isinstance(requires, list) or len(requires) > MAX_QUESTS
                or any(type(r) is not str or r not in seen for r in requires)
                or len(set(requires)) != len(requires)):
            raise HarborError("salvage story prerequisites must be earlier unique quests")
        _integer(quest["reward"], 0, 100, "salvage story reputation reward")
        seen.add(name)
        stories.add(story)
    return deepcopy(board)


def _trigger(quest: dict[str, Any], overlay: dict[str, Any], world: dict[str, Any]) -> bool:
    kind, target = quest["kind"], quest["target"]
    if kind == "recover":
        return target in overlay["cargo"] or target in overlay["secured"]
    if kind == "secure":
        return target in overlay["secured"]
    if kind == "deliver":
        return world["delivered"]
    if kind == "rescue":
        return overlay["complete"]
    return overlay["reward"] >= target


def build_salvage_story(report: Any, board: Any, *,
                        require_all: bool = False,
                        _legacy_report_anchor: bool = False) -> dict[str, Any]:
    verify_salvage(report)
    authored = validate_story_board(board, report)
    source = report["source"]
    salvage_board = report["board"]
    world = initial_state(source)
    overlay = initial_salvage_state(salvage_board)
    completed: list[str] = []
    events: list[dict[str, Any]] = []
    reputation = 0
    # Keep immutable source+board ownership stable across report extensions.
    # Historical v1 reports remain independently reverified below.
    seed = {"source": report["source_digest"],
            "board": digest(authored), "genesis": True}
    if _legacy_report_anchor:
        seed["report"] = report["report_digest"]
    previous = digest(seed)
    for index, raw in enumerate(report["actions"]):
        action = normalize_salvage_action(raw)
        core = ({"op": "choose", "choice": "signal"} if action["op"] == "rescue"
                else {"op": "wait"} if action["op"] in SPECIAL else action)
        next_world = step(source, world, core)
        next_overlay = _transition(source, salvage_board, overlay, world, next_world, action)
        for quest in authored["quests"]:
            if (quest["id"] in completed
                    or not set(quest["requires"]).issubset(completed)
                    or not _trigger(quest, next_overlay, next_world)):
                continue
            event = {"sequence": len(events), "tick": index + 1,
                     "quest_id": quest["id"], "story": quest["story"],
                     "previous": previous}
            event["digest"] = digest(event)
            events.append(event)
            previous = event["digest"]
            completed.append(quest["id"])
            reputation += quest["reward"]
        world, overlay = next_world, next_overlay
    if world != report["bundle"]["state"] or overlay != report["state"]:
        raise HarborError("salvage story replay state divergence")
    if require_all and len(completed) != len(authored["quests"]):
        raise HarborError("salvage story quests not all earned")
    earned_rescue = next(
        (quest["story"] for quest in authored["quests"]
         if quest["kind"] == "rescue" and quest["id"] in completed), None
    )
    state = {"completed": completed, "reputation": reputation,
             "ending": earned_rescue if overlay["complete"] else None,
             "tick": overlay["tick"]}
    result = {"schema": REPORT_SCHEMA, "report": deepcopy(report),
              "board": authored, "events": events, "state": state,
              "board_digest": digest(authored)}
    result["story_digest"] = digest(result)
    if len(canonical(result)) > MAX_STORY_REPORT_BYTES:
        raise HarborError("salvage story report exceeds byte budget")
    return result


def verify_salvage_story(story: Any, *, require_all: bool = False) -> dict[str, Any]:
    _keys(story, REPORT_KEYS, "salvage story report")
    if story["schema"] != REPORT_SCHEMA or len(canonical(story)) > MAX_STORY_REPORT_BYTES:
        raise HarborError("unsupported or oversized salvage story report")
    if story["story_digest"] != digest({k: v for k, v in story.items()
                                         if k != "story_digest"}):
        raise HarborError("salvage story report digest mismatch")
    rebuilt = build_salvage_story(story["report"], story["board"], require_all=require_all)
    if rebuilt != story:
        # Permit legacy v1 custody only after complete independent replay;
        # no hash repair, implicit approval or borrowed event identity.
        legacy = build_salvage_story(
            story["report"], story["board"], require_all=require_all,
            _legacy_report_anchor=True,
        )
        if legacy != story:
            raise HarborError("salvage story event chain mismatch")
    return deepcopy(story["state"])


def resume_salvage_story(story: Any, actions: Any, *, expected_digest: str,
                         require_all: bool = False) -> dict[str, Any]:
    verify_salvage_story(story)
    if type(expected_digest) is not str or expected_digest != story["story_digest"]:
        raise HarborError("stale salvage story CAS lease")
    resumed = resume_salvage(story["report"], actions,
                             expected_digest=story["report"]["report_digest"])
    return build_salvage_story(resumed, story["board"], require_all=require_all)
