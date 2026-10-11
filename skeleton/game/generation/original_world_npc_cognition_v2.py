"""A persistent, player-accountable NPC cognition and social economy.

Unlike the original profession-only NPC loop, this engine gives every person
bounded autobiographical memory, individual drives, explicit ranked goals,
social ties, remembered observations, scheduled work orders, interruptible
plans, health/care behavior and physical resource-backed civic projects.

Deterministic rule-based utility planning (NOT a pretrained language model).
Every step acts on the same finite terrain stocks and inherited citizen
identities. No duplicate resource production, teleportation, invisible NPCs,
free constructions or spontaneous social trust.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_terrain import (
    TerrainState, cell_at, _write_cell, validate_terrain,
)
from .original_world_product_agents import (
    Person, PhysicalSociety, NpcReceipt, _path, _neighbors, _resource,
    _specialty, _deliver, _acquire, validate_society, MAX_AGENTS,
)

VERSION = "original-npc-cognition.v2"
GOALS = frozenset(("work", "eat", "recover", "deliver", "scout", "care",
                   "socialize", "construct", "guard", "investigate"))
STOCK = ("food", "wood", "stone", "water")
WAREHOUSE = {"food": "provisions", "wood": "lumber",
             "stone": "masonry", "water": "freshwater"}
MAX_MEMORY = 8
MAX_BONDS = 64
MAX_ORDERS = 24
MAX_HISTORY = 1000


@dataclass(frozen=True)
class Memory:
    turn: int
    subject: str
    position: tuple[int, int]
    value: int
    confidence: int
    witness: int
    # Personal observation, not hallucinated omniscient knowledge.


@dataclass(frozen=True)
class Mind:
    person_id: int
    temperament: str
    curiosity: int
    empathy: int
    discipline: int
    prudence: int
    goal: str = "work"
    goal_age: int = 0
    objective: tuple[int, int] = (0, 0)
    morale: int = 10
    stress: int = 0
    memories: tuple[Memory, ...] = ()
    decisions: int = 0


@dataclass(frozen=True)
class Bond:
    left: int
    right: int
    affinity: int = 0
    trust: int = 0
    reciprocated_aid: int = 0


@dataclass(frozen=True)
class Order:
    order_id: int
    citizen: int
    kind: str
    quantity: int
    delivered: int = 0
    status: str = "open"
    issuer: str = "player"


@dataclass(frozen=True)
class CitizenIntelligence:
    world_id: str
    minds: tuple[Mind, ...]
    bonds: tuple[Bond, ...] = ()
    orders: tuple[Order, ...] = ()
    next_order: int = 0
    day: int = 0
    meetings: int = 0
    interventions: int = 0
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class ThoughtReceipt:
    person_id: int
    goal: str
    utility: int
    reason: str
    action: str
    real_resource: str = ""
    quantity: int = 0


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode()).hexdigest()


def _bounded(value: object, lo: int, hi: int, label: str) -> None:
    if type(value) is not int or not lo <= value <= hi:
        raise FoundationError("invalid NPC cognition " + label)


def make_intelligence(world: TerrainState, society: PhysicalSociety) -> CitizenIntelligence:
    validate_society(society, world)
    minds = []
    temperaments = ("steadfast", "inquisitive", "tender", "pragmatic",
                    "cautious", "venturesome", "devoted", "restless")
    for p in society.inhabitants:
        raw = sha256(f"{world.design_id}:{p.id}:personality".encode()).digest()
        minds.append(Mind(
            p.id, temperaments[raw[0] % len(temperaments)],
            1 + raw[1] % 10, 1 + raw[2] % 10,
            1 + raw[3] % 10, 1 + raw[4] % 10,
        ))
    # An older save can have an existing physically advanced town clock.
    # Seed new minds at that actual day, never invent past observations.
    result = CitizenIntelligence(world.design_id, tuple(minds), day=society.tick)
    validate_intelligence(result, society, world)
    return result


def validate_intelligence(
    state: CitizenIntelligence, people: PhysicalSociety, world: TerrainState,
) -> None:
    validate_society(people, world)
    if not isinstance(state, CitizenIntelligence) or state.world_id != world.design_id:
        raise FoundationError("NPC thoughts are bound to a different physical world")
    if state.day != people.tick:
        raise FoundationError("inhabitant thought clock diverged from physical body")
    if not isinstance(state.minds, tuple) or len(state.minds) != len(people.inhabitants):
        raise FoundationError("missing or extra persistent minds")
    for p, mind in zip(people.inhabitants, state.minds):
        if not isinstance(mind, Mind) or mind.person_id != p.id or mind.goal not in GOALS:
            raise FoundationError("mind-to-body identity mismatch")
        if mind.temperament not in (
            "steadfast", "inquisitive", "tender", "pragmatic",
            "cautious", "venturesome", "devoted", "restless",
        ):
            raise FoundationError("unknown original NPC temperament")
        for name, low, high in (
            ("curiosity", 1, 10), ("empathy", 1, 10),
            ("discipline", 1, 10), ("prudence", 1, 10),
            ("goal_age", 0, MAX_HISTORY), ("morale", 0, 20),
            ("stress", 0, 20), ("decisions", 0, MAX_HISTORY),
        ):
            _bounded(getattr(mind, name), low, high, name)
        if not isinstance(mind.memories, tuple) or len(mind.memories) > MAX_MEMORY:
            raise FoundationError("unbounded individual NPC autobiographical memory")
        for memory in mind.memories:
            if not isinstance(memory, Memory) or memory.subject not in (
                "food", "wood", "stone", "water", "danger", "friend", "shelter"
            ):
                raise FoundationError("invented NPC memory observation")
            _bounded(memory.turn, 0, MAX_HISTORY, "memory day")
            if memory.turn > state.day:
                raise FoundationError("NPC claims knowledge of a future world")
            _bounded(memory.value, 0, 1000, "remembered stock")
            _bounded(memory.confidence, 1, 100, "observation reliability")
            _bounded(memory.witness, 0, MAX_AGENTS - 1, "witness identity")
            if not isinstance(memory.position, tuple) or len(memory.position) != 2:
                raise FoundationError("bad memory location")
            for c in memory.position:
                _bounded(c, -(1 << 20), 1 << 20, "memory coordinate")
        if not isinstance(mind.objective, tuple) or len(mind.objective) != 2:
            raise FoundationError("invalid planned NPC destination")
        for c in mind.objective:
            _bounded(c, -(1 << 20), 1 << 20, "planned coordinate")
    if not isinstance(state.bonds, tuple) or len(state.bonds) > MAX_BONDS:
        raise FoundationError("unbounded local relationship graph")
    seen_bonds = set()
    for b in state.bonds:
        if not isinstance(b, Bond) or not 0 <= b.left < b.right < len(people.inhabitants):
            raise FoundationError("bond references missing people")
        if (b.left, b.right) in seen_bonds:
            raise FoundationError("duplicate NPC relationship graph edge")
        seen_bonds.add((b.left, b.right))
        for field, lower, upper in (
            ("affinity", -20, 20), ("trust", -20, 20),
            ("reciprocated_aid", 0, 1000),
        ):
            _bounded(getattr(b, field), lower, upper, "social bond " + field)
    if not isinstance(state.orders, tuple) or len(state.orders) > MAX_ORDERS:
        raise FoundationError("NPC work order budget exceeded")
    seen_orders = set()
    for o in state.orders:
        if not isinstance(o, Order) or o.kind not in STOCK or o.issuer != "player":
            raise FoundationError("unsupported NPC work contract")
        _bounded(o.order_id, 0, 100000, "order identity")
        _bounded(o.citizen, 0, len(people.inhabitants) - 1, "order assignee")
        _bounded(o.quantity, 1, 20, "order quantity")
        _bounded(o.delivered, 0, o.quantity, "verified order delivery")
        if o.status not in ("open", "fulfilled", "cancelled"):
            raise FoundationError("invalid NPC contract status")
        if (o.status == "fulfilled") != (o.delivered == o.quantity) and o.status != "cancelled":
            raise FoundationError("contract status does not match real delivered stock")
        if o.order_id in seen_orders:
            raise FoundationError("duplicate individual contract")
        seen_orders.add(o.order_id)
    if seen_orders and max(seen_orders) >= state.next_order:
        raise FoundationError("order counter reuses existing contract identity")
    for name in ("day", "meetings", "interventions", "event_count"):
        _bounded(getattr(state, name), 0, MAX_HISTORY, name)
    _bounded(state.next_order, 0, 100000, "next contract ID")
    if not isinstance(state.event_head, str) or len(state.event_head) != 64 or any(
        c not in "0123456789abcdef" for c in state.event_head
    ):
        raise FoundationError("invalid cognitive event chain")


def _remember(mind: Mind, event: Memory) -> Mind:
    # A repeated observation updates beliefs rather than infinitely adding
    # duplicated memories. A 100%-confidence stock observation always wins.
    entries = [
        x for x in mind.memories
        if not (x.subject == event.subject and x.position == event.position)
    ]
    entries.append(event)
    return replace(mind, memories=tuple(entries[-MAX_MEMORY:]))


def _bond_change(
    state: CitizenIntelligence, a: int, b: int,
    *, affinity: int = 0, trust: int = 0, aid: int = 0,
) -> CitizenIntelligence:
    if a == b:
        return state
    x, y = sorted((a, b))
    pairs = {(p.left, p.right): p for p in state.bonds}
    prior = pairs.get((x, y), Bond(x, y))
    pairs[(x, y)] = replace(
        prior, affinity=max(-20, min(20, prior.affinity + affinity)),
        trust=max(-20, min(20, prior.trust + trust)),
        reciprocated_aid=min(1000, prior.reciprocated_aid + aid),
    )
    if len(pairs) > MAX_BONDS:
        return state
    return replace(state, bonds=tuple(pairs[k] for k in sorted(pairs)))


def register_player_care(
    state: CitizenIntelligence, people: PhysicalSociety,
    citizen: int, *, food: int = 1,
) -> CitizenIntelligence:
    """Log care events only AFTER product layer debits actual player food."""
    _bounded(citizen, 0, len(people.inhabitants) - 1, "care recipient")
    _bounded(food, 1, 3, "real aid")
    minds = list(state.minds)
    original = minds[citizen]
    minds[citizen] = _remember(
        replace(original, morale=min(20, original.morale + food),
                stress=max(0, original.stress - food)),
        Memory(state.day, "friend",
               (people.inhabitants[citizen].x, people.inhabitants[citizen].y),
               food, 100, citizen),
    )
    return replace(state, minds=tuple(minds),
                   interventions=state.interventions + 1)


def commission(
    state: CitizenIntelligence, people: PhysicalSociety, world: TerrainState,
    *, citizen: int, material: str, quantity: int,
) -> CitizenIntelligence:
    validate_intelligence(state, people, world)
    _bounded(citizen, 0, len(people.inhabitants) - 1, "work order citizen")
    _bounded(quantity, 1, 20, "requested real stock")
    if material not in STOCK:
        raise FoundationError("order material must exist in actual terrain")
    if len(state.orders) >= MAX_ORDERS:
        raise FoundationError("work order limit reached")
    if any(o.citizen == citizen and o.status == "open" for o in state.orders):
        raise FoundationError("citizen already has a pending paid contract")
    new = Order(state.next_order, citizen, material, quantity)
    result = replace(state, orders=state.orders + (new,),
                     next_order=state.next_order + 1,
                     interventions=state.interventions + 1)
    validate_intelligence(result, people, world)
    return result


def cancel_order(
    state: CitizenIntelligence, people: PhysicalSociety, world: TerrainState,
    order_id: int,
) -> CitizenIntelligence:
    validate_intelligence(state, people, world)
    found = tuple(o for o in state.orders if o.order_id == order_id)
    if len(found) != 1 or found[0].status != "open":
        raise FoundationError("cannot cancel unknown or already closed contract")
    orders = tuple(replace(o, status="cancelled") if o.order_id == order_id else o
                   for o in state.orders)
    return replace(state, orders=orders,
                   interventions=state.interventions + 1)


def _plan(person: Person, mind: Mind, state: CitizenIntelligence,
          world: TerrainState) -> tuple[str, int, str, tuple[int, int]]:
    """Deterministic bounded utility choice, personalized and explainable.

    Hunger, injury and carrying precede autonomous production. Orders are
    strong commitments unless a citizen's survival is endangered. Resource
    destinations are reached by real BFS; goal utility never grants travel.
    """
    outstanding = next((o for o in state.orders
                        if o.citizen == person.id and o.status == "open"), None)
    nearby_hurt = any(
        person.id != other.person_id and other.stress >= 8
        for other in state.minds
    )
    scores = {
        "eat": person.hunger * 5 + (15 if person.health < 8 else 0),
        "recover": (20 - person.energy) * 3 + (20 - person.health),
        "deliver": 10 + 70 * bool(person.cargo),
        "work": 12 + mind.discipline * 2,
        "scout": 4 + mind.curiosity * 3,
        "care": mind.empathy * 2 + (25 if nearby_hurt else 0),
        "socialize": 3 + mind.empathy * 2 - mind.stress,
        "construct": (15 if person.profession in ("builder", "engineer") else 0)
                     + mind.discipline,
        "guard": 4 + mind.prudence * 2,
        "investigate": 2 + mind.curiosity * 2,
    }
    if person.hunger >= 7:
        scores["eat"] += 60
    if person.energy <= 2:
        scores["recover"] += 100
    if person.health <= 4:
        scores["recover"] += 80
    if person.cargo:
        scores["deliver"] += 100
        for category in ("work", "scout", "investigate", "construct"):
            scores[category] = -1
    if outstanding and not person.cargo:
        scores["work"] += 100 + min(20, outstanding.quantity - outstanding.delivered)
    if person.profession in ("builder", "engineer") and not person.cargo:
        scores["construct"] += 25
    if person.profession in ("guardian",):
        scores["guard"] += 35
    if person.profession in ("healer", "caretaker"):
        scores["care"] += 30
    if person.profession in ("scout", "naturalist"):
        scores["investigate"] += 30
    # Preserve goal coherence for multi-day harvesting, but interrupt
    # immediately for sickness/hunger and dangerous exhaustion.
    if mind.goal_age < 5:
        scores[mind.goal] += 8
    winner = max(sorted(scores), key=lambda key: scores[key])
    if outstanding and winner == "work":
        reason = "fulfill a recorded real-material contract"
    elif winner in ("eat", "recover"):
        reason = "survival needs override work schedules"
    elif winner == "deliver":
        reason = "return physical cargo to the common warehouse"
    else:
        reason = f"temperament={mind.temperament}; role={person.profession}"
    return winner, scores[winner], reason, (person.x, person.y)


def _physically_move(
    world: TerrainState, person: Person, predicate,
) -> tuple[Person, bool]:
    path = _path(world, (person.x, person.y), predicate)
    if len(path) > 1 and person.energy >= 1:
        nx, ny = path[1]
        return replace(person, x=nx, y=ny, energy=person.energy - 1), True
    return person, False


def _gather_from_known_world(
    world: TerrainState, person: Person, mind: Mind, kind: str,
) -> tuple[TerrainState, Person, str, str, int]:
    """Bounded perception-and-memory plan, not omniscient harvest search.

    Perceive the present cell and physically adjacent traversable cells.
    Otherwise follow an explicit individual observation that may be stale.
    After finding an exhausted remembered location, discover new terrain
    instead of minting stock from prior knowledge.
    """
    if kind not in STOCK or person.cargo:
        raise FoundationError("invalid autonomous known-stock gathering")
    x, y = person.x, person.y
    current = cell_at(world, x, y)
    if _resource(current, kind) > 0:
        return _acquire(world, person, kind)
    visible = [(nx, ny) for nx, ny in _neighbors(world, x, y)
               if _resource(cell_at(world, nx, ny), kind) > 0]
    visible.sort(key=lambda c: (
        -_resource(cell_at(world, *c), kind), c[0], c[1]))
    if visible and person.energy > 0:
        nx, ny = visible[0]
        return world, replace(
            person, x=nx, y=ny, energy=person.energy - 1,
        ), "move-to-observed-stock", "", 0
    remembered = sorted(
        (o for o in mind.memories if o.subject == kind and o.value > 0
         and o.position != (x, y)),
        key=lambda o: (
            -(o.value * o.confidence) + (mind.decisions - o.turn) * 2,
            abs(o.position[0] - x) + abs(o.position[1] - y),
            o.position,
        ),
    )
    for known in remembered[:MAX_MEMORY]:
        path = _path(
            world, (x, y),
            lambda px, py, point=known.position: (px, py) == point,
        )
        if len(path) > 1 and person.energy > 0:
            nx, ny = path[1]
            return world, replace(
                person, x=nx, y=ny, energy=person.energy - 1,
            ), "follow-individual-resource-memory", "", 0
    frontier = tuple(_neighbors(world, x, y))
    if frontier and person.energy > 0:
        # Explore a bounded new physical tile. Experience changes the
        # preferred edge so that identical stalled choices do not lock
        # citizens in place forever.
        nx, ny = frontier[
            (person.id * 3 + mind.decisions + mind.curiosity) % len(frontier)
        ]
        return world, replace(
            person, x=nx, y=ny, energy=person.energy - 1,
            discoveries=min(1000, person.discoveries + 1),
        ), "survey-unfamiliar-material-source", "", 0
    return world, person, "no-reachable-visible-or-remembered-material", "", 0


def smart_npc_tick(
    world: TerrainState,
    people: PhysicalSociety,
    thinking: CitizenIntelligence,
) -> tuple[TerrainState, PhysicalSociety, CitizenIntelligence,
           tuple[NpcReceipt, ...], tuple[ThoughtReceipt, ...]]:
    validate_intelligence(thinking, people, world)
    if thinking.day >= MAX_HISTORY or people.tick >= MAX_HISTORY:
        raise FoundationError("bounded cognitive simulator event budget exceeded")
    before = thinking
    current_world = world
    updated_people: list[Person] = []
    updated_minds: list[Mind] = []
    receipts: list[NpcReceipt] = []
    thoughts: list[ThoughtReceipt] = []
    completed = {o.order_id: o for o in thinking.orders}
    # Healing is scheduled against stable citizen identities and settled once
    # after all actors act, independent of job/identity iteration order.
    healing: dict[int, int] = {}
    bonds = thinking
    for person, mind in zip(people.inhabitants, thinking.minds):
        start = (person.x, person.y)
        goal, utility, reason, objective = _plan(person, mind, thinking, current_world)
        p = replace(person, hunger=min(20, person.hunger + 1))
        operation, resource, quantity = "idle", "", 0
        if p.health == 0:
            operation = "incapacitated"
        elif p.hunger >= 7 or goal == "eat":
            if (p.x, p.y) == (0, 0) and current_world.provisions > 0:
                current_world = replace(current_world,
                                        provisions=current_world.provisions - 1)
                p = replace(p, hunger=max(0, p.hunger - 7),
                            health=min(20, p.health + 1))
                operation, resource, quantity = "eat-supplied-food", "food", 1
            else:
                p, walked = _physically_move(current_world, p,
                                            lambda x, y: (x, y) == (0, 0))
                operation = "seek-real-meal" if walked else "cannot-reach-food"
                if p.hunger >= 15:
                    p = replace(p, health=max(0, p.health - 1))
        elif goal == "recover" or p.energy <= 2:
            p = replace(p, energy=min(20, p.energy + 4))
            operation = "recover-physically"
        elif p.cargo:
            current_world, p, operation, resource, quantity = _deliver(current_world, p)
            if operation == "deliver":
                for order in thinking.orders:
                    if (order.citizen == p.id and order.status == "open"
                            and order.kind == person.cargo_kind):
                        received = min(quantity, order.quantity - order.delivered)
                        due = order.delivered + received
                        completed[order.order_id] = replace(
                            order, delivered=due,
                            status="fulfilled" if due == order.quantity else "open",
                        )
                        break
        elif goal in ("work", "deliver"):
            active = next((o for o in thinking.orders
                           if o.citizen == p.id and o.status == "open"), None)
            kind = active.kind if active else _specialty(p)
            if kind:
                current_world, p, operation, resource, quantity = (
                    _gather_from_known_world(current_world, p, mind, kind)
                )
            else:
                operation = "no-assigned-harvest"
        elif goal == "care":
            others = [x for x in people.inhabitants if x.id != p.id
                      and (x.health < 20 or x.hunger >= 7)]
            others.sort(key=lambda x: (x.health, -x.hunger, x.id))
            if others:
                target = others[0]
                distance = abs(target.x - p.x) + abs(target.y - p.y)
                if distance <= 1 and current_world.freshwater >= 1 and target.health < 20:
                    current_world = replace(
                        current_world, freshwater=current_world.freshwater - 1)
                    # Target may not have acted yet: apply care into a stable
                    # previously recorded delta and settle it by target ID.
                    healing[target.id] = healing.get(target.id, 0) + 2
                    bonds = _bond_change(bonds, p.id, target.id,
                                         affinity=1, trust=1, aid=1)
                    operation, resource, quantity = "healed-named-patient", "water", 1
                else:
                    p, moved = _physically_move(
                        current_world, p,
                        lambda x, y: abs(x - target.x) + abs(y - target.y) <= 1,
                    )
                    operation = "seek-patient" if moved else "patient-inaccessible"
            else:
                operation = "no-patient"
        elif goal in ("scout", "investigate", "guard"):
            moves = tuple(_neighbors(current_world, p.x, p.y))
            if moves:
                dest = moves[(thinking.day + p.id * 3 + mind.curiosity) % len(moves)]
                p = replace(p, x=dest[0], y=dest[1], energy=max(0, p.energy - 1),
                            discoveries=min(1000, p.discoveries + 1))
                operation = "inspect-real-local-geography"
        elif goal == "construct":
            at = cell_at(current_world, p.x, p.y)
            if (not at.building and not at.blocking
                    and current_world.lumber >= 2
                    and current_world.masonry >= 1):
                current_world = replace(
                    current_world, lumber=current_world.lumber - 2,
                    masonry=current_world.masonry - 1,
                    shelter=min(1000, current_world.shelter + 1),
                )
                current_world = _write_cell(current_world, replace(at, building="hearth"))
                operation, resource, quantity = "build-real-hearth", "structure", 1
            else:
                operation = "construction-blocked-by-materials"
        else:
            operation = "consider-local-company"
        if p.hunger >= 18 and operation != "eat-supplied-food":
            p = replace(p, health=max(0, p.health - 1))
        if p.energy < 0 or abs(p.x - start[0]) + abs(p.y - start[1]) > 1:
            raise FoundationError("NPC cognitive decision teleported or overspent energy")
        observed = cell_at(current_world, p.x, p.y)
        # Up to four truthful stock observations per tile, retained in a
        # bounded eight-entry autobiographical memory. These impressions
        # drive the next journey and update stale/depleted locations.
        memory = mind
        for kind in STOCK:
            memory = _remember(memory, Memory(
                thinking.day + 1, kind, (p.x, p.y),
                _resource(observed, kind), 100, p.id,
            ))
        if goal == mind.goal:
            age = min(MAX_HISTORY, mind.goal_age + 1)
        else:
            age = 0
        updated_minds.append(replace(
            memory, goal=goal, goal_age=age, objective=(p.x, p.y),
            stress=max(0, min(20, memory.stress
                              + (2 if operation in ("cannot-reach-food",
                                                   "patient-inaccessible") else -1))),
            morale=max(0, min(20, memory.morale
                              + (1 if operation in ("deliver", "build-real-hearth") else 0))),
            decisions=min(MAX_HISTORY, memory.decisions + 1),
        ))
        updated_people.append(p)
        receipts.append(NpcReceipt(
            people.event_count + 1, p.id, p.profession, operation,
            start, (p.x, p.y), resource, quantity,
        ))
        thoughts.append(ThoughtReceipt(
            p.id, goal, utility, reason, operation, resource, quantity,
        ))
    if healing:
        updated_people = [
            replace(p, health=min(20, p.health + healing.get(p.id, 0)))
            for p in updated_people
        ]
    # The social bond graph updates only for physically co-located human
    # interactions. Each pair counts at most one meeting per day.
    for i, a in enumerate(updated_people):
        for b in updated_people[i+1:]:
            if (a.x, a.y) != (b.x, b.y):
                continue
            if a.health == 0 or b.health == 0:
                continue
            if updated_minds[a.id].goal not in ("socialize", "care") and (
                updated_minds[b.id].goal not in ("socialize", "care")
            ):
                continue
            bonds = _bond_change(bonds, a.id, b.id, affinity=1, trust=1)
    next_people = replace(
        people, tick=people.tick + 1,
        inhabitants=tuple(updated_people),
        event_count=people.event_count + 1,
        event_head=_hash({
            "physical-schema": "npc-autonomy.v2", "prior": people.event_head,
            "citizens": [asdict(p) for p in updated_people],
            "material": [getattr(current_world, x) for x in WAREHOUSE.values()],
            "observations": [asdict(r) for r in receipts],
        }),
    )
    result = replace(
        bonds, minds=tuple(updated_minds),
        orders=tuple(completed[o.order_id] for o in thinking.orders),
        day=next_people.tick,
        meetings=bonds.meetings + max(0, len(bonds.bonds) - len(thinking.bonds)),
        event_count=thinking.event_count + 1,
        event_head=_hash({
            "schema": VERSION, "prior": before.event_head,
            "world": current_world.design_id,
            "minds": [asdict(m) for m in updated_minds],
            "orders": [asdict(completed[o.order_id]) for o in thinking.orders],
            "bonds": [asdict(b) for b in bonds.bonds],
            "thoughts": [asdict(t) for t in thoughts],
        }),
    )
    validate_intelligence(result, next_people, current_world)
    return current_world, next_people, result, tuple(receipts), tuple(thoughts)


def cognition_save(state: CitizenIntelligence) -> dict:
    payload = asdict(state)
    return {"schema": VERSION, "payload": payload, "checksum": _hash(payload)}


def cognition_restore(data: dict, people: PhysicalSociety,
                      world: TerrainState) -> CitizenIntelligence:
    try:
        if not isinstance(data, dict) or set(data) != {
            "schema", "payload", "checksum"
        } or data["schema"] != VERSION:
            raise FoundationError("wrong cognitive save version")
        raw = data["payload"]
        if data["checksum"] != _hash(raw) or set(raw) != set(
            CitizenIntelligence.__dataclass_fields__
        ):
            raise FoundationError("cognitive memory integrity mismatch")
        minds = tuple(Mind(
            **{**m, "objective": tuple(m["objective"]),
               "memories": tuple(Memory(
                   **{**obs, "position": tuple(obs["position"])}
               ) for obs in m["memories"])}
        ) for m in raw["minds"])
        relationships = tuple(Bond(**b) for b in raw["bonds"])
        orders = tuple(Order(**o) for o in raw["orders"])
        state = CitizenIntelligence(
            **{**raw, "minds": minds, "bonds": relationships, "orders": orders}
        )
        validate_intelligence(state, people, world)
        return state
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise FoundationError("invalid independent NPC cognition save") from exc


def cognition_report(state: CitizenIntelligence, people: PhysicalSociety,
                     world: TerrainState) -> dict:
    validate_intelligence(state, people, world)
    return {
        "version": VERSION,
        "citizens": len(state.minds),
        "social_relationships": len(state.bonds),
        "verified_world_observations": sum(len(m.memories) for m in state.minds),
        "contracts": [asdict(o) for o in state.orders],
        "active_goals": {m.person_id: m.goal for m in state.minds},
        "health_and_stress": {
            str(m.person_id): {
                "health": people.inhabitants[m.person_id].health,
                "hunger": people.inhabitants[m.person_id].hunger,
                "morale": m.morale, "stress": m.stress,
            } for m in state.minds
        },
        "report_not_an_llm": True,
    }
