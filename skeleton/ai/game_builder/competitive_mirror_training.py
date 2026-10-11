"""Competitive mirror-room and evidence-bounded learning candidates.

Three independent logical roles:
* red team mutates gameplay, witness testimony, narrative causality;
* blue team executes the actual validators, not heuristic 'looks fine';
* critic independently rebuilds the original incident and grades defects.
Outputs are quarantined supervised examples with provenance and reproducible
splits. This does not secretly train an LLM, edit weights or expand the
scheduler's mirror-call frequency.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json

from .contracts import canonical_digest, canonical_json
from .quest_scene_engine import DirectorWorld, DirectorReplay, DirectorError, director_verify
from .npc_society_runtime import Society
from .npc_witness_quest_engine import (
    WitnessCampaign, WitnessReceipt, WitnessError,
    observe_story, validate_witness, audit_witness_campaign,
)

class MirrorCompetitionError(ValueError):
    """Adversarial execution, evidence or release-candidate validation failed."""

ATTACK_FAMILIES=(
    "world_identity", "foreign_replay", "action_index", "state_forgery",
    "action_forgery", "spatial_teleport", "action_kind", "action_target",
    "chronology", "memory_forgery", "fabricated_theme", "altered_emotion",
    "observer_substitution", "motive_laundering", "main_story_rewrite",
    "fake_quest_objective", "erased_eyewitness", "fabricated_quest_unlock",
)
DIFFICULTY={
    "world_identity":3,"foreign_replay":3,"action_index":3,
    "state_forgery":4,"action_forgery":4,"spatial_teleport":4,
    "action_kind":4,"action_target":4,"chronology":4,
    "memory_forgery":5,"fabricated_theme":5,"altered_emotion":5,
    "observer_substitution":7,"motive_laundering":7,
    "main_story_rewrite":8,"fake_quest_objective":8,
    "erased_eyewitness":8,"fabricated_quest_unlock":9,
}
FULL_AUDIT=frozenset({
    "observer_substitution","motive_laundering","main_story_rewrite",
    "fake_quest_objective","erased_eyewitness","fabricated_quest_unlock",
})


@dataclass(frozen=True,slots=True)
class CompetitionProbe:
    index: int
    family: str
    adversary: str
    defense: str
    detected: bool
    attack_digest: str
    severity: int
    verdict: str

    def payload(self):
        return dict(index=self.index,family=self.family,
                    adversary=self.adversary,defense=self.defense,
                    detected=self.detected,attack_digest=self.attack_digest,
                    severity=self.severity,verdict=self.verdict)


@dataclass(frozen=True,slots=True)
class CompetitionReport:
    world_digest: str
    baseline_digest: str
    campaign_digest: str
    probes: tuple[CompetitionProbe,...]
    control_passed: bool
    reviewer_agreement: bool

    @property
    def passed(self):
        return bool(self.control_passed and self.reviewer_agreement and
                    len(self.probes)>=36 and all(p.detected for p in self.probes))

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        totals={}
        for p in self.probes:
            bucket=totals.setdefault(p.family,dict(attempts=0,detected=0))
            bucket["attempts"]+=1
            bucket["detected"]+=int(p.detected)
        return dict(schema="skeleton.game_builder.competitive_mirror.v1",
                    world_digest=self.world_digest,
                    baseline_digest=self.baseline_digest,
                    campaign_digest=self.campaign_digest,
                    control_passed=self.control_passed,
                    reviewer_agreement=self.reviewer_agreement,
                    attempts=len(self.probes),
                    detected=sum(p.detected for p in self.probes),
                    missed=sum(not p.detected for p in self.probes),
                    attack_family_count=len(totals),
                    by_family=totals,
                    probes=[p.payload() for p in self.probes],
                    outcome="pass" if self.passed else "blocked",
                    weight_training_performed=False,
                    publishing_approved=False)


@dataclass(frozen=True,slots=True)
class TrainingCandidate:
    project_digest: str
    split: str
    example_id: str
    instruction: str
    input: dict
    expected: dict
    evidence: dict
    approval: str = "quarantined"

    def payload(self):
        return dict(schema="skeleton.game_builder.adversarial_training_candidate.v1",
                    project_digest=self.project_digest,
                    split=self.split,example_id=self.example_id,
                    instruction=self.instruction,
                    input=self.input,expected=self.expected,
                    evidence=self.evidence,approval=self.approval)


def _attack(base: WitnessReceipt,campaign: WitnessCampaign,family: str,trial: int):
    changed=base
    altered=campaign
    if family=="world_identity":
        changed=replace(base,world_digest="f"*64)
    elif family=="foreign_replay":
        changed=replace(base,replay_digest="b"*64)
    elif family=="action_index":
        changed=replace(base,action_index=100000+trial)
    elif family=="state_forgery":
        changed=replace(base,source_state_digest="c"*64)
    elif family=="action_forgery":
        changed=replace(base,action_digest="d"*64)
    elif family=="spatial_teleport":
        changed=replace(base,scene="phantom_scene")
    elif family=="action_kind":
        changed=replace(base,action_kind="fight" if base.action_kind!="fight" else "heal")
    elif family=="action_target":
        changed=replace(base,action_target="phantom_objective")
    elif family=="chronology":
        changed=replace(base,observed_turn=base.observed_turn+103)
    elif family=="memory_forgery":
        changed=replace(base,source_memory_digest="e"*64)
    elif family=="fabricated_theme":
        changed=replace(base,theme="fabricated_lore")
    elif family=="altered_emotion":
        changed=replace(base,emotion=99 if base.emotion!=99 else -99)
    elif family=="observer_substitution":
        changed=replace(base,observer="citizen_9999")
    elif family=="motive_laundering":
        changed=replace(base,motive=("freedom" if base.motive!="freedom" else "mastery"))
    elif family=="main_story_rewrite":
        altered=replace(campaign,storyboard_goal="Replace the original story with foreign IP.")
    elif family=="fake_quest_objective":
        if not campaign.opportunities:
            raise MirrorCompetitionError("original witness campaign contains no derived quests")
        q=campaign.opportunities[0]
        forged=replace(q,premise="Invented quest victory without performed evidence")
        altered=replace(campaign,opportunities=(forged,*campaign.opportunities[1:]))
    elif family=="erased_eyewitness":
        altered=replace(campaign,witnessed=campaign.witnessed[1:])
    elif family=="fabricated_quest_unlock":
        if not campaign.opportunities:
            raise MirrorCompetitionError("original witness campaign contains no derived quests")
        altered=replace(campaign,opportunities=campaign.opportunities[1:])
    else:
        raise MirrorCompetitionError("unregistered red-team attack")
    if changed!=base:
        altered=replace(campaign,witnessed=(changed,*campaign.witnessed[1:]))
    return changed,altered


def run_mirror_competition(
    world: DirectorWorld,replay: DirectorReplay,campaign: WitnessCampaign,*,
    population: int,active_budget: int=40,ambient_budget: int=40,
    maximum_witnesses: int=128,attempts: int=72,authorized: bool,
    starting_society: Society | None=None,
)->CompetitionReport:
    if not authorized:
        raise PermissionError("competitive game mirrors require operator authority")
    if type(attempts) is not int or not 36<=attempts<=360:
        raise MirrorCompetitionError("bounded high-coverage red-team budget required")
    if not campaign.witnessed or not campaign.opportunities:
        raise MirrorCompetitionError("no original NPC witness/quest available for review")
    director_verify(world,replay)
    audit_witness_campaign(world,replay,campaign,population=population,
                           active_budget=active_budget,
                           ambient_budget=ambient_budget,
                           maximum_witnesses=maximum_witnesses,
                           starting_society=starting_society,authorized=True)
    expected=observe_story(world,replay,population=population,
                           active_budget=active_budget,
                           ambient_budget=ambient_budget,
                           maximum_witnesses=maximum_witnesses,
                           starting_society=starting_society,authorized=True)
    agreement=expected.digest==campaign.digest
    probes=[]
    for i in range(attempts):
        family=ATTACK_FAMILIES[i%len(ATTACK_FAMILIES)]
        tampered,variant=_attack(campaign.witnessed[0],campaign,family,i)
        defense=("campaign_reconstruction" if family in FULL_AUDIT
                 else "independent_action_and_memory_verification")
        try:
            if family in FULL_AUDIT:
                audit_witness_campaign(
                    world,replay,variant,population=population,
                    active_budget=active_budget,ambient_budget=ambient_budget,
                    maximum_witnesses=maximum_witnesses,authorized=True,
                )
            else:
                validate_witness(world,replay,tampered,authorized=True)
            caught=False
        except (DirectorError,WitnessError,ValueError,TypeError):
            caught=True
        probes.append(CompetitionProbe(
            index=i,family=family,
            adversary="red_team_source_mutator_v1",
            defense=defense,detected=caught,
            attack_digest=canonical_digest({
                "family":family,"trial":i,
                "tampered_witness":tampered.payload(),
                "tampered_campaign":variant.digest,
            }),
            severity=DIFFICULTY[family],
            verdict="correctly_rejected" if caught else "defense_missed",
        ))
    return CompetitionReport(
        world.digest,replay.digest,campaign.digest,
        tuple(probes),True,agreement,
    )


def split_project(project_digest: str) -> str:
    """Projects stay in one split; similar per-project variants cannot leak."""
    bucket=int(project_digest[:12],16)%20
    return "train" if bucket<15 else "validation" if bucket<18 else "test"


def distill_mirror_cases(
    report: CompetitionReport,campaign: WitnessCampaign,*,
    authorized: bool,include_failed: bool=True,
) -> tuple[TrainingCandidate,...]:
    if not authorized:
        raise PermissionError("training-candidate preparation needs operator authority")
    if not isinstance(report,CompetitionReport) or not report.control_passed:
        raise MirrorCompetitionError("review must have an executable positive control")
    if report.campaign_digest!=campaign.digest or report.world_digest!=campaign.world_digest:
        raise MirrorCompetitionError("training set would join unrelated projects")
    split=split_project(report.world_digest)
    examples=[]
    for probe in report.probes:
        if not probe.detected and not include_failed:
            continue
        examples.append(TrainingCandidate(
            project_digest=report.world_digest,split=split,
            example_id=canonical_digest({
                "report":report.digest,"trial":probe.index,
            }),
            instruction=(
                "Verify that NPC-origin quest evidence follows actual original "
                "gameplay, local eyewitness presence, memory provenance and "
                "the authored invariant story goal. Never endorse unverified lore."
            ),
            input=dict(attack_family=probe.family,
                       attack_digest=probe.attack_digest,
                       source_campaign_digest=campaign.digest),
            expected=dict(decision="reject" if probe.detected else "escalate",
                          reason=probe.family,
                          preserve_main_goal=campaign.storyboard_goal,
                          required_defense=probe.defense),
            evidence=dict(world_digest=report.world_digest,
                          canonical_replay_digest=report.baseline_digest,
                          critic_report_digest=report.digest,
                          discovered=probe.detected,
                          severity=probe.severity,
                          code_based_review=True),
        ))
    return tuple(examples)


def training_jsonl(examples: tuple[TrainingCandidate,...],*,authorized: bool) -> bytes:
    if not authorized:
        raise PermissionError("preparation of candidate data needs operator authority")
    if type(examples) is not tuple or len(examples)>2000:
        raise MirrorCompetitionError("bounded typed candidate collection required")
    if any(not isinstance(x,TrainingCandidate) or x.approval!="quarantined"
           for x in examples):
        raise MirrorCompetitionError("unreviewed candidates cannot impersonate approved weights")
    if len({x.example_id for x in examples})!=len(examples):
        raise MirrorCompetitionError("duplicate training examples")
    return ("\n".join(canonical_json(x.payload()) for x in examples)
            + ("\n" if examples else "")).encode("utf-8")


__all__=[
    "MirrorCompetitionError","CompetitionProbe","CompetitionReport",
    "TrainingCandidate","ATTACK_FAMILIES","run_mirror_competition",
    "distill_mirror_cases","training_jsonl","split_project",
]
