"""Portable original stealth-patrol distribution and full replay verification."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_patrol import (
    MAX_REPORT_BYTES, build_patrol, validate_patrol_board, verify_patrol,
)

SCHEMA = "skeleton.game.harbor.patrol-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.patrol-package-play.v1"
MAX_PACKAGE_BYTES = MAX_REPORT_BYTES * 2
MAX_PLAY_BYTES = MAX_REPORT_BYTES * 3
PACKAGE_KEYS = {"schema", "id", "source", "board", "source_digest",
                "board_digest", "demo", "manifest", "package_digest"}
PLAY_KEYS = {"schema", "package", "actions", "report", "play_digest"}


def _manifest(source: dict[str, Any], board: dict[str, Any],
              demo: dict[str, Any]) -> list[dict[str, Any]]:
    parts = {"board.json": board, "demo.json": demo, "world.json": source}
    return [{"path": name, "sha256": digest(parts[name]),
             "bytes": len(canonical(parts[name]))} for name in sorted(parts)]


def build_patrol_package(source: Any, board: Any, demo_actions: Any, *,
                         package_id: str) -> dict[str, Any]:
    authored = validate_patrol_board(board, source)
    demo = build_patrol(source, authored, demo_actions, require_complete=True)
    verify_patrol(demo, require_complete=True)
    package = {"schema": SCHEMA, "id": _identifier(package_id, "patrol package id"),
               "source": demo["source"], "board": authored,
               "source_digest": demo["source_digest"],
               "board_digest": demo["board_digest"], "demo": demo,
               "manifest": _manifest(demo["source"], authored, demo)}
    package["package_digest"] = digest(package)
    if len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("patrol package exceeds byte budget")
    return package


def verify_patrol_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_KEYS, "patrol package")
    if package["schema"] != SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized patrol package")
    if package["package_digest"] != digest({k: v for k, v in package.items()
                                             if k != "package_digest"}):
        raise HarborError("patrol package digest mismatch")
    if not isinstance(package["demo"], dict) or not isinstance(package["demo"].get("actions"), list):
        raise HarborError("patrol package demo must contain an action list")
    rebuilt = build_patrol_package(
        package["source"], package["board"], package["demo"]["actions"],
        package_id=package["id"],
    )
    if rebuilt != package:
        raise HarborError("patrol package source or demo replay mismatch")
    return {"id": package["id"], "package_digest": package["package_digest"],
            "demo_score": package["demo"]["state"]["score"]}


def play_patrol_package(package: Any, actions: Any, *,
                        require_complete: bool = False) -> dict[str, Any]:
    verify_patrol_package(package)
    report = build_patrol(package["source"], package["board"], actions,
                          require_complete=require_complete)
    result = {"schema": PLAY_SCHEMA, "package": deepcopy(package),
              "actions": deepcopy(report["actions"]), "report": report}
    result["play_digest"] = digest(result)
    if len(canonical(result)) > MAX_PLAY_BYTES:
        raise HarborError("patrol play exceeds byte budget")
    return result


def verify_patrol_package_play(play: Any, *,
                               require_complete: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_KEYS, "patrol package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized patrol play")
    if play["play_digest"] != digest({k: v for k, v in play.items()
                                      if k != "play_digest"}):
        raise HarborError("patrol play digest mismatch")
    rebuilt = play_patrol_package(play["package"], play["actions"],
                                  require_complete=require_complete)
    if rebuilt != play:
        raise HarborError("patrol package play replay mismatch")
    return verify_patrol(play["report"], require_complete=require_complete)
