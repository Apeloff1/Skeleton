"""Rounds 3..18: replayable, fail-closed game AI / Dragon weight evolution.

R1/R2 live in the three-council research pipeline. This module manages
R3-R18 as 16 *distinct* finite work packages. A stored round is only a
signed evidence receipt; a reviewer's signature does NOT prove a crawl,
model inference, new dataset or weight training actually took place.
Actions for relevance scoring, real shadow sandbox, Dragon research
query planning and memory ordering use their specialized typed engines.
Completion never activates a local model or changes core LLM parameters.

Explicit host idle+thermal+privacy signals govern rounds 5 and 6.
Research-only rights are never promoted to model-training rights.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from typing import Callable
from urllib.parse import urlsplit
from ipaddress import ip_address
import hmac

from .contracts import canonical_digest
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .competitive_title_radar import ThreatRadarError,_id,_sha,_date
from .game_18round_relevance import OriginalTaskFocus,TopicPriority
from .game_18round_shadow_sandbox import SandboxVerification,HyperweightLoadOrder
from ..webcrawler.dragon_research_missions import (
    MissionPolicy,ResearchInterest,ResearchMission,plan_research,
)

ROUND_DESCRIPTIONS=(
 (3,"relevance_predecessor_ultraweight","task-relevance posterior, lawful concepts, strongest documented earlier genre evidence","original research queue before any actual parameter changes"),
 (4,"shadow_preapproval_and_sandbox","original-game shadow priority plus frozen champion comparison and exact code review","hold in isolated sandbox until independent nonregression, then human approval"),
 (5,"idle_priority_queue","new gameplay learning goals from active user project and existing verified queue","opt-in host idle, thermal, privacy and bounded resource checks"),
 (6,"background_general_game_knowledge","gamewide mechanics beyond current project, new independent references","background ONLY; no live user interaction or uncontrolled acquisition"),
 (7,"era_genre_theme_shadow","era/platform, genre and thematic modular weight candidates","separate modules, verified origin and era-specific no-regression evidence"),
 (8,"objective_game_creation_standards","build/play accessibility, original assets, code style, reproducible engine QA","predeclared professional standards and operational performance limits"),
 (9,"project_target_crawler_research","new project task gaps and uncertain historical/competitor knowledge","predeclared scoped research mission, no unauthorized URL fetch"),
 (10,"crawler_target_brief","ranked source categories and exact task, competitor and game-era target","human-reviewed target brief with rights and provenance boundaries"),
 (11,"acquire_crawler_destinations","validated public HTTPS source destinations acquired from reviewed metadata","SSRF/terms/robots authority and no crawler fetch presumed"),
 (12,"crawler_logs_to_shadow_scrutiny","content-safe source receipt, status, revision, licence and review metadata","no raw prompts/videos/log secrets or unreviewed gradient examples"),
 (13,"adversarial_shadow_review","candidate tests against current protected game policies and fallback","fresh holdouts, unrelated replay groups, reversibility"),
 (14,"weight_structure_optimization","sparse loading, no uncontrolled drift, regression-safe candidate evaluation","professional code quality and consumer resource envelopes"),
 (15,"hyperweight_structuring","modular game knowledge/weight routing with exact content version","separate era/genre/theme adapters, rights, proof and rollback records"),
 (16,"probability_ordered_queue","bounded task-match and utility lower-bound order for verified shadow modules","queue only, never install model parameters"),
 (17,"acquisition_and_gain_report","all model changes, source additions, deficits and benchmark deltas","user-visible evidence report; unknown and untrained stay unknown"),
 (18,"adjacent_topic_recrawl","unresolved adjacent mechanics, independently sourced follow-on knowledge","new bounded Dragon mission, never automatic research-to-weight promotion"),
)
ROUND_KINDS=tuple(x[1] for x in ROUND_DESCRIPTIONS)
IDLE_ROUNDS=frozenset({5,6})
SHADOW_ROUNDS=frozenset({4,7,8,13,14,15,16})
RESEARCH_ROUNDS=frozenset({3,9,10,11,12,17,18})


@dataclass(frozen=True,slots=True)
class EvolutionRoundReceipt:
    round_number: int
    action_type: str
    project_task_digest: str
    input_chain_digest: str
    report_digest: str
    external_evidence_roots: tuple[str,...]
    status: str
    research_reference_only: bool
    reviewer_id: str
    observed_at: str
    signature: str

    def __post_init__(self):
        if (type(self.round_number) is not int or not 3<=self.round_number<=18
                or self.action_type!=ROUND_DESCRIPTIONS[self.round_number-3][1]
                or self.status not in {"research_recorded","shadow_queued",
                                       "verified_sandbox","idle_assessed",
                                       "blocked","reviewed"}
                or type(self.research_reference_only) is not bool):
            raise ThreatRadarError("single typed bounded 18-round action receipt required")
        for d in (self.project_task_digest,self.input_chain_digest,
                  self.report_digest,self.signature):_sha(d)
        if (type(self.external_evidence_roots) is not tuple
                or not 1<=len(self.external_evidence_roots)<=64
                or tuple(sorted(set(self.external_evidence_roots)))!=self.external_evidence_roots):
            raise ThreatRadarError("independently identified bounded 18-round evidence roots")
        for d in self.external_evidence_roots:_sha(d)
        _id(self.reviewer_id,"one operator-configured review service")
        _date(self.observed_at)

    def body(self):
        return dict(schema="skeleton.game_ai.round_evolution_receipt.v1",
                    round_number=self.round_number,
                    action_type=self.action_type,
                    project_task_digest=self.project_task_digest,
                    input_chain_digest=self.input_chain_digest,
                    report_digest=self.report_digest,
                    external_evidence_roots=list(self.external_evidence_roots),
                    status=self.status,
                    research_reference_only=self.research_reference_only,
                    reviewer_id=self.reviewer_id,observed_at=self.observed_at)

    def payload(self):
        return dict(self.body(),signature=self.signature)

    @property
    def digest(self):
        return canonical_digest(self.payload())


def sign_round_receipt(row:EvolutionRoundReceipt,reviewer:TrustedCompetitionJudge):
    if not isinstance(row,EvolutionRoundReceipt) or reviewer.judge_id!=row.reviewer_id:
        raise ThreatRadarError("cannot forge another round actor")
    return replace(row,signature=_mac(row.body(),reviewer.key))


@dataclass(frozen=True,slots=True)
class EvolutionRun:
    task:OriginalTaskFocus
    rounds:tuple[EvolutionRoundReceipt,...]
    shadow_approved_for_stage: bool
    user_model_activation_granted: bool=False

    @property
    def digest(self):return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_ai.18round_evolution.v1",
                    task=self.task.payload(),
                    rounds=[x.payload() for x in self.rounds],
                    next_round=(len(self.rounds)+3 if len(self.rounds)<16 else None),
                    shadow_approved_for_stage=self.shadow_approved_for_stage,
                    user_model_activation_granted=self.user_model_activation_granted,
                    foundation_llm_weights_changed=False,
                    model_installed=False,
                    unattended_background_daemon=False)


def begin_18round_evolution(task:OriginalTaskFocus,*,authorized:bool):
    if not authorized:raise PermissionError("original game AI evolution needs owner consent")
    if not isinstance(task,OriginalTaskFocus):
        raise ThreatRadarError("exact real user task and current game context required")
    return EvolutionRun(task,(),False)


def accept_round(
    state:EvolutionRun,receipt:EvolutionRoundReceipt,
    signer:TrustedCompetitionJudge,*,
    authorized:bool,
    host_idle:Callable[[],bool]|None=None,
    thermal_safe:Callable[[],bool]|None=None,
    host_consented:bool=False,
    shadow_proof:SandboxVerification|None=None,
    shadow_verifier:TrustedCompetitionJudge|None=None,
)->EvolutionRun:
    if not authorized:raise PermissionError("no involuntary background AI game learning")
    if (not isinstance(state,EvolutionRun)
            or not isinstance(receipt,EvolutionRoundReceipt)
            or not isinstance(signer,TrustedCompetitionJudge)
            or len(state.rounds)>=16):
        raise ThreatRadarError("source-bound uncompleted round required")
    expected=3+len(state.rounds)
    if (receipt.round_number!=expected
            or receipt.project_task_digest!=state.task.task_digest
            or receipt.input_chain_digest!=(state.task.task_digest if not state.rounds
                                             else state.rounds[-1].digest)
            or receipt.reviewer_id!=signer.judge_id
            or not hmac.compare_digest(receipt.signature,
                                        _mac(receipt.body(),signer.key))):
        raise ThreatRadarError("stale, skipped or forged round transition")
    if state.rounds and _date(receipt.observed_at)<=_date(state.rounds[-1].observed_at):
        raise ThreatRadarError("no old research can be replayed as a new round")
    if expected in IDLE_ROUNDS:
        if (host_consented is not True or
                not callable(host_idle) or not callable(thermal_safe)):
            raise PermissionError("idle-only rounds require explicit host/thermal/consent probes")
        try:
            ready=host_idle()
            cool=thermal_safe()
        except Exception as exc:
            raise ThreatRadarError("host idle or thermal probe failed closed") from exc
        if type(ready) is not bool or type(cool) is not bool or not ready or not cool:
            raise ThreatRadarError("user active or device unsafe: defer background round")
        if receipt.status not in {"idle_assessed","blocked"}:
            raise ThreatRadarError("idle-only round cannot claim model installation")
    elif receipt.status=="idle_assessed":
        raise ThreatRadarError("foreground rounds may not claim idle evidence")
    if expected in SHADOW_ROUNDS:
        if receipt.status=="verified_sandbox":
            if (not isinstance(shadow_proof,SandboxVerification)
                    or not shadow_proof.permission_to_stage or
                    shadow_proof.blockers or not shadow_proof.strict_measured_gain
                    or shadow_proof.model_activation_performed
                    or not isinstance(shadow_verifier,TrustedCompetitionJudge)
                    or shadow_verifier.judge_id==signer.judge_id
                    or shadow_proof.verifier_id!=shadow_verifier.judge_id
                    or not hmac.compare_digest(
                        shadow_proof.signature,
                        _mac(shadow_proof.signed_body(),shadow_verifier.key))
                    or shadow_proof.digest!=receipt.report_digest):
                raise ThreatRadarError("only actual verified shadow sandbox is eligible for a stage")
        elif receipt.status not in {"shadow_queued","blocked","reviewed"}:
            raise ThreatRadarError("shadow round requires queue or sandbox result")
    elif receipt.status=="verified_sandbox":
        raise ThreatRadarError("crawler-only round cannot attest model quality")
    # Stage flags are informational; the actual model registry remains the
    # sole authority for staging, six reviews, usage/idle and activation.
    stage=state.shadow_approved_for_stage or (
        receipt.status=="verified_sandbox" and shadow_proof is not None
        and shadow_proof.permission_to_stage)
    return replace(state,rounds=state.rounds+(receipt,),
                   shadow_approved_for_stage=bool(stage))


@dataclass(frozen=True,slots=True)
class CrawlerDestination:
    source_id: str
    url: str
    source_revision_digest: str
    canonical_rights_digest: str
    reviewed_metadata_digest: str
    license_use: str

    def __post_init__(self):
        _id(self.source_id,"reviewed crawler publisher")
        for digest in (self.source_revision_digest,self.canonical_rights_digest,
                       self.reviewed_metadata_digest):_sha(digest)
        if self.license_use not in {"facts_ideas_reference","explicit_model_train"}:
            raise ThreatRadarError("source use is not automatically training consent")
        url=urlsplit(self.url)
        if (url.scheme!="https" or not url.hostname or url.username or url.password
                or url.port not in (None,443) or len(self.url)>2048
                or any(c in self.url for c in "\r\n\t\\")
                or url.fragment or url.hostname.lower() in {"localhost","localhost.localdomain"}
                or url.hostname.lower().endswith((".local",".internal",".localhost"))):
            raise ThreatRadarError("only explicit source-owned public HTTPS research destinations")
        try:
            ip_address(url.hostname)
        except ValueError:
            if "." not in url.hostname:raise ThreatRadarError("public fully-qualified domain required")
        else:
            raise ThreatRadarError("literal IP hosts require separate external network safety review")
    def payload(self):
        return dict(source_id=self.source_id,url=self.url,
                    source_revision_digest=self.source_revision_digest,
                    canonical_rights_digest=self.canonical_rights_digest,
                    reviewed_metadata_digest=self.reviewed_metadata_digest,
                    license_use=self.license_use,
                    authorized_to_fetch=False,robots_terms_checked_by_transport=False)


@dataclass(frozen=True,slots=True)
class CrawlerLogObservation:
    source_id: str
    destination_review_digest: str
    response_content_digest: str
    sanitized_log_digest: str
    verified_revision_digest: str
    result_kind: str
    rights: str
    reviewer_id: str
    signature: str

    def __post_init__(self):
        _id(self.source_id,"lawful crawler evidence")
        for d in (self.destination_review_digest,self.response_content_digest,
                  self.sanitized_log_digest,self.verified_revision_digest,
                  self.signature):_sha(d)
        _id(self.reviewer_id,"crawler evidence reviewer")
        if self.result_kind not in {"source_metadata","verified_research","crawl_failure"}:
            raise ThreatRadarError("finite honest crawler outcome required")
        if self.rights not in {"reference_only","training_cleared","unknown"}:
            raise ThreatRadarError("explicit separate research and gradient permission")
    def body(self):
        return dict(source_id=self.source_id,
                    destination_review_digest=self.destination_review_digest,
                    response_content_digest=self.response_content_digest,
                    sanitized_log_digest=self.sanitized_log_digest,
                    verified_revision_digest=self.verified_revision_digest,
                    result_kind=self.result_kind,rights=self.rights,
                    reviewer_id=self.reviewer_id)

def sign_crawler_log(row:CrawlerLogObservation,judge:TrustedCompetitionJudge):
    if row.reviewer_id!=judge.judge_id:raise ThreatRadarError("source log reviewer missing")
    return replace(row,signature=_mac(row.body(),judge.key))


def qualify_crawler_log_handoff(
    destinations:tuple[CrawlerDestination,...],
    logs:tuple[CrawlerLogObservation,...],
    reviewers:tuple[TrustedCompetitionJudge,...],*,
    authorized:bool,
)->dict:
    if not authorized:raise PermissionError("crawler logs need explicit verified project custody")
    if (type(destinations) is not tuple or type(logs) is not tuple or
            not 1<=len(destinations)<=128 or not 1<=len(logs)<=128 or
            len({x.source_id for x in destinations})!=len(destinations)
            or any(not isinstance(x,CrawlerDestination) for x in destinations)
            or any(not isinstance(x,CrawlerLogObservation) for x in logs)):
        raise ThreatRadarError("complete bounded reviewed HTTPS destinations and logs required")
    by_id={x.source_id:x for x in destinations}
    keyring={k.judge_id:k for k in reviewers}
    seen=set();approved=[];research=[]
    for row in logs:
        dest=by_id.get(row.source_id);key=keyring.get(row.reviewer_id)
        if row.source_id in seen or not dest or not key or not hmac.compare_digest(
                row.signature,_mac(row.body(),key.key)):
            raise ThreatRadarError("unreviewed, repeated or fake crawler log")
        seen.add(row.source_id)
        if (row.destination_review_digest!=dest.reviewed_metadata_digest
                or row.verified_revision_digest!=dest.source_revision_digest):
            raise ThreatRadarError("crawler log was collected from an obsolete unverified source")
        if row.result_kind=="verified_research":
            research.append(row.source_id)
            if row.rights=="training_cleared" and dest.license_use=="explicit_model_train":
                approved.append(row.source_id)
    return dict(schema="skeleton.game_ai.sanitized_crawler_shadow_handoff.v1",
                reviewed_sources=sorted(seen),
                research_admissible_sources=sorted(research),
                potential_train_rights_sources=sorted(approved),
                no_raw_crawled_text_or_urls_sent_to_weights=True,
                actual_wiki_recheck_still_required=True,
                source_review_receipts=[canonical_digest(x.body()) for x in logs])


@dataclass(frozen=True,slots=True)
class EighteenRoundFrontier:
    task_digest: str
    completed_rounds: tuple[int,...]
    pending_rounds: tuple[dict,...]
    total_gate_count: int
    potentially_shadow_eligible: bool
    actually_installed: bool=False

    def payload(self):
        return dict(schema="skeleton.game_ai.18round_roadmap.v1",
                    task_digest=self.task_digest,
                    completed_rounds=list(self.completed_rounds),
                    pending_rounds=list(self.pending_rounds),
                    total_gate_count=self.total_gate_count,
                    potentially_shadow_eligible=self.potentially_shadow_eligible,
                    actually_installed=self.actually_installed)


def report_remaining_rounds(state:EvolutionRun,*,authorized:bool)->EighteenRoundFrontier:
    if not authorized:raise PermissionError("AI evolution backlog inspection requires operator")
    if not isinstance(state,EvolutionRun):raise ThreatRadarError("canonical progression required")
    remaining=tuple(dict(round_number=i,title=name,
                         expectation=objective,verification_gate=gate,
                         background_only=i in IDLE_ROUNDS,
                         automatic_weight_change=False)
                    for i,name,objective,gate in ROUND_DESCRIPTIONS[len(state.rounds):])
    return EighteenRoundFrontier(
        state.task.task_digest,tuple(x.round_number for x in state.rounds),
        remaining,len(remaining),
        state.shadow_approved_for_stage,False)


def next_dragon_adjacency_mission(
    task:OriginalTaskFocus,prior_topics:tuple[str,...],
    unresolved_gap_topics:tuple[str,...],*,
    authorized:bool,consent:bool,max_topics:int=20,
)->ResearchMission:
    if not authorized or not consent:
        raise PermissionError("round 18 recrawl must be explicitly scoped and consented")
    if (not isinstance(task,OriginalTaskFocus) or
            type(prior_topics) is not tuple or type(unresolved_gap_topics) is not tuple
            or not 1<=len(unresolved_gap_topics)<=32 or
            type(max_topics) is not int or not 1<=max_topics<=20):
        raise ThreatRadarError("bounded unresolved original-game research targets")
    base=set(prior_topics)
    normalized=[]
    for topic in unresolved_gap_topics:
        if not isinstance(topic,str) or not 2<=len(topic)<=96 or any(
                not (c.isalnum() or c in " _-") for c in topic):
            raise ThreatRadarError("no crawler prompt injection or URL/secret in topic")
        normalized.append(" ".join(topic.lower().split()))
    unique=[topic for topic in dict.fromkeys(normalized) if topic not in base]
    if not unique:raise ThreatRadarError("adjacent topics need genuinely new unresolved gaps")
    interests=tuple(ResearchInterest(
        f"original video game {task.genre} {task.era} {topic} independent study",
        round(max(0.30,0.98-0.025*i),3))
        for i,topic in enumerate(unique[:max_topics]))
    return plan_research(task.original_id,interests,authorized=True,
                         geographic_consent=False,
                         policy=MissionPolicy(max_interests=max_topics,
                                              max_queries=4*max_topics,
                                              include_places=False))

__all__=["ROUND_DESCRIPTIONS","EvolutionRoundReceipt","sign_round_receipt",
         "EvolutionRun","begin_18round_evolution","accept_round",
         "CrawlerDestination","CrawlerLogObservation","sign_crawler_log",
         "qualify_crawler_log_handoff","EighteenRoundFrontier",
         "report_remaining_rounds","next_dragon_adjacency_mission"]
