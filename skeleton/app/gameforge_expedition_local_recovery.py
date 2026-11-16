"""Resume real local harbor gameplay from a verified event ledger.

The preexisting route and crafting planner supplies a fast candidate.
A bounded best-first fallback explores actual canonical transitions when
the greedy recipe choice cannot finish an altered player state.
Neither proposal is trusted until complete independent replay.
"""
from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_expedition import _available_harbor
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_planner import _CampaignPlanner, _distance

SCHEMA = "skeleton.gameforge.expedition.local_recovery.v1"
MAX_STATES = 4096


def _key(world: dict, state: dict) -> tuple:
    return (tuple(state["pos"]), tuple(state["npc_pos"]),
            state["tick"] % len(world["npc"]["route"]),
            tuple(sorted(state["inventory"].items())),
            tuple(sorted(state["stock"].items())),
            tuple(sorted(state["npc_stock"].items())),
            state["coins"], state["delivered"], state["ending"], state["reputation"])


def _score(world: dict, state: dict) -> tuple:
    """Heuristic ordering only, deliberately not an optimality claim."""
    missing = sum(max(0, qty - state["inventory"].get(item, 0))
                  for item, qty in world["delivery"].items())
    if state["delivered"]:
        missing = 0
    return (0 if state["ending"] else 1, 0 if state["delivered"] else 1,
            missing, state["tick"] + _distance(state["pos"], world["dock"]))


def _valid_suffix(world: dict, prefix: list, suffix: list, required: str) -> dict:
    bundle = harbor.export_bundle(world, [*prefix, *suffix], require_win=True)
    state = harbor.verify_bundle(bundle, require_win=True)
    _require(state["ending"] == required and state["delivered"], "wrong local completion outcome")
    return bundle


def _greedy(world: dict, initial: dict, prefix: list, choice: str, required: str) -> list | None:
    planner = _CampaignPlanner(world)
    planner.state = detached(initial)
    try:
        if not planner.state["delivered"]:
            for item, amount in sorted(world["delivery"].items()):
                planner.ensure(item, amount)
            planner.navigate(lambda s: _distance(s["pos"], world["dock"]) == 1)
            planner.emit({"op": "deliver"})
        else:
            planner.navigate(lambda s: _distance(s["pos"], world["dock"]) == 1)
        planner.emit({"op": "choose", "choice": choice})
        _valid_suffix(world, prefix, planner.actions, required)
        return planner.actions
    except (ValueError, RecursionError):
        return None


def _search(world: dict, initial: dict, required: str, budget: int) -> tuple[str, list, int]:
    serial = count()
    # Parent links are immutable; a later discovery can dominate a previous
    # key without rewriting the earlier path used by descendants.
    nodes = [(initial, None, None)]
    frontier = [(_score(world, initial), next(serial), 0)]
    best = {_key(world, initial): initial["tick"]}
    expanded = 0
    truncated = False
    while frontier:
        if expanded >= budget:
            return "budget_exhausted", [], expanded
        _, _, index = heappop(frontier)
        state, parent, action = nodes[index]
        if state["tick"] != best[_key(world, state)]:
            continue
        expanded += 1
        if state["ending"] == required:
            path = []
            while parent is not None:
                path.append(action)
                _, parent, action = nodes[parent]
            return "completion_witness", list(reversed(path)), expanded
        if state["ending"] is not None or state["tick"] >= world["max_ticks"]:
            continue
        for action in _available_harbor(world, state):
            after = harbor.step(world, state, action)
            if after["ending"] is not None and after["ending"] != required:
                continue
            key = _key(world, after)
            if key in best and best[key] <= after["tick"]:
                continue
            if len(nodes) >= budget:
                truncated = True
                continue
            best[key] = after["tick"]
            nodes.append((after, index, action))
            heappush(frontier, (_score(world, after), next(serial), len(nodes) - 1))
    return ("budget_exhausted" if truncated else "unreachable"), [], expanded


def recover_local(world: Any, prefix: Any, required_ending: str,
                  *, witness: Any | None = None, max_states: int = 1024) -> dict:
    """Return a verified legal suffix, exhaustion, or narrowly proven blocker."""
    _encode({"world": world, "prefix": prefix, "witness": witness})
    budget = _integer(max_states, 1, MAX_STATES)
    _require(type(required_ending) is str and required_ending in {"beacon", "safe_harbor"},
             "unsupported local ending")
    authored = harbor.validate_source(world)
    _require(type(prefix) is list, "local prefix must be an action ledger")
    normalized = [harbor.normalize_action(a) for a in prefix]
    prior = harbor.export_bundle(authored, normalized)
    initial = harbor.verify_bundle(prior)
    choice = "signal" if required_ending == "beacon" else "shelter"
    strategy = None
    expanded = 0
    suffix = []
    final = None
    if initial["ending"] == required_ending:
        status = "already_completed"
        final = prior
    elif initial["ending"] is not None:
        status = "alternate_ending"
    elif initial["tick"] >= authored["max_ticks"]:
        status = "tick_budget_exhausted"
    else:
        proposed = None
        if witness is not None:
            _require(type(witness) is list, "local witness must be a ledger")
            known = [harbor.normalize_action(a) for a in witness]
            if known[:len(normalized)] == normalized:
                try:
                    _valid_suffix(authored, normalized, known[len(normalized):], required_ending)
                except ValueError:
                    pass
                else:
                    proposed = known[len(normalized):]
                    strategy = "verified_witness_suffix"
        if proposed is None and budget >= 64:
            # The legacy greedy route planner has its own per-route ceiling;
            # small caller budgets skip this separate bounded strategy.
            proposed = _greedy(authored, initial, normalized, choice, required_ending)
            if proposed is not None:
                strategy = "canonical_crafting_planner"
        if proposed is not None:
            status, suffix = "completion_witness", proposed
        else:
            strategy = "bounded_transition_search"
            status, suffix, expanded = _search(authored, initial, required_ending, budget)
        if status == "completion_witness":
            final = _valid_suffix(authored, normalized, suffix, required_ending)
    body = {"schema": SCHEMA, "source_digest": harbor.digest(authored),
            "checkpoint_bundle_digest": prior["bundle_digest"],
            "required_ending": required_ending, "status": status, "strategy": strategy,
            "search_budget": budget, "expanded": expanded, "additional": suffix,
            "completion_bundle_digest": final["bundle_digest"] if final else None,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "recovery_digest": digest(body)}
    _encode(result)
    return result


def verify_local_recovery(world: Any, prefix: Any, submitted: Any,
                          *, witness: Any | None = None) -> bool:
    try:
        return _encode(submitted) == _encode(recover_local(
            world, prefix, submitted["required_ending"], witness=witness,
            max_states=submitted["search_budget"]))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
