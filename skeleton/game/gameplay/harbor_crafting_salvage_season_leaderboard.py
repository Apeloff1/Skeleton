"""Deterministic replay-certified salvage season leaderboard."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_season import (
    MAX_SEASON_SAVE_BYTES, verify_salvage_season,
)

SCHEMA = "skeleton.game.harbor.salvage-season-leaderboard.v1"
MAX_BYTES = MAX_SEASON_SAVE_BYTES * 2
MAX_ENTRIES = 32
FIELDS = {"schema", "entries", "ranking", "board_digest", "leaderboard_digest"}
ENTRY_FIELDS = {"player", "save"}


def build_season_leaderboard(entries: Any) -> dict[str, Any]:
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise HarborError("invalid salvage leaderboard size")
    names: set[str] = set()
    ranked: list[dict[str, Any]] = []
    board_digest = None
    for entry in entries:
        _keys(entry, ENTRY_FIELDS, "salvage leaderboard entry")
        player = _identifier(entry["player"], "salvage leaderboard player")
        if player in names:
            raise HarborError("duplicate salvage leaderboard player")
        names.add(player)
        status = verify_salvage_season(entry["save"])
        source_board_digest = digest({"source": entry["save"]["source"],
                                      "board": entry["save"]["board"]})
        if board_digest is not None and source_board_digest != board_digest:
            raise HarborError("salvage leaderboard source or board mismatch")
        board_digest = source_board_digest
        ranked.append({"player": player, "score": status["score"],
                       "rounds": status["rounds_earned"], "complete": status["complete"],
                       "save_digest": status["save_digest"]})
    ranked.sort(key=lambda row: (-row["score"], -row["rounds"], row["player"]))
    result = {"schema": SCHEMA, "entries": deepcopy(entries),
              "ranking": ranked, "board_digest": board_digest}
    result["leaderboard_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("salvage leaderboard exceeds byte budget")
    return result


def verify_season_leaderboard(board: Any) -> list[dict[str, Any]]:
    _keys(board, FIELDS, "salvage leaderboard")
    if board["schema"] != SCHEMA or len(canonical(board)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage leaderboard")
    if board["leaderboard_digest"] != digest({k: v for k, v in board.items()
                                               if k != "leaderboard_digest"}):
        raise HarborError("salvage leaderboard digest mismatch")
    rebuilt = build_season_leaderboard(board["entries"])
    if rebuilt != board:
        raise HarborError("salvage leaderboard replay mismatch")
    return deepcopy(board["ranking"])
