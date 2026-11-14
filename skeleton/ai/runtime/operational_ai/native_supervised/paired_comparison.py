"""Exact same 768 source IDs for champion/candidate, with critical regression hold."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .challenge_score import score
from .canonical import digest
from .errors import reject


def compare(champion:ChallengeRun,candidate:ChallengeRun)->dict:
    if type(champion) is not ChallengeRun or type(candidate) is not ChallengeRun:
        reject("pair-comparison-runs")
    if champion.source_sha256!=candidate.source_sha256:
        reject("pair-source-drift")
    if champion.start!=candidate.start or len(champion.results)!=len(candidate.results):
        reject("pair-segments-mismatch")
    if champion.model_sha256==candidate.model_sha256:
        reject("pair-requires-distinct-models")
    baseline={x.case_id:x for x in champion.results}
    contender={x.case_id:x for x in candidate.results}
    if len(baseline)!=len(champion.results) or len(contender)!=len(candidate.results):
        reject("pair-duplicate-cases")
    if set(baseline)!=set(contender):
        reject("pair-case-set")
    improved=regressed=unchanged=critical_regression=0
    for item_id in sorted(baseline):
        b,c=baseline[item_id],contender[item_id]
        if b.case_sha256!=c.case_sha256 or b.severity!=c.severity:
            reject("pair-case-content")
        if not b.passed and c.passed:
            improved+=1
        elif b.passed and not c.passed:
            regressed+=1
            if b.severity=="critical":
                critical_regression+=1
        else:
            unchanged+=1
    bscore=score(champion)
    cscore=score(candidate)
    return {
        "schema":"skeleton.native-supervised.paired-comparison.v1",
        "source_sha256":champion.source_sha256,
        "champion_sha256":champion.model_sha256,
        "candidate_sha256":candidate.model_sha256,
        "cases":len(baseline),
        "full_768_case_comparison":champion.complete and candidate.complete,
        "improved":improved,"regressed":regressed,"unchanged":unchanged,
        "critical_regression":critical_regression,
        "champion_score_ppm":bscore["score_ppm"],
        "candidate_score_ppm":cscore["score_ppm"],
        "candidate_ahead_measured":cscore["score_ppm"]>bscore["score_ppm"],
        "independent_evaluator_signed":False,
        "production_authorized":False,
    }
