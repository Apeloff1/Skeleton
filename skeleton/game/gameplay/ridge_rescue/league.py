"""Replay-derived offline rescue league with optimistic append and deterministic ranking.

A score is earned only from the canonical game engine's verified portable
replay. Handles are labels, not authenticated identities. No external network
or trusted-clock dependency is required for offline tournaments.
"""
from __future__ import annotations
from copy import deepcopy
import re

from .custody import canonical, digest, verify_run
from .routebook import _document
from .schema import parse_world, world_dict

SOURCE_SCHEMA = "ridge.rescue.league.v1"
BOARD_SCHEMA = "ridge.rescue.league.board.v1"
EXPORT_SCHEMA = "ridge.rescue.league.export.v1"
MAX_SOURCE = 128_000
MAX_BOARD = 1_000_000
MAX_ENTRIES = 32
HANDLE = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")


class LeagueError(ValueError):
    pass


def parse_league(source: dict | str | bytes) -> dict:
    data = _document(source, MAX_SOURCE)
    if set(data) != {"schema", "id", "title", "objective", "world", "max_entries"}:
        raise LeagueError("invalid league source fields")
    if data["schema"] != SOURCE_SCHEMA:
        raise LeagueError("unsupported league source")
    if not isinstance(data["id"], str) or not HANDLE.fullmatch(data["id"]):
        raise LeagueError("invalid league id")
    if not isinstance(data["title"], str) or not 1 <= len(data["title"]) <= 96 or any(ord(c) < 32 for c in data["title"]):
        raise LeagueError("invalid league title")
    if data["objective"] not in ("protect", "salvage", "any"):
        raise LeagueError("invalid league objective")
    if type(data["max_entries"]) is not int or not 1 <= data["max_entries"] <= MAX_ENTRIES:
        raise LeagueError("invalid league entry budget")
    try:
        world = parse_world(data["world"])
    except (ValueError, TypeError, KeyError) as exc:
        raise LeagueError("invalid league world") from exc
    result = {"schema": SOURCE_SCHEMA, "id": data["id"], "title": data["title"],
              "objective": data["objective"], "world": world_dict(world),
              "max_entries": data["max_entries"]}
    if len(canonical(result)) > MAX_SOURCE:
        raise LeagueError("league source too large")
    return result


def _head(board: dict) -> str:
    return digest({key: value for key, value in board.items() if key != "head"})


def open_league(source: dict | str | bytes) -> dict:
    league = parse_league(source)
    result = {"schema": BOARD_SCHEMA, "source": league, "source_sha256": digest(league),
              "entries": [], "head": ""}
    result["head"] = _head(result)
    return result


def _score(league: dict, run: dict) -> dict:
    try:
        verified = verify_run(run)
    except (ValueError, TypeError, KeyError) as exc:
        raise LeagueError("invalid or unreplayable league run") from exc
    if canonical(world_dict(verified["world"])) != canonical(league["world"]):
        raise LeagueError("league run source mismatch")
    state = verified["state"]
    status = state["status"]
    if status not in ("won:protect", "won:salvage"):
        raise LeagueError("league accepts earned victories only")
    if league["objective"] != "any" and status != "won:" + league["objective"]:
        raise LeagueError("victory does not match league objective")
    rescued = sum(value == "rescued" for value in state["civilians"].values())
    defeated = sum(enemy["health"] == 0 for enemy in state["raiders"].values())
    beacon = int(state["flags"]["beacon"] is True)
    score = (1000 if status == "won:protect" else 700) + 120 * rescued + 40 * defeated + (
        80 * beacon) + 12 * state["health"] + 3 * state["stamina"] - 2 * state["turn"]
    return {"score": score, "turns": state["turn"], "status": status, "rescued": rescued,
            "defeated": defeated, "beacon": bool(beacon), "health": state["health"],
            "stamina": state["stamina"]}


def verify_league(board: dict | str | bytes) -> dict:
    data = _document(board, MAX_BOARD)
    if set(data) != {"schema", "source", "source_sha256", "entries", "head"} or data["schema"] != BOARD_SCHEMA:
        raise LeagueError("invalid league board fields")
    league = parse_league(data["source"])
    if canonical(league) != canonical(data["source"]) or digest(league) != data["source_sha256"]:
        raise LeagueError("league source mismatch")
    entries = data["entries"]
    if not isinstance(entries, list) or len(entries) > league["max_entries"]:
        raise LeagueError("invalid league entry count")
    handles = set()
    ranking = []
    for sequence, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {
            "sequence", "handle", "run", "run_sha256", "result"
        }:
            raise LeagueError("invalid league entry fields")
        handle = entry["handle"]
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle) or handle in handles:
            raise LeagueError("invalid or duplicate league handle")
        handles.add(handle)
        if type(entry["sequence"]) is not int or entry["sequence"] != sequence:
            raise LeagueError("invalid league sequence")
        if entry["run_sha256"] != digest(entry["run"]):
            raise LeagueError("league run digest mismatch")
        result = _score(league, entry["run"])
        if canonical(result) != canonical(entry["result"]):
            raise LeagueError("league result not earned from replay")
        ranking.append({"handle": handle, "sequence": sequence, **result})
    if data["head"] != _head(data):
        raise LeagueError("league head mismatch")
    ranking.sort(key=lambda item: (-item["score"], item["turns"], item["handle"]))
    for index, item in enumerate(ranking, 1):
        item["rank"] = index
    return {"source": league, "head": data["head"], "ranking": ranking,
            "entries": len(entries), "champion": ranking[0]["handle"] if ranking else None}


def submit_run(board: dict, *, expected_head: str, handle: str, run: dict) -> dict:
    checked = verify_league(board)
    if expected_head != checked["head"]:
        raise LeagueError("stale league board revision")
    if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        raise LeagueError("invalid league handle")
    if any(entry["handle"] == handle for entry in board["entries"]):
        raise LeagueError("league handle already submitted")
    if checked["entries"] >= checked["source"]["max_entries"]:
        raise LeagueError("league entry budget exhausted")
    if not isinstance(run, dict):
        raise LeagueError("invalid league run")
    result = _score(checked["source"], run)
    updated = deepcopy(board)
    updated["entries"].append({"sequence": len(updated["entries"]) + 1,
                               "handle": handle, "run": deepcopy(run),
                               "run_sha256": digest(run), "result": result})
    updated["head"] = _head(updated)
    if len(canonical(updated)) > MAX_BOARD:
        raise LeagueError("league board byte budget exceeded")
    verify_league(updated)
    return updated


def export_league(board: dict) -> dict:
    checked = verify_league(board)
    payload = {"schema": EXPORT_SCHEMA, "board": deepcopy(board),
               "ranking": checked["ranking"], "source_sha256": digest(checked["source"])}
    if len(canonical(payload)) > MAX_BOARD:
        raise LeagueError("league export too large")
    return {"payload": payload, "sha256": digest(payload)}


def verify_league_export(bundle: dict | str | bytes) -> dict:
    data = _document(bundle, MAX_BOARD)
    if set(data) != {"payload", "sha256"} or not isinstance(data["payload"], dict):
        raise LeagueError("invalid league export")
    if data["sha256"] != digest(data["payload"]):
        raise LeagueError("league export digest mismatch")
    payload = data["payload"]
    if set(payload) != {"schema", "board", "ranking", "source_sha256"} or payload["schema"] != EXPORT_SCHEMA:
        raise LeagueError("invalid league export payload")
    checked = verify_league(payload["board"])
    if payload["source_sha256"] != digest(checked["source"]) or canonical(payload["ranking"]) != canonical(checked["ranking"]):
        raise LeagueError("league export ranking mismatch")
    return checked
