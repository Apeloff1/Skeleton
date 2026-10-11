"""Cross-system adversarial mirror for authored director, mission, NPC and scene.

Each probe executes a real rejected operation or reconstructs a verified
invariant; none is an imagined adversarial 'agent call'. This deepens a
single review pass and does not alter scheduling or calling frequency.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import random

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorAction, DirectorError, DirectorWorld, director_play, director_verify,
)
from .quest_director_solver import solve_quest
from .quest_director_endings import evaluate_story_ending
from .npc_society_runtime import (
    Society, SocietyError, society_tick, apply_world_event,
)
from .npc_social_economy import (
    Economy, EconomyError, transact,
)
from .modular_mission_runtime import (
    Formula, MissionError, atom,
)
from .modular_mission_compiler import compile_modular_missions
from .modular_scene_compositor import (
    CompositionError, compose_scene,
)
from .director_capability_graph import (
    CapabilityError, resolve_capabilities, TIERS,
)


class EvolutionMirrorError(ValueError):
    """Integration evidence is incomplete or adversarial review failed."""


@dataclass(frozen=True,slots=True)
class EvolutionProbe:
    index: int
    family: str
    accepted: bool
    receipt: str

    def payload(self):
        return dict(index=self.index,family=self.family,
                    accepted=self.accepted,receipt=self.receipt)


@dataclass(frozen=True,slots=True)
class EvolutionMirror:
    world_digest: str
    director_proof_digest: str
    npc_society_digest: str
    economy_digest: str
    results: tuple[EvolutionProbe,...]

    @property
    def passed(self):
        return len(self.results)>=64 and all(r.accepted for r in self.results)

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.evolution_mirror_room.v1",
                    world_digest=self.world_digest,
                    director_proof_digest=self.director_proof_digest,
                    npc_society_digest=self.npc_society_digest,
                    economy_digest=self.economy_digest,
                    attempts=len(self.results),
                    pass_count=sum(x.accepted for x in self.results),
                    families=sorted({x.family for x in self.results}),
                    results=[x.payload() for x in self.results],
                    scheduling_frequency_changed=False,
                    human_playtested=False,
                    model_weights_benchmarked=False,
                    legal_cleared=False)


def _reject(operation):
    try:
        operation()
    except (PermissionError,DirectorError,SocietyError,
            EconomyError,CompositionError,CapabilityError,MissionError):
        return True
    return False


def review_evolution(
    world: DirectorWorld,
    society: Society,
    economy: Economy,
    *, authorized: bool, attempts: int = 128,
) -> EvolutionMirror:
    if not authorized:
        raise PermissionError("cross-system mirror needs operator authorization")
    if (not isinstance(world,DirectorWorld) or not isinstance(society,Society)
        or not isinstance(economy,Economy)
        or society.world_digest!=world.digest
        or economy.society_digest!=world.digest):
        raise EvolutionMirrorError("all subsystems must use one verified source world")
    if type(attempts) is not int or not 64<=attempts<=512:
        raise EvolutionMirrorError("adversarial workload must remain bounded")
    main=next(q for q in world.quests if q.scope=="main")
    proof=solve_quest(world,main.key,strategy="creative",authorized=True).replay
    director_verify(world,proof)
    book=compile_modular_missions(world,authorized=True)
    rng=random.Random(int(world.digest[:14],16))
    cases=[]
    for i in range(attempts):
        family=i%12
        point=rng.randrange(len(proof.actions))
        if family==0:
            label="canonical_replay_reconstruction"
            recomputed=director_play(world,proof.actions)
            passed=recomputed==proof
        elif family==1:
            label="forged_replay_result"
            tampered=replace(proof,world_digest="0"*64)
            passed=_reject(lambda:director_verify(world,tampered))
        elif family==2:
            label="illegal_source_teleport"
            state=director_play(world,proof.actions[:point]).final
            passed=_reject(lambda:__import__(
                "skeleton.ai.game_builder.quest_scene_engine",
                fromlist=["director_step"]).director_step(
                    world,state,DirectorAction("travel","nonexistent",state.scene)))
        elif family==3:
            label="unearned_faction_ending"
            passed=_reject(lambda:evaluate_story_ending(
                world,proof,desired="independence",authorized=True))
        elif family==4:
            label="foreign_npc_source"
            foreign=replace(society,world_digest="foreign")
            passed=_reject(lambda:society_tick(
                foreign,world,player_scene=world.starting_scene,
                active_budget=8,ambient_budget=8,authorized=True))
        elif family==5:
            label="imaginary_npc_witness"
            passed=_reject(lambda:apply_world_event(
                society,world,event="unknown_witness",subject="hero",
                scene=world.starting_scene,valence=50,
                witnesses=("invented_citizen",),authorized=True))
        elif family==6:
            label="self_trade_resource_inflation"
            first=society.profiles[0].key
            passed=_reject(lambda:transact(
                economy,society,seller=first,buyer=first,
                resource="grain",quantity=1,authorized=True))
        elif family==7:
            label="unauthorized_market_mutation"
            first=society.profiles[0].key
            second=society.profiles[1].key
            passed=_reject(lambda:transact(
                economy,society,seller=first,buyer=second,
                resource="grain",quantity=1,authorized=False))
        elif family==8:
            label="unavailable_proprietary_tool"
            passed=_reject(lambda:resolve_capabilities(
                ("npc.language_model",),tier=TIERS["high_end"]))
        elif family==9:
            label="foreign_cinematic_scene"
            passed=_reject(lambda:compose_scene(
                world,society,"unwritten_scene",authorized=True))
        elif family==10:
            label="invalid_objective_threshold"
            passed=_reject(lambda:Formula(
                "at_least",children=(atom("inspect","clue_a"),
                                     atom("inspect","clue_b")),threshold=3))
        else:
            label="story_goal_preservation"
            passed=(all(m.main_goal==book.invariant_goal for m in book.missions)
                    and book.invariant_goal==world.bible.invariant_goal)
        cases.append(EvolutionProbe(
            i,label,passed,
            canonical_digest(dict(index=i,label=label,
                                  source=world.digest,accepted=passed,point=point)),
        ))
    report=EvolutionMirror(
        world.digest,proof.digest,society.digest,economy.digest,tuple(cases),
    )
    if not report.passed:
        raise EvolutionMirrorError("actual adversarial subsystem probe failed")
    return report


__all__=[
    "EvolutionMirrorError","EvolutionProbe","EvolutionMirror","review_evolution",
]
