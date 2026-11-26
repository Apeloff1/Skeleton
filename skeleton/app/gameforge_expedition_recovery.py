"""Source-bound expedition completion planning and alternate outcome comparison."""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest
from skeleton.app.gameforge_campaign_assist import MAX_EXPANSIONS, plan_completion
from skeleton.app.gameforge_expedition import (
    MAX_ACTIONS, _admit, resume_expedition, verify_expedition,
)
from skeleton.app.gameforge_expedition_local_recovery import MAX_STATES, recover_local
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.gameforge.errors import GameForgeError

SCHEMA = "skeleton.gameforge.expedition.recovery.v1"
COMPARE_SCHEMA = "skeleton.gameforge.expedition.comparison.v1"


def plan_expedition(source: Any, checkpoint: Any, *, dialogue_budget: int = 1024,
                    local_budget: int = 1024) -> dict:
    """Compose outer narrative recovery with actual local inventory recovery.

    The two search budgets are distinct: dialogue expansions per outer
    plan, and retained local transition states per unfinished episode.
    """
    dialogue_budget = _integer(dialogue_budget, 1, MAX_EXPANSIONS)
    local_budget = _integer(local_budget, 1, MAX_STATES)
    _require(verify_expedition(source, checkpoint, session=True),
             "expedition checkpoint does not replay")
    data, _, _, _, episodes = _admit(source)
    state = checkpoint["state"]
    outer = plan_completion(data["campaign"], state["campaign"],
                            max_expansions=dialogue_budget)
    outer_status = outer["status"]
    additional = []
    local_results = {}
    blocker = None
    final = None
    status = outer_status
    if outer_status == "already_completed":
        _require(state["status"] == "completed" and
                 all(row["gate_satisfied"] for row in state["episodes"].values()),
                 "outer completion lacks episode evidence")
        final = checkpoint
    elif outer_status != "completion_witness":
        blocker = {"scope": "campaign", "detail": outer["blocker"]}
    else:
        for action in outer["additional"]:
            if action["type"] == "resolve" and action["objective"] in episodes:
                oid = action["objective"]
                ep = episodes[oid]
                prefix = [row["action"] for row in checkpoint["actions"]
                          if row["type"] == "harbor" and row["objective"] == oid]
                local = recover_local(ep["source"], prefix, ep["ending"],
                                      witness=ep["witness"], max_states=local_budget,
                                      mission_board=ep.get("mission_board"),
                                      required_missions=ep.get("required_missions"))
                local_results[oid] = local
                if local["status"] not in {"already_completed", "completion_witness"}:
                    status = "local_" + local["status"]
                    blocker = {"scope": "episode", "objective": oid,
                               "reason": local["status"]}
                    break
                additional.extend({"type": "harbor", "objective": oid, "action": row}
                                  for row in local["additional"])
            additional.append(action)
            if len(checkpoint["actions"]) + len(additional) > MAX_ACTIONS:
                status = "action_budget_exhausted"
                blocker = {"scope": "expedition", "reason": "combined action ceiling"}
                break
        if status == "completion_witness":
            final = resume_expedition(source, checkpoint, additional)
            _require(final["state"]["status"] == "completed" and
                     all(row["gate_satisfied"] for row in final["state"]["episodes"].values()),
                     "combined recovery is not a canonical completion")
        else:
            additional = []
    # Local receipts still explain attempted search, but the top-level
    # proposal is never a partial sequence described as a completion.
    body = {"schema": SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": checkpoint["session_digest"],
            "status": status, "blocker": blocker, "dialogue_budget": dialogue_budget,
            "local_budget_per_episode": local_budget,
            "outer_status": outer_status, "outer_expanded": outer["expanded"],
            "local_results": local_results, "additional": additional,
            "next_action": additional[0] if additional else None,
            "completion_digest": final["session_digest"] if final else None,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "recovery_digest": digest(body)}
    _encode({"request": source, "receipt": checkpoint, "recovery": result})
    return result


def verify_plan(source: Any, checkpoint: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(plan_expedition(
            source, checkpoint, dialogue_budget=submitted["dialogue_budget"],
            local_budget=submitted["local_budget_per_episode"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def compare_expeditions(source: Any, left: Any, right: Any, *,
                        dialogue_budget: int = 256, local_budget: int = 256) -> dict:
    """Compare earned episode state and actual global ledger divergence."""
    _require(verify_expedition(source, left, session=True)
             and verify_expedition(source, right, session=True), "both branches must replay")
    a, b = left["actions"], right["actions"]
    common = 0
    for first, second in zip(a, b):
        if first != second:
            break
        common += 1
    ls, rs = left["state"], right["state"]
    outcomes = {}
    for oid, ep in sorted(ls["episodes"].items()):
        old, new = ep["state"], rs["episodes"][oid]["state"]
        items = old["inventory"].keys() | new["inventory"].keys()
        outcomes[oid] = {
            "left_ending": old["ending"], "right_ending": new["ending"],
            "left_delivered": old["delivered"], "right_delivered": new["delivered"],
            "left_gate": ep["gate_satisfied"], "right_gate": rs["episodes"][oid]["gate_satisfied"],
            "tick_delta": new["tick"] - old["tick"], "coin_delta": new["coins"] - old["coins"],
            "reputation_delta": new["reputation"] - old["reputation"],
            "inventory_delta": {k: new["inventory"].get(k, 0) - old["inventory"].get(k, 0)
                                for k in sorted(items)},
        }

    for oid, row in outcomes.items():
        if "missions" in ls["episodes"][oid]:
            first, second = ls["episodes"][oid]["missions"], rs["episodes"][oid]["missions"]
            row["mission_outcomes"] = {"left_completed": first["completed"],
                                       "right_completed": second["completed"],
                                       "points_delta": second["points"] - first["points"]}

    def totals(rows: list) -> dict:
        result: dict[str, int] = {}
        for row in rows:
            result[row["kind"]] = result.get(row["kind"], 0) + row["amount"]
        return result

    lt, rt = totals(ls["earned_rewards"]), totals(rs["earned_rewards"])
    lp = plan_expedition(source, left, dialogue_budget=dialogue_budget, local_budget=local_budget)
    rp = plan_expedition(source, right, dialogue_budget=dialogue_budget, local_budget=local_budget)
    body = {"schema": COMPARE_SCHEMA, "source_digest": digest(source),
            "left_digest": left["session_digest"], "right_digest": right["session_digest"],
            "common_prefix": common,
            "left_first_divergence": a[common] if common < len(a) else None,
            "right_first_divergence": b[common] if common < len(b) else None,
            "left_status": ls["status"], "right_status": rs["status"],
            "episodes": outcomes,
            "reward_delta": {k: rt.get(k, 0) - lt.get(k, 0) for k in sorted(lt.keys() | rt.keys())},
            "left_recovery": {"status": lp["status"], "blocker": lp["blocker"]},
            "right_recovery": {"status": rp["status"], "blocker": rp["blocker"]},
            "dialogue_budget": dialogue_budget, "local_budget_per_episode": local_budget,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "comparison_digest": digest(body)}
    _encode(result)
    return result


def verify_comparison(source: Any, left: Any, right: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(compare_expeditions(
            source, left, right, dialogue_budget=submitted["dialogue_budget"],
            local_budget=submitted["local_budget_per_episode"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
