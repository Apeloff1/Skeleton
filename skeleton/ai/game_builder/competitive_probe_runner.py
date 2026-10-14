"""Execute deterministic scoring of genuine recorded rival/original playtest trials.

The runner consumes externally captured *original telemetry scores*, one replay
digest per session and explicit normal/fault conditions. It calculates a
conservative 95% normal-approximation estimate over each condition and returns
the worse (adversarial) scenario for every game. No scores are fabricated from
missing video, no player recording is captured, no competitor code is run.

Metric adapters must independently transform actual hardware/gameplay/audio/
story telemetry into predeclared bounded scores before calling this function.
It produces an HMAC measurement receipt whose integrity can be checked by
the existing four-domain/anecstry scorers.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt,ceil,floor

from .contracts import canonical_digest
from .competitive_title_radar import ThreatRadarError,_id,_sha,_date
from .competitive_deep_analysis import (
    ScriptedProbe,FacetMeasurement,sign_facet_measurement,
)
from .competitive_delivery_gate import TrustedCompetitionJudge

CONDITIONS=("adversarial","normal")


@dataclass(frozen=True,slots=True)
class RecordedProbeTrial:
    subject_id: str
    script_digest: str
    evaluator_id: str
    play_session_digest: str
    build_digest: str
    participant_token_digest: str
    condition: str
    score_bp: int
    observed_at: str
    telemetry_evidence_digest: str

    def __post_init__(self):
        for name in ("subject_id","evaluator_id"):
            _id(getattr(self,name),name)
        for name in ("script_digest","play_session_digest","build_digest",
                     "participant_token_digest","telemetry_evidence_digest"):
            _sha(getattr(self,name),name)
        if self.condition not in CONDITIONS:
            raise ThreatRadarError("normal and adversarial/fault controls required")
        if type(self.score_bp) is not int or not 0<=self.score_bp<=10000:
            raise ThreatRadarError("reported original telemetry must be bounded basis points")
        _date(self.observed_at)

    def payload(self):
        return dict(
            schema="skeleton.game_builder.recorded_probe_trial.v1",
            subject_id=self.subject_id,script_digest=self.script_digest,
            evaluator_id=self.evaluator_id,
            play_session_digest=self.play_session_digest,
            build_digest=self.build_digest,
            participant_token_digest=self.participant_token_digest,
            condition=self.condition,score_bp=self.score_bp,
            observed_at=self.observed_at,
            telemetry_evidence_digest=self.telemetry_evidence_digest,
            manual_originality_or_licensing_clearance_not_inferred=True)


@dataclass(frozen=True,slots=True)
class ProbeExecutionReceipt:
    script_digest: str
    subject_id: str
    evaluator_id: str
    outcome: FacetMeasurement
    condition_counts: tuple[tuple[str,int],...]
    condition_means_bp: tuple[tuple[str,int],...]
    raw_trial_evidence_root: str
    automated_real_world_capture_performed: bool=False

    def payload(self):
        return dict(
            schema="skeleton.game_builder.probe_execution.v1",
            script_digest=self.script_digest,subject_id=self.subject_id,
            evaluator_id=self.evaluator_id,
            outcome=self.outcome.payload(),
            condition_counts=[list(x) for x in self.condition_counts],
            condition_means_bp=[list(x) for x in self.condition_means_bp],
            raw_trial_evidence_root=self.raw_trial_evidence_root,
            automated_real_world_capture_performed=self.automated_real_world_capture_performed,
            actual_game_assets_reproduced=False,
            operator_source_telemetry_verification_still_required=True)


def _score_interval(rows):
    scores=[x.score_bp for x in rows]
    n=len(scores)
    if n<5:
        raise ThreatRadarError("at least five unique real sessions per adversarial control condition")
    average=sum(scores)/n
    if n==1:
        deviation=0
    else:
        variance=sum((x-average)**2 for x in scores)/(n-1)
        deviation=1.96*sqrt(variance/n)
    return (int(round(average)),max(0,int(floor(average-deviation))),
            min(10000,int(ceil(average+deviation))))


def score_recorded_probe_batch(
    script: ScriptedProbe,
    trials: tuple[RecordedProbeTrial,...],
    judge: TrustedCompetitionJudge, *,
    subject_id: str,
    as_of: str,
    authorized: bool,
    source_capture_consent: bool,
    independent_telemetry_reviewed: bool,
    min_trials: int=20,
    max_age_days: int=180,
)->ProbeExecutionReceipt:
    if not authorized:
        raise PermissionError("signed replay evaluation requires independent operator authority")
    if not source_capture_consent or not independent_telemetry_reviewed:
        raise PermissionError("consent, rights and actual independently reviewed probe telemetry required")
    if (not isinstance(script,ScriptedProbe)
            or not isinstance(judge,TrustedCompetitionJudge)
            or type(trials) is not tuple or not 10<=len(trials)<=10000
            or any(not isinstance(x,RecordedProbeTrial) for x in trials)
            or type(min_trials) is not int or not 10<=min_trials<=10000
            or len(trials)<min_trials
            or type(max_age_days) is not int or not 1<=max_age_days<=365):
        raise ThreatRadarError("bounded full-scenario real game replay required")
    _id(subject_id,"played title")
    now=_date(as_of)
    conditions={c:[] for c in CONDITIONS}
    unique_sessions=set()
    unique_players=set()
    build_digests=set()
    for trial in trials:
        if (trial.subject_id!=subject_id
                or trial.evaluator_id!=judge.judge_id
                or trial.script_digest!=script.digest):
            raise ThreatRadarError("unexpected title, script or evaluator replay")
        if (trial.play_session_digest in unique_sessions
                or trial.participant_token_digest in unique_players):
            raise ThreatRadarError("repeated session/player cannot inflate trial sample size")
        unique_sessions.add(trial.play_session_digest)
        unique_players.add(trial.participant_token_digest)
        build_digests.add(trial.build_digest)
        observed=_date(trial.observed_at)
        if observed>now or (now-observed).days>max_age_days:
            raise ThreatRadarError("future or stale playtest telemetry")
        conditions[trial.condition].append(trial)
    if len(build_digests)!=1:
        raise ThreatRadarError("mixing builds makes game competition statistically uninterpretable")
    intervals={}
    for name in CONDITIONS:
        intervals[name]=_score_interval(conditions[name])
    # Worst-condition evaluation gives robustness its deserved weight: high
    # ordinary performance cannot hide broken adversarial/fault behavior.
    middle=min(v[0] for v in intervals.values())
    low=min(v[1] for v in intervals.values())
    high=max(v[2] for v in intervals.values())
    # Conservative enclosing interval: never claims a narrower range than
    # either observed scenario; caller supplies raw telemetry via trust gate.
    root=canonical_digest([
        trial.payload() for trial in sorted(
            trials,key=lambda x:(x.condition,x.play_session_digest))])
    result=sign_facet_measurement(FacetMeasurement(
        script.digest,subject_id,judge.judge_id,
        middle,low,high,len(trials),root,as_of,"0"*64),judge)
    return ProbeExecutionReceipt(
        script.digest,subject_id,judge.judge_id,result,
        tuple((x,len(conditions[x])) for x in CONDITIONS),
        tuple((x,intervals[x][0]) for x in CONDITIONS),root)


__all__=["CONDITIONS","RecordedProbeTrial","ProbeExecutionReceipt",
         "score_recorded_probe_batch"]
