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

from dataclasses import asdict, dataclass, field, replace
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
from .original_world_npc_civics import (
    CivicInstitutions, validate_civics, settle_civic, civic_report,
    civic_restore, SCHEMA as CIVIC_SCHEMA,
)
from .original_world_npc_apprenticeships import (
    TeachingLedger, validate_teaching, settle_training, training_report,
    training_restore, SCHEMA as TRAINING_SCHEMA,
)

VERSION = "original-npc-cognition.v2"
GOALS = frozenset(("work", "eat", "recover", "deliver", "scout", "care",
                   "socialize", "construct", "guard", "investigate"))
GOAL_ORDER = tuple(sorted(GOALS))
STOCK = ("food", "wood", "stone", "water")
WAREHOUSE = {"food": "provisions", "wood": "lumber",
             "stone": "masonry", "water": "freshwater"}
MAX_MEMORY = 16
MAX_TESTIMONIES = 256
MAX_BONDS = 64
MAX_ORDERS = 24
MAX_PROJECTS = 12
PROJECT_COSTS = {"hearth": (2, 1, 2), "mill": (1, 3, 3),
                 "beacon": (2, 2, 3)}
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
    loneliness: int = 0
    learned: tuple[int, ...] = (0,) * 10
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
class CivicProject:
    project_id: int
    kind: str
    x: int
    y: int
    escrow_wood: int
    escrow_stone: int
    contributors: tuple[int, ...] = ()
    status: str = "open"


@dataclass(frozen=True)
class Testimony:
    citizen: int
    subject: str
    x: int
    y: int
    observation_turn: int
    value: int
    confidence: int


@dataclass(frozen=True)
class CitizenIntelligence:
    world_id: str
    minds: tuple[Mind, ...]
    bonds: tuple[Bond, ...] = ()
    orders: tuple[Order, ...] = ()
    next_order: int = 0
    projects: tuple[CivicProject, ...] = ()
    next_project: int = 0
    testimonies: tuple[Testimony, ...] = ()
    civic: CivicInstitutions = field(default_factory=CivicInstitutions)
    training: TeachingLedger = field(default_factory=TeachingLedger)
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
    validate_civics(state.civic, people, world, state.day)
    validate_teaching(state.training, people, world)
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
            ("stress", 0, 20), ("loneliness", 0, 20),
            ("decisions", 0, MAX_HISTORY),
        ):
            _bounded(getattr(mind, name), low, high, name)
        if (not isinstance(mind.learned, tuple)
                or len(mind.learned) != len(GOAL_ORDER)):
            raise FoundationError("individual learned utility policy is malformed")
        for preference in mind.learned:
            _bounded(preference, -12, 12, "learned behavioral policy")
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
    if not isinstance(state.projects, tuple) or len(state.projects) > MAX_PROJECTS:
        raise FoundationError("too many concurrent authored civic projects")
    project_ids, project_locations = set(), set()
    for project in state.projects:
        if (not isinstance(project, CivicProject)
                or project.kind not in PROJECT_COSTS
                or project.status not in ("open", "completed", "cancelled")):
            raise FoundationError("invalid civic infrastructure project")
        _bounded(project.project_id, 0, 10000, "public project ID")
        _bounded(project.x, -(1 << 20), 1 << 20, "project x")
        _bounded(project.y, -(1 << 20), 1 << 20, "project y")
        if (project.escrow_wood, project.escrow_stone) != PROJECT_COSTS[project.kind][:2]:
            raise FoundationError("civic project lacks exact physical materials in escrow")
        if not isinstance(project.contributors, tuple):
            raise FoundationError("invalid civic project labor records")
        for person_id in project.contributors:
            _bounded(person_id, 0, len(people.inhabitants) - 1, "worker identity")
        if len(set(project.contributors)) != len(project.contributors):
            raise FoundationError("duplicated civic labor cannot produce free construction")
        if len(project.contributors) > PROJECT_COSTS[project.kind][2]:
            raise FoundationError("civic labor count exceeds required physical workers")
        if (project.status == "completed") != (
            len(project.contributors) == PROJECT_COSTS[project.kind][2]
        ) and project.status != "cancelled":
            raise FoundationError("structure completion missing verified work receipts")
        if project.project_id in project_ids:
            raise FoundationError("duplicated civic project identity")
        project_ids.add(project.project_id)
        if project.status == "open":
            if (project.x, project.y) in project_locations:
                raise FoundationError("two construction projects claim the same building site")
            project_locations.add((project.x, project.y))
    if project_ids and max(project_ids) >= state.next_project:
        raise FoundationError("reused public construction identity")
    if not isinstance(state.testimonies, tuple) or len(state.testimonies) > MAX_TESTIMONIES:
        raise FoundationError("unbounded personal oral-history evidence")
    seen_evidence = set()
    for statement in state.testimonies:
        if not isinstance(statement, Testimony) or statement.subject not in STOCK:
            raise FoundationError("invalid independent NPC statement")
        _bounded(statement.citizen, 0, len(people.inhabitants)-1, "speaker")
        _bounded(statement.observation_turn, 0, state.day, "testimony time")
        _bounded(statement.value, 1, 1000, "testified observed stock")
        _bounded(statement.confidence, 70, 100, "corroboration confidence")
        for coordinate in (statement.x, statement.y):
            _bounded(coordinate, -(1 << 20), 1 << 20, "reported location")
        # A physical observation site is a unique evidence claim even when
        # revisited; advancing time alone cannot mint duplicate public facts.
        key = (statement.citizen, statement.subject, statement.x,
               statement.y)
        if key in seen_evidence:
            raise FoundationError("duplicated testimony cannot mint game evidence")
        seen_evidence.add(key)
    for name in ("day", "meetings", "interventions", "event_count"):
        _bounded(getattr(state, name), 0, MAX_HISTORY, name)
    _bounded(state.next_order, 0, 100000, "next contract ID")
    _bounded(state.next_project, 0, 10000, "next construction ID")
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


def interview_citizen(
    state: CitizenIntelligence, people: PhysicalSociety,
    world: TerrainState, *, citizen: int, subject: str = "",
) -> tuple[CitizenIntelligence, Testimony]:
    """Citizen can testify only to a witnessed, recent, positive observation.

    Player proximity and AP/evidence credit are enforced in the product
    transaction. Duplicate interviews do not create unlimited evidence.
    """
    validate_intelligence(state, people, world)
    _bounded(citizen, 0, len(people.inhabitants) - 1, "interviewed person")
    if subject and subject not in STOCK:
        raise FoundationError("interview topic must correspond to a real observed stock")
    records = sorted(
        (m for m in state.minds[citizen].memories
         if m.subject in STOCK and (not subject or m.subject == subject)
         and m.value > 0 and m.confidence >= 70
         and m.witness == citizen and state.day - m.turn <= 8),
        key=lambda m: (-m.confidence, -m.turn, -m.value,
                       m.subject, m.position),
    )
    archived = {
        (t.citizen, t.subject, t.x, t.y)
        for t in state.testimonies
    }
    for memory in records:
        claim = Testimony(
            citizen, memory.subject, *memory.position,
            memory.turn, memory.value, memory.confidence,
        )
        key = (claim.citizen, claim.subject, claim.x, claim.y)
        if key not in archived:
            if len(state.testimonies) >= MAX_TESTIMONIES:
                raise FoundationError("public witnessed-testimony ledger is full")
            result = replace(
                state, testimonies=state.testimonies + (claim,),
                interventions=state.interventions + 1,
            )
            validate_intelligence(result, people, world)
            return result, claim
    raise FoundationError("person has no fresh, previously untold first-hand evidence")


def _teach_while_present(
    minds: list[Mind], giver: Person, recipient: Person,
    day: int,
) -> bool:
    """Trusted, co-located people transmit actual observations at lower certainty.

    Each transfer preserves ORIGINAL observation time and witnessing citizen,
    preventing rumor propagation from becoming a fake new eyewitness claim.
    """
    donor = minds[giver.id]
    receiver = minds[recipient.id]
    candidates = sorted(
        (m for m in donor.memories if m.subject in STOCK
         and m.value > 0 and m.confidence > 35),
        key=lambda m: (-m.confidence, -m.turn, -m.value,
                       m.subject, m.position),
    )
    for item in candidates:
        existing = next(
            (m for m in receiver.memories
             if m.subject == item.subject and m.position == item.position),
            None,
        )
        transmitted = max(1, item.confidence - 20)
        if existing is not None and existing.confidence >= transmitted:
            continue
        minds[recipient.id] = _remember(receiver, replace(
            item, confidence=transmitted))
        return True
    return False


def commission_project(
    state: CitizenIntelligence, people: PhysicalSociety, world: TerrainState,
    *, kind: str, x: int, y: int,
) -> tuple[TerrainState, CitizenIntelligence]:
    validate_intelligence(state, people, world)
    if kind not in PROJECT_COSTS or len(state.projects) >= MAX_PROJECTS:
        raise FoundationError("unsupported or over-budget civic construction")
    from .original_world_product_terrain import _coords
    _coords(x, y)
    site = cell_at(world, x, y)
    if site.blocking or site.building:
        raise FoundationError("construction needs accessible empty physical terrain")
    if any(p.status == "open" and (p.x, p.y) == (x, y) for p in state.projects):
        raise FoundationError("same physical building site already commissioned")
    wood, stone, _required_labor = PROJECT_COSTS[kind]
    if world.lumber < wood or world.masonry < stone:
        raise FoundationError("civic construction cannot create unpaid materials")
    project = CivicProject(state.next_project, kind, x, y, wood, stone)
    financed = replace(world, lumber=world.lumber - wood,
                       masonry=world.masonry - stone)
    updated = replace(state, projects=state.projects + (project,),
                      next_project=state.next_project + 1,
                      interventions=state.interventions + 1)
    validate_intelligence(updated, people, financed)
    return financed, updated


def cancel_project(
    state: CitizenIntelligence, people: PhysicalSociety, world: TerrainState,
    project_id: int,
) -> tuple[TerrainState, CitizenIntelligence]:
    validate_intelligence(state, people, world)
    found = [p for p in state.projects if p.project_id == project_id]
    if len(found) != 1 or found[0].status != "open":
        raise FoundationError("only an unfinished real project can be cancelled")
    project = found[0]
    if (world.lumber + project.escrow_wood > 1000
            or world.masonry + project.escrow_stone > 1000):
        raise FoundationError("depot cannot accept returned construction escrow")
    refunded = replace(world, lumber=world.lumber + project.escrow_wood,
                       masonry=world.masonry + project.escrow_stone)
    updated = replace(
        state, projects=tuple(
            replace(p, status="cancelled") if p.project_id == project_id else p
            for p in state.projects
        ), interventions=state.interventions + 1,
    )
    validate_intelligence(updated, people, refunded)
    return refunded, updated


def _plan(person: Person, mind: Mind, state: CitizenIntelligence,
          world: TerrainState) -> tuple[str, int, str, tuple[int, int]]:
    """Deterministic bounded utility choice, personalized and explainable.

    Hunger, injury and carrying precede autonomous production. Orders are
    strong commitments unless a citizen's survival is endangered. Resource
    destinations are reached by real BFS; goal utility never grants travel.
    """
    outstanding = next((o for o in state.orders
                        if o.citizen == person.id and o.status == "open"), None)
    construction = next(
        (p for p in state.projects if p.status == "open"
         and person.id not in p.contributors
         and person.profession in ("builder", "engineer")),
        None,
    )
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
        "socialize": 3 + mind.empathy * 2 + mind.loneliness * 4 - mind.stress,
        "construct": (15 if person.profession in ("builder", "engineer") else 0)
                     + mind.discipline,
        "guard": 4 + mind.prudence * 2,
        "investigate": 2 + mind.curiosity * 2,
    }
    # Deterministic lightweight reinforcement, earned only after measurable
    # prior outcomes. No external provider weights and no subjective labels.
    for index, key in enumerate(GOAL_ORDER):
        scores[key] += mind.learned[index]
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
    if state.civic.active_mandate == "expedition":
        scores["scout"] += 25
        scores["investigate"] += 25
    if state.civic.active_mandate == "conservation":
        if world.lumber < 5 or world.masonry < 4:
            scores["construct"] = -100
    if person.profession in ("builder", "engineer") and not person.cargo:
        scores["construct"] += 25
        if construction:
            scores["construct"] += 105
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
    civic_projects = {p.project_id: p for p in thinking.projects}
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
            at = cell_at(current_world, p.x, p.y)
            if p.cargo_kind == "food" and p.cargo:
                p = replace(p, hunger=max(0, p.hunger - 7),
                            cargo=p.cargo - 1,
                            cargo_kind="" if p.cargo == 1 else "food",
                            health=min(20, p.health + 1))
                operation, resource, quantity = "consume-owned-carried-food", "food", 1
            elif (p.x, p.y) == (0, 0) and current_world.provisions > 0:
                current_world = replace(
                    current_world, provisions=current_world.provisions - 1)
                p = replace(p, hunger=max(0, p.hunger - 7),
                            health=min(20, p.health + 1))
                operation, resource, quantity = "eat-supplied-food", "food", 1
            elif at.food:
                current_world = _write_cell(
                    current_world, replace(at, food=at.food - 1))
                p = replace(p, hunger=max(0, p.hunger - 7),
                            health=min(20, p.health + 1))
                operation, resource, quantity = "eat-actual-wild-harvest", "food", 1
            elif current_world.provisions == 0:
                current_world, p, operation, resource, quantity = (
                    _gather_from_known_world(current_world, p, mind, "food"))
                if operation == "gather":
                    operation = "emergency-food-procurement"
            else:
                p, walked = _physically_move(
                    current_world, p, lambda x, y: (x, y) == (0, 0))
                operation = "seek-real-meal" if walked else "cannot-reach-food"
            if p.hunger >= 15 and quantity == 0:
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
        elif goal == "socialize":
            company = sorted(
                (x for x in people.inhabitants if x.id != p.id and x.health > 0),
                key=lambda x: (abs(x.x - p.x) + abs(x.y - p.y), x.id),
            )
            if company:
                friend = company[0]
                if (p.x, p.y) == (friend.x, friend.y):
                    operation = "spend-real-time-in-conversation"
                else:
                    p, moved = _physically_move(
                        current_world, p,
                        lambda px, py, q=friend: (px, py) == (q.x, q.y),
                    )
                    operation = ("seek-physical-company" if moved
                                 else "social-route-blocked")
            else:
                operation = "isolated-alone"
        elif goal == "construct":
            assigned = next(
                (project for project in civic_projects.values()
                 if project.status == "open" and p.id not in project.contributors
                 and p.profession in ("builder", "engineer")),
                None,
            )
            if assigned:
                location = (assigned.x, assigned.y)
                if (p.x, p.y) != location:
                    p, moved = _physically_move(
                        current_world, p,
                        lambda nx, ny, dest=location: (nx, ny) == dest,
                    )
                    operation = ("travel-to-funded-civic-project" if moved
                                 else "public-worksite-route-inaccessible")
                else:
                    p = replace(p, energy=max(0, p.energy - 2),
                                experience=min(1000, p.experience + 2))
                    contributing = assigned.contributors + (p.id,)
                    done = len(contributing) == PROJECT_COSTS[assigned.kind][2]
                    civic_projects[assigned.project_id] = replace(
                        assigned, contributors=contributing,
                        status="completed" if done else "open",
                    )
                    if done:
                        site = cell_at(current_world, *location)
                        if site.blocking or site.building:
                            raise FoundationError("completed building site was obstructed")
                        current_world = _write_cell(
                            current_world, replace(site, building=assigned.kind))
                        if assigned.kind == "hearth":
                            current_world = replace(
                                current_world,
                                shelter=min(1000, current_world.shelter + 1))
                        operation, resource, quantity = (
                            "cooperatively-completed-funded-civic-project",
                            "structure", 1)
                    else:
                        operation = "verified-distinct-citizen-construction-labor"
            else:
                at = cell_at(current_world, p.x, p.y)
                if (not at.building and not at.blocking
                        and current_world.lumber >= 2
                        and current_world.masonry >= 1):
                    current_world = replace(
                        current_world, lumber=current_world.lumber - 2,
                        masonry=current_world.masonry - 1,
                        shelter=min(1000, current_world.shelter + 1),
                    )
                    current_world = _write_cell(
                        current_world, replace(at, building="hearth"))
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
        delivered_or_helped = {
            "gather", "deliver", "healed-named-patient",
            "verified-distinct-citizen-construction-labor",
            "cooperatively-completed-funded-civic-project",
            "build-real-hearth", "spend-real-time-in-conversation",
            "eat-supplied-food", "consume-owned-carried-food",
            "eat-actual-wild-harvest", "emergency-food-procurement",
            "follow-individual-resource-memory",
            "move-to-observed-stock", "inspect-real-local-geography",
        }
        failed_experiments = {
            "no-reachable-visible-or-remembered-material",
            "public-worksite-route-inaccessible",
            "construction-blocked-by-materials",
            "cannot-reach-food", "patient-inaccessible",
            "social-route-blocked", "depot-stock-full",
        }
        # Pay feedback only for an actual embodied result; idle thought
        # cycles cannot be misinterpreted as model-training success.
        reinforcement = (
            2 if operation in delivered_or_helped
            else -2 if operation in failed_experiments else 0
        )
        policy = list(memory.learned)
        policy_index = GOAL_ORDER.index(goal)
        policy[policy_index] = max(
            -12, min(12, policy[policy_index] + reinforcement))
        memory = replace(memory, learned=tuple(policy))
        if goal == mind.goal:
            age = min(MAX_HISTORY, mind.goal_age + 1)
        else:
            age = 0
        updated_minds.append(replace(
            memory, goal=goal, goal_age=age, objective=(p.x, p.y),
            stress=max(0, min(20, memory.stress
                              + (2 if operation in ("cannot-reach-food",
                                                   "patient-inaccessible") or p.hunger >= 15
                                 else -1))),
            loneliness=min(20, memory.loneliness + 1),
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
            trusted = next(
                (edge.trust for edge in bonds.bonds
                 if edge.left == min(a.id, b.id)
                 and edge.right == max(a.id, b.id)), 0)
            if trusted >= 2:
                _teach_while_present(updated_minds, a, b, thinking.day + 1)
                _teach_while_present(updated_minds, b, a, thinking.day + 1)
            for friend, witness in ((a, b), (b, a)):
                remembered = updated_minds[friend.id]
                updated_minds[friend.id] = _remember(
                    replace(remembered,
                            loneliness=max(0, remembered.loneliness - 6),
                            morale=min(20, remembered.morale + 1)),
                    Memory(thinking.day + 1, "friend",
                           (friend.x, friend.y), 1, 100, witness.id),
                )
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
        projects=tuple(civic_projects[p.project_id] for p in thinking.projects),
        day=next_people.tick,
        meetings=bonds.meetings + max(0, len(bonds.bonds) - len(thinking.bonds)),
        event_count=thinking.event_count + 1,
        event_head=_hash({
            "schema": VERSION, "prior": before.event_head,
            "world": current_world.design_id,
            "minds": [asdict(m) for m in updated_minds],
            "orders": [asdict(completed[o.order_id]) for o in thinking.orders],
            "projects": [asdict(civic_projects[p.project_id])
                         for p in thinking.projects],
            "bonds": [asdict(b) for b in bonds.bonds],
            "thoughts": [asdict(t) for t in thoughts],
        }),
    )
    current_world, next_people, civic, outcomes = settle_civic(
        result.civic, next_people, current_world, result.minds, next_people.tick)
    training, next_people, current_world, lessons = settle_training(
        result.training, next_people, current_world)
    result = replace(
        result, civic=civic, training=training, event_head=_hash({
            "prior-npc-day": result.event_head,
            "civic-state": asdict(civic),
            "civic-outcomes": outcomes,
            "training-state": asdict(training),
            "paid-lessons": lessons,
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
        allowed_fields = set(CitizenIntelligence.__dataclass_fields__)
        if data["checksum"] != _hash(raw) or set(raw) not in (
            allowed_fields, allowed_fields - {"civic"},
            allowed_fields - {"training"},
            allowed_fields - {"civic", "training"},
        ):
            raise FoundationError("cognitive memory integrity mismatch")
        minds = tuple(Mind(
            **{**m, "objective": tuple(m["objective"]),
               "learned": tuple(m["learned"]),
               "memories": tuple(Memory(
                   **{**obs, "position": tuple(obs["position"])}
               ) for obs in m["memories"])}
        ) for m in raw["minds"])
        relationships = tuple(Bond(**b) for b in raw["bonds"])
        orders = tuple(Order(**o) for o in raw["orders"])
        projects = tuple(CivicProject(
            **{**p, "contributors": tuple(p["contributors"])}
        ) for p in raw["projects"])
        testimonies = tuple(Testimony(**statement) for statement in raw["testimonies"])
        civic = (civic_restore({
            "schema": CIVIC_SCHEMA,
            "payload": raw["civic"],
            "checksum": _hash(raw["civic"]),
        }, people, world, people.tick) if "civic" in raw else CivicInstitutions())
        training = (training_restore({
            "schema": TRAINING_SCHEMA,
            "payload": raw["training"],
            "checksum": _hash(raw["training"]),
        }, people, world) if "training" in raw else TeachingLedger())
        state = CitizenIntelligence(
            **{**raw, "minds": minds, "bonds": relationships,
               "orders": orders, "projects": projects,
               "testimonies": testimonies, "civic": civic,
               "training": training}
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
        "civic_projects": [asdict(p) for p in state.projects],
        "first_hand_testimonies": [asdict(t) for t in state.testimonies],
        "public_institutions": civic_report(state.civic),
        "earned_apprenticeships": training_report(state.training),
        "socially_learned_material_observations": sum(
            m.subject in STOCK and m.witness != mind.person_id
            for mind in state.minds for m in mind.memories
        ),
        "completed_constructed_projects": sum(p.status == "completed"
                                              for p in state.projects),
        "active_goals": {m.person_id: m.goal for m in state.minds},
        "health_and_stress": {
            str(m.person_id): {
                "health": people.inhabitants[m.person_id].health,
                "hunger": people.inhabitants[m.person_id].hunger,
                "morale": m.morale, "stress": m.stress,
                "loneliness": m.loneliness, "active_goal": m.goal,
                "earned_behavior_preferences": {
                    label: m.learned[i] for i, label in enumerate(GOAL_ORDER)
                },
            } for m in state.minds
        },
        "report_not_an_llm": True,
    }


def npc_profile(
    state: CitizenIntelligence, people: PhysicalSociety,
    world: TerrainState, person_id: int,
) -> dict:
    """Read-only biography assembled from actual citizen state and memories."""
    validate_intelligence(state, people, world)
    _bounded(person_id, 0, len(people.inhabitants) - 1, "inspected citizen")
    person, mind = people.inhabitants[person_id], state.minds[person_id]
    contacts = [
        {
            "citizen": b.right if b.left == person_id else b.left,
            "affinity": b.affinity, "trust": b.trust,
            "materially_reciprocated_aid": b.reciprocated_aid,
        } for b in state.bonds if person_id in (b.left, b.right)
    ]
    known = sorted(
        (asdict(memory) for memory in mind.memories),
        key=lambda evidence: (
            -evidence["turn"], -evidence["confidence"],
            evidence["subject"], evidence["position"],
        ),
    )
    return {
        "identity": person.id,
        "profession": person.profession,
        "temperament": mind.temperament,
        "individual_drives": {
            "curiosity": mind.curiosity, "empathy": mind.empathy,
            "discipline": mind.discipline, "prudence": mind.prudence,
        },
        "physical_position": (person.x, person.y),
        "carried_stock": {
            "kind": person.cargo_kind,
            "units": person.cargo,
        },
        "needs": {
            "health": person.health, "energy": person.energy,
            "hunger": person.hunger, "morale": mind.morale,
            "stress": mind.stress, "loneliness": mind.loneliness,
        },
        "current_goal": mind.goal,
        "goal_persistence": mind.goal_age,
        "last_visited_objective": mind.objective,
        "decision_count": mind.decisions,
        "learned_action_policies": {
            goal: mind.learned[i] for i, goal in enumerate(GOAL_ORDER)
        },
        "observation_memory": known,
        "social_contacts": contacts,
        "personal_contracts": [
            asdict(o) for o in state.orders if o.citizen == person_id
        ],
        "mentorship_history": [
            asdict(a) for a in state.training.records
            if person_id in (a.mentor, a.apprentice)
        ],
        "construction_contributions": [
            asdict(p) for p in state.projects if person_id in p.contributors
        ],
        "first_hand_testimony": [
            asdict(e) for e in state.testimonies if e.citizen == person_id
        ],
        "provenance": VERSION,
        "individually_simulated_not_a_language_model": True,
    }
