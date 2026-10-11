"""Three-round, three-authority competitive battle-plan deliberation.

Models never sign for one another. 'Dragon', 'Jeeves' and 'Adversarial' must
each submit a distinct evidence-bound assessment through an operator
configured credential. Their names alone do NOT prove real models executed.
A crawler round is admissible ONLY from fresh currently approved Wiki/rights
citations, at increasing independently evidenced breadth. All 102 facets
are explicitly covered by each system, but a finding may call for more data.

After the three rounds the plan is DRAFT/AWAITING_USER, not automatically
accepted. Reject/revise creates a stricter new epoch with the three-round
research and review sequence repeated.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
import hmac

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError,_date,_id,_sha
from .competitive_deep_analysis import ALL_FACETS
from .competitive_user_critique import CurrentProjectCritique
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .reviewed_knowledge import ReviewedKnowledgeStore,KnowledgeBrief
from .knowledge_rights_bridge import ClearedResearchPacket,require_cleared_research_current
from .rights import RightsLedger

ROLES=("adversarial","dragon","jeeves")
ROUND_TYPES=("focused","reinterrogation","wider_search")
TARGET_SOURCES=(2,4,6)
TARGET_GROUPS=(2,3,4)


@dataclass(frozen=True,slots=True)
class ApprovedCrawlerRound:
    epoch: int
    round_number: int
    strategy: str
    source_ids: tuple[str,...]
    independent_groups: tuple[str,...]
    reviewed_citation_digests: tuple[str,...]
    wiki_root: str
    rights_root: str
    packet_digest: str
    researched_at: str
    freshness_verified: bool

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.crawler_research_round.v1",
                    epoch=self.epoch,round_number=self.round_number,
                    strategy=self.strategy,source_ids=list(self.source_ids),
                    independent_groups=list(self.independent_groups),
                    reviewed_citation_digests=list(self.reviewed_citation_digests),
                    wiki_root=self.wiki_root,rights_root=self.rights_root,
                    packet_digest=self.packet_digest,
                    researched_at=self.researched_at,
                    freshness_verified=self.freshness_verified,
                    network_fetch_performed_by_this_function=False,
                    source_freshness_requires_live_wiki_rights=True)


def admit_crawler_round(
    wiki: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    packet: ClearedResearchPacket,
    rights: RightsLedger,*,
    epoch: int,round_number: int,as_of: str,
    authorized: bool,
)->ApprovedCrawlerRound:
    if not authorized:
        raise PermissionError("actual human-reviewed crawler research clearance required")
    _date(as_of)
    if (type(epoch) is not int or not 0<=epoch<=100
            or type(round_number) is not int or not 1<=round_number<=3
            or not isinstance(brief,KnowledgeBrief)
            or not isinstance(packet,ClearedResearchPacket)
            or not isinstance(wiki,ReviewedKnowledgeStore)
            or not isinstance(rights,RightsLedger)):
        raise ThreatRadarError("canonical Wiki and rights verified three-round research required")
    wiki.require_fresh_brief(brief,authorized=True)
    require_cleared_research_current(packet,wiki,rights,authorized=True)
    if (brief.scope!="design_reference" or brief.owner!=packet.owner
            or brief.knowledge_root!=packet.knowledge_root
            or packet.research_brief_digest!=brief.to_payload()["brief_digest"]
            or canonical_digest([x.to_payload() for x in brief.citations])!=
               canonical_digest([x.to_payload() for x in packet.citations])):
        raise ThreatRadarError("crawler sources differ from freshly cleared citations")
    sources=tuple(sorted({x.source_id for x in brief.citations}))
    groups=tuple(sorted({x.dependence_group for x in brief.citations}))
    multiplier=min(4,1+epoch)
    min_sources=TARGET_SOURCES[round_number-1]*multiplier
    min_groups=TARGET_GROUPS[round_number-1]+epoch
    if len(sources)<min_sources or len(groups)<min_groups:
        raise ThreatRadarError("round has insufficient actual independent reviewed research breadth")
    if any(_date(x.observed_at)>_date(as_of) for x in brief.citations):
        raise ThreatRadarError("research citation from future")
    return ApprovedCrawlerRound(
        epoch,round_number,ROUND_TYPES[round_number-1],sources,groups,
        tuple(sorted(canonical_digest(x.to_payload()) for x in brief.citations)),
        brief.knowledge_root,packet.rights_ledger_digest,
        packet.to_payload()["packet_digest"],as_of,True)


@dataclass(frozen=True,slots=True)
class RoleFinding:
    facet: str
    severity_bp: int
    evidence_status: str
    critique: str
    recommendation: str
    test_of_success: str
    source_digest: str

    def __post_init__(self):
        if self.facet not in ALL_FACETS:
            raise ThreatRadarError("agent findings must be typed game scrutiny facets")
        if type(self.severity_bp) is not int or not 0<=self.severity_bp<=10000:
            raise ThreatRadarError("bounded technical severity required")
        if self.evidence_status not in {"measured","hypothesis","missing"}:
            raise ThreatRadarError("agent must distinguish measured from unverified")
        for val in (self.critique,self.recommendation,self.test_of_success):
            if not isinstance(val,str) or not 24<=len(val)<=900 or not val.strip():
                raise ThreatRadarError("substantive falsifiable critique/recommendation/test required")
        _sha(self.source_digest,"research reference")

    def payload(self):
        return dict(facet=self.facet,severity_bp=self.severity_bp,
                    evidence_status=self.evidence_status,
                    critique=self.critique,
                    recommendation=self.recommendation,
                    test_of_success=self.test_of_success,
                    source_digest=self.source_digest)


@dataclass(frozen=True,slots=True)
class AgentDeliberation:
    role: str
    epoch: int
    round_number: int
    project_critique_digest: str
    research_digest: str
    reviewed_facets: tuple[str,...]
    reviewed_source_ids: tuple[str,...]
    findings: tuple[RoleFinding,...]
    challenged_role: str
    challenge: str
    answer_to_prior_objection: str
    quantified_quality_bp: int
    hard_vetoes: tuple[str,...]
    signer_id: str
    authored_at: str
    signature: str

    def __post_init__(self):
        if self.role not in ROLES or self.challenged_role not in ROLES or self.role==self.challenged_role:
            raise ThreatRadarError("roles need independent adversarial peer critique")
        if type(self.epoch) is not int or not 0<=self.epoch<=100 or type(self.round_number) is not int or not 1<=self.round_number<=3:
            raise ThreatRadarError("three-round model deliberation only")
        for d in (self.project_critique_digest,self.research_digest,self.signature):
            _sha(d)
        if (type(self.reviewed_facets) is not tuple or
                self.reviewed_facets!=tuple(sorted(ALL_FACETS))):
            raise ThreatRadarError("each reviewer must cover all 102 original + competitor scrutiny facets")
        if type(self.reviewed_source_ids) is not tuple or self.reviewed_source_ids!=tuple(sorted(set(self.reviewed_source_ids))):
            raise ThreatRadarError("exact reviewed sources in every role report required")
        if type(self.findings) is not tuple or not 2<=len(self.findings)<=24 or any(not isinstance(f,RoleFinding) for f in self.findings):
            raise ThreatRadarError("multiple substantive, typed independently challenged findings required")
        if len({x.facet for x in self.findings})!=len(self.findings):
            raise ThreatRadarError("repetitive finding filler is not a high-effort deliberation")
        for text in (self.challenge,self.answer_to_prior_objection):
            if not isinstance(text,str) or not 50<=len(text)<=1600:
                raise ThreatRadarError("substantive independent challenge and rebuttal required")
        if (type(self.quantified_quality_bp) is not int or
                not 0<=self.quantified_quality_bp<=10000 or
                type(self.hard_vetoes) is not tuple or
                len(self.hard_vetoes)>12 or any(not isinstance(v,str) or len(v)<10 or len(v)>300 for v in self.hard_vetoes)):
            raise ThreatRadarError("bounded honest quality judgment and explicit vetoes required")
        _id(self.signer_id,"model service credential")
        _date(self.authored_at)

    def body(self):
        return dict(schema="skeleton.game_builder.separate_ai_review.v1",
                    role=self.role,epoch=self.epoch,round_number=self.round_number,
                    project_critique_digest=self.project_critique_digest,
                    research_digest=self.research_digest,
                    reviewed_facets=list(self.reviewed_facets),
                    reviewed_source_ids=list(self.reviewed_source_ids),
                    findings=[x.payload() for x in self.findings],
                    challenged_role=self.challenged_role,
                    challenge=self.challenge,
                    answer_to_prior_objection=self.answer_to_prior_objection,
                    quantified_quality_bp=self.quantified_quality_bp,
                    hard_vetoes=list(self.hard_vetoes),
                    signer_id=self.signer_id,authored_at=self.authored_at)

    def payload(self):
        return dict(self.body(),signature=self.signature)

    @property
    def digest(self):
        return canonical_digest(self.payload())


def sign_deliberation(review: AgentDeliberation, signer: TrustedCompetitionJudge):
    if (not isinstance(review,AgentDeliberation)
            or not isinstance(signer,TrustedCompetitionJudge)
            or signer.judge_id!=review.signer_id):
        raise ThreatRadarError("cannot sign for another agent identity")
    return replace(review,signature=_mac(review.body(),signer.key))


@dataclass(frozen=True,slots=True)
class DeliberatedRound:
    research: ApprovedCrawlerRound
    role_reviews: tuple[AgentDeliberation,...]
    accepted: bool
    objection_codes: tuple[str,...]
    action_priorities: tuple[str,...]
    quality_floor_bp: int

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.tri_council_round.v1",
                    research=self.research.payload(),
                    role_reviews=[r.payload() for r in self.role_reviews],
                    accepted=self.accepted,
                    objection_codes=list(self.objection_codes),
                    action_priorities=list(self.action_priorities),
                    quality_floor_bp=self.quality_floor_bp,
                    no_model_weights_or_game_code_modified=True)


def deliberate_verified_round(
    critique: CurrentProjectCritique,
    research: ApprovedCrawlerRound,
    reviews: tuple[AgentDeliberation,...],
    trusted_keys: tuple[TrustedCompetitionJudge,...], *,
    authorized: bool,
    minimum_role_score_bp: int=7800,
)->DeliberatedRound:
    if not authorized:
        raise PermissionError("independent multi-model deliberation needs operator permission")
    if (not isinstance(critique,CurrentProjectCritique)
            or not isinstance(research,ApprovedCrawlerRound)
            or not research.freshness_verified
            or type(reviews) is not tuple or len(reviews)!=3
            or {r.role for r in reviews}!=set(ROLES)
            or type(trusted_keys) is not tuple or len(trusted_keys)!=3
            or len({k.judge_id for k in trusted_keys})!=3
            or type(minimum_role_score_bp) is not int or
            not 7000<=minimum_role_score_bp<=9500):
        raise ThreatRadarError("three distinct and complete authenticated AI deliberators required")
    keyring={x.judge_id:x for x in trusted_keys}
    objections=[]
    all_actions=[]
    for review in reviews:
        signing_key=keyring.get(review.signer_id)
        if (review.epoch!=research.epoch or review.round_number!=research.round_number
                or review.project_critique_digest!=critique.digest
                or review.research_digest!=research.digest
                or review.reviewed_source_ids!=research.source_ids
                or signing_key is None
                or not hmac.compare_digest(review.signature,_mac(review.body(),signing_key.key))):
            raise ThreatRadarError("unauthorized model, stale research or forged review")
        if _date(review.authored_at)<_date(research.researched_at):
            raise ThreatRadarError("AI deliberation predates newly researched evidence")
        if review.quantified_quality_bp<minimum_role_score_bp:
            objections.append(review.role+":below_predeclared_quality")
        if review.hard_vetoes:
            objections.append(review.role+":critical_veto")
        all_actions.extend(f.facet for f in review.findings)
    # Each actor must address at least one distinct other model.
    challenged={r.challenged_role for r in reviews}
    if challenged!=set(ROLES):
        raise ThreatRadarError("three-way review cannot silently omit criticism of one role")
    return DeliberatedRound(
        research,tuple(sorted(reviews,key=lambda r:r.role)),
        not objections,tuple(sorted(objections)),
        tuple(sorted(set(all_actions))),
        min(r.quantified_quality_bp for r in reviews))


@dataclass(frozen=True,slots=True)
class ThreeRoundBattlePlan:
    original_id: str
    snapshot_digest: str
    critique_digest: str
    epoch: int
    rounds: tuple[DeliberatedRound,...]
    user_decision: str = "not_requested"
    user_feedback: str = ""
    packet_digest: str|None = None

    @property
    def digest(self):
        return canonical_digest(self.payload())

    @property
    def ready_for_pdf_review(self):
        return len(self.rounds)==3 and all(r.accepted for r in self.rounds)

    def payload(self):
        return dict(schema="skeleton.game_builder.three_round_battle_plan.v1",
                    original_id=self.original_id,snapshot_digest=self.snapshot_digest,
                    critique_digest=self.critique_digest,epoch=self.epoch,
                    rounds=[x.payload() for x in self.rounds],
                    user_decision=self.user_decision,user_feedback=self.user_feedback,
                    packet_digest=self.packet_digest,
                    ready_for_pdf_review=self.ready_for_pdf_review,
                    automated_release=False)


def begin_battle_plan(critique: CurrentProjectCritique,*,authorized: bool):
    if not authorized:
        raise PermissionError("game campaign only starts with user project access")
    if not isinstance(critique,CurrentProjectCritique) or critique.all_facet_count!=len(ALL_FACETS):
        raise ThreatRadarError("full 102-facet self-analysis required before declaring a battle plan")
    return ThreeRoundBattlePlan(critique.original_id,critique.snapshot_digest,critique.digest,0,())


def add_verified_round(
    battle: ThreeRoundBattlePlan,
    result: DeliberatedRound,*,
    authorized: bool,
):
    if not authorized:
        raise PermissionError("one round at a time with exact trust evidence")
    if not isinstance(battle,ThreeRoundBattlePlan) or not isinstance(result,DeliberatedRound):
        raise ThreatRadarError("typed battle council results required")
    expected=len(battle.rounds)+1
    if (expected>3 or result.research.epoch!=battle.epoch
            or result.research.round_number!=expected
            or not result.accepted
            or battle.user_decision!="not_requested"):
        raise ThreatRadarError("incomplete/unaccepted round cannot skip to higher research")
    if battle.rounds:
        prior=battle.rounds[-1].research
        if (len(result.research.source_ids)<=len(prior.source_ids)
                or len(result.research.independent_groups)<=len(prior.independent_groups)
                or not set(prior.source_ids).issubset(result.research.source_ids)
                or not set(prior.independent_groups).issubset(result.research.independent_groups)
                or result.research.wiki_root==prior.wiki_root
                or result.research.packet_digest==prior.packet_digest
                or _date(result.research.researched_at)<=_date(prior.researched_at)):
            raise ThreatRadarError("each next round must actually widen/freshen source research")
    return replace(battle,rounds=battle.rounds+(result,))


def attach_multipart_pdf_packet(battle: ThreeRoundBattlePlan,packet_digest: str,*,
                                authorized: bool):
    if not authorized:
        raise PermissionError("independent verified tri-PDF packet requires studio authority")
    _sha(packet_digest,"three-document PDF manifest")
    if not battle.ready_for_pdf_review or battle.packet_digest is not None:
        raise ThreatRadarError("all three research and role rounds must pass before publishing PDFs")
    return replace(battle,packet_digest=packet_digest,user_decision="awaiting_user")


def record_user_plan_decision(
    battle: ThreeRoundBattlePlan,*,decision: str,feedback: str,
    exact_packet_digest: str,authorized: bool,
):
    if not authorized:
        raise PermissionError("only authenticated end-user session may decide proposal")
    _sha(exact_packet_digest,"reviewed packet digest")
    if (not isinstance(battle,ThreeRoundBattlePlan)
            or battle.user_decision!="awaiting_user"
            or battle.packet_digest!=exact_packet_digest):
        raise ThreatRadarError("cannot approve incomplete or swapped three-authority PDFs")
    if decision=="approve":
        if feedback and (not isinstance(feedback,str) or len(feedback)>2000):
            raise ThreatRadarError("bounded user approval annotations required")
        return replace(battle,user_decision="user_approved",
                       user_feedback=feedback)
    if decision!="revise" or not isinstance(feedback,str) or not 40<=len(feedback)<=2000:
        raise ThreatRadarError("user rejection must specify substantive higher-effort feedback")
    if battle.epoch>=3:
        raise ThreatRadarError("structured feedback exceeded bounded epochs; requires operator reset")
    # Rejected packets remain historical and never get silently approved.
    return ThreeRoundBattlePlan(
        battle.original_id,battle.snapshot_digest,battle.critique_digest,
        battle.epoch+1,(),user_decision="not_requested",
        user_feedback=feedback,packet_digest=None)


__all__=["ROLES","TARGET_SOURCES","ApprovedCrawlerRound",
         "admit_crawler_round","RoleFinding","AgentDeliberation",
         "sign_deliberation","DeliberatedRound","deliberate_verified_round",
         "ThreeRoundBattlePlan","begin_battle_plan",
         "add_verified_round","attach_multipart_pdf_packet",
         "record_user_plan_decision"]
