"""Readiness-bound activation authorization for Jeeves historical champions.

A lifecycle proposal and a readiness report are independently fingerprinted.
This module binds those exact reviewed artifacts into one activation token before
the champion ledger can be mutated. The underlying lifecycle still performs its
normal fresh revalidation at activation time.

The authorization contains no provider credentials and grants no capability by
itself; it is a deterministic integrity binding valid for one candidate, proposal
fingerprint, promotion decision, readiness report, and readiness policy. It is
not a cryptographic signature or a substitute for process/access-control trust.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.historical_lifecycle import (
    HistoricalLifecycleError,
    HistoricalModelLifecycle,
    LifecycleActivation,
    LifecycleProposal,
)
from skeleton.jeeves.historical_models import ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_readiness import HistoricalReadinessReport


class HistoricalActivationAuthorizationError(HistoricalLifecycleError):
    code = "JVS.HISTORICAL_ACTIVATION_AUTHORIZATION"
    http_status = 409


@dataclass(frozen=True, slots=True)
class ActivationAuthorization:
    candidate: ModelIdentity
    proposal_fingerprint: str
    promotion_decision_fingerprint: str
    readiness_fingerprint: str
    readiness_policy_fingerprint: str
    authorization_fingerprint: str


class HistoricalActivationAuthorizer:
    """Bind reviewed lifecycle and readiness evidence before activation."""

    @staticmethod
    def authorize(
        *,
        proposal: LifecycleProposal,
        readiness: HistoricalReadinessReport,
    ) -> ActivationAuthorization:
        HistoricalActivationAuthorizer._validate_inputs(proposal=proposal, readiness=readiness)
        if not proposal.promotable:
            raise HistoricalActivationAuthorizationError(
                "non-promotable proposal cannot be authorized",
                context={"reason": "proposal_not_promotable", "hold_reasons": list(proposal.hold_reasons)},
            )
        if not readiness.passed:
            raise HistoricalActivationAuthorizationError(
                "historical readiness did not pass",
                context={"reason": "readiness_failed", "reasons": list(readiness.reasons)},
            )
        payload = HistoricalActivationAuthorizer._payload(proposal=proposal, readiness=readiness)
        return ActivationAuthorization(
            candidate=proposal.candidate,
            proposal_fingerprint=proposal.fingerprint,
            promotion_decision_fingerprint=proposal.promotion.decision_fingerprint,
            readiness_fingerprint=readiness.report_fingerprint,
            readiness_policy_fingerprint=readiness.policy_fingerprint,
            authorization_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def verify(
        *,
        proposal: LifecycleProposal,
        readiness: HistoricalReadinessReport,
        authorization: ActivationAuthorization,
    ) -> None:
        HistoricalActivationAuthorizer._validate_inputs(proposal=proposal, readiness=readiness)
        if not isinstance(authorization, ActivationAuthorization):
            raise HistoricalActivationAuthorizationError(
                "authorization must be ActivationAuthorization",
                context={"reason": "invalid_authorization"},
            )
        if not proposal.promotable:
            raise HistoricalActivationAuthorizationError(
                "proposal is no longer promotable",
                context={"reason": "proposal_not_promotable"},
            )
        if not readiness.passed:
            raise HistoricalActivationAuthorizationError(
                "readiness is no longer passing",
                context={"reason": "readiness_failed"},
            )
        expected = HistoricalActivationAuthorizer.authorize(proposal=proposal, readiness=readiness)
        if authorization != expected:
            raise HistoricalActivationAuthorizationError(
                "activation authorization does not match current reviewed evidence",
                context={
                    "reason": "authorization_mismatch",
                    "expected": expected.authorization_fingerprint,
                    "provided": authorization.authorization_fingerprint,
                },
            )

    @staticmethod
    def activate(
        *,
        lifecycle: HistoricalModelLifecycle,
        proposal: LifecycleProposal,
        readiness: HistoricalReadinessReport,
        authorization: ActivationAuthorization,
    ) -> LifecycleActivation:
        if not isinstance(lifecycle, HistoricalModelLifecycle):
            raise HistoricalActivationAuthorizationError(
                "lifecycle must be HistoricalModelLifecycle",
                context={"reason": "invalid_lifecycle"},
            )
        # The lifecycle mutation boundary performs authorization verification and
        # then re-runs ranking, promotion, and optional lineage review. Keeping
        # verification there prevents callers from bypassing readiness by invoking
        # the lifecycle directly on production-configured instances.
        return lifecycle.activate(
            proposal,
            readiness=readiness,
            authorization=authorization,
        )

    @staticmethod
    def _validate_inputs(
        *,
        proposal: LifecycleProposal,
        readiness: HistoricalReadinessReport,
    ) -> None:
        if not isinstance(proposal, LifecycleProposal):
            raise HistoricalActivationAuthorizationError(
                "proposal must be LifecycleProposal",
                context={"reason": "invalid_proposal"},
            )
        if not isinstance(readiness, HistoricalReadinessReport):
            raise HistoricalActivationAuthorizationError(
                "readiness must be HistoricalReadinessReport",
                context={"reason": "invalid_readiness"},
            )
        if readiness.candidate != proposal.candidate:
            raise HistoricalActivationAuthorizationError(
                "readiness candidate does not match lifecycle proposal",
                context={
                    "reason": "candidate_mismatch",
                    "proposal": proposal.candidate.key,
                    "readiness": readiness.candidate.key,
                },
            )

    @staticmethod
    def _payload(
        *,
        proposal: LifecycleProposal,
        readiness: HistoricalReadinessReport,
    ) -> dict[str, object]:
        return {
            "candidate": proposal.candidate.key,
            "proposal_fingerprint": proposal.fingerprint,
            "promotion_decision_fingerprint": proposal.promotion.decision_fingerprint,
            "readiness_fingerprint": readiness.report_fingerprint,
            "readiness_policy_fingerprint": readiness.policy_fingerprint,
        }


def summarize_authorization(authorization: ActivationAuthorization) -> dict[str, object]:
    return {
        "candidate": authorization.candidate.key,
        "proposal_fingerprint": authorization.proposal_fingerprint,
        "promotion_decision_fingerprint": authorization.promotion_decision_fingerprint,
        "readiness_fingerprint": authorization.readiness_fingerprint,
        "readiness_policy_fingerprint": authorization.readiness_policy_fingerprint,
        "authorization_fingerprint": authorization.authorization_fingerprint,
    }