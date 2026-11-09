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
from .npc_society_runtime import Society
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
    reviewed_source_digest: str | None = None

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.witness_quest_replay.v1",
                    world_digest=self.world_digest,
                    canonical_replay_digest=self.canonical_replay_digest,
                    campaign_digest=self.campaign_digest,
                    reviewed_source_digest=self.reviewed_source_digest,
                    active=sum(s.status=="active" for s in self.quests),
                    solved=sum(s.status=="solved" for s in self.quests),
                    results=[s.payload() for s in self.quests],
                    retrospective_victory_allowed=False,
                    review_required_before_canonical_inclusion=True,
                    real_native_integration_verified=False)


def _validate_authored_chapters(world: DirectorWorld,chapters: tuple) -> None:
    from .modular_mission_runtime import ObjectiveStage
    if (not isinstance(chapters,tuple) or not 2<=len(chapters)<=16
            or any(not isinstance(s,ObjectiveStage) for s in chapters)):
        raise WitnessProgressError("human-approved NPC quests need 2..16 typed chapters")
    scenes={s.key:s for s in world.scenes}
    if len({s.key for s in chapters})!=len(chapters):
        raise WitnessProgressError("designer quest stages require unique identities")
    def validate_formula(formula,allowed):
        if formula.op=="atom":
            p=formula.atoms[0]
            if not any(
                (s in scenes and any(a.kind==p.kind and a.target==p.target
                                    for a in scenes[s].affordances)
                 and (p.location is None or p.location==s))
                for s in allowed
            ):
                raise WitnessProgressError("author's objective has no playable original-world action")
        else:
            for child in formula.children:
                validate_formula(child,allowed)
    for stage in chapters:
        if any(s not in scenes for s in stage.allowed_scenes):
            raise WitnessProgressError("witness chapter references an unauthored scene")
        validate_formula(stage.victory,stage.allowed_scenes)
        for condition in stage.optional:
            validate_formula(condition,stage.allowed_scenes)


def replay_witness_quests(
    world: DirectorWorld,replay: DirectorReplay,campaign: WitnessCampaign,*,
    population: int,active_budget: int=40,ambient_budget: int=40,
    maximum_witnesses: int=128,authorized: bool,
    authored_chapters: dict[str,tuple] | None=None,
    human_reviewed: bool=False,
    starting_society: Society | None=None,
) -> WitnessQuestReplay:
    if not authorized:
        raise PermissionError("real witnessed quest replay needs original operator authority")
    director_verify(world,replay)
    audit_witness_campaign(world,replay,campaign,
                           population=population,active_budget=active_budget,
                           ambient_budget=ambient_budget,
                           maximum_witnesses=maximum_witnesses,
                           starting_society=starting_society,authorized=True)
    if authored_chapters is not None:
        if human_reviewed is not True or type(authored_chapters) is not dict:
            raise WitnessProgressError("designer witness changes require human review")
        allowed={q.key for q in campaign.opportunities}
        if not set(authored_chapters)<=allowed:
            raise WitnessProgressError("custom witness quests require observed real NPCs")
        for chapters in authored_chapters.values():
            _validate_authored_chapters(world,chapters)
    source_digest=(
        canonical_digest({k:[s.payload() for s in v]
                          for k,v in sorted(authored_chapters.items())})
        if authored_chapters is not None else None
    )
    facts=director_facts(world,replay)
    results=[]
    for proposed in campaign.opportunities:
        source=proposed.witness
        validate_witness(world,replay,source,authorized=True)
        if proposed.story_goal!=world.bible.invariant_goal:
            raise WitnessProgressError("witness cannot replace original main story goal")
        chapters=(authored_chapters[proposed.key]
                  if authored_chapters is not None and proposed.key in authored_chapters
                  else proposed.chapters)
        if len({stage.key for stage in chapters})!=len(chapters):
            raise WitnessProgressError("indistinguishable emergent chapters")
        index=0
        next_action=source.action_index+1
        start_turn=source.observed_turn
        receipts=[]
        if next_action>=len(facts):
            results.append(EmergentQuestState(
                proposed.key,source.digest,0,len(chapters),
                next_action,start_turn,None,(),"active",
            ))
            continue
        for step,fact in enumerate(facts[next_action:],start=next_action):
            if index==len(chapters):
                break
            current=chapters[index]
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
        status="solved" if index==len(chapters) else "active"
        results.append(EmergentQuestState(
            proposed.key,source.digest,index,len(chapters),
            source.action_index+1,source.observed_turn,
            facts[receipts[-1].completed_at_action].turn if status=="solved" else None,
            tuple(receipts),status,
        ))
    return WitnessQuestReplay(world.digest,replay.digest,
                              campaign.digest,tuple(results),source_digest)


__all__=[
    "WitnessProgressError","EmergentStageResult","EmergentQuestState",
    "WitnessQuestReplay","replay_witness_quests",
]
