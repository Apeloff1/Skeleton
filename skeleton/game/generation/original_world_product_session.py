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
)

SCHEMA = "original-world-playable-product-session.v2"
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
    if state.society.tick != state.living.living_turns or state.terrain.turns != state.living.living_turns:
        raise FoundationError("source-world, landscape and actor clocks diverged")
    if type(state.events) is not int or not 0 <= state.events <= LIMIT:
        raise FoundationError("invalid product event budget")
    if not isinstance(state.event_head, str) or len(state.event_head) != 64:
        raise FoundationError("invalid product receipt")
    return law


def create_product(index: int, *, inhabitants: int = 12) -> ProductSession:
    law = living_at(index)
    physical = create_terrain(
        law.design_id, BIOMES_BY_ARCH[law.source.spatial.architecture.architecture_id])
    inhabitants_state = create_society(physical, inhabitants)
    minds = make_intelligence(physical, inhabitants_state)
    game = ProductSession(law.world_id, create_living(index),
                          physical, inhabitants_state, cognition=minds)
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
    if action.verb == "commission":
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
    elif action.verb == "council":
        if world.position != (0, 0) or world.provisions < 1:
            raise FoundationError("public council requires depot and one food offering")
        if len(society.inhabitants) < 2:
            raise FoundationError("a public council needs at least two living residents")
        world = replace(world, provisions=world.provisions - 1)
        thinking = _bond_change(
            thinking, 0, 1, affinity=1, trust=1, aid=1)
        thinking = replace(thinking, meetings=thinking.meetings + 1,
                           interventions=thinking.interventions + 1)
        living = session.living
        message = "Public council spent real provisions and strengthened a recorded civic tie"
    else:
        raise FoundationError("unrecognized cognitive command")
    return replace(session, terrain=world, living=_spend_source_ap(living),
                   cognition=thinking), (message,)


def step_product(
    state: ProductSession, action: ProductAction,
) -> tuple[ProductSession, ProductReceipt]:
    law = validate_product(state)
    if state.events >= LIMIT:
        raise FoundationError("product receipt capacity exhausted")
    if not isinstance(action, ProductAction) or action.layer not in (
        "terrain", "living", "spatial", "mode", "arc", "causal", "studio", "npc",
    ):
        raise FoundationError("invalid product command layer")
    if type(action.amount) is not int or not 1 <= action.amount <= 3:
        raise FoundationError("product quantity must be 1..3")
    if type(action.target) is not int or not -1 <= action.target <= 23:
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
    else:
        living, evidence = step_living(
            state.living, LivingAction(action.layer, action.verb,
                                      action.amount, action.target, action.option))
        new = replace(state, living=living)
        info = evidence.changes
        if action.layer == "causal" and action.verb == "end_turn":
            terrain, _ = step_terrain(
                state.terrain, TerrainAction("end_turn", 0, 0))
            terrain, society, cognition, residents, thoughts = smart_npc_tick(
                terrain, state.society, state.cognition)
            new = replace(new, terrain=terrain, society=society,
                          cognition=cognition)
            deliveries = sum(rec.quantity for rec in residents if rec.operation == "deliver")
            info += (f"Cognitive citizens: {len(residents)} decisions, "
                     f"{deliveries} physically delivered resources; "
                     f"{len(cognition.bonds)} tracked social relationships",)
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
        "schema": SCHEMA, "world_id": law.world_id, "design_id": law.design_id,
        "living": json.loads(save_living(state.living)),
        "terrain": json.loads(terrain_save(state.terrain)),
        "society": society_save(state.society),
        "cognition": cognition_save(state.cognition),
        "events": state.events, "event_head": state.event_head,
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
        if set(obj) != {"schema", "world_id", "design_id", "living",
                        "terrain", "society", "events", "event_head"} or obj["schema"] != SCHEMA:
            raise FoundationError("wrong product save version")
        terrain = terrain_restore(json.dumps(obj["terrain"]))
        living = restore_living(json.dumps(obj["living"]))
        result = ProductSession(
            obj["world_id"], living, terrain,
            society_restore(obj["society"], terrain),
            obj["events"], obj["event_head"],
        )
        if validate_product(result).design_id != obj["design_id"]:
            raise FoundationError("underlying authored world changed across save")
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise FoundationError("product session save rejected") from exc
