"""Review-and-refine turns for the standalone local model.

This is not a second executor. Stage order, sibling isolation, receipts and
the publication gate stay with the canonical cooperation and verification
owners. Each stage is one call through ``LocalModelAdapter``, the local
provider boundary that reaches the loaded GGUF binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from collections.abc import Mapping
from typing import Any
from uuid import NAMESPACE_URL, uuid5

UTC = timezone.utc

from skeleton.ai.runtime.inference.local import LocalModelAdapter
from skeleton.contracts.verification import (
    ClaimKind,
    EvidenceProducer,
    EvidenceReference,
    EvidenceRelation,
    VerificationClaim,
    VerificationOutcome,
    VerificationRisk,
)
from skeleton.intelligence.admission import ResourceBudget
from skeleton.intelligence.cooperation import (
    SCHEMA,
    CooperationPolicyError,
    canonical,
    cooperation_stages,
    cooperation_summary,
    initial_cooperation_state,
    normalize_cooperation_policy,
    stage_prompt,
    validate_cooperation_state,
    validate_cooperation_summary,
)
from skeleton.intelligence.verification_runtime import (
    FinalizationDisposition,
    VerificationRuntime,
)
from skeleton.provider_runtime import AIMessage, ProviderRequest

RECEIPT_SCHEMA = "skeleton.local.cooperation_receipt.v1"
_STAGE_FLOOR = 64
_TENANT = "local-standalone"
_ABSTAIN = "The supplied local sources do not establish an answer."
_CONTRADICTION = (
    "A supplied source contradicts the model draft. "
    "The grounded answer does not adopt it."
)
_UNPUBLISHED = (
    "The refined draft was not published. "
    "Verification did not pass, and the critique is not that decision."
)


class LocalReviewError(ValueError):
    """A local reviewed turn cannot be admitted or published."""


@dataclass(frozen=True, slots=True)
class LocalCooperationResult:
    text: str
    published: bool
    verification_disposition: str
    verification_outcome: str
    input_tokens: int
    output_tokens: int
    execution_receipt_digest: str
    receipt: dict[str, Any]


def bind_cooperation_digest(digest: str, policy: Mapping[str, object]) -> str:
    """Domain-separate a reviewed turn from an ordinary turn with the same id."""
    normalized = normalize_cooperation_policy(dict(policy))
    if normalized is None:
        raise CooperationPolicyError("cooperation policy required")
    if not isinstance(digest, str) or len(digest) != 64:
        raise CooperationPolicyError("invalid request digest")
    material = "skeleton.offline-cooperation-request.v1:" + digest + ":" + canonical(normalized)
    return sha256(material.encode("utf-8")).hexdigest()


def compose_offline_request_digest(
    message: str,
    max_output_tokens: int,
    *,
    grounded: bool,
    document_ids: tuple[str, ...] | None,
    require_full_history: bool,
    cooperation: Mapping[str, object] | None,
) -> tuple[str, dict[str, object] | None]:
    """Build the durable request digest shared by replay, evidence and SQLite."""
    from skeleton.ai.model_runtime.offline_chat import _digest_request
    from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
    from skeleton.app.local_ai import _strict_context_digest
    from skeleton.app.offline_grounding import (
        grounded_request_digest,
        scoped_grounded_request_digest,
    )

    if not isinstance(message, str) or not message.strip():
        raise LocalReviewError("message must not be empty")
    digest = _digest_request(
        message.strip(), GenerationConfig(max_new_tokens=max_output_tokens),
    )
    if grounded:
        digest = grounded_request_digest(digest)
        digest = scoped_grounded_request_digest(digest, document_ids)
    digest = _strict_context_digest(digest, require_full_history)
    if cooperation is None:
        return digest, None
    policy = normalize_cooperation_policy(cooperation)
    if policy is None:
        raise CooperationPolicyError("cooperation policy required")
    return bind_cooperation_digest(digest, policy), policy


def _context_digest(prompt: str, history: tuple[tuple[str, str], ...], snapshot: object) -> str:
    payload = {
        "prompt": prompt,
        "history": [{"role": role, "content": content} for role, content in history],
        "source_snapshot": snapshot,
    }
    return sha256(canonical(payload).encode("utf-8")).hexdigest()


def _kept_grounded_text(faithfulness: Mapping[str, Any]) -> tuple[str, bool]:
    """Drop sentences the supplied passages do not establish."""
    disposition = faithfulness.get("disposition")
    claims = faithfulness.get("claims")
    if disposition == "supported" and isinstance(faithfulness.get("published_text"), str):
        return str(faithfulness["published_text"]), True
    if disposition == "qualified" and isinstance(claims, list):
        kept = [
            str(claim["text"])
            for claim in claims
            if isinstance(claim, Mapping)
            and claim.get("status") in {"supported", "hedged", "non_factual"}
            and isinstance(claim.get("text"), str)
        ]
        text = " ".join(kept).strip()
        if text:
            return text, True
        return _ABSTAIN, False
    if disposition == "contested":
        return _CONTRADICTION, False
    return _ABSTAIN, False


def _contradicting_evidence(
    claim: VerificationClaim,
    citation: str,
    when: datetime,
) -> EvidenceReference:
    body = "supplied local source contradicts the model draft"
    return EvidenceReference(
        evidence_id=str(uuid5(NAMESPACE_URL, "local-contradiction:" + claim.claim_id + ":" + citation)),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id=citation[:2048],
        origin_id=citation[:2048],
        content_digest=sha256(body.encode("utf-8")).hexdigest(),
        locator=citation[:4096],
        relation=EvidenceRelation.CONTRADICTS,
        producer=EvidenceProducer.SOURCE,
        observed_at=when,
    )


def decide_local_publication(
    candidate: str,
    *,
    evidence_manifest: Mapping[str, Any] | None,
    verified_at: datetime | None = None,
    critique_text: str | None = None,
) -> dict[str, Any]:
    """Publish only when the existing verifier passes.

    ``critique_text`` is accepted so callers can show that a glowing critique
    was present. It is not read. A positive critique cannot publish a failed,
    abstained or unsupported draft.
    """
    del critique_text
    if not isinstance(candidate, str) or not candidate.strip():
        raise LocalReviewError("refined candidate is empty")
    when = verified_at or datetime.now(UTC)
    if when.tzinfo is None or when.utcoffset() is None:
        raise LocalReviewError("verification time must be timezone-aware")
    faithfulness = None
    grounded_text = candidate.strip()
    grounded_ok = True
    if evidence_manifest is not None:
        from skeleton.app.offline_grounding import audit_answer_faithfulness

        faithfulness = audit_answer_faithfulness(candidate, dict(evidence_manifest))
        grounded_text, grounded_ok = _kept_grounded_text(faithfulness)
    claim = VerificationClaim(
        claim_id=str(uuid5(
            NAMESPACE_URL,
            "local-chat-claim:" + sha256(candidate.strip().encode("utf-8")).hexdigest(),
        )),
        tenant_id=_TENANT,
        text=candidate.strip(),
        kind=ClaimKind.HYPOTHESIS,
        risk=VerificationRisk.LOW,
        created_at=when,
        generated_by_model=True,
    )
    evidence: tuple[EvidenceReference, ...] = ()
    if isinstance(faithfulness, Mapping) and faithfulness.get("disposition") == "contested":
        claims = faithfulness.get("claims")
        citation = "local-source"
        if isinstance(claims, list):
            for item in claims:
                if isinstance(item, Mapping) and item.get("status") == "contradicted":
                    raw = item.get("citation")
                    if isinstance(raw, str) and raw.strip():
                        citation = raw.strip()
                    break
        evidence = (_contradicting_evidence(claim, citation, when),)
    assessment = VerificationRuntime().verify(
        claim,
        evidence=evidence,
        verified_at=when,
        verifier_id="local-chat:stage3",
    )
    verified = (
        assessment.outcome is VerificationOutcome.PASSED
        and assessment.policy_satisfied
    )
    if not verified:
        disposition = (
            FinalizationDisposition.BLOCK
            if assessment.outcome is VerificationOutcome.FAILED
            else FinalizationDisposition.ABSTAIN
        )
        visible = _UNPUBLISHED
        published = False
    elif not grounded_ok:
        disposition = (
            FinalizationDisposition.BLOCK
            if isinstance(faithfulness, Mapping) and faithfulness.get("disposition") == "contested"
            else FinalizationDisposition.ABSTAIN
        )
        visible = grounded_text
        published = False
    else:
        disposition = FinalizationDisposition.PUBLISH
        visible = grounded_text
        published = True
    if not visible.strip():
        visible = _ABSTAIN
        published = False
        disposition = FinalizationDisposition.ABSTAIN
    return {
        "published": published,
        "verification_disposition": disposition.value,
        "verification_outcome": assessment.outcome.value,
        "text": visible,
        "independent_review_certified": False,
        "critique_is_verification": False,
        "faithfulness_disposition": (
            None if faithfulness is None else faithfulness.get("disposition")
        ),
    }


def _stage_share(remaining: int, stages_left: int, ceiling: int, model_limit: int) -> int:
    if remaining < _STAGE_FLOOR * stages_left:
        raise LocalReviewError(
            "parent output grant cannot cover the remaining review stages"
        )
    share = min(ceiling, model_limit, remaining // stages_left)
    if share < _STAGE_FLOOR:
        raise LocalReviewError("stage output share is below the 64-token floor")
    return share


def _receipt_digest(receipt: Mapping[str, Any]) -> str:
    return sha256(canonical(dict(receipt)).encode("utf-8")).hexdigest()


async def run_local_cooperation(
    adapter: LocalModelAdapter,
    *,
    prompt: str,
    history: tuple[tuple[str, str], ...],
    instructions: str,
    policy: Mapping[str, object],
    max_output_tokens: int,
    operation_id: str,
    grounding_context: str | None = None,
    evidence_manifest: Mapping[str, Any] | None = None,
) -> LocalCooperationResult:
    """Run plan, drafts and critique/refine under one parent grant."""
    if not isinstance(adapter, LocalModelAdapter):
        raise LocalReviewError("local review requires the canonical local provider adapter")
    if not isinstance(instructions, str):
        raise LocalReviewError("instructions must be text")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise LocalReviewError("one parent operation id is required")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        raise LocalReviewError("output grant must be an integer")
    normalized = normalize_cooperation_policy(policy)
    if normalized is None:
        raise CooperationPolicyError("cooperation policy required")
    roles = normalized["roles"]
    if isinstance(roles, Mapping):
        for role, pair in roles.items():
            if (
                not isinstance(pair, Mapping)
                or pair.get("provider_id") != adapter.provider_id
                or pair.get("model_id") != adapter.model
            ):
                raise LocalReviewError(
                    f"cooperation role {role} is not the activated local model"
                )
    stages = cooperation_stages(normalized)
    if max_output_tokens < _STAGE_FLOOR * len(stages):
        raise LocalReviewError(
            f"reviewed local turn needs at least {_STAGE_FLOOR * len(stages)} "
            f"output tokens for {len(stages)} stages"
        )
    ceiling = int(normalized["max_stage_output_tokens"])
    limits = adapter.generation_limits()
    model_limit = int(limits["max_output_tokens"])
    if any(
        not isinstance(role, str) or not isinstance(content, str) or not content.strip()
        or role not in {"user", "assistant"}
        for role, content in history
    ):
        raise LocalReviewError("local review history is invalid")
    if grounding_context is not None and (
        not isinstance(grounding_context, str) or not grounding_context.strip()
    ):
        raise LocalReviewError("grounding context must be untrusted user text")
    snapshot: list[str] = []
    if evidence_manifest is not None:
        citations = evidence_manifest.get("citations")
        if not isinstance(citations, list) or not citations:
            raise LocalReviewError("grounded review requires supplied local citations")
        for item in citations:
            if not isinstance(item, Mapping) or not isinstance(item.get("citation"), str):
                raise LocalReviewError("grounded citation is invalid")
            snapshot.append(item["citation"])
    history_rows = [{"role": role, "content": content} for role, content in history]
    context_digest = _context_digest(prompt.strip(), history, snapshot)
    state = initial_cooperation_state(
        normalized,
        prompt=prompt.strip(),
        history=history_rows,
        context_digest=context_digest,
        source_snapshot=snapshot,
    )
    parent = ResourceBudget(
        max_output_tokens=max_output_tokens,
        max_provider_attempts=max(len(stages), 1),
        max_cost_usd=0.0,
        max_wall_seconds=max(30.0, 30.0 * len(stages)),
    )
    deadline = datetime.now(UTC).timestamp() + parent.max_wall_seconds
    messages = tuple(AIMessage(role=role, content=content) for role, content in history)
    consumed_output = 0
    consumed_input = 0
    remaining = max_output_tokens
    receipts: list[str] = []
    critique_text = ""
    for index, _stage in enumerate(stages):
        if datetime.now(UTC).timestamp() >= deadline:
            raise LocalReviewError("parent review deadline elapsed before the next stage")
        share = _stage_share(remaining, len(stages) - index, ceiling, model_limit)
        user_prompt = stage_prompt(state)
        if grounding_context is not None:
            # Evidence stays in the user turn. It is never a system instruction.
            user_prompt = user_prompt + "\n\n" + grounding_context
        response = await adapter.generate(ProviderRequest(
            instructions=instructions,
            prompt=user_prompt,
            history=messages,
            max_output_tokens=share,
            model=adapter.model,
            operation_id=operation_id,
            execution_id=operation_id,
            turn_id=stages[index][0],
            resource_budget=parent,
            deadline=datetime.fromtimestamp(deadline, UTC),
            tool_choice="none",
        ))
        text = response.text.strip() if isinstance(response.text, str) else ""
        provider_receipt = response.response_id or response.request_id
        if (
            not text
            or not isinstance(provider_receipt, str)
            or not provider_receipt.strip()
            or response.provider != adapter.provider_id
            or response.model != adapter.model
        ):
            raise LocalReviewError("local stage did not return a bound provider receipt")
        used_output = response.usage.output_tokens
        used_input = response.usage.input_tokens
        if (
            isinstance(used_output, bool) or not isinstance(used_output, int)
            or isinstance(used_input, bool) or not isinstance(used_input, int)
            or used_output < 0 or used_input < 0
            or used_output > share or used_output > remaining
        ):
            raise LocalReviewError("local stage usage escaped the parent grant")
        artifacts = list(state["artifacts"])
        artifacts.append({
            "stage_id": stages[index][0],
            "role": stages[index][1],
            "text": text,
            "output_digest": sha256(text.encode("utf-8")).hexdigest(),
            "request_digest": sha256(user_prompt.encode("utf-8")).hexdigest(),
            "provider_receipt": provider_receipt,
            "provider": response.provider,
            "model": response.model,
        })
        state = {
            **state,
            "cursor": index + 1,
            "artifacts": artifacts,
        }
        state = validate_cooperation_state(
            state,
            normalized,
            context_digest=context_digest,
            source_snapshot=snapshot,
        )
        if stages[index][1] == "critique":
            critique_text = text
        receipts.append(provider_receipt)
        consumed_output += used_output
        consumed_input += used_input
        remaining -= used_output
        if consumed_output > max_output_tokens or remaining < 0:
            raise LocalReviewError("review stages exceeded the parent output grant")
    summary = validate_cooperation_summary(
        cooperation_summary(state),
        normalized,
        snapshot,
        receipts,
    )
    if summary.get("complete") is not True or summary.get("independent_review_certified") is not False:
        raise LocalReviewError("cooperation summary is not a complete advisory record")
    candidate = str(state["artifacts"][-1]["text"])
    decision = decide_local_publication(
        candidate,
        evidence_manifest=evidence_manifest,
        critique_text=critique_text,
    )
    if decision["published"] and decision["verification_outcome"] != VerificationOutcome.PASSED.value:
        raise LocalReviewError("a non-passing verification cannot publish")
    if decision["critique_is_verification"] is not False or decision["independent_review_certified"] is not False:
        raise LocalReviewError("critique was treated as verification")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "published": decision["published"],
        "verification_disposition": decision["verification_disposition"],
        "verification_outcome": decision["verification_outcome"],
        "independent_review_certified": False,
        "critique_is_verification": False,
        "faithfulness_disposition": decision["faithfulness_disposition"],
        "model": {"provider": adapter.provider_id, "model": adapter.model},
        "parent_grant": {
            "operation_id": operation_id,
            "max_output_tokens": max_output_tokens,
            "consumed_output_tokens": consumed_output,
            "stage_output_ceiling": ceiling,
        },
        "summary": summary,
        "stages": [
            {
                "stage_id": artifact["stage_id"],
                "role": artifact["role"],
                "text": artifact["text"],
                "provider": artifact["provider"],
                "model": artifact["model"],
                "provider_receipt": artifact["provider_receipt"],
                "output_digest": artifact["output_digest"],
            }
            for artifact in state["artifacts"]
        ],
    }
    encoded = canonical(receipt)
    if len(encoded.encode("utf-8")) > 700_000:
        raise LocalReviewError("cooperation receipt exceeds its storage bound")
    # Re-parse so callers cannot mutate the recorded receipt.
    frozen = json.loads(encoded)
    return LocalCooperationResult(
        text=decision["text"],
        published=bool(decision["published"]),
        verification_disposition=str(decision["verification_disposition"]),
        verification_outcome=str(decision["verification_outcome"]),
        input_tokens=consumed_input,
        output_tokens=consumed_output,
        execution_receipt_digest=_receipt_digest(frozen),
        receipt=frozen,
    )


__all__ = [
    "RECEIPT_SCHEMA",
    "LocalCooperationResult",
    "LocalReviewError",
    "bind_cooperation_digest",
    "compose_offline_request_digest",
    "decide_local_publication",
    "run_local_cooperation",
]
