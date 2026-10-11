"""Independent, evidence-first game-tester learning almanac.

Runs diverse *real* original game playthroughs, then injects controlled
corruptions into their receipts. A tester is not credited for detecting bugs
unless a canonical replay validator actually rejects the mutation. Reports
distinguish objective playability from subjective fun and cross-platform QA.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorWorld, DirectorReplay, DirectorAction, DirectorError,
    director_initial, director_play, director_verify,
)
from .quest_director_solver import solve_quest
from .modular_mission_compiler import compile_modular_missions
from .modular_mission_runtime import replay_mission_book

TESTER_PERSONAS = (
    ("first_time", "ordinary", False),
    ("speedrunner", "fast", False),
    ("inventor", "creative", False),
    ("completionist", "creative", True),
    ("mixed_strategy", "balanced", True),
)
TEST_FAMILIES = (
    "foreign_world","foreign_genesis","forged_checkpoint",
    "forged_terminal_scene","rewound_clock","future_clock",
    "skipped_quest_stage","unearned_quest","invented_item",
    "narrative_flag_injection","cutscene_teleport","score_inflation",
    "creativity_inflation","optional_victory_forgery",
    "speed_bonus_forgery","method_substitution","action_suppression",
    "action_insertion","action_key_spoof","source_scene_spoof",
    "terminal_proof_swap","lore_rewrite","unsupported_completion",
    "chronology_disruption",
)
SEVERITY = {name:(9 if name in {
    "foreign_world","foreign_genesis","forged_checkpoint",
    "unearned_quest","terminal_proof_swap","chronology_disruption",
    "narrative_flag_injection","source_scene_spoof",
} else 7 if name in {
    "skipped_quest_stage","score_inflation","optional_victory_forgery",
    "method_substitution","action_suppression","action_insertion",
    "unsupported_completion",
} else 5) for name in TEST_FAMILIES}


class PlaytestError(ValueError):
    """Real game test replay, source or bounded population was invalid."""


@dataclass(frozen=True, slots=True)
class TesterCase:
    persona: str
    method: str
    replay_digest: str
    game_turns: int
    action_count: int
    visited_scenes: tuple[str, ...]
    completed_quests: tuple[str, ...]
    completed_stages: int
    score: int
    alternate_methods: tuple[str, ...]
    optional_awards: int
    narrative_flags: tuple[str, ...]
    cutscenes_seen: int
    mission_parity: bool
    source_story_goal: str

    def payload(self):
        return dict(persona=self.persona,method=self.method,
                    replay_digest=self.replay_digest,
                    game_turns=self.game_turns,action_count=self.action_count,
                    visited_scenes=list(self.visited_scenes),
                    completed_quests=list(self.completed_quests),
                    completed_stages=self.completed_stages,score=self.score,
                    alternate_methods=list(self.alternate_methods),
                    optional_awards=self.optional_awards,
                    narrative_flags=list(self.narrative_flags),
                    cutscenes_seen=self.cutscenes_seen,
                    mission_parity=self.mission_parity,
                    source_story_goal=self.source_story_goal)


@dataclass(frozen=True, slots=True)
class FaultProbe:
    persona: str
    family: str
    severity: int
    source_replay_digest: str
    corrupted_digest: str
    detected: bool
    changed_field: str
    original_fragment: object
    mutated_fragment: object

    def payload(self):
        return dict(persona=self.persona,family=self.family,
                    severity=self.severity,
                    source_replay_digest=self.source_replay_digest,
                    corrupted_digest=self.corrupted_digest,
                    detected=self.detected,
                    changed_field=self.changed_field,
                    original_fragment=self.original_fragment,
                    mutated_fragment=self.mutated_fragment,
                    evidence="canonical_replay_independently_reexecuted")


@dataclass(frozen=True, slots=True)
class GameTesterAlmanac:
    world_digest: str
    invariant_goal: str
    quest: str
    testers: tuple[TesterCase, ...]
    probes: tuple[FaultProbe, ...]
    visited_scene_count: int
    scene_count: int
    unique_solution_patterns: int
    unresolved_gameplay_gaps: tuple[str,...]

    @property
    def passed(self):
        return len(self.testers)>=3 and all(t.mission_parity for t in self.testers) and (
            all(p.detected for p in self.probes))

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        summary=Counter(p.family for p in self.probes if p.detected)
        return dict(
            schema="skeleton.game_builder.game_tester_almanac.v1",
            source_world_digest=self.world_digest,
            invariant_main_goal=self.invariant_goal,
            tested_quest=self.quest,
            tester_count=len(self.testers),
            replayed_action_count=sum(t.action_count for t in self.testers),
            test_families=len(TEST_FAMILIES),
            adversarial_attempts=len(self.probes),
            detected=sum(p.detected for p in self.probes),
            missed=sum(not p.detected for p in self.probes),
            scene_coverage_percent=(100*self.visited_scene_count)//self.scene_count,
            distinct_solutions=self.unique_solution_patterns,
            tests=[t.payload() for t in self.testers],
            mutations=[p.payload() for p in self.probes],
            family_coverage={k:summary.get(k,0) for k in TEST_FAMILIES},
            gaps=list(self.unresolved_gameplay_gaps),
            objective_replay_gates_passed=self.passed,
            subjective_fun_or_story_quality_proven=False,
            human_playtest_approval=False,
            native_device_certification=False,
            neural_network_trained=False,
        )


def _corrupt(replay: DirectorReplay, family: str, index: int) -> DirectorReplay:
    """Each attempt changes material evidence, never just an arbitrary name."""
    state=replay.final
    records=state.results
    if family=="foreign_world":
        return replace(replay,world_digest="f"*64)
    if family=="foreign_genesis":
        return replace(replay,initial_digest="e"*64)
    if family=="forged_checkpoint":
        return replace(replay,state_digests=("d"*64,*replay.state_digests[1:]))
    if family=="forged_terminal_scene":
        return replace(replay,final=replace(state,scene="ghost_scene"))
    if family=="rewound_clock":
        return replace(replay,final=replace(state,turn=max(0,state.turn-1)))
    if family=="future_clock":
        return replace(replay,final=replace(state,turn=state.turn+100))
    if family=="skipped_quest_stage":
        key,value=state.stage_index[0]
        updated=((key,max(0,value-1)),*state.stage_index[1:])
        return replace(replay,final=replace(state,stage_index=updated))
    if family=="unearned_quest":
        return replace(replay,final=replace(state,complete=(*state.complete,"imagined_win")))
    if family=="invented_item":
        return replace(replay,final=replace(state,acquired=(*state.acquired,"stolen_artwork")))
    if family=="narrative_flag_injection":
        return replace(replay,final=replace(state,narrative_flags=(*state.narrative_flags,"false_lore")))
    if family=="cutscene_teleport":
        return replace(replay,final=replace(state,cutscenes_seen=(*state.cutscenes_seen,"fake_cinematic")))
    if family in {"score_inflation","creativity_inflation","optional_victory_forgery",
                  "speed_bonus_forgery","method_substitution","lore_rewrite"}:
        if not records:
            raise PlaytestError("real completed stages required for scoring attacks")
        current=records[0]
        edited={
            "score_inflation":replace(current,score=current.score+10000),
            "creativity_inflation":replace(current,creativity_bonus=current.creativity_bonus+70),
            "optional_victory_forgery":replace(current,optional_bonus=current.optional_bonus+15),
            "speed_bonus_forgery":replace(current,speed_bonus=current.speed_bonus+90),
            "method_substitution":replace(current,approach="unproven_strategy"),
            "lore_rewrite":replace(current,lore_entry="Fabricated foreign source"),
        }[family]
        return replace(replay,final=replace(state,results=(edited,*records[1:])))
    if family=="action_suppression":
        return replace(replay,actions=replay.actions[:-1])
    if family=="action_insertion":
        return replace(replay,actions=(*replay.actions,DirectorAction("wait","wait",state.scene)))
    if family=="action_key_spoof":
        actions=list(replay.actions)
        actions[0]=replace(actions[0],key="phantom_quest_key")
        return replace(replay,actions=tuple(actions))
    if family=="source_scene_spoof":
        actions=list(replay.actions)
        actions[0]=replace(actions[0],scene="foreign_scene")
        return replace(replay,actions=tuple(actions))
    if family=="terminal_proof_swap":
        return replace(replay,final=director_initial_digest_spoof(state))
    if family=="unsupported_completion":
        return replace(replay,final=replace(state,results=records[:-1]))
    if family=="chronology_disruption":
        return replace(replay,state_digests=(*replay.state_digests[:-1],"c"*64))
    raise PlaytestError("unknown game-tester attack family")


def director_initial_digest_spoof(state):
    return replace(state,scene="rewritten_scene",turn=0)


def _mutation_excerpt(before: DirectorReplay,after: DirectorReplay):
    """A small genuine before/after proof fragment instead of a guessed bug
    description. Retains material data for learning and reproduction.
    """
    original=before.payload()
    altered=after.payload()
    for field in ("world_digest","initial_digest","state_digests","actions","final"):
        if original[field]==altered[field]:
            continue
        if field=="final":
            for key in sorted(original["final"]):
                if original["final"][key]!=altered["final"][key]:
                    before_value=original["final"][key]
                    after_value=altered["final"][key]
                    if key=="results":
                        changes=[
                            i for i,(a,b) in enumerate(zip(before_value,after_value))
                            if a!=b
                        ]
                        if changes:
                            index=changes[0]
                            return ("final.results."+str(index),
                                    before_value[index],after_value[index])
                    return "final."+key,before_value,after_value
        if field in {"actions","state_digests"}:
            values_before=original[field];values_after=altered[field]
            difference=next(
                (i for i in range(min(len(values_before),len(values_after)))
                 if values_before[i]!=values_after[i]),None)
            if difference is None:
                return field+".length",len(values_before),len(values_after)
            return field+"."+str(difference),values_before[difference],values_after[difference]
        return field,original[field],altered[field]
    raise PlaytestError("adversarial mutation has no observable evidence change")


def test_game_personas(world: DirectorWorld, quest_key: str,*,
                       authorized: bool,max_personas: int=5,
                       mutation_families: tuple[str,...]=TEST_FAMILIES) -> GameTesterAlmanac:
    if not authorized:
        raise PermissionError("original game tester almanac needs operator authority")
    if not isinstance(world,DirectorWorld) or type(max_personas) is not int or not 3<=max_personas<=5:
        raise PlaytestError("typed original game and bounded tester cohort required")
    if (not isinstance(mutation_families,tuple) or not mutation_families or
        len(mutation_families)>len(TEST_FAMILIES) or
        len(set(mutation_families))!=len(mutation_families) or
        any(k not in TEST_FAMILIES for k in mutation_families)):
        raise PlaytestError("only independently implemented tester fault families allowed")
    quest=next((q for q in world.quests if q.key==quest_key),None)
    if quest is None or quest.requires_quests:
        raise PlaytestError("tester needs a playable quest without unmet dependencies")
    book=compile_modular_missions(world,authorized=True)
    observed=[]
    testers=[]
    probes=[]
    methods=set()
    for persona,strategy,optional in TESTER_PERSONAS[:max_personas]:
        witness=solve_quest(world,quest_key,strategy=strategy,optional=optional,
                            authorized=True)
        replay=director_play(world,witness.replay.actions)
        director_verify(world,replay)
        if replay!=witness.replay:
            raise PlaytestError("game tester's action trace failed independent replay")
        progress=replay_mission_book(book,world,replay,authorized=True)
        q=next(q for q in world.quests if q.key==quest_key)
        outcomes=[o for o in progress.outcomes if o.mission==quest_key]
        results=[v for v in replay.final.results if v.quest==quest_key]
        parity=len(outcomes)==len(results)==len(q.stages)
        if not parity:
            raise PlaytestError("modular mission objectives disagree with canonical playable game")
        current=director_initial(world)
        scenes={current.scene}
        for action in replay.actions:
            from .quest_scene_engine import director_step
            current=director_step(world,current,action)
            scenes.add(current.scene)
        observed.extend(scenes)
        method=tuple(x.approach for x in results)
        methods.add(method)
        testers.append(TesterCase(
            persona,strategy,replay.digest,replay.final.turn,len(replay.actions),
            tuple(sorted(scenes)),replay.final.complete,len(results),
            sum(x.score for x in results),method,
            sum(x.optional_bonus//15 for x in results),
            replay.final.narrative_flags,len(replay.final.cutscenes_seen),
            parity,world.bible.invariant_goal,
        ))
        for family in mutation_families:
            changed=_corrupt(replay,family,len(probes))
            # Explicit positive/negative control: the original must be valid,
            # the modified source must differ, and its proof must be rejected.
            if changed==replay:
                raise PlaytestError("adversarial source mutation had no effect")
            try:
                director_verify(world,changed)
                caught=False
            except (DirectorError,ValueError,TypeError):
                caught=True
            field,original_value,mutated_value=_mutation_excerpt(replay,changed)
            probes.append(FaultProbe(
                persona,family,SEVERITY[family],replay.digest,
                canonical_digest(changed.payload()),caught,
                field,original_value,mutated_value,
            ))
    gaps=[]
    if len(set(observed))<len(world.scenes):
        gaps.append("not_all_authored_scenes_exercised")
    if len(methods)<2:
        gaps.append("test_personas_converged_on_one_solution")
    if any(t.cutscenes_seen==0 for t in testers):
        gaps.append("at_least_one_test_persona_observed_no_cutscene")
    if any(not p.detected for p in probes):
        gaps.append("unhandled_adversarial_mutation")
    return GameTesterAlmanac(
        world.digest,world.bible.invariant_goal,quest_key,
        tuple(testers),tuple(probes),len(set(observed)),len(world.scenes),
        len(methods),tuple(gaps),
    )


__all__=[
    "PlaytestError","TesterCase","FaultProbe","GameTesterAlmanac",
    "TESTER_PERSONAS","TEST_FAMILIES","test_game_personas",
]
