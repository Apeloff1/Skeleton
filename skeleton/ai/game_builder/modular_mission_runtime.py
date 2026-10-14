"""Proof-backed mission graph algebra, dynamic stage placement and score engine.

Events come only from replayed authored scene actions. An AND/OR/k-of-n
expression accepts multiple genuine victory routes, with optional conditions,
timing and narrative consequences. The central story invariant is immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from collections import defaultdict

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorAction, DirectorError, DirectorReplay, DirectorWorld,
    director_initial, director_step, director_verify,
)

KIND_SET = frozenset((
    "inspect", "talk", "trade", "gather", "deliver", "craft", "repair",
    "build", "fight", "pacify", "negotiate", "sneak", "protect",
    "reinforce", "survive", "heal", "research", "attune", "infuse",
    "train", "solve", "escort_follow", "escort_leash",
    "escort_introduce", "travel", "activate", "interact", "discover",
    "wait", "quest_complete", "scene_enter", "npc_help", "npc_trust",
))
LANES = frozenset(("main", "story_arc", "regional", "side", "rival",
                   "profession", "world_event", "repeatable"))


class MissionError(ValueError):
    """Mission authoring violated a typed world fact or solver requirement."""


@dataclass(frozen=True, slots=True)
class Predicate:
    kind: str
    target: str
    quantity: int = 1
    location: str | None = None

    def __post_init__(self):
        if self.kind not in KIND_SET or not isinstance(self.target, str) or not self.target:
            raise MissionError("unknown original objective predicate")
        if type(self.quantity) is not int or not 1 <= self.quantity <= 200:
            raise MissionError("objective quantity budget exceeded")
        if self.location is not None and not isinstance(self.location, str):
            raise MissionError("invalid original scene filter")

    def payload(self):
        return dict(kind=self.kind,target=self.target,
                    quantity=self.quantity,location=self.location)


@dataclass(frozen=True, slots=True)
class Formula:
    op: str
    atoms: tuple[Predicate, ...] = ()
    children: tuple["Formula", ...] = ()
    threshold: int = 0

    def __post_init__(self):
        if self.op not in {"atom", "all", "any", "at_least"}:
            raise MissionError("unsupported mission formula operator")
        if self.op == "atom":
            if len(self.atoms) != 1 or self.children or self.threshold:
                raise MissionError("atomic victory must have exactly one predicate")
        else:
            if self.atoms or not 2 <= len(self.children) <= 12:
                raise MissionError("composite victory needs bounded child conditions")
            if any(not isinstance(c, Formula) for c in self.children):
                raise MissionError("mission formula contains untyped expression")
            if self.op == "at_least" and (type(self.threshold) is not int or
                                          not 1 <= self.threshold <= len(self.children)):
                raise MissionError("invalid k-of-n required objectives")
            if self.op != "at_least" and self.threshold:
                raise MissionError("threshold only applies to k-of-n conditions")
        if self.depth() > 6 or self.size() > 80:
            raise MissionError("mission objective expression is unbounded")

    def depth(self):
        return 1 + max((c.depth() for c in self.children), default=0)

    def size(self):
        return 1 + sum(c.size() for c in self.children)

    def payload(self):
        return dict(op=self.op,atoms=[a.payload() for a in self.atoms],
                    children=[c.payload() for c in self.children],
                    threshold=self.threshold)

    def evaluate(self, facts: Sequence["MissionFact"]) -> bool:
        if self.op == "atom":
            test = self.atoms[0]
            amount = sum(f.amount for f in facts if f.kind == test.kind and
                         f.target == test.target and
                         (test.location is None or f.scene == test.location))
            return amount >= test.quantity
        completed = [c.evaluate(facts) for c in self.children]
        return (
            all(completed) if self.op == "all" else
            any(completed) if self.op == "any" else
            sum(completed) >= self.threshold
        )


def atom(kind: str, target: str, quantity: int = 1,
         location: str | None = None) -> Formula:
    return Formula("atom", atoms=(Predicate(kind,target,quantity,location),))


@dataclass(frozen=True, slots=True)
class MissionFact:
    kind: str
    target: str
    scene: str
    turn: int
    amount: int
    source_digest: str
    actor: str = "player"

    def __post_init__(self):
        if self.kind not in KIND_SET:
            raise MissionError("unknown source action")
        if not all(isinstance(x,str) and x for x in
                   (self.target,self.scene,self.source_digest,self.actor)):
            raise MissionError("unidentifiable original event")
        if type(self.turn) is not int or not 0 <= self.turn <= 1000000:
            raise MissionError("event time exceeds mission clock")
        if type(self.amount) is not int or not 1 <= self.amount <= 200:
            raise MissionError("event evidence quantity must be real")

    def payload(self):
        return dict(kind=self.kind,target=self.target,scene=self.scene,
                    turn=self.turn,amount=self.amount,
                    source_digest=self.source_digest,actor=self.actor)


@dataclass(frozen=True, slots=True)
class ObjectiveStage:
    key: str
    premise: str
    victory: Formula
    optional: tuple[Formula, ...]
    allowed_scenes: tuple[str, ...]
    deadline: int = 200
    reward: int = 100
    consequence: str = "completed"
    cinematic: str | None = None

    def __post_init__(self):
        if not isinstance(self.key,str) or not self.key:
            raise MissionError("stage identity required")
        if not isinstance(self.premise,str) or not 1 <= len(self.premise) <= 1000:
            raise MissionError("stage lore must be authorable and bounded")
        if not isinstance(self.victory,Formula):
            raise MissionError("stage requires an expressive victory formula")
        if len(self.optional) > 12 or any(not isinstance(o,Formula) for o in self.optional):
            raise MissionError("bounded optional objectives required")
        if not self.allowed_scenes or len(self.allowed_scenes) > 16:
            raise MissionError("stage needs actual original game locations")
        if type(self.deadline) is not int or not 1 <= self.deadline <= 5000:
            raise MissionError("mission deadline out of bounds")
        if type(self.reward) is not int or not 0 <= self.reward <= 10000:
            raise MissionError("mission base reward exceeds budget")

    def payload(self):
        return dict(key=self.key,premise=self.premise,
                    victory=self.victory.payload(),
                    optional=[o.payload() for o in self.optional],
                    allowed_scenes=list(self.allowed_scenes),
                    deadline=self.deadline,reward=self.reward,
                    consequence=self.consequence,cinematic=self.cinematic)


@dataclass(frozen=True, slots=True)
class Mission:
    key: str
    lane: str
    main_goal: str
    prerequisites: tuple[str,...]
    stages: tuple[ObjectiveStage,...]
    placement: str = "story"
    repeat_limit: int = 1

    def __post_init__(self):
        if self.lane not in LANES or not self.key or not self.main_goal:
            raise MissionError("mission lane, identity and central context required")
        if not 1 <= len(self.stages) <= 16:
            raise MissionError("mission chapter budget exceeded")
        if len({s.key for s in self.stages}) != len(self.stages):
            raise MissionError("duplicate mission stage identity")
        if self.placement not in {"story","seeded","regional","choice"}:
            raise MissionError("unsupported mission placement")
        if type(self.repeat_limit) is not int or not 1 <= self.repeat_limit <= 32:
            raise MissionError("repeat budget exceeded")
        if self.lane != "repeatable" and self.repeat_limit != 1:
            raise MissionError("only explicitly repeatable missions can reset")

    def payload(self):
        return dict(key=self.key,lane=self.lane,main_goal=self.main_goal,
                    prerequisites=list(self.prerequisites),
                    stages=[s.payload() for s in self.stages],
                    placement=self.placement,repeat_limit=self.repeat_limit)


@dataclass(frozen=True, slots=True)
class MissionBook:
    world_digest: str
    invariant_goal: str
    missions: tuple[Mission,...]

    def __post_init__(self):
        if not 1 <= len(self.missions) <= 256:
            raise MissionError("mission book exceeds bounded authored scenes")
        keys = {m.key for m in self.missions}
        if len(keys) != len(self.missions) or not any(m.lane=="main" for m in self.missions):
            raise MissionError("main plot and unique quest identities required")
        for mission in self.missions:
            if mission.main_goal != self.invariant_goal:
                raise MissionError("side quest cannot rewrite the main story's goal")
            if any(p not in keys or p == mission.key for p in mission.prerequisites):
                raise MissionError("invalid mission chain reference")
        by_key={m.key:m for m in self.missions}
        def visit(key,visiting,resolved):
            if key in visiting:
                raise MissionError("cyclic story chains cannot be solved")
            if key in resolved:return
            visiting.add(key)
            for p in by_key[key].prerequisites:visit(p,visiting,resolved)
            visiting.remove(key);resolved.add(key)
        resolved=set()
        for m in self.missions:visit(m.key,set(),resolved)

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.mission_logic.v1",
                    world_digest=self.world_digest,
                    invariant_goal=self.invariant_goal,
                    missions=[m.payload() for m in self.missions])


@dataclass(frozen=True, slots=True)
class StageOutcome:
    mission: str
    stage: str
    time_used: int
    optional_completed: int
    reward: int
    flags: tuple[str,...]

    def payload(self):
        return dict(mission=self.mission,stage=self.stage,time_used=self.time_used,
                    optional_completed=self.optional_completed,
                    reward=self.reward,flags=list(self.flags))


@dataclass(frozen=True, slots=True)
class MissionSnapshot:
    book_digest: str
    stage_indexes: tuple[tuple[str,int],...]
    completed: tuple[str,...]
    facts: tuple[MissionFact,...]
    outcomes: tuple[StageOutcome,...]
    stage_starts: tuple[tuple[str,int],...]
    flags: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(book_digest=self.book_digest,
                    stage_indexes=[list(x) for x in self.stage_indexes],
                    completed=list(self.completed),
                    facts=[f.payload() for f in self.facts],
                    outcomes=[o.payload() for o in self.outcomes],
                    stage_starts=[list(x) for x in self.stage_starts],
                    flags=list(self.flags))


def mission_initial(book: MissionBook) -> MissionSnapshot:
    return MissionSnapshot(
        book.digest,tuple((m.key,0) for m in book.missions),
        (),(),(),tuple((m.key,0) for m in book.missions),(),
    )


def mission_step(book: MissionBook,state: MissionSnapshot,
                 fact: MissionFact) -> MissionSnapshot:
    if not isinstance(state,MissionSnapshot) or state.book_digest!=book.digest:
        raise MissionError("mission state is foreign or forged")
    if state.facts and fact.turn < state.facts[-1].turn:
        raise MissionError("time travel rewrites earlier mission evidence")
    indexes=dict(state.stage_indexes);starts=dict(state.stage_starts)
    completed=set(state.completed);outcomes=list(state.outcomes)
    flags=set(state.flags)
    all_facts=(*state.facts,fact)
    for mission in book.missions:
        if mission.key in completed or not set(mission.prerequisites)<=completed:
            continue
        idx=indexes[mission.key]
        if idx>=len(mission.stages):
            continue
        stage=mission.stages[idx]
        if fact.scene not in stage.allowed_scenes:
            continue
        # Scope stage facts by independent start clock and physical scene.
        # Multiple quest chains may observe a shared action if relevant.
        own=tuple(x for x in all_facts if x.turn >= starts[mission.key] and
                  x.scene in stage.allowed_scenes)
        if not stage.victory.evaluate(own):
            continue
        time_used=max(1,fact.turn-starts[mission.key])
        optional=sum(formula.evaluate(own) for formula in stage.optional)
        speed=max(0,stage.deadline-time_used)
        reward=stage.reward+speed+optional*25
        flags.add(stage.consequence)
        outcomes.append(StageOutcome(mission.key,stage.key,time_used,
                                     optional,reward,(stage.consequence,)))
        indexes[mission.key]+=1;starts[mission.key]=fact.turn+1
        if indexes[mission.key]==len(mission.stages):
            completed.add(mission.key)
    if len(all_facts)>8192:
        raise MissionError("event journal requires archiving before more play")
    return MissionSnapshot(
        book.digest,tuple((m.key,indexes[m.key]) for m in book.missions),
        tuple(sorted(completed)),all_facts,tuple(outcomes),
        tuple((m.key,starts[m.key]) for m in book.missions),tuple(sorted(flags)),
    )


def director_facts(world: DirectorWorld,replay: DirectorReplay) -> tuple[MissionFact,...]:
    """Only materialize events verified against the canonical game simulator."""
    director_verify(world,replay)
    state=director_initial(world)
    result=[]
    for index,action in enumerate(replay.actions):
        before=state
        state=director_step(world,state,action)
        if action.kind=="use":
            here=next(s for s in world.scenes if s.key==before.scene)
            item=next(a for a in here.affordances if a.key==action.key)
            kind,target=item.kind,item.target
        elif action.kind=="travel":
            kind,target="scene_enter",action.key
        else:
            kind,target="wait","time"
        result.append(MissionFact(
            kind,target,state.scene,state.turn,1,
            canonical_digest({"world":world.digest,"index":index,
                              "action":action.payload(),"state":state.digest}),
        ))
    return tuple(result)


def replay_mission_book(book: MissionBook,world: DirectorWorld,
                        replay: DirectorReplay,*,authorized: bool) -> MissionSnapshot:
    if not authorized:
        raise PermissionError("mission validation requires operator authority")
    if book.world_digest!=world.digest or book.invariant_goal!=world.bible.invariant_goal:
        raise MissionError("mission book does not belong to original authored world")
    state=mission_initial(book)
    for fact in director_facts(world,replay):
        state=mission_step(book,state,fact)
    return state


__all__ = [
    "MissionError","Predicate","Formula","atom","MissionFact","ObjectiveStage",
    "Mission","MissionBook","StageOutcome","MissionSnapshot",
    "mission_initial","mission_step","director_facts","replay_mission_book",
]
