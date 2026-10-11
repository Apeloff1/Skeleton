"""Era-aware, resource-conserving, bounded-cost NPC population streaming.

40 authored era identifiers map to an explicit local cognition budget and a
larger sparse *cohort* population. Only 1..32 named citizens own full minds,
memory, physical collisions, families, duties and local NPC turn processing.
Background districts have anchored positions, real finite census, food stores,
health and morale. They do not impersonate individually simulated people.

The cohort scheduler updates a limited number of districts each world turn,
settling elapsed consumption arithmetically and never creating supplies.
Game actions dispatch escrow-backed food caravans between local warehouse and
regional districts, with delivery latency and capacity checks. Save/load
preserves every pending caravan, material transfer and deterministic cursor.
This is simulation LOD, not thousands of high-fidelity NPC brains.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_era_runtime import ERA_LEVELS
from .original_world_product_agents import PhysicalSociety, MAX_AGENTS, validate_society
from .original_world_product_terrain import (
    TerrainState, cell_at, validate_terrain,
)

SCHEMA = "original-world-era-population.v1"
MAX_DISTRICTS = 64
MAX_CARAVANS = 24
MAX_HISTORY = 1000
MAX_POPULATION = 16384
MAX_FOOD = 2000000
ERA_ROLES = {
    0: ("forager", "scout", "naturalist", "caretaker", "guardian"),
    1: ("forager", "scout", "naturalist", "caretaker", "guardian",
        "farmer", "builder"),
    2: ("forager", "scout", "naturalist", "caretaker", "guardian",
        "farmer", "builder", "mason", "courier"),
    3: ("forager", "scout", "naturalist", "caretaker", "guardian",
        "farmer", "builder", "mason", "courier", "forester", "healer"),
    4: ("forager", "scout", "naturalist", "caretaker", "guardian",
        "farmer", "builder", "mason", "courier", "forester",
        "healer", "engineer"),
}


def permitted_roles(era: str) -> tuple[str, ...]:
    level = era_budget(era).technology
    return ERA_ROLES[min(level, 4)]


def inhabitant_role_profile(
    state: PhysicalSociety, era: str,
) -> PhysicalSociety:
    roles = permitted_roles(era)
    people = tuple(replace(p, profession=roles[i % len(roles)])
                   for i, p in enumerate(state.inhabitants))
    return replace(state, inhabitants=people)



@dataclass(frozen=True)
class EraBudget:
    era: str
    technology: int
    full_npc_limit: int
    district_limit: int
    background_limit: int
    district_updates: int
    render_budget: int
    visibility_radius: int
    caravan_speed: int


@dataclass(frozen=True)
class District:
    id: int
    x: int
    y: int
    population: int
    pantry: int
    morale: int = 10
    hardship: int = 0
    deaths: int = 0
    days_simulated: int = 0
    food_fraction: int = 0
    # food_fraction counts owed 1/16 food units; never rounded away.
    last_day: int = 0


@dataclass(frozen=True)
class Caravan:
    id: int
    district: int
    direction: str
    food: int
    departed: int
    arrives: int
    status: str = "travelling"


@dataclass(frozen=True)
class EraPopulation:
    era: str
    world_id: str
    districts: tuple[District, ...]
    caravans: tuple[Caravan, ...] = ()
    day: int = 0
    cursor: int = 0
    caravan_seq: int = 0
    food_consumed: int = 0
    food_lost: int = 0
    total_deaths: int = 0
    updates: int = 0
    event_head: str = "0" * 64
    fidelity: str = "balanced"


def _hash(data: object) -> str:
    return sha256(json.dumps(data, ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def _check_int(value: object, lo: int, hi: int, label: str) -> None:
    if type(value) is not int or not lo <= value <= hi:
        raise FoundationError("invalid era population " + label)


def era_budget(era: str) -> EraBudget:
    if not isinstance(era, str) or era not in ERA_LEVELS:
        raise FoundationError("unknown authored historical or fictional era")
    tier = ERA_LEVELS[era]
    if era in ("primordial-earth", "early-life"):
        # No fictional humans are counted as paleontological inhabitants.
        return EraBudget(era, tier, 1, 0, 0, 0, 0, 0, 1)
    if tier == 0:
        return EraBudget(era, tier, 8, 2, 24, 1, 4, 5, 1)
    direct = min(MAX_AGENTS, 8 + 3 * tier)
    districts = min(MAX_DISTRICTS, 2 + 6 * tier)
    people = min(MAX_POPULATION, 32 * (tier + 1) ** 2 * (tier + 2))
    updates = min(8, 1 + tier // 2)
    return EraBudget(
        era, tier, direct, districts, people,
        updates, min(64, 6 + tier * 6),
        min(14, 5 + tier),
        min(8, 1 + tier // 2),
    )


def _site(world: TerrainState, index: int) -> tuple[int, int]:
    """Stable actual passable coordinate outside the player's home tile."""
    r = sha256(f"{world.design_id}:district:{index}".encode()).digest()
    for distance in range(4, 18):
        for turn in range(8):
            x = (r[0] + 3 * index + turn * 7) % (2 * distance + 1) - distance
            y = (r[1] + 5 * index + turn * 11) % (2 * distance + 1) - distance
            if (x, y) == (0, 0):
                continue
            tile = cell_at(world, x, y)
            if not tile.blocking:
                return x, y
    raise FoundationError("could not find a real traversable district anchor")


def _allocation(people: int, count: int) -> tuple[int, ...]:
    if count == 0:
        return ()
    return tuple(people // count + (i < people % count)
                 for i in range(count))


def create_era_population(
    world: TerrainState, people: PhysicalSociety, era: str,
    *, fidelity: str = "balanced",
) -> EraPopulation:
    validate_society(people, world)
    budget = era_budget(era)
    if fidelity not in FIDELITY_MODES:
        raise FoundationError("invalid local cognitive hardware budget")
    if len(people.inhabitants) > budget.full_npc_limit:
        raise FoundationError("requested detailed NPCs exceed era/CPU fidelity budget")
    allowed_roles = permitted_roles(era)
    if any(p.profession not in allowed_roles for p in people.inhabitants):
        raise FoundationError("anachronistic NPC professions for selected technology era")
    if budget.background_limit == 0:
        result = EraPopulation(era, world.design_id, (), day=people.tick,
                               fidelity=fidelity)
        validate_population(result, people, world)
        return result
    allocations = _allocation(budget.background_limit, budget.district_limit)
    districts = []
    sites = set()
    for index, count in enumerate(allocations):
        x, y = _site(world, index)
        # Distinct physical district anchors, not duplicated population pins.
        while (x, y) in sites:
            index_probe = index + len(sites) * 13
            x, y = _site(world, index_probe)
        sites.add((x, y))
        # These are initial locally authored *regional* stores, separate from
        # the player's starter supplies. They can run out; no daily minting.
        districts.append(District(index, x, y, count, count * 6))
    result = EraPopulation(
        era, world.design_id, tuple(districts), day=people.tick,
        fidelity=fidelity,
    )
    validate_population(result, people, world)
    return result


def validate_population(
    state: EraPopulation, people: PhysicalSociety, world: TerrainState,
) -> None:
    validate_society(people, world)
    if not isinstance(state, EraPopulation) or state.world_id != world.design_id:
        raise FoundationError("era population belongs to another physical world")
    budget = era_budget(state.era)
    if state.fidelity not in FIDELITY_MODES:
        raise FoundationError("unrecognized active-brain hardware preset")
    if (len(people.inhabitants) > budget.full_npc_limit
            or len(state.districts) != budget.district_limit
            or any(p.profession not in permitted_roles(state.era)
                   for p in people.inhabitants)):
        raise FoundationError("era detailed and background budgets disagree")
    if state.day != people.tick:
        raise FoundationError("era population tick is not the NPC world clock")
    for label, value, maximum in (
        ("clock", state.day, MAX_HISTORY),
        ("cursor", state.cursor, MAX_HISTORY * MAX_DISTRICTS),
        ("sequence", state.caravan_seq, MAX_HISTORY),
        ("food consumption", state.food_consumed, MAX_FOOD),
        ("food lost", state.food_lost, MAX_FOOD),
        ("mortality", state.total_deaths, MAX_POPULATION),
        ("district work", state.updates, MAX_HISTORY * 8),
    ):
        _check_int(value, 0, maximum, label)
    if not state.districts and state.cursor != 0:
        raise FoundationError("empty region has invalid scheduler cursor")
    if not isinstance(state.districts, tuple):
        raise FoundationError("invalid sparse district table")
    count, deaths, points = 0, 0, set()
    for i, d in enumerate(state.districts):
        if not isinstance(d, District) or d.id != i:
            raise FoundationError("district identity collision")
        site = (d.x, d.y)
        if site in points or cell_at(world, *site).blocking:
            raise FoundationError("district site duplicates or occupies impassable terrain")
        points.add(site)
        for name, v, high in (
            ("census", d.population, MAX_POPULATION),
            ("pantry", d.pantry, MAX_FOOD),
            ("morale", d.morale, 20),
            ("hardship", d.hardship, 1000),
            ("dead", d.deaths, MAX_POPULATION),
            ("simulated days", d.days_simulated, MAX_HISTORY),
            ("fractional ration", d.food_fraction, 15),
            ("last serviced", d.last_day, state.day),
        ):
            _check_int(v, 0, high, name)
        count += d.population + d.deaths
        deaths += d.deaths
        if d.days_simulated != d.last_day:
            raise FoundationError("district cannot conceal deferred simulated days")
    if count != budget.background_limit or deaths != state.total_deaths:
        raise FoundationError("background census illegally creates or loses residents")
    if (not isinstance(state.caravans, tuple)
            or len(state.caravans) > MAX_CARAVANS):
        raise FoundationError("unbounded material transport")
    ids = set()
    for c in state.caravans:
        if not isinstance(c, Caravan):
            raise FoundationError("invalid transport order")
        _check_int(c.id, 0, MAX_HISTORY, "caravan ID")
        _check_int(c.district, 0, max(0, len(state.districts) - 1), "caravan district")
        _check_int(c.food, 1, 3, "transport quantity")
        _check_int(c.departed, 0, state.day, "departure")
        _check_int(c.arrives, c.departed + 1, MAX_HISTORY, "arrival")
        if (c.status not in ("travelling", "delivered")
                or c.direction not in ("to-region", "to-player")
                or c.id in ids or c.id >= state.caravan_seq):
            raise FoundationError("transport order identity or status mismatch")
        if c.status == "delivered" and c.arrives > state.day:
            raise FoundationError("future food delivery forged")
        ids.add(c.id)
    if (not isinstance(state.event_head, str) or len(state.event_head) != 64
            or any(ch not in "0123456789abcdef" for ch in state.event_head)):
        raise FoundationError("invalid era population receipt chain")


def _seal(before: EraPopulation, after: EraPopulation, action: str) -> EraPopulation:
    return replace(after, event_head=_hash({
        "schema": SCHEMA, "previous": before.event_head, "action": action,
        "before": asdict(before), "after": asdict(after),
    }))


def dispatch_food(
    state: EraPopulation, people: PhysicalSociety, world: TerrainState,
    *, district: int, amount: int, direction: str,
) -> tuple[EraPopulation, TerrainState]:
    validate_population(state, people, world)
    _check_int(amount, 1, 3, "shipment amount")
    if type(district) is not int or not 0 <= district < len(state.districts):
        raise FoundationError("not a physically anchored district")
    if direction not in ("to-region", "to-player"):
        raise FoundationError("shipment lacks source and destination")
    if len(state.caravans) >= MAX_CARAVANS or state.caravan_seq >= MAX_HISTORY:
        raise FoundationError("transport manifest at capacity")
    d = state.districts[district]
    if direction == "to-region":
        if world.provisions < amount:
            raise FoundationError("cannot send more player food than physically owned")
        world = replace(world, provisions=world.provisions - amount)
    else:
        if d.pantry < amount:
            raise FoundationError("regional ration warehouse has insufficient stores")
        districts = list(state.districts)
        districts[district] = replace(d, pantry=d.pantry - amount)
        state = replace(state, districts=tuple(districts))
    distance = abs(d.x) + abs(d.y)
    travel = max(1, (distance + era_budget(state.era).caravan_speed - 1)
                 // era_budget(state.era).caravan_speed)
    if state.day + travel > MAX_HISTORY:
        raise FoundationError("transport arrives after world simulation expiry")
    record = Caravan(state.caravan_seq, district, direction, amount,
                     state.day, state.day + travel)
    result = _seal(state, replace(
        state, caravans=state.caravans + (record,),
        caravan_seq=state.caravan_seq + 1,
    ), "escrow-caravan-" + direction)
    validate_population(result, people, world)
    return result, world


def tick_population(
    state: EraPopulation, people: PhysicalSociety, world: TerrainState,
) -> tuple[EraPopulation, TerrainState, tuple[str, ...]]:
    if people.tick != state.day + 1:
        raise FoundationError("regional simulation must advance exactly one world day")
    validate_population(state, replace(people, tick=state.day), world)
    current = state.day + 1
    budget = era_budget(state.era)
    districts = list(state.districts)
    manifests = []
    receipts = []
    # Arrivals never create goods: every shipment was already debited from
    # its source at dispatch, and remains in transit if destination is full.
    for manifest in state.caravans:
        if manifest.status != "travelling" or manifest.arrives > current:
            manifests.append(manifest)
            continue
        d = districts[manifest.district]
        if manifest.direction == "to-region":
            if d.pantry + manifest.food > MAX_FOOD:
                manifests.append(manifest)
                continue
            districts[d.id] = replace(d, pantry=d.pantry + manifest.food)
        else:
            if world.provisions + manifest.food > 1000:
                manifests.append(manifest)
                continue
            world = replace(world, provisions=world.provisions + manifest.food)
        manifests.append(replace(manifest, status="delivered"))
        receipts.append(f"Caravan {manifest.id} arrived with {manifest.food} real rations")
    consumed = state.food_consumed
    deaths = state.total_deaths
    updated_count = 0
    if districts:
        slots = min(budget.district_updates, len(districts))
        for i in range(slots):
            index = (state.cursor + i) % len(districts)
            district = districts[index]
            elapsed = current - district.last_day
            if elapsed <= 0:
                continue
            # Each 16 residents consume one ration per simulated day.
            # Keep remainder for the next wave; no free rounding.
            owed = district.food_fraction + district.population * elapsed
            rations, remainder = divmod(owed, 16)
            eaten = min(district.pantry, rations)
            shortage = rations - eaten
            lost = min(district.population, shortage // 3)
            hardship = min(1000, district.hardship + shortage)
            morale = max(0, min(20, district.morale +
                                (1 if shortage == 0 else -min(shortage, 3))))
            districts[index] = replace(
                district, pantry=district.pantry - eaten,
                population=district.population - lost,
                deaths=district.deaths + lost,
                morale=morale, hardship=hardship,
                food_fraction=remainder if shortage == 0 else 0,
                days_simulated=current, last_day=current,
            )
            consumed += eaten
            deaths += lost
            updated_count += 1
            if shortage:
                receipts.append(
                    f"District {index} lacked {shortage} rations; "
                    f"{lost} actual census losses"
                )
    result = _seal(state, replace(
        state, day=current,
        cursor=(state.cursor + updated_count) % len(districts) if districts else 0,
        districts=tuple(districts),
        caravans=tuple(manifests),
        food_consumed=consumed, total_deaths=deaths,
        updates=state.updates + updated_count,
    ), "regional-day-" + str(current))
    validate_population(result, people, world)
    return result, world, tuple(receipts)


def population_save(state: EraPopulation) -> dict:
    raw = asdict(state)
    return {"schema": SCHEMA, "payload": raw, "checksum": _hash(raw)}


def population_restore(
    envelope: dict, people: PhysicalSociety, world: TerrainState,
) -> EraPopulation:
    try:
        if (not isinstance(envelope, dict) or set(envelope) != {
                "schema", "payload", "checksum"
            } or envelope["schema"] != SCHEMA
                or envelope["checksum"] != _hash(envelope["payload"])):
            raise FoundationError("tampered or unsupported population save")
        raw = envelope["payload"]
        fields = set(EraPopulation.__dataclass_fields__)
        if set(raw) not in (fields, fields - {"fidelity"}):
            raise FoundationError("unexpected population archive")
        districts = tuple(District(**d) for d in raw["districts"])
        caravans = tuple(Caravan(**c) for c in raw["caravans"])
        result = EraPopulation(**{**raw, "districts": districts,
                                  "caravans": caravans})
        validate_population(result, people, world)
        return result
    except (TypeError, KeyError, ValueError, AttributeError) as exc:
        raise FoundationError("invalid era population archive") from exc


def population_report(state: EraPopulation, local: int) -> dict:
    b = era_budget(state.era)
    count = sum(d.population for d in state.districts)
    return {
        "schema": SCHEMA, "era": b.era, "technology": b.technology,
        "cognitive_preset": state.fidelity,
        "full_local_brain_budget_per_turn": active_brain_budget(
            state.era, state.fidelity),
        "full_personality_and_physics_NPCs": local,
        "detailed_limit": b.full_npc_limit,
        "regional_aggregated_residents": count,
        "total_census": local + count,
        "background_loss_of_life": state.total_deaths,
        "districts": len(state.districts),
        "limited_district_updates_per_turn": b.district_updates,
        "visible_proxy_budget": b.render_budget,
        "render_radius": b.visibility_radius,
        "remote_food_consumed": state.food_consumed,
        "caravans": [asdict(c) for c in state.caravans],
        "district_status": [
            {"id": d.id, "position": [d.x, d.y],
             "census": d.population, "pantry": d.pantry,
             "morale": d.morale, "hardship": d.hardship,
             "last_simulated_day": d.days_simulated}
            for d in state.districts
        ],
        "fidelity": (
            "Detailed local people have individual cognition. "
            "Remote census uses conserved finite supplies and sparse cohort "
            "updates, not individually instantiated AI agents."
        ),
    }


# Adaptive resource fidelity: budget is per active local *brain*, not the
# regional cohort count. All 32 local bodies still exist and age each turn.
# Four levels are available for testing and user-selected consumer hardware.
FIDELITY_MODES = ("economy", "balanced", "vivid", "unrestricted")
MAX_IMPRESSIONS = 64


def active_brain_budget(era: str, preset: str = "balanced") -> int:
    b = era_budget(era)
    if preset not in FIDELITY_MODES:
        raise FoundationError("unknown NPC hardware fidelity preset")
    limits = {"economy": 3, "balanced": 7,
              "vivid": 16, "unrestricted": MAX_AGENTS}
    return min(b.full_npc_limit, limits[preset])


def select_active_brains(
    state: EraPopulation, society: PhysicalSociety, terrain: TerrainState,
    cognition, *, preset: str = "balanced",
) -> tuple[int, ...]:
    """Deterministic urgency, local proximity, promise and fairness scheduler.

    Every selected ID is a fully embodied resident. Selecting a subset never
    promotes a regional census member into an actual individual. The rest are
    explicit passive bodies: they continue to age/hunger but cannot harvest,
    teleport, form free friendships or create offscreen resource credits.
    """
    validate_population(state, society, terrain)
    limit = min(active_brain_budget(state.era, preset),
                len(society.inhabitants))
    here = terrain.position
    protected = set()
    for order in cognition.orders:
        if order.status == "open":
            protected.add(order.citizen)
    for build in cognition.projects:
        if build.status == "open":
            protected.update(p.id for p in society.inhabitants
                             if p.profession in ("builder", "engineer")
                             and p.id not in build.contributors)
    for lesson in cognition.training.records:
        if lesson.status == "active":
            protected.update((lesson.mentor, lesson.apprentice))
    for family in cognition.households.families:
        if family.status == "established":
            child = society.inhabitants[family.child_id]
            if child.hunger >= 5:
                protected.update((family.caregiver_a, family.caregiver_b,
                                  family.child_id))
    ranking = []
    n = len(society.inhabitants)
    for p in society.inhabitants:
        distance = abs(here[0] - p.x) + abs(here[1] - p.y)
        class_rank = (
            0 if p.health <= 5 or p.hunger >= 10 else
            1 if p.id in protected else
            2 if distance <= 4 else 3
        )
        # Rotate background priorities each real day to avoid permanent
        # id-based preference and keep every idle local body eligible.
        fair = (p.id - state.day * max(1, limit)) % n
        ranking.append((class_rank, min(distance, 1024)
                        if class_rank <= 2 else 0, fair, p.id))
    return tuple(sorted(x[3] for x in sorted(ranking)[:limit]))


def ambient_impressions(
    state: EraPopulation, terrain: TerrainState, *,
    radius: int = 8, max_visible: int | None = None,
) -> tuple[dict, ...]:
    """Honest, spatially anchored background *render proxies*.

    Distinct sprites are drawn around physically anchored districts in the
    current viewport. Each is deliberately tagged visual-only, without
    individual AI, assets, goods, ballots, citizen IDs or persistent health.
    Work is O(min(render budget, 64)), never O(census).
    """
    validate_terrain(terrain)
    if type(radius) is not int or not 2 <= radius <= 24:
        raise FoundationError("invalid hardware-safe ambient viewport")
    budget = era_budget(state.era)
    amount = budget.render_budget if max_visible is None else max_visible
    if type(amount) is not int or not 0 <= amount <= MAX_IMPRESSIONS:
        raise FoundationError("rendered population budget out of bounds")
    if not state.districts or amount == 0:
        return ()
    ox, oy = terrain.position
    occupied = set()
    result = []
    for district in state.districts:
        if district.population == 0:
            continue
        # Anchor sprites to the district's real map point with bounded local
        # spread. The same day, coordinates and seed replay exactly.
        limit = min(6, district.population, amount-len(result))
        if limit <= 0:
            break
        for i in range(limit * 3):
            if len(result) >= amount:
                break
            hashed = sha256(
                f"{state.world_id}:{district.id}:{i}:{state.day//3}".encode()
            ).digest()
            x = district.x + hashed[0] % 9 - 4
            y = district.y + hashed[1] % 9 - 4
            if ((x,y) in occupied or (x,y) == (ox,oy)
                    or abs(x-ox) > radius or abs(y-oy) > radius):
                continue
            if cell_at(terrain, x, y).blocking:
                continue
            occupied.add((x,y))
            result.append({
                "id": f"ambient-{district.id}-{i}",
                "district": district.id,
                "x": x, "y": y,
                "role": "background-crowd",
                "is_simplified_visual_proxy": True,
                "has_individual_cognition": False,
                "can_use_resources": False,
                "can_vote": False,
            })
            if len([p for p in result if p["district"] == district.id]) >= limit:
                break
    return tuple(result)


def fidelity_report(
    state: EraPopulation, people: PhysicalSociety, terrain: TerrainState,
    *, preset: str = "balanced",
) -> dict:
    # Never implicitly simulate brains merely to compute public counters.
    return {
        "era": state.era, "preset": preset,
        "named_physical_people": len(people.inhabitants),
        "maximum_individual_brain_decisions_per_turn":
            min(active_brain_budget(state.era, preset),
                len(people.inhabitants)),
        "local_passive_survival_bodies": max(
            0, len(people.inhabitants) -
            active_brain_budget(state.era, preset)),
        "regional_simplified_census": sum(d.population for d in state.districts),
        "regional_individual_cognitive_agents": 0,
        "graphic_crowd_impressions_cap": min(
            era_budget(state.era).render_budget, MAX_IMPRESSIONS),
        "guarantee": (
            "Only scheduled real residents run full per-person cognition; "
            "passive bodies consume no magically created resources, "
            "while remote district stocks are conserved independently."
        ),
    }
