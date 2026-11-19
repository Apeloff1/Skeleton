"""Recover the existing Lantern Quay package authoring/distribution into expeditions.

Packages remain authored local-game sources, never executable code or player
progress. All generated bindings are admitted by the expedition owner;
distribution verification cannot automatically complete any objective.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_expedition import (
    MAX_EPISODES, REQUEST_SCHEMA, build_expedition, play_expedition,
)
from skeleton.app.original_quest_cli import _encode, _object, _require, _strings, _text
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_missions import validate_board
from skeleton.game.gameplay.harbor_crafting_package import build_package, verify_package
from skeleton.gameforge.errors import GameForgeError

AUTHOR_SCHEMA = "skeleton.gameforge.expedition.author.v1"
RECEIPT_SCHEMA = "skeleton.gameforge.expedition.author.receipt.v1"


def author_expedition(source: Any) -> dict:
    """Build or verify canonical playable packages and attach them to outer objectives.

    The caller independently provides each authored world and mission board.
    Optional submitted packages must exactly match that input and the
    package owner's deterministic construction. The package's demo is a
    witness only; genesis creates no pre-earned event history.
    """
    data = _object(detached(source), {"schema", "campaign", "bindings"})
    _require(data["schema"] == AUTHOR_SCHEMA, "unsupported expedition author schema")
    bindings = data["bindings"]
    _require(type(bindings) is list and 1 <= len(bindings) <= MAX_EPISODES,
             "invalid package binding count")
    episodes = []
    custody = []
    seen = set()
    for raw in bindings:
        item = _object(raw, {"objective", "world", "mission_board", "choice", "required_missions"},
                       {"package"})
        objective = _text(item["objective"], 128)
        _require(objective not in seen, "duplicate package binding")
        seen.add(objective)
        world = harbor.validate_source(item["world"])
        board = validate_board(item["mission_board"], world)
        choice = _text(item["choice"], 32)
        _require(choice in {"signal", "shelter"}, "unsupported package ending choice")
        required = sorted(_strings(item["required_missions"], 12, 48, nonempty=True))
        _require(set(required) <= {row["id"] for row in board["missions"]},
                 "unknown bound mission")
        if "package" in item:
            package = item["package"]
            # Do not use untrusted submitted paths or reinterpret its source.
            summary = verify_package(package)
            _require(harbor.canonical(package["source"]) == harbor.canonical(world)
                     and harbor.canonical(package["board"]) == harbor.canonical(board)
                     and package["choice"] == choice, "package independent source mismatch")
        else:
            package = build_package(world, board, choice=choice)
            summary = verify_package(package)
        _require(set(required) <= set(package["demo"]["completed"]),
                 "package demo lacks required mission evidence")
        ending = "beacon" if choice == "signal" else "safe_harbor"
        _require(summary["demo_ending"] == ending, "package demo ending mismatch")
        witness = [harbor.normalize_action(event["action"])
                   for event in package["demo"]["bundle"]["events"]]
        episodes.append({"objective": objective, "source": world, "required_ending": ending,
                         "witness": witness, "mission_board": board,
                         "required_missions": required})
        custody.append({"objective": objective, "package_id": summary["id"],
                        "package_digest": summary["package_digest"],
                        "source_digest": summary["source_digest"],
                        "board_digest": summary["board_digest"],
                        "demo_ending": summary["demo_ending"], "demo_points": summary["demo_points"],
                        "witness_action_count": len(witness)})
    request = {"schema": REQUEST_SCHEMA, "campaign": data["campaign"], "episodes": episodes}
    design = build_expedition(request)
    genesis = play_expedition(request, [])
    _require(genesis["actions"] == [] and not genesis["state"]["earned_rewards"]
             and all(row["event_count"] == 0 for row in genesis["state"]["episodes"].values()),
             "package demo cannot confer player progress")
    body = {"schema": RECEIPT_SCHEMA, "author_source_digest": digest(data),
            "request": request, "design_digest": design["design_digest"],
            "genesis_digest": genesis["session_digest"], "package_custody": custody,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "author_digest": digest(body)}
    _encode({"request": source, "composition": result})
    return result


def verify_authoring(source: Any, receipt: Any) -> bool:
    try:
        return _encode(receipt) == _encode(author_expedition(source))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
