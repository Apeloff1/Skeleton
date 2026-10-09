"""Measured semantic gate for speculative inference optimization in VOL-007.

Draft/speculative work is never authoritative. Only an authoritative canonical
ModelResult may be published. This gate records whether speculative output was
semantically equivalent to that authoritative result.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json

from .session import InferenceContractError, ModelResult


def _digest(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class SpeculativeCandidate:
    operation_id: str
    request_digest: str
    provider: str
    model: str
    event_chain_digest: str
    response_digest: str | None
    terminal_reason: str
    draft_tokens: int
    accepted_tokens: int
    authority_scope: str = "speculative-candidate-only"

    def __post_init__(self) -> None:
        for field in ("operation_id", "provider", "model"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise InferenceContractError(f"invalid {field}")
        for field in ("request_digest", "event_chain_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise InferenceContractError(f"invalid {field}")
        if self.response_digest is not None and (
            len(self.response_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.response_digest)
        ):
            raise InferenceContractError("invalid response_digest")
        if self.terminal_reason not in {
            "completed",
            "cancelled",
            "deadline",
            "provider_error",
            "policy_denied",
        }:
            raise InferenceContractError("invalid terminal reason")
        for field in ("draft_tokens", "accepted_tokens"):
            value = getattr(self, field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise InferenceContractError(f"invalid {field}")
        if self.accepted_tokens > self.draft_tokens:
            raise InferenceContractError("accepted tokens exceed draft tokens")
        if self.terminal_reason == "completed" and self.response_digest is None:
            raise InferenceContractError("completed candidate requires response")
        if self.terminal_reason != "completed" and self.response_digest is not None:
            raise InferenceContractError(
                "non-completed candidate cannot publish response digest"
            )
        if self.authority_scope != "speculative-candidate-only":
            raise InferenceContractError(
                "speculative candidate cannot grant inference authority"
            )

    @property
    def candidate_digest(self) -> str:
        return _digest(
            {
                "operation_id": self.operation_id,
                "request_digest": self.request_digest,
                "provider": self.provider,
                "model": self.model,
                "event_chain_digest": self.event_chain_digest,
                "response_digest": self.response_digest,
                "terminal_reason": self.terminal_reason,
                "draft_tokens": self.draft_tokens,
                "accepted_tokens": self.accepted_tokens,
                "authority_scope": self.authority_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class SpeculationDecision:
    candidate_digest: str
    authoritative_result_digest: str
    equivalent: bool
    accepted_tokens: int
    draft_tokens: int
    authority_scope: str = "speculation-evidence-only"

    def __post_init__(self) -> None:
        for field in ("candidate_digest", "authoritative_result_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise InferenceContractError(f"invalid {field}")
        if not isinstance(self.equivalent, bool):
            raise InferenceContractError("equivalent must be bool")
        for field in ("accepted_tokens", "draft_tokens"):
            value = getattr(self, field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise InferenceContractError(
                    "invalid speculation token accounting"
                )
        if self.accepted_tokens > self.draft_tokens:
            raise InferenceContractError("accepted tokens exceed draft tokens")
        if self.authority_scope != "speculation-evidence-only":
            raise InferenceContractError(
                "speculation decision cannot grant inference authority"
            )

    @property
    def acceptance_ratio(self) -> float:
        if self.draft_tokens == 0:
            return 0.0
        return self.accepted_tokens / self.draft_tokens

    @property
    def decision_digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate_digest,
                "authoritative_result_digest": self.authoritative_result_digest,
                "equivalent": self.equivalent,
                "accepted_tokens": self.accepted_tokens,
                "draft_tokens": self.draft_tokens,
                "authority_scope": self.authority_scope,
            }
        )


def assess_speculative_candidate(
    candidate: SpeculativeCandidate,
    authoritative: ModelResult,
) -> SpeculationDecision:
    if not isinstance(candidate, SpeculativeCandidate):
        raise InferenceContractError("SpeculativeCandidate required")
    if not isinstance(authoritative, ModelResult):
        raise InferenceContractError("ModelResult required")

    same_identity = (
        candidate.operation_id == authoritative.operation_id
        and hmac.compare_digest(
            candidate.request_digest,
            authoritative.request_digest,
        )
        and candidate.provider == authoritative.provider
        and candidate.model == authoritative.model
    )
    same_semantics = (
        same_identity
        and candidate.terminal_reason == authoritative.terminal_reason
        and hmac.compare_digest(
            candidate.event_chain_digest,
            authoritative.event_chain_digest,
        )
        and (
            candidate.response_digest is None
            and authoritative.response_digest is None
            or candidate.response_digest is not None
            and authoritative.response_digest is not None
            and hmac.compare_digest(
                candidate.response_digest,
                authoritative.response_digest,
            )
        )
    )

    return SpeculationDecision(
        candidate_digest=candidate.candidate_digest,
        authoritative_result_digest=authoritative.result_digest,
        equivalent=same_semantics,
        accepted_tokens=candidate.accepted_tokens if same_semantics else 0,
        draft_tokens=candidate.draft_tokens,
    )


def require_speculative_equivalence(
    candidate: SpeculativeCandidate,
    authoritative: ModelResult,
) -> SpeculationDecision:
    decision = assess_speculative_candidate(candidate, authoritative)
    if not decision.equivalent:
        raise InferenceContractError(
            "speculative candidate diverged from authoritative inference result"
        )
    return decision
