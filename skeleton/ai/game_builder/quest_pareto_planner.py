"""Bounded alternative-quest search, not a predetermined action checklist.

Searches the real authored scene graph for multiple Pareto-relevant ways to
complete each quest chapter. Every candidate comes from director_step and
its final trace is independently replayed. The planner measures stage timing
from actual completion ticks, avoiding known legacy clock errors in runtime
display scores; it never silently changes that canonical engine's receipts.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Sequence

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorAction, DirectorWorld, DirectorError, DirectorState,
    director_initial, director_step, director_play, director_verify,
    available_director_actions,
)


class PlannerError(ValueError):
    """No proven strategy fits the explicit scene or search budgets."""


@dataclass(frozen=True,slots=True)
class PlannerBudget:
    max_expansions: int = 2200
    max_actions: int = 120
    beam: int = 12
    minimum_diversity: int = 2

    def __post_init__(self):
        for v,lower,upper in (
            (self.max_expansions,100,50000),(self.max_actions,4,1024),
            (self.beam,2,48),(self.minimum_diversity,1,8),
        ):
            if type(v) is not int or not lower <= v <= upper:
                raise PlannerError("bounded exhaustive/beam planning budget required")


@dataclass(frozen=True,slots=True)
class Route:
    actions: tuple[DirectorAction,...]
    state: DirectorState
    score: int
    elapsed: int
    optional_count: int
    creative_count: int
    method_sequence: tuple[str,...]
    certified_replay_digest: str
    legacy_score_mismatch: bool

    def payload(self):
        return dict(schema="skeleton.game_builder.quest_route.v1",
                    action_count=len(self.actions),turns=self.elapsed,
                    planner_score=self.score,optional_count=self.optional_count,
                    creative_count=self.creative_count,
                    method_sequence=list(self.method_sequence),
                    replay_digest=self.certified_replay_digest,
                    legacy_score_mismatch=self.legacy_score_mismatch)


@dataclass(frozen=True,slots=True)
class ParetoReport:
    world_digest: str
    quest_key: str
    expanded_states: int
    completed_candidates: int
    methods_explored: tuple[str,...]
    routes: tuple[Route,...]
    budget: PlannerBudget

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.quest_pareto_search.v1",
                    world_digest=self.world_digest,quest_key=self.quest_key,
                    expanded_states=self.expanded_states,
                    completed_candidates=self.completed_candidates,
                    methods_explored=list(self.methods_explored),
                    routes=[r.payload() for r in self.routes],
                    budget=dict(max_expansions=self.budget.max_expansions,
                                max_actions=self.budget.max_actions,
                                beam=self.budget.beam),
                    native_engine_convergence_claimed=False)


def _signature(state: DirectorState, key: str):
    progress=dict(state.stage_index)[key]
    records=tuple(r for r in state.records if r[0]==key)
    return (state.scene,progress,records,state.acquired)


def _candidate_actions(world: DirectorWorld,state: DirectorState,quest_key: str):
    quest=next(q for q in world.quests if q.key==quest_key)
    index=dict(state.stage_index)[quest_key]
    if index>=len(quest.stages):
        return ()
    stage=quest.stages[index]
    here=state.scene
    graph={s.key:s.links for s in world.scenes}
    # Optimal shortest-path bound on scene steps to at least one stage goal.
    distance={site:0 for site in stage.scene_ids}
    queue=deque(distance)
    while queue:
        node=queue.popleft()
        for neighbor in graph[node]:
            if neighbor not in distance:
                distance[neighbor]=distance[node]+1
                queue.append(neighbor)
    available=available_director_actions(world,state)
    options=[]
    for action in available:
        if action.kind=="travel":
            if distance.get(action.key,1000) >= distance.get(here,1000):
                continue
        elif action.kind=="use":
            affordance=next(a for s in world.scenes if s.key==here
                            for a in s.affordances if a.key==action.key)
            needed={(p.kind,p.target) for solution in stage.solutions
                    for p in solution.required}
            needed.update((p.kind,p.target) for p in stage.optional)
            if (affordance.kind,affordance.target) not in needed:
                continue
        else:
            continue  # waiting without timing requirements cannot improve this quest
        options.append(action)
    return tuple(sorted(options,key=lambda a: (
        0 if a.kind=="use" else 1,a.key,
    )))


def _stage_search(world: DirectorWorld, quest_key: str,
                  state: DirectorState, actions: tuple[DirectorAction,...],
                  budget: PlannerBudget) -> tuple[list[tuple[DirectorState,tuple[DirectorAction,...]]],int]:
    before=dict(state.stage_index)[quest_key]
    candidates=[]
    pending=deque([(state,actions)])
    # Nondominance: preserve variants with distinct event evidence while
    # discarding strictly slower identical scene/progress arrangements.
    best={_signature(state,quest_key):state.turn}
    expanded=0
    while pending and expanded<budget.max_expansions:
        here,path=pending.popleft()
        expanded+=1
        if len(path)>=budget.max_actions:
            continue
        for action in _candidate_actions(world,here,quest_key):
            try:
                after=director_step(world,here,action)
            except DirectorError:
                continue
            new_path=(*path,action)
            if dict(after.stage_index)[quest_key] > before:
                candidates.append((after,new_path))
                continue
            sign=_signature(after,quest_key)
            if best.get(sign,10**9)<=after.turn:
                continue
            best[sign]=after.turn
            pending.append((after,new_path))
    return candidates,expanded


def _regrade(world: DirectorWorld,route: tuple[DirectorAction,...],
             quest_key: str) -> Route:
    replay=director_play(world,route)
    director_verify(world,replay)
    quest=next(q for q in world.quests if q.key==quest_key)
    if quest_key not in replay.final.complete:
        raise PlannerError("route did not prove the whole original quest")
    state=director_initial(world)
    stage_started=0
    method=[]
    score=0
    optionals=0
    creative=0
    mismatch=False
    for action in route:
        old_progress=dict(state.stage_index)[quest_key]
        nxt=director_step(world,state,action)
        if dict(nxt.stage_index)[quest_key]>old_progress:
            stage=quest.stages[old_progress]
            result=next(x for x in nxt.results if x.quest==quest_key and
                        x.stage==stage.key)
            observed=max(1,nxt.turn-stage_started)
            speed=max(0,stage.time_target-observed)*3
            corrected=100+result.creativity_bonus+result.optional_bonus+speed
            mismatch |= result.turns!=observed or corrected!=result.score
            score+=corrected
            optionals+=result.optional_bonus//15
            creative+=result.creativity_bonus
            method.append(result.approach)
            stage_started=nxt.turn
        state=nxt
    return Route(route,replay.final,score,replay.final.turn,
                 optionals,creative,tuple(method),replay.digest,mismatch)


def _rank(route: Route, objective: str):
    if objective=="speed":
        return (route.elapsed, -route.score, -route.creative_count)
    if objective=="creative":
        return (-route.creative_count, -route.optional_count,
                -route.score, route.elapsed)
    if objective=="thorough":
        return (-route.optional_count, -route.score,
                -route.creative_count,route.elapsed)
    if objective=="balanced":
        return (route.elapsed-route.creative_count//20-
                route.optional_count*4,-route.score,route.elapsed)
    raise PlannerError("unknown multi-objective quest preference")


def find_quest_routes(
    world: DirectorWorld,quest_key: str,*,objective: str="balanced",
    budget: PlannerBudget=PlannerBudget(),authorized: bool,
) -> ParetoReport:
    if not authorized:
        raise PermissionError("game route exploration requires operator authority")
    if not isinstance(world,DirectorWorld) or not isinstance(budget,PlannerBudget):
        raise PlannerError("typed original game and planner budget required")
    if objective not in {"balanced","speed","creative","thorough"}:
        raise PlannerError("invalid alternate quest optimization objective")
    quest=next((q for q in world.quests if q.key==quest_key),None)
    if quest is None or quest.requires_quests:
        raise PlannerError("standalone quest search requires all prerequisites resolved")
    frontier=[(director_initial(world),())]
    expanded=0
    for index in range(len(quest.stages)):
        next_frontier=[]
        for state,path in frontier:
            routes,used=_stage_search(world,quest_key,state,path,budget)
            expanded+=used
            next_frontier.extend(routes)
        if not next_frontier:
            raise PlannerError("no real alternative path reaches the next authored stage")
        # Preserve distinct successful strategies as well as travel economy.
        unique={}
        for state,path in next_frontier:
            methods=tuple(r.approach for r in state.results if r.quest==quest_key)
            choices=tuple(r.optional_bonus for r in state.results if r.quest==quest_key)
            key=(state.scene,methods,choices)
            old=unique.get(key)
            if old is None or state.turn<old[0].turn:
                unique[key]=(state,path)
        next_frontier=list(unique.values())
        # Deliberate diversity: each solution signature competes on score and
        # speed but cannot be erased by an identical template variant.
        next_frontier.sort(key=lambda p: (
            -sum(r.creativity_bonus + r.optional_bonus for r in p[0].results
                 if r.quest==quest_key),
            p[0].turn,len(p[1]),
        ))
        frontier=next_frontier[:budget.beam]
    routes=[_regrade(world,actions,quest_key) for state,actions in frontier]
    routes.sort(key=lambda route:_rank(route,objective))
    if len({r.method_sequence for r in routes}) < budget.minimum_diversity:
        raise PlannerError("quest alternatives collapse to one genuine method")
    return ParetoReport(
        world.digest,quest_key,expanded,len(frontier),
        tuple(sorted({m for r in routes for m in r.method_sequence})),
        tuple(routes),budget,
    )


__all__=[
    "PlannerError","PlannerBudget","Route","ParetoReport","find_quest_routes",
]
