"""Replay-derived ranked standings across original completed convoy leagues."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_convoy_league import MAX_SAVE_BYTES, verify_league

SCHEMA = "skeleton.game.harbor.convoy-league-leaderboard.v1"
MAX_ENTRANTS = 16
MAX_BOARD_BYTES = MAX_ENTRANTS * MAX_SAVE_BYTES + 65536
FIELDS = {"schema", "entrants", "ranking", "league_digest", "board_digest"}
ENTRANT_FIELDS = {"id", "save"}


def build_league_leaderboard(entrants: Any) -> dict[str, Any]:
    if not isinstance(entrants, list) or not 1 <= len(entrants) <= MAX_ENTRANTS:
        raise HarborError("invalid league leaderboard entrants")
    seen: set[str] = set()
    source_hash = None
    league_hash = None
    ranking = []
    for entrant in entrants:
        _keys(entrant, ENTRANT_FIELDS, "league entrant")
        name = _identifier(entrant["id"], "league entrant id")
        if name in seen:
            raise HarborError("duplicate league entrant")
        seen.add(name)
        status = verify_league(entrant["save"], require_complete=True)
        save = entrant["save"]
        if source_hash is None:
            source_hash, league_hash = save["source_digest"], save["league_digest"]
        if save["source_digest"] != source_hash or save["league_digest"] != league_hash:
            raise HarborError("league leaderboard source or board mismatch")
        ticks = sum(row["ticks"] for row in save["standings"])
        ranking.append({
            "id": name, "score": status["score"], "ticks": ticks,
            "save_digest": status["save_digest"],
        })
    ranking.sort(key=lambda row: (-row["score"], row["ticks"], row["id"]))
    for index, row in enumerate(ranking):
        row["rank"] = index + 1
    board = {
        "schema": SCHEMA, "entrants": deepcopy(entrants),
        "ranking": ranking, "league_digest": league_hash,
    }
    board["board_digest"] = digest(board)
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("league leaderboard exceeds byte budget")
    return board


def verify_league_leaderboard(board: Any) -> dict[str, Any]:
    _keys(board, FIELDS, "league leaderboard")
    if board["schema"] != SCHEMA or len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("unsupported or oversized league leaderboard")
    if board["board_digest"] != digest({
        key: value for key, value in board.items() if key != "board_digest"
    }):
        raise HarborError("league leaderboard digest mismatch")
    rebuilt = build_league_leaderboard(board["entrants"])
    if rebuilt != board:
        raise HarborError("league leaderboard replay mismatch")
    return {
        "verified": True, "ranking": deepcopy(rebuilt["ranking"]),
        "board_digest": rebuilt["board_digest"],
    }
