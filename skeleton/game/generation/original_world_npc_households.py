"""Bounded, generational original-world households with material accountability.

An established partnership with recorded mutual trust may sponsor a planned
new dependent. Three elapsed world days, an actual built hearth, finite food
and clean water, healthy present caregivers and population capacity are
required. A new persistent body enters society only at completion; it is not
an instant employment/population counter and requires further daily care.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_agents import Person, PhysicalSociety, MAX_AGENTS, validate_society
from .original_world_product_terrain import TerrainState, cell_at

SCHEMA = "original-world-npc-intergenerational-households.v1"
MAX_HOUSEHOLDS = 12
GESTATION = 3
FOOD_ESCROW = 3
WATER_ESCROW = 2
INITIAL_ADULT_AGE = 24
CHILDCARE_TURNS = 4


@dataclass(frozen=True)
class Household:
    family_id: int
    caregiver_a: int
    caregiver_b: int
    opened_day: int
    expected_day: int
    child_id: int = -1
    status: str = "awaiting"
    food_reserved: int = FOOD_ESCROW
    water_reserved: int = WATER_ESCROW


@dataclass(frozen=True)
class HouseholdState:
    ages: tuple[int, ...] = ()
    families: tuple[Household, ...] = ()
    day: int = 0
    next_family: int = 0
    completed: int = 0
    head: str = "0" * 64


def _hash(v: object) -> str:
    return sha256(json.dumps(v, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def household_origin(people: PhysicalSociety) -> HouseholdState:
    return HouseholdState(
        ages=(INITIAL_ADULT_AGE,) * len(people.inhabitants),
        day=people.tick,
    )


def validate_households(
    state: HouseholdState, people: PhysicalSociety, world: TerrainState,
) -> None:
    validate_society(people, world)
    if not isinstance(state, HouseholdState):
        raise FoundationError("invalid generational households")
    if state.day != people.tick:
        raise FoundationError("household age clock differs from real world")
    if len(state.ages) != len(people.inhabitants) or not isinstance(state.ages, tuple):
        raise FoundationError("households cannot omit bodies or invent ages")
    for age in state.ages:
        if type(age) is not int or not 0 <= age <= 1000:
            raise FoundationError("invalid persistent individual age")
    if not isinstance(state.families, tuple) or len(state.families) > MAX_HOUSEHOLDS:
        raise FoundationError("unbounded original household register")
    for n in ("day", "next_family", "completed"):
        x = getattr(state, n)
        if type(x) is not int or not 0 <= x <= 1000:
            raise FoundationError("invalid household timeline accounting")
    unique, children = set(), set()
    completed = 0
    for household in state.families:
        if not isinstance(household, Household):
            raise FoundationError("malformed household proof")
        if (type(household.family_id) is not int or household.family_id in unique
                or not 0 <= household.family_id < state.next_family):
            raise FoundationError("household reused another family's identity")
        unique.add(household.family_id)
        if household.status not in ("awaiting", "established", "cancelled"):
            raise FoundationError("invalid planned family state")
        for parent in (household.caregiver_a, household.caregiver_b):
            if type(parent) is not int or not 0 <= parent < len(people.inhabitants):
                raise FoundationError("unknown or absent registered caregiver")
        if household.caregiver_a == household.caregiver_b:
            raise FoundationError("a single person cannot invent a second caregiver")
        if (type(household.opened_day) is not int
                or not 0 <= household.opened_day <= state.day
                or household.expected_day != household.opened_day + GESTATION):
            raise FoundationError("future/fraudulent family preparation date")
        if (household.food_reserved != FOOD_ESCROW
                or household.water_reserved != WATER_ESCROW):
            raise FoundationError("family formation missing physical escrow")
        if household.status == "established":
            completed += 1
            if (state.day < household.expected_day
                    or not 0 <= household.child_id < len(people.inhabitants)
                    or household.child_id in children
                    or household.child_id in (
                        household.caregiver_a, household.caregiver_b)):
                raise FoundationError("childless or duplicated family certification")
            children.add(household.child_id)
        elif household.child_id != -1:
            raise FoundationError("nonestablished household assigned invented child")
    if completed != state.completed:
        raise FoundationError("unearned generational milestone counter")
    if (not isinstance(state.head, str) or len(state.head) != 64
            or any(c not in "0123456789abcdef" for c in state.head)):
        raise FoundationError("invalid generational evidence receipt")


def _seal(before: HouseholdState, after: HouseholdState, action: str) -> HouseholdState:
    return replace(after, head=_hash({
        "version": SCHEMA, "before": asdict(before),
        "after": asdict(after), "action": action, "prior": before.head,
    }))


def establish_household(
    state: HouseholdState, people: PhysicalSociety, world: TerrainState,
    *, caregiver_a: int, caregiver_b: int,
    affinity: int, mutual_trust: int,
) -> tuple[TerrainState, HouseholdState]:
    validate_households(state, people, world)
    if (type(caregiver_a) is not int or type(caregiver_b) is not int
            or caregiver_a == caregiver_b
            or not 0 <= caregiver_a < len(people.inhabitants)
            or not 0 <= caregiver_b < len(people.inhabitants)):
        raise FoundationError("two existing distinct caregivers required")
    first, second = (people.inhabitants[caregiver_a],
                     people.inhabitants[caregiver_b])
    if (state.ages[caregiver_a] < 12 or state.ages[caregiver_b] < 12
            or first.health < 12 or second.health < 12
            or first.hunger >= 8 or second.hunger >= 8):
        raise FoundationError("only healthy adult residents can sustain a new dependent")
    if mutual_trust < 2 or affinity < 2:
        raise FoundationError("household requires a mutually evidenced positive relationship")
    if (abs(first.x) + abs(first.y) > 1
            or abs(second.x) + abs(second.y) > 1):
        raise FoundationError("both caregivers must be present at the community hearth")
    if (cell_at(world, 0, 0).building != "hearth" or world.shelter < 1
            or world.provisions < FOOD_ESCROW or world.freshwater < WATER_ESCROW):
        raise FoundationError("new family needs built shelter and finite nourishment")
    if (len(people.inhabitants) >= MAX_AGENTS
            or len(state.families) >= MAX_HOUSEHOLDS):
        raise FoundationError("bounded physical population cannot expand")
    if any(x.status == "awaiting" for x in state.families):
        raise FoundationError("existing dependent preparation must finish first")
    family = Household(
        state.next_family, caregiver_a, caregiver_b,
        people.tick, people.tick + GESTATION,
    )
    resources = replace(
        world, provisions=world.provisions - FOOD_ESCROW,
        freshwater=world.freshwater - WATER_ESCROW,
    )
    updated = _seal(state, replace(
        state, families=state.families + (family,),
        next_family=state.next_family + 1,
    ), "fund-family")
    validate_households(updated, people, resources)
    return resources, updated


def cancel_household(
    state: HouseholdState, people: PhysicalSociety, world: TerrainState,
    household_id: int,
) -> tuple[TerrainState, HouseholdState]:
    validate_households(state, people, world)
    family = next((f for f in state.families
                   if f.family_id == household_id and f.status == "awaiting"), None)
    if family is None:
        raise FoundationError("only an unfinished dependent plan can be cancelled")
    if (world.provisions + family.food_reserved > 1000
            or world.freshwater + family.water_reserved > 1000):
        raise FoundationError("warehouse cannot accept returned family escrow")
    returned = replace(
        world, provisions=world.provisions + family.food_reserved,
        freshwater=world.freshwater + family.water_reserved,
    )
    result = _seal(state, replace(
        state, families=tuple(
            replace(f, status="cancelled") if f.family_id == household_id else f
            for f in state.families
        )), "return-family-escrow")
    validate_households(result, people, returned)
    return returned, result


def settle_households(
    state: HouseholdState, people: PhysicalSociety, world: TerrainState,
) -> tuple[TerrainState, PhysicalSociety, HouseholdState,
           tuple[Household, ...]]:
    # The bodies have already acted and advanced by exactly one day.
    # Validate the incoming family ledger against the immediately previous
    # world clock before deriving new ages or births.
    if people.tick != state.day + 1:
        raise FoundationError("generational settlement must advance exactly one real world day")
    validate_households(state, replace(people, tick=state.day), world)
    aged = tuple(min(1000, n + 1) for n in state.ages)
    residents = list(people.inhabitants)
    families = list(state.families)
    new_people = []
    for i, family in enumerate(families):
        if family.status != "awaiting" or people.tick < family.expected_day:
            continue
        a, b = people.inhabitants[family.caregiver_a], people.inhabitants[family.caregiver_b]
        # A family can only grow from an actually accessible and occupied
        # warm settlement. Unmet conditions keep its escrow committed.
        if (a.health < 1 or b.health < 1 or world.shelter < 1
                or cell_at(world, 0, 0).building != "hearth"
                or len(residents) >= MAX_AGENTS):
            continue
        identity = len(residents)
        newcomer = Person(
            identity, "caretaker", 0, 0,
            energy=8, hunger=0, health=18, relationships=4,
        )
        residents.append(newcomer)
        aged += (0,)
        record = replace(family, status="established", child_id=identity)
        families[i] = record
        new_people.append(record)
    result_people = replace(people, inhabitants=tuple(residents))
    updated = _seal(state, replace(
        state, ages=aged, families=tuple(families),
        day=people.tick, completed=state.completed + len(new_people),
    ), "generational-world-day-" + str(people.tick))
    validate_households(updated, result_people, world)
    return world, result_people, updated, tuple(new_people)


def household_save(state: HouseholdState) -> dict:
    raw = asdict(state)
    return {"schema": SCHEMA, "payload": raw, "checksum": _hash(raw)}


def household_restore(data: dict, people: PhysicalSociety,
                      world: TerrainState) -> HouseholdState:
    try:
        if (not isinstance(data, dict) or set(data) != {
                "schema", "payload", "checksum"}
                or data["schema"] != SCHEMA or
                data["checksum"] != _hash(data["payload"])):
            raise FoundationError("invalid family history signature")
        raw = data["payload"]
        if set(raw) != set(HouseholdState.__dataclass_fields__):
            raise FoundationError("unknown family history shape")
        families = tuple(Household(**x) for x in raw["families"])
        value = HouseholdState(**{
            **raw, "families": families, "ages": tuple(raw["ages"]),
        })
        validate_households(value, people, world)
        return value
    except (ValueError, KeyError, AttributeError, TypeError) as exc:
        raise FoundationError("family history save rejected") from exc


def household_report(state: HouseholdState) -> dict:
    return {
        "schema": SCHEMA,
        "individual_ages": list(state.ages),
        "families": [asdict(f) for f in state.families],
        "actually_established_dependents": state.completed,
        "protected_childcare_turns": CHILDCARE_TURNS,
    }
