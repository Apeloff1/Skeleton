"""Deterministic, original narrative RPG simulation: living NPCs and quests.

A second *executable* game genre, not a decorative content catalog.
Schedules advance on every action; world travel follows a real graph;
conversations, resources, faction trust, quest resolution and endings all
change a typed and replay-verifiable game state. Open-ended modes never
require an ending. No provider, external model or copyrighted game asset.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import random
import re
from typing import Sequence

from .contracts import canonical_digest


class StoryError(ValueError):
    """Malformed story data, invalid simulation action or forged proof."""


REGION_ROOTS = (
    "Amber", "Azure", "Briar", "Cinder", "Dawn", "Echo", "Fern", "Glass",
    "Harbor", "Ivory", "Juniper", "Kite", "Lumen", "Moss", "North", "Opal",
    "Pine", "Quartz", "River", "Silver", "Thistle", "Umber", "Vale", "Willow",
)
REGION_SUFFIXES = ("Reach", "Garden", "Market", "Hollow", "Pass", "Harbor",
                   "Crossing", "Grove", "Station", "Commons", "Terrace", "Basin")
NAMES = ("Alma", "Bran", "Cleo", "Daren", "Eira", "Fenn", "Galen", "Hana",
         "Ivo", "Jori", "Kira", "Lio", "Mara", "Nico", "Oren", "Pia",
         "Quin", "Rhea", "Soren", "Tavi", "Uma", "Vero", "Wren", "Xeni")
ROLES = ("grower", "cartographer", "tinkerer", "healer", "courier", "poet",
         "cook", "maker", "watcher", "naturalist", "builder", "scribe")
FACTIONS = ("gardeners", "wayfinders", "makers")
ENDING_IDS = ("stewardship", "discovery", "independence")
MAX_TURNS = 1024
MOVE_SPAN = 3
CYCLE = 12
STORY_SCHEMA = "skeleton.game_builder.living_story.v1"


def _id(text: object, *, limit: int = 96) -> str:
    if not isinstance(text, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0," + str(limit - 1) + r"}", text):
        raise StoryError("invalid game identifier")
    return text


@dataclass(frozen=True, slots=True)
class StoryIntent:
    project_id: str
    title: str
    seed: int
    regions: int = 7
    population: int = 24
    mode: str = "postgame"
    quests_to_finish: int = 2
    quest_arcs: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.project_id
        ):
            raise StoryError("invalid original story project ID")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= 120 or any(
            ord(x) < 32 for x in self.title
        ):
            raise StoryError("invalid original story title")
        if type(self.seed) is not int or not 0 <= self.seed < 2**63:
            raise StoryError("story seed outside safe range")
        if type(self.regions) is not int or not 4 <= self.regions <= 12:
            raise StoryError("story region budget is 4-12")
        if type(self.population) is not int or not 6 <= self.population <= 128:
            raise StoryError("story population budget is 6-128")
        if self.mode not in {"campaign", "postgame", "sandbox"}:
            raise StoryError("unknown world mode")
        if type(self.quest_arcs) is not int or not 3 <= self.quest_arcs <= 24:
            raise StoryError("living RPG must have 3 to 24 original quest arcs")
        if self.population < self.quest_arcs:
            raise StoryError("one unique quest-giving NPC required per original quest arc")
        if (type(self.quests_to_finish) is not int
                or not 1 <= self.quests_to_finish <= self.quest_arcs):
            raise StoryError("story milestone requires 1 to original arc count")

    def payload(self) -> dict[str, object]:
        return {"project_id": self.project_id, "title": self.title, "seed": self.seed,
                "regions": self.regions, "population": self.population,
                "mode": self.mode, "quests_to_finish": self.quests_to_finish,
                "quest_arcs": self.quest_arcs}


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    name: str
    neighbors: tuple[str, ...]
    atmosphere: str

    def payload(self) -> dict[str, object]:
        return {"key": self.key, "name": self.name,
                "neighbors": list(self.neighbors), "atmosphere": self.atmosphere}


@dataclass(frozen=True, slots=True)
class Citizen:
    key: str
    name: str
    role: str
    faction: str
    home: str
    workplace: str
    lookout: str
    temperament: str

    def payload(self) -> dict[str, object]:
        return vars_dict(self)


@dataclass(frozen=True, slots=True)
class Quest:
    key: str
    giver: str
    item: str
    source_region: str
    faction: str
    reward: int
    premise: str

    def payload(self) -> dict[str, object]:
        return vars_dict(self)


def vars_dict(obj: object) -> dict[str, object]:
    return {key: getattr(obj, key) for key in obj.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class StoryWorld:
    intent: StoryIntent
    regions: tuple[Region, ...]
    citizens: tuple[Citizen, ...]
    quests: tuple[Quest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.intent, StoryIntent):
            raise StoryError("story requires typed intent")
        if len(self.regions) != self.intent.regions or len(self.citizens) != self.intent.population:
            raise StoryError("actual world resource count differs from budget")
        if len(self.quests) != self.intent.quest_arcs:
            raise StoryError("actual original quest count differs from budget")
        ids = {r.key for r in self.regions}
        if len(ids) != len(self.regions) or any(
            not isinstance(r, Region) or r.key not in ids
            or any(neighbor not in ids for neighbor in r.neighbors)
            or not r.neighbors or r.key in r.neighbors
            for r in self.regions
        ):
            raise StoryError("invalid region graph")
        graph = {r.key: set(r.neighbors) for r in self.regions}
        if any(r.key not in graph[n] for r in self.regions for n in r.neighbors):
            raise StoryError("world graph links must be bidirectional")
        if len(_routes(graph, self.regions[0].key)) != len(ids):
            raise StoryError("story world contains unreachable regions")
        citizens = {c.key: c for c in self.citizens}
        if len(citizens) != len(self.citizens) or any(
            c.home not in ids or c.workplace not in ids or c.lookout not in ids
            or c.faction not in FACTIONS for c in self.citizens
        ):
            raise StoryError("invalid citizen schedule or faction")
        if (len({q.key for q in self.quests}) != len(self.quests)
                or len({q.item for q in self.quests}) != len(self.quests)):
            raise StoryError("original quests need distinct objectives")
        if any(q.giver not in citizens or q.source_region not in ids
               or q.faction != citizens[q.giver].faction for q in self.quests):
            raise StoryError("quest references an absent original citizen")

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {"schema": STORY_SCHEMA, "intent": self.intent.payload(),
                "regions": [r.payload() for r in self.regions],
                "citizens": [c.payload() for c in self.citizens],
                "quests": [q.payload() for q in self.quests]}


def _routes(graph: dict[str, set[str]], origin: str) -> dict[str, tuple[str, ...]]:
    paths = {origin: ()}
    todo = deque([origin])
    while todo:
        here = todo.popleft()
        for neighbor in sorted(graph[here]):
            if neighbor not in paths:
                paths[neighbor] = (*paths[here], neighbor)
                todo.append(neighbor)
    return paths


def original_story_world(intent: StoryIntent, *, authorized: bool) -> StoryWorld:
    if not authorized:
        raise PermissionError("story creation requires local operator authority")
    if not isinstance(intent, StoryIntent):
        raise StoryError("typed story intent required")
    rng = random.Random(intent.seed)
    roots = rng.sample(REGION_ROOTS, intent.regions)
    regions = []
    for index in range(intent.regions):
        neighbor_indices = {
            (index - 1) % intent.regions, (index + 1) % intent.regions,
        }
        # A bidirectional long-distance ferry link expands meaningful route
        # options without allowing arbitrary teleportation.
        if intent.regions >= 6:
            neighbor_indices.add((index + intent.regions // 2) % intent.regions)
            neighbor_indices.add((index - intent.regions // 2) % intent.regions)
        suffix = REGION_SUFFIXES[(index + rng.randrange(len(REGION_SUFFIXES))) % len(REGION_SUFFIXES)]
        regions.append(Region(
            key=f"region_{index:02d}", name=roots[index] + " " + suffix,
            neighbors=tuple(f"region_{n:02d}" for n in sorted(neighbor_indices)),
            atmosphere=("sunrise terraces", "rainwashed streets", "lively workshops",
                        "quiet lantern paths")[index % 4],
        ))
    citizens = []
    for index in range(intent.population):
        home = regions[index % intent.regions].key
        workplace = regions[(index + 2) % intent.regions].key
        lookout = regions[(index + 3) % intent.regions].key
        role = ROLES[index % len(ROLES)]
        citizens.append(Citizen(
            key=f"npc_{index:03d}",
            name=NAMES[index % len(NAMES)] + (" " + roots[index % len(roots)]),
            role=role, faction=FACTIONS[index % 3],
            home=home, workplace=workplace, lookout=lookout,
            temperament=("curious", "patient", "inventive", "careful")[rng.randrange(4)],
        ))
    quests = []
    verbs = (
        "Restore the seed archive", "Chart the lost footpath",
        "Repair the communal beacon", "Shelter the migratory birds",
        "Recover the village records", "Rebuild a quiet bridge",
        "Plant the last moonflower", "Map the hidden springs",
        "Craft a lantern for night travel", "Reopen a mountain trail",
        "Prepare the shared orchard", "Repair the weather station",
    )
    for index in range(intent.quest_arcs):
        leader = citizens[index]
        source = regions[(index * 2 + 3) % len(regions)].key
        quests.append(Quest(
            key=f"quest_{index:02d}", giver=leader.key,
            item=f"artifact_{index:02d}", source_region=source,
            faction=leader.faction, reward=20 + index * 5,
            premise=verbs[index % len(verbs)] + (
                f" — chapter {index // len(verbs) + 1}"
                if index >= len(verbs) else ""
            ),
        ))
    return StoryWorld(intent, tuple(regions), tuple(citizens), tuple(quests))


def npc_region(npc: Citizen, turn: int) -> str:
    if type(turn) is not int or not 0 <= turn <= MAX_TURNS:
        raise StoryError("invalid schedule turn")
    phase = (turn // MOVE_SPAN) % 4
    # Citizens work, visit the social hub and return home each day.
    return (npc.home, npc.workplace, npc.lookout, npc.home)[phase]


@dataclass(frozen=True, slots=True)
class StoryState:
    world_digest: str
    location: str
    turn: int
    inventory: tuple[str, ...]
    known: tuple[str, ...]
    completed: tuple[str, ...]
    discussed: tuple[str, ...]
    faction_trust: tuple[int, int, int]
    ending: str | None
    status: str
    score: int

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {"world_digest": self.world_digest, "location": self.location,
                "turn": self.turn, "inventory": list(self.inventory),
                "known": list(self.known), "completed": list(self.completed),
                "discussed": list(self.discussed),
                "faction_trust": list(self.faction_trust), "ending": self.ending,
                "status": self.status, "score": self.score}


def _check_state(world: StoryWorld, state: StoryState) -> None:
    if not isinstance(world, StoryWorld) or not isinstance(state, StoryState):
        raise StoryError("typed story world and player state required")
    if state.world_digest != world.digest:
        raise StoryError("narrative replay refers to another original world")
    if state.location not in {r.key for r in world.regions}:
        raise StoryError("player location outside original world")
    if type(state.turn) is not int or not 0 <= state.turn <= MAX_TURNS:
        raise StoryError("story turn budget exceeded")
    quests = {q.key for q in world.quests}
    items = {q.item for q in world.quests}
    citizens = {c.key for c in world.citizens}
    for values, domain in ((state.inventory, items), (state.known, quests),
                           (state.completed, quests), (state.discussed, citizens)):
        if not isinstance(values, tuple) or tuple(sorted(set(values))) != values or set(values) - domain:
            raise StoryError("story state contains duplicate/foreign progress")
    if any(q.key in state.completed and q.item in state.inventory for q in world.quests):
        raise StoryError("a delivered quest item cannot remain in inventory")
    if (not isinstance(state.faction_trust, tuple)
            or len(state.faction_trust) != 3
            or any(type(x) is not int or not 0 <= x <= 100 for x in state.faction_trust)):
        raise StoryError("faction reputation outside safe range")
    if type(state.score) is not int or not 0 <= state.score <= sum(q.reward for q in world.quests):
        raise StoryError("game score contradicts quest reward budget")
    if state.score != sum(q.reward for q in world.quests if q.key in state.completed):
        raise StoryError("story score must match independently completed quest evidence")
    expected_trust = tuple(min(100, sum(
        25 for q in world.quests if q.key in state.completed and q.faction == faction
    )) for faction in FACTIONS)
    if state.faction_trust != expected_trust:
        raise StoryError("forged faction reputation")
    if state.ending is not None and state.ending not in ENDING_IDS:
        raise StoryError("unrecognized story ending")
    if state.ending is not None and len(state.completed) < world.intent.quests_to_finish:
        raise StoryError("ending claimed before required quests completed")
    if state.ending is not None and state.faction_trust[ENDING_IDS.index(state.ending)] < 25:
        raise StoryError("story ending was claimed without earning its faction support")
    expected_status = (
        "playing" if state.ending is None else
        "won" if world.intent.mode == "campaign" else
        "epilogue" if world.intent.mode == "postgame" else "open"
    )
    if state.status != expected_status:
        raise StoryError("world mode and progress status diverged")


def first_story_state(world: StoryWorld, *, authorized: bool) -> StoryState:
    if not authorized:
        raise PermissionError("story state creation requires authorization")
    if not isinstance(world, StoryWorld):
        raise StoryError("typed world required")
    state = StoryState(world.digest, world.regions[0].key, 0, (), (), (), (),
                       (0, 0, 0), None, "playing", 0)
    _check_state(world, state)
    return state


def story_choices(world: StoryWorld, state: StoryState) -> tuple[str, ...]:
    _check_state(world, state)
    if state.status == "won" or state.turn >= MAX_TURNS:
        return ()
    region = next(r for r in world.regions if r.key == state.location)
    choices = ["wait"]
    choices.extend("travel:" + n for n in region.neighbors)
    for quest in world.quests:
        if (quest.key not in state.completed and quest.item not in state.inventory
                and quest.source_region == state.location):
            choices.append("gather:" + quest.item)
    for citizen in world.citizens:
        if npc_region(citizen, state.turn) == state.location:
            if citizen.key not in state.discussed:
                choices.append("talk:" + citizen.key)
            for quest in world.quests:
                if (quest.giver == citizen.key and quest.key in state.known
                        and quest.item in state.inventory and quest.key not in state.completed):
                    choices.append("resolve:" + quest.key)
    if state.ending is None and len(state.completed) >= world.intent.quests_to_finish:
        choices.extend(
            "choose:" + ending for i, ending in enumerate(ENDING_IDS)
            if state.faction_trust[i] >= 25
        )
    return tuple(choices)


def story_step(world: StoryWorld, state: StoryState, action: str, *, authorized: bool) -> StoryState:
    if not authorized:
        raise PermissionError("story action requires authorization")
    _check_state(world, state)
    if not isinstance(action, str) or action not in story_choices(world, state):
        raise StoryError("action is unavailable or story session is terminal")
    if state.turn >= MAX_TURNS:
        raise StoryError("story turn ceiling reached")
    location = state.location
    inv = set(state.inventory)
    known = set(state.known)
    completed = set(state.completed)
    discussed = set(state.discussed)
    ending = state.ending
    if action.startswith("travel:"):
        location = action[7:]
    elif action.startswith("gather:"):
        inv.add(action[7:])
    elif action.startswith("talk:"):
        who = action[5:]
        discussed.add(who)
        known.update(q.key for q in world.quests if q.giver == who)
    elif action.startswith("resolve:"):
        key = action[8:]
        quest = next(q for q in world.quests if q.key == key)
        inv.remove(quest.item)
        completed.add(key)
    elif action.startswith("choose:"):
        ending = action[7:]
    trust = tuple(min(100, sum(
        25 for q in world.quests if q.key in completed and q.faction == faction
    )) for faction in FACTIONS)
    status = ("playing" if ending is None else
              "won" if world.intent.mode == "campaign" else
              "epilogue" if world.intent.mode == "postgame" else "open")
    result = StoryState(
        world.digest, location, state.turn + 1,
        tuple(sorted(inv)), tuple(sorted(known)), tuple(sorted(completed)),
        tuple(sorted(discussed)), trust, ending, status,
        sum(q.reward for q in world.quests if q.key in completed),
    )
    _check_state(world, result)
    return result


def dialogue_line(world: StoryWorld, state: StoryState, citizen_id: str) -> str:
    _check_state(world, state)
    npc = next((c for c in world.citizens if c.key == citizen_id), None)
    if npc is None:
        raise StoryError("dialogue references an unknown citizen")
    phase = ("morning", "working hours", "evening", "night")[state.turn // MOVE_SPAN % 4]
    quest = next((q for q in world.quests if q.giver == npc.key), None)
    if quest is not None and quest.key in state.completed:
        purpose = "Your work helped our community thrive."
    elif quest is not None and quest.item in state.inventory:
        purpose = "You found our missing item. Please bring it to me."
    elif quest is not None:
        purpose = quest.premise + " — seek the artifact in " + next(
            r.name for r in world.regions if r.key == quest.source_region
        ) + "."
    else:
        purpose = "I keep notes on our changing paths and visitors."
    return f"{npc.name}, the {npc.temperament} {npc.role} ({npc.faction}), says during {phase}: {purpose}"


@dataclass(frozen=True, slots=True)
class StoryActionReceipt:
    index: int
    action: str
    before_digest: str
    after_digest: str
    predecessor: str | None

    @property
    def digest(self) -> str:
        return canonical_digest(vars_dict(self))

    def payload(self) -> dict[str, object]:
        return {**vars_dict(self), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class StoryReplay:
    world_digest: str
    initial_digest: str
    receipts: tuple[StoryActionReceipt, ...]
    final: StoryState

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {"schema": "skeleton.game_builder.living_story_replay.v1",
                "world_digest": self.world_digest,
                "initial_digest": self.initial_digest,
                "actions": [r.payload() for r in self.receipts],
                "final": self.final.payload()}


def story_play(world: StoryWorld, actions: Sequence[str], *, authorized: bool) -> StoryReplay:
    if not authorized:
        raise PermissionError("story replay requires operator authorization")
    if not isinstance(actions, (tuple, list)) or len(actions) > MAX_TURNS:
        raise StoryError("bounded sequence of story actions required")
    state = first_story_state(world, authorized=True)
    before = state.digest
    chain = []
    for index, action in enumerate(actions):
        nxt = story_step(world, state, action, authorized=True)
        chain.append(StoryActionReceipt(
            index, action, state.digest, nxt.digest,
            chain[-1].digest if chain else None,
        ))
        state = nxt
    return StoryReplay(world.digest, before, tuple(chain), state)


def story_verify(world: StoryWorld, replay: StoryReplay, *, authorized: bool) -> None:
    if not authorized:
        raise PermissionError("story proof verification requires authorization")
    if not isinstance(world, StoryWorld) or not isinstance(replay, StoryReplay):
        raise StoryError("typed original story and replay required")
    if replay.world_digest != world.digest or len(replay.receipts) > MAX_TURNS:
        raise StoryError("replay world identity/action budget mismatch")
    state = first_story_state(world, authorized=True)
    if state.digest != replay.initial_digest:
        raise StoryError("story genesis state was forged")
    predecessor = None
    for index, row in enumerate(replay.receipts):
        if (not isinstance(row, StoryActionReceipt) or row.index != index
                or row.predecessor != predecessor or row.before_digest != state.digest):
            raise StoryError("narrative replay chain tampering")
        state = story_step(world, state, row.action, authorized=True)
        if row.after_digest != state.digest:
            raise StoryError("narrative replay transition mismatch")
        predecessor = row.digest
    if replay.final != state:
        raise StoryError("narrative replay final-state corruption")


def _path(world: StoryWorld, source: str, destination: str) -> tuple[str, ...]:
    graph = {r.key: set(r.neighbors) for r in world.regions}
    paths = _routes(graph, source)
    if destination not in paths:
        raise StoryError("quest source disconnected")
    return paths[destination]


def demonstrate_story(
    world: StoryWorld, *, authorized: bool, ending: str = "stewardship",
) -> StoryReplay:
    """Actually solve authored quests and NPC time windows through real actions."""
    if not authorized:
        raise PermissionError("narrative witness requires authorization")
    if not isinstance(world, StoryWorld) or ending not in ENDING_IDS:
        raise StoryError("unknown original narrative ending")
    state = first_story_state(world, authorized=True)
    actions: list[str] = []

    def perform(action: str) -> None:
        nonlocal state
        if action not in story_choices(world, state):
            raise StoryError("narrative proof attempted a forbidden action")
        state = story_step(world, state, action, authorized=True)
        actions.append(action)

    def move(destination: str) -> None:
        for region in _path(world, state.location, destination):
            perform("travel:" + region)

    def meet(citizen: Citizen) -> None:
        # Wait at the citizen's home; work and social schedules have bounded
        # 12-turn periods. This is a genuine timing constraint, not teleport.
        move(citizen.home)
        for _ in range(CYCLE + 1):
            if npc_region(citizen, state.turn) == state.location:
                return
            perform("wait")
        raise StoryError("scheduled NPC missed a full day at home")

    # The three endings are *causally earned*, never three renamed buttons.
    # A player must have resolved at least one real faction quest matching
    # the selected outcome, in addition to the global progression budget.
    required_faction = FACTIONS[ENDING_IDS.index(ending)]
    signature_quest = next(
        q for q in world.quests if q.faction == required_faction
    )
    selected = [signature_quest]
    selected.extend(q for q in world.quests if q.key != signature_quest.key)
    for quest in selected[:world.intent.quests_to_finish]:
        npc = next(c for c in world.citizens if c.key == quest.giver)
        meet(npc)
        perform("talk:" + npc.key)
        move(quest.source_region)
        perform("gather:" + quest.item)
        meet(npc)
        perform("resolve:" + quest.key)
    perform("choose:" + ending)
    proof = story_play(world, tuple(actions), authorized=True)
    story_verify(world, proof, authorized=True)
    if proof.final.ending != ending or (
        world.intent.mode == "campaign" and proof.final.status != "won"
    ):
        raise StoryError("story witness did not reach requested narrative ending")
    if world.intent.mode != "campaign":
        if not story_choices(world, proof.final):
            raise StoryError("nonterminal story world was not replayable after ending")
        # Verify a meaningful action after the ending to prove persistence.
        epilogue = story_play(
            world, (*actions, story_choices(world, proof.final)[0]), authorized=True,
        )
        story_verify(world, epilogue, authorized=True)
        if epilogue.final.turn <= proof.final.turn:
            raise StoryError("post-completion world did not remain playable")
    return proof


__all__ = [
    "StoryError", "StoryIntent", "StoryWorld", "StoryState",
    "Region", "Citizen", "Quest", "StoryActionReceipt", "StoryReplay",
    "original_story_world", "npc_region", "first_story_state",
    "story_choices", "story_step", "story_play", "story_verify",
    "demonstrate_story", "dialogue_line", "ENDING_IDS", "MAX_TURNS",
]
