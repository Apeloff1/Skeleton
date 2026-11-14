"""Bind independent replay, source completeness and critical-quality holds."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .challenge_score import score
from .challenge_replay import ReplayAudit
from .paired_comparison import compare
from .errors import reject


def admit(
    baseline:ChallengeRun,candidate:ChallengeRun,
    baseline_replay:ReplayAudit,candidate_replay:ReplayAudit,
)->dict:
    for obj,cls in (
        (baseline,ChallengeRun),(candidate,ChallengeRun),
        (baseline_replay,ReplayAudit),(candidate_replay,ReplayAudit),
    ):
        if type(obj) is not cls:
            reject("evaluation-evidence-types")
    if not baseline.complete or not candidate.complete:
        reject("evaluation-not-all-cases")
    if baseline_replay.evaluated!=768 or candidate_replay.evaluated!=768:
        reject("evaluation-not-independently-replayed")
    if baseline_replay.mismatched_ids or candidate_replay.mismatched_ids:
        reject("evaluation-replay-inconsistent")
    if baseline_replay.model_sha256!=baseline.model_sha256:
        reject("evaluation-champion-replay-model")
    if candidate_replay.model_sha256!=candidate.model_sha256:
        reject("evaluation-candidate-replay-model")
    if baseline_replay.source_sha256!=baseline.source_sha256:
        reject("evaluation-champion-replay-source")
    if candidate_replay.source_sha256!=candidate.source_sha256:
        reject("evaluation-candidate-replay-source")
    conclusion=compare(baseline,candidate)
    quality=score(candidate)
    if conclusion["critical_regression"] or quality["critical_failed"]:
        hold="critical-failure"
    elif not conclusion["candidate_ahead_measured"]:
        hold="no-measured-improvement"
    else:
        hold="independent-operator-review"
    return {
        "schema":"skeleton.native-supervised.evaluation-admission.v1",
        "status":hold,
        "source_sha256":candidate.source_sha256,
        "candidate_model_sha256":candidate.model_sha256,
        "cases":768,
        "champion_replayed":768,
        "candidate_replayed":768,
        "critical_regressions":conclusion["critical_regression"],
        "critical_failures":quality["critical_failed"],
        "candidate_better_on_this_original_suite":conclusion["candidate_ahead_measured"],
        "independent_replay_verified":True,
        "model_quality_generally_proven":False,
        "production_authorized":False,
        "release_certified":False,
    }
