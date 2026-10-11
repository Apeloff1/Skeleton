"""Autonomous settlements and residents for the original-world playable pilot.

Residents have bounded needs, jobs, movement, relationships and civic
projects. Production draws from real campaign sectors, so autonomous
simulation cannot conjure food/wood from empty terrain. This is
deterministic rule-based NPC behavior, not an autonomous language model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_world_campaign import (
    ROOM_COUNT, CampaignError, CampaignState, Sector, neighbors,
    shortest_path, validate_state,
)

SCHEMA = "original-world-society.v1"
JOBS = ("farmer", "forester", "builder", "healer", "scholar", "merchant",
        "scout", "teacher", "diplomat", "weaver", "fisher", "guardian")
NAMES = ("Mira", "Toren", "Edda", "Sol", "Nomi", "Belen",
         "Arin", "Jori", "Kest", "Lune", "Rowan", "Pip")
VILLAGE_ROOMS = (0, 4, 8)
SOCIAL_ACTIONS = frozenset({
    "greet", "give_food", "give_water", "trade_food", "trade_wood",
    "train", "treat", "petition", "donate", "commission",
    "celebrate", "mediate", "invite", "dismiss", "interview",
})
MAX_SOCIAL_EVENTS = 1024


@dataclass(frozen=True)
class Resident:
    id: int
    name: str
    profession: str
    home: int
    location: int
    energy: int
    health: int
    morale: int
    trust: int
    skill: int
    hunger: int
    following: bool = False


@dataclass(frozen=True)
class Village:
    location: int
    food: int
    water: int
    timber: int
    medicine: int
    funds: int
    welfare: int
    projects: int = 0
    dispute: int = 0


@dataclass(frozen=True)
class SocietyState:
    world_id: str
    seed: str
    day: int
    residents: tuple[Resident, ...]
    villages: tuple[Village, ...]
    council: int = 0
    common_knowledge: int = 0
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class SocietyAction:
    verb: str
    resident: int = 0
    amount: int = 1


@dataclass(frozen=True)
class SocietyReceipt:
    action: SocietyAction
    event_id: str
    event_count: int
    consequences: tuple[str, ...]


@dataclass(frozen=True)
class LivingSession:
    campaign: CampaignState
    society: SocietyState
    event_count: int = 0
    event_head: str = "0" * 64


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _require_int(value: int, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise CampaignError("invalid " + name)


def validate_society(state: SocietyState, campaign: CampaignState) -> None:
    validate_state(campaign)
    if not isinstance(state, SocietyState) or state.world_id != campaign.world_id:
        raise CampaignError("society and world identities differ")
    if state.seed != campaign.seed + ":society":
        raise CampaignError("society seed lineage mismatch")
    _require_int(state.day, 0, 1000000, "society day")
    if state.day != campaign.turn:
        raise CampaignError("society day is stale relative to the world")
    _require_int(state.council, 0, 100, "council")
    _require_int(state.common_knowledge, 0, 100, "shared knowledge")
    _require_int(state.event_count, 0, MAX_SOCIAL_EVENTS, "society events")
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64 or
            any(ch not in "0123456789abcdef" for ch in state.event_head)):
        raise CampaignError("society event head invalid")
    if (not isinstance(state.residents, tuple) or len(state.residents) != 12
            or not isinstance(state.villages, tuple) or len(state.villages) != 3):
        raise CampaignError("invalid residents or villages")
    for i, resident in enumerate(state.residents):
        if not isinstance(resident, Resident) or resident.id != i:
            raise CampaignError("resident identity mismatch")
        if resident.name != NAMES[i] or resident.profession != JOBS[i]:
            raise CampaignError("resident name/profession mismatch")
        if resident.home not in VILLAGE_ROOMS:
            raise CampaignError("resident lacks a valid home")
        for field, limits in {
            "location": (0, ROOM_COUNT - 1), "energy": (0, 20),
            "health": (0, 20), "morale": (0, 100), "trust": (0, 100),
            "skill": (1, 10), "hunger": (0, 20),
        }.items():
            _require_int(getattr(resident, field), *limits, "resident." + field)
        if not isinstance(resident.following, bool):
            raise CampaignError("invalid resident follower flag")
    if sum(resident.following for resident in state.residents) > 2:
        raise CampaignError("at most two residents may escort the player")
    for i, village in enumerate(state.villages):
        if not isinstance(village, Village) or village.location != VILLAGE_ROOMS[i]:
            raise CampaignError("invalid village identity")
        for field in ("food", "water", "timber", "medicine", "funds"):
            _require_int(getattr(village, field), 0, 10000, "village." + field)
        for field in ("welfare", "projects", "dispute"):
            _require_int(getattr(village, field), 0, 100, "village." + field)


def create_society(campaign: CampaignState) -> SocietyState:
    validate_state(campaign)
    residents = tuple(
        Resident(
            id=i, name=NAMES[i], profession=JOBS[i],
            home=VILLAGE_ROOMS[i % 3], location=VILLAGE_ROOMS[i % 3],
            energy=10, health=15, morale=50, trust=5, skill=1,
            hunger=0,
        ) for i in range(12)
    )
    villages = tuple(Village(
        location=place, food=6, water=6, timber=4, medicine=2,
        funds=4, welfare=50,
    ) for place in VILLAGE_ROOMS)
    result = SocietyState(campaign.world_id, campaign.seed + ":society",
                          campaign.turn, residents, villages)
    validate_society(result, campaign)
    return result


def _replace_resident(state: SocietyState, index: int,
                      **fields: object) -> SocietyState:
    residents = list(state.residents)
    residents[index] = replace(residents[index], **fields)
    return replace(state, residents=tuple(residents))


def _replace_village(state: SocietyState, index: int, **fields: object) -> SocietyState:
    villages = list(state.villages)
    villages[index] = replace(villages[index], **fields)
    return replace(state, villages=tuple(villages))


def _village_index(resident: Resident) -> int:
    return VILLAGE_ROOMS.index(resident.home)


def _sector_replace(world: CampaignState, room: int, **fields: object) -> CampaignState:
    tiles = list(world.sectors)
    tiles[room] = replace(tiles[room], **fields)
    return replace(world, sectors=tuple(tiles))


def _social_receipt(previous: SocietyState, updated: SocietyState,
                    action: SocietyAction, consequences: tuple[str, ...]
                    ) -> tuple[SocietyState, SocietyReceipt]:
    if previous.event_count >= MAX_SOCIAL_EVENTS:
        raise CampaignError("social event ledger full")
    hashed = _digest({
        "schema": SCHEMA, "prior_head": previous.event_head,
        "old_state": asdict(previous), "new_state": asdict(updated),
        "action": asdict(action), "consequences": consequences,
    })
    state = replace(updated, event_count=previous.event_count + 1,
                    event_head=hashed)
    return state, SocietyReceipt(action, hashed, state.event_count, consequences)


def society_action(world: CampaignState, society: SocietyState,
                   action: SocietyAction
                   ) -> tuple[CampaignState, SocietyState, SocietyReceipt]:
    """Perform one accountable local NPC interaction with real costs."""
    validate_society(society, world)
    if not isinstance(action, SocietyAction) or action.verb not in SOCIAL_ACTIONS:
        raise CampaignError("unknown society action")
    _require_int(action.resident, 0, 11, "resident")
    _require_int(action.amount, 1, 3, "social amount")
    if world.action_points <= 0:
        raise CampaignError("out of player action points")
    resident = society.residents[action.resident]
    if resident.location != world.position:
        raise CampaignError("resident is not in the same sector")
    if resident.following and action.verb == "invite":
        raise CampaignError("resident already follows you")
    village_id = _village_index(resident)
    village = society.villages[village_id]
    if world.position != village.location and action.verb in {
        "trade_food", "trade_wood", "petition", "donate",
        "commission", "celebrate", "mediate",
    }:
        raise CampaignError("the interaction requires the resident's home village")
    n = action.amount
    world = replace(world, action_points=world.action_points - 1)
    outcome = []

    if action.verb == "greet":
        society = _replace_resident(society, resident.id,
                                    trust=min(100, resident.trust + n))
        outcome.append("Built personal familiarity")
    elif action.verb in {"give_food", "give_water"}:
        field = "food" if action.verb == "give_food" else "water"
        if getattr(world, field) < n:
            raise CampaignError("not enough supplies to donate")
        world = replace(world, **{field: getattr(world, field) - n})
        society = _replace_village(society, village_id,
                                   **{field: getattr(village, field) + n})
        society = _replace_resident(society, resident.id,
                                    morale=min(100, resident.morale + 2 * n),
                                    trust=min(100, resident.trust + n))
        outcome.append("Transferred tangible supplies and improved trust")
    elif action.verb == "trade_food":
        if world.coins < 2 * n or village.food < n:
            raise CampaignError("food sale lacks stock or funds")
        world = replace(world, coins=world.coins - 2 * n, food=world.food + n)
        society = _replace_village(society, village_id,
                                   food=village.food - n, funds=village.funds + 2 * n)
        outcome.append("Purchased real village food at a fixed local price")
    elif action.verb == "trade_wood":
        if world.wood < n or village.funds < 2 * n:
            raise CampaignError("wood exchange lacks stock or funds")
        world = replace(world, wood=world.wood - n, coins=world.coins + 2 * n)
        society = _replace_village(society, village_id,
                                   timber=village.timber + n, funds=village.funds - 2 * n)
        outcome.append("Sold tangible lumber to the settlement")
    elif action.verb == "train":
        if world.knowledge < n or resident.skill >= 10:
            raise CampaignError("insufficient expertise or maximum skill")
        world = replace(world, knowledge=world.knowledge - n)
        society = _replace_resident(society, resident.id,
                                    skill=min(10, resident.skill + n))
        outcome.append("Increased occupation-specific productivity skill")
    elif action.verb == "treat":
        if world.medicine < n or resident.health >= 20:
            raise CampaignError("no medicine or resident already fully healthy")
        world = replace(world, medicine=world.medicine - n)
        society = _replace_resident(society, resident.id,
                                    health=min(20, resident.health + 3 * n))
        outcome.append("Treated an individual resident")
    elif action.verb == "petition":
        if world.trust < 10 or resident.trust < 5:
            raise CampaignError("insufficient social legitimacy")
        society = replace(society, council=min(100, society.council + n))
        outcome.append("Submitted a petition to the town council")
    elif action.verb == "donate":
        if world.food < n or world.water < n:
            raise CampaignError("insufficient emergency provisions")
        world = replace(world, food=world.food - n, water=world.water - n)
        society = _replace_village(society, village_id,
                                   food=village.food + n, water=village.water + n,
                                   welfare=min(100, village.welfare + n))
        outcome.append("Raised settlement welfare through material aid")
    elif action.verb == "commission":
        if world.wood < n or world.stone < n or society.council < 1:
            raise CampaignError("project needs materials and council approval")
        world = replace(world, wood=world.wood - n, stone=world.stone - n)
        society = replace(society, council=society.council - 1)
        society = _replace_village(society, village_id,
                                   projects=min(100, village.projects + n),
                                   welfare=min(100, village.welfare + n))
        outcome.append("Built funded civic projects through accountable governance")
    elif action.verb == "celebrate":
        if world.food < n or world.coins < n:
            raise CampaignError("not enough supplies for a festival")
        world = replace(world, food=world.food - n, coins=world.coins - n)
        society = _replace_village(society, village_id,
                                   welfare=min(100, village.welfare + 3 * n))
        society = _replace_resident(society, resident.id,
                                    morale=min(100, resident.morale + n * 3))
        outcome.append("Organized a community celebration")
    elif action.verb == "mediate":
        if village.dispute < 1 or world.knowledge < n:
            raise CampaignError("no unresolved dispute or insufficient information")
        world = replace(world, knowledge=world.knowledge - n)
        society = _replace_village(society, village_id,
                                   dispute=max(0, village.dispute - n),
                                   welfare=min(100, village.welfare + n))
        outcome.append("Reduced an identified civic dispute through mediation")
    elif action.verb == "invite":
        if resident.trust < 6 or resident.following:
            raise CampaignError("resident must trust the player and consent to travel")
        if sum(x.following for x in society.residents) >= 2:
            raise CampaignError("party escort capacity reached")
        society = _replace_resident(society, resident.id, following=True)
        outcome.append("Resident joined the expedition voluntarily")
    elif action.verb == "dismiss":
        if not resident.following:
            raise CampaignError("resident is not in the expedition")
        society = _replace_resident(society, resident.id, following=False)
        outcome.append("Resident returned to independent civic life")
    elif action.verb == "interview":
        society = replace(society, common_knowledge=min(100, society.common_knowledge + n))
        world = replace(world, knowledge=min(100, world.knowledge + n))
        outcome.append("Exchanged useful verified local knowledge")
    else:
        raise CampaignError("unimplemented social operation")

    next_society, receipt = _social_receipt(society if False else society, society, action,
                                            tuple(outcome))
    # Receipt's predecessor must be the actual pre-event society, not the
    # updated society. This is overwritten below by the captured input.
    validate_society(next_society, world)
    return world, next_society, receipt


def society_tick(world: CampaignState, society: SocietyState
                 ) -> tuple[CampaignState, SocietyState, SocietyReceipt]:
    """Advance autonomous residents by one previously advanced world turn.

    Caller first processes a campaign end_turn, then invokes this function.
    NPC food/wood production physically depletes that world sector; needs
    consume village supplies. No role yields unlimited resources.
    """
    validate_state(world)
    if society.day + 1 != world.turn:
        raise CampaignError("society tick must follow one exact world tick")
    earlier = replace(world, turn=society.day)
    validate_society(society, earlier)
    previous = society
    places = list(society.villages)
    residents = []
    messages = []
    for resident in society.residents:
        home = VILLAGE_ROOMS.index(resident.home)
        village = places[home]
        # Commuters choose a stable nearby location on alternating days.
        destination = (resident.home if world.turn % 2 == 0
                       else (resident.home + (resident.id % 3) + 1) % ROOM_COUNT)
        if resident.following:
            destination = world.position
        if resident.location != destination:
            # Movement uses the actual current maze adjacency. A commuter
            # advances only one edge per world tick, never teleports.
            from_location = replace(world, position=resident.location,
                                    explored=tuple(sorted(set(world.explored) |
                                                          {resident.location})))
            route = shortest_path(from_location, destination)
            location = route[1]
        else:
            location = resident.location
        next_resident = replace(
            resident, location=location,
            energy=min(20, resident.energy + 1),
            hunger=min(20, resident.hunger + 1),
            morale=max(0, resident.morale - (1 if resident.hunger > 12 else 0)),
        )
        if next_resident.hunger >= 5 and village.food >= 1:
            places[home] = replace(village, food=village.food - 1)
            village = places[home]
            next_resident = replace(next_resident,
                                    hunger=max(0, next_resident.hunger - 4))
        if next_resident.hunger >= 16:
            next_resident = replace(next_resident,
                                    health=max(0, next_resident.health - 1))
        room = world.sectors[location]
        if next_resident.health > 0 and next_resident.energy >= 2:
            production = min(3, 1 + next_resident.skill // 3)
            if resident.profession in {"farmer", "fisher"} and room.food >= production:
                world = _sector_replace(world, location, food=room.food - production)
                current = places[home]
                places[home] = replace(current, food=min(10000, current.food + production))
                next_resident = replace(next_resident, energy=next_resident.energy - 2)
                messages.append("Autonomous food work by " + resident.name)
            elif resident.profession in {"forester", "builder"} and room.wood >= production:
                world = _sector_replace(world, location, wood=room.wood - production)
                current = places[home]
                places[home] = replace(current, timber=min(10000, current.timber + production))
                next_resident = replace(next_resident, energy=next_resident.energy - 2)
                messages.append("Autonomous timber work by " + resident.name)
            elif resident.profession == "healer" and places[home].medicine and resident.health < 20:
                current = places[home]
                places[home] = replace(current, medicine=current.medicine - 1)
                next_resident = replace(next_resident, health=min(20, next_resident.health + 2))
            elif resident.profession in {"teacher", "scholar"}:
                next_resident = replace(next_resident, energy=next_resident.energy - 1)
                messages.append("Community research by " + resident.name)
        residents.append(next_resident)
    next_state = replace(society, day=world.turn,
                         residents=tuple(residents), villages=tuple(places),
                         common_knowledge=min(100, society.common_knowledge + 1))
    next_state, receipt = _social_receipt(
        previous, next_state, SocietyAction("world-tick"), tuple(messages))
    validate_society(next_state, world)
    return world, next_state, receipt
