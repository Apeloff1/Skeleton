"""Resume real local gameplay and mission progress from verified event ledgers.

Existing harbor movement, resource, economy and mission transitions remain
the owners. Search candidates are accepted only after independent complete
replay. Search ceilings and greedy failures are not impossibility proofs.
"""
from __future__ import annotations

from copy import deepcopy
from heapq import heappop, heappush
from itertools import count
from typing import Any

from skeleton.app.gameforge_campaign import digest, detached
from skeleton.app.gameforge_expedition import _available_harbor, _mission_summary
from skeleton.app.original_quest_cli import _encode, _integer, _require, _strings
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_missions import (
    advance_mission_progress, validate_board,
)
from skeleton.game.gameplay.harbor_crafting_planner import _CampaignPlanner, _distance

SCHEMA = "skeleton.gameforge.expedition.local_recovery.v1"
MAX_STATES = 4096


def _key(world: dict, state: dict, completed: list, progress: dict) -> tuple:
    # Earlier ticks at the same phase, position, resources and mission progress
    # dominate later ticks: the only mission time constraints are deadlines.
    return (tuple(state["pos"]), tuple(state["npc_pos"]),
            state["tick"] % len(world["npc"]["route"]),
            tuple(sorted(state["inventory"].items())),
            tuple(sorted(state["stock"].items())),
            tuple(sorted(state["npc_stock"].items())),
            state["coins"], state["delivered"], state["ending"], state["reputation"],
            tuple(sorted(completed)), tuple((k, tuple(v)) for k, v in sorted(progress.items())))


def _score(world: dict, state: dict, completed: list, closure: set[str]) -> tuple:
    """Heuristic ordering only, deliberately not an optimality claim."""
    missing = sum(max(0, qty - state["inventory"].get(item, 0))
                  for item, qty in world["delivery"].items())
    if state["delivered"]:
        missing = 0
    return (0 if state["ending"] else 1, len(closure - set(completed)),
            0 if state["delivered"] else 1, missing,
            state["tick"] + _distance(state["pos"], world["dock"]))


def _mission_contract(world: dict, board: Any, required: Any) -> dict:
    _require((board is None) == (required is None), "mission recovery requires board and mission IDs")
    if board is None:
        return {}
    authored = validate_board(board, world)
    names = sorted(_strings(required, 12, 48, nonempty=True))
    by_id = {row["id"]: row for row in authored["missions"]}
    _require(set(names) <= set(by_id), "unknown required mission")
    closure = set(names)
    for row in reversed(authored["missions"]):
        if row["id"] in closure:
            closure.update(row["requires"])
    return {"mission_board": authored, "required_missions": names,
            "closure": closure, "deadlines": {key: by_id[key]["deadline"] for key in closure}}


def _earned(contract: dict, bundle: dict) -> dict | None:
    return _mission_summary(contract, bundle) if contract else None


def _valid_suffix(world: dict, prefix: list, suffix: list, required: str, contract: dict) -> dict:
    bundle = harbor.export_bundle(world, [*prefix, *suffix], require_win=True)
    state = harbor.verify_bundle(bundle, require_win=True)
    _require(state["ending"] == required and state["delivered"], "wrong local completion outcome")
    summary = _earned(contract, bundle)
    _require(summary is None or summary["satisfied"], "required missions were not earned")
    return bundle


def _greedy(world: dict, initial: dict, prefix: list, choice: str,
            required: str, contract: dict) -> list | None:
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
        _valid_suffix(world, prefix, planner.actions, required, contract)
        return planner.actions
    except (ValueError, RecursionError):
        return None


def _expired(contract: dict, state: dict, completed: list) -> bool:
    return any(state["tick"] >= deadline and key not in completed
               for key, deadline in contract.get("deadlines", {}).items())


def _search(world: dict, initial: dict, required: str, budget: int,
            contract: dict, summary: dict | None) -> tuple[str, list, int]:
    serial = count()
    closure = contract.get("closure", set())
    completed = summary["completed"] if summary else []
    progress = summary["progress"] if summary else {}
    # Parent links are immutable; a later discovery can dominate a previous
    # key without rewriting the earlier path used by descendants.
    nodes = [(initial, completed, progress, None, None)]
    frontier = [(_score(world, initial, completed, closure), next(serial), 0)]
    best = {_key(world, initial, completed, progress): initial["tick"]}
    expanded = 0
    truncated = False
    while frontier:
        if expanded >= budget:
            return "budget_exhausted", [], expanded
        _, _, index = heappop(frontier)
        state, completed, progress, parent, action = nodes[index]
        if state["tick"] != best[_key(world, state, completed, progress)]:
            continue
        expanded += 1
        if state["ending"] == required and closure <= set(completed):
            path = []
            while parent is not None:
                path.append(action)
                _, _, _, parent, action = nodes[parent]
            return "completion_witness", list(reversed(path)), expanded
        if (state["ending"] is not None or state["tick"] >= world["max_ticks"]
                or _expired(contract, state, completed)):
            continue
        for action in _available_harbor(world, state):
            after = harbor.step(world, state, action)
            if after["ending"] is not None and after["ending"] != required:
                continue
            following = list(completed)
            counts = deepcopy(progress)
            if contract:
                advance_mission_progress(contract["mission_board"], world, action,
                                         state, after, following, counts)
            if _expired(contract, after, following):
                continue
            if after["ending"] is not None and not closure <= set(following):
                continue
            key = _key(world, after, following, counts)
            if key in best and best[key] <= after["tick"]:
                continue
            if len(nodes) >= budget:
                truncated = True
                continue
            best[key] = after["tick"]
            nodes.append((after, following, counts, index, action))
            heappush(frontier, (_score(world, after, following, closure), next(serial), len(nodes) - 1))
    return ("budget_exhausted" if truncated else "unreachable"), [], expanded


def _witness_suffix(world: dict, prefix: list, known: list,
                    required: str, contract: dict) -> tuple[list | None, str | None]:
    # A wait inserted into an otherwise matching ledger may shift merchant
    # timing and deadlines. Never infer equivalence; replay the actual suffix.
    if known[:len(prefix)] == prefix:
        candidates = [(len(prefix), "verified_witness_suffix")]
    else:
        stripped = [action for action in prefix if action["op"] != "wait"]
        candidates = [(i, "verified_wait_splice") for i in range(len(known) + 1)
                      if [action for action in known[:i] if action["op"] != "wait"] == stripped]
        candidates = candidates[-4:]  # explicit bounded alignment attempts
    for index, strategy in candidates:
        suffix = known[index:]
        try:
            _valid_suffix(world, prefix, suffix, required, contract)
        except ValueError:
            continue
        return suffix, strategy
    return None, None


def recover_local(world: Any, prefix: Any, required_ending: str, *,
                  witness: Any | None = None, max_states: int = 1024,
                  mission_board: Any | None = None, required_missions: Any | None = None) -> dict:
    """Return a verified legal suffix, exhaustion, or narrowly proven blocker."""
    _encode({"world": world, "prefix": prefix, "witness": witness,
             "mission_board": mission_board, "required_missions": required_missions})
    budget = _integer(max_states, 1, MAX_STATES)
    _require(type(required_ending) is str and required_ending in {"beacon", "safe_harbor"},
             "unsupported local ending")
    authored = harbor.validate_source(world)
    contract = _mission_contract(authored, mission_board, required_missions)
    _require(type(prefix) is list, "local prefix must be an action ledger")
    normalized = [harbor.normalize_action(a) for a in prefix]
    prior = harbor.export_bundle(authored, normalized)
    initial = harbor.verify_bundle(prior)
    summary = _earned(contract, prior)
    choice = "signal" if required_ending == "beacon" else "shelter"
    strategy = None
    expanded = 0
    suffix = []
    final = None
    if initial["ending"] == required_ending:
        if summary is None or summary["satisfied"]:
            status = "already_completed"
            final = prior
        else:
            status = "required_missions_missing"
    elif initial["ending"] is not None:
        status = "alternate_ending"
    elif initial["tick"] >= authored["max_ticks"]:
        status = "tick_budget_exhausted"
    elif summary is not None and _expired(contract, initial, summary["completed"]):
        status = "mission_deadline_exhausted"
    else:
        proposed = None
        if witness is not None:
            _require(type(witness) is list and len(witness) <= authored["max_ticks"],
                     "local witness must be a bounded ledger")
            known = [harbor.normalize_action(a) for a in witness]
            proposed, strategy = _witness_suffix(authored, normalized, known, required_ending, contract)
        if proposed is None and budget >= 64:
            # The legacy greedy route planner has its own per-route ceiling;
            # small caller budgets skip this separate bounded strategy.
            proposed = _greedy(authored, initial, normalized, choice, required_ending, contract)
            if proposed is not None:
                strategy = "canonical_crafting_planner"
        if proposed is not None:
            status, suffix = "completion_witness", proposed
        else:
            strategy = "bounded_transition_search"
            status, suffix, expanded = _search(authored, initial, required_ending, budget, contract, summary)
        if status == "completion_witness":
            final = _valid_suffix(authored, normalized, suffix, required_ending, contract)
    final_missions = _earned(contract, final) if final else None
    body = {"schema": SCHEMA, "source_digest": harbor.digest(authored),
            "checkpoint_bundle_digest": prior["bundle_digest"],
            "required_ending": required_ending, "status": status, "strategy": strategy,
            "search_budget": budget, "expanded": expanded, "additional": suffix,
            "completion_bundle_digest": final["bundle_digest"] if final else None,
            "native_qualified": False, "release_qualified": False}
    if contract:
        body["mission_board_digest"] = harbor.digest(contract["mission_board"])
        body["required_missions"] = contract["required_missions"]
        body["completion_missions"] = final_missions
    result = {**body, "recovery_digest": digest(body)}
    _encode(result)
    return result


def verify_local_recovery(world: Any, prefix: Any, submitted: Any, *,
                          witness: Any | None = None, mission_board: Any | None = None,
                          required_missions: Any | None = None) -> bool:
    try:
        return _encode(submitted) == _encode(recover_local(
            world, prefix, submitted["required_ending"], witness=witness,
            max_states=submitted["search_budget"], mission_board=mission_board,
            required_missions=required_missions))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
