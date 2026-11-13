"""Portable, bounded, source-bound salvage game package and replayed play record.

Digests detect accidental/tampered data but are not digital signatures.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage import (
    MAX_REPORT_BYTES, build_salvage, validate_salvage_board, verify_salvage,
)

PACKAGE_SCHEMA = "skeleton.game.harbor.salvage-package.v1"
PLAY_SCHEMA = "skeleton.game.harbor.salvage-package-play.v1"
MAX_PACKAGE_BYTES = 131072
MAX_PLAY_BYTES = MAX_REPORT_BYTES * 2
PACKAGE_KEYS = {"schema", "id", "source", "board", "source_digest",
                "board_digest", "package_digest"}
PLAY_KEYS = {"schema", "package", "report", "package_digest",
             "report_digest", "play_digest"}


def build_salvage_package(source: Any, board: Any, *, package_id: str) -> dict[str, Any]:
    authored = validate_salvage_board(board, source)
    world = build_salvage(source, authored, [])["source"]
    result = {"schema": PACKAGE_SCHEMA, "id": _identifier(package_id, "salvage package id"),
              "source": world, "board": authored,
              "source_digest": digest(world), "board_digest": digest(authored)}
    result["package_digest"] = digest(result)
    if len(canonical(result)) > MAX_PACKAGE_BYTES:
        raise HarborError("salvage package exceeds byte budget")
    return result


def verify_salvage_package(package: Any) -> dict[str, Any]:
    _keys(package, PACKAGE_KEYS, "salvage package")
    if package["schema"] != PACKAGE_SCHEMA or len(canonical(package)) > MAX_PACKAGE_BYTES:
        raise HarborError("unsupported or oversized salvage package")
    rebuilt = build_salvage_package(package["source"], package["board"],
                                    package_id=package["id"])
    if rebuilt != package:
        raise HarborError("salvage package digest or source mismatch")
    return deepcopy(package)


def play_salvage_package(package: Any, actions: Any, *,
                         require_complete: bool = False) -> dict[str, Any]:
    verified = verify_salvage_package(package)
    report = build_salvage(verified["source"], verified["board"], actions,
                           require_complete=require_complete)
    play = {"schema": PLAY_SCHEMA, "package": verified, "report": report,
            "package_digest": verified["package_digest"],
            "report_digest": report["report_digest"]}
    play["play_digest"] = digest(play)
    if len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("salvage package play exceeds byte budget")
    return play


def verify_salvage_package_play(play: Any, *,
                                require_complete: bool = False) -> dict[str, Any]:
    _keys(play, PLAY_KEYS, "salvage package play")
    if play["schema"] != PLAY_SCHEMA or len(canonical(play)) > MAX_PLAY_BYTES:
        raise HarborError("unsupported or oversized salvage package play")
    if play["play_digest"] != digest({k: v for k, v in play.items()
                                      if k != "play_digest"}):
        raise HarborError("salvage package play digest mismatch")
    package = verify_salvage_package(play["package"])
    status = verify_salvage(play["report"], require_complete=require_complete)
    rebuilt = play_salvage_package(package, play["report"]["actions"],
                                   require_complete=require_complete)
    if rebuilt != play or package["package_digest"] != play["package_digest"] or (
            status["report_digest"] != play["report_digest"]):
        raise HarborError("salvage package play replay mismatch")
    return status
