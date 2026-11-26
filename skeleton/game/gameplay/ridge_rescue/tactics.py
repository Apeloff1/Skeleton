"""Replay-verified field tactics: real engine previews, never invented outcomes.

A source-authored policy ranks available canonical actions by bounded one-turn
simulations. The advisory is deterministic but cannot guarantee victory: mobile
raiders, finite supplies and later player decisions can invalidate its estimate.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .custody import canonical, digest
from .engine import apply, available_actions, DIRECTIONS
from .guidance import route
from .journal import append_journal, open_journal, verify_journal, export_journal
from .routebook import _document
from .schema import World, parse_world, world_dict

SCHEMA = "ridge.rescue.tactics.v1"
MAX_POLICY_BYTES = 16_384
MAX_PREVIEW_ACTIONS = 128
MAX_AUTOPLAY = 256


class TacticsError(ValueError):
    pass


def parse_policy(value: dict | str | bytes) -> dict:
    data = _document(value, MAX_POLICY_BYTES)
    if set(data) != {"schema", "title", "objective", "risk", "prefer_crafting", "max_steps"}:
        raise TacticsError("invalid tactics policy fields")
    if data["schema"] != SCHEMA:
        raise TacticsError("unsupported tactics schema")
    title = data["title"]
    if not isinstance(title, str) or not 1 <= len(title) <= 96 or any(ord(c) < 32 for c in title):
        raise TacticsError("invalid tactics title")
    if data["objective"] not in ("protect", "salvage"):
        raise TacticsError("invalid tactics objective")
    if type(data["risk"]) is not int or not 0 <= data["risk"] <= 100:
        raise TacticsError("invalid tactics risk")
    if type(data["prefer_crafting"]) is not bool:
        raise TacticsError("invalid tactics crafting preference")
    if type(data["max_steps"]) is not int or not 1 <= data["max_steps"] <= MAX_AUTOPLAY:
        raise TacticsError("invalid tactics step budget")
    return deepcopy(data)


def _goal(world: World, state: dict, policy: dict) -> tuple[str, list[tuple[int, int]]]:
    waiting = [(ident, at) for ident, at in world.civilians if state["civilians"][ident] == "waiting"]
    if waiting:
        return "rescue", [at for _, at in waiting]
    if policy["objective"] == "protect" and not state["flags"]["beacon"]:
        inventory = state["inventory"]
        if inventory["signal"] > 0:
            return "signal", [world.shelter]
        if inventory["ore"] >= 2 and inventory["wood"] >= 1:
            return "craft", [tuple(state["position"])]
        wanted = []
        if inventory["ore"] < 2:
            wanted.append("ore")
        if inventory["wood"] < 1:
            wanted.append("wood")
        sources = [at for ident, kind, at, _ in world.resources
                   if kind in wanted and state["resources"][ident] > 0]
        if sources:
            return "supply", sources
    return "evacuate", [world.shelter]


def _distance(world: World, state: dict, targets: list[tuple[int, int]], adjacent: bool) -> int:
    start = tuple(state["position"])
    blocked = frozenset(tuple(v["at"]) for v in state["raiders"].values() if v["health"] > 0)
    blocked = blocked | frozenset(at for ident, at in world.civilians if state["civilians"][ident] == "waiting")
    candidates = []
    for target in targets:
        endpoints = [target]
        if adjacent:
            endpoints = [(target[0] + dx, target[1] + dy) for dx, dy in DIRECTIONS.values()]
            if abs(start[0] - target[0]) + abs(start[1] - target[1]) <= 1:
                return 0
        for endpoint in endpoints:
            path = route(world, start, endpoint, blocked)
            if path is not None:
                candidates.append(len(path))
    return min(candidates, default=world.width * world.height + 100)


def _score(world: World, before: dict, after: dict, action: dict, policy: dict) -> tuple[int, list[str]]:
    reasons = []
    if after["status"].startswith("lost:"):
        return -100_000, ["defeat in exact next-turn simulation"]
    if after["status"] == "won:" + policy["objective"]:
        return 100_000, ["earned requested ending"]
    if after["status"].startswith("won:"):
        return -10_000, ["wrong ending for selected objective"]
    score = -6
    health_loss = before["health"] - after["health"]
    score -= health_loss * (100 - policy["risk"] + 15)
    if health_loss:
        reasons.append("health risk: " + str(health_loss))
    stamina_gain = after["stamina"] - before["stamina"]
    score += stamina_gain * (5 if before["stamina"] <= 3 else 1)
    goal, targets = _goal(world, before, policy)
    if goal != "craft":
        prior = _distance(world, before, targets, goal in ("rescue", "supply"))
        next_distance = _distance(world, after, targets, goal in ("rescue", "supply"))
        progress = max(-50, min(50, prior - next_distance))
        score += 24 * progress
        if progress > 0:
            reasons.append("shortens verified static objective route")
    rescued = sum(value == "rescued" for value in after["civilians"].values()) - sum(
        value == "rescued" for value in before["civilians"].values())
    if rescued:
        score += 800 * rescued
        reasons.append("civilian actually rescued")
    if after["flags"]["beacon"] and not before["flags"]["beacon"]:
        score += 500
        reasons.append("earned beacon activated")
    if action["verb"] == "craft":
        if action["item"] == "signal" and policy["objective"] == "protect":
            score += 450
            reasons.append("signal crafted from finite supplies")
        elif policy["prefer_crafting"]:
            score += 30
    if action["verb"] == "gather":
        kind = next(kind for ident, kind, _, _ in world.resources if ident == action["target"])
        if goal == "supply" and kind in ("ore", "wood"):
            score += 180
            reasons.append("collected required signal material")
        else:
            score += 15
    if action["verb"] == "attack":
        enemy = action["target"]
        damage = before["raiders"][enemy]["health"] - after["raiders"][enemy]["health"]
        score += 12 * damage
        if after["raiders"][enemy]["health"] == 0:
            score += 110
            reasons.append("raider defeated by canonical combat")
    if action["verb"] == "rest":
        if before["stamina"] >= 7 and before["health"] == after["health"]:
            score -= 100
        elif before["stamina"] <= 2:
            score += 80
            reasons.append("recovering depleted stamina")
    if action["verb"] == "trade":
        score -= 15
    return score, reasons


def suggest(world: World, journal: dict, policy: dict | str | bytes) -> dict:
    rules = parse_policy(policy)
    try:
        checked = verify_journal(journal)
    except (ValueError, KeyError, TypeError) as exc:
        raise TacticsError("invalid or unreplayable tactics journal") from exc
    if canonical(world_dict(world)) != canonical(world_dict(checked["world"])):
        raise TacticsError("tactics world differs from journal")
    state = checked["state"]
    if state["status"] != "playing":
        return {"schema": "ridge.rescue.tactics.advice.v1", "status": state["status"],
                "journal_head": checked["head"], "policy_sha256": digest(rules),
                "guaranteed": False, "ranked": []}
    actions = available_actions(world, state)
    if len(actions) > MAX_PREVIEW_ACTIONS:
        raise TacticsError("too many legal actions to preview safely")
    ranked = []
    for action in actions:
        try:
            next_state = apply(world, state, action)
        except (ValueError, TypeError, KeyError) as exc:
            raise TacticsError("legal action failed canonical preview") from exc
        score, reasons = _score(world, state, next_state, action, rules)
        ranked.append({"action": deepcopy(action), "score": score,
                       "next_status": next_state["status"], "next_health": next_state["health"],
                       "next_stamina": next_state["stamina"], "reasons": reasons})
    ranked.sort(key=lambda x: (-x["score"], canonical(x["action"])))
    return {"schema": "ridge.rescue.tactics.advice.v1", "status": state["status"],
            "journal_head": checked["head"], "policy_sha256": digest(rules),
            "guaranteed": False, "ranked": ranked}


def advance(world: World, journal: dict, policy: dict | str | bytes, *, expected_head: str) -> dict:
    advice = suggest(world, journal, policy)
    if expected_head != advice["journal_head"]:
        raise TacticsError("stale tactics journal revision")
    if not advice["ranked"]:
        raise TacticsError("no legal tactics action")
    chosen = advice["ranked"][0]["action"]
    try:
        next_journal = append_journal(journal, chosen, expected_head=expected_head)
    except (ValueError, TypeError, KeyError) as exc:
        raise TacticsError("tactics action rejected by canonical journal") from exc
    if next_journal["state"]["status"] != advice["ranked"][0]["next_status"]:
        raise TacticsError("preview and committed turn diverged")
    return {"journal": next_journal, "action": chosen, "advice": advice}


def autoplay(world: World, policy: dict | str | bytes, journal: dict | None = None) -> dict:
    rules = parse_policy(policy)
    current = open_journal(world) if journal is None else deepcopy(journal)
    checked = verify_journal(current)
    if canonical(world_dict(checked["world"])) != canonical(world_dict(world)):
        raise TacticsError("autoplay world mismatch")
    turns = 0
    while current["state"]["status"] == "playing" and turns < rules["max_steps"]:
        result = advance(world, current, rules, expected_head=current["head"])
        current = result["journal"]
        turns += 1
    verified = verify_journal(current)
    return {"schema": "ridge.rescue.tactics.autoplay.v1",
            "policy_sha256": digest(rules), "steps_executed": turns,
            "status": verified["state"]["status"],
            "reached_step_budget": turns == rules["max_steps"] and verified["state"]["status"] == "playing",
            "guaranteed": False, "journal": current, "bundle": export_journal(current)}
