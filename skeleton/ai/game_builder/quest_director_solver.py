"""Actual playable quest solvers, alternative-route witnesses and evaluation.

Selects legal actions and navigates authored scene entrances to satisfy a
quest via its declared method. Neither quest completion nor a narrative
claim can be obtained merely by naming an objective or submitting a flag.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorAction, DirectorError, DirectorReplay, DirectorWorld,
    DirectorState, director_initial, available_director_actions,
    director_play, director_step, director_verify,
)


@dataclass(frozen=True, slots=True)
class QuestWitness:
    quest_key: str
    strategy: str
    steps: int
    score: int
    completed: bool
    replay: DirectorReplay
    expected_results: tuple[str, ...]
    method_digest: str

    def payload(self):
        return {
            "schema": "skeleton.game_builder.quest_method_witness.v1",
            "quest_key": self.quest_key, "strategy": self.strategy,
            "steps": self.steps, "score": self.score,
            "completed": self.completed, "replay_digest": self.replay.digest,
            "expected_results": list(self.expected_results),
            "method_digest": self.method_digest,
        }


def _shortest(world: DirectorWorld, begin: str, end: str) -> tuple[str, ...]:
    if begin == end:
        return ()
    graph = {s.key: s.links for s in world.scenes}
    pending = deque([(begin, ())])
    visited = {begin}
    while pending:
        current, path = pending.popleft()
        for link in graph[current]:
            if link in visited:
                continue
            new_path = (*path, link)
            if link == end:
                return new_path
            visited.add(link)
            pending.append((link, new_path))
    raise DirectorError("original authored scene graph disconnects a quest stage")


def _perform(
    world: DirectorWorld, state: DirectorState,
    actions: list[DirectorAction],
    instruction: DirectorAction,
) -> DirectorState:
    if instruction not in available_director_actions(world, state):
        raise DirectorError("quest solver attempted unavailable authored interaction")
    next_state = director_step(world, state, instruction)
    if next_state.turn <= state.turn:
        raise DirectorError("quest actions must causally advance simulation time")
    actions.append(instruction)
    return next_state


def _go(
    world: DirectorWorld, state: DirectorState,
    actions: list[DirectorAction],
    target: str,
) -> DirectorState:
    for step in _shortest(world, state.scene, target):
        state = _perform(
            world, state, actions, DirectorAction("travel", step, state.scene),
        )
    return state


def _resolve(
    world: DirectorWorld, state: DirectorState,
    actions: list[DirectorAction], quest_key: str,
    method: str, optional: bool, visiting: set[str],
) -> DirectorState:
    by_key = {q.key: q for q in world.quests}
    if quest_key in state.complete:
        return state
    if quest_key in visiting:
        raise DirectorError("cyclic quest dependency during executable proof")
    if quest_key not in by_key:
        raise DirectorError("quest resolution references another original world")
    visiting.add(quest_key)
    quest = by_key[quest_key]
    for dependency in quest.requires_quests:
        state = _resolve(
            world, state, actions, dependency, method, optional, visiting,
        )
    visiting.remove(quest_key)
    for stage in quest.stages:
        if quest.key in state.complete:
            break
        progress = dict(state.stage_index).get(quest.key)
        if progress is None:
            raise DirectorError("stage progress lacks quest identity")
        if progress >= len(quest.stages):
            break
        live = quest.stages[progress]
        if live.key != stage.key:
            continue
        if method == "balanced":
            middle = sorted(live.solutions, key=lambda s: s.creativity)
            ranked = sorted(middle, key=lambda s: (
                abs(s.creativity - middle[len(middle)//2].creativity), s.key,
            ))
        elif method == "fast":
            ranked = sorted(live.solutions, key=lambda s: (
                len(s.required), sum(p.count for p in s.required),
                -s.creativity,
            ))
        elif method == "creative":
            ranked = sorted(live.solutions, key=lambda s: (
                -s.creativity, len(s.required),
            ))
        else:
            ranked = list(live.solutions)
        chosen = ranked[0]
        requirements = (*live.optional, *chosen.required) if optional else chosen.required
        for parameter in requirements:
            candidates = [
                (s.key, a) for s in world.scenes
                if s.key in live.scene_ids
                for a in s.affordances
                if (a.kind, a.target) == (parameter.kind, parameter.target)
            ]
            if not candidates:
                raise DirectorError("quest stage has no real valid playable method")
            site, affordance = min(candidates, key=lambda r: (
                len(_shortest(world, state.scene, r[0])), r[1].effort, r[0],
            ))
            state = _go(world, state, actions, site)
            for _ in range(parameter.count):
                instruction = DirectorAction("use", affordance.key, state.scene)
                state = _perform(world, state, actions, instruction)
        if dict(state.stage_index)[quest.key] != progress + 1:
            raise DirectorError("quest parameters did not complete the real stage")
    if quest.key not in state.complete:
        raise DirectorError("multi-stage quest did not complete after chosen strategy")
    return state


def solve_quest(
    world: DirectorWorld, quest_key: str, *,
    strategy: str = "creative", optional: bool = False,
    authorized: bool,
) -> QuestWitness:
    if not authorized:
        raise PermissionError("full quest proof requires operator authority")
    if not isinstance(world, DirectorWorld):
        raise DirectorError("typed original director world required")
    if strategy not in {"ordinary", "fast", "creative", "balanced"} or type(optional) is not bool:
        raise DirectorError("unsupported quest strategy or optional scoring policy")
    trace: list[DirectorAction] = []
    state = _resolve(
        world, director_initial(world), trace, quest_key,
        strategy, optional, set(),
    )
    replay = director_play(world, trace)
    director_verify(world, replay)
    if replay.final != state or quest_key not in replay.final.complete:
        raise DirectorError("solver and real quest simulation diverged")
    results = tuple(x.approach for x in state.results if x.quest == quest_key)
    quest = next(q for q in world.quests if q.key == quest_key)
    if len(results) != len(quest.stages):
        raise DirectorError("quest completion witness lacks every chapter")
    score = sum(x.score for x in state.results if x.quest == quest_key)
    return QuestWitness(
        quest_key, strategy, len(trace), score, True, replay, results,
        canonical_digest({
            "world": world.digest, "strategy": strategy,
            "optional": optional, "methods": results,
        }),
    )


def compare_solution_routes(
    world: DirectorWorld, quest_key: str, *,
    authorized: bool,
) -> dict[str, object]:
    if not authorized:
        raise PermissionError("method comparison requires operator authority")
    options = {
        method: solve_quest(
            world, quest_key, strategy=method, authorized=True,
        ) for method in ("ordinary", "creative", "fast")
    }
    bonus = solve_quest(
        world, quest_key, strategy="creative", optional=True, authorized=True,
    )
    if len({x.replay.digest for x in options.values()}) < 2:
        raise DirectorError("original quest lacks genuinely divergent playable routes")
    return {
        "schema": "skeleton.game_builder.quest_solution_comparison.v1",
        "world_digest": world.digest, "quest": quest_key,
        "solutions": {name: result.payload() for name, result in options.items()},
        "optional_bonuses": bonus.payload(),
        "different_paths_proven": True,
        "all_quests_end_in_real_python_states": True,
        "publisher_approved": False,
    }


__all__ = ["QuestWitness", "solve_quest", "compare_solution_routes"]
