"""Bounded exact-history recovery for fixed advanced saga owners.

Never collapse two histories according to an incomplete state projection.
Even histories with equal inventory/location may have distinct survey,
weather, contract or quest evidence. Every accepted transition is built
and summarized by its original gameplay owner.
"""
from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_saga_owners import (
    action_limit, raw_candidates, replay_episode, summarize, MAX_CANDIDATES,
)
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.game.gameplay.harbor_crafting import HarborError

MAX_STATES = 128
MAX_ATTEMPTS = 512
SCHEMA = "skeleton.gameforge.saga.advanced_recovery.v1"


def _priority(summary: dict, depth: int) -> tuple:
    # Ordering is only a heuristic, not an optimality guarantee. All
    # successful paths must pass full original-owner replay.
    if summary["kind"] == "survey_expedition":
        return (not summary["gate_satisfied"], len(summary["required_sites_remaining"]),
                not summary["delivery_permit"], not summary["state"]["delivered"],
                -summary["score"], depth)
    if summary["kind"] == "convoy_league":
        return (not summary["gate_satisfied"], len(summary["remaining"]),
                -summary["score"], -summary["rounds_played"], -summary["waypoint"], depth)
    return (not summary["gate_satisfied"], len(summary["required_contracts_remaining"]),
            -summary["points"], -summary["bounty"], -summary["waypoint"], depth)


def search(episode: dict, prior: list, *, max_states: int = 32, max_attempts: int = 128) -> dict:
    """Search a finite tree of actual actions, with strict global attempt limits.

    Nodes retain only suffix actions and compact ordering keys, not full
    replay reports. Each expansion reconstructs and verifies its history.
    A rejected action consumes an attempt just like an accepted transition.
    """
    max_states = _integer(max_states, 1, MAX_STATES)
    max_attempts = _integer(max_attempts, 1, MAX_ATTEMPTS)
    _encode({"episode": episode, "prior": prior})
    prior = detached(prior)
    initial = replay_episode(episode, prior)
    first = summarize(episode, initial)
    serial = count()
    queue = [(_priority(first, 0), next(serial), [])]
    states = 1
    attempts = 0
    expanded = 0
    truncated = False
    completion = None
    suffix = []
    status = "unreachable_within_owner_actions"
    if first["gate_satisfied"]:
        status = "already_earned"
        completion = first["report_digest"]
    elif first["terminal"]:
        status = "terminal_without_gate"
    else:
        while queue:
            _, _, tail = heappop(queue)
            report = replay_episode(episode, prior + tail)
            current = summarize(episode, report)
            expanded += 1
            if current["gate_satisfied"]:
                suffix = tail
                completion = current["report_digest"]
                status = "completion_witness"
                break
            if current["terminal"] or len(prior) + len(tail) >= action_limit(episode):
                continue
            candidates = raw_candidates(episode, report, current)
            _require(len(candidates) <= MAX_CANDIDATES, "advanced action enumeration ceiling exceeded")
            for action in candidates:
                if attempts >= max_attempts:
                    truncated = True
                    break
                attempts += 1
                proposed = tail + [action]
                try:
                    result = replay_episode(episode, prior + proposed)
                    state = summarize(episode, result)
                except HarborError:
                    continue
                if state["gate_satisfied"]:
                    suffix = proposed
                    completion = state["report_digest"]
                    status = "completion_witness"
                    break
                if state["terminal"]:
                    continue
                if states >= max_states:
                    truncated = True
                    continue
                states += 1
                heappush(queue, (_priority(state, len(proposed)), next(serial), proposed))
            if completion is not None:
                break
        if completion is None and truncated:
            status = "budget_exhausted"
    if status == "completion_witness":
        verified = summarize(episode, replay_episode(episode, prior + suffix))
        _require(verified["gate_satisfied"] and verified["report_digest"] == completion,
                 "advanced recovery did not independently replay")
    body = {"schema": SCHEMA, "objective": episode["objective"],
            "source_digest": digest(episode), "checkpoint_report_digest": first["report_digest"],
            "status": status, "additional": suffix, "completion_report_digest": completion,
            "state_budget": max_states, "attempt_budget": max_attempts,
            "retained_states": states, "expanded": expanded, "attempts": attempts,
            "native_qualified": False, "release_qualified": False}
    output = {**body, "search_digest": digest(body)}
    _encode(output)
    return output
