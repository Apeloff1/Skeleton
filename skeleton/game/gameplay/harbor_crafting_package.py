"""Original offline Lantern Quay game distribution and playable package custody.

The package embeds validated authored sources and a replay-proven sample victory,
not executable code or third-party assets. Every import replays gameplay and
mission consequences; a matching outer hash alone never authorizes a game.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, export_bundle,
    validate_source, verify_bundle,
)
from .harbor_crafting_missions import (
    mission_report, solve_missions, validate_board, verify_mission_report,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.package-play.v1"
MAX_PACKAGE_BYTES = MAX_BUNDLE_BYTES * 4
MAX_PLAY_BYTES = MAX_BUNDLE_BYTES * 4
MANIFEST_PATHS = ("board.json", "demo-report.json", "world.json")


def _manifest(source: dict[str, Any], board: dict[str, Any], demo: dict[str, Any]) -> list[dict[str, Any]]:
    parts = {
        "board.json": board,
        "demo-report.json": demo,
        "world.json": source,
    }
    return [
        {"path": path, "sha256": digest(parts[path]), "bytes": len(canonical(parts[path]))}
        for path in MANIFEST_PATHS
    ]


def build_package(source: Any, board: Any, *, choice: str = "signal") -> dict[str, Any]:
    """Build a complete playable, deterministic, source-bound JSON distribution."""
    world = validate_source(source)
    authored = validate_board(board, world)
    demo = solve_missions(world, authored, choice=choice)
    if verify_mission_report(demo, require_all=True)["points"] != demo["points"]:
        raise HarborError("package demo mission replay mismatch")
    if verify_bundle(demo["bundle"], require_win=True) != demo["bundle"]["state"]:
        raise HarborError("package demo gameplay replay mismatch")
    package = {
        "schema": PACKAGE_SCHEMA,
        "id": world["id"],
        "choice": choice,
        "source": world,
        "source_digest": digest(world),
        "board": authored,
        "board_digest": digest(authored),
        "demo": demo,
        "manifest": _manifest(world, authored, demo),
    }
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("game package exceeds byte limit")
    return package


def verify_package(package: Any) -> dict[str, Any]:
    """Reconstruct source, manifest and earned demo; reject forged distributions."""
    _keys(package, {
        "schema", "id", "choice", "source", "source_digest",
        "board", "board_digest", "demo", "manifest", "package_digest",
    }, "game package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized game package")
    if package["package_digest"] != digest({
        key: value for key, value in package.items() if key != "package_digest"
    }):
        raise HarborError("game package digest mismatch")
    source = validate_source(package["source"])
    board = validate_board(package["board"], source)
    if package["id"] != source["id"]:
        raise HarborError("game package identity mismatch")
    if package["source_digest"] != digest(source) or package["board_digest"] != digest(board):
        raise HarborError("game package source mismatch")
    if package["manifest"] != _manifest(source, board, package["demo"]):
        raise HarborError("game package manifest mismatch")
    verify_mission_report(package["demo"], require_all=True)
    if package["demo"]["source_digest"] != package["source_digest"]:
        raise HarborError("game package demo source mismatch")
    if package["demo"]["board_digest"] != package["board_digest"]:
        raise HarborError("game package demo board mismatch")
    recreated = build_package(source, board, choice=package["choice"])
    if recreated != package:
        raise HarborError("game package replay mismatch")
    return {
        "id": source["id"],
        "source_digest": package["source_digest"],
        "board_digest": package["board_digest"],
        "package_digest": package["package_digest"],
        "demo_ending": package["demo"]["bundle"]["state"]["ending"],
        "demo_points": package["demo"]["points"],
    }


def play_package(package: Any, actions: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Play any legal action sequence from a verified packaged original world."""
    verify_package(package)
    if not isinstance(actions, list):
        raise HarborError("package actions must be a list")
    bundle = export_bundle(package["source"], actions)
    report = mission_report(bundle, package["board"], require_all=require_all)
    play = {
        "schema": PLAY_SCHEMA,
        "package": deepcopy(package),
        "package_digest": package["package_digest"],
        "actions": deepcopy(actions),
        "report": report,
    }
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("package play exceeds byte limit")
    return play


def verify_package_play(play: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Re-run every player transition and mission result from packaged sources."""
    _keys(play, {
        "schema", "package", "package_digest", "actions", "report", "play_digest",
    }, "package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized package play")
    if play["play_digest"] != digest({key: value for key, value in play.items() if key != "play_digest"}):
        raise HarborError("package play digest mismatch")
    package = play["package"]
    if not isinstance(package, dict) or play["package_digest"] != package.get("package_digest"):
        raise HarborError("package play source mismatch")
    recreated = play_package(package, play["actions"], require_all=require_all)
    if recreated != play:
        raise HarborError("package play replay mismatch")
    result = verify_mission_report(play["report"], require_all=require_all)
    return {
        "package_digest": play["package_digest"],
        "ending": play["report"]["bundle"]["state"]["ending"],
        "points": result["points"],
        "completed": result["completed"],
    }
