"""Unified Director ⇄ Scene ⇄ Quest ⇄ NPC society simulation.

A real integration layer: the same legal authored player action updates the
canonical director runtime, bounded NPC needs and local observed memories,
and compositional mission criteria. Session replay recalculates everything;
mirror cadence and external provider access are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorAction, DirectorError, DirectorWorld, DirectorState,
    director_initial, director_step, director_play, director_verify,
    available_director_actions,
)
from .npc_society_runtime import (
    Society, make_society, society_tick, apply_world_event,
)
from .modular_mission_runtime import (
    MissionBook, MissionSnapshot, MissionFact, mission_initial, mission_step,
    replay_mission_book,
)
from .modular_mission_compiler import compile_modular_missions
from .director_capability_graph import DeviceTier, ExecutionPlan, TIERS, resolve_capabilities


class IntegrationError(ValueError):
    """Shared world, policy, action or evidence divergence."""


@dataclass(frozen=True, slots=True)
class DirectorSession:
    world_digest: str
    capability_digest: str
    story: DirectorState
    society: Society
    missions: MissionSnapshot
    actions: tuple[DirectorAction,...]
    evidence: tuple[str,...]
    player_scene: str

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.director_session.v1",
                    world_digest=self.world_digest,
                    capability_digest=self.capability_digest,
                    story=self.story.payload(),
                    society=self.society.payload(),
                    missions=self.missions.payload(),
                    actions=[a.payload() for a in self.actions],
                    evidence=list(self.evidence),
                    player_scene=self.player_scene)


@dataclass(frozen=True, slots=True)
class DirectorOrchestration:
    world_digest: str
    source_proof: str
    session: DirectorSession
    checkpoints: tuple[str,...]
    device: str
    performance: dict[str,int]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.director_orchestration.v1",
                    world_digest=self.world_digest,
                    source_proof=self.source_proof,
                    terminal_session_digest=self.session.digest,
                    checkpoints=list(self.checkpoints),
                    device=self.device,
                    performance=dict(sorted(self.performance.items())),
                    no_external_provider_execution=True,
                    independent_native_parity_verified=False)


def orchestrator_plan(tier: str="desktop") -> ExecutionPlan:
    if tier not in TIERS:
        raise IntegrationError("unrecognized consumer device tier")
    return resolve_capabilities(
        ("director.synergy","mission.solver","mission.endings",
         "scene.cinematic","npc.memory"),tier=TIERS[tier],
    )


def open_director_session(world: DirectorWorld, *, population: int,
                          tier: str="desktop", authorized: bool) -> DirectorSession:
    if not authorized:
        raise PermissionError("shared game director simulation requires authorization")
    if not isinstance(world,DirectorWorld):
        raise IntegrationError("typed original director world required")
    plan=orchestrator_plan(tier)
    if population < 3 or population > 512:
        raise IntegrationError("original population 3..512 required")
    book=compile_modular_missions(world,authorized=True)
    if len(book.missions)>plan.target.mission_budget:
        raise IntegrationError("world mission count exceeds selected consumer device tier")
    society=make_society(world,population,authorized=True)
    return DirectorSession(
        world.digest,plan.digest,director_initial(world),society,
        mission_initial(book),(),(),world.starting_scene,
    )


def director_session_step(world: DirectorWorld,session: DirectorSession,
                          action: DirectorAction,*,tier: str,
                          authorized: bool) -> DirectorSession:
    if not authorized:
        raise PermissionError("operator authority required for mixed engine execution")
    plan=orchestrator_plan(tier)
    book=compile_modular_missions(world,authorized=True)
    if (not isinstance(session,DirectorSession) or
        session.world_digest!=world.digest or
        session.capability_digest!=plan.digest or
        session.story.world_digest!=world.digest or
        session.society.world_digest!=world.digest or
        session.missions.book_digest!=book.digest or
        session.player_scene!=session.story.scene):
        raise IntegrationError("scene, NPC, mission and director state must share original provenance")
    if len(session.actions)>=512 or not isinstance(action,DirectorAction):
        raise IntegrationError("unbounded or untyped game action")
    if action not in available_director_actions(world,session.story):
        raise IntegrationError("invalid gameplay action for the current original scene")
    prior=session.story
    after=director_step(world,prior,action)
    if after.turn <= prior.turn or after.turn-prior.turn>60:
        raise IntegrationError("invalid multi-engine time advance")
    if action.kind=="use":
        scene=next(s for s in world.scenes if s.key==prior.scene)
        affordance=next(a for a in scene.affordances if a.key==action.key)
        kind,target=affordance.kind,affordance.target
    elif action.kind=="travel":
        kind,target="scene_enter",action.key
    else:
        kind,target="wait","time"
    receipt=canonical_digest({
        "world":world.digest,"index":len(session.actions),
        "action":action.payload(),"state":after.digest,
    })
    fact=MissionFact(kind,target,after.scene,after.turn,1,receipt)
    missions=mission_step(book,session.missions,fact)
    citizens=session.society
    if action.kind=="use":
        sentiment=(-55 if kind in {"fight","sneak"} else
                   55 if kind in {"heal","protect","negotiate",
                                  "escort_follow","escort_leash"} else
                   25 if kind in {"talk","trade","repair","build"} else 10)
        citizens=apply_world_event(
            citizens,world,event="observed_"+kind,subject="hero",
            scene=prior.scene,valence=sentiment,authorized=True,
        )
    threat=prior.scene if kind in {"fight","survive"} else None
    for _ in range(after.turn-prior.turn):
        citizens=society_tick(
            citizens,world,player_scene=after.scene,
            active_budget=min(plan.target.actor_budget,len(citizens.minds)),
            ambient_budget=min(plan.target.ambient_budget,len(citizens.minds)),
            threat_scene=threat,authorized=True,
        )
    # Exactly completed chapters broadcast real news only to witnesses
    # colocated in the authored scene, never through omniscient world edits.
    new=missions.outcomes[len(session.missions.outcomes):]
    for outcome in new:
        citizens=apply_world_event(
            citizens,world,event="chapter_resolution",subject="hero",
            scene=after.scene,valence=35,authorized=True,
        )
    return DirectorSession(
        world.digest,plan.digest,after,citizens,missions,
        (*session.actions,action),(*session.evidence,receipt),after.scene,
    )


def simulate_director(world: DirectorWorld,actions: Sequence[DirectorAction],*,
                      population: int=96,tier: str="desktop",
                      authorized: bool) -> DirectorOrchestration:
    if not authorized:
        raise PermissionError("original game director evaluation requires authorization")
    if not isinstance(actions,(tuple,list)) or len(actions)>512:
        raise IntegrationError("bounded complete original action trace required")
    original=director_play(world,actions)
    director_verify(world,original)
    session=open_director_session(world,population=population,tier=tier,authorized=True)
    checks=[]
    for action in actions:
        session=director_session_step(world,session,action,tier=tier,authorized=True)
        checks.append(session.digest)
    if session.story!=original.final:
        raise IntegrationError("multi-engine game director deviated from canonical story")
    # Separate mission-only replay excludes NPC-generated perception events.
    book=compile_modular_missions(world,authorized=True)
    independent=replay_mission_book(book,world,original,authorized=True)
    if independent != session.missions:
        raise IntegrationError("independent modular mission replay diverged")
    if session.society.turn!=session.story.turn:
        raise IntegrationError("NPC schedules are out of sync with gameplay turns")
    target=TIERS[tier]
    states=session.society.minds
    report=dict(population=len(states),npc_active=sum(m.lod=="active" for m in states),
                npc_ambient=sum(m.lod=="ambient" for m in states),
                npc_persistent_dormant=sum(m.lod=="dormant" for m in states),
                authored_scenes=len(world.scenes),
                authored_quests=len(world.quests),
                quest_stages_completed=len(session.missions.outcomes),
                canonical_quest_stages=len(session.story.results),
                observed_memory_count=sum(len(m.memories) for m in states),
                relationship_count=sum(len(m.bonds) for m in states),
                mission_scores=sum(r.reward for r in session.missions.outcomes),
                real_game_actions=len(session.actions),
                world_turns=session.story.turn,
                tier_cpu_budget=target.work_units)
    return DirectorOrchestration(world.digest,original.digest,session,
                                 tuple(checks),tier,report)


__all__ = [
    "IntegrationError","DirectorSession","DirectorOrchestration",
    "orchestrator_plan","open_director_session","director_session_step",
    "simulate_director",
]
