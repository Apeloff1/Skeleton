"""Executable spatial layer for 12,288,000 indexed rule compositions.

Each architecture has its own graph, constrained traversal, intervention and
hazard/resource dynamics. The bounded twenty-four-room scene is a reference
simulation, not a 3D renderer or unlimited world. Existing million-runtime
saves and indexes stay unchanged; this wrapper owns its own replay envelope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_million_runtime import (
    AdvancedAction, AdvancedState, create_advanced, step_advanced,
    restore_advanced, save_advanced, validate_game,
)
from .original_world_tenfold_compiler import (
    TenfoldWorld, tenfold_at, tenfold_from_id,
)
from .original_world_tenfold_architectures import ARCHITECTURE_BY_ID

ROOMS = 24
MAX_EVENTS = 1000
MAX_SAVE = 262144
SPACE_VERBS = frozenset({
    "travel", "survey", "extract", "resupply", "repair", "rest",
    "pave", "splice", "anchor", "ferry", "brace",
    "tether", "align", "attune", "stabilize", "seal",
})


@dataclass(frozen=True)
class TenfoldAction:
    layer: str
    verb: str
    amount: int = 1
    target: int = -1
    option: str = ""


@dataclass(frozen=True)
class TenfoldState:
    world_id: str
    game: AdvancedState
    position: int = 0
    tick: int = 0
    visited: tuple[int, ...] = (0,)
    surveyed: tuple[int, ...] = (0,)
    extraction: tuple[tuple[int, int], ...] = ()
    materials: int = 8
    oxygen: int = 12
    fuel: int = 9
    danger: int = 0
    roadways: int = 0
    splices: int = 0
    anchors: int = 0
    ferries: int = 0
    braces: int = 0
    tethers: int = 0
    alignment: int = 0
    attunement: int = 0
    stability: int = 0
    seals: int = 0
    events: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class TenfoldReceipt:
    event_id: str
    number: int
    action: TenfoldAction
    changes: tuple[str, ...]
    nested_game_head: str


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _number(value: object, lo: int, hi: int, label: str) -> None:
    if type(value) is not int or not lo <= value <= hi:
        raise FoundationError("invalid spatial " + label)


def _edge(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _ring(start: int, length: int):
    return {_edge(start + i, start + ((i + 1) % length))
            for i in range(length)}


def _grid():
    edges = set()
    for i in range(ROOMS):
        x, y = i % 6, i // 6
        if x < 5:
            edges.add(_edge(i, i + 1))
        if y < 3:
            edges.add(_edge(i, i + 6))
    return edges


def _labyrinth_tree(seed: str):
    """Deterministic randomized depth-first spanning tree, all rooms reachable."""
    visited, stack, edges = {0}, [0], set()
    while stack:
        node = stack[-1]
        neighbors = [
            peer for pair in _grid() if node in pair
            for peer in pair if peer != node and peer not in visited
        ]
        if not neighbors:
            stack.pop()
            continue
        pick = min(neighbors, key=lambda peer: _digest(
            {"seed": seed, "from": node, "to": peer}))
        edges.add(_edge(node, pick))
        stack.append(pick)
        visited.add(pick)
    if len(visited) != ROOMS or len(edges) != ROOMS - 1:
        raise FoundationError("spanning tree failed to reach all rooms")
    return edges


def _graph(state: TenfoldState) -> tuple[tuple[int, int], ...]:
    law = tenfold_from_id(state.world_id)
    kind = law.spatial.architecture.architecture_id
    phase = state.tick
    if kind == "lattice":
        edges = _grid()
        if state.roadways:
            edges.add(_edge(0, 23))
    elif kind == "spiral":
        edges = {_edge(i, i + 1) for i in range(ROOMS - 1)}
        if state.splices:
            edges.add(_edge(0, 12))
            edges.add(_edge(8, 20))
    elif kind == "labyrinth":
        edges = _labyrinth_tree(law.design_id)
        # Fixed tree guarantees a path regardless of rotating passages.
        for i in range(2):
            a = (phase * 7 + i * 11) % ROOMS
            adjacent = sorted(b for edge in _grid() if a in edge
                              for b in edge if b != a)
            if adjacent:
                edges.add(_edge(a, adjacent[(phase + i) % len(adjacent)]))
        if state.anchors:
            edges.add(_edge(0, 6))
    elif kind == "archipelago":
        edges = set().union(*(_ring(start, 6) for start in (0, 6, 12, 18)))
        if state.ferries:
            edges.update({_edge(5, 6), _edge(11, 12),
                          _edge(17, 18), _edge(23, 0)})
    elif kind == "strata":
        edges = set().union(*(_ring(start, 6) for start in (0, 6, 12, 18)))
        edges.update({_edge(i, i + 6) for i in (0, 6, 12)})
        if state.braces:
            edges.update({_edge(i, i + 6) for i in (3, 9, 15)})
    elif kind == "canopy":
        edges = set().union(*(_ring(start, 6) for start in (0, 6, 12, 18)))
        edges.update({_edge(i, i + 6) for i in (0, 6, 12)})
        if phase % 2 == 0 or state.tethers:
            edges.update({_edge(i, i + 7) for i in (1, 7, 13)})
    elif kind == "orbit":
        edges = set().union(*(_ring(start, 4) for start in (0, 4, 8, 12, 16, 20)))
        if phase % 3 == 0 or state.alignment:
            edges.update({_edge(i, i + 4) for i in (0, 4, 8, 12, 16)})
    elif kind == "pocket":
        edges = _ring(0, 12) | _ring(12, 12)
        if state.attunement:
            edges.update({_edge(i, i + 12) for i in (0, 3, 6, 9)})
    elif kind == "phase":
        edges = _ring(0, ROOMS)
        point = (7 * phase + 3) % ROOMS
        edges.add(_edge(point, (point + 9) % ROOMS))
        if state.stability:
            edges.add(_edge(0, 12))
    else:  # abyss
        edges = _grid()
        if phase % 2 == 0 or state.seals:
            edges.update({_edge(2, 14), _edge(5, 23)})
    return tuple(sorted(edges))


def validate_tenfold(state: TenfoldState) -> TenfoldWorld:
    if not isinstance(state, TenfoldState):
        raise FoundationError("invalid topological game state")
    law = tenfold_from_id(state.world_id)
    if not isinstance(state.game, AdvancedState):
        raise FoundationError("invalid nested genre game")
    game_law = validate_game(state.game)
    if game_law.design_id != law.advanced.design_id:
        raise FoundationError("nested gameplay source differs from world-architecture identity")
    for field, hi in (
        ("position", 23), ("tick", 1000000), ("materials", 100),
        ("oxygen", 30), ("fuel", 30), ("danger", 100),
        ("roadways", 10), ("splices", 10), ("anchors", 10),
        ("ferries", 10), ("braces", 10), ("tethers", 10),
        ("alignment", 10), ("attunement", 10), ("stability", 10),
        ("seals", 10), ("events", MAX_EVENTS),
    ):
        _number(getattr(state, field), 0, hi, field)
    for field in ("visited", "surveyed"):
        locations = getattr(state, field)
        if (not isinstance(locations, tuple) or len(locations) > ROOMS
                or len(locations) != len(set(locations))
                or any(type(i) is not int or not 0 <= i < ROOMS for i in locations)
                or 0 not in locations):
            raise FoundationError("invalid spatial exploration ledger")
    if state.position not in state.visited:
        raise FoundationError("player location absent from visited sites")
    if (not isinstance(state.extraction, tuple)
            or len(state.extraction) > ROOMS
            or len(set(k for k, _ in state.extraction)) != len(state.extraction)
            or any(type(k) is not int or not 0 <= k < ROOMS or
                   type(v) is not int or not 0 < v <= 8
                   for k, v in state.extraction)):
        raise FoundationError("invalid resource depletion ledger")
    for site, quantity in state.extraction:
        if quantity > site_capacity(law.design_id, site):
            raise FoundationError("resource extraction exceeds actual geology")
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64
            or any(c not in "0123456789abcdef" for c in state.event_head)):
        raise FoundationError("invalid spatial receipt identity")
    return law


def passages(state: TenfoldState) -> tuple[int, ...]:
    validate_tenfold(state)
    return tuple(sorted({
        peer for edge in _graph(state) if state.position in edge
        for peer in edge if peer != state.position
    }))


def site_capacity(design_id: str, position: int) -> int:
    _number(position, 0, 23, "geological position")
    digest = sha256((design_id + ":" + str(position)).encode("ascii")).digest()
    return 3 + digest[0] % 6


def available_material(state: TenfoldState, position: int | None = None) -> int:
    law = validate_tenfold(state)
    site = state.position if position is None else position
    baseline = site_capacity(law.design_id, site)
    return baseline - dict(state.extraction).get(site, 0)


def create_tenfold(selector: int | str) -> TenfoldState:
    law = tenfold_at(selector) if type(selector) is int else tenfold_from_id(selector)
    state = TenfoldState(
        law.tenfold_id, create_advanced(law.advanced.advanced_id),
    )
    validate_tenfold(state)
    return state


def _spend_game(
    game: AdvancedState, *, energy: int = 0,
    supplies: int = 0, trust: int = 0, evidence: int = 0,
) -> AdvancedState:
    before = game.causal
    for field, amount in (("energy", energy), ("supplies", supplies),
                          ("trust", trust), ("evidence", evidence)):
        if type(amount) is not int or amount < 0 or getattr(before, field) < amount:
            raise FoundationError("spatial world lacks " + field)
    updated = replace(before, energy=before.energy - energy,
                      supplies=before.supplies - supplies,
                      trust=before.trust - trust,
                      evidence=before.evidence - evidence)
    return replace(game, causal=updated)


def _spend_spatial(
    state: TenfoldState, *, materials: int = 0, oxygen: int = 0,
    fuel: int = 0,
) -> TenfoldState:
    for name, amount in (("materials", materials), ("oxygen", oxygen), ("fuel", fuel)):
        if type(amount) is not int or amount < 0 or getattr(state, name) < amount:
            raise FoundationError("insufficient spatial " + name)
    return replace(state, materials=state.materials - materials,
                   oxygen=state.oxygen - oxygen, fuel=state.fuel - fuel)


def _navigation(
    state: TenfoldState, target: int,
) -> tuple[TenfoldState, tuple[str, ...]]:
    kind = tenfold_from_id(state.world_id).spatial.architecture.architecture_id
    if target not in passages(state):
        raise FoundationError("destination is not connected in the current world phase")
    current = state.position
    game = state.game
    state = _spend_spatial(state, oxygen=(
        1 if kind in ("pocket", "abyss") and not state.seals else 0
    ))
    extra_energy = 0
    extra_danger = 0
    if kind == "lattice":
        extra_danger = 0 if state.roadways else (1 if target % 6 == 5 else 0)
    elif kind == "spiral":
        extra_energy = 1 if abs(current - target) > 1 else 0
    elif kind == "labyrinth":
        extra_danger = (1 if state.tick % 2 and not state.anchors else 0)
    elif kind == "archipelago":
        if current // 6 != target // 6:
            if not state.ferries:
                raise FoundationError("inter-island ferry network not financed")
            state = _spend_spatial(state, fuel=2)
            extra_danger = 1 if state.tick % 3 == 2 else 0
    elif kind == "strata":
        if current // 6 != target // 6:
            extra_energy = 1
            extra_danger = 0 if state.braces else max(1, target // 6)
    elif kind == "canopy":
        if current // 6 != target // 6:
            extra_danger = 0 if state.tethers else 2
    elif kind == "orbit":
        if current // 4 != target // 4:
            state = _spend_spatial(state, fuel=3)
            extra_danger = 0 if state.alignment else 1
    elif kind == "pocket":
        if (current < 12) != (target < 12):
            if not state.attunement:
                raise FoundationError("reality gate requires calibrated portal")
            extra_energy = 1
    elif kind == "phase":
        if abs(current - target) not in (1, 23):
            extra_danger = 0 if state.stability else 2
    elif kind == "abyss":
        extra_energy = 1 if target // 6 > current // 6 else 0
        extra_danger = 0 if state.seals else target // 6
    game = _spend_game(game, energy=1 + extra_energy)
    if state.danger + extra_danger > 100:
        raise FoundationError("unsafe navigation exceeds spatial hazard budget")
    state = replace(
        state, game=game, position=target,
        visited=tuple(sorted(set(state.visited) | {target})),
        danger=state.danger + extra_danger,
    )
    return state, (
        f"Traversed real {kind} edge {current} to {target}",
        f"Energy debit: {1 + extra_energy}; extra hazard: {extra_danger}",
    )


def _intervention(state: TenfoldState, verb: str, amount: int
                  ) -> tuple[TenfoldState, tuple[str, ...]]:
    kind = tenfold_from_id(state.world_id).spatial.architecture.architecture_id
    required = ARCHITECTURE_BY_ID[kind].intervention
    if verb != required:
        raise FoundationError("world architecture does not support this intervention")
    # Architecture improvements are bounded material purchases. Only their
    # corresponding game rules and traversable graphs are changed.
    cost = {
        "pave": 2, "splice": 3, "anchor": 2, "ferry": 3,
        "brace": 2, "tether": 2, "align": 3,
        "attune": 3, "stabilize": 2, "seal": 3,
    }[verb] * amount
    field = {
        "pave": "roadways", "splice": "splices", "anchor": "anchors",
        "ferry": "ferries", "brace": "braces", "tether": "tethers",
        "align": "alignment", "attune": "attunement",
        "stabilize": "stability", "seal": "seals",
    }[verb]
    if getattr(state, field) + amount > 10:
        raise FoundationError("spatial engineering capacity exceeded")
    if verb == "anchor" and state.game.causal.evidence < amount:
        raise FoundationError("maze stabilizer needs investigated evidence")
    if verb == "align" and state.fuel < amount:
        raise FoundationError("orbital alignment needs reaction fuel")
    if verb == "attune" and state.game.causal.trust < amount:
        raise FoundationError("realm portal needs consented access")
    if verb == "ferry" and state.position % 6 not in (0, 5):
        raise FoundationError("ferries can be repaired only at proper landing piers")
    state = _spend_spatial(
        state, materials=cost, fuel=(amount if verb == "align" else 0),
    )
    if verb == "anchor":
        state = replace(state, game=_spend_game(state.game, evidence=amount))
    if verb == "attune":
        state = replace(state, game=_spend_game(state.game, trust=amount))
    state = replace(state, **{field: getattr(state, field) + amount})
    return state, (
        f"Installed {amount} real {kind} improvement(s): {verb}",
        "Debited finite physical construction materials",
    )


def _step_space(
    state: TenfoldState, action: TenfoldAction
) -> tuple[TenfoldState, tuple[str, ...]]:
    verb, n = action.verb, action.amount
    kind = tenfold_from_id(state.world_id).spatial.architecture.architecture_id
    if verb not in SPACE_VERBS:
        raise FoundationError("unsupported spatial action")
    if state.game.causal.action_points <= 0:
        raise FoundationError("end the world turn before further spatial decisions")
    if verb == "travel":
        if n != 1 or action.target < 0:
            raise FoundationError("travel requires one adjacent target node")
        state, effects = _navigation(state, action.target)
    elif verb == "survey":
        unseen = tuple(peer for peer in passages(state) if peer not in state.surveyed)
        if not unseen:
            raise FoundationError("no unseen adjacent room to survey")
        if state.game.causal.evidence >= 100:
            raise FoundationError("knowledge inventory already saturated")
        state = replace(state, game=_spend_game(state.game, energy=n),
                        surveyed=tuple(sorted(set(state.surveyed) | {unseen[0]})))
        game = state.game
        state = replace(state, game=replace(
            game, causal=replace(game.causal, evidence=game.causal.evidence + 1),
        ))
        effects = (f"Surveyed actually reachable room {unseen[0]}",)
    elif verb == "extract":
        law = tenfold_from_id(state.world_id)
        current = dict(state.extraction)
        available = site_capacity(law.design_id, state.position) - current.get(state.position, 0)
        if n > available or state.materials + n > 100:
            raise FoundationError("depleted geology or full material inventory")
        state = replace(state, game=_spend_game(state.game, energy=n))
        current[state.position] = current.get(state.position, 0) + n
        state = replace(state, extraction=tuple(sorted(current.items())),
                        materials=state.materials + n)
        effects = (f"Extracted {n} finite material(s) from real site {state.position}",)
    elif verb == "resupply":
        if state.game.causal.supplies + n > 10000:
            raise FoundationError("world supplies exceed safe capacity")
        state = _spend_spatial(state, materials=n)
        game = state.game
        state = replace(state, game=replace(game, causal=replace(
            game.causal, supplies=game.causal.supplies + n,
        )))
        effects = ("Transferred mined material to genre/civic supply inventory",)
    elif verb == "repair":
        state = _spend_spatial(state, materials=n)
        state = replace(state, danger=max(0, state.danger - 4 * n))
        effects = ("Spent actual material to repair accumulated travel harm",)
    elif verb == "rest":
        state = replace(state, game=_spend_game(state.game, supplies=n),
                        oxygen=min(30, state.oxygen + 3 * n),
                        fuel=min(30, state.fuel + (n if kind == "orbit" else 0)))
        effects = ("Paid real supplies to recover oxygen and onboard readiness",)
    else:
        state, effects = _intervention(state, verb, n)
    game = state.game
    state = replace(state, game=replace(
        game, causal=replace(
            game.causal, action_points=game.causal.action_points - 1,
        ),
    ))
    return state, effects


def step_tenfold(
    state: TenfoldState, action: TenfoldAction
) -> tuple[TenfoldState, TenfoldReceipt]:
    law = validate_tenfold(state)
    if state.events >= MAX_EVENTS:
        raise FoundationError("spatial event budget exhausted")
    if not isinstance(action, TenfoldAction) or action.layer not in (
        "spatial", "mode", "arc", "causal",
    ):
        raise FoundationError("invalid action-layer contract")
    _number(action.amount, 1, 3, "action amount")
    _number(action.target, -1, 23, "action target")
    if (not isinstance(action.verb, str) or not action.verb
            or len(action.verb) > 64 or
            not isinstance(action.option, str) or len(action.option) > 32):
        raise FoundationError("invalid spatial action payload")
    updated, effects = state, ()
    if action.layer == "spatial":
        updated, effects = _step_space(state, action)
    else:
        if action.target > 11:
            raise FoundationError("nonspatial target cannot exceed reference game's twelve rooms")
        game, receipt = step_advanced(state.game, AdvancedAction(
            action.layer, action.verb, action.amount,
            action.target, action.option,
        ))
        updated = replace(state, game=game)
        effects = receipt.changes
        if action.layer == "causal" and action.verb == "end_turn":
            updated = replace(updated, tick=state.tick + 1)
            if updated.tick % 4 == 0 and updated.danger:
                updated = replace(updated, danger=min(100, updated.danger + 1))
                effects += ("Unresolved terrain hazards compounded across seasons",)
            if (law.spatial.architecture.architecture_id == "abyss"
                    and not updated.seals and updated.position // 6 >= 2):
                updated = _spend_spatial(updated, oxygen=1)
                effects += ("Deep-water pressure consumed additional oxygen",)
    event = _digest({
        "schema": "original-tenfold-spatial-runtime.v1",
        "source": law.design_id, "previous": state.event_head,
        "before": asdict(state), "after": asdict(updated),
        "action": asdict(action), "changes": effects,
    })
    final = replace(updated, events=state.events + 1, event_head=event)
    validate_tenfold(final)
    return final, TenfoldReceipt(
        event, final.events, action, tuple(effects),
        final.game.event_head,
    )


def replay_tenfold(index: int, actions: tuple[TenfoldAction, ...]):
    if not isinstance(actions, tuple) or len(actions) > MAX_EVENTS:
        raise FoundationError("invalid bounded spatial replay sequence")
    state = create_tenfold(index)
    receipts = []
    for action in actions:
        state, receipt = step_tenfold(state, action)
        receipts.append(receipt)
    return state, tuple(receipts)


def save_tenfold(state: TenfoldState) -> str:
    law = validate_tenfold(state)
    payload = {
        "schema": "original-tenfold-spatial-runtime.v1",
        "source_design_id": law.design_id,
        "world_id": state.world_id,
        "nested": json.loads(save_advanced(state.game)),
        "space": {
            name: getattr(state, name) for name in
            TenfoldState.__dataclass_fields__ if name not in ("world_id", "game")
        },
    }
    return json.dumps({
        "payload": payload, "checksum": _digest(payload),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def restore_tenfold(value: str) -> TenfoldState:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_SAVE:
        raise FoundationError("invalid spatial save length")
    try:
        envelope = json.loads(value)
        if set(envelope) != {"payload", "checksum"}:
            raise FoundationError("invalid save envelope")
        payload = envelope["payload"]
        if (set(payload) != {"schema", "source_design_id", "world_id", "nested", "space"}
                or payload["schema"] != "original-tenfold-spatial-runtime.v1"
                or envelope["checksum"] != _digest(payload)):
            raise FoundationError("spatial save integrity or schema mismatch")
        spatial = payload["space"]
        if set(spatial) != set(TenfoldState.__dataclass_fields__) - {"world_id", "game"}:
            raise FoundationError("invalid spatial save properties")
        spatial["visited"] = tuple(spatial["visited"])
        spatial["surveyed"] = tuple(spatial["surveyed"])
        spatial["extraction"] = tuple(tuple(row) for row in spatial["extraction"])
        state = TenfoldState(
            payload["world_id"],
            restore_advanced(json.dumps(payload["nested"])),
            **spatial,
        )
        law = validate_tenfold(state)
        if law.design_id != payload["source_design_id"]:
            raise FoundationError("cross-version world law identity mismatch")
        return state
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise FoundationError("invalid spatial save") from exc
