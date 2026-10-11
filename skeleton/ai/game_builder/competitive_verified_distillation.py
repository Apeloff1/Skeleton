"""Strict rights, two-witness evidence and user-approved knowledge handoff.

All 4,080 probe results and 12,240 independent role reviews must qualify
before empirical learning is considered. Public enemy reviews may be used
for *rights-permitted research* but are NEVER copied into model training
without explicit MODEL_TRAINING rights. Consumer- or project-owned examples
need their own current original-game rights record, heldout project splits
and externally inspected raw data.

This module prepares a quarantined training / almanac handoff, not actual
foundation-model weight optimization. Jeeves/Dragon/Adversarial weights
must only be updated by independent authorized optimizers, heldout tests,
regression gates and user/model promotion authority.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError,_date,_sha,_id
from .competitive_4080_scrutiny import (
    CampaignCatalog,ProbeEvidenceReceipt,
    audit_scrutiny_campaign,
)
from .competitive_4080_role_reviews import CampaignCouncilAudit
from .competitive_tri_council import ThreeRoundBattlePlan,ROLES
from .competitive_battle_approval import UserPacketDecision
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger,UseKind,RightsState
from .game_training_flow import CandidateBatch,plan_training_flow


@dataclass(frozen=True,slots=True)
class LicensedGameTrainingSources:
    source_ids: tuple[str,...]
    original_project_ids: tuple[str,...]
    heldout_validation_projects: tuple[str,...]
    heldout_test_projects: tuple[str,...]
    dataset_receipt_digest: str
    human_training_consent: bool

    def __post_init__(self):
        for name in ("source_ids","original_project_ids",
                     "heldout_validation_projects","heldout_test_projects"):
            value=getattr(self,name)
            if (type(value) is not tuple or not value or
                    value!=tuple(sorted(set(value)))):
                raise ThreatRadarError("legal training source and disjoint project splits required")
            for item in value:
                _id(item,name)
        _sha(self.dataset_receipt_digest,"actual training data content receipt")
        if type(self.human_training_consent) is not bool:
            raise ThreatRadarError("human licensed training consent must be explicit")
        groups=(
            set(self.original_project_ids),
            set(self.heldout_validation_projects),
            set(self.heldout_test_projects),
        )
        if any(groups[i]&groups[j] for i in range(3) for j in range(i+1,3)):
            raise ThreatRadarError("training/validation/test project leakage")
        if len(self.original_project_ids)<2:
            raise ThreatRadarError("multiple genuinely independent training projects required")


@dataclass(frozen=True,slots=True)
class TwoWitnessExperimentSeal:
    catalog_digest: str
    research_digest: str
    all_probe_evidence_digest: str
    sealed_at: str
    witnessed_experiments: int
    assessor_ids: tuple[str,str]
    assessor_signatures: tuple[str,str]

    def __post_init__(self):
        for field in ("catalog_digest","research_digest",
                      "all_probe_evidence_digest"):
            _sha(getattr(self,field),field)
        _date(self.sealed_at)
        if self.witnessed_experiments!=4080:
            raise ThreatRadarError("cannot seal partial 4080 experimental program")
        if (type(self.assessor_ids) is not tuple or len(self.assessor_ids)!=2
                or len(set(self.assessor_ids))!=2
                or type(self.assessor_signatures) is not tuple
                or len(self.assessor_signatures)!=2):
            raise ThreatRadarError("two independent bound evaluator keys required")
        for v in self.assessor_ids:
            _id(v,"evidence witness")
        for v in self.assessor_signatures:
            _sha(v,"evidence witness signature")

    def body(self):
        return dict(
            schema="skeleton.game_builder.4080_evidence_seal.v1",
            catalog_digest=self.catalog_digest,
            research_digest=self.research_digest,
            all_probe_evidence_digest=self.all_probe_evidence_digest,
            sealed_at=self.sealed_at,
            witnessed_experiments=self.witnessed_experiments,
            assessor_ids=list(self.assessor_ids))


def sign_two_witness_seal(
    seal: TwoWitnessExperimentSeal,
    keys: tuple[TrustedCompetitionJudge,TrustedCompetitionJudge],
):
    if not isinstance(seal,TwoWitnessExperimentSeal) or type(keys) is not tuple or len(keys)!=2 or tuple(x.judge_id for x in keys)!=seal.assessor_ids:
        raise ThreatRadarError("only exact independent experiment witness services can sign")
    return replace(seal,assessor_signatures=tuple(
        _mac(seal.body(),k.key) for k in keys))


@dataclass(frozen=True,slots=True)
class VerifiedLearningHandoff:
    original_id: str
    catalog_digest: str
    player_evidence_digest: str
    council_digest: str
    signed_approval_digest: str
    live_wiki_root: str
    permitted_reference_source_ids: tuple[str,...]
    training_licensed_source_ids: tuple[str,...]
    disjoint_project_groups: tuple[tuple[str,...],...]
    quarantined_dataset_digest: str
    status: str
    original_playtest_evidence_only: bool=True

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.verified_learning_handoff.v1",
            original_id=self.original_id,catalog_digest=self.catalog_digest,
            player_evidence_digest=self.player_evidence_digest,
            council_digest=self.council_digest,
            signed_approval_digest=self.signed_approval_digest,
            live_wiki_root=self.live_wiki_root,
            permitted_reference_source_ids=list(self.permitted_reference_source_ids),
            training_licensed_source_ids=list(self.training_licensed_source_ids),
            disjoint_project_groups=[list(g) for g in self.disjoint_project_groups],
            quarantined_dataset_digest=self.quarantined_dataset_digest,
            status=self.status,
            original_playtest_evidence_only=self.original_playtest_evidence_only,
            foundation_weight_updates_completed=False,
            local_review_model_optimized=False,
            wiki_almanac_write_completed=False,
            requires_separate_optimizer_and_promotion_review=True)


def prepare_verified_learning_handoff(
    catalog: CampaignCatalog,
    probes: tuple[ProbeEvidenceReceipt,...],
    seal: TwoWitnessExperimentSeal,
    witness_keys: tuple[TrustedCompetitionJudge,TrustedCompetitionJudge],
    council: CampaignCouncilAudit,
    battle: ThreeRoundBattlePlan,
    decision: UserPacketDecision,
    session_key: bytes,
    wiki: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    cleared: ClearedResearchPacket,
    rights: RightsLedger,
    licensed: LicensedGameTrainingSources, *,
    authorized: bool,
)->VerifiedLearningHandoff:
    if not authorized:
        raise PermissionError("verified learning promotion needs independent operator scope")
    if (not isinstance(catalog,CampaignCatalog)
            or not isinstance(seal,TwoWitnessExperimentSeal)
            or not isinstance(council,CampaignCouncilAudit)
            or not isinstance(battle,ThreeRoundBattlePlan)
            or not isinstance(decision,UserPacketDecision)
            or not isinstance(licensed,LicensedGameTrainingSources)
            or type(session_key) is not bytes or len(session_key)<32):
        raise ThreatRadarError("authenticated complete original-game experiment and legal training authority required")
    evidence=audit_scrutiny_campaign(catalog,probes,authorized=True)
    if not evidence.promotion_eligible:
        raise ThreatRadarError("all 4080 independently measured and failure-free probes required")
    sealed_digest=canonical_digest([x.payload() for x in sorted(
        probes,key=lambda x:x.probe_digest)])
    if (seal.catalog_digest!=catalog.digest
            or seal.all_probe_evidence_digest!=sealed_digest
            or seal.research_digest!=battle.rounds[-1].research.digest
            or seal.witnessed_experiments!=4080
            or tuple(x.judge_id for x in witness_keys)!=seal.assessor_ids
            or any(not hmac.compare_digest(sig,_mac(seal.body(),key.key))
                   for sig,key in zip(seal.assessor_signatures,witness_keys))):
        raise ThreatRadarError("experiment witness signatures or 4080 evidence root invalid")
    if (council.catalog_digest!=catalog.digest or
            council.total_reviewed_obligations!=12240 or
            not council.all_nine_reports_attested or
            council.unresolved_obligations!=0 or
            not battle.ready_for_pdf_review or
            battle.original_id!=catalog.original_id):
        raise ThreatRadarError("all three models must have fully reviewed empirical probes")
    approval_body=decision.body()
    if (decision.decision!="approve"
            or decision.packet_digest!=battle.packet_digest
            or decision.reviewed_roles!=tuple(sorted(ROLES))
            or not hmac.compare_digest(
                decision.signature,
                hmac.new(session_key,canonical_digest(approval_body).encode(),
                         "sha256").hexdigest())):
        raise ThreatRadarError("user did not approve the exact multipart peer-review PDF set")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(cleared,wiki,rights,authorized=True)
    if (brief.knowledge_root!=battle.rounds[-1].research.wiki_root
            or cleared.rights_ledger_digest!=battle.rounds[-1].research.rights_root
            or cleared.research_brief_digest!=brief.to_payload()["brief_digest"]
            or not set(battle.rounds[-1].research.source_ids).issubset(
                {x.source_id for x in brief.citations})):
        raise ThreatRadarError("latest Dragon/Wiki reviewed sources are no longer the approved evidence")
    if not licensed.human_training_consent:
        raise ThreatRadarError("original playtest train permission is not given")
    for sid in licensed.source_ids:
        rec=rights.source(sid)
        if (rec.rights_state in {RightsState.UNKNOWN_QUARANTINE,
                                RightsState.FORBIDDEN,
                                RightsState.FACTS_IDEAS_REFERENCE_ONLY,
                                RightsState.RESTRICTED_REFERENCE_ONLY}
                or UseKind.MODEL_TRAINING not in rec.allowed_uses):
            raise ThreatRadarError("reference-only, forbidden or not-train-permitted source")
    return VerifiedLearningHandoff(
        catalog.original_id,catalog.digest,sealed_digest,
        canonical_digest(council.payload()),
        canonical_digest(decision.payload()),brief.knowledge_root,
        tuple(sorted({x.source_id for x in brief.citations})),
        licensed.source_ids,
        (licensed.original_project_ids,licensed.heldout_validation_projects,
         licensed.heldout_test_projects),
        licensed.dataset_receipt_digest,"QUARANTINED_READY_FOR_REAL_TRAINING",
        True)


__all__=["LicensedGameTrainingSources","TwoWitnessExperimentSeal",
         "sign_two_witness_seal","VerifiedLearningHandoff",
         "prepare_verified_learning_handoff"]
