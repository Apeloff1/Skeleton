"""Source-bound player board, evidence and recovery for multi-owner sagas.

Recovery composes the existing outer expedition planner with independently
verified local witness continuations. It never claims that an unsuccessful
local continuation proves all alternative player outcomes impossible.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest
from skeleton.app.gameforge_expedition_board import expedition_board
from skeleton.app.gameforge_expedition_recovery import plan_expedition
from skeleton.app.gameforge_saga import MAX_ACTIONS, _admit, resume_saga, verify_saga
from skeleton.app.gameforge_saga_owners import replay_episode, summarize
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.game.gameplay.harbor_crafting import HarborError
from skeleton.gameforge.errors import GameForgeError

BOARD_SCHEMA = "skeleton.gameforge.saga.board.v1"
EVIDENCE_SCHEMA = "skeleton.gameforge.saga.episode.evidence.v1"
PLAN_SCHEMA = "skeleton.gameforge.saga.recovery.v1"
DIFF_SCHEMA = "skeleton.gameforge.saga.comparison.v1"


def _events(receipt: dict, objective: str) -> list:
    return [event["action"] for event in receipt["actions"]
            if event["type"] == "episode" and event["objective"] == objective]


def board(source: Any, receipt: Any) -> dict:
    _require(verify_saga(source, receipt, session=True), "saga checkpoint does not replay")
    state = receipt["state"]
    base = expedition_board(source["expedition"], state["base"])
    # Nested screens are descriptive; neither nested board can supply
    # authority to bypass the stronger saga-level action gate.
    base.pop("board_digest")
    base["legal_actions"] = state["legal_actions"]
    base["campaign_view"]["legal_actions"] = state["legal_actions"]
    body = {"schema": BOARD_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": receipt["session_digest"], "expedition_view": base,
            "advanced_episodes": state["episodes"], "blockers": state["blockers"],
            "legal_actions": state["legal_actions"], "status": state["status"],
            "native_qualified": False, "release_qualified": False}
    result = {**body, "board_digest": digest(body)}
    _encode(result)
    return result


def selected_action(source: Any, receipt: Any, expected_digest: str, index: int) -> dict:
    current = board(source, receipt)
    _require(type(expected_digest) is str and current["board_digest"] == expected_digest,
             "saga player board changed")
    choices = current["legal_actions"]
    _require(bool(choices), "saga has no legal actions")
    return choices[_integer(index, 0, len(choices) - 1)]


def turn(source: Any, receipt: Any, expected_digest: str, index: int) -> dict:
    action = selected_action(source, receipt, expected_digest, index)
    next_receipt = resume_saga(source, receipt, [action])
    result = {"action": action, "receipt": next_receipt, "board": board(source, next_receipt),
              "native_qualified": False, "release_qualified": False}
    _encode(result)
    return result


def episode_evidence(source: Any, receipt: Any, objective: str) -> dict:
    _require(verify_saga(source, receipt, session=True), "saga checkpoint does not replay")
    _, _, _, episodes = _admit(source)
    _require(type(objective) is str and objective in episodes, "unknown advanced episode")
    episode = episodes[objective]
    report = replay_episode(episode, _events(receipt, objective))
    summary = summarize(episode, report)
    _require(summary == receipt["state"]["episodes"][objective], "local owner evidence differs")
    body = {"schema": EVIDENCE_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": receipt["session_digest"], "objective": objective,
            "kind": episode["kind"], "summary": summary, "report": report,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "evidence_digest": digest(body)}
    _encode({"request": source, "receipt": receipt, "evidence": result})
    return result


def _continuation(episode: dict, prior: list, summary: dict) -> tuple[str, list]:
    if summary["gate_satisfied"]:
        return "already_earned", []
    if summary["terminal"]:
        return "terminal_without_gate", []
    witness = episode["witness"]
    candidates = []
    if witness[:len(prior)] == prior:
        candidates.append((len(prior), "verified_witness_suffix"))
    else:
        normalized = [action for action in prior if action.get("op") != "wait"]
        matches = [i for i in range(len(witness) + 1)
                   if [a for a in witness[:i] if a.get("op") != "wait"] == normalized]
        candidates.extend((i, "verified_wait_splice") for i in reversed(matches[-4:]))
    for index, policy in candidates:
        suffix = witness[index:]
        try:
            following = replay_episode(episode, prior + suffix)
        except HarborError:
            continue
        if summarize(episode, following)["gate_satisfied"]:
            return policy, suffix
    return "no_verified_local_continuation", []


def recover(source: Any, receipt: Any, *, dialogue_budget: int = 1024, local_budget: int = 1024) -> dict:
    _require(verify_saga(source, receipt, session=True), "saga checkpoint does not replay")
    _, _, _, episodes = _admit(source)
    state = receipt["state"]
    outer = plan_expedition(source["expedition"], state["base"],
                            dialogue_budget=dialogue_budget, local_budget=local_budget)
    status = outer["status"]
    additional = []
    details = {}
    blocker = None
    completion = None
    if status == "already_completed":
        _require(state["status"] == "completed" and
                 all(ep["gate_satisfied"] for ep in state["episodes"].values()), "saga state mismatch")
        completion = receipt
    elif status != "completion_witness":
        blocker = {"scope": "base_expedition", "detail": outer["blocker"]}
    else:
        for action in outer["additional"]:
            if action["type"] == "resolve" and action["objective"] in episodes:
                oid = action["objective"]
                policy, suffix = _continuation(episodes[oid], _events(receipt, oid),
                                                state["episodes"][oid])
                details[oid] = {"strategy": policy, "actions": len(suffix),
                                "report_digest": state["episodes"][oid]["report_digest"]}
                if policy in {"terminal_without_gate", "no_verified_local_continuation"}:
                    status = policy
                    blocker = {"scope": "advanced_episode", "objective": oid, "reason": policy}
                    break
                additional.extend({"type": "episode", "objective": oid, "action": a} for a in suffix)
            additional.append(action)
            if len(receipt["actions"]) + len(additional) > MAX_ACTIONS:
                status = "action_budget_exhausted"
                blocker = {"scope": "saga", "reason": "combined action ceiling"}
                break
        if status == "completion_witness":
            completion = resume_saga(source, receipt, additional)
            _require(completion["state"]["status"] == "completed"
                     and all(ep["gate_satisfied"] for ep in completion["state"]["episodes"].values()),
                     "combined recovery did not earn all objectives")
        else:
            additional = []
    body = {"schema": PLAN_SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": receipt["session_digest"], "status": status,
            "dialogue_budget": dialogue_budget, "local_budget": local_budget,
            "advanced_strategies": details, "blocker": blocker,
            "additional": additional, "next_action": additional[0] if additional else None,
            "completion_digest": completion["session_digest"] if completion else None,
            "native_qualified": False, "release_qualified": False}
    output = {**body, "recovery_digest": digest(body)}
    _encode({"request": source, "receipt": receipt, "recovery": output})
    return output


def compare(source: Any, left: Any, right: Any) -> dict:
    _require(verify_saga(source, left, session=True) and verify_saga(source, right, session=True),
             "both saga histories must replay")
    a, b = left["actions"], right["actions"]
    common = 0
    for first, second in zip(a, b):
        if first != second:
            break
        common += 1
    ls, rs = left["state"], right["state"]
    outcomes = {}
    for oid, old in sorted(ls["episodes"].items()):
        new = rs["episodes"][oid]
        row = {"kind": old["kind"], "left_gate": old["gate_satisfied"],
               "right_gate": new["gate_satisfied"], "left_terminal": old["terminal"],
               "right_terminal": new["terminal"], "tick_delta": new["state"]["tick"] - old["state"]["tick"]}
        if old["kind"] == "survey_expedition":
            row.update({"left_ending": old["state"]["ending"], "right_ending": new["state"]["ending"],
                        "score_delta": new["score"] - old["score"], "energy_delta": new["energy"] - old["energy"],
                        "trust_delta": new["trust"] - old["trust"], "left_flags": old["flags"],
                        "right_flags": new["flags"]})
        elif old["kind"] == "convoy_league":
            row.update({key + "_delta": new[key] - old[key]
                        for key in ("score", "points", "rounds_played")})
            row.update({"left_earned": old["earned"], "right_earned": new["earned"],
                        "left_championship": old["championship"], "right_championship": new["championship"]})
        else:
            row.update({key + "_delta": new[key] - old[key]
                        for key in ("hull", "waypoint", "bounty", "points", "credits", "reputation")})
            row.update({"left_tokens": old["tokens"], "right_tokens": new["tokens"]})
        outcomes[oid] = row

    def totals(rewards: list) -> dict:
        result: dict[str, int] = {}
        for reward in rewards:
            result[reward["kind"]] = result.get(reward["kind"], 0) + reward["amount"]
        return result

    lt, rt = totals(ls["earned_rewards"]), totals(rs["earned_rewards"])
    body = {"schema": DIFF_SCHEMA, "source_digest": digest(source),
            "left_digest": left["session_digest"], "right_digest": right["session_digest"],
            "common_prefix": common, "left_status": ls["status"], "right_status": rs["status"],
            "left_first_divergence": a[common] if common < len(a) else None,
            "right_first_divergence": b[common] if common < len(b) else None,
            "advanced_outcomes": outcomes,
            "reward_delta": {k: rt.get(k, 0) - lt.get(k, 0) for k in sorted(lt.keys() | rt.keys())},
            "native_qualified": False, "release_qualified": False}
    result = {**body, "comparison_digest": digest(body)}
    _encode(result)
    return result


def verify_derived(source: Any, receipt: Any, submitted: Any, *, kind: str, other: Any = None) -> bool:
    try:
        if kind == "board":
            expected = board(source, receipt)
        elif kind == "evidence":
            expected = episode_evidence(source, receipt, submitted["objective"])
        elif kind == "recovery":
            expected = recover(source, receipt, dialogue_budget=submitted["dialogue_budget"],
                               local_budget=submitted["local_budget"])
        elif kind == "comparison":
            expected = compare(source, receipt, other)
        else:
            return False
        return _encode(expected) == _encode(submitted)
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
