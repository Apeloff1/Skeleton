"""Executable post-witness quest progression from real canonical actions.

The witness creates an independent, source-linked opportunity at the precise
action index when an NPC actually observed an incident. Victory conditions
count only *later* independently verified game actions; historical facts
cannot retroactively complete quests. These are playable overlay prototypes,
not an unreviewed rewrite of the canonical story world.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import canonical_digest
from .quest_scene_engine import DirectorWorld,DirectorReplay,director_verify
from .modular_mission_runtime import director_facts
from .npc_witness_quest_engine import (
    WitnessCampaign,EmergentQuest,WitnessError,
    audit_witness_campaign,validate_witness,
)


class WitnessProgressError(ValueError):
    """Dynamic quest receipts disagree with the real witnessed game."""


@dataclass(frozen=True,slots=True)
class EmergentStageResult:
    quest: str
    stage: str
    source_witness: str
    activated_at_action: int
    completed_at_action: int
    source_action_digest: str
    turn_cost: int
    optional_awards: int
    reward: int
    consequence: str

    def payload(self):
        return dict(quest=self.quest,stage=self.stage,
                    source_witness=self.source_witness,
                    activated_at_action=self.activated_at_action,
                    completed_at_action=self.completed_at_action,
                    source_action_digest=self.source_action_digest,
                    turn_cost=self.turn_cost,
                    optional_awards=self.optional_awards,
                    reward=self.reward,consequence=self.consequence)


@dataclass(frozen=True,slots=True)
class EmergentQuestState:
    key: str
    witness_digest: str
    stage_index: int
    stage_count: int
    activated_after_action: int
    observed_turn: int
    completion_turn: int | None
    results: tuple[EmergentStageResult,...]
    status: str

    def payload(self):
        return dict(key=self.key,witness_digest=self.witness_digest,
                    stage_index=self.stage_index,
                    stage_count=self.stage_count,
                    activated_after_action=self.activated_after_action,
                    observed_turn=self.observed_turn,
                    completion_turn=self.completion_turn,
                    results=[r.payload() for r in self.results],
                    status=self.status)


@dataclass(frozen=True,slots=True)
class WitnessQuestReplay:
    world_digest: str
    canonical_replay_digest: str
    campaign_digest: str
    quests: tuple[EmergentQuestState,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.witness_quest_replay.v1",
                    world_digest=self.world_digest,
                    canonical_replay_digest=self.canonical_replay_digest,
                    campaign_digest=self.campaign_digest,
                    active=sum(s.status=="active" for s in self.quests),
                    solved=sum(s.status=="solved" for s in self.quests),
                    results=[s.payload() for s in self.quests],
                    retrospective_victory_allowed=False,
                    review_required_before_canonical_inclusion=True,
                    real_native_integration_verified=False)


def replay_witness_quests(
    world: DirectorWorld,replay: DirectorReplay,campaign: WitnessCampaign,*,
    population: int,active_budget: int=40,ambient_budget: int=40,
    maximum_witnesses: int=128,authorized: bool,
) -> WitnessQuestReplay:
    if not authorized:
        raise PermissionError("real witnessed quest replay needs original operator authority")
    director_verify(world,replay)
    audit_witness_campaign(world,replay,campaign,
                           population=population,active_budget=active_budget,
                           ambient_budget=ambient_budget,
                           maximum_witnesses=maximum_witnesses,authorized=True)
    facts=director_facts(world,replay)
    results=[]
    for proposed in campaign.opportunities:
        source=proposed.witness
        validate_witness(world,replay,source,authorized=True)
        if proposed.story_goal!=world.bible.invariant_goal:
            raise WitnessProgressError("witness cannot replace original main story goal")
        if len({stage.key for stage in proposed.chapters})!=len(proposed.chapters):
            raise WitnessProgressError("indistinguishable emergent chapters")
        index=0
        next_action=source.action_index+1
        start_turn=source.observed_turn
        receipts=[]
        if next_action>=len(facts):
            results.append(EmergentQuestState(
                proposed.key,source.digest,0,len(proposed.chapters),
                next_action,start_turn,None,(),"active",
            ))
            continue
        for step,fact in enumerate(facts[next_action:],start=next_action):
            if index==len(proposed.chapters):
                break
            current=proposed.chapters[index]
            if fact.scene not in current.allowed_scenes:
                continue
            # Each stage sees only its own actual action facts, after its
            # activation. Shared narratives may choose other approaches.
            eligible=tuple(f for f in facts[next_action:step+1]
                           if f.scene in current.allowed_scenes)
            if not current.victory.evaluate(eligible):
                continue
            time=max(1,fact.turn-start_turn)
            optional=sum(option.evaluate(eligible) for option in current.optional)
            awarded=current.reward+max(0,current.deadline-time)+optional*25
            receipts.append(EmergentStageResult(
                proposed.key,current.key,source.digest,next_action,step,
                fact.source_digest,time,optional,awarded,current.consequence,
            ))
            index+=1
            next_action=step+1
            start_turn=fact.turn+1
        status="solved" if index==len(proposed.chapters) else "active"
        results.append(EmergentQuestState(
            proposed.key,source.digest,index,len(proposed.chapters),
            source.action_index+1,source.observed_turn,
            facts[receipts[-1].completed_at_action].turn if status=="solved" else None,
            tuple(receipts),status,
        ))
    return WitnessQuestReplay(world.digest,replay.digest,
                              campaign.digest,tuple(results))


__all__=[
    "WitnessProgressError","EmergentStageResult","EmergentQuestState",
    "WitnessQuestReplay","replay_witness_quests",
]
