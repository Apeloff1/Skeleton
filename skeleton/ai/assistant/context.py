"""Trust-aware bounded context assembly for product assistant requests."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Iterable

from .contracts import (
    AssistantContractError,
    AssistantRequest,
    CompiledContext,
    ContextCandidate,
    TrustTier,
    digest_json,
)


_TRUST_ORDER = {
    TrustTier.TRUSTED_CONTROL: 0,
    TrustTier.AUTHORIZED_USER: 1,
    TrustTier.PRIVATE_RETRIEVED: 2,
    TrustTier.PUBLIC_EVIDENCE: 3,
    TrustTier.TOOL_OUTPUT: 4,
    TrustTier.MODEL_DERIVED: 5,
}


class ContextCompiler:
    """Compile context without allowing evidence to promote itself to policy."""

    def __init__(
        self,
        *,
        reserve_control_chars: int = 8_192,
        max_candidates: int = 512,
    ) -> None:
        if reserve_control_chars < 0:
            raise ValueError("reserve_control_chars must be non-negative")
        if not 1 <= max_candidates <= 4096:
            raise ValueError("max_candidates outside hard bounds")
        self.reserve_control_chars = reserve_control_chars
        self.max_candidates = max_candidates

    @staticmethod
    def _dedupe(candidates: Iterable[ContextCandidate]) -> list[ContextCandidate]:
        by_content: dict[str, ContextCandidate] = {}
        for candidate in candidates:
            if not isinstance(candidate, ContextCandidate):
                raise TypeError("context candidates must be ContextCandidate")
            key = hashlib.sha256(candidate.content.encode("utf-8")).hexdigest()
            prior = by_content.get(key)
            if prior is None:
                by_content[key] = candidate
                continue
            # Prefer higher authority first, then higher priority/relevance,
            # then deterministic source identity.
            current_key = (
                _TRUST_ORDER[candidate.trust],
                -candidate.priority,
                -candidate.relevance,
                candidate.source_id,
            )
            prior_key = (
                _TRUST_ORDER[prior.trust],
                -prior.priority,
                -prior.relevance,
                prior.source_id,
            )
            if current_key < prior_key:
                by_content[key] = candidate
        return list(by_content.values())

    @staticmethod
    def _sort_key(candidate: ContextCandidate) -> tuple[object, ...]:
        return (
            _TRUST_ORDER[candidate.trust],
            -candidate.priority,
            -candidate.relevance,
            -candidate.observed_at.timestamp(),
            candidate.source_id,
        )

    def compile(
        self,
        request: AssistantRequest,
        candidates: Iterable[ContextCandidate],
        *,
        now: datetime | None = None,
        allow_restricted: bool = False,
    ) -> CompiledContext:
        if not isinstance(request, AssistantRequest):
            raise TypeError("request must be AssistantRequest")
        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)

        normalized = self._dedupe(candidates)
        if len(normalized) > self.max_candidates:
            raise AssistantContractError("context candidate count exceeds hard bound")

        omitted: list[str] = []
        eligible: list[ContextCandidate] = []
        for candidate in normalized:
            if candidate.is_expired(instant):
                omitted.append(candidate.source_id)
                continue
            if candidate.data_class == "restricted" and not allow_restricted:
                omitted.append(candidate.source_id)
                continue
            # Instruction-shaped text from untrusted evidence remains evidence.
            # The flag is intentionally preserved; trust is never upgraded here.
            eligible.append(candidate)

        eligible.sort(key=self._sort_key)

        controls = [
            item for item in eligible if item.trust is TrustTier.TRUSTED_CONTROL
        ]
        others = [
            item for item in eligible if item.trust is not TrustTier.TRUSTED_CONTROL
        ]

        budget = request.max_context_chars
        selected: list[ContextCandidate] = []
        used = 0

        control_budget = min(
            budget,
            max(
                self.reserve_control_chars,
                min(sum(len(item.content) for item in controls), budget),
            ),
        )
        for item in controls:
            size = len(item.content)
            if used + size > control_budget:
                omitted.append(item.source_id)
                continue
            selected.append(item)
            used += size

        for item in others:
            size = len(item.content)
            if used + size > budget:
                omitted.append(item.source_id)
                continue
            selected.append(item)
            used += size

        # Never allow a derived/untrusted segment to appear before trusted
        # control/user authority due to relevance scoring.
        selected.sort(key=self._sort_key)
        omitted = list(dict.fromkeys(omitted))

        payload = {
            "request_digest": request.digest,
            "candidates": [
                {
                    "source_id": item.source_id,
                    "content": item.content,
                    "trust": item.trust.value,
                    "provenance": list(item.provenance),
                }
                for item in selected
            ],
            "omitted_source_ids": omitted,
        }
        return CompiledContext(
            request_digest=request.digest,
            candidates=tuple(selected),
            omitted_source_ids=tuple(omitted),
            char_count=used,
            digest=digest_json(payload),
        )


__all__ = ["ContextCompiler"]
