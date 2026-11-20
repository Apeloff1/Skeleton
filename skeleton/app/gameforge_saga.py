"""Generated multi-owner saga with explicit source-bound local gameplay gates.

The base expedition retains world, narrative, crafting and mission authority.
Each advanced objective additionally requires one recovered gameplay owner
to earn its authored outcome. Source receipts are never auto-applied.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_expedition import (
    _admit as admit_base, _replay as replay_base, build_expedition, play_expedition,
)
from skeleton.app.gameforge_saga_owners import (
    action_limit, admit_episode, candidate_actions, replay_episode, summarize,
)
from skeleton.app.original_quest_cli import _encode, _object, _require, _text
from skeleton.gameforge.errors import GameForgeError

REQUEST_SCHEMA = "skeleton.gameforge.saga.request.v1"
DESIGN_SCHEMA = "skeleton.gameforge.saga.design.v1"
SESSION_SCHEMA = "skeleton.gameforge.saga.session.v1"
MAX_EPISODES = 8
MAX_ACTIONS = 8192


def _admit(source: Any) -> tuple[dict, tuple, dict, dict]:
    data = _object(detached(source), {"schema", "expedition", "episodes"})
    _require(data["schema"] == REQUEST_SCHEMA, "unsupported saga schema")
    prepared = admit_base(data["expedition"])
    design = build_expedition(data["expedition"])
    known = {step["id"] for step in prepared[2]}
    rows = data["episodes"]
    _require(type(rows) is list and 1 <= len(rows) <= MAX_EPISODES, "invalid saga episode count")
    episodes = {}
    for row in rows:
        episode = admit_episode(row)
        objective = episode["objective"]
        _require(objective in known and objective not in episodes, "unknown or duplicate saga objective")
        episodes[objective] = episode
    return data, prepared, design, episodes


def _replay(data: dict, prepared: tuple, episodes: dict, events: Any, *, offer_actions: bool = True) -> dict:
    actions = detached(events)
    _require(type(actions) is list and len(actions) <= MAX_ACTIONS, "saga action ceiling exceeded")
    _, campaign, steps, _, _ = prepared
    location = campaign["world"]["start"]
    projected = []
    local = {oid: [] for oid in episodes}
    admitted: set[str] = set()
    resolved = 0
    reports = {}
    summaries = {}

    def report_for(oid: str) -> dict:
        if oid not in reports:
            reports[oid] = replay_episode(episodes[oid], local[oid])
            summaries[oid] = summarize(episodes[oid], reports[oid])
        return reports[oid]

    for event in actions:
        _require(resolved < len(steps), "saga already completed")
        _require(type(event) is dict, "invalid saga action")
        kind = event.get("type")
        step = steps[resolved]
        oid = step["id"]
        if kind == "episode":
            action = _object(event, {"type", "objective", "action"})
            _require(action["objective"] == oid and oid in episodes and location == step["location"],
                     "saga episode not at active objective region")
            if oid not in admitted:
                # The stronger outer resolve gate proves correct dialogue,
                # optional crafting mission completion and objective order.
                prior = replay_base(*prepared, projected)
                resolve = {"type": "resolve", "objective": oid, "npc": step["npc"]}
                _require(resolve in prior["legal_actions"], "base expedition gate not earned")
                admitted.add(oid)
            _require(type(action["action"]) is dict, "local owner action must be an object")
            local[oid].append(action["action"])
            _require(len(local[oid]) <= action_limit(episodes[oid]),
                     "local owner tick ceiling exceeded")
            reports.pop(oid, None)
            summaries.pop(oid, None)
            continue
        if kind == "move":
            action = _object(event, {"type", "to"})
            destination = _text(action["to"], 64)
            _require(destination in campaign["world"]["edges"][location], "saga travel not adjacent")
            location = destination
        elif kind == "resolve":
            action = _object(event, {"type", "objective", "npc"})
            _require(action["objective"] == oid and location == step["location"]
                     and action["npc"] == step["npc"], "saga resolution outside active region or objective")
            if oid in episodes:
                report_for(oid)
                _require(summaries[oid]["gate_satisfied"], "advanced episode outcome not earned")
            resolved += 1
        elif kind == "dialogue":
            _object(event, {"type", "npc", "choice"})
        elif kind == "harbor":
            _object(event, {"type", "objective", "action"})
        else:
            raise ValueError("unsupported saga event")
        projected.append(event)

    base = play_expedition(data["expedition"], projected)
    state = base["state"]
    _require(state["location"] == location and
             state["campaign"]["state"]["quest"]["state"]["resolutions"] == resolved,
             "saga and base expedition projections diverged")
    for oid in episodes:
        report_for(oid)
    choices = []
    blockers = []
    if state["status"] == "in_progress":
        step = steps[resolved]
        oid = step["id"]
        base_ready = False
        for action in state["legal_actions"]:
            if action["type"] == "resolve" and action["objective"] in episodes:
                base_ready = True
                if not summaries[action["objective"]]["gate_satisfied"]:
                    continue
            choices.append(action)
        if oid in episodes and not summaries[oid]["gate_satisfied"]:
            episode = episodes[oid]
            summary = summaries[oid]
            if summary["terminal"]:
                reason = "advanced_terminal_without_gate"
            elif location != step["location"]:
                reason = "travel_to_advanced_episode"
            elif not base_ready:
                reason = "base_expedition_gate_missing"
            else:
                reason = "advanced_episode_in_progress"
                if offer_actions:
                    choices.extend({"type": "episode", "objective": oid, "action": action}
                                   for action in candidate_actions(episode, reports[oid], summary))
            blockers.append({"objective": oid, "kind": episode["kind"],
                             "region": step["location"], "reason": reason})
    return {"base": base, "location": location, "status": state["status"],
            "earned_rewards": state["earned_rewards"], "episodes": summaries,
            "legal_actions": choices, "blockers": blockers}


def _design(data: dict, prepared: tuple, base: dict, episodes: dict) -> dict:
    witness = []
    for event in base["witness"]:
        if event["type"] == "resolve" and event["objective"] in episodes:
            oid = event["objective"]
            witness.extend({"type": "episode", "objective": oid, "action": action}
                           for action in episodes[oid]["witness"])
        witness.append(event)
    state = _replay(data, prepared, episodes, witness)
    _require(state["status"] == "completed" and all(
        ep["gate_satisfied"] for ep in state["episodes"].values())
        and state["earned_rewards"] == base["witness_state"]["earned_rewards"],
        "combined saga witness does not earn all canonical objectives")
    body = {"schema": DESIGN_SCHEMA, "source_digest": digest(data),
            "base_design_digest": base["design_digest"], "witness": witness,
            "witness_state": state, "native_qualified": False, "release_qualified": False}
    result = {**body, "design_digest": digest(body)}
    _encode({"request": data, "receipt": result})
    return result


def build_saga(source: Any) -> dict:
    return _design(*_admit(source))


def play_saga(source: Any, actions: Any) -> dict:
    data, prepared, base, episodes = _admit(source)
    design = _design(data, prepared, base, episodes)
    state = _replay(data, prepared, episodes, actions)
    body = {"schema": SESSION_SCHEMA, "source_digest": design["source_digest"],
            "design_digest": design["design_digest"], "actions": detached(actions),
            "state": state, "native_qualified": False, "release_qualified": False}
    result = {**body, "session_digest": digest(body)}
    _encode({"request": data, "receipt": result})
    return detached(result)


def verify_saga(source: Any, receipt: Any, *, session: bool = False) -> bool:
    try:
        expected = play_saga(source, receipt["actions"]) if session else build_saga(source)
        return _encode(receipt) == _encode(expected)
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def resume_saga(source: Any, previous: Any, additional: Any) -> dict:
    _encode({"request": source, "receipt": previous, "additional": additional})
    _require(verify_saga(source, previous, session=True), "saga checkpoint replay mismatch")
    _require(type(additional) is list and 1 <= len(additional) <= MAX_ACTIONS,
             "invalid saga append")
    return play_saga(source, previous["actions"] + additional)
