"""Competitive title superiority gate: objectively outwork a rival, not imitate it.

A rival's published score is NOT enough. Comparison uses the same predeclared
scenario/population/protocol, independent evaluators, uncertainty intervals,
freshness and protected-axis nonregression. Priority work is derived from
measured gaps; no copied characters, levels, visual style or names become
implementation instructions. Release remains under the canonical original
game/consumer rights and QA authorities, never this advisory gate.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass,replace
from datetime import datetime
import hashlib
import hmac
import re

from .contracts import QUALITY_AXES,PROTECTED_AXES,canonical_digest
from .competitive_title_radar import (
    PlannedOriginalTitle,ThreatAssessment,ThreatRadarError,_id,_sha,_date,_tags,
)
from .rights import RightsLedger

ALL_AXES=frozenset(QUALITY_AXES)
CORE_AXES=frozenset({
    "player_value","fun_engagement","originality","mechanical_depth",
    "clarity_readability","aesthetic_coherence","technical_correctness",
    "performance","accessibility","replayability","rights_provenance_safety",
})
POLISH_AXES=frozenset({
    "clarity_readability","aesthetic_coherence","performance",
    "accessibility","maintainability","technical_correctness",
    "narrative_coherence",
})


def _bp(value,name):
    if type(value) is not int or not 0<=value<=10000:
        raise ThreatRadarError(f"{name} must be integer basis points")
    return value


@dataclass(frozen=True,slots=True)
class TrustedCompetitionJudge:
    """Operator-supplied HMAC verifier: possession is checked, human identity not."""

    judge_id: str
    key: bytes

    def __post_init__(self):
        _id(self.judge_id,"trusted evaluator")
        if type(self.key) is not bytes or len(self.key)<32:
            raise ThreatRadarError("independent benchmark signer requires >=256 bit secret")


def _mac(body,key):
    return hmac.new(key,canonical_digest(body).encode("ascii"),
                    hashlib.sha256).hexdigest()


@dataclass(frozen=True,slots=True)
class VerifiedQualitySample:
    """Operator-supplied score envelope; judge identity alone is not a signature."""

    subject_id: str
    axis: str
    score_bp: int
    lower_bp: int
    upper_bp: int
    protocol_digest: str
    scenario_digest: str
    population_digest: str
    evidence_digest: str
    judge_id: str
    observed_at: str
    sample_count: int
    platform: str
    signature: str

    def __post_init__(self):
        _id(self.subject_id,"subject")
        if self.axis not in ALL_AXES:
            raise ThreatRadarError("quality metric outside canonical game quality axes")
        for n in ("score_bp","lower_bp","upper_bp"):
            _bp(getattr(self,n),n)
        if not self.lower_bp<=self.score_bp<=self.upper_bp:
            raise ThreatRadarError("measurement uncertainty must contain observed score")
        for n in ("protocol_digest","scenario_digest","population_digest",
                  "evidence_digest"):
            _sha(getattr(self,n),n)
        _id(self.judge_id,"judge")
        _id(self.platform,"platform")
        _sha(self.signature,"benchmark signature")
        _date(self.observed_at)
        if type(self.sample_count) is not int or not 10<=self.sample_count<=1000000:
            raise ThreatRadarError("quality needs independent repeatable evaluation, n >=10")

    def signed_body(self):
        return dict(
            schema="skeleton.game_builder.quality_measurement.v1",
            subject_id=self.subject_id,axis=self.axis,
            score_bp=self.score_bp,lower_bp=self.lower_bp,upper_bp=self.upper_bp,
            protocol_digest=self.protocol_digest,
            scenario_digest=self.scenario_digest,
            population_digest=self.population_digest,
            evidence_digest=self.evidence_digest,
            judge_id=self.judge_id,observed_at=self.observed_at,
            sample_count=self.sample_count,platform=self.platform)

    def payload(self):
        return dict(self.signed_body(),signature=self.signature)


def sign_competitive_sample(sample: VerifiedQualitySample,
                            judge: TrustedCompetitionJudge):
    if not isinstance(sample,VerifiedQualitySample) or not isinstance(judge,TrustedCompetitionJudge):
        raise ThreatRadarError("typed benchmark sample and evaluator key required")
    if judge.judge_id!=sample.judge_id:
        raise ThreatRadarError("judge key does not match declared subject")
    return replace(sample,signature=_mac(sample.signed_body(),judge.key))


@dataclass(frozen=True,slots=True)
class OriginalIdentityReview:
    original_id: str
    candidate_digest: str
    canonical_design_digest: str
    retained_pillars: tuple[str,...]
    measured_originality_bp: int
    max_similarity_risk_bp: int
    independent_originality_evidence: str
    reviewer_id: str
    reviewed_at: str
    human_reviewed: bool
    signature: str

    def __post_init__(self):
        _id(self.original_id)
        for n in ("candidate_digest","canonical_design_digest",
                  "independent_originality_evidence"):
            _sha(getattr(self,n),n)
        _tags(self.retained_pillars,"retained_pillars",3,32)
        _bp(self.measured_originality_bp,"originality")
        _bp(self.max_similarity_risk_bp,"similarity risk")
        _id(self.reviewer_id,"independent reviewer")
        _date(self.reviewed_at)
        if type(self.human_reviewed) is not bool:
            raise ThreatRadarError("explicit independent review status required")
        _sha(self.signature,"originality reviewer signature")

    def signed_body(self):
        return dict(
            schema="skeleton.game_builder.originality_review.v1",
            original_id=self.original_id,candidate_digest=self.candidate_digest,
            canonical_design_digest=self.canonical_design_digest,
            retained_pillars=list(self.retained_pillars),
            measured_originality_bp=self.measured_originality_bp,
            max_similarity_risk_bp=self.max_similarity_risk_bp,
            independent_originality_evidence=self.independent_originality_evidence,
            reviewer_id=self.reviewer_id,reviewed_at=self.reviewed_at,
            human_reviewed=self.human_reviewed)

    def payload(self):
        return dict(self.signed_body(),signature=self.signature)


def sign_identity_review(review: OriginalIdentityReview,
                         judge: TrustedCompetitionJudge):
    if not isinstance(review,OriginalIdentityReview) or not isinstance(judge,TrustedCompetitionJudge):
        raise ThreatRadarError("typed independent originality-review signature required")
    if judge.judge_id!=review.reviewer_id:
        raise ThreatRadarError("originality signer identity mismatch")
    return replace(review,signature=_mac(review.signed_body(),judge.key))


@dataclass(frozen=True,slots=True)
class SuperiorityStandard:
    competitive_margin_bp: int = 150
    minimum_independent_judges: int = 2
    min_cohort_size: int = 10
    max_measurement_age_days: int = 180
    max_risk_bp: int = 1800
    required_axes: tuple[str,...] = tuple(sorted(CORE_AXES))
    preserve_existing_target: bool = True

    def __post_init__(self):
        if (any(type(getattr(self,n)) is not int for n in (
                "competitive_margin_bp","minimum_independent_judges",
                "min_cohort_size","max_measurement_age_days","max_risk_bp"))
                or not 50<=self.competitive_margin_bp<=2000
                or not 2<=self.minimum_independent_judges<=8
                or not 10<=self.min_cohort_size<=100000
                or not 1<=self.max_measurement_age_days<=365
                or not 0<=self.max_risk_bp<=3000
                or type(self.preserve_existing_target) is not bool):
            raise ThreatRadarError("invalid competitive non-regression standard")
        if (type(self.required_axes) is not tuple or not set(CORE_AXES).issubset(
                self.required_axes) or len(set(self.required_axes))!=len(self.required_axes)
                or tuple(sorted(self.required_axes))!=self.required_axes
                or set(self.required_axes)-ALL_AXES):
            raise ThreatRadarError("must retain all core and protected competitive quality gates")

    def payload(self):
        return dict(
            competitive_margin_bp=self.competitive_margin_bp,
            minimum_independent_judges=self.minimum_independent_judges,
            min_cohort_size=self.min_cohort_size,
            max_measurement_age_days=self.max_measurement_age_days,
            max_risk_bp=self.max_risk_bp,
            required_axes=list(self.required_axes),
            preserve_existing_target=self.preserve_existing_target)


@dataclass(frozen=True,slots=True)
class DeliveryDemand:
    original_id: str
    rival_id: str
    axis: str
    target_floor_bp: int
    observed_original_lower_bp: int | None
    observed_rival_upper_bp: int | None
    priority: int
    required_proof: str
    original_direction: str
    blocked_reason: str | None

    def payload(self):
        return dict(
            original_id=self.original_id,rival_id=self.rival_id,axis=self.axis,
            target_floor_bp=self.target_floor_bp,
            observed_original_lower_bp=self.observed_original_lower_bp,
            observed_rival_upper_bp=self.observed_rival_upper_bp,
            priority=self.priority,required_proof=self.required_proof,
            original_direction=self.original_direction,
            blocked_reason=self.blocked_reason,
            no_reimplementation_of_competitor_expression=True)


@dataclass(frozen=True,slots=True)
class CompetitiveDeliveryReport:
    original_id: str
    rival_id: str
    as_of: str
    watch_digest: str
    baseline_design_digest: str
    competitor_status: str
    quality_results: tuple[dict,...]
    demands: tuple[DeliveryDemand,...]
    identity_blockers: tuple[str,...]
    qualified_to_claim_superiority: bool

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.competitive_delivery.v1",
            original_id=self.original_id,rival_id=self.rival_id,as_of=self.as_of,
            watch_digest=self.watch_digest,
            baseline_design_digest=self.baseline_design_digest,
            competitor_status=self.competitor_status,
            quality_results=list(self.quality_results),
            demands=[d.payload() for d in self.demands],
            identity_blockers=list(self.identity_blockers),
            qualified_to_claim_superiority=self.qualified_to_claim_superiority,
            **{"no_claim_of_consumer_release":True,
               "no_assumed_independent_judge_credentials":True,
               "verified_operator_configured_hmac_evaluator_keys":True,
               "no_right_to_copy_competing_game":True,
               "requires_canonical_release_assurance":True})


def _identity_blockers(planned, proof, rights, standard, as_of, trusted_identity_reviewer):
    reasons=[]
    if proof is None:
        return ["no_independent_original_identity_review"]
    if not isinstance(proof,OriginalIdentityReview):
        raise ThreatRadarError("typed independent originality evidence required")
    if (not isinstance(trusted_identity_reviewer,TrustedCompetitionJudge)
            or trusted_identity_reviewer.judge_id!=proof.reviewer_id
            or not hmac.compare_digest(proof.signature,_mac(
                proof.signed_body(),trusted_identity_reviewer.key))):
        reasons.append("missing_or_forged_independent_originality_signature")
    if proof.original_id!=planned.title_id:
        reasons.append("wrong_title_originality_review")
    if proof.canonical_design_digest!=planned.design_digest:
        reasons.append("changed_original_design_requires_new_review")
    if set(proof.retained_pillars)!=set(planned.identity_pillars):
        reasons.append("lost_originality_pillars")
    if proof.measured_originality_bp<planned.originality_floor_bp:
        reasons.append("originality_below_immutable_floor")
    if proof.max_similarity_risk_bp>standard.max_risk_bp:
        reasons.append("unresolved_near_clone_risk")
    if not proof.human_reviewed or proof.reviewer_id==planned.title_id:
        reasons.append("unapproved_or_non_independent_identity_review")
    if _date(proof.reviewed_at)>_date(as_of):
        reasons.append("future_identity_review")
    if (_date(as_of)-_date(proof.reviewed_at)).days>standard.max_measurement_age_days:
        reasons.append("stale_identity_review")
    if rights.unresolved_high_risk(artifact_digest=proof.candidate_digest):
        reasons.append("unresolved_canonical_similarity_rights_gate")
    return reasons


def compare_competitive_delivery(
    planned: PlannedOriginalTitle,
    assessment: ThreatAssessment,
    measurements: tuple[VerifiedQualitySample,...],
    rights: RightsLedger,*,
    as_of: str,authorized: bool,
    identity: OriginalIdentityReview|None=None,
    trusted_identity_reviewer: TrustedCompetitionJudge|None=None,
    trusted_judges: tuple[TrustedCompetitionJudge,...]=(),
    standard: SuperiorityStandard=SuperiorityStandard(),
    preceding: CompetitiveDeliveryReport|None=None,
)->CompetitiveDeliveryReport:
    if not authorized:
        raise PermissionError("objective competitive game benchmarks require reviewer authority")
    if (not isinstance(planned,PlannedOriginalTitle)
            or not isinstance(assessment,ThreatAssessment)
            or not isinstance(rights,RightsLedger)
            or type(measurements) is not tuple or len(measurements)>4096
            or any(not isinstance(x,VerifiedQualitySample) for x in measurements)
            or not isinstance(standard,SuperiorityStandard)):
        raise ThreatRadarError("typed original title, threat, scores and rights required")
    date=_date(as_of)
    if (assessment.original_id!=planned.title_id
            or assessment.status!="enemy"
            or _date(assessment.as_of)>date):
        raise ThreatRadarError("only corroborated current enemy benchmarks create outperform obligations")
    if preceding is not None and (
            not isinstance(preceding,CompetitiveDeliveryReport)
            or preceding.original_id!=planned.title_id
            or preceding.rival_id!=assessment.rival_id
            or preceding.baseline_design_digest!=planned.design_digest
            or _date(preceding.as_of)>=date):
        raise ThreatRadarError("previous title/standard evidence inconsistent or time rolled back")
    if (type(trusted_judges) is not tuple or
            any(not isinstance(x,TrustedCompetitionJudge) for x in trusted_judges)
            or len({x.judge_id for x in trusted_judges})!=len(trusted_judges)):
        raise ThreatRadarError("distinct, operator-trusted quality benchmark keys required")
    trusted={x.judge_id:x for x in trusted_judges}
    # Protocol, population and platform MUST match *per axis*. Diverse
    # judges within a protocol are required; score means are never a proof.
    records=defaultdict(lambda:defaultdict(list))
    seen=set()
    for row in measurements:
        judge=trusted.get(row.judge_id)
        if judge is None or not hmac.compare_digest(
                row.signature,_mac(row.signed_body(),judge.key)):
            raise ThreatRadarError("missing or invalid exact-sample quality benchmark signature")
        if row.subject_id not in {planned.title_id,assessment.rival_id}:
            raise ThreatRadarError("unrelated competitor measurement")
        if row.platform not in planned.platforms:
            raise ThreatRadarError("tested platform outside original game plan")
        if _date(row.observed_at)>date or (
                date-_date(row.observed_at)).days>standard.max_measurement_age_days:
            raise ThreatRadarError("future/stale quality comparison cannot be counted")
        identity_key=(row.subject_id,row.axis,row.judge_id,
                      row.protocol_digest,row.scenario_digest,
                      row.population_digest,row.platform)
        if identity_key in seen:
            raise ThreatRadarError("replayed measurement from same judge cannot inflate evidence")
        seen.add(identity_key)
        records[row.axis][row.subject_id].append(row)
    identity_blockers=_identity_blockers(
        planned,identity,rights,standard,as_of,trusted_identity_reviewer)
    quality=[]
    demands=[]
    for axis in standard.required_axes:
        ours=records[axis][planned.title_id]
        theirs=records[axis][assessment.rival_id]
        blockers=[]
        if len({x.judge_id for x in ours})<standard.minimum_independent_judges:
            blockers.append("insufficient_own_independent_judges")
        if len({x.judge_id for x in theirs})<standard.minimum_independent_judges:
            blockers.append("insufficient_rival_independent_judges")
        if any(x.sample_count<standard.min_cohort_size for x in ours+theirs):
            blockers.append("insufficient_benchmark_sample_count")
        protocols={(x.protocol_digest,x.scenario_digest,
                    x.population_digest,x.platform) for x in ours+theirs}
        if len(protocols)!=1:
            blockers.append("protocol_scenario_platform_or_cohort_mismatch")
        # No optional metric padding; no unobserved value equals a real 0.
        our_low=min((x.lower_bp for x in ours),default=None)
        competitor_high=max((x.upper_bp for x in theirs),default=None)
        prior_target=next((d.target_floor_bp for d in preceding.demands
                           if d.axis==axis),0) if preceding else 0
        desired=max(prior_target,(competitor_high or 0)+standard.competitive_margin_bp)
        unreachable=desired>10000
        target=min(10000,desired)
        if unreachable:
            blockers.append("superiority_margin_unattainable_under_current_metric")
        ahead=(not blockers and our_low is not None
               and competitor_high is not None
               and our_low>=target)
        result=dict(
            axis=axis,status="outperformed" if ahead else
            "unverifiable" if blockers else "improvement_required",
            original_conservative_lower_bp=our_low,
            competitor_conservative_upper_bp=competitor_high,
            target_floor_bp=target,
            prior_target_floor_bp=prior_target,
            blocker_codes=sorted(set(blockers)),
            own_independent_judges=len({x.judge_id for x in ours}),
            rival_independent_judges=len({x.judge_id for x in theirs}),
            comparison_protocol_digest=(
                next(iter(protocols))[0] if len(protocols)==1 else None),
            protected_axis=axis in PROTECTED_AXES,
            sufficient_evidence=not blockers)
        quality.append(result)
        if not ahead:
            gap=max(0,target-(our_low if our_low is not None else 0))
            # Do NOT populate a backlog with a competitor's level, soundtrack,
            # characters, artwork, exact mechanics or protected expressions.
            # Every lane must preserve original identity pillars.
            direction=(
                f"Improve original {axis} through the project's distinct "
                f"{', '.join(planned.identity_pillars)} pillars; "
                "invent an independent design solution and measure it under "
                "the same heldout protocol, platforms and player population."
            )
            priority=min(100000,20*gap+(30000 if axis in PROTECTED_AXES else 0)
                         +(15000 if axis in POLISH_AXES else 0)
                         +(10000 if blockers else 0))
            demands.append(DeliveryDemand(
                planned.title_id,assessment.rival_id,axis,target,
                our_low,competitor_high,priority,
                "independent_gameplay_replay_plus_blind_quality_and_rights_review",
                direction,";".join(sorted(set(blockers))) or None))
    if not standard.required_axes:
        raise ThreatRadarError("full game-quality standard required")
    demands.sort(key=lambda d:(-d.priority,d.axis))
    return CompetitiveDeliveryReport(
        planned.title_id,assessment.rival_id,as_of,
        canonical_digest(assessment.payload()),
        planned.design_digest,assessment.status,
        tuple(quality),tuple(demands),tuple(sorted(set(identity_blockers))),
        not demands and not identity_blockers)


def ratchet_superiority_standard(
    old: SuperiorityStandard,new: SuperiorityStandard,*,
    authorized: bool,
)->SuperiorityStandard:
    if not authorized:
        raise PermissionError("competition bar requires operator authority")
    if (not isinstance(old,SuperiorityStandard)
            or not isinstance(new,SuperiorityStandard)):
        raise ThreatRadarError("typed old and new competition standards required")
    if (new.competitive_margin_bp<old.competitive_margin_bp
            or new.minimum_independent_judges<old.minimum_independent_judges
            or new.min_cohort_size<old.min_cohort_size
            or new.max_measurement_age_days>old.max_measurement_age_days
            or new.max_risk_bp>old.max_risk_bp
            or not set(old.required_axes).issubset(new.required_axes)
            or not new.preserve_existing_target):
        raise ThreatRadarError("cannot lower any protected, quality or originality ratchet")
    return new


__all__=["TrustedCompetitionJudge","sign_competitive_sample",
         "sign_identity_review","VerifiedQualitySample","OriginalIdentityReview","SuperiorityStandard",
         "DeliveryDemand","CompetitiveDeliveryReport",
         "compare_competitive_delivery","ratchet_superiority_standard"]
