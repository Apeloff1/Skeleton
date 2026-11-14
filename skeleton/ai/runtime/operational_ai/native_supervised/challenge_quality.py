"""Conservative assessment: incomplete or critically regressed runs fail closed."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .paired_comparison import compare
from .challenge_score import score
from .errors import reject


def qualify(champion:ChallengeRun,candidate:ChallengeRun)->dict:
    if type(champion) is not ChallengeRun or type(candidate) is not ChallengeRun:
        reject("quality-comparison-required")
    if not champion.complete or not candidate.complete:
        return {
            "status":"held-partial",
            "independent_quality_verified":False,
            "release_certified":False,
        }
    comparison=compare(champion,candidate)
    candidate_score=score(candidate)
    if comparison["critical_regression"]:
        status="held-critical-regression"
    elif candidate_score["critical_failed"]:
        status="held-critical-incorrect"
    elif not comparison["candidate_ahead_measured"]:
        status="held-no-measured-improvement"
    else:
        status="eligible-for-independent-review"
    return {
        "status":status,
        "comparison":comparison,
        "candidate_domains":candidate_score["domains"],
        "real_768_case_evaluation":True,
        "independent_quality_verified":False,
        "automatic_model_promotion":False,
        "release_certified":False,
    }
