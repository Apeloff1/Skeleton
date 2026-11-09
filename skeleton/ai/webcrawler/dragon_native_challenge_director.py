"""Game challenge direction from measurable routes, not invented player feelings.

Challenge and occasional frustration can be deliberate, but measured solution
depth or search work alone is not enjoyment data. This director keeps those
claims separate, supports optional bounded aggregate playtest observations,
and offers recoverable peaks, transparent difficulty and player choice.

All inputs are original level route reports; it does not crawl commercial
levels or feed gameplay signals into model weights without separate approval.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
import json

SCHEMA="skeleton.ai.dragon.challenge_director.v1"
MAX_STAGES=8
PROFILES={
    "gentle":(25,13,2),
    "balanced":(43,19,3),
    "challenging":(63,22,3),
    "spicy":(78,25,4),
}

@dataclass(frozen=True)
class PlayerAggregate:
    """Voluntary local aggregate counters, no identifiers or raw input logs."""
    attempts:int
    completions:int
    player_moves:int
    undo_count:int
    hint_requests:int
    abandons:int
    difficult_rating:int|None=None
    enjoyment_rating:int|None=None

    def validate(self):
        counts=(self.attempts,self.completions,self.player_moves,
                self.undo_count,self.hint_requests,self.abandons)
        if any(type(v) is not int or not 0<=v<=100000 for v in counts):
            raise ValueError("anonymous original game playtest counters invalid")
        if (self.attempts<1 or self.completions>self.attempts or
                self.abandons>self.attempts or
                self.completions+self.abandons>self.attempts):
            raise ValueError("playtest cannot complete/abandon more attempts than recorded")
        for rating in (self.difficult_rating,self.enjoyment_rating):
            if rating is not None and (type(rating) is not int or not 1<=rating<=5):
                raise ValueError("optional subjective rating must be 1..5")

@dataclass(frozen=True)
class StageDirector:
    stage:int
    role:str
    original_route_count:int
    structural_solutions:int
    shortest_moves:int
    shortest_pushes:int
    measured_search_states:int
    measured_complexity:int
    intended_tension:int
    tension_gap:int
    spike:bool
    recovery:bool
    rescue_tools:tuple[str,...]
    warnings:tuple[str,...]
    human_enjoyment_evidence:bool

@dataclass(frozen=True)
class ChallengePlan:
    schema:str
    profile:str
    stages:tuple[StageDirector,...]
    has_player_observations:bool
    player_feedback_scope:str
    overall_fairness_warnings:tuple[str,...]
    observation_evidence_digest:str|None
    plan_digest:str
    claim:str


def make_challenge_plan(route_reports:tuple[dict,...], *,
                        profile:str="balanced",
                        player_samples:tuple[PlayerAggregate|None,...]|None=None,
                        branching:bool=True)->ChallengePlan:
    if profile not in PROFILES:
        raise ValueError("challenge intent must be gentle, balanced, challenging or spicy")
    if not isinstance(route_reports,tuple) or not 1<=len(route_reports)<=MAX_STAGES:
        raise ValueError("challenge director requires one to eight measured original stages")
    if type(branching) is not bool:
        raise ValueError("branching creator intent must be a boolean")
    if player_samples is not None:
        if (not isinstance(player_samples,tuple) or
                len(player_samples)!=len(route_reports)):
            raise ValueError("optional playtest observations must align to each game stage")
        for item in player_samples:
            if item is not None:
                if not isinstance(item,PlayerAggregate):
                    raise ValueError("playtest observation must use exact typed bounded counters")
                item.validate()
    target,volatility,period=PROFILES[profile]
    authored=[]
    warnings=[]
    evidence=[]
    for index,record in enumerate(route_reports):
        if not isinstance(record,dict) or record.get("schema")!=(
                "skeleton.ai.dragon.original_multiroute.v1"):
            raise ValueError("invalid original game solver evidence")
        routes=record.get("routes")
        if not isinstance(routes,(list,tuple)) or not routes:
            raise ValueError("solver portfolio has no winning route to measure")
        baseline=routes[0]
        move_count=baseline.get("moves")
        pushes=baseline.get("pushes")
        complex_score=record.get("difficulty_estimate")
        explored=record.get("examined_states")
        structural=record.get("structurally_distinct")
        if (type(move_count) is not int or not 1<=move_count<=400 or
                type(pushes) is not int or not 1<=pushes<=move_count or
                type(complex_score) is not int or not 0<=complex_score<=100 or
                type(explored) is not int or not 1<=explored<=800000 or
                type(structural) is not int or not 1<=structural<=len(routes)):
            raise ValueError("original native game complexity metrics invalid")
        # Deliberate tension with relief valleys every 3/4 stages. A relief
        # chapter is NEVER covertly substituted for a player's own skill
        # level; it is an advisory to the original level author.
        recovery=index>0 and (index+1)%period==0
        spike=profile=="spicy" and index>0 and not recovery and index%4==1
        expected=max(8,min(92,target+
            min(18,index*2) + (volatility if spike else 0) -
            (volatility if recovery else 0)))
        sample=player_samples[index] if player_samples is not None else None
        sample_warning=[]
        has_rating=False
        if sample is not None:
            has_rating=sample.enjoyment_rating is not None
            evidence.append(asdict(sample))
            if sample.attempts>=3:
                dropout=(100*sample.abandons)//sample.attempts
                if dropout>=40:
                    sample_warning.append("observed_high_abandonment")
                if sample.enjoyment_rating is not None and sample.enjoyment_rating<=2:
                    sample_warning.append("observed_low_enjoyment")
        margin=abs(complex_score-expected)
        risk=[]
        if margin>33:risk.append("challenge_far_from_intended_profile")
        if structural<2 and index>0:risk.append("few_distinct_crate_strategies")
        if spike and not branching and len(route_reports)>=3:
            risk.append("frustration_peak_without_campaign_detour")
        risk.extend(sample_warning)
        if recovery and complex_score>expected+15:
            risk.append("planned_recovery_chapter_is_measurably_difficult")
        warnings.extend(f"stage_{index+1}:{name}" for name in risk)
        rescue=("manual_undo","manual_live_hint","replay_shortest_path")
        if spike:
            rescue+=("optional_easier_campaign_branch",)
        role="recovery" if recovery else "tension_spike" if spike else "exploration"
        authored.append(StageDirector(
            index+1,role,len(routes),structural,move_count,pushes,explored,
            complex_score,expected,complex_score-expected,spike,recovery,
            rescue,tuple(risk),has_rating,
        ))
    evidence_digest=(sha256(json.dumps(evidence,sort_keys=True,
                separators=(",",":")).encode("ascii")).hexdigest()
                     if evidence else None)
    plain=[asdict(item) for item in authored]
    digest=sha256(json.dumps({
        "profile":profile,"stages":plain,
        "player_sample_digest":evidence_digest,
    },sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    return ChallengePlan(
        SCHEMA,profile,tuple(authored),bool(evidence),
        ("subjective feedback present for some stages" if any(
            x.human_enjoyment_evidence for x in authored) else
         "no player-rated enjoyment observations"),
        tuple(warnings),evidence_digest,digest,
        "measured solver complexity and declared challenge intent, "
        "NOT proof of entertainment, frustration or player satisfaction",
    )

def challenge_report(plan:ChallengePlan)->dict:
    return asdict(plan)

def review_player_tension(stage:StageDirector,
                          observations:PlayerAggregate)->dict:
    observations.validate()
    if not isinstance(stage,StageDirector):
        raise ValueError("stage challenge evidence is missing")
    completion=(100*observations.completions)//observations.attempts
    hint_rate=(100*observations.hint_requests)//observations.attempts
    undo_rate=(100*observations.undo_count)//observations.attempts
    # Evidence-led recommendations, not covert forced changes to live games.
    suggestions=[]
    if completion<35 and observations.attempts>=5:
        suggestions.append("offer_alternative_chapter_route_or_opt_in_hint")
    if hint_rate>100:suggestions.append("audit_signposting_or_deadend_clarity")
    if undo_rate>200:suggestions.append("review_crate_deadlocks_and_recovery")
    if observations.enjoyment_rating is not None:
        if observations.enjoyment_rating<=2:
            suggestions.append("collect_consenting_qualitative_player_feedback")
        elif observations.enjoyment_rating>=4:
            suggestions.append("retain_profile_for_comparative_playtests")
    return {
        "schema":SCHEMA,"stage":stage.stage,
        "observed_attempts":observations.attempts,
        "completion_rate_percent":completion,
        "hints_per_attempt_percent":hint_rate,
        "undos_per_attempt_percent":undo_rate,
        "optional_enjoyment_rating":observations.enjoyment_rating,
        "suggestions":suggestions,
        "claim":"aggregated counts only; consent and sampling representativeness unverified",
    }
