"""One real playable session unifying authored world, physics, citizens and UI.

A source world is a 122.88m-index living configuration, but this runtime
instantiates exactly one game. Its 24-node large-scale map, local sparse
tile terrain, autonomous NPC behavior, economic transfers, controls, story
and renderers are linked through a single immutable transactional session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_living_10x_compiler import living_at, living_from_id
from .original_world_living_10x_runtime import (
    LivingAction, LivingState, create_living, step_living,
    validate_living, save_living, restore_living,
)
from .original_world_product_terrain import (
    TerrainAction, TerrainState, create_terrain, step_terrain,
    validate_terrain, terrain_save, terrain_restore,
)
from .original_world_product_agents import (
    PhysicalSociety, create_society, npc_tick, validate_society,
    society_save, society_restore, Person, ROLES,
)
from .original_world_npc_cognition_v2 import (
    CitizenIntelligence, make_intelligence, validate_intelligence,
    smart_npc_tick, cognition_save, cognition_restore,
    register_player_care, commission, cancel_order, _bond_change,
    commission_project, cancel_project, interview_citizen,
)
from .original_world_npc_civics import propose_civic
from .original_world_npc_apprenticeships import enroll, cancel_enrollment
from .original_world_npc_households import establish_household, cancel_household
from .original_world_npc_era_population import (
    EraPopulation, era_budget, create_era_population,
    validate_population, dispatch_food, tick_population,
    population_save, population_restore, population_report,
    select_active_brains,
    permitted_roles, inhabitant_role_profile,
    adjust_fidelity, embody_regional_citizen,
)

SCHEMA = "original-world-playable-product-session.v3"
PRIOR_SCHEMA = "original-world-playable-product-session.v2"
LEGACY_SCHEMA = "original-world-playable-product-session.v1"
LIMIT = 2048
SAVED_BYTES_LIMIT = 4194304
BIOMES_BY_ARCH = {
    "lattice": "temperate", "spiral": "desert",
    "labyrinth": "forest", "archipelago": "archipelago",
    "strata": "caverns", "canopy": "forest", "orbit": "caverns",
    "pocket": "tundra", "phase": "temperate", "abyss": "archipelago",
}


@dataclass(frozen=True)
class ProductAction:
    layer: str
    verb: str
    amount: int = 1
    x: int = 0
    y: int = 0
    target: int = -1
    option: str = ""


@dataclass(frozen=True)
class ProductSession:
    world_id: str
    living: LivingState
    terrain: TerrainState
    society: PhysicalSociety
    events: int = 0
    event_head: str = "0" * 64
    cognition: CitizenIntelligence | None = None
    population: EraPopulation | None = None


@dataclass(frozen=True)
class ProductReceipt:
    number: int
    receipt: str
    layer: str
    changes: tuple[str, ...]
    world_head: str
    physical_head: str
    society_head: str


def _hash(v: object) -> str:
    return sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_product(state: ProductSession):
    if not isinstance(state, ProductSession):
        raise FoundationError("invalid original game product session")
    law = living_from_id(state.world_id)
    validate_living(state.living)
    if state.living.world_id != law.world_id:
        raise FoundationError("product switched to unauthorized source world")
    validate_terrain(state.terrain)
    if state.terrain.design_id != law.design_id:
        raise FoundationError("physical landscape does not match authored causal source")
    if state.terrain.biome != BIOMES_BY_ARCH[law.source.spatial.architecture.architecture_id]:
        raise FoundationError("local landscape conflicts with selected world architecture")
    validate_society(state.society, state.terrain)
    validate_intelligence(state.cognition, state.society, state.terrain)
    if state.population is not None:
        validate_population(state.population, state.society, state.terrain)
    if state.society.tick != state.living.living_turns or state.terrain.turns != state.living.living_turns:
        raise FoundationError("source-world, landscape and actor clocks diverged")
    if type(state.events) is not int or not 0 <= state.events <= LIMIT:
        raise FoundationError("invalid product event budget")
    if not isinstance(state.event_head, str) or len(state.event_head) != 64:
        raise FoundationError("invalid product receipt")
    return law


def create_product(
    index: int, *, inhabitants: int | None = None, era: str | None = None,
    npc_fidelity: str = "balanced",
) -> ProductSession:
    law = living_at(index)
    if era is not None:
        budget = era_budget(era)
        # Reserve two full-mind slots for physically founded future families.
        count = (max(1, budget.full_npc_limit - 2)
                 if inhabitants is None else inhabitants)
    else:
        count = 12 if inhabitants is None else inhabitants
    physical = create_terrain(
        law.design_id, BIOMES_BY_ARCH[law.source.spatial.architecture.architecture_id])
    inhabitants_state = create_society(physical, count)
    if era is not None:
        inhabitants_state = inhabitant_role_profile(inhabitants_state, era)
    minds = make_intelligence(physical, inhabitants_state)
    if era is None and npc_fidelity != "balanced":
        raise FoundationError("hardware NPC fidelity requires selected original era")
    regional = (create_era_population(
        physical, inhabitants_state, era, fidelity=npc_fidelity)
                if era is not None else None)
    game = ProductSession(law.world_id, create_living(index),
                          physical, inhabitants_state, cognition=minds,
                          population=regional)
    validate_product(game)
    return game


def _spend_source_ap(game: LivingState, amount: int = 1) -> LivingState:
    current = game.spatial.game.causal
    if current.action_points < amount:
        raise FoundationError("no actions remain; advance world time")
    spatial = game.spatial
    advanced = spatial.game
    advanced = replace(advanced, causal=replace(
        current, action_points=current.action_points - amount,
    ))
    return replace(game, spatial=replace(spatial, game=advanced))


def _product_operation(
    session: ProductSession, action: ProductAction
) -> tuple[ProductSession, tuple[str, ...]]:
    local, living, society = session.terrain, session.living, session.society
    verb = action.verb
    if local.position != (0, 0) and verb.startswith("deposit_"):
        raise FoundationError("physical depot transfers require player presence at origin")
    if verb == "assign" and session.population is not None:
        if action.option not in permitted_roles(session.population.era):
            raise FoundationError("profession is unavailable in this historical technology era")
    if verb in ("deposit_wood", "deposit_stone"):
        key = "lumber" if verb == "deposit_wood" else "masonry"
        if getattr(local, key) < action.amount:
            raise FoundationError("cannot transfer material not in player's depot")
        if living.spatial.materials + action.amount > 100:
            raise FoundationError("world-wide material stock at capacity")
        local = replace(local, **{key: getattr(local, key) - action.amount})
        world = replace(living.spatial, materials=living.spatial.materials + action.amount)
        living = replace(living, spatial=world)
        message = f"Transferred {action.amount} real {key} into world construction stock"
    elif verb == "share_food":
        if local.position != (0, 0):
            raise FoundationError("food delivery requires physical depot")
        if local.provisions < action.amount:
            raise FoundationError("can't donate unowned food")
        causal = living.spatial.game.causal
        if causal.supplies + action.amount > 10000:
            raise FoundationError("world supplies full")
        local = replace(local, provisions=local.provisions - action.amount)
        advanced = living.spatial.game
        spatial = replace(living.spatial, game=replace(
            advanced, causal=replace(causal, supplies=causal.supplies + action.amount),
        ))
        living = replace(living, spatial=spatial)
        message = "Supplied actual harvested provisions to the continuing world economy"
    elif verb == "gift":
        if type(action.target) is not int or not 0 <= action.target < len(society.inhabitants):
            raise FoundationError("gift needs existing physical NPC identity")
        person = society.inhabitants[action.target]
        if abs(person.x - local.position[0]) + abs(person.y - local.position[1]) > 1:
            raise FoundationError("social aid requires a physically nearby resident")
        if local.provisions < action.amount:
            raise FoundationError("cannot give food not actually harvested")
        local = replace(local, provisions=local.provisions - action.amount)
        residents = list(society.inhabitants)
        residents[action.target] = replace(
            person, hunger=max(0, person.hunger - 4 * action.amount),
            relationships=min(20, person.relationships + action.amount),
        )
        society = replace(society, inhabitants=tuple(residents))
        cognition = register_player_care(
            session.cognition, society, action.target, food=action.amount)
        message = "Delivered food and formed remembered trust with a physical resident"
    elif verb == "assign":
        if type(action.target) is not int or not 0 <= action.target < len(society.inhabitants):
            raise FoundationError("assignment requires a known physical resident")
        if action.option not in ROLES:
            raise FoundationError("assignment requires supported profession")
        person = society.inhabitants[action.target]
        if abs(person.x - local.position[0]) + abs(person.y - local.position[1]) > 1:
            raise FoundationError("job assignment requires face-to-face conversation")
        if person.profession == action.option:
            raise FoundationError("already assigned to that profession")
        if living.spatial.game.causal.trust < 1:
            raise FoundationError("public employment needs available consent/trust")
        world = living.spatial
        advanced = world.game
        world = replace(world, game=replace(advanced, causal=replace(
            advanced.causal, trust=advanced.causal.trust - 1)))
        living = replace(living, spatial=world)
        residents = list(society.inhabitants)
        residents[action.target] = replace(person, profession=action.option)
        society = replace(society, inhabitants=tuple(residents))
        message = "Reassigned one consenting resident through real trust expenditure"
    else:
        raise FoundationError("unsupported cross-economy/social studio operation")
    living = _spend_source_ap(living)
    return replace(session, terrain=local, living=living, society=society,
                   cognition=cognition if verb == "gift" else session.cognition), (message,)


def _npc_operation(
    session: ProductSession, action: ProductAction,
) -> tuple[ProductSession, tuple[str, ...]]:
    """Authenticated-by-gameplay commands changing real person contracts.

    Work orders cost one civic trust and one action point, and require face
    contact or posting at the central depot. The player's order does not
    create any resources: fulfillment is recorded only when an NPC physically
    delivers stocks from depleted terrain deposits.
    """
    world, society = session.terrain, session.society
    thinking = session.cognition
    if action.verb == "mentor" and session.population is not None:
        if not 0 <= action.target < len(society.inhabitants):
            raise FoundationError("unknown era teacher")
        if society.inhabitants[action.target].profession not in permitted_roles(
                session.population.era):
            raise FoundationError("a future-era profession cannot be taught yet")
    if action.verb == "household":
        try:
            caregiver_b = int(action.option)
        except ValueError as exc:
            raise FoundationError("household requires two existing distinct caregivers") from exc
        first, second = action.target, caregiver_b
        candidate = next(
            (bond for bond in thinking.bonds
             if (bond.left, bond.right) == (min(first, second),
                                           max(first, second))),
            None,
        )
        if session.living.spatial.game.causal.trust < 1:
            raise FoundationError("new household requires community legitimacy")
        physical, family = establish_household(
            thinking.households, society, world,
            caregiver_a=first, caregiver_b=second,
            affinity=candidate.affinity if candidate else 0,
            mutual_trust=candidate.trust if candidate else 0,
        )
        world = physical
        thinking = replace(thinking, households=family)
        previous = session.living.spatial
        living = replace(session.living, spatial=replace(
            previous, game=replace(previous.game, causal=replace(
                previous.game.causal, trust=previous.game.causal.trust - 1))))
        message = (
            f"Two mutually trusted caregivers {first} and {second} reserved "
            "finite food and water for a household; the new dependent is "
            "not yet an available citizen"
        )
    elif action.verb == "cancel_household":
        world, family = cancel_household(
            thinking.households, society, world, action.target)
        thinking = replace(thinking, households=family)
        living = session.living
        message = "Pending dependent's food and water escrow returned to actual stores"
    elif action.verb == "mentor":
        try:
            apprentice = int(action.option)
        except ValueError as exc:
            raise FoundationError("mentor requires existing apprentice ID") from exc
        if session.living.spatial.game.causal.trust < 1:
            raise FoundationError("professional mentorship requires authentic civic consent")
        trained = enroll(thinking.training, society, world,
                         mentor=action.target, student=apprentice)
        thinking = replace(thinking, training=trained)
        source = session.living.spatial
        living = replace(session.living, spatial=replace(
            source, game=replace(source.game, causal=replace(
                source.game.causal, trust=source.game.causal.trust - 1))))
        message = (f"Real citizen {action.target} enrolled citizen {apprentice} "
                   "in three paid in-person professional lessons")
    elif action.verb == "cancel_mentorship":
        thinking = replace(thinking, training=cancel_enrollment(
            thinking.training, society, world, action.target))
        living = session.living
        message = "An unfinished individual apprenticeship was cancelled"
    elif action.verb == "propose":
        if world.position != (0, 0):
            raise FoundationError("player must attend the physical public depot")
        if world.provisions < 1:
            raise FoundationError("a public vote needs a real funded meeting meal")
        old = session.living.spatial
        if old.game.causal.trust < 1:
            raise FoundationError("public policy requires an actual civic trust mandate")
        revised = propose_civic(
            thinking.civic, society, world, policy=action.option,
            citizen=action.target, day=thinking.day,
        )
        thinking = replace(thinking, civic=revised)
        world = replace(world, provisions=world.provisions - 1)
        living = replace(session.living, spatial=replace(
            old, game=replace(old.game, causal=replace(
                old.game.causal, trust=old.game.causal.trust - 1))))
        message = (
            f"Resident {action.target} sponsored {action.option}; "
            "real food and trust paid. Actual in-person ballots occur on next world turn"
        )
    elif action.verb == "interview":
        if not 0 <= action.target < len(society.inhabitants):
            raise FoundationError("interviewee must be a real local citizen")
        actor = society.inhabitants[action.target]
        if abs(actor.x - world.position[0]) + abs(actor.y - world.position[1]) > 1:
            raise FoundationError("verified testimony requires in-person discussion")
        old = session.living.spatial
        if old.game.causal.evidence >= 100:
            raise FoundationError("public evidence register has reached capacity")
        thinking, statement = interview_citizen(
            thinking, society, world, citizen=action.target,
            subject=action.option)
        new_game = replace(old.game, causal=replace(
            old.game.causal, evidence=old.game.causal.evidence + 1))
        living = replace(session.living, spatial=replace(old, game=new_game))
        message = (
            f"Citizen {statement.citizen} gave first-hand evidence of "
            f"{statement.value} {statement.subject} at ({statement.x},{statement.y}) "
            f"on historical day {statement.observation_turn}; unique testimony "
            "entered the real game evidence ledger"
        )
    elif action.verb == "commission":
        if not 0 <= action.target < len(society.inhabitants):
            raise FoundationError("contract must refer to an existing citizen")
        actor = society.inhabitants[action.target]
        if (world.position != (0, 0)
                and abs(actor.x - world.position[0])
                + abs(actor.y - world.position[1]) > 1):
            raise FoundationError("commission must be posted at depot or in person")
        causal = session.living.spatial.game.causal
        if causal.trust < 1:
            raise FoundationError("work contract requires civic legitimacy")
        thinking = commission(thinking, society, world,
                              citizen=action.target, material=action.option,
                              quantity=action.amount)
        previous = session.living.spatial
        revised = replace(previous, game=replace(
            previous.game, causal=replace(causal, trust=causal.trust - 1)))
        living = replace(session.living, spatial=revised)
        message = (
            f"Citizen {action.target} accepted real-material {action.option} "
            f"contract for {action.amount} goods; public trust paid")
    elif action.verb == "cancel":
        thinking = cancel_order(thinking, society, world, action.target)
        living = session.living
        message = f"Open work contract {action.target} cancelled without fabricating goods"
    elif action.verb == "project":
        if world.position != (0, 0) and world.position != (action.x, action.y):
            raise FoundationError("civic plan needs posting at depot or physical worksite")
        world, thinking = commission_project(
            thinking, society, world, kind=action.option, x=action.x, y=action.y)
        previous = session.living.spatial
        if previous.game.causal.trust < 1:
            raise FoundationError("public construction requires real civic trust")
        living = replace(session.living, spatial=replace(
            previous, game=replace(previous.game, causal=replace(
                previous.game.causal, trust=previous.game.causal.trust - 1))))
        message = ("Reserved finite construction materials for "
                   + action.option + f" at ({action.x},{action.y})"
                   + "; skilled NPCs must physically assemble it")
    elif action.verb == "cancel_project":
        world, thinking = cancel_project(
            thinking, society, world, action.target)
        living = session.living
        message = "Unspent public construction escrow returned to the real depot"
    elif action.verb == "council":
        if world.position != (0, 0) or world.provisions < 1:
            raise FoundationError("public council requires depot and one food offering")
        present = sorted(
            p.id for p in society.inhabitants
            if abs(p.x) + abs(p.y) <= 1 and p.health > 0
        )
        if len(present) < 2:
            raise FoundationError("public council requires two physically present citizens")
        world = replace(world, provisions=world.provisions - 1)
        thinking = _bond_change(
            thinking, present[0], present[1],
            affinity=1, trust=1, aid=1)
        thinking = replace(thinking, meetings=thinking.meetings + 1,
                           interventions=thinking.interventions + 1)
        living = session.living
        message = "Public council spent real provisions and strengthened a recorded civic tie"
    else:
        raise FoundationError("unrecognized cognitive command")
    return replace(session, terrain=world, living=_spend_source_ap(living),
                   cognition=thinking), (message,)


def _regional_operation(
    state: ProductSession, action: ProductAction,
) -> tuple[ProductSession, tuple[str, ...]]:
    if state.population is None:
        raise FoundationError("era-region action needs an explicitly selected era")
    if action.verb == "set_detail":
        changed = adjust_fidelity(state.population, action.option)
        return replace(state, population=changed), (
            "NPC hardware budget changed to " + changed.fidelity
            + "; persistent regional people, goods and historical actions retained",
        )
    if action.verb == "recruit":
        causal = state.living.spatial.game.causal
        if causal.trust < 1:
            raise FoundationError("individual regional migration requires civic trust")
        region, people = embody_regional_citizen(
            state.population, state.society, state.terrain, district=action.target)
        new_mind = make_intelligence(state.terrain, people).minds[-1]
        thinking = replace(
            state.cognition,
            minds=state.cognition.minds + (new_mind,),
            households=replace(
                state.cognition.households,
                ages=state.cognition.households.ages + (24,),
            ),
        )
        source = state.living.spatial
        living = replace(
            state.living, spatial=replace(
                source, game=replace(
                    source.game, causal=replace(causal, trust=causal.trust - 1))))
        return replace(
            state, society=people, population=region,
            cognition=thinking, living=_spend_source_ap(living),
        ), (
            f"Actual resident {people.inhabitants[-1].id} embodied from "
            f"district {action.target}; census debited, personal mind and "
            "work capability added, public trust expended",
        )
    if action.verb != "dispatch_food":
        raise FoundationError("unknown era-scale physical operation")
    if state.terrain.position != (0, 0):
        raise FoundationError("regional caravans originate at actual player depot")
    if state.living.spatial.game.causal.action_points <= 0:
        raise FoundationError("regional logistics require one player action")
    population, terrain = dispatch_food(
        state.population, state.society, state.terrain,
        district=action.target, amount=action.amount, direction=action.option)
    return replace(
        state, terrain=terrain,
        living=_spend_source_ap(state.living), population=population,
    ), (
        f"Dispatched {action.amount} real food from physical stores on route "
        f"{action.target}; material stays in transit until valid arrival",
    )

def step_product(
    state: ProductSession, action: ProductAction,
) -> tuple[ProductSession, ProductReceipt]:
    law = validate_product(state)
    if state.events >= LIMIT:
        raise FoundationError("product receipt capacity exhausted")
    if not isinstance(action, ProductAction) or action.layer not in (
        "terrain", "living", "spatial", "mode", "arc", "causal", "studio", "npc", "population",
    ):
        raise FoundationError("invalid product command layer")
    if type(action.amount) is not int or not 1 <= action.amount <= 3:
        raise FoundationError("product quantity must be 1..3")
    max_target = 63 if action.layer == "population" else 23
    if type(action.target) is not int or not -1 <= action.target <= max_target:
        raise FoundationError("invalid product world target")
    if any(type(v) is not int for v in (action.x, action.y)):
        raise FoundationError("invalid local physical coordinates")
    if not isinstance(action.verb, str) or not 0 < len(action.verb) <= 64:
        raise FoundationError("unrecognized product command")
    if not isinstance(action.option, str) or len(action.option) > 64:
        raise FoundationError("invalid product command option")
    new, info = state, ()
    if action.layer == "terrain":
        if action.verb == "end_turn":
            raise FoundationError("only causal end_turn may advance all synchronized clocks")
        if state.living.spatial.game.causal.action_points <= 0:
            raise FoundationError("end the world turn before more actions")
        terrain, receipt = step_terrain(
            state.terrain, TerrainAction(action.verb, action.x, action.y, action.amount))
        living = _spend_source_ap(state.living)
        new = replace(state, terrain=terrain, living=living)
        info = (f"Real physical tile action: {action.verb} ({action.x},{action.y})",)
    elif action.layer == "studio":
        new, info = _product_operation(state, action)
    elif action.layer == "npc":
        new, info = _npc_operation(state, action)
    elif action.layer == "population":
        new, info = _regional_operation(state, action)
    else:
        living, evidence = step_living(
            state.living, LivingAction(action.layer, action.verb,
                                      action.amount, action.target, action.option))
        new = replace(state, living=living)
        info = evidence.changes
        if action.layer == "causal" and action.verb == "end_turn":
            terrain, _ = step_terrain(
                state.terrain, TerrainAction("end_turn", 0, 0))
            thinkers = (select_active_brains(
                state.population, state.society, terrain, state.cognition,
                preset=state.population.fidelity)
                if state.population is not None else None)
            terrain, society, cognition, residents, thoughts = smart_npc_tick(
                terrain, state.society, state.cognition, active_ids=thinkers)
            new = replace(new, terrain=terrain, society=society,
                          cognition=cognition)
            if state.population is not None:
                regional, terrain, regional_events = tick_population(
                    state.population, society, new.terrain)
                new = replace(new, population=regional, terrain=terrain)
                info += regional_events
            deliveries = sum(rec.quantity for rec in residents if rec.operation == "deliver")
            total_thinking = len(residents) if thinkers is None else len(thinkers)
            info += (
                f"Autonomous citizens: {total_thinking} full cognitive decisions, "
                f"{len(residents)-total_thinking} real passive bodies; "
                f"{deliveries} physically delivered resource units; "
                f"{len(cognition.bonds)} tracked social relationships",
            )
    event_hash = _hash({
        "schema": SCHEMA, "world": law.design_id,
        "previous": state.event_head,
        "before": asdict(state), "after": asdict(new),
        "player_action": asdict(action), "changes": info,
    })
    result = replace(new, events=state.events + 1, event_head=event_hash)
    validate_product(result)
    return result, ProductReceipt(
        result.events, event_hash, action.layer, tuple(info),
        result.living.event_head, result.terrain.event_head,
        result.society.event_head,
    )


def product_save(state: ProductSession) -> str:
    law = validate_product(state)
    payload = {
        "schema": SCHEMA if state.population is not None else PRIOR_SCHEMA,
        "world_id": law.world_id, "design_id": law.design_id,
        "living": json.loads(save_living(state.living)),
        "terrain": json.loads(terrain_save(state.terrain)),
        "society": society_save(state.society),
        "cognition": cognition_save(state.cognition),
        "events": state.events, "event_head": state.event_head,
        **({"population": population_save(state.population)}
           if state.population is not None else {}),
    }
    return json.dumps(
        {"payload": payload, "checksum": _hash(payload)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def product_restore(value: str) -> ProductSession:
    if not isinstance(value, str) or len(value.encode("utf-8")) > SAVED_BYTES_LIMIT:
        raise FoundationError("product save oversized or invalid")
    try:
        data = json.loads(value)
        if set(data) != {"payload", "checksum"} or data["checksum"] != _hash(data["payload"]):
            raise FoundationError("product checksum mismatch")
        obj = data["payload"]
        common = {"schema", "world_id", "design_id", "living",
                  "terrain", "society", "events", "event_head"}
        if (obj["schema"] == SCHEMA
                and set(obj) == common | {"cognition", "population"}):
            current, has_population = True, True
        elif (obj["schema"] == SCHEMA
              and set(obj) == common | {"cognition"}):
            current, has_population = True, False
        elif (obj["schema"] == PRIOR_SCHEMA
              and set(obj) == common | {"cognition"}):
            current, has_population = True, False
        elif obj["schema"] == LEGACY_SCHEMA and set(obj) == common:
            current, has_population = False, False
        else:
            raise FoundationError("wrong product save version or unexpected fields")
        terrain = terrain_restore(json.dumps(obj["terrain"]))
        living = restore_living(json.dumps(obj["living"]))
        society = society_restore(obj["society"], terrain)
        if current:
            cognition = cognition_restore(obj["cognition"], society, terrain)
        else:
            # Preserve older playable saves; introduce the cognitive layer with
            # no fabricated past memories or relationships.
            cognition = replace(make_intelligence(terrain, society),
                                day=society.tick)
        regional = (population_restore(obj["population"], society, terrain)
                    if has_population else None)
        result = ProductSession(
            obj["world_id"], living, terrain, society,
            obj["events"], obj["event_head"], cognition, regional,
        )
        if validate_product(result).design_id != obj["design_id"]:
            raise FoundationError("underlying authored world changed across save")
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise FoundationError("product session save rejected") from exc
