"""Small deterministic *executable* sample of original mechanic semantics.

This is a bounded abstract simulation, NOT a native console or 3-D runtime.
Only mechanics in EXECUTABLE_RULE_IDS are interpreted. All other atlas
entries remain design-only and cannot be passed to this interpreter.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_mechanic_catalog import MECHANICS


class WorldRuleError(ValueError):
    """An invalid or unsupported gameplay rule invocation."""


EXECUTABLE_RULE_IDS = frozenset({
    "time-m01", "topology-m02", "ecology-m02", "serenity-m01",
    "survival-m01", "crafting-m04", "physics-m02", "infrastructure-m01",
})
if not EXECUTABLE_RULE_IDS.issubset(MECHANICS):
    raise WorldRuleError("sample executable rule IDs are not present in the atlas")
if any(not MECHANICS[rule].cost_specified for rule in EXECUTABLE_RULE_IDS):
    raise WorldRuleError("sample executor must not accept uncosted world levers")


@dataclass(frozen=True)
class WorldRuleState:
    tick: int = 0
    event_count: int = 0
    event_head: str = "0" * 64
    action_points: int = 2
    future_action_debt: int = 0
    energy: int = 6
    food: int = 0
    wild_food: int = 10
    wood: int = 3
    shelter_durability: int = 3
    rainfall: tuple[int, int] = (5, 5)
    shadow_momentum: int = 0
    route_order: tuple[str, ...] = ("r0", "r1", "r2", "r3", "r4")


@dataclass(frozen=True)
class WorldRuleAction:
    mechanic_id: str
    amount: int = 1
    mode: str = ""


@dataclass(frozen=True)
class WorldRuleReceipt:
    action: WorldRuleAction
    prior_state_digest: str
    next_state_digest: str
    event_digest: str
    tick: int
    rule_status: str = "simulated-abstract"


def _digest(obj: dict) -> str:
    return sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _validate_state(state: WorldRuleState) -> None:
    if not isinstance(state, WorldRuleState):
        raise WorldRuleError("state type not recognized")
    if any(isinstance(getattr(state, field), bool)
           or not isinstance(getattr(state, field), int)
           for field in (
               "tick", "event_count", "action_points", "future_action_debt",
               "energy", "food", "wild_food", "wood", "shelter_durability",
               "shadow_momentum",
           )):
        raise WorldRuleError("noninteger state")
    if (state.tick < 0 or state.event_count < 0 or
            not 0 <= state.action_points <= 5 or
            not 0 <= state.future_action_debt <= 12 or
            not 0 <= state.energy <= 10 or
            not 0 <= state.food <= 1000 or
            not 0 <= state.wild_food <= 1000 or
            not 0 <= state.wood <= 1000 or
            not 0 <= state.shelter_durability <= 10 or
            not -20 <= state.shadow_momentum <= 20):
        raise WorldRuleError("world state out of bounds")
    if (not isinstance(state.rainfall, tuple) or len(state.rainfall) != 2 or
            any(isinstance(x, bool) or not isinstance(x, int)
                or not 0 <= x <= 10 for x in state.rainfall) or
            sum(state.rainfall) != 10):
        raise WorldRuleError("rainfall conservation violated")
    if (not isinstance(state.route_order, tuple) or
            len(state.route_order) != 5 or
            state.route_order[0] != "r0" or
            set(state.route_order) != {"r0", "r1", "r2", "r3", "r4"}):
        raise WorldRuleError("route order must retain a connected 5-room cycle")
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64 or
            any(c not in "0123456789abcdef" for c in state.event_head)):
        raise WorldRuleError("invalid event digest")


def route_edges(state: WorldRuleState) -> tuple[tuple[str, str], ...]:
    """Materialize a connected cycle, regardless of mutable room ordering."""
    _validate_state(state)
    order = state.route_order
    return tuple((order[n], order[(n + 1) % len(order)]) for n in range(len(order)))


def _receipt(old: WorldRuleState, new: WorldRuleState,
             action: WorldRuleAction, seed: str) -> tuple[WorldRuleState, WorldRuleReceipt]:
    before = _digest(asdict(old))
    candidate_digest = _digest(asdict(new))
    event = _digest({
        "before": before, "candidate": candidate_digest,
        "action": asdict(action), "seed": seed,
        "version": "original-mechanic-executor.v1",
    })
    result = replace(new, event_head=event, event_count=old.event_count + 1)
    _validate_state(result)
    return result, WorldRuleReceipt(
        action=action, prior_state_digest=before,
        next_state_digest=_digest(asdict(result)), event_digest=event,
        tick=result.tick,
    )


def _validate_action(action: WorldRuleAction, seed: str) -> None:
    if not isinstance(action, WorldRuleAction):
        raise WorldRuleError("action type not recognized")
    if action.mechanic_id not in EXECUTABLE_RULE_IDS:
        raise WorldRuleError("rule not compiled for the abstract simulator")
    if (isinstance(action.amount, bool) or
            not isinstance(action.amount, int) or not 1 <= action.amount <= 3):
        raise WorldRuleError("amount must be integer between 1 and 3")
    if not isinstance(action.mode, str):
        raise WorldRuleError("invalid action mode")
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise WorldRuleError("invalid world seed")


def apply_rule(state: WorldRuleState, action: WorldRuleAction, *,
               seed: str = "atlas-demo") -> tuple[WorldRuleState, WorldRuleReceipt]:
    """Apply one supported mechanic transactionally with deterministic receipts.

    Illegal actions raise without changing the original immutable state.
    No side effects, external models, clock source or hidden random generator.
    """
    _validate_state(state)
    _validate_action(action, seed)
    if state.action_points <= 0:
        raise WorldRuleError("no actions remain on this tick")
    n = action.amount
    mechanic = action.mechanic_id
    next_state = replace(state, action_points=state.action_points - 1)

    if mechanic == "time-m01":
        if action.mode:
            raise WorldRuleError("future collateral has no mode")
        if state.future_action_debt + n > 12:
            raise WorldRuleError("future collateral debt ceiling")
        next_state = replace(
            next_state,
            action_points=min(5, next_state.action_points + n),
            future_action_debt=state.future_action_debt + n,
        )
    elif mechanic in {"topology-m02", "infrastructure-m01"}:
        requested = "unobserved" if mechanic == "topology-m02" else "last_train"
        if action.mode != requested:
            raise WorldRuleError("the route transition precondition is absent")
        old = state.route_order[1:]
        shift = int.from_bytes(sha256(
            (seed + ":" + str(state.event_count) + ":" + mechanic).encode()
        ).digest()[:4], "big") % 3 + 1
        shifted = old[shift:] + old[:shift]
        next_state = replace(next_state, route_order=("r0",) + shifted)
    elif mechanic == "ecology-m02":
        if action.mode not in {"west-to-east", "east-to-west"}:
            raise WorldRuleError("rain herding requires a movement direction")
        source, dest = ((0, 1) if action.mode == "west-to-east" else (1, 0))
        water = list(state.rainfall)
        if water[source] < n or water[dest] + n > 10:
            raise WorldRuleError("insufficient transferable rainfall")
        water[source] -= n
        water[dest] += n
        next_state = replace(next_state, rainfall=tuple(water))
    elif mechanic == "serenity-m01":
        if action.mode:
            raise WorldRuleError("rest has no mode")
        next_state = replace(next_state, energy=min(10, state.energy + n))
    elif mechanic == "survival-m01":
        if action.mode:
            raise WorldRuleError("resource intake has no mode")
        if n > state.wild_food or state.food + n > 1000:
            raise WorldRuleError("insufficient renewable food")
        next_state = replace(next_state, food=state.food + n,
                             wild_food=state.wild_food - n)
    elif mechanic == "crafting-m04":
        if action.mode or n != 1:
            raise WorldRuleError("shelter repair uses one material bundle")
        if state.wood < 1 or state.energy < 1 or state.shelter_durability >= 10:
            raise WorldRuleError("insufficient materials or no repair needed")
        next_state = replace(next_state, wood=state.wood - 1,
                             energy=state.energy - 1,
                             shelter_durability=min(10, state.shelter_durability + 3))
    elif mechanic == "physics-m02":
        if action.mode not in {"left", "right"} or state.energy < 1:
            raise WorldRuleError("shadow momentum requires direction and energy")
        impulse = (-n if action.mode == "left" else n)
        if abs(state.shadow_momentum + impulse) > 20:
            raise WorldRuleError("shadow momentum ceiling")
        next_state = replace(next_state,
                             shadow_momentum=state.shadow_momentum + impulse,
                             energy=state.energy - 1)
    else:
        raise WorldRuleError("unhandled rule")
    return _receipt(state, next_state, action, seed)


def advance_tick(state: WorldRuleState, *,
                 seed: str = "atlas-demo") -> tuple[WorldRuleState, WorldRuleReceipt]:
    """Repay borrowed action points before a fresh turn receives its budget."""
    _validate_state(state)
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise WorldRuleError("invalid world seed")
    repaid = min(state.future_action_debt, 2)
    refreshed = replace(
        state, tick=state.tick + 1, action_points=2 - repaid,
        future_action_debt=state.future_action_debt - repaid,
    )
    return _receipt(state, refreshed, WorldRuleAction("world.tick"), seed)


def replay_rules(actions: tuple[WorldRuleAction, ...], *,
                 seed: str = "atlas-demo",
                 starting_state: WorldRuleState | None = None
                 ) -> tuple[WorldRuleState, tuple[WorldRuleReceipt, ...]]:
    """Replay a bounded sequence, with explicit world.tick actions for turns."""
    if not isinstance(actions, tuple) or len(actions) > 4096:
        raise WorldRuleError("replay must be a bounded tuple")
    state = starting_state or WorldRuleState()
    receipts = []
    for action in actions:
        if not isinstance(action, WorldRuleAction):
            raise WorldRuleError("invalid replay action")
        state, receipt = (
            advance_tick(state, seed=seed)
            if action.mechanic_id == "world.tick"
            else apply_rule(state, action, seed=seed)
        )
        receipts.append(receipt)
    return state, tuple(receipts)
