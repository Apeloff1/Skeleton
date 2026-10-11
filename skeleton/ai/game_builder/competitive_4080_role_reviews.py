"""Twelve thousand two hundred forty per-probe independent role obligations.

Authentic agent role reviews MUST arrive from separately configured
services. Missing measurements are explicitly marked unmeasured and cannot
be reclassified as an empirical weakness. One role cannot sign another's
findings; a review is for one 1,020/1,020/2,040 round slice only.

An independently verifiable machine annex must accompany the concise
27-page human strategy. The PDF can prioritize findings; nothing is
silently dropped from this annex.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from collections import Counter
import hmac

from .contracts import canonical_digest
from .competitive_4080_scrutiny import (
    CampaignCatalog,CampaignProbe,ProbeEvidenceReceipt,ROLE_NAMES,SIZES,
)
from .competitive_tri_council import ThreeRoundBattlePlan
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .competitive_title_radar import ThreatRadarError,_sha,_date,_id


@dataclass(frozen=True,slots=True)
class AgentProbeJudgment:
    probe_digest: str
    verdict: str
    impact_bp: int
    evidence_digest: str|None
    criticism: str
    improvement_direction: str
    verification_action: str

    def __post_init__(self):
        _sha(self.probe_digest)
        if self.verdict not in {"not_yet_tested","verified_risk",
                               "verified_strength","inconclusive"}:
            raise ThreatRadarError("every probe must carry an honest empirical status")
        if type(self.impact_bp) is not int or not 0<=self.impact_bp<=10000:
            raise ThreatRadarError("measured severity must be basis-point bounded")
        if self.evidence_digest is not None:
            _sha(self.evidence_digest)
        if self.verdict in {"verified_risk","verified_strength"} and self.evidence_digest is None:
            raise ThreatRadarError("unverified game quality cannot masquerade as empirical")
        if self.verdict=="not_yet_tested" and (self.impact_bp!=0 or self.evidence_digest is not None):
            raise ThreatRadarError("unmeasured competitor/game results have zero reported severity")
        for text in (self.criticism,self.improvement_direction,self.verification_action):
            if not isinstance(text,str) or not 30<=len(text)<=1200 or not text.strip():
                raise ThreatRadarError("each probe needs a falsifiable substantive report, not generic filler")

    def payload(self):
        return dict(probe_digest=self.probe_digest,verdict=self.verdict,
                    impact_bp=self.impact_bp,evidence_digest=self.evidence_digest,
                    criticism=self.criticism,
                    improvement_direction=self.improvement_direction,
                    verification_action=self.verification_action)


@dataclass(frozen=True,slots=True)
class AgentCampaignRoundReport:
    role: str
    round_number: int
    epoch: int
    catalog_digest: str
    matching_research_digest: str
    assessments: tuple[AgentProbeJudgment,...]
    critique_digest: str
    quality_objections: tuple[str,...]
    independent_review_notes: str
    signed_at: str
    signer_id: str
    signature: str

    def __post_init__(self):
        if self.role not in ROLE_NAMES or self.round_number not in (1,2,3):
            raise ThreatRadarError("role/time lane must be one of nine")
        if type(self.epoch) is not int or not 0<=self.epoch<=100:
            raise ThreatRadarError("bounded revision epoch")
        for d in (self.catalog_digest,self.matching_research_digest,
                  self.critique_digest,self.signature):
            _sha(d)
        if (type(self.assessments) is not tuple
                or len(self.assessments)!=SIZES[self.round_number-1]
                or any(not isinstance(x,AgentProbeJudgment) for x in self.assessments)
                or len({x.probe_digest for x in self.assessments})!=len(self.assessments)):
            raise ThreatRadarError("exact per-agent 1020/1020/2040 assessment coverage required")
        if (type(self.quality_objections) is not tuple
                or len(self.quality_objections)>100
                or type(self.independent_review_notes) is not str
                or not 80<=len(self.independent_review_notes)<=8000):
            raise ThreatRadarError("document specific peer objections and independent methodology")
        _date(self.signed_at)
        _id(self.signer_id,"actual AI service credential")

    def body(self):
        return dict(schema="skeleton.game_builder.ai_probe_round_report.v1",
                    role=self.role,round_number=self.round_number,
                    epoch=self.epoch,catalog_digest=self.catalog_digest,
                    matching_research_digest=self.matching_research_digest,
                    assessments=[x.payload() for x in self.assessments],
                    critique_digest=self.critique_digest,
                    quality_objections=list(self.quality_objections),
                    independent_review_notes=self.independent_review_notes,
                    signed_at=self.signed_at,signer_id=self.signer_id)

    def payload(self):
        return dict(self.body(),signature=self.signature)

    @property
    def digest(self):
        return canonical_digest(self.payload())


def sign_campaign_role_report(report: AgentCampaignRoundReport,
                              key: TrustedCompetitionJudge):
    if not isinstance(report,AgentCampaignRoundReport) or not isinstance(key,TrustedCompetitionJudge) or report.signer_id!=key.judge_id:
        raise ThreatRadarError("actual report signer must control assigned role service")
    return replace(report,signature=_mac(report.body(),key.key))


@dataclass(frozen=True,slots=True)
class CampaignCouncilAudit:
    original_id: str
    catalog_digest: str
    round_roles: tuple[str,...]
    total_reviewed_obligations: int
    measured_obligations: int
    unresolved_obligations: int
    all_nine_reports_attested: bool
    evidence_based_superiority: bool
    report_digests: tuple[str,...]

    def payload(self):
        return dict(schema="skeleton.game_builder.campaign_council_audit.v1",
                    original_id=self.original_id,catalog_digest=self.catalog_digest,
                    round_roles=list(self.round_roles),
                    total_reviewed_obligations=self.total_reviewed_obligations,
                    measured_obligations=self.measured_obligations,
                    unresolved_obligations=self.unresolved_obligations,
                    all_nine_reports_attested=self.all_nine_reports_attested,
                    evidence_based_superiority=self.evidence_based_superiority,
                    report_digests=list(self.report_digests),
                    role_names_without_signed_inference_are_not_model_execution=True)


def audit_council_scrutiny(
    catalog: CampaignCatalog,
    battle: ThreeRoundBattlePlan,
    reports: tuple[AgentCampaignRoundReport,...],
    configured_services: tuple[tuple[str,TrustedCompetitionJudge],...],*,
    authorized: bool,
)->CampaignCouncilAudit:
    if not authorized:
        raise PermissionError("actual three-system full campaign review needs operator scope")
    if (not isinstance(catalog,CampaignCatalog)
            or not isinstance(battle,ThreeRoundBattlePlan)
            or not battle.ready_for_pdf_review
            or type(reports) is not tuple or len(reports)!=9
            or any(not isinstance(x,AgentCampaignRoundReport) for x in reports)
            or type(configured_services) is not tuple or len(configured_services)!=3
            or any(role not in ROLE_NAMES or not isinstance(key,TrustedCompetitionJudge)
                   for role,key in configured_services)
            or len({x[0] for x in configured_services})!=3
            or len({x[1].judge_id for x in configured_services})!=3
            or catalog.original_id!=battle.original_id):
        raise ThreatRadarError("all nine model/round roles need configured distinct verified services")
    registry=dict(configured_services)
    expect={(role,i) for role in ROLE_NAMES for i in (1,2,3)}
    if {(r.role,r.round_number) for r in reports}!=expect:
        raise ThreatRadarError("nine unique temporal/agent role reports required")
    by_round={i:set(p.digest for p in catalog.probes if p.round_number==i)
              for i in (1,2,3)}
    measured=0
    for report in reports:
        signer=registry[report.role]
        if (report.epoch!=battle.epoch or report.catalog_digest!=catalog.digest
                or report.critique_digest!=battle.critique_digest
                or report.matching_research_digest!=battle.rounds[
                    report.round_number-1].research.digest
                or report.signer_id!=signer.judge_id
                or not hmac.compare_digest(
                    report.signature,_mac(report.body(),signer.key))
                or set(x.probe_digest for x in report.assessments)!=by_round[report.round_number]):
            raise ThreatRadarError("unverified/partial/cross-time model probe report")
        if _date(report.signed_at)<_date(battle.rounds[
                report.round_number-1].research.researched_at):
            raise ThreatRadarError("model report predates reviewed round-specific research")
        measured+=sum(x.verdict in {"verified_risk","verified_strength"}
                      for x in report.assessments)
    all_count=sum(SIZES)*3
    return CampaignCouncilAudit(
        catalog.original_id,catalog.digest,
        tuple(f"{r.round_number}_{r.role}" for r in sorted(
            reports,key=lambda x:(x.round_number,x.role))),
        all_count,measured,all_count-measured,True,
        False,  # No verified consumer superiority without separate actual
                # independent cohort, ancestry, rights and release gates.
        tuple(r.digest for r in sorted(reports,key=lambda x:(x.round_number,x.role))))


__all__=["AgentProbeJudgment","AgentCampaignRoundReport",
         "sign_campaign_role_report","CampaignCouncilAudit","audit_council_scrutiny"]
