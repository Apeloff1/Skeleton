from dataclasses import replace

import pytest

from skeleton.inference.session import (
    InferenceContractError,
    InferenceUsage,
    ModelResult,
)
from skeleton.inference.speculation import (
    SpeculativeCandidate,
    SpeculationDecision,
    assess_speculative_candidate,
    require_speculative_equivalence,
)


H = "a" * 64


def result(
    *,
    provider: str = "p",
    model: str = "m",
    event: str = "b" * 64,
    response: str | None = "c" * 64,
    reason: str = "completed",
    usage: InferenceUsage | None = None,
) -> ModelResult:
    return ModelResult(
        "op",
        H,
        provider,
        model,
        reason,
        usage or InferenceUsage(10, 4, 1),
        event,
        response,
    )


def candidate(authoritative: ModelResult, **overrides) -> SpeculativeCandidate:
    values = dict(
        operation_id=authoritative.operation_id,
        request_digest=authoritative.request_digest,
        provider=authoritative.provider,
        model=authoritative.model,
        event_chain_digest=authoritative.event_chain_digest,
        response_digest=authoritative.response_digest,
        terminal_reason=authoritative.terminal_reason,
        draft_tokens=8,
        accepted_tokens=4,
    )
    values.update(overrides)
    return SpeculativeCandidate(**values)


def test_exact_speculative_semantics_are_admissible_as_evidence_only():
    authoritative = result()
    decision = require_speculative_equivalence(
        candidate(authoritative),
        authoritative,
    )
    assert decision.equivalent is True
    assert decision.accepted_tokens == 4
    assert decision.acceptance_ratio == 0.5
    assert decision.authority_scope == "speculation-evidence-only"
    assert len(decision.decision_digest) == 64


def test_usage_accounting_difference_does_not_change_semantic_equivalence():
    authoritative = result(usage=InferenceUsage(20, 5, 2))
    decision = assess_speculative_candidate(candidate(authoritative), authoritative)
    assert decision.equivalent is True
    assert decision.authoritative_result_digest == authoritative.result_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_id", "other"),
        ("request_digest", "d" * 64),
        ("provider", "other-provider"),
        ("model", "other-model"),
        ("event_chain_digest", "e" * 64),
        ("response_digest", "f" * 64),
        ("terminal_reason", "provider_error"),
    ],
)
def test_any_semantic_divergence_is_rejected(field, value):
    authoritative = result()
    speculative = candidate(authoritative, **{field: value})
    decision = assess_speculative_candidate(speculative, authoritative)
    assert decision.equivalent is False
    assert decision.accepted_tokens == 0
    with pytest.raises(InferenceContractError, match="diverged"):
        require_speculative_equivalence(speculative, authoritative)


def test_failure_candidate_can_only_match_failure_without_response():
    authoritative = result(reason="deadline", response=None)
    speculative = candidate(
        authoritative,
        response_digest=None,
        terminal_reason="deadline",
        draft_tokens=3,
        accepted_tokens=0,
    )
    assert require_speculative_equivalence(speculative, authoritative).equivalent


def test_speculative_candidate_cannot_claim_result_authority():
    authoritative = result()
    values = candidate(authoritative)
    with pytest.raises(InferenceContractError, match="cannot grant inference authority"):
        SpeculativeCandidate(
            values.operation_id,
            values.request_digest,
            values.provider,
            values.model,
            values.event_chain_digest,
            values.response_digest,
            values.terminal_reason,
            values.draft_tokens,
            values.accepted_tokens,
            "inference-result-only",
        )


def test_speculation_decision_cannot_claim_execution_authority():
    authoritative = result()
    speculative = candidate(authoritative)
    decision = assess_speculative_candidate(speculative, authoritative)
    with pytest.raises(InferenceContractError, match="cannot grant inference authority"):
        SpeculationDecision(
            decision.candidate_digest,
            decision.authoritative_result_digest,
            True,
            4,
            8,
            "execution",
        )


def test_accepted_tokens_cannot_exceed_draft_budget():
    authoritative = result()
    with pytest.raises(InferenceContractError, match="accepted tokens exceed"):
        candidate(authoritative, draft_tokens=1, accepted_tokens=2)
