"""Deterministic verification runtime for claims, evidence, and actions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Mapping, Protocol

from skeleton.contracts.verification import (
    Claim,
    ClaimCheck,
    ClaimKind,
    ConfidenceBand,
    EvidenceReference,
    PostconditionCheck,
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
    VerificationRequest,
    content_digest,
)
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


_LEVEL_RANK = {
    VerificationLevel.NONE: 0,
    VerificationLevel.STRUCTURAL: 1,
    VerificationLevel.EVIDENCE: 2,
    VerificationLevel.ACTION: 3,
    VerificationLevel.HIGH_IMPACT: 4,
}


@dataclass(frozen=True, slots=True)
class DeterministicVerificationInput:
    candidate_text: str
    claims: tuple[Claim, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    postconditions: tuple[PostconditionCheck, ...] = ()
    evidence_content: Mapping[str, str] | None = None


def tool_receipt_postcondition(
    receipt: ToolExecutionReceipt,
) -> PostconditionCheck:
    """Convert one observable tool receipt into a verification postcondition."""

    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    passed = receipt.status is ToolExecutionStatus.SUCCEEDED
    return PostconditionCheck(
        check_id="tool:" + receipt.receipt_id,
        subject_ref="tool-receipt:" + receipt.receipt_id,
        passed=passed,
        reason_code=(
            "tool_succeeded"
            if passed
            else "tool_" + receipt.status.value
        ),
        evidence_refs=(),
    )


class VerificationRuntime:
    """Verify only observable candidate/evidence/action properties."""

    @staticmethod
    def _claim_checks(
        claims: Iterable[Claim],
        evidence: Iterable[EvidenceReference],
        *,
        evidence_content: Mapping[str, str] | None = None,
    ) -> tuple[ClaimCheck, ...]:
        evidence_by_id: dict[str, EvidenceReference] = {}
        for item in evidence:
            if not isinstance(item, EvidenceReference):
                raise TypeError("evidence must contain EvidenceReference values")
            if item.evidence_id in evidence_by_id:
                raise ValueError("evidence ids must be unique")
            evidence_by_id[item.evidence_id] = item

        content_map = dict(evidence_content or {})
        checks: list[ClaimCheck] = []
        seen_claims: set[str] = set()

        for claim in claims:
            if not isinstance(claim, Claim):
                raise TypeError("claims must contain Claim values")
            if claim.claim_id in seen_claims:
                raise ValueError("claim ids must be unique")
            seen_claims.add(claim.claim_id)

            reasons: list[str] = []
            resolved = tuple(
                ref for ref in claim.evidence_refs if ref in evidence_by_id
            )
            missing = tuple(
                ref for ref in claim.evidence_refs if ref not in evidence_by_id
            )
            if missing:
                reasons.append("missing_evidence_ref")

            requires_evidence = (
                claim.required
                and claim.kind
                in {
                    ClaimKind.FACTUAL,
                    ClaimKind.INTERPRETATION,
                    ClaimKind.ACTION,
                }
            )
            grounded = not missing and (
                bool(resolved) if requires_evidence else True
            )
            if requires_evidence and not resolved:
                reasons.append("claim_ungrounded")

            digest_failed = False
            for evidence_id in resolved:
                if evidence_id not in content_map:
                    continue
                observed = content_digest(content_map[evidence_id])
                if observed != evidence_by_id[evidence_id].content_digest:
                    digest_failed = True
                    reasons.append("evidence_digest_mismatch")
            if digest_failed:
                grounded = False

            citation_ids: set[str] = set()
            for evidence_id in resolved:
                item = evidence_by_id[evidence_id]
                citation_ids.add(item.evidence_id)
                citation_id = item.citation_metadata.get("citation_id")
                if isinstance(citation_id, str) and citation_id.strip():
                    citation_ids.add(citation_id.strip())

            citation_valid = all(
                ref in citation_ids
                for ref in claim.citation_refs
            )
            if not citation_valid:
                reasons.append("citation_not_bound_to_claim_evidence")

            checks.append(
                ClaimCheck(
                    claim_id=claim.claim_id,
                    grounded=grounded,
                    citation_valid=citation_valid,
                    evidence_refs=resolved,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                )
            )
        return tuple(checks)

    @staticmethod
    def _outcome_for_failure(
        level: VerificationLevel,
        *,
        structural_failure: bool,
        evidence_failure: bool,
        action_failure: bool,
    ) -> tuple[VerificationOutcome, dict[str, object] | None]:
        if structural_failure:
            return (
                VerificationOutcome.REPAIR,
                {
                    "reason": "structural_verification_failed",
                    "retry_allowed": True,
                },
            )
        if action_failure:
            return (VerificationOutcome.BLOCK, None)
        if evidence_failure:
            if level is VerificationLevel.HIGH_IMPACT:
                return (VerificationOutcome.BLOCK, None)
            return (
                VerificationOutcome.QUALIFIED,
                {
                    "reason": "evidence_incomplete",
                    "retry_allowed": True,
                },
            )
        if level is VerificationLevel.HIGH_IMPACT:
            return (
                VerificationOutcome.BLOCK,
                {
                    "reason": "semantic_high_impact_verifier_required",
                    "retry_allowed": False,
                },
            )
        return (VerificationOutcome.VERIFIED, None)

    def verify_deterministic(
        self,
        request: VerificationRequest,
        verification_input: DeterministicVerificationInput,
        *,
        now: datetime | None = None,
    ) -> VerificationReceipt:
        if not isinstance(request, VerificationRequest):
            raise TypeError("request must be VerificationRequest")
        if not isinstance(
            verification_input,
            DeterministicVerificationInput,
        ):
            raise TypeError(
                "verification_input must be DeterministicVerificationInput"
            )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )

        reasons: list[str] = []
        candidate = verification_input.candidate_text
        structural_failure = (
            not isinstance(candidate, str)
            or not candidate.strip()
        )
        if structural_failure:
            reasons.append("candidate_empty")

        deadline_expired = (
            request.deadline is not None
            and instant > request.deadline
        )
        if deadline_expired:
            reasons.append("verification_deadline_expired")

        claim_checks = self._claim_checks(
            verification_input.claims,
            verification_input.evidence,
            evidence_content=verification_input.evidence_content,
        )

        level = request.required_level
        evidence_required = _LEVEL_RANK[level] >= _LEVEL_RANK[
            VerificationLevel.EVIDENCE
        ]
        action_required = _LEVEL_RANK[level] >= _LEVEL_RANK[
            VerificationLevel.ACTION
        ]

        evidence_failure = False
        if evidence_required:
            failed_claims = tuple(
                item
                for item in claim_checks
                if not item.passed
            )
            evidence_failure = bool(failed_claims)
            if failed_claims:
                reasons.append("claim_grounding_or_citation_failed")

            declared = set(request.evidence_refs)
            supplied = {
                item.evidence_id
                for item in verification_input.evidence
            }
            if not declared.issubset(supplied):
                evidence_failure = True
                reasons.append("declared_evidence_missing")

        postconditions = verification_input.postconditions
        if any(
            not isinstance(item, PostconditionCheck)
            for item in postconditions
        ):
            raise TypeError(
                "postconditions must contain PostconditionCheck values"
            )

        action_failure = False
        if action_required:
            if request.tool_receipt_refs and not postconditions:
                action_failure = True
                reasons.append("action_postconditions_missing")
            failed_postconditions = tuple(
                item for item in postconditions if not item.passed
            )
            if failed_postconditions:
                action_failure = True
                reasons.append("action_postcondition_failed")

        if deadline_expired:
            structural_failure = True
            reasons.append("verification_incomplete")

        outcome, repair = self._outcome_for_failure(
            level,
            structural_failure=structural_failure,
            evidence_failure=evidence_failure,
            action_failure=action_failure,
        )

        if outcome is VerificationOutcome.VERIFIED:
            confidence = (
                ConfidenceBand.HIGH
                if level in {
                    VerificationLevel.ACTION,
                    VerificationLevel.HIGH_IMPACT,
                }
                else ConfidenceBand.MEDIUM
            )
        elif outcome is VerificationOutcome.QUALIFIED:
            confidence = ConfidenceBand.LOW
        else:
            confidence = ConfidenceBand.UNKNOWN

        evidence_refs = tuple(
            dict.fromkeys(
                ref
                for check in claim_checks
                for ref in check.evidence_refs
            )
        )

        return VerificationReceipt(
            verification_id=request.verification_id,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            turn_id=request.turn_id,
            candidate_ref=request.candidate_ref,
            level=level,
            outcome=outcome,
            reason_codes=tuple(dict.fromkeys(reasons)),
            claim_checks=claim_checks,
            postcondition_checks=tuple(postconditions),
            evidence_refs=evidence_refs,
            repair_directive=repair,
            confidence_band=confidence,
            created_at=instant,
            completed_at=instant,
        )




class SemanticVerifierError(RuntimeError):
    """Semantic verification could not produce a trustworthy verdict."""


@dataclass(frozen=True, slots=True)
class SemanticVerificationDecision:
    outcome: VerificationOutcome
    reason_codes: tuple[str, ...]
    confidence_band: ConfidenceBand
    route_ref: str
    repair_instruction: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "outcome",
            VerificationOutcome(self.outcome),
        )
        object.__setattr__(
            self,
            "confidence_band",
            ConfidenceBand(self.confidence_band),
        )
        if not isinstance(self.route_ref, str) or not self.route_ref.strip():
            raise ValueError("route_ref is required")
        object.__setattr__(
            self,
            "reason_codes",
            tuple(
                dict.fromkeys(
                    str(item).strip()
                    for item in self.reason_codes
                    if str(item).strip()
                )
            ),
        )
        if self.repair_instruction is not None:
            instruction = str(self.repair_instruction).strip()
            object.__setattr__(
                self,
                "repair_instruction",
                instruction or None,
            )


class SemanticVerifier(Protocol):
    async def verify(
        self,
        request: VerificationRequest,
        verification_input: DeterministicVerificationInput,
    ) -> SemanticVerificationDecision:
        ...


RepairCallback = Callable[
    [str, str, int],
    str | Awaitable[str],
]


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    attempt: int
    parent_candidate_ref: str
    repaired_candidate_ref: str
    reason_codes: tuple[str, ...]
    instruction: str

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "parent_candidate_ref": self.parent_candidate_ref,
            "repaired_candidate_ref": self.repaired_candidate_ref,
            "reason_codes": list(self.reason_codes),
            "instruction": self.instruction,
        }


@dataclass(frozen=True, slots=True)
class VerificationRunResult:
    receipt: VerificationReceipt
    candidate_text: str
    repair_lineage: tuple[RepairAttempt, ...] = ()


async def _await_value(value):
    if hasattr(value, "__await__"):
        return await value
    return value


class CanonicalProviderSemanticVerifier:
    """Bounded semantic verifier that uses the canonical provider boundary."""

    def __init__(
        self,
        provider,
        *,
        model: str | None = None,
        max_output_tokens: int = 512,
    ) -> None:
        if not hasattr(provider, "generate"):
            raise TypeError("provider must implement canonical generate")
        if max_output_tokens < 64 or max_output_tokens > 4096:
            raise ValueError("max_output_tokens must be within [64, 4096]")
        self.provider = provider
        self.model = model
        self.max_output_tokens = max_output_tokens

    async def verify(
        self,
        request: VerificationRequest,
        verification_input: DeterministicVerificationInput,
    ) -> SemanticVerificationDecision:
        from skeleton.provider_runtime import ProviderRequest

        evidence_by_id = {
            item.evidence_id: item
            for item in verification_input.evidence
        }
        content_map = dict(verification_input.evidence_content or {})
        payload = {
            "candidate": verification_input.candidate_text,
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "kind": claim.kind.value,
                    "evidence_refs": list(claim.evidence_refs),
                    "citation_refs": list(claim.citation_refs),
                }
                for claim in verification_input.claims
            ],
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "content_digest": item.content_digest,
                    "authority_class": item.authority_class,
                    "citation_metadata": dict(item.citation_metadata),
                    "content": content_map.get(evidence_id),
                }
                for evidence_id, item in sorted(evidence_by_id.items())
            ],
            "postconditions": [
                item.as_dict()
                for item in verification_input.postconditions
            ],
        }
        prompt = json_dumps_canonical(payload)
        schema = {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": [
                        "verified",
                        "qualified",
                        "abstain",
                        "repair",
                        "block",
                    ],
                },
                "reason_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 64,
                },
                "confidence_band": {
                    "type": "string",
                    "enum": ["high", "medium", "low", "unknown"],
                },
                "repair_instruction": {
                    "type": ["string", "null"],
                },
            },
            "required": [
                "outcome",
                "reason_codes",
                "confidence_band",
                "repair_instruction",
            ],
            "additionalProperties": False,
        }
        provider_request = ProviderRequest(
            instructions=(
                "Verify only the supplied candidate against supplied observable "
                "evidence and postconditions. Do not reveal chain-of-thought. "
                "Return only the requested structured verdict."
            ),
            prompt=prompt,
            max_output_tokens=self.max_output_tokens,
            model=self.model,
            data_class="internal",
            purpose="verification",
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            turn_id=request.turn_id,
            structured_output_schema=schema,
            tool_choice="none",
            deadline=request.deadline,
        )
        response = await self.provider.generate(provider_request)
        structured = response.structured_output
        if not isinstance(structured, Mapping):
            raise SemanticVerifierError(
                "canonical provider returned no structured verifier result"
            )
        try:
            outcome = VerificationOutcome(str(structured["outcome"]))
            confidence = ConfidenceBand(str(structured["confidence_band"]))
        except (KeyError, ValueError) as exc:
            raise SemanticVerifierError(
                "canonical provider returned invalid verifier enums"
            ) from exc
        reasons_raw = structured.get("reason_codes", ())
        if not isinstance(reasons_raw, list) or any(
            not isinstance(item, str)
            for item in reasons_raw
        ):
            raise SemanticVerifierError(
                "canonical provider returned invalid verifier reasons"
            )
        repair_instruction = structured.get("repair_instruction")
        if repair_instruction is not None and not isinstance(
            repair_instruction, str
        ):
            raise SemanticVerifierError(
                "canonical provider returned invalid repair instruction"
            )
        response_identity = (
            response.response_id
            or response.request_id
            or "unknown"
        )
        return SemanticVerificationDecision(
            outcome=outcome,
            reason_codes=tuple(reasons_raw),
            confidence_band=confidence,
            route_ref=(
                "provider:"
                + response.provider
                + ":"
                + str(response_identity)
            ),
            repair_instruction=repair_instruction,
        )


def json_dumps_canonical(value: Mapping[str, Any]) -> str:
    import json

    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _semantic_receipt(
    base: VerificationReceipt,
    decision: SemanticVerificationDecision,
    *,
    outcome: VerificationOutcome | None = None,
    extra_reason_codes: tuple[str, ...] = (),
    repair_directive: Mapping[str, object] | None = None,
) -> VerificationReceipt:
    return replace(
        base,
        outcome=decision.outcome if outcome is None else outcome,
        reason_codes=tuple(
            dict.fromkeys(
                base.reason_codes
                + decision.reason_codes
                + extra_reason_codes
            )
        ),
        verifier_route_refs=tuple(
            dict.fromkeys(
                base.verifier_route_refs + (decision.route_ref,)
            )
        ),
        repair_directive=repair_directive,
        confidence_band=decision.confidence_band,
        completed_at=datetime.now(timezone.utc),
    )


async def verify_with_semantic(
    runtime: VerificationRuntime,
    request: VerificationRequest,
    verification_input: DeterministicVerificationInput,
    *,
    semantic_verifier: SemanticVerifier | None,
    repair_callback: RepairCallback | None = None,
    now: datetime | None = None,
) -> VerificationRunResult:
    """Run deterministic checks then bounded semantic verification/repair."""

    current_request = request
    current_input = verification_input
    lineage: list[RepairAttempt] = []
    max_repairs_raw = request.budget.get("max_repairs", 0)
    max_repairs = (
        int(max_repairs_raw)
        if isinstance(max_repairs_raw, int)
        and not isinstance(max_repairs_raw, bool)
        and max_repairs_raw >= 0
        else 0
    )
    max_repairs = min(max_repairs, 3)

    while True:
        deterministic = runtime.verify_deterministic(
            current_request,
            current_input,
            now=now,
        )

        semantic_only_block = (
            deterministic.outcome is VerificationOutcome.BLOCK
            and deterministic.repair_directive is not None
            and deterministic.repair_directive.get("reason")
            == "semantic_high_impact_verifier_required"
            and not deterministic.reason_codes
        )

        if (
            current_request.required_level
            is not VerificationLevel.HIGH_IMPACT
        ):
            return VerificationRunResult(
                receipt=deterministic,
                candidate_text=current_input.candidate_text,
                repair_lineage=tuple(lineage),
            )

        if not semantic_only_block:
            return VerificationRunResult(
                receipt=deterministic,
                candidate_text=current_input.candidate_text,
                repair_lineage=tuple(lineage),
            )

        if semantic_verifier is None:
            return VerificationRunResult(
                receipt=deterministic,
                candidate_text=current_input.candidate_text,
                repair_lineage=tuple(lineage),
            )

        try:
            decision = await semantic_verifier.verify(
                current_request,
                current_input,
            )
        except Exception:
            failed = replace(
                deterministic,
                outcome=VerificationOutcome.BLOCK,
                reason_codes=tuple(
                    dict.fromkeys(
                        deterministic.reason_codes
                        + ("semantic_verifier_failed",)
                    )
                ),
                repair_directive=None,
                confidence_band=ConfidenceBand.UNKNOWN,
                completed_at=datetime.now(timezone.utc),
            )
            return VerificationRunResult(
                receipt=failed,
                candidate_text=current_input.candidate_text,
                repair_lineage=tuple(lineage),
            )

        if decision.outcome is VerificationOutcome.REPAIR:
            if (
                repair_callback is None
                or len(lineage) >= max_repairs
            ):
                exhausted = _semantic_receipt(
                    deterministic,
                    decision,
                    outcome=VerificationOutcome.BLOCK,
                    extra_reason_codes=("repair_budget_exhausted",),
                    repair_directive=None,
                )
                return VerificationRunResult(
                    receipt=exhausted,
                    candidate_text=current_input.candidate_text,
                    repair_lineage=tuple(lineage),
                )
            instruction = (
                decision.repair_instruction
                or "Repair the candidate using the verifier reason codes."
            )
            attempt = len(lineage) + 1
            repaired = await _await_value(
                repair_callback(
                    current_input.candidate_text,
                    instruction,
                    attempt,
                )
            )
            if not isinstance(repaired, str) or not repaired.strip():
                invalid = _semantic_receipt(
                    deterministic,
                    decision,
                    outcome=VerificationOutcome.BLOCK,
                    extra_reason_codes=("repair_callback_invalid",),
                    repair_directive=None,
                )
                return VerificationRunResult(
                    receipt=invalid,
                    candidate_text=current_input.candidate_text,
                    repair_lineage=tuple(lineage),
                )
            repaired_ref = (
                request.candidate_ref
                + ":repair:"
                + str(attempt)
            )
            lineage.append(
                RepairAttempt(
                    attempt=attempt,
                    parent_candidate_ref=current_request.candidate_ref,
                    repaired_candidate_ref=repaired_ref,
                    reason_codes=decision.reason_codes,
                    instruction=instruction,
                )
            )
            current_request = replace(
                current_request,
                candidate_ref=repaired_ref,
            )
            current_input = replace(
                current_input,
                candidate_text=repaired.strip(),
            )
            continue

        final = _semantic_receipt(
            deterministic,
            decision,
            repair_directive=None,
        )
        return VerificationRunResult(
            receipt=final,
            candidate_text=current_input.candidate_text,
            repair_lineage=tuple(lineage),
        )


__all__ = [
    "CanonicalProviderSemanticVerifier",
    "DeterministicVerificationInput",
    "RepairAttempt",
    "SemanticVerificationDecision",
    "SemanticVerifier",
    "SemanticVerifierError",
    "VerificationRunResult",
    "VerificationRuntime",
    "tool_receipt_postcondition",
    "verify_with_semantic",
]
