"""Source-bound, replay-derived field routebooks for player-authored rescue runs.

Routebooks are executable game content, not a shortcut around the game engine.
Every step goes through the canonical action validator, turn simulation and CAS
journal. Source digests are integrity checks, not signatures or identity proof.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from .custody import canonical, digest
from .engine import apply, available_actions, initial_state
from .journal import append_journal, open_journal, verify_journal, export_journal
from .schema import parse_world, world_dict

SOURCE_SCHEMA = "ridge.rescue.routebook.v1"
SESSION_SCHEMA = "ridge.rescue.routebook.session.v1"
EXPORT_SCHEMA = "ridge.rescue.routebook.export.v1"
MAX_SOURCE = 160_000
MAX_SESSION = 512_000
MAX_TRACKS = 16
MAX_ACTIONS = 256
IDENT = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


class RoutebookError(ValueError):
    """Invalid source, stale revision, or non-replayable gameplay."""


def _document(source: Any, limit: int) -> dict:
    if isinstance(source, bytes):
        if len(source) > limit:
            raise RoutebookError("document exceeds byte budget")
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RoutebookError("document must be UTF-8") from exc
    if isinstance(source, str):
        if len(source.encode("utf-8")) > limit:
            raise RoutebookError("document exceeds byte budget")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise RoutebookError("duplicate JSON key")
                result[key] = value
            return result
        try:
            source = json.loads(source, object_pairs_hook=unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(RoutebookError("nonfinite number")))
        except (ValueError, TypeError) as exc:
            raise RoutebookError("invalid routebook JSON") from exc
    if not isinstance(source, dict):
        raise RoutebookError("expected document object")
    try:
        if len(canonical(source)) > limit:
            raise RoutebookError("document exceeds byte budget")
    except (ValueError, TypeError, OverflowError) as exc:
        raise RoutebookError("noncanonical document") from exc
    return source


def _ident(value: Any) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise RoutebookError("invalid route identifier")
    return value


def _title(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 96 or any(ord(c) < 32 for c in value):
        raise RoutebookError("invalid route title")
    return value


def _guard(value: Any, world) -> dict:
    if not isinstance(value, dict) or set(value) != {"kind", "value"}:
        raise RoutebookError("invalid route guard")
    kind, arg = value["kind"], value["value"]
    if kind == "always" and arg is True:
        return {"kind": kind, "value": True}
    if kind == "beacon" and arg is True:
        return {"kind": kind, "value": True}
    if kind == "rescued" and isinstance(arg, str) and arg in {ident for ident, _ in world.civilians}:
        return {"kind": kind, "value": arg}
    if kind == "turn-before" and type(arg) is int and 0 <= arg <= world.max_turns:
        return {"kind": kind, "value": arg}
    if kind == "health-at-least" and type(arg) is int and 1 <= arg <= 10:
        return {"kind": kind, "value": arg}
    raise RoutebookError("unsupported or invalid route guard")


def _action(value: Any) -> dict:
    if not isinstance(value, dict) or not value or len(value) > 3:
        raise RoutebookError("invalid route action")
    if set(value) - {"verb", "direction", "target", "item", "choice", "side"}:
        raise RoutebookError("unknown route action fields")
    if not isinstance(value.get("verb"), str) or value["verb"] not in {
        "move", "gather", "craft", "attack", "rescue", "rest", "signal", "evacuate", "trade"
    }:
        raise RoutebookError("unsupported route action")
    if any(not isinstance(v, str) or not 1 <= len(v) <= 64 for v in value.values()):
        raise RoutebookError("invalid action argument")
    return deepcopy(value)


def parse_routebook(source: dict | str | bytes) -> dict:
    data = _document(source, MAX_SOURCE)
    if set(data) != {"schema", "id", "title", "world", "tracks"} or data["schema"] != SOURCE_SCHEMA:
        raise RoutebookError("unsupported routebook source")
    try:
        world = parse_world(data["world"])
    except (ValueError, TypeError, KeyError) as exc:
        raise RoutebookError("invalid routebook world") from exc
    tracks = data["tracks"]
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= MAX_TRACKS:
        raise RoutebookError("invalid track count")
    seen = set()
    normalized = []
    for track in tracks:
        if not isinstance(track, dict) or set(track) != {"id", "title", "ending", "steps"}:
            raise RoutebookError("invalid route track")
        ident = _ident(track["id"])
        if ident in seen:
            raise RoutebookError("duplicate track")
        seen.add(ident)
        ending = track["ending"]
        if ending not in ("protect", "salvage"):
            raise RoutebookError("invalid route ending")
        steps = track["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= min(MAX_ACTIONS, world.max_turns):
            raise RoutebookError("invalid route step count")
        entries = []
        for step in steps:
            if not isinstance(step, dict) or set(step) != {"guard", "action"}:
                raise RoutebookError("invalid route step")
            entries.append({"guard": _guard(step["guard"], world), "action": _action(step["action"])})
        if entries[-1]["action"] != {"verb": "evacuate", "choice": ending}:
            raise RoutebookError("route must finish with its declared ending action")
        normalized.append({"id": ident, "title": _title(track["title"]), "ending": ending, "steps": entries})
    result = {"schema": SOURCE_SCHEMA, "id": _ident(data["id"]), "title": _title(data["title"]),
              "world": world_dict(world), "tracks": normalized}
    if len(canonical(result)) > MAX_SOURCE:
        raise RoutebookError("normalized source too large")
    return result


def _holds(guard: dict, state: dict) -> bool:
    kind, value = guard["kind"], guard["value"]
    if kind == "always":
        return True
    if kind == "beacon":
        return state["flags"]["beacon"] is True
    if kind == "rescued":
        return state["civilians"][value] == "rescued"
    if kind == "turn-before":
        return state["turn"] < value
    return state["health"] >= value


def _track(source: dict, track_id: str) -> dict:
    matches = [item for item in source["tracks"] if item["id"] == track_id]
    if len(matches) != 1:
        raise RoutebookError("unknown route track")
    return matches[0]


def _head(session: dict) -> str:
    return digest({key: value for key, value in session.items() if key != "head"})


def open_route(source: dict | str | bytes, track_id: str) -> dict:
    routebook = parse_routebook(source)
    track = _track(routebook, track_id)
    world = parse_world(routebook["world"])
    result = {"schema": SESSION_SCHEMA, "source": routebook, "source_sha256": digest(routebook),
              "track": track["id"], "cursor": 0, "journal": open_journal(world), "status": "playing"}
    result["head"] = _head(result)
    if len(canonical(result)) > MAX_SESSION:
        raise RoutebookError("route session too large")
    return result


def verify_route(session: dict | str | bytes) -> dict:
    data = _document(session, MAX_SESSION)
    if set(data) != {"schema", "source", "source_sha256", "track", "cursor", "journal", "status", "head"}:
        raise RoutebookError("invalid route session fields")
    if data["schema"] != SESSION_SCHEMA:
        raise RoutebookError("unsupported route session")
    source = parse_routebook(data["source"])
    if canonical(source) != canonical(data["source"]) or digest(source) != data["source_sha256"]:
        raise RoutebookError("route source digest mismatch")
    track = _track(source, data["track"])
    cursor = data["cursor"]
    if type(cursor) is not int or not 0 <= cursor <= len(track["steps"]):
        raise RoutebookError("invalid route cursor")
    try:
        verified = verify_journal(data["journal"])
    except (ValueError, TypeError, KeyError) as exc:
        raise RoutebookError("unreplayable route journal") from exc
    if canonical(world_dict(verified["world"])) != canonical(source["world"]):
        raise RoutebookError("route journal uses different world")
    if len(verified["actions"]) != cursor:
        raise RoutebookError("route cursor does not match actions")
    state = initial_state(verified["world"])
    for index, action in enumerate(verified["actions"]):
        step = track["steps"][index]
        if not _holds(step["guard"], state) or action != step["action"]:
            raise RoutebookError("route guard or action mismatch")
        if action not in available_actions(verified["world"], state):
            raise RoutebookError("route action was not available")
        state = apply(verified["world"], state, action)
    if canonical(state) != canonical(verified["state"]):
        raise RoutebookError("route replay diverged")
    expected_status = "completed" if cursor == len(track["steps"]) and state["status"] == "won:" + track["ending"] else "playing"
    if cursor == len(track["steps"]) and expected_status != "completed":
        raise RoutebookError("route did not earn declared ending")
    if cursor < len(track["steps"]) and state["status"] != "playing":
        raise RoutebookError("route terminated before final step")
    if data["status"] != expected_status or data["head"] != _head(data):
        raise RoutebookError("route status or head mismatch")
    return {"source": source, "track": track, "cursor": cursor, "state": state,
            "status": expected_status, "head": data["head"], "journal_head": verified["head"]}


def step_route(session: dict, *, expected_head: str) -> dict:
    verified = verify_route(session)
    if not isinstance(expected_head, str) or expected_head != verified["head"]:
        raise RoutebookError("stale route session revision")
    if verified["status"] != "playing":
        raise RoutebookError("route already completed")
    step = verified["track"]["steps"][verified["cursor"]]
    if not _holds(step["guard"], verified["state"]):
        raise RoutebookError("route guard not satisfied")
    world = parse_world(verified["source"]["world"])
    if step["action"] not in available_actions(world, verified["state"]):
        raise RoutebookError("route action unavailable")
    result = deepcopy(session)
    result["journal"] = append_journal(result["journal"], step["action"], expected_head=result["journal"]["head"])
    result["cursor"] += 1
    if result["cursor"] == len(verified["track"]["steps"]):
        if result["journal"]["state"]["status"] != "won:" + verified["track"]["ending"]:
            raise RoutebookError("route did not earn its ending")
        result["status"] = "completed"
    result["head"] = _head(result)
    if len(canonical(result)) > MAX_SESSION:
        raise RoutebookError("route session byte budget exceeded")
    verify_route(result)
    return result


def run_route(source: dict | str | bytes, track_id: str) -> dict:
    session = open_route(source, track_id)
    count = len(_track(session["source"], track_id)["steps"])
    for _ in range(count):
        session = step_route(session, expected_head=session["head"])
    return session


def export_route(session: dict) -> dict:
    verified = verify_route(session)
    payload = {"schema": EXPORT_SCHEMA, "session": deepcopy(session),
               "gameplay": export_journal(session["journal"]),
               "source_sha256": digest(verified["source"])}
    if len(canonical(payload)) > MAX_SESSION:
        raise RoutebookError("route export too large")
    return {"payload": payload, "sha256": digest(payload)}


def verify_route_export(bundle: dict | str | bytes) -> dict:
    data = _document(bundle, MAX_SESSION)
    if set(data) != {"payload", "sha256"} or not isinstance(data["payload"], dict):
        raise RoutebookError("invalid route export envelope")
    if data["sha256"] != digest(data["payload"]):
        raise RoutebookError("route export digest mismatch")
    payload = data["payload"]
    if set(payload) != {"schema", "session", "gameplay", "source_sha256"} or payload["schema"] != EXPORT_SCHEMA:
        raise RoutebookError("invalid route export payload")
    verified = verify_route(payload["session"])
    if payload["source_sha256"] != digest(verified["source"]):
        raise RoutebookError("route export source mismatch")
    from .custody import verify_run
    gameplay = verify_run(payload["gameplay"])
    if canonical(gameplay["state"]) != canonical(verified["state"]):
        raise RoutebookError("route export state mismatch")
    if gameplay["actions"] != [entry["action"] for entry in payload["session"]["journal"]["entries"]]:
        raise RoutebookError("route export actions mismatch")
    return verified
