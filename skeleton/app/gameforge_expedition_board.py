"""Player-facing expedition board and portable, independently verified episode evidence."""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_campaign_board import board as campaign_board
from skeleton.app.gameforge_expedition import (
    _admit, resume_expedition, verify_expedition,
)
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_missions import mission_report, verify_mission_report
from skeleton.gameforge.errors import GameForgeError

BOARD_SCHEMA = "skeleton.gameforge.expedition.board.v1"
PORTABLE_SCHEMA = "skeleton.gameforge.expedition.episode_evidence.v1"


def expedition_board(source: Any, checkpoint: Any) -> dict:
    _require(verify_expedition(source, checkpoint, session=True), "expedition checkpoint does not replay")
    data, _, steps, _, episodes = _admit(source)
    state = checkpoint["state"]
    base = campaign_board(data["campaign"], state["campaign"])
    local = []
    for step in steps:
        oid = step["id"]
        if oid not in episodes:
            continue
        ep = episodes[oid]
        summary = state["episodes"][oid]
        current = summary["state"]
        position = current["pos"]
        tiles = [list(row) for row in ep["source"]["map"]]
        for resource in ep["source"]["resources"]:
            x, y = resource["at"]
            if current["stock"][resource["id"]] > 0:
                tiles[y][x] = "R"
        x, y = ep["source"]["dock"]
        tiles[y][x] = "D"
        x, y = current["npc_pos"]
        tiles[y][x] = "M"
        x, y = position
        tiles[y][x] = "@"
        local.append({"objective": oid, "region": step["location"],
                      "required_ending": ep["ending"], "gate_satisfied": summary["gate_satisfied"],
                      "grid": ["".join(row) for row in tiles],
                      "active_here": any(a["type"] == "harbor" and a["objective"] == oid
                                         for a in state["legal_actions"]),
                      "tick": current["tick"], "max_ticks": ep["source"]["max_ticks"],
                      "inventory": current["inventory"], "resource_stock": current["stock"],
                      "merchant_stock": current["npc_stock"], "coins": current["coins"],
                      "delivered": current["delivered"], "ending": current["ending"],
                      "reputation": current["reputation"]})
        if "missions" in summary:
            local[-1]["missions"] = summary["missions"]
    # Do not accidentally expose a base-campaign resolve action without its
    # stronger episode gate. Only the combined runtime owns legal actions.
    base.pop("board_digest")
    base["legal_actions"] = state["legal_actions"]
    body = {"schema": BOARD_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": checkpoint["session_digest"], "campaign_view": base,
            "episodes": local, "blockers": state["blockers"],
            "legal_actions": state["legal_actions"], "native_qualified": False,
            "release_qualified": False}
    receipt = {**body, "board_digest": digest(body)}
    _encode(receipt)
    return detached(receipt)


def turn(source: Any, checkpoint: Any, board_digest: str, index: int) -> dict:
    current = expedition_board(source, checkpoint)
    _require(type(board_digest) is str and board_digest == current["board_digest"],
             "expedition board changed")
    actions = current["legal_actions"]
    _require(bool(actions), "no legal expedition actions")
    selected = _integer(index, 0, len(actions) - 1)
    following = resume_expedition(source, checkpoint, [actions[selected]])
    result = {"action": actions[selected], "receipt": following,
              "board": expedition_board(source, following),
              "native_qualified": False, "release_qualified": False}
    _encode(result)
    return result


def episode_evidence(source: Any, checkpoint: Any, objective: str) -> dict:
    _require(verify_expedition(source, checkpoint, session=True),
             "expedition checkpoint does not replay")
    _, _, _, _, episodes = _admit(source)
    _require(type(objective) is str and objective in episodes, "unknown episode")
    ep = episodes[objective]
    actions = [event["action"] for event in checkpoint["actions"]
               if event["type"] == "harbor" and event["objective"] == objective]
    bundle = harbor.export_bundle(ep["source"], actions)
    state = harbor.verify_bundle(bundle)
    summary = checkpoint["state"]["episodes"][objective]
    _require(state == summary["state"] and bundle["bundle_digest"] == summary["bundle_digest"],
             "episode evidence differs from integrated replay")
    body = {"schema": PORTABLE_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": checkpoint["session_digest"], "objective": objective,
            "required_ending": ep["ending"], "gate_satisfied": summary["gate_satisfied"],
            "bundle": bundle, "native_qualified": False, "release_qualified": False}
    if "mission_board" in ep:
        report = mission_report(bundle, ep["mission_board"])
        verify_mission_report(report)
        _require(report["report_digest"] == summary["missions"]["report_digest"],
                 "mission evidence differs from integrated replay")
        body["mission_report"] = report
    receipt = {**body, "evidence_digest": digest(body)}
    _encode({"request": source, "receipt": checkpoint, "evidence": receipt})
    return receipt


def verify_evidence(source: Any, checkpoint: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(episode_evidence(source, checkpoint, submitted["objective"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def verify_board(source: Any, checkpoint: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(expedition_board(source, checkpoint))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
