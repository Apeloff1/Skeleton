"""Reviewed cross-project original-game knowledge distillation and custody.

Turn actual red-team failures and valid witnessed controls into balanced,
source-anchored instruction pairs. Project-grouped splits prevent copying
near-identical original game evidence from training into validation. Wiki/
HOAG/release reviewers explicitly decide promotion. Compact rule weights
are *not* LLM model parameters and are never silently applied to an AI.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
from hashlib import sha256
from pathlib import Path
import json

from .contracts import canonical_digest,canonical_json
from .competitive_mirror_training import (
    CompetitionReport,TrainingCandidate,MirrorCompetitionError,
    distill_mirror_cases,split_project,training_jsonl,
)
from .npc_witness_quest_engine import WitnessCampaign


class AlmanacError(ValueError):
    """Untrusted original-game learning data or premature promotion."""


@dataclass(frozen=True,slots=True)
class Curriculum:
    project_digest: str
    split: str
    source_mirror_digest: str
    examples: tuple[TrainingCandidate,...]
    red_team_count: int
    positive_controls: int

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.original_learning_curriculum.v1",
                    project_digest=self.project_digest,
                    split=self.split,
                    source_mirror_digest=self.source_mirror_digest,
                    red_team_count=self.red_team_count,
                    positive_controls=self.positive_controls,
                    examples=[x.payload() for x in self.examples],
                    rights_status="original_generated_gameplay_only",
                    training_run_executed=False,
                    autonomous_model_weight_update=False,
                    approval="quarantined")


def build_curriculum(report: CompetitionReport,campaign: WitnessCampaign,*,
                     authorized: bool)->Curriculum:
    if not authorized:
        raise PermissionError("AI learning-candidate distillation requires operator authority")
    if not report.passed:
        raise AlmanacError("rejected real game mirror cases cannot be a positive training baseline")
    negatives=distill_mirror_cases(report,campaign,authorized=True)
    split=split_project(report.world_digest)
    positives=[]
    for number,receipt in enumerate(campaign.witnessed[:min(12,len(negatives)//3)]):
        positives.append(TrainingCandidate(
            project_digest=report.world_digest,split=split,
            example_id=canonical_digest({
                "source":receipt.digest,"mirror":report.digest,"kind":"verified_control"
            }),
            instruction=(
                "Assess first-person NPC memory and mission opportunity claims "
                "against verified gameplay, spatial witnessing and unaltered story."
            ),
            input=dict(canonical_witness=receipt.payload(),
                       source_campaign_digest=campaign.digest),
            expected=dict(decision="accept_witnessed_incident_only",
                          reason="canonical_action_and_firsthand_memory_replayed",
                          requires_quest_author_review=True,
                          invariant_goal=campaign.storyboard_goal),
            evidence=dict(world_digest=campaign.world_digest,
                          original_replay_digest=campaign.original_replay_digest,
                          mirror_digest=report.digest,
                          witness_digest=receipt.digest,
                          verified_control=True),
        ))
    combined=tuple((*negatives,*positives))
    training_jsonl(combined,authorized=True)
    return Curriculum(report.world_digest,split,report.digest,combined,
                      len(negatives),len(positives))


@dataclass(frozen=True,slots=True)
class ReviewDecision:
    curriculum_digest: str
    wiki_verified: bool
    hoag_approved: bool
    mirror_verified: bool
    human_approved: bool
    rights_reviewed: bool
    device_replay_checked: bool
    reviewer_notes: str

    def __post_init__(self):
        if (not isinstance(self.reviewer_notes,str)
                or len(self.reviewer_notes)>2000):
            raise AlmanacError("review note must be bounded human-provided text")
        for value in (
            self.wiki_verified,self.hoag_approved,self.mirror_verified,
            self.human_approved,self.rights_reviewed,self.device_replay_checked,
        ):
            if type(value) is not bool:
                raise AlmanacError("evidence gates must be explicit booleans")

    @property
    def approved(self):
        return all((
            self.wiki_verified,self.hoag_approved,self.mirror_verified,
            self.human_approved,self.rights_reviewed,self.device_replay_checked,
        ))


@dataclass(frozen=True,slots=True)
class DistilledKnowledge:
    project_digest: str
    curriculum_digest: str
    review_digest: str
    rules: tuple[tuple[str,str,int],...]
    source_example_count: int
    split: str

    def payload(self):
        return dict(schema="skeleton.game_builder.reviewed_knowledge_rules.v1",
                    project_digest=self.project_digest,
                    curriculum_digest=self.curriculum_digest,
                    review_digest=self.review_digest,
                    rules=[dict(challenge=k,defense=defense,verified_count=count)
                           for k,defense,count in self.rules],
                    source_example_count=self.source_example_count,
                    split=self.split,
                    knowledge_format="content_addressed_symbolic_rules",
                    neural_model_parameters=False,
                    human_review_receipt_required=True)


def promote_curriculum(curriculum: Curriculum,review: ReviewDecision,*,
                       authorized: bool)->DistilledKnowledge:
    if not authorized:
        raise PermissionError("game knowledge cannot be promoted without operator authority")
    if not isinstance(curriculum,Curriculum) or not isinstance(review,ReviewDecision):
        raise AlmanacError("typed source knowledge and review evidence required")
    if review.curriculum_digest!=curriculum.digest or not review.approved:
        raise AlmanacError("Wiki, HOAG, mirror, rights, device and human gates must all approve")
    if curriculum.split!="train":
        raise AlmanacError("validation/test project examples cannot leak into trained rule index")
    counts={}
    for example in curriculum.examples:
        if (example.project_digest!=curriculum.project_digest or
            example.split!=curriculum.split or example.approval!="quarantined"):
            raise AlmanacError("training evidence provenance was altered")
        if example.expected["decision"]!="reject":
            continue
        key=(example.input["attack_family"],example.expected["required_defense"])
        counts[key]=counts.get(key,0)+1
    if not counts:
        raise AlmanacError("no adversarially verified rules to distill")
    return DistilledKnowledge(
        curriculum.project_digest,curriculum.digest,canonical_digest({
            "curriculum":review.curriculum_digest,"wiki":review.wiki_verified,
            "hoag":review.hoag_approved,"mirror":review.mirror_verified,
            "human":review.human_approved,"rights":review.rights_reviewed,
            "device":review.device_replay_checked,
            "notes":review.reviewer_notes,
        }),
        tuple(sorted((k,defense,n) for (k,defense),n in counts.items())),
        len(curriculum.examples),curriculum.split,
    )


def multi_project_index(knowledge: tuple[DistilledKnowledge,...],*,
                        authorized: bool)->dict:
    if not authorized:
        raise PermissionError("cross-game knowledge indexing requires review")
    if len(knowledge)>512 or any(not isinstance(k,DistilledKnowledge) for k in knowledge):
        raise AlmanacError("bounded verified project-level almanac required")
    unique={k.project_digest for k in knowledge}
    if len(unique)!=len(knowledge):
        raise AlmanacError("duplicate project data would overweight training")
    aggregated={}
    for entry in knowledge:
        if entry.split!="train":
            raise AlmanacError("held-out project evidence cannot enter training almanac")
        for key,defense,observations in entry.rules:
            aggregated[(key,defense)]=aggregated.get((key,defense),0)+observations
    return dict(schema="skeleton.game_builder.cross_project_rules.v1",
                verified_project_count=len(knowledge),
                project_digests=sorted(unique),
                rules=[dict(attack=k,defense=d,count=n)
                       for (k,d),n in sorted(aggregated.items())],
                raw_external_artwork_included=False,
                code_fixes_automatically_deployed=False,
                machine_weight_training_performed=False)


def quarantine_curriculum(curriculum: Curriculum,workspace_root: str|Path,*,
                          authorized: bool)->dict:
    if not authorized:
        raise PermissionError("training candidate storage requires operator authority")
    from .game_project_workspace import GameWorkspace,WorkspaceError
    studio=GameWorkspace(workspace_root)
    if not isinstance(curriculum,Curriculum):
        raise AlmanacError("typed original training curriculum required")
    if curriculum.split!=split_project(curriculum.project_digest):
        raise AlmanacError("project split not reproducible")
    data=training_jsonl(curriculum.examples,authorized=True)
    if len(data)>2_000_000:
        raise AlmanacError("candidate evidence exceeds consumer data budget")
    target=studio.root/"training/quarantine"/(curriculum.digest+".jsonl")
    if target.is_symlink() or target.exists():
        raise AlmanacError("identical training data already quarantined")
    with target.open("xb") as handle:
        handle.write(data)
    return dict(schema="skeleton.game_builder.training_quarantine_receipt.v1",
                path=str(target),project_digest=curriculum.project_digest,
                split=curriculum.split,examples=len(curriculum.examples),
                source_sha256=sha256(data).hexdigest(),
                curriculum_digest=curriculum.digest,
                approved=False,neural_training_performed=False)


__all__=[
    "AlmanacError","Curriculum","ReviewDecision","DistilledKnowledge",
    "build_curriculum","promote_curriculum","multi_project_index",
    "quarantine_curriculum",
]
