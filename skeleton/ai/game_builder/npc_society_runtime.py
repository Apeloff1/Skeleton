"""Original NPC society: deterministic motives, beliefs, schedules and interactions.

Bounded agent autonomy under a transparent decision policy. Not a neural
language model. States are immutable, events are causal and replayable, and
LOD conserves CPU without sacrificing the persistence of citizens.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re

from .contracts import canonical_digest
from .quest_scene_engine import DirectorWorld, DirectorError

MAX_CITIZENS = 512
MEMORY_LIMIT = 24
_REL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ROLES = ("grower", "artisan", "watcher", "scribe", "healer", "courier",
         "explorer", "builder", "cook", "mediator", "scholar", "guard")
MOTIVES = ("safety", "belonging", "mastery", "freedom", "discovery", "prosperity")
INTENTS = ("rest", "work", "socialize", "explore", "assist", "trade", "protect")


class SocietyError(ValueError):
    """Impossible NPC transition, policy violation or invalid social evidence."""


def ident(s):
    if not isinstance(s, str) or not _REL.fullmatch(s):
        raise SocietyError("invalid original citizen or scene identity")
    return s


def integer(n, low, high):
    if type(n) is not int or not low <= n <= high:
        raise SocietyError("invalid bounded NPC attribute")
    return n


@dataclass(frozen=True, slots=True)
class Citizen:
    key: str
    name: str
    profession: str
    faction: str
    home: str
    workplace: str
    meeting_place: str
    motive: str
    bravery: int = 50
    empathy: int = 50
    curiosity: int = 50
    diligence: int = 50

    def __post_init__(self):
        ident(self.key)
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 90:
            raise SocietyError("citizen needs an original authored name")
        for s in (self.profession, self.faction, self.home, self.workplace,
                  self.meeting_place):
            ident(s)
        if self.motive not in MOTIVES:
            raise SocietyError("unknown intrinsic social motivation")
        for n in (self.bravery, self.empathy, self.curiosity, self.diligence):
            integer(n, 0, 100)

    def payload(self):
        return dict(key=self.key, name=self.name, profession=self.profession,
                    faction=self.faction, home=self.home, workplace=self.workplace,
                    meeting_place=self.meeting_place, motive=self.motive,
                    bravery=self.bravery, empathy=self.empathy,
                    curiosity=self.curiosity, diligence=self.diligence)


@dataclass(frozen=True, slots=True)
class Memory:
    event: str
    subject: str
    scene: str
    turn: int
    valence: int
    certainty: int
    origin: str

    def __post_init__(self):
        for s in (self.event, self.subject, self.scene, self.origin):
            ident(s)
        integer(self.turn, 0, 1000000)
        integer(self.valence, -100, 100)
        integer(self.certainty, 0, 100)

    def payload(self):
        return dict(event=self.event, subject=self.subject, scene=self.scene,
                    turn=self.turn, valence=self.valence, certainty=self.certainty,
                    origin=self.origin)


@dataclass(frozen=True, slots=True)
class Mind:
    key: str
    scene: str
    energy: int
    hunger: int
    stress: int
    belonging: int
    skill: int
    supplies: int
    intent: str
    memories: tuple[Memory, ...] = ()
    bonds: tuple[tuple[str, int], ...] = ()
    belief_flags: tuple[str, ...] = ()
    lod: str = "active"

    def __post_init__(self):
        ident(self.key); ident(self.scene)
        for v in (self.energy, self.hunger, self.stress, self.belonging, self.skill):
            integer(v, 0, 100)
        integer(self.supplies, 0, 255)
        if self.intent not in INTENTS or self.lod not in {"active", "ambient", "dormant"}:
            raise SocietyError("invalid actor intention/importance class")
        if len(self.memories) > MEMORY_LIMIT or any(not isinstance(m, Memory) for m in self.memories):
            raise SocietyError("unbounded or invented character memory")
        if any(not isinstance(k, str) or not -100 <= value <= 100
               for k, value in self.bonds):
            raise SocietyError("unbounded NPC relationship")
        if len({k for k, _ in self.bonds}) != len(self.bonds):
            raise SocietyError("duplicate social identity")
        for f in self.belief_flags:
            ident(f)

    def payload(self):
        return dict(key=self.key, scene=self.scene, energy=self.energy,
                    hunger=self.hunger, stress=self.stress,
                    belonging=self.belonging, skill=self.skill,
                    supplies=self.supplies, intent=self.intent,
                    memories=[m.payload() for m in self.memories],
                    bonds=[list(b) for b in self.bonds],
                    belief_flags=list(self.belief_flags), lod=self.lod)


@dataclass(frozen=True, slots=True)
class Society:
    project_digest: str
    world_digest: str
    profiles: tuple[Citizen, ...]
    minds: tuple[Mind, ...]
    turn: int = 0
    latest_event: str = "initial"

    def __post_init__(self):
        if len(self.profiles) == 0 or len(self.profiles) > MAX_CITIZENS:
            raise SocietyError("population exceeds bounded current implementation")
        if len(self.profiles) != len(self.minds):
            raise SocietyError("missing persistent NPC state")
        if len({p.key for p in self.profiles}) != len(self.profiles):
            raise SocietyError("duplicate original citizens")
        if tuple(p.key for p in self.profiles) != tuple(m.key for m in self.minds):
            raise SocietyError("mismatched profiles and minds")
        integer(self.turn, 0, 1000000)

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.npc_society.v1",
                    project_digest=self.project_digest,
                    world_digest=self.world_digest,
                    profiles=[p.payload() for p in self.profiles],
                    minds=[m.payload() for m in self.minds], turn=self.turn,
                    latest_event=self.latest_event)


def make_society(world: DirectorWorld, population: int, *, authorized: bool) -> Society:
    if not authorized:
        raise PermissionError("simulating citizens requires operator authority")
    if not isinstance(world, DirectorWorld):
        raise SocietyError("original authored scene world required")
    integer(population, 3, MAX_CITIZENS)
    scenes = [s.key for s in world.scenes]
    profiles, minds = [], []
    for i in range(population):
        key = f"citizen_{i:04d}"
        home = scenes[i % len(scenes)]
        work = scenes[(i * 3 + 1) % len(scenes)]
        meeting = scenes[(i * 7 + 2) % len(scenes)]
        profile = Citizen(
            key, f"Original Citizen {i+1}", ROLES[i % len(ROLES)],
            ("guild", "commons", "independents")[i % 3],
            home, work, meeting, MOTIVES[(i * 5 + world.seed) % len(MOTIVES)],
            (world.seed + i * 7) % 101,
            (world.seed // 2 + i * 11) % 101,
            (world.seed // 3 + i * 13) % 101,
            (world.seed // 4 + i * 17) % 101,
        )
        profiles.append(profile)
        minds.append(Mind(key, home, 85, 10, 5, 60, 25 + i % 25,
                          4, "rest"))
    return Society(world.digest, world.digest, tuple(profiles), tuple(minds))


def _distance(world: DirectorWorld, a: str, b: str) -> int:
    if a == b:
        return 0
    # Deterministic bounded graph reachability. No teleport.
    from collections import deque
    edges = {s.key: s.links for s in world.scenes}
    q = deque([(a, 0)])
    seen = {a}
    while q:
        node, distance = q.popleft()
        for neighbor in edges[node]:
            if neighbor == b:
                return distance + 1
            if neighbor not in seen:
                seen.add(neighbor)
                q.append((neighbor, distance + 1))
    raise SocietyError("citizen cannot reach an authored destination")


def _next_step(world: DirectorWorld, a: str, b: str) -> str:
    if a == b:
        return a
    here = next(s for s in world.scenes if s.key == a)
    return min(here.links, key=lambda node: (_distance(world, node, b), node))


def choose_intent(profile: Citizen, mind: Mind, phase: int,
                  *, nearby_threat: bool = False) -> str:
    """Deterministic utility arbitration with stable authored personality."""
    scores = {
        "rest": (100 - mind.energy) * 2 + (30 if phase >= 3 else 0),
        "work": profile.diligence + (35 if phase == 1 else 0) + mind.hunger,
        "socialize": 100 - mind.belonging + profile.empathy // 2,
        "explore": profile.curiosity + (20 if profile.motive == "discovery" else 0),
        "assist": profile.empathy + (30 if profile.motive == "belonging" else 0),
        "trade": mind.hunger + (40 if mind.supplies <= 1 else 0),
        "protect": profile.bravery + (100 if nearby_threat else -30),
    }
    if mind.stress >= 80:
        scores["rest"] += 90
    # Fair tie-break does not depend on dict iteration or hash seed.
    return min(scores, key=lambda key: (-scores[key], key))


def _remember(mind: Mind, memory: Memory) -> Mind:
    # Importance + recency bounded memory. Preserve high-valence history.
    previous = [m for m in mind.memories if (m.event, m.subject) !=
                (memory.event, memory.subject)]
    previous.append(memory)
    if len(previous) > MEMORY_LIMIT:
        previous.sort(key=lambda m: (abs(m.valence) * m.certainty,
                                      m.turn, m.event), reverse=True)
        previous = previous[:MEMORY_LIMIT]
        previous.sort(key=lambda m: (m.turn, m.event, m.subject))
    return replace(mind, memories=tuple(previous))


def apply_world_event(society: Society, world: DirectorWorld, *,
                      event: str, subject: str, scene: str, valence: int,
                      authorized: bool, witnesses: tuple[str, ...] = ()) -> Society:
    if not authorized:
        raise PermissionError("scene consequence propagation requires authority")
    if society.world_digest != world.digest:
        raise SocietyError("narrative cannot mutate a different authored world")
    for value in (event, subject, scene):
        ident(value)
    integer(valence, -100, 100)
    if scene not in {s.key for s in world.scenes}:
        raise SocietyError("world event references uncreated scene")
    if any(key not in {p.key for p in society.profiles} for key in witnesses):
        raise SocietyError("invented NPC event witness")
    minds = []
    for mind in society.minds:
        observed = mind.scene == scene and (not witnesses or mind.key in witnesses)
        if not observed:
            minds.append(mind)
            continue
        memory = Memory(event, subject, scene, society.turn,
                        valence, 100, "observed")
        remembered = _remember(mind, memory)
        beliefs = tuple(sorted(set((*remembered.belief_flags, event))))
        bonds = dict(remembered.bonds)
        bonds[subject] = max(-100, min(100, bonds.get(subject, 0) + valence // 5))
        minds.append(replace(
            remembered, stress=max(0, min(100, remembered.stress - valence // 4)),
            belonging=max(0, min(100, remembered.belonging + valence // 5)),
            bonds=tuple(sorted(bonds.items())), belief_flags=beliefs,
        ))
    return replace(society, minds=tuple(minds), latest_event=event)


def society_tick(society: Society, world: DirectorWorld, *, player_scene: str,
                 active_budget: int, ambient_budget: int,
                 threat_scene: str | None = None, authorized: bool) -> Society:
    if not authorized:
        raise PermissionError("citizen simulation requires operator authority")
    if society.world_digest != world.digest:
        raise SocietyError("foreign original NPC world")
    scenes = {s.key for s in world.scenes}
    if player_scene not in scenes or (threat_scene is not None and threat_scene not in scenes):
        raise SocietyError("NPC attention references invalid world position")
    integer(active_budget, 0, MAX_CITIZENS)
    integer(ambient_budget, 0, MAX_CITIZENS)
    if society.turn >= 1000000:
        raise SocietyError("simulated world clock exceeded")
    phase = ((society.turn + 1) // 3) % 4
    # Attention is a deterministic scheduler; preserve every citizen even
    # when only a fraction are actively simulated.
    ranked = sorted(zip(society.profiles, society.minds),
                    key=lambda item: (
                        0 if item[1].scene == player_scene else 1,
                        _distance(world, item[1].scene, player_scene),
                        item[0].key,
                    ))
    active = {p.key for p, m in ranked[:active_budget]}
    ambient = {p.key for p, m in ranked[active_budget:
                                    active_budget + ambient_budget]}
    next_minds = []
    for profile, mind in zip(society.profiles, society.minds):
        priority = ("active" if profile.key in active else
                    "ambient" if profile.key in ambient else "dormant")
        if priority == "dormant":
            # Cheap continuity: needs still progress; no fictional travel.
            next_minds.append(replace(
                mind, lod=priority, hunger=min(100, mind.hunger + 1),
                energy=max(0, mind.energy - 1),
            ))
            continue
        action = choose_intent(profile, mind, phase,
                               nearby_threat=(mind.scene == threat_scene))
        location = mind.scene
        target = {
            "rest": profile.home, "work": profile.workplace,
            "socialize": profile.meeting_place,
            "explore": profile.meeting_place, "assist": player_scene,
            "trade": profile.workplace, "protect": threat_scene or profile.home,
        }[action]
        if priority == "active" and target != location:
            location = _next_step(world, location, target)
        updated = replace(
            mind, scene=location, intent=action, lod=priority,
            energy=max(0, min(100, mind.energy + (10 if action == "rest" else -2))),
            hunger=max(0, min(100, mind.hunger + (-8 if action == "trade" else 2))),
            stress=max(0, mind.stress - (3 if action == "rest" else 0)),
            belonging=max(0, min(100, mind.belonging +
                                 (3 if action == "socialize" else -1))),
            supplies=min(255, mind.supplies +
                         (1 if action == "work" and location == target else 0)),
            skill=min(100, mind.skill + (1 if action == "work" else 0)),
        )
        next_minds.append(updated)
    return replace(society, minds=tuple(next_minds), turn=society.turn + 1,
                   latest_event="simulated_tick")


def society_replay(world: DirectorWorld, population: int, *,
                   steps: int, player_scene: str, active_budget: int = 24,
                   ambient_budget: int = 48, authorized: bool) -> dict:
    if not authorized:
        raise PermissionError("NPC simulation replay requires operator authority")
    integer(steps, 1, 100)
    initial = make_society(world, population, authorized=True)
    society = initial
    hashes = []
    for _ in range(steps):
        society = society_tick(society, world, player_scene=player_scene,
                              active_budget=active_budget,
                              ambient_budget=ambient_budget, authorized=True)
        hashes.append(society.digest)
    return dict(schema="skeleton.game_builder.npc_society_replay.v1",
                world_digest=world.digest, first_digest=initial.digest,
                final_digest=society.digest, turns=steps,
                state_digests=hashes, full_population=len(society.minds),
                actively_simulated=sum(m.lod == "active" for m in society.minds),
                ambient=sum(m.lod == "ambient" for m in society.minds),
                persistent_dormant=sum(m.lod == "dormant" for m in society.minds),
                final=society.payload())


__all__ = [
    "SocietyError", "Citizen", "Memory", "Mind", "Society", "make_society",
    "choose_intent", "apply_world_event", "society_tick", "society_replay",
]
