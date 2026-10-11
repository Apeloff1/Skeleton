"""Ten distinct autonomous living-world reference simulations.

The ten modes share typed serialization but NOT identical transitions.
Each changes population, matter, energy, evidence or obligations through
its own independently governed state machine. Every authored world retains
the full existing spatial/genre/arc simulation underneath.

This is a bounded abstract gameplay kernel; no claim of 122.88m separately
written histories, native shipped games or production NPC animation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_living_10x_compiler import (
    LivingWorld, living_at, living_from_id,
)
from .original_world_living_systems import SYSTEM_BY_ID
from .original_world_tenfold_runtime import (
    TenfoldAction, TenfoldState, create_tenfold, step_tenfold,
    save_tenfold, restore_tenfold, validate_tenfold,
)

SCHEMA = "original-living-world-simulation.v1"
EVENT_LIMIT = 1000
SAVE_LIMIT = 524288
ACTIVE_LAYERS = frozenset(("living", "spatial", "causal", "mode", "arc"))


@dataclass(frozen=True)
class LivingMetrics:
    # Trophic: actual vegetation and food-web population.
    vegetation: int = 14
    seedlings: int = 5
    grazers: int = 6
    predators: int = 2
    habitat: int = 8
    # Settlement: population cannot exceed housing.
    households: int = 3
    housing: int = 4
    food: int = 12
    unrest: int = 2
    arrivals: int = 2
    # Caravans: shipped goods take two actual world-turns to arrive.
    cargo: int = 6
    in_transit: int = 0
    transit_due: int = 0
    delivered: int = 0
    credit: int = 8
    escorts: int = 1
    # Hydrology: bounded water and persistent flood damage.
    reservoir: int = 9
    soil: int = 5
    dam_strength: int = 1
    flood: int = 0
    irrigated: int = 0
    # Energy: fueled generation and finite storage.
    generator: int = 3
    battery: int = 4
    power_demand: int = 4
    outages: int = 0
    grid_wear: int = 0
    # Fictional life-forms and fictional spore infection.
    unaffected: int = 8
    affected: int = 2
    recovered: int = 0
    remedies: int = 5
    isolation: int = 0
    # Self-governed fabrication with wear and parts budgets.
    builders: int = 2
    components: int = 8
    orders: int = 0
    completed: int = 0
    wear: int = 1
    designs: int = 1
    # Evidence commons.
    observations: int = 2
    proven: int = 0
    rumors: int = 1
    shared: int = 0
    # Three-valley diplomacy (two major parties plus public mediator).
    faction_a: int = 5
    faction_b: int = 5
    tension: int = 4
    promises: int = 1
    goodwill: int = 3
    # Historic echoes: prior action receipts are NEVER rewritten.
    queued_echoes: int = 0
    echo_delay: int = 0
    time_debt: int = 2
    chronal_energy: int = 8
    settled_echoes: int = 0


@dataclass(frozen=True)
class LivingState:
    world_id: str
    spatial: TenfoldState
    metrics: LivingMetrics = LivingMetrics()
    living_turns: int = 0
    events: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class LivingAction:
    layer: str
    verb: str
    amount: int = 1
    target: int = -1
    option: str = ""


@dataclass(frozen=True)
class LivingReceipt:
    number: int
    event_hash: str
    action: LivingAction
    changes: tuple[str, ...]
    nested_event_hash: str
    system_id: str


METRIC_NAMES = frozenset(LivingMetrics.__dataclass_fields__)
MAX_METRIC = 1000


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _integer(value: object, name: str, lower: int = 0, upper: int = 1000) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise FoundationError("invalid living system " + name)


def _metrics_replace(metrics: LivingMetrics, **deltas: int) -> LivingMetrics:
    update = {}
    for field, change in deltas.items():
        if field not in METRIC_NAMES or type(change) is not int:
            raise FoundationError("unknown/invalid living system variable")
        result = getattr(metrics, field) + change
        if not 0 <= result <= MAX_METRIC:
            raise FoundationError("living-world causal meter overflow/underflow: " + field)
        update[field] = result
    return replace(metrics, **update)


def _spend(
    world: TenfoldState, *, energy: int = 0,
    supplies: int = 0, materials: int = 0,
    evidence: int = 0, fuel: int = 0, trust: int = 0,
) -> TenfoldState:
    req = {
        "energy": energy, "supplies": supplies, "materials": materials,
        "evidence": evidence, "fuel": fuel, "trust": trust,
    }
    for name, amount in req.items():
        _integer(amount, "expense " + name)
        available = getattr(
            world, name, None
        ) if name in ("materials", "fuel") else getattr(world.game.causal, name)
        if available < amount:
            raise FoundationError("insufficient real " + name + " for living-world action")
    game = world.game
    causal = game.causal
    causal = replace(
        causal,
        energy=causal.energy - energy,
        supplies=causal.supplies - supplies,
        evidence=causal.evidence - evidence,
        trust=causal.trust - trust,
    )
    return replace(world, game=replace(game, causal=causal),
                   materials=world.materials - materials,
                   fuel=world.fuel - fuel)


def validate_living(state: LivingState) -> LivingWorld:
    if not isinstance(state, LivingState):
        raise FoundationError("invalid living game object")
    law = living_from_id(state.world_id)
    validate_tenfold(state.spatial)
    if state.spatial.world_id != law.source.tenfold_id:
        raise FoundationError("living world embedded wrong source game")
    if not isinstance(state.metrics, LivingMetrics):
        raise FoundationError("invalid living metric table")
    for name in METRIC_NAMES:
        _integer(getattr(state.metrics, name), name)
    m = state.metrics
    if m.households > m.housing:
        raise FoundationError("households must occupy actual housing")
    if m.isolation > m.affected:
        raise FoundationError("fictional isolation cannot exceed affected organisms")
    if m.in_transit == 0 and m.transit_due != 0:
        raise FoundationError("phantom caravan delivery timer")
    if m.in_transit > 0 and m.transit_due == 0:
        raise FoundationError("unaccounted caravan transit time")
    _integer(state.events, "event count", upper=EVENT_LIMIT)
    _integer(state.living_turns, "living tick", upper=1000000)
    if state.living_turns != state.spatial.tick:
        raise FoundationError("living clock desynchronized from actual game turn")
    if not isinstance(state.event_head, str) or len(state.event_head) != 64 or any(
        character not in "0123456789abcdef" for character in state.event_head
    ):
        raise FoundationError("invalid living event chain hash")
    return law


def create_living(index: int | str) -> LivingState:
    law = living_at(index) if type(index) is int else living_from_id(index)
    state = LivingState(law.world_id, create_tenfold(law.source.index))
    validate_living(state)
    return state


def _intervene(
    state: LivingState, law: LivingWorld, action: LivingAction,
) -> tuple[LivingState, tuple[str, ...]]:
    m, world = state.metrics, state.spatial
    system, verb, n = law.foundation.system.system_id, action.verb, action.amount
    if verb not in SYSTEM_BY_ID[system].commands:
        raise FoundationError("intervention unavailable in this authored living system")
    if world.game.causal.action_points == 0:
        raise FoundationError("world turn must advance to refresh action points")
    changes = []
    if system == "trophic":
        if verb == "reseed":
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, seedlings=n * 2, habitat=n)
            changes.append("Paid harvested supplies to plant viable habitat seeds")
        elif verb == "graze":
            if m.vegetation < n or m.grazers < 1:
                raise FoundationError("no viable grazer herd or edible vegetation")
            m = _metrics_replace(m, vegetation=-n, grazers=n)
            changes.append("Vegetation was consumed into actual grazer biomass")
        else:
            world = _spend(world, materials=n)
            m = _metrics_replace(m, habitat=n, predators=-min(n, m.predators))
            changes.append("Protection cost building material; predator pressure decreased")
    elif system == "settlement":
        if verb == "house":
            world = _spend(world, materials=2 * n)
            m = _metrics_replace(m, housing=n)
            changes.append("Built physical shelter for families")
        elif verb == "welcome":
            if m.arrivals < n or m.households + n > m.housing:
                raise FoundationError("refugee arrival requires unoccupied physical homes")
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, arrivals=-n, households=n, unrest=-min(m.unrest, n))
            changes.append("Arriving households occupy finite shelter and consume stores")
        else:
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, food=n * 3, unrest=-min(m.unrest, n))
            changes.append("Transferred real civic supplies into communal food stores")
    elif system == "caravans":
        if verb == "dispatch":
            if m.cargo < n or m.in_transit:
                raise FoundationError("caravan cannot duplicate goods or overlap departure")
            world = _spend(world, fuel=n)
            m = _metrics_replace(m, cargo=-n, in_transit=n, transit_due=2)
            changes.append("Dispatched cargo and propellant to a delayed trade route")
        elif verb == "escort":
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, escorts=n)
            changes.append("Paid for a real protective caravan escort")
        else:
            if m.delivered < n:
                raise FoundationError("goods have not yet physically arrived at market")
            m = _metrics_replace(m, delivered=-n, credit=2 * n)
            changes.append("Sold only previously delivered trade inventory")
    elif system == "watershed":
        if verb == "irrigate":
            if m.reservoir < n:
                raise FoundationError("no stored water for irrigation")
            m = _metrics_replace(m, reservoir=-n, soil=2 * n, irrigated=n)
            changes.append("Irrigated crops by consuming finite reservoir water")
        elif verb == "dam":
            world = _spend(world, materials=2 * n)
            m = _metrics_replace(m, dam_strength=n)
            changes.append("Engineered a tangible flood barrier from material")
        else:
            if m.reservoir < n:
                raise FoundationError("can't release uncontained water")
            m = _metrics_replace(m, reservoir=-n,
                                 flood=-min(m.flood, 2 * n))
            changes.append("Released water to reduce an existing flood hazard")
    elif system == "power":
        if verb == "generate":
            world = _spend(world, fuel=n)
            m = _metrics_replace(m, battery=n * 3)
            changes.append("Burned real fuel to generate stored power")
        elif verb == "charge":
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, battery=n * 2)
            changes.append("Converted scarce replaceable cells into battery energy")
        else:
            if m.battery < n:
                raise FoundationError("cannot route electricity that is not stored")
            m = _metrics_replace(m, battery=-n,
                                 outages=-min(m.outages, n),
                                 grid_wear=-min(m.grid_wear, n))
            changes.append("Routed real battery supply to public infrastructure")
    elif system == "spores":
        if verb == "isolate":
            if m.affected - m.isolation < n:
                raise FoundationError("cannot isolate more than affected organisms")
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, isolation=n)
            changes.append("Built finite fictional quarantine shelter")
        elif verb == "remedy":
            if m.affected < n or m.remedies < n:
                raise FoundationError("treatment needs actual affected organisms and remedies")
            m = _metrics_replace(m, affected=-n,
                                 recovered=n, remedies=-n,
                                 isolation=-min(m.isolation, n))
            changes.append("Finite fictional spore remedy moved organisms to recovered cohort")
        else:
            world = _spend(world, evidence=n)
            m = _metrics_replace(m, remedies=n)
            changes.append("Spent validated observations to synthesize fictional remedies")
    elif system == "fabrication":
        if verb == "design":
            world = _spend(world, evidence=n)
            m = _metrics_replace(m, designs=n, orders=n)
            changes.append("Validated an actual blueprint and queued an unbuilt structure")
        elif verb == "assemble":
            if m.components < n:
                raise FoundationError("no robot components to commission assembly")
            world = _spend(world, materials=n)
            m = _metrics_replace(m, components=-n, builders=n)
            changes.append("Commissioned real robots using spare parts and materials")
        else:
            if m.wear < n:
                raise FoundationError("cannot service an undamaged fleet")
            world = _spend(world, materials=n)
            m = _metrics_replace(m, wear=-n)
            changes.append("Repair consumed physical parts and restored builder fitness")
    elif system == "knowledge":
        if verb == "observe":
            world = _spend(world, energy=n)
            m = _metrics_replace(m, observations=2 * n)
            changes.append("Field investigation gathered reviewable observations")
        elif verb == "verify":
            if m.observations < 2 * n:
                raise FoundationError("independent evidence threshold not satisfied")
            world = _spend(world, evidence=n)
            m = _metrics_replace(m, observations=-2 * n, proven=n,
                                 rumors=-min(m.rumors, n))
            changes.append("Promoted only independently paid and corroborated knowledge")
        else:
            if m.proven < n:
                raise FoundationError("cannot teach knowledge that remains unverified")
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, proven=-n, shared=2 * n)
            changes.append("Shared verified learning through finite classroom resources")
    elif system == "diplomacy":
        if verb == "petition":
            world = _spend(world, energy=n)
            m = _metrics_replace(m, goodwill=n,
                                 tension=-min(m.tension, n))
            changes.append("Legitimacy-building negotiations consumed genuine effort")
        elif verb == "pledge":
            world = _spend(world, supplies=2 * n)
            m = _metrics_replace(m, promises=n,
                                 faction_b=n)
            changes.append("Treaty promises are material-backed, not free dialogue flags")
        else:
            if m.goodwill < n:
                raise FoundationError("mediator lacks public standing")
            world = _spend(world, trust=n)
            m = _metrics_replace(m, goodwill=-n,
                                 tension=-min(m.tension, 2 * n),
                                 promises=-min(m.promises, n))
            changes.append("A real public mediation spent trust and reconciled promises")
    else:  # echoes
        if verb == "record":
            if m.queued_echoes:
                raise FoundationError("temporal queue must settle before another recording")
            world = _spend(world, energy=n)
            m = _metrics_replace(m, chronal_energy=-n,
                                 queued_echoes=n, echo_delay=2,
                                 time_debt=n)
            changes.append("Recorded a delayed effect and an unavoidable future debt")
        elif verb == "hasten":
            if m.queued_echoes == 0 or m.echo_delay == 0:
                raise FoundationError("no pending history remains to hasten")
            world = _spend(world, evidence=n)
            m = _metrics_replace(m, echo_delay=-min(m.echo_delay, n))
            changes.append("Expended observations to shorten the causal echo delay")
        else:
            if m.time_debt < n:
                raise FoundationError("no outstanding temporal obligation of that size")
            world = _spend(world, supplies=n)
            m = _metrics_replace(m, time_debt=-n, settled_echoes=n)
            changes.append("Reconciled a historical debt without deleting event receipts")
    game = world.game
    world = replace(world, game=replace(game, causal=replace(
        game.causal, action_points=game.causal.action_points - 1,
    )))
    return replace(state, metrics=m, spatial=world), tuple(changes)


def _autonomous(state: LivingState, law: LivingWorld) -> tuple[LivingState, tuple[str, ...]]:
    m, world = state.metrics, state.spatial
    system = law.foundation.system.system_id
    tick = state.living_turns
    effects = []
    if system == "trophic":
        # Plants regrow only from a finite seed bank. Grazers eat existing
        # plants; predators consume finite grazers, never conjured animals.
        sprout = min(m.seedlings, max(0, m.habitat // 3))
        m = _metrics_replace(m, seedlings=-sprout, vegetation=sprout)
        appetite = min(m.vegetation, (m.grazers + 1) // 3)
        starvation = max(0, (m.grazers + 1) // 3 - appetite)
        m = _metrics_replace(m, vegetation=-appetite,
                             grazers=-min(m.grazers, starvation))
        prey = min(m.grazers, m.predators // 2)
        m = _metrics_replace(m, grazers=-prey,
                             predators=-min(m.predators, int(prey == 0)))
        effects.append(f"Food web advanced: sprouted {sprout}, grazed {appetite}, hunted {prey}")
    elif system == "settlement":
        meals = min(m.food, m.households)
        hungry = m.households - meals
        depart = min(m.households, 1 if hungry else 0)
        m = _metrics_replace(m, food=-meals,
                             households=-depart,
                             unrest=min(5, hungry + depart))
        if not hungry and tick % 3 == 0 and m.arrivals < 30:
            m = _metrics_replace(m, arrivals=1)
        effects.append(f"Fed {meals} households; departed {depart}; new requests remain")
    elif system == "caravans":
        if m.in_transit:
            if m.transit_due > 1:
                m = _metrics_replace(m, transit_due=-1)
            else:
                loss = min(m.in_transit, 1 if m.escorts == 0 else 0)
                delivered = m.in_transit - loss
                m = _metrics_replace(m, in_transit=-m.in_transit,
                                     transit_due=-1, delivered=delivered,
                                     escorts=-min(m.escorts, 1))
                if loss and world.danger < 100:
                    world = replace(world, danger=world.danger + 1)
                effects.append(f"Caravan reached market: {delivered} goods, {loss} lost")
        if not effects:
            effects.append("Trade goods remain stored or physically en route")
    elif system == "watershed":
        precipitation = 1 + (tick + world.position) % 3
        intake = m.reservoir + precipitation
        capacity = 12 + 4 * m.dam_strength
        overflow = max(0, intake - capacity)
        m = replace(m, reservoir=min(intake, capacity))
        if overflow:
            m = _metrics_replace(m, flood=min(10, overflow))
        evaporation = 1 if m.reservoir > 0 else 0
        m = _metrics_replace(m, reservoir=-evaporation,
                             soil=-min(m.soil, 1 if tick % 3 == 0 else 0))
        effects.append(f"Rainfall {precipitation}; overflow {overflow}; evaporation {evaporation}")
    elif system == "power":
        # The generator burns real spatial-world fuel. Storage never grows
        # from an uncosted endless function call.
        generation = min(m.generator, world.fuel)
        world = replace(world, fuel=world.fuel - generation)
        produced = min(1000 - m.battery, generation * 2)
        m = _metrics_replace(m, battery=produced)
        served = min(m.battery, m.power_demand)
        shortage = max(0, m.power_demand - served)
        m = _metrics_replace(m, battery=-served,
                             outages=min(5, shortage),
                             grid_wear=min(3, shortage))
        effects.append(f"Burned {generation} fuel; served {served} load; shortfall {shortage}")
    elif system == "spores":
        exposed = max(0, m.affected - m.isolation)
        spread = min(m.unaffected, exposed // 2)
        m = _metrics_replace(m, unaffected=-spread, affected=spread)
        # Fictional organism population conserved across cohorts.
        effects.append(f"Fictional spore contact moved {spread} organisms to affected cohort")
    elif system == "fabrication":
        active = max(0, m.builders - m.wear)
        output = min(m.orders, active, m.components)
        m = _metrics_replace(m, orders=-output,
                             completed=output, components=-output)
        if active > 0:
            m = _metrics_replace(m, wear=min(1, m.builders - m.wear))
        effects.append(f"Autonomous builders completed {output} paid orders and wore down")
    elif system == "knowledge":
        diffusion = min(m.proven, 1 if tick % 2 == 0 else 0)
        m = _metrics_replace(m, proven=-diffusion, shared=diffusion,
                             rumors=min(1, 1000 - m.rumors) if tick % 4 == 0 else 0)
        effects.append(f"Verified knowledge diffused {diffusion}; unsupported rumors persist")
    elif system == "diplomacy":
        pressure = (1 if m.promises and tick % 2 == 0 else 0)
        m = _metrics_replace(m, tension=min(pressure, 1000 - m.tension))
        if m.tension >= 9 and world.game.causal.trust > 0:
            game = world.game
            world = replace(world, game=replace(game, causal=replace(
                game.causal, trust=game.causal.trust - 1,
            )))
        effects.append(f"Public treaty obligations added {pressure} grievance pressure")
    else:  # echoes
        if m.queued_echoes:
            if m.echo_delay > 1:
                m = _metrics_replace(m, echo_delay=-1)
            else:
                matured = m.queued_echoes
                m = _metrics_replace(m, queued_echoes=-matured,
                                     echo_delay=-m.echo_delay,
                                     chronal_energy=min(matured, 1000 - m.chronal_energy))
                effects.append(f"{matured} delayed echoes matured; historical debt persists")
        if m.time_debt > 6 and world.danger < 100:
            world = replace(world, danger=world.danger + 1)
            effects.append("Unpaid chronal debt created persistent world hazard")
        if not effects:
            effects.append("Chronal histories progressed without rewriting event chains")
    return replace(state, metrics=m, spatial=world), tuple(effects)


def step_living(state: LivingState, action: LivingAction) -> tuple[LivingState, LivingReceipt]:
    law = validate_living(state)
    if state.events >= EVENT_LIMIT:
        raise FoundationError("living-world event budget exhausted")
    if not isinstance(action, LivingAction) or action.layer not in ACTIVE_LAYERS:
        raise FoundationError("invalid living game action layer")
    _integer(action.amount, "action magnitude", 1, 3)
    _integer(action.target, "world target", -1, 23)
    if (not isinstance(action.verb, str) or not action.verb or len(action.verb) > 64
            or not isinstance(action.option, str) or len(action.option) > 32):
        raise FoundationError("unsupported world action arguments")
    updated = state
    if action.layer == "living":
        updated, effects = _intervene(state, law, action)
    else:
        world, receipt = step_tenfold(
            state.spatial, TenfoldAction(
                action.layer, action.verb, action.amount,
                action.target, action.option,
            ),
        )
        updated = replace(state, spatial=world)
        effects = receipt.changes
        if action.layer == "causal" and action.verb == "end_turn":
            updated = replace(updated, living_turns=state.living_turns + 1)
            updated, additional = _autonomous(updated, law)
            effects += additional
    event_hash = _digest({
        "version": SCHEMA, "world_design": law.design_id,
        "previous": state.event_head, "before": asdict(state),
        "after": asdict(updated), "action": asdict(action),
        "effects": effects,
    })
    final = replace(updated, events=state.events + 1, event_head=event_hash)
    validate_living(final)
    return final, LivingReceipt(
        final.events, event_hash, action, tuple(effects),
        final.spatial.event_head, law.foundation.system.system_id,
    )


def replay_living(index: int, actions: tuple[LivingAction, ...]):
    if not isinstance(actions, tuple) or len(actions) > EVENT_LIMIT:
        raise FoundationError("invalid bounded living replay")
    state, events = create_living(index), []
    for action in actions:
        state, receipt = step_living(state, action)
        events.append(receipt)
    return state, tuple(events)


def save_living(state: LivingState) -> str:
    law = validate_living(state)
    payload = {
        "schema": SCHEMA, "design_id": law.design_id,
        "world_id": state.world_id,
        "spatial": json.loads(save_tenfold(state.spatial)),
        "metrics": asdict(state.metrics),
        "living_turns": state.living_turns,
        "events": state.events, "event_head": state.event_head,
    }
    return json.dumps({"payload": payload, "checksum": _digest(payload)},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def restore_living(value: str) -> LivingState:
    if not isinstance(value, str) or len(value.encode("utf-8")) > SAVE_LIMIT:
        raise FoundationError("invalid/oversized living-world save data")
    try:
        envelope = json.loads(value)
        if set(envelope) != {"payload", "checksum"}:
            raise FoundationError("unknown living save envelope")
        payload = envelope["payload"]
        if (set(payload) != {
            "schema", "design_id", "world_id", "spatial", "metrics",
            "living_turns", "events", "event_head",
        } or payload["schema"] != SCHEMA
                or envelope["checksum"] != _digest(payload)
                or set(payload["metrics"]) != METRIC_NAMES):
            raise FoundationError("living save integrity mismatch")
        state = LivingState(
            payload["world_id"],
            restore_tenfold(json.dumps(payload["spatial"])),
            LivingMetrics(**payload["metrics"]),
            payload["living_turns"], payload["events"], payload["event_head"],
        )
        law = validate_living(state)
        if law.design_id != payload["design_id"]:
            raise FoundationError("authored world changed across save version")
        return state
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        raise FoundationError("living save is structurally invalid") from exc
