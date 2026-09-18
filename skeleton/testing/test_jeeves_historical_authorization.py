from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.historical_authorization import (
    ActivationAuthorization,
    HistoricalActivationAuthorizationError,
    HistoricalActivationAuthorizer,
    summarize_authorization,
)
from skeleton.jeeves.historical_evaluation import (
    HoldoutEvaluation,
    HoldoutWindow,
    PromotionAction,
    PromotionDecision,
)
from skeleton.jeeves.historical_lifecycle import LifecycleProposal
from skeleton.jeeves.historical_models import ChampionDecision, ModelIdentity, ModelScore, canonical_fingerprint
from skeleton.jeeves.historical_readiness import HistoricalReadinessReport, ReadinessCheck


CANDIDATE = ModelIdentity("provider", "candidate", "r1")
OTHER = ModelIdentity("provider", "other", "r1")


def _proposal(*, candidate=CANDIDATE, fingerprint="proposal-fp", promotable=True):
    score = ModelScore(
        model=candidate,
        score=0.90,
        conservative_score=0.88,
        coverage=1.0,
        effective_samples=200,
        domains=(),
    )
    ranking = ChampionDecision(
        champion=score,
        candidates=(score,),
        evaluated_at=100.0,
        policy_fingerprint="ranking-policy",
        evidence_fingerprint="ranking-evidence",
    )
    holdout = HoldoutEvaluation(
        model=candidate,
        suite_key="suite@v1",
        window=HoldoutWindow(10.0, 20.0),
        score=0.90,
        coverage=1.0,
        samples=200,
        max_volatility=0.01,
        max_latest_drop=0.0,
        domains=(),
        missing_required_domains=(),
        evidence_fingerprint="holdout-evidence",
    )
    promotion = PromotionDecision(
        action=PromotionAction.PROMOTE if promotable else PromotionAction.HOLD,
        candidate=holdout,
        incumbent=None,
        reasons=() if promotable else ("fixture_hold",),
        margin=None,
        suite_fingerprint="suite-fp",
        policy_fingerprint="promotion-policy",
        decision_fingerprint="promotion-decision",
    )
    return LifecycleProposal(
        ranking=ranking,
        promotion=promotion,
        incumbent=None,
        candidate_scope=None,
        fingerprint=fingerprint,
    )


def _readiness(
    *,
    candidate=CANDIDATE,
    passed=True,
    policy="readiness-policy",
    evidence_fingerprint="readiness-evidence",
):
    check = ReadinessCheck(
        check_id="fixture",
        required=True,
        present=True,
        passed=passed,
        evidence_fingerprint=evidence_fingerprint,
    )
    reasons = () if passed else ("failed:fixture",)
    payload = {
        "candidate": candidate.key,
        "policy": policy,
        "checks": [
            {
                "id": check.check_id,
                "required": check.required,
                "present": check.present,
                "passed": check.passed,
                "evidence": check.evidence_fingerprint,
            }
        ],
        "reasons": list(reasons),
    }
    return HistoricalReadinessReport(
        candidate=candidate,
        passed=passed,
        checks=(check,),
        reasons=reasons,
        policy_fingerprint=policy,
        report_fingerprint=canonical_fingerprint(payload),
    )


def test_authorization_binds_exact_proposal_and_readiness() -> None:
    proposal = _proposal()
    readiness = _readiness()
    authorization = HistoricalActivationAuthorizer.authorize(proposal=proposal, readiness=readiness)
    assert authorization.candidate == CANDIDATE
    assert authorization.proposal_fingerprint == proposal.fingerprint
    assert authorization.promotion_decision_fingerprint == proposal.promotion.decision_fingerprint
    assert authorization.readiness_fingerprint == readiness.report_fingerprint
    HistoricalActivationAuthorizer.verify(
        proposal=proposal,
        readiness=readiness,
        authorization=authorization,
    )


def test_non_promotable_proposal_cannot_be_authorized() -> None:
    with pytest.raises(HistoricalActivationAuthorizationError) as exc:
        HistoricalActivationAuthorizer.authorize(
            proposal=_proposal(promotable=False),
            readiness=_readiness(),
        )
    assert exc.value.context["reason"] == "proposal_not_promotable"


def test_failed_readiness_cannot_be_authorized() -> None:
    with pytest.raises(HistoricalActivationAuthorizationError) as exc:
        HistoricalActivationAuthorizer.authorize(
            proposal=_proposal(),
            readiness=_readiness(passed=False),
        )
    assert exc.value.context["reason"] == "readiness_failed"


def test_candidate_mismatch_is_rejected() -> None:
    with pytest.raises(HistoricalActivationAuthorizationError) as exc:
        HistoricalActivationAuthorizer.authorize(
            proposal=_proposal(),
            readiness=_readiness(candidate=OTHER),
        )
    assert exc.value.context["reason"] == "candidate_mismatch"


def test_authorization_from_old_proposal_cannot_authorize_new_proposal() -> None:
    readiness = _readiness()
    old = _proposal(fingerprint="old-proposal")
    authorization = HistoricalActivationAuthorizer.authorize(proposal=old, readiness=readiness)
    new = _proposal(fingerprint="new-proposal")
    with pytest.raises(HistoricalActivationAuthorizationError) as exc:
        HistoricalActivationAuthorizer.verify(
            proposal=new,
            readiness=readiness,
            authorization=authorization,
        )
    assert exc.value.context["reason"] == "authorization_mismatch"


def test_authorization_from_old_readiness_report_cannot_be_reused() -> None:
    proposal = _proposal()
    old = _readiness(evidence_fingerprint="old-evidence")
    authorization = HistoricalActivationAuthorizer.authorize(proposal=proposal, readiness=old)
    refreshed = _readiness(evidence_fingerprint="new-evidence")
    with pytest.raises(HistoricalActivationAuthorizationError):
        HistoricalActivationAuthorizer.verify(
            proposal=proposal,
            readiness=refreshed,
            authorization=authorization,
        )


def test_readiness_policy_change_invalidates_authorization() -> None:
    proposal = _proposal()
    old = _readiness(policy="policy-a")
    authorization = HistoricalActivationAuthorizer.authorize(proposal=proposal, readiness=old)
    changed = _readiness(policy="policy-b")
    with pytest.raises(HistoricalActivationAuthorizationError):
        HistoricalActivationAuthorizer.verify(
            proposal=proposal,
            readiness=changed,
            authorization=authorization,
        )


def test_tampered_authorization_fingerprint_is_rejected() -> None:
    proposal = _proposal()
    readiness = _readiness()
    authorization = HistoricalActivationAuthorizer.authorize(proposal=proposal, readiness=readiness)
    tampered = replace(authorization, authorization_fingerprint="tampered")
    with pytest.raises(HistoricalActivationAuthorizationError):
        HistoricalActivationAuthorizer.verify(
            proposal=proposal,
            readiness=readiness,
            authorization=tampered,
        )


def test_invalid_authorization_type_is_rejected() -> None:
    with pytest.raises(HistoricalActivationAuthorizationError):
        HistoricalActivationAuthorizer.verify(
            proposal=_proposal(),
            readiness=_readiness(),
            authorization=object(),  # type: ignore[arg-type]
        )


def test_summary_is_json_friendly() -> None:
    authorization = HistoricalActivationAuthorizer.authorize(
        proposal=_proposal(),
        readiness=_readiness(),
    )
    summary = summarize_authorization(authorization)
    assert summary["candidate"] == CANDIDATE.key
    assert summary["authorization_fingerprint"] == authorization.authorization_fingerprint


def test_authorization_dataclass_does_not_hide_candidate_identity() -> None:
    authorization = HistoricalActivationAuthorizer.authorize(
        proposal=_proposal(),
        readiness=_readiness(),
    )
    assert isinstance(authorization, ActivationAuthorization)
    assert authorization.candidate.key == "provider:candidate@r1"