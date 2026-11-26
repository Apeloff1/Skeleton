"""Join the recovered Lantern Quay playable engine to the generated campaign.

A harbor episode gates a single generated objective. The player must earn
the specified ending through actual collision, resource, crafting, trade
and delivery actions. Campaign and harbor engines remain authoritative.
No portal can inject rewards, teleport or rewrite the original ledger.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import (
    _admit as admit_campaign, _gate_open, build_campaign, detached, digest,
    play_campaign, verify_session as verify_campaign_session,
)
from skeleton.app.gameforge_quest_bridge import _steps
from skeleton.app.original_quest_cli import _encode, _object, _require, _strings, _text
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_missions import (
    mission_report, validate_board, verify_mission_report,
)
from skeleton.gameforge.errors import GameForgeError

REQUEST_SCHEMA = "skeleton.gameforge.expedition.request.v1"
DESIGN_SCHEMA = "skeleton.gameforge.expedition.design.v1"
SESSION_SCHEMA = "skeleton.gameforge.expedition.session.v1"
MAX_EPISODES = 8
MAX_EPISODE_TICKS = 256
MAX_ACTIONS = 8192
ENDINGS = frozenset({"beacon", "safe_harbor"})


def _admit(source: Any) -> tuple[dict, dict, list, dict, dict]:
    data = _object(detached(source), {"schema", "campaign", "episodes"})
    _require(data["schema"] == REQUEST_SCHEMA, "unsupported expedition schema")
    base, _, gates = admit_campaign(data["campaign"])
    campaign = build_campaign(data["campaign"])
    steps = _steps(base["quest_receipt"]["artifact"])
    by_id = {step["id"]: step for step in steps}
    raw = data["episodes"]
    _require(type(raw) is list and 1 <= len(raw) <= MAX_EPISODES, "invalid episode count")
    episodes = {}
    for row in raw:
        entry = _object(row, {"objective", "source", "required_ending", "witness"},
                        {"mission_board", "required_missions"})
        objective = _text(entry["objective"], 128)
        _require(objective in by_id and objective not in episodes, "unknown or duplicate episode objective")
        world = harbor.validate_source(entry["source"])
        _require(world["max_ticks"] <= MAX_EPISODE_TICKS, "episode tick ceiling exceeded")
        ending = _text(entry["required_ending"], 32)
        _require(ending in ENDINGS, "unknown harbor ending")
        witness = entry["witness"]
        _require(type(witness) is list and 1 <= len(witness) <= world["max_ticks"],
                 "episode witness exceeds tick budget")
        bundle = harbor.export_bundle(world, witness, require_win=True)
        verified = harbor.verify_bundle(bundle, require_win=True)
        _require(verified["ending"] == ending and verified["delivered"],
                 "episode witness did not earn its required ending")
        episode = {"source": world, "ending": ending,
                   "witness": [harbor.normalize_action(a) for a in witness]}
        _require(("mission_board" in entry) == ("required_missions" in entry),
                 "mission board and required missions must be supplied together")
        if "mission_board" in entry:
            board = validate_board(entry["mission_board"], world)
            required = sorted(_strings(entry["required_missions"], 12, 48, nonempty=True))
            _require(set(required) <= {mission["id"] for mission in board["missions"]},
                     "unknown required mission")
            episode.update({"mission_board": board, "required_missions": required})
            _require(_mission_summary(episode, bundle)["satisfied"],
                     "episode witness did not earn every required mission")
        episodes[objective] = episode
    return data, campaign, steps, gates, episodes


def _mission_summary(episode: dict, bundle: dict) -> dict:
    report = mission_report(bundle, episode["mission_board"])
    earned = verify_mission_report(report)
    required = episode["required_missions"]
    latest = report["journal"][-1]["progress"] if report["journal"] else {
        row["id"]: [0] * len(row["objectives"]) for row in episode["mission_board"]["missions"]
    }
    return {"board_digest": report["board_digest"], "report_digest": report["report_digest"],
            "required": required, "completed": earned["completed"], "points": earned["points"],
            "progress": latest, "satisfied": set(required) <= set(earned["completed"])}


def _open_gate(objective: str, episodes: dict, states: dict, missions: dict) -> bool:
    return objective not in episodes or (
        states[objective]["ending"] == episodes[objective]["ending"]
        and states[objective]["delivered"] is True
        and ("mission_board" not in episodes[objective] or missions[objective]["satisfied"])
    )


def _available_harbor(world: dict, state: dict) -> list[dict]:
    if state["ending"] is not None or state["tick"] >= world["max_ticks"]:
        return []
    actions = [{"op": "move", "direction": direction} for direction in sorted(harbor.DIRECTIONS)]
    actions += [{"op": "gather"}, {"op": "deliver"}, {"op": "wait"}]
    actions += [{"op": "craft", "recipe": row["id"]} for row in world["recipes"]]
    actions += [{"op": "trade", "item": item} for item in sorted(world["npc"]["stock"])]
    actions += [{"op": "choose", "choice": choice} for choice in ("signal", "shelter")]
    result = []
    for action in actions:
        try:
            harbor.step(world, state, action)
        except harbor.HarborError:
            continue
        result.append(action)
    return result


def _replay(data: dict, campaign: dict, steps: list, gates: dict, episodes: dict,
            actions: Any) -> dict:
    actions = detached(actions)
    _require(type(actions) is list and len(actions) <= MAX_ACTIONS, "expedition action ceiling exceeded")
    world = campaign["world"]
    loc = world["start"]
    resolved = 0
    projected = []
    authorized: set[str] = set()
    missions: dict[str, dict] = {}
    # Dialogue authorization is replayed at every portal admission; otherwise
    # its original owner checks the complete projected ledger at the end.
    episode_actions: dict[str, list] = {key: [] for key in episodes}
    states = {key: harbor.initial_state(row["source"]) for key, row in episodes.items()}
    for event in actions:
        _require(resolved < len(steps), "expedition already completed")
        _require(type(event) is dict, "invalid expedition action")
        kind = event.get("type")
        current = steps[resolved]
        oid = current["id"]
        if kind == "harbor":
            item = _object(event, {"type", "objective", "action"})
            _require(item["objective"] == oid and oid in episodes and loc == current["location"],
                     "episode is not the active local objective")
            if oid in gates and oid not in authorized:
                prior = play_campaign(data["campaign"], projected)
                _require(_gate_open(gates[oid], prior["state"]["dialogues"]),
                         "episode requires the authored dialogue grant first")
                # A canonically ended conversation cannot be reopened or revoke its grant.
                authorized.add(oid)
            normalized = harbor.normalize_action(item["action"])
            states[oid] = harbor.step(episodes[oid]["source"], states[oid], normalized)
            episode_actions[oid].append(normalized)
            continue
        if kind == "move":
            item = _object(event, {"type", "to"})
            destination = _text(item["to"], 64)
            _require(destination in world["edges"][loc], "expedition travel not adjacent")
            loc = destination
        elif kind == "resolve":
            item = _object(event, {"type", "objective", "npc"})
            _require(item["objective"] == oid and loc == current["location"],
                     "expedition objective out of order or outside region")
            if oid in episodes and "mission_board" in episodes[oid]:
                episode = episodes[oid]
                missions[oid] = _mission_summary(episode, harbor.export_bundle(
                    episode["source"], episode_actions[oid]))
            _require(_open_gate(oid, episodes, states, missions), "required harbor ending or missions not earned")
            resolved += 1
        elif kind == "dialogue":
            _object(event, {"type", "npc", "choice"})
        else:
            raise ValueError("unknown expedition action")
        projected.append(event)

    receipt = play_campaign(data["campaign"], projected)
    _require(verify_campaign_session(data["campaign"], receipt), "canonical campaign replay mismatch")
    state = receipt["state"]
    _require(state["location"] == loc and
             state["quest"]["state"]["resolutions"] == resolved, "expedition projection mismatch")
    summaries = {}
    for oid, episode in episodes.items():
        bundle = harbor.export_bundle(episode["source"], episode_actions[oid])
        verified = harbor.verify_bundle(bundle)
        _require(verified == states[oid], "harbor incremental and independent replay disagree")
        if "mission_board" in episode:
            missions[oid] = _mission_summary(episode, bundle)
        summaries[oid] = {
            "source_digest": bundle["source_digest"], "bundle_digest": bundle["bundle_digest"],
            "event_count": len(bundle["events"]), "state": verified,
            "required_ending": episode["ending"], "gate_satisfied": _open_gate(oid, episodes, states, missions),
        }

        if oid in missions:
            summaries[oid]["missions"] = missions[oid]

    legal = []
    blockers = []
    if resolved < len(steps):
        current = steps[resolved]
        oid = current["id"]
        for action in state["legal_actions"]:
            if action["type"] == "resolve" and not _open_gate(action["objective"], episodes, states, missions):
                continue
            legal.append(action)
        if oid in episodes:
            episode = episodes[oid]
            local = current["location"] == loc
            dialogue_ready = oid not in gates or _gate_open(gates[oid], state["dialogues"])
            if local and dialogue_ready:
                legal.extend({"type": "harbor", "objective": oid, "action": action}
                             for action in _available_harbor(episode["source"], states[oid]))
            if not _open_gate(oid, episodes, states, missions):
                harbor_state = states[oid]
                if harbor_state["ending"] == episode["ending"] and oid in missions and not missions[oid]["satisfied"]:
                    reason = "required_missions_missing"
                elif harbor_state["ending"] is not None:
                    reason = "alternate_ending"
                elif harbor_state["tick"] >= episode["source"]["max_ticks"]:
                    reason = "tick_budget_exhausted"
                elif oid in missions and any(
                    mission["id"] in episode["required_missions"]
                    and mission["id"] not in missions[oid]["completed"]
                    and harbor_state["tick"] >= mission["deadline"]
                    for mission in episode["mission_board"]["missions"]
                ):
                    reason = "required_mission_deadline_missed"
                elif not dialogue_ready:
                    reason = "dialogue_grant_missing"
                elif not local:
                    reason = "travel_to_episode"
                else:
                    reason = "episode_in_progress"
                blockers.append({"objective": oid, "reason": reason, "region": current["location"],
                                 "required_ending": episode["ending"]})
    return {"campaign": receipt, "location": loc, "status": state["status"],
            "earned_rewards": state["earned_rewards"], "episodes": summaries,
            "legal_actions": legal, "blockers": blockers}


def _design(data: dict, campaign: dict, steps: list, gates: dict, episodes: dict) -> dict:
    actions = []
    for event in campaign["witness"]:
        if event["type"] == "resolve" and event["objective"] in episodes:
            oid = event["objective"]
            actions.extend({"type": "harbor", "objective": oid, "action": action}
                           for action in episodes[oid]["witness"])
        actions.append(event)
    _require(len(actions) <= MAX_ACTIONS, "combined witness exceeds action ceiling")
    result = _replay(data, campaign, steps, gates, episodes, actions)
    _require(result["status"] == "completed"
             and result["earned_rewards"] == campaign["witness_state"]["earned_rewards"]
             and all(ep["gate_satisfied"] for ep in result["episodes"].values()),
             "expedition witness did not complete all canonical games")
    body = {"schema": DESIGN_SCHEMA, "source_digest": digest(data),
            "campaign_design_digest": campaign["design_digest"], "witness": actions,
            "witness_state": result, "native_qualified": False, "release_qualified": False}
    receipt = {**body, "design_digest": digest(body)}
    _encode({"request": data, "receipt": receipt})
    return receipt


def build_expedition(source: Any) -> dict:
    return _design(*_admit(source))


def play_expedition(source: Any, actions: Any) -> dict:
    data, campaign, steps, gates, episodes = _admit(source)
    design = _design(data, campaign, steps, gates, episodes)
    state = _replay(data, campaign, steps, gates, episodes, actions)
    body = {"schema": SESSION_SCHEMA, "source_digest": design["source_digest"],
            "design_digest": design["design_digest"], "actions": detached(actions),
            "state": state, "native_qualified": False, "release_qualified": False}
    result = {**body, "session_digest": digest(body)}
    _encode({"request": data, "receipt": result})
    return detached(result)


def verify_expedition(source: Any, receipt: Any, *, session: bool = False) -> bool:
    try:
        expected = play_expedition(source, receipt["actions"]) if session else build_expedition(source)
        return _encode(receipt) == _encode(expected)
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def resume_expedition(source: Any, previous: Any, additional: Any) -> dict:
    _encode({"request": source, "receipt": previous, "additional": additional})
    _require(verify_expedition(source, previous, session=True), "expedition checkpoint replay mismatch")
    _require(type(additional) is list and 1 <= len(additional) <= MAX_ACTIONS,
             "additional actions must be bounded and nonempty")
    return play_expedition(source, previous["actions"] + additional)
