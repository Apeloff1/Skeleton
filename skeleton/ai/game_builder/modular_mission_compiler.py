"""Compile full authored director quests into modular victory and story graphs.

Preserves every authored action parameter and alternative. No generic
'quest complete' placeholder is accepted as victory; conditions depend on
real game actions in canonical replayed scenes.
"""
from __future__ import annotations

from .quest_scene_engine import DirectorError, DirectorWorld, Parameter
from .modular_mission_runtime import (
    Formula, Mission, MissionBook, ObjectiveStage, atom,
)


def _parameter(p: Parameter) -> Formula:
    if not isinstance(p, Parameter):
        raise DirectorError("typed author quest parameter expected")
    return atom(p.kind,p.target,p.count)


def compile_modular_missions(world: DirectorWorld, *, authorized: bool) -> MissionBook:
    if not authorized:
        raise PermissionError("modular mission authoring needs operator authority")
    if not isinstance(world, DirectorWorld):
        raise DirectorError("typed authored director world required")
    missions=[]
    for quest in world.quests:
        steps=[]
        for stage in quest.stages:
            candidates=[]
            for solution in stage.solutions:
                conditions=tuple(_parameter(p) for p in solution.required)
                candidates.append(conditions[0] if len(conditions)==1 else
                                  Formula("all",children=conditions))
            victory=(candidates[0] if len(candidates)==1 else
                     Formula("any",children=tuple(candidates)))
            steps.append(ObjectiveStage(
                key=stage.key,premise=stage.lore,victory=victory,
                optional=tuple(_parameter(p) for p in stage.optional),
                allowed_scenes=stage.scene_ids,
                deadline=stage.time_target,reward=100,
                consequence="complete_"+quest.key+"_"+stage.key,
                cinematic=stage.cutscene_on_complete,
            ))
        lane=(
            "main" if quest.scope=="main" else
            "repeatable" if quest.scope=="repeatable" else
            "rival" if quest.scope=="rival" else
            "regional" if quest.scope=="region" else
            "story_arc" if quest.scope=="arc" else "side"
        )
        placement=(
            "choice" if quest.placement=="player_choice" else quest.placement
        )
        missions.append(Mission(
            key=quest.key,lane=lane,
            main_goal=world.bible.invariant_goal,
            prerequisites=quest.requires_quests,
            stages=tuple(steps),
            placement=placement,
            repeat_limit=quest.repeat_limit,
        ))
    return MissionBook(world.digest,world.bible.invariant_goal,tuple(missions))


__all__ = ["compile_modular_missions"]
