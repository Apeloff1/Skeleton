"""Witnessed NPC events become causally sourced, optional quest opportunities.

Only actual canonical director actions are eligible. An NPC must be physically
present when the action happens, and have observed it firsthand. The resulting
quest starts *after* the observation, preventing retroactive victory, and
preserves the authored world's invariant goal. An original event can open
multiple narrative threads with different motives and response methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorWorld, DirectorReplay, DirectorState, DirectorError,
    director_verify, director_initial, director_step, DirectorAction,
)
from .modular_mission_runtime import (
    Mission, MissionBook, ObjectiveStage, Formula, atom,
    MissionFact, MissionSnapshot, mission_initial, mission_step,
)
from .modular_mission_compiler import compile_modular_missions
from .npc_society_runtime import (
    Society, Mind, Citizen, SocietyError, make_society, society_tick,
    apply_world_event,
)
from .director_capability_graph import TIERS


class WitnessError(ValueError):
    """NPC witness event or emergent mission failed causal provenance."""


# The motive selects the NPC's coherent reason to care; not a randomly
# generated claim about a character's knowledge.
REACTIONS = {
    "fight": ("danger", "protect", "pacify", "negotiate", -70),
    "sneak": ("suspicion", "inspect", "negotiate", "talk", -40),
    "heal": ("gratitude", "protect", "research", "talk", 80),
    "protect": ("gratitude", "repair", "build", "talk", 65),
    "gather": ("scarcity", "trade", "deliver", "craft", -10),
    "trade": ("commerce", "deliver", "gather", "negotiate", 35),
    "research": ("discovery", "inspect", "solve", "talk", 40),
    "discover": ("discovery", "research", "solve", "talk", 55),
    "repair": ("recovery", "build", "gather", "trade", 60),
    "build": ("recovery", "repair", "craft", "trade", 50),
    "escort_follow": ("companionship", "talk", "heal", "trade", 55),
    "escort_leash": ("companionship", "talk", "protect", "negotiate", 50),
    "negotiate": ("peace", "talk", "trade", "protect", 70),
    "craft": ("mastery", "trade", "research", "gather", 35),
    "infuse": ("mystery", "research", "inspect", "solve", 30),
    "attune": ("mystery", "research", "inspect", "solve", 45),
}


@dataclass(frozen=True, slots=True)
class WitnessReceipt:
    world_digest: str
    replay_digest: str
    action_index: int
    source_state_digest: str
    action_digest: str
    observer: str
    scene: str
    action_kind: str
    action_target: str
    observed_turn: int
    theme: str
    motive: str
    emotion: int
    source_memory_digest: str

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.npc_witness.v1",
                    world_digest=self.world_digest,
                    replay_digest=self.replay_digest,
                    action_index=self.action_index,
                    source_state_digest=self.source_state_digest,
                    action_digest=self.action_digest,
                    observer=self.observer, scene=self.scene,
                    action_kind=self.action_kind, action_target=self.action_target,
                    observed_turn=self.observed_turn, theme=self.theme,
                    motive=self.motive, emotion=self.emotion,
                    source_memory_digest=self.source_memory_digest,
                    hearsay=False, automatically_approved_lore=False)


@dataclass(frozen=True, slots=True)
class EmergentQuest:
    key: str
    witness: WitnessReceipt
    story_goal: str
    title: str
    premise: str
    chapters: tuple[ObjectiveStage, ...]
    evidence_requirements: tuple[str, ...]
    status: str

    def payload(self):
        return dict(schema="skeleton.game_builder.npc_emergent_quest.v1",
                    key=self.key,witness_digest=self.witness.digest,
                    main_goal=self.story_goal,title=self.title,
                    premise=self.premise,
                    chapters=[stage.payload() for stage in self.chapters],
                    evidence_requirements=list(self.evidence_requirements),
                    status=self.status, review_approved=False,
                    playable_in_native_game=False)


@dataclass(frozen=True, slots=True)
class WitnessCampaign:
    world_digest: str
    original_replay_digest: str
    witnessed: tuple[WitnessReceipt, ...]
    opportunities: tuple[EmergentQuest, ...]
    source_society_digest: str
    resulting_society_digest: str
    unrepresented_actions: int
    storyboard_goal: str

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.npc_witness_campaign.v1",
                    world_digest=self.world_digest,
                    original_replay_digest=self.original_replay_digest,
                    witnessed=[w.payload() for w in self.witnessed],
                    opportunities=[q.payload() for q in self.opportunities],
                    source_society_digest=self.source_society_digest,
                    resulting_society_digest=self.resulting_society_digest,
                    unrepresented_actions=self.unrepresented_actions,
                    invariant_main_goal=self.storyboard_goal,
                    human_author_review_required=True,
                    automatic_npc_training=False)


def _affordance(world, scene, action):
    current=next(s for s in world.scenes if s.key==scene)
    if action.kind!="use":
        return None
    return next(a for a in current.affordances if a.key==action.key)


def _candidate_stages(world: DirectorWorld, receipt: WitnessReceipt):
    # Use real authored affordances instead of falsely inventing playable
    # 'NPC dialogue' commands. Proposed opportunities can be authored further.
    genre=REACTIONS[receipt.action_kind]
    scene=next(s for s in world.scenes if s.key==receipt.scene)
    mapping={}
    for s in world.scenes:
        for a in s.affordances:
            if a.kind in genre[1:4] and a.kind not in mapping:
                mapping[a.kind]=(s.key,a)
    if len(mapping)<2:
        return (), "requires_designer_actions"
    kinds=[key for key in genre[1:4] if key in mapping]
    candidates=[]
    for i in range(2):
        methods=[]
        for kind in kinds:
            location,a=mapping[kind]
            methods.append(atom(a.kind,a.target,location=location))
        stage=ObjectiveStage(
            key=f"witness_stage_{i:02d}",
            premise=(f"{receipt.observer} remembers the {receipt.theme} at "
                     f"{receipt.scene}. Respond to the crisis through real "
                     f"actions while protecting: {world.bible.invariant_goal}"),
            victory=Formula("any",children=tuple(methods)) if len(methods)>1
                    else methods[0],
            optional=(methods[-1],) if len(methods)>1 else (),
            allowed_scenes=tuple(sorted({mapping[k][0] for k in kinds})),
            deadline=24+12*i,reward=150+i*70,
            consequence=f"witness_{receipt.theme}_response_{i}",
        )
        candidates.append(stage)
    return tuple(candidates), "proposed_review_required"


def observe_story(
    world: DirectorWorld, replay: DirectorReplay, *,
    population: int=96, active_budget: int=40, ambient_budget: int=40,
    maximum_witnesses: int=128, authorized: bool,
    starting_society: Society | None=None,
) -> WitnessCampaign:
    if not authorized:
        raise PermissionError("NPC witness-to-quest engine requires operator authority")
    director_verify(world,replay)
    if any(type(v) is not int for v in (population,active_budget,ambient_budget,maximum_witnesses)):
        raise WitnessError("integer bounded human-configured witness budgets required")
    if not 3<=population<=512 or not 0<=active_budget<=512 or not 0<=ambient_budget<=512:
        raise WitnessError("NPC cohort exceeds consumer-grade limits")
    if not 1<=maximum_witnesses<=512:
        raise WitnessError("bounded real witness recording limit required")
    society=starting_society or make_society(world,population,authorized=True)
    if society.world_digest!=world.digest or society.turn!=0 or len(society.minds)!=population:
        raise WitnessError("witness profile must be original and at initial clock")
    initial=society.digest
    previous=director_initial(world)
    witnessed=[]
    emergent=[]
    skipped=0
    observed_signatures=set()
    for index,action in enumerate(replay.actions):
        next_state=director_step(world,previous,action)
        a=_affordance(world,previous.scene,action)
        if a is None or a.kind not in REACTIONS:
            skipped+=1
        else:
            category,*_=REACTIONS[a.kind]
            valence=REACTIONS[a.kind][-1]
            # This is *before* the next time tick; the bystanders must have
            # genuinely been in the scene when the action occurred.
            present=[m for m in society.minds if m.scene==previous.scene]
            for mind in present:
                if len(witnessed)>=maximum_witnesses:
                    break
                signature=(mind.key,category,a.target)
                if signature in observed_signatures:
                    continue  # no infinite copies of identical testimony
                observed_signatures.add(signature)
                memory_event="observed_"+a.kind
                updated=apply_world_event(
                    society,world,event=memory_event,subject="hero",
                    scene=previous.scene,valence=valence,
                    witnesses=(mind.key,),authorized=True,
                )
                target=next(m for m in updated.minds if m.key==mind.key)
                record=next((m for m in target.memories
                             if m.event==memory_event and m.origin=="observed"),None)
                if record is None or record.certainty!=100:
                    raise WitnessError("event did not create a firsthand NPC memory")
                profile=next(p for p in society.profiles if p.key==mind.key)
                receipt=WitnessReceipt(
                    world.digest,replay.digest,index,previous.digest,
                    canonical_digest(action.payload()),mind.key,previous.scene,
                    a.kind,a.target,next_state.turn,category,
                    profile.motive,valence,canonical_digest(record.payload()),
                )
                witnessed.append(receipt)
                society=updated
                # Every original observation can open a distinct authored
                # story premise; requirements are *separately* reviewed.
                chapters,status=_candidate_stages(world,receipt)
                if chapters:
                    emergent.append(EmergentQuest(
                        f"emergent_{index:04d}_{mind.key}",receipt,
                        world.bible.invariant_goal,
                        f"{profile.name}: {category.replace('_',' ').title()}",
                        (f"{profile.name}, a {profile.profession} driven by "
                         f"{profile.motive}, directly witnessed {a.kind} "
                         f"affecting {a.target} at {previous.scene}. "
                         f"Their prior relationships may alter their response. "
                         f"The world's goal must remain: "
                         f"{world.bible.invariant_goal}"),
                        chapters,("independent_author_review",
                                  "originality_review","replay_after_activation"),
                        status,
                    ))
        for _ in range(next_state.turn-previous.turn):
            society=society_tick(
                society,world,player_scene=next_state.scene,
                active_budget=active_budget,ambient_budget=ambient_budget,
                authorized=True,
            )
        previous=next_state
    if previous!=replay.final:
        raise WitnessError("witness observation diverged from canonical game replay")
    return WitnessCampaign(
        world.digest,replay.digest,tuple(witnessed),tuple(emergent),
        initial,society.digest,skipped,world.bible.invariant_goal,
    )


def validate_witness(world: DirectorWorld,replay: DirectorReplay,
                     receipt: WitnessReceipt,*,authorized: bool) -> None:
    if not authorized:
        raise PermissionError("independent witness validation requires operator authority")
    director_verify(world,replay)
    if receipt.world_digest!=world.digest or receipt.replay_digest!=replay.digest:
        raise WitnessError("witness source project or action replay is foreign")
    if receipt.action_index<0 or receipt.action_index>=len(replay.actions):
        raise WitnessError("invented witness action index")
    state=director_initial(world)
    for action in replay.actions[:receipt.action_index]:
        state=director_step(world,state,action)
    action=replay.actions[receipt.action_index]
    affordance=_affordance(world,state.scene,action)
    if (state.digest!=receipt.source_state_digest or
        canonical_digest(action.payload())!=receipt.action_digest or
        affordance is None or affordance.kind!=receipt.action_kind or
        affordance.target!=receipt.action_target or
        state.scene!=receipt.scene or
        director_step(world,state,action).turn!=receipt.observed_turn or
        receipt.action_kind not in REACTIONS):
        raise WitnessError("witness testimony cannot be verified from gameplay facts")


__all__=[
    "WitnessError","WitnessReceipt","EmergentQuest","WitnessCampaign",
    "observe_story","validate_witness","REACTIONS",
]
