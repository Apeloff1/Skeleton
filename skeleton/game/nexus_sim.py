"""NEXUS-EXTRACT headless sim. Rooms, heat, stalker, extract. No GUI. No SSE."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from skeleton.game.ai_policy import run_policy
from skeleton.game.catalog_data import pack as catalog_pack
from skeleton.game.extract_loop import step as heat_step
from skeleton.game.mechanics import AIBehaviorSpec
from skeleton.game.token_clock import TOKEN_PERIOD
from skeleton.game.world_graph import place, walk


MAX_TICKS = 96
VERBS = ("move", "heat", "sleep", "extract", "craft", "bait", "wait")


class NexusSimError(ValueError):
    """Nexus sim contract violation."""


def _dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _blank(start: str) -> dict[str, Any]:
    return {
        "room": start,
        "heat": 0,
        "scrap": 0,
        "parts": 0,
        "sleep": 0,
        "tokens": 0,
        "extracted": 0,
        "crafted": 0,
        "baited": 0,
        "hp": 40,
    }


def _script(path: list[str], ticks: int) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for _ in range(3):
        steps.append({"verb": "heat"})
    for room in path[1:]:
        steps.append({"verb": "move", "to": room})
        if room.startswith("r"):
            steps.append({"verb": "heat"})
    steps.append({"verb": "craft"})
    steps.append({"verb": "bait"})
    steps.append({"verb": "extract"})
    steps.append({"verb": "sleep"})
    while len(steps) < ticks:
        steps.append({"verb": "wait"})
    return steps[:ticks]


def apply(state: dict[str, Any], raw: Mapping[str, Any], *, tick: int, extract_room: str) -> dict[str, Any]:
    verb = str(raw.get("verb") or "").strip().lower()
    if verb not in VERBS:
        raise NexusSimError(f"unknown nexus verb: {verb}")
    nxt = dict(state)
    if verb == "move":
        dest = str(raw.get("to") or "")
        if not dest:
            raise NexusSimError("move requires to")
        nxt["room"] = dest
        nxt["heat"] = min(100, int(nxt["heat"]) + 1)
    elif verb in {"heat", "sleep", "extract"}:
        if verb == "extract" and nxt["room"] != extract_room:
            raise NexusSimError("extract only at extract room")
        core = heat_step(
            {"heat": int(nxt["heat"]), "scrap": int(nxt["scrap"]), "sleep": int(nxt["sleep"])},
            verb,
        )
        nxt["heat"] = core["heat"]
        nxt["scrap"] = core["scrap"]
        nxt["sleep"] = core["sleep"]
        if verb == "extract":
            nxt["extracted"] = int(nxt["extracted"]) + 1
    elif verb == "craft":
        if int(nxt["scrap"]) < 1:
            raise NexusSimError("craft requires scrap")
        nxt["scrap"] = int(nxt["scrap"]) - 1
        nxt["parts"] = int(nxt["parts"]) + 1
        nxt["crafted"] = int(nxt["crafted"]) + 1
    elif verb == "bait":
        nxt["baited"] = int(nxt["baited"]) + 1
        nxt["heat"] = max(0, int(nxt["heat"]) - 3)
    if tick % TOKEN_PERIOD == TOKEN_PERIOD - 1:
        nxt["tokens"] = int(nxt["tokens"]) + 1
    return nxt


def simulate(*, seed: int = 8847291, ticks: int = 32) -> dict[str, Any]:
    if ticks < 8 or ticks > MAX_TICKS:
        raise NexusSimError("ticks out of range")
    graph = place(seed=int(seed), rooms=5)
    walked = walk(graph)
    extract_room = next(node["id"] for node in graph["nodes"] if node["kind"] == "extract")
    state = _blank("r0")
    frames = [dict(state)]
    script = _script(list(walked["path"]), ticks)
    for raw in script:
        try:
            state = apply(state, raw, tick=len(frames) - 1, extract_room=extract_room)
        except NexusSimError as exc:
            if "extract requires heat" in str(exc) or "extract only" in str(exc):
                state = apply(state, {"verb": "heat"}, tick=len(frames) - 1, extract_room=extract_room)
            elif "craft requires scrap" in str(exc):
                state = apply(state, {"verb": "heat"}, tick=len(frames) - 1, extract_room=extract_room)
            else:
                raise
        frames.append(dict(state))
    ai = run_policy(
        AIBehaviorSpec(entity_type="stalker", behaviors=("patrol", "chase"), aggression_level=0.7, intelligence_level=0.4),
        seed=int(seed),
        ticks=min(8, ticks),
    )
    catalogs = catalog_pack(int(seed))
    body: dict[str, Any] = {
        "kind": "nexus_sim",
        "seed": int(seed),
        "ticks": ticks,
        "path": walked["path"],
        "extract_room": extract_room,
        "final": state,
        "frames": len(frames),
        "extracted": int(state["extracted"]),
        "tokens": int(state["tokens"]),
        "every_frame": False,
        "ai_frames": len(ai),
        "catalog_n": catalogs["n"],
        "world_extract": walked["extract_count"],
        "passed": int(state["extracted"]) >= 1 and walked["passed"],
        "sota_ready": False,
        "stored_prose": 0,
    }
    body["digest"] = hashlib.sha256(_dumps({k: v for k, v in body.items() if k != "digest"}).encode("utf-8")).hexdigest()
    body["ok"] = True
    return body
