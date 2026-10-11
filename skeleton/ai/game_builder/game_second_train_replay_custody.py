"""Two-independent-reviewer original TRAIN replay custody for secondary weights.

The local game ranker cannot use a caller-supplied 'mechanic' string as
proof that a real game actually exercised that mechanic. For EVERY new
TRAIN example two distinct configured reviewers must attest that the
exact original-game project, example and canonical replay evidence match
a separately captured replay receipt. Test/validation examples are
NEVER used here or written into the gradient evidence archive.

HMAC attests assigned secret possession, NOT independent scientific truth:
real game-device replay capture, reviewer identities and controlled licence
authority must be validated externally before configuring review keys.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
from hashlib import sha256
import hmac

from .contracts import canonical_digest
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .game_training_flow import FlowPlan
from .game_model_promotion import PromotionError
from .competitive_title_radar import _sha,_id,_date


@dataclass(frozen=True,slots=True)
class OriginalReplayTrainingAttestation:
    example_id: str
    original_project_digest: str
    exact_evidence_digest: str
    mechanic: str
    independent_replay_digest: str
    review_role: str
    reviewer_id: str
    observed_at: str
    signature: str

    def __post_init__(self):
        for value in (self.example_id,self.original_project_digest,
                      self.exact_evidence_digest,self.independent_replay_digest,
                      self.signature):
            _sha(value,"independent original-game replay")
        _id(self.mechanic,"tested original mechanic")
        _id(self.reviewer_id,"authorized independent replay witness")
        if self.review_role not in {"independent_gameplay","adversarial_mirror"}:
            raise PromotionError("separate original gameplay and adversarial review required")
        _date(self.observed_at)

    def body(self):
        return dict(
            schema="skeleton.game_builder.original_second_train_replay.v1",
            example_id=self.example_id,
            original_project_digest=self.original_project_digest,
            exact_evidence_digest=self.exact_evidence_digest,
            mechanic=self.mechanic,
            independent_replay_digest=self.independent_replay_digest,
            review_role=self.review_role,reviewer_id=self.reviewer_id,
            observed_at=self.observed_at)

    def payload(self):
        return dict(self.body(),signature=self.signature)


def sign_train_replay(
    attestation: OriginalReplayTrainingAttestation,
    signer: TrustedCompetitionJudge,
):
    if (not isinstance(attestation,OriginalReplayTrainingAttestation)
            or not isinstance(signer,TrustedCompetitionJudge)
            or signer.judge_id!=attestation.reviewer_id):
        raise PromotionError("replay signer must authenticate exactly their own role")
    return replace(attestation,signature=_mac(attestation.body(),signer.key))


@dataclass(frozen=True,slots=True)
class VerifiedSecondTrainCustody:
    flow_plan_digest: str
    covered_examples: int
    independent_original_projects: int
    reviewer_roles: tuple[str,...]
    manifest_digest: str
    heldout_example_ids_disclosed: bool=False

    def payload(self):
        return dict(
            schema="skeleton.game_builder.second_train_replay_custody.v1",
            flow_plan_digest=self.flow_plan_digest,
            covered_examples=self.covered_examples,
            independent_original_projects=self.independent_original_projects,
            reviewer_roles=list(self.reviewer_roles),
            manifest_digest=self.manifest_digest,
            heldout_example_ids_disclosed=self.heldout_example_ids_disclosed,
            training_performed=False,
            no_unlicensed_external_media_in_training=True)


def qualify_second_original_game_replays(
    plan: FlowPlan,
    attestations: tuple[OriginalReplayTrainingAttestation,...], *,
    trusted_reviewers: tuple[tuple[str,TrustedCompetitionJudge],...],
    authorized: bool,
)->VerifiedSecondTrainCustody:
    if not authorized:
        raise PermissionError("second reviewer training needs external replay clearance")
    if (not isinstance(plan,FlowPlan)
            or type(attestations) is not tuple
            or not 1<=len(attestations)<=8192
            or any(not isinstance(x,OriginalReplayTrainingAttestation)
                   for x in attestations)
            or type(trusted_reviewers) is not tuple
            or len(trusted_reviewers)!=2
            or {x[0] for x in trusted_reviewers}!=
                {"independent_gameplay","adversarial_mirror"}
            or len({judge.judge_id for _,judge in trusted_reviewers})!=2):
        raise PromotionError("two configured independent reviewers and complete signed TRAIN receipts required")
    cases={x.example_id:x for x in plan.selected if x.split=="train"}
    if not cases or len(cases)>4096:
        raise PromotionError("bounded independent TRAIN project evidence necessary")
    if len({x.project_digest for x in cases.values()})<2:
        raise PromotionError("at least two separate original TRAIN game projects")
    if len(attestations)!=2*len(cases):
        raise PromotionError("every original training example needs both gameplay and adversarial replay attestation")
    roles=dict(trusted_reviewers)
    seen=set()
    replay_owners={}
    manifest=[]
    for x in attestations:
        candidate=cases.get(x.example_id)
        judge=roles.get(x.review_role)
        if candidate is None:
            raise PromotionError("validation, test or foreign case included as secondary TRAIN evidence")
        if (judge is None or x.reviewer_id!=judge.judge_id
                or not hmac.compare_digest(
                    x.signature,_mac(x.body(),judge.key))):
            raise PromotionError("forged or improperly delegated original replay identity")
        if (candidate.project_digest!=x.original_project_digest
                or canonical_digest(candidate.evidence)!=x.exact_evidence_digest
                or candidate.evidence.get("mechanic")!=x.mechanic
                or candidate.approval!="quarantined"):
            raise PromotionError("mechanic tags and original-game evidence must match exact signed replay")
        forbidden={"source_url","reference_text","copyrighted_text",
                   "third_party_video","external_training_source"}
        if forbidden&set(candidate.evidence):
            raise PromotionError("reference-only third party content cannot enter training receipts")
        original_owner=replay_owners.setdefault(x.independent_replay_digest,
                                                 x.example_id)
        if original_owner!=x.example_id:
            raise PromotionError("one gameplay recording reused as multiple independent game examples")
        identity=(x.example_id,x.review_role)
        if identity in seen:
            raise PromotionError("reused replay signer cannot inflate independent gameplay proof")
        seen.add(identity)
        manifest.append(canonical_digest(x.body()))
    return VerifiedSecondTrainCustody(
        canonical_digest(plan.payload()),len(cases),
        len({x.project_digest for x in cases.values()}),
        tuple(sorted(roles)),
        canonical_digest(sorted(manifest)))


__all__=["OriginalReplayTrainingAttestation",
         "sign_train_replay","VerifiedSecondTrainCustody",
         "qualify_second_original_game_replays"]
