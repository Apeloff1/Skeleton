"""Review-and-refine turns for the standalone local model.

This is not a second executor. Stage order, sibling isolation, receipts and
the publication gate stay with the canonical cooperation and verification
owners. Each stage is one call through ``LocalModelAdapter``, the local
provider boundary that reaches the loaded GGUF binding.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import threading
from collections.abc import Callable, Mapping
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


def _operation_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise LocalReviewError("one parent operation id is required")
    if any(ord(char) < 32 for char in value):
        raise LocalReviewError("one parent operation id is required")
    return value.strip()


def _ledger_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocalReviewError(f"{label} must be a non-negative integer")
    return value


def _ledger_cost(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocalReviewError(f"{label} must be a finite non-negative number")
    cost = float(value)
    if cost < 0 or cost != cost or cost in {float("inf"), float("-inf")}:
        raise LocalReviewError(f"{label} must be a finite non-negative number")
    return cost


def _ledger_flag(value: object) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value == 0 or value is None:
        return False
    raise LocalReviewError("stored review reservation is invalid")


def _ledger_row(row: Mapping[str, Any]) -> dict[str, Any]:
    digest_value = row.get("receipt_digest")
    if digest_value is not None and (
        not isinstance(digest_value, str) or len(digest_value) != 64
    ):
        raise LocalReviewError("stored review reservation is invalid")
    return {
        "output_tokens": _ledger_int(row.get("output_tokens"), "reserved output"),
        "attempts": _ledger_int(row.get("attempts"), "reserved attempts"),
        "cost_usd": _ledger_cost(row.get("cost_usd"), "reserved cost"),
        "receipt_digest": digest_value,
        "cancelled": _ledger_flag(row.get("cancelled")),
        "published": _ledger_flag(row.get("published")),
    }


class LocalReviewLedger:
    """Charge a reviewed operation until its response receipt exists.

    An absent response is not spare capacity. Cancellation and a later
    explicit re-authorization keep the original charge. They do not dispatch
    the same operation id again.
    """

    def __init__(
        self,
        *,
        output_tokens: int,
        attempts: int,
        cost_usd: float,
        rows: dict[str, dict[str, Any]] | None = None,
        persist: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.output_tokens = _ledger_int(output_tokens, "output capacity")
        self.attempts = _ledger_int(attempts, "attempt capacity")
        self.cost_usd = _ledger_cost(cost_usd, "cost capacity")
        self.rows: dict[str, dict[str, Any]] = {}
        if rows:
            for operation_id, row in rows.items():
                self.rows[_operation_id(operation_id)] = _ledger_row(row)
        self._persist = persist

    @classmethod
    def session(cls, store: Any) -> LocalReviewLedger:
        loaded = store.review_reservations()

        def persist(operation_id: str, row: dict[str, Any]) -> None:
            store.save_review_reservation(operation_id, row)

        return cls(
            output_tokens=1_048_576,
            attempts=10_000,
            cost_usd=1_000_000.0,
            rows=loaded,
            persist=persist,
        )

    def begin(
        self,
        operation_id: str,
        *,
        output_tokens: int,
        attempts: int,
        cost_usd: float,
    ) -> None:
        operation_id = _operation_id(operation_id)
        output_tokens = _ledger_int(output_tokens, "reserved output")
        attempts = _ledger_int(attempts, "reserved attempts")
        cost_usd = _ledger_cost(cost_usd, "reserved cost")
        existing = self.rows.get(operation_id)
        if existing is not None:
            if not existing.get("receipt_digest"):
                raise LocalReviewError(
                    "provider dispatch reservation already exists; physical outcome is uncertain"
                )
            raise LocalReviewError("operation id already has a response receipt")
        charged_output = sum(row["output_tokens"] for row in self.rows.values())
        charged_attempts = sum(row["attempts"] for row in self.rows.values())
        charged_cost = sum(row["cost_usd"] for row in self.rows.values())
        if (
            charged_output + output_tokens > self.output_tokens
            or charged_attempts + attempts > self.attempts
            or charged_cost + cost_usd > self.cost_usd + 1e-9
        ):
            raise LocalReviewError("uncertain reservation is not free capacity")
        self.rows[operation_id] = {
            "output_tokens": output_tokens,
            "attempts": attempts,
            "cost_usd": cost_usd,
            "receipt_digest": None,
            "cancelled": False,
            "published": False,
        }
        self._save(operation_id)

    def cancel(self, operation_id: str) -> None:
        operation_id = _operation_id(operation_id)
        row = self.rows.get(operation_id)
        if row is None:
            raise LocalReviewError("cancellation requires the original operation id")
        row["cancelled"] = True
        row["published"] = False
        self._save(operation_id)

    def settle(self, operation_id: str, receipt_digest: str, *, published: bool) -> None:
        operation_id = _operation_id(operation_id)
        row = self.rows.get(operation_id)
        if row is None:
            raise LocalReviewError("settlement requires the original operation id")
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            raise LocalReviewError("settlement requires the response receipt digest")
        if row.get("cancelled"):
            row["published"] = False
        else:
            row["receipt_digest"] = receipt_digest
            row["published"] = published is True
        self._save(operation_id)

    def reauthorize(self, operation_id: str) -> str:
        operation_id = _operation_id(operation_id)
        row = self.rows.get(operation_id)
        if row is None or row.get("receipt_digest"):
            raise LocalReviewError("re-authorization requires an uncertain reservation")
        new_id = "op-" + sha256(
            ("skeleton.local.review-reauthorize.v1:" + operation_id).encode("utf-8")
        ).hexdigest()[:32]
        if new_id == operation_id or new_id in self.rows:
            new_id = new_id + "-2"
        return new_id

    def _save(self, operation_id: str) -> None:
        if self._persist is not None:
            self._persist(operation_id, dict(self.rows[operation_id]))


def evidence_snapshot(
    manifest: Mapping[str, Any] | None,
) -> tuple[tuple[str, str], ...]:
    """Citation and passage digest pairs that distinguish one evidence snapshot."""
    if manifest is None:
        return ()
    citations = manifest.get("citations")
    if not isinstance(citations, list):
        raise LocalReviewError("grounded review requires supplied local citations")
    rows: list[tuple[str, str]] = []
    for item in citations:
        if not isinstance(item, Mapping):
            raise LocalReviewError("grounded citation is invalid")
        citation = item.get("citation")
        passage_sha = item.get("passage_sha256")
        if not isinstance(citation, str) or not isinstance(passage_sha, str):
            raise LocalReviewError("grounded citation is invalid")
        rows.append((citation, passage_sha))
    rows.sort()
    return tuple(rows)


def reviewed_request_identity(
    *,
    message: str,
    max_output_tokens: int,
    document_ids: tuple[str, ...] | None,
    policy: Mapping[str, object],
    history: tuple[tuple[str, str], ...],
    evidence: tuple[tuple[str, str], ...],
    nonce: str | None,
    instructions: str,
    require_full_history: bool,
) -> str:
    """Identity of one reviewed request. A new nonce is a different request."""
    normalized = normalize_cooperation_policy(dict(policy))
    if normalized is None:
        raise CooperationPolicyError("cooperation policy required")
    if not isinstance(message, str) or not message.strip():
        raise LocalReviewError("message must not be empty")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        raise LocalReviewError("output grant must be an integer")
    if not isinstance(instructions, str):
        raise LocalReviewError("instructions must be text")
    if type(require_full_history) is not bool:
        raise LocalReviewError("require_full_history must be a boolean")
    if nonce is not None and (
        not isinstance(nonce, str)
        or not nonce.strip()
        or len(nonce) > 128
        or any(ord(char) < 32 for char in nonce)
    ):
        raise LocalReviewError("review nonce must be bounded text")
    payload = {
        "schema": "skeleton.local.reviewed_request.v1",
        "message": message.strip(),
        "grant": max_output_tokens,
        "grounding_scope": list(document_ids) if document_ids else [],
        "policy": normalized,
        "history": [{"role": role, "content": content} for role, content in history],
        "evidence": [
            {"citation": citation, "passage_sha256": passage_sha}
            for citation, passage_sha in evidence
        ],
        "nonce": "" if nonce is None else nonce.strip(),
        "instructions": instructions,
        "require_full_history": require_full_history,
    }
    return sha256(canonical(payload).encode("utf-8")).hexdigest()


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


def _factual_sentence(sentence: str) -> bool:
    """A sentence the existing atom scorer can check against a passage."""
    from skeleton.intelligence.grounded_journey import _atoms, _is_hedge

    words, negations, numbers = _atoms(sentence)
    if not words and not numbers and not negations:
        return False
    return not _is_hedge(sentence, words, numbers)


def _sentence_claim(sentence: str, when: datetime, *, factual: bool) -> VerificationClaim:
    kind = ClaimKind.FACT if factual else ClaimKind.HYPOTHESIS
    risk = VerificationRisk.MEDIUM if factual else VerificationRisk.LOW
    return VerificationClaim(
        claim_id=str(uuid5(
            NAMESPACE_URL,
            "local-chat-claim:" + sha256(sentence.encode("utf-8")).hexdigest(),
        )),
        tenant_id=_TENANT,
        text=sentence,
        kind=kind,
        risk=risk,
        created_at=when,
        generated_by_model=True,
    )


def _passage_evidence(
    claim: VerificationClaim,
    binding: Mapping[str, Any],
    when: datetime,
) -> EvidenceReference:
    relation = (
        EvidenceRelation.SUPPORTS
        if binding.get("relation") == "supports"
        else EvidenceRelation.CONTRADICTS
    )
    citation = str(binding["citation"])
    origin = binding.get("document_id")
    if not isinstance(origin, str) or not origin.strip():
        origin = citation
    return EvidenceReference(
        evidence_id=str(uuid5(
            NAMESPACE_URL,
            "local-evidence:" + claim.claim_id + ":" + citation + ":" + relation.value,
        )),
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        source_id=citation,
        origin_id=origin.strip(),
        content_digest=str(binding["content_digest"]),
        locator=citation,
        relation=relation,
        producer=EvidenceProducer.SOURCE,
        observed_at=when,
    )


def _cited(sentence: str, citation: str) -> str:
    if citation in sentence:
        return sentence
    return sentence + " [" + citation + "]"


def _sentence_attributions(bound: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bindings = bound.get("bindings")
    if not isinstance(bindings, list):
        return rows
    for binding in bindings:
        if not isinstance(binding, Mapping) or not isinstance(binding.get("text"), str):
            continue
        relation = binding.get("relation")
        if relation not in {"supports", "contradicts"}:
            relation = "unsupported"
        citation = binding.get("citation")
        if relation == "unsupported" or not isinstance(citation, str) or not citation:
            citation = None
        score = binding.get("lexical_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            score = 0.0
        rows.append({
            "text": binding["text"],
            "relation": relation,
            "citation": citation,
            "lexical_score": round(float(score), 4),
        })
    return rows


def _decision(
    *,
    published: bool,
    disposition: FinalizationDisposition,
    outcome: str,
    text: str,
    faithfulness: str | None,
    source_verified: bool,
    attributions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    visible = text.strip() or _ABSTAIN
    if not visible:
        published = False
        disposition = FinalizationDisposition.ABSTAIN
        visible = _ABSTAIN
    if not published and disposition is FinalizationDisposition.PUBLISH:
        disposition = FinalizationDisposition.ABSTAIN
    return {
        "published": published,
        "verification_disposition": disposition.value,
        "verification_outcome": outcome,
        "text": visible,
        "independent_review_certified": False,
        "critique_is_verification": False,
        "source_verified": source_verified and published,
        "faithfulness_disposition": faithfulness,
        "sentence_attributions": list(attributions or []),
    }


def decide_local_publication(
    candidate: str,
    *,
    evidence_manifest: Mapping[str, Any] | None,
    verified_at: datetime | None = None,
    critique_text: str | None = None,
) -> dict[str, Any]:
    """Publish only sentences the existing verifier accepts against evidence.

    ``critique_text`` is accepted so callers can show that a glowing critique
    was present. It is not read. A positive critique cannot publish a failed,
    abstained, contradicted or unsupported draft.
    """
    del critique_text
    if not isinstance(candidate, str) or not candidate.strip():
        raise LocalReviewError("refined candidate is empty")
    when = verified_at or datetime.now(UTC)
    if when.tzinfo is None or when.utcoffset() is None:
        raise LocalReviewError("verification time must be timezone-aware")
    from skeleton.intelligence.grounded_journey import _claim_sentences

    sentences = _claim_sentences(candidate.strip()) or (candidate.strip(),)
    runtime = VerificationRuntime()
    if evidence_manifest is None:
        factual = [sentence for sentence in sentences if _factual_sentence(sentence)]
        if not factual:
            claim = _sentence_claim(candidate.strip(), when, factual=False)
            assessment = runtime.verify(
                claim,
                evidence=(),
                verified_at=when,
                verifier_id="local-chat:stage3",
            )
            passed = (
                assessment.outcome is VerificationOutcome.PASSED
                and assessment.policy_satisfied
            )
            return _decision(
                published=passed,
                disposition=(
                    FinalizationDisposition.PUBLISH if passed
                    else FinalizationDisposition.ABSTAIN
                ),
                outcome=assessment.outcome.value,
                text=candidate.strip() if passed else _UNPUBLISHED,
                faithfulness=None,
                source_verified=False,
            )
        outcome = VerificationOutcome.UNKNOWN
        for sentence in factual:
            assessment = runtime.verify(
                _sentence_claim(sentence, when, factual=True),
                evidence=(),
                verified_at=when,
                verifier_id="local-chat:stage3",
            )
            if assessment.outcome is VerificationOutcome.FAILED:
                outcome = VerificationOutcome.FAILED
                break
            if assessment.outcome is not VerificationOutcome.PASSED or not assessment.policy_satisfied:
                outcome = assessment.outcome
        # Empty evidence cannot pass a factual claim, even if a structural
        # policy would. The draft stays visible and is not source-verified.
        if outcome is VerificationOutcome.PASSED:
            outcome = VerificationOutcome.UNKNOWN
        return _decision(
            published=False,
            disposition=(
                FinalizationDisposition.BLOCK
                if outcome is VerificationOutcome.FAILED
                else FinalizationDisposition.ABSTAIN
            ),
            outcome=outcome.value,
            text=candidate.strip(),
            faithfulness=None,
            source_verified=False,
        )

    from skeleton.app.offline_grounding import bind_sentence_evidence

    bound = bind_sentence_evidence(candidate, dict(evidence_manifest))
    attributions = _sentence_attributions(bound)
    faithfulness = bound.get("disposition") if isinstance(bound.get("disposition"), str) else None
    contradicted = False
    contradicted_outcome = VerificationOutcome.FAILED
    supported: list[str] = []
    for binding in bound["bindings"]:
        sentence = str(binding["text"])
        if not _factual_sentence(sentence):
            continue
        relation = binding.get("relation")
        claim = _sentence_claim(sentence, when, factual=True)
        evidence: tuple[EvidenceReference, ...] = ()
        if relation in {"supports", "contradicts"} and isinstance(binding.get("content_digest"), str):
            evidence = (_passage_evidence(claim, binding, when),)
        assessment = runtime.verify(
            claim,
            evidence=evidence,
            verified_at=when,
            verifier_id="local-chat:stage3",
        )
        passed = (
            assessment.outcome is VerificationOutcome.PASSED
            and assessment.policy_satisfied
        )
        if relation == "contradicts" or assessment.outcome is VerificationOutcome.CONTESTED:
            contradicted = True
            contradicted_outcome = (
                assessment.outcome
                if assessment.outcome is not VerificationOutcome.PASSED
                else VerificationOutcome.FAILED
            )
            continue
        citation = binding.get("citation")
        if (
            relation == "supports"
            and passed
            and isinstance(citation, str)
            and citation
        ):
            supported.append(_cited(sentence, citation))
    if contradicted or faithfulness == "contested":
        visible_outcome = (
            contradicted_outcome
            if contradicted
            else VerificationOutcome.FAILED
        )
        if visible_outcome is VerificationOutcome.PASSED:
            visible_outcome = VerificationOutcome.FAILED
        return _decision(
            published=False,
            disposition=FinalizationDisposition.BLOCK,
            outcome=visible_outcome.value,
            text=_UNPUBLISHED,
            faithfulness="contested" if faithfulness is None else faithfulness,
            source_verified=False,
            attributions=attributions,
        )
    if not supported:
        return _decision(
            published=False,
            disposition=FinalizationDisposition.ABSTAIN,
            outcome=VerificationOutcome.UNKNOWN.value,
            text=_ABSTAIN,
            faithfulness=faithfulness,
            source_verified=False,
            attributions=attributions,
        )
    return _decision(
        published=True,
        disposition=FinalizationDisposition.PUBLISH,
        outcome=VerificationOutcome.PASSED.value,
        text=" ".join(supported),
        faithfulness=faithfulness,
        source_verified=True,
        attributions=attributions,
    )


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


def _assert_stage_context(
    adapter: LocalModelAdapter,
    instructions: str,
    history: tuple[tuple[str, str], ...],
    user_prompt: str,
    output_tokens: int,
) -> None:
    """Refuse a stage that does not fit. Do not shorten policy, evidence, or instructions."""
    from skeleton.ai.runtime.inference.local import (
        LocalInferenceRequest,
        LocalInputBudget,
        LocalInputBudgetError,
    )

    request = LocalInferenceRequest(
        prompt=user_prompt,
        instructions=instructions,
        history=history,
        max_output_tokens=output_tokens,
    )
    budget = LocalInputBudget.from_limits(adapter.generation_limits())
    counter = getattr(adapter.engine.model, "count_input_tokens", None)
    rendered = request.rendered_input
    tokens = counter(request) if callable(counter) else len(rendered.encode("utf-8")) + 1
    try:
        budget.validate_tokens(tokens, output_tokens)
    except LocalInputBudgetError as exc:
        raise LocalReviewError(str(exc)) from exc


def _stage_user_prompt(state: Mapping[str, object], grounding_context: str | None) -> str:
    user_prompt = stage_prompt(state)
    if grounding_context is not None:
        # Evidence stays in the user turn. It is never a system instruction.
        user_prompt = user_prompt + "\n\n" + grounding_context
    return user_prompt


def _missing_question_terms(question: str, passages: list[str]) -> tuple[str, ...]:
    from skeleton.app.offline_knowledge import _terms

    present: set[str] = set()
    for passage in passages:
        present.update(_terms(passage))
    return tuple(term for term in _terms(question) if term not in present)


def _hit_from_citation(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_id": item["document_id"],
        "title": item["title"],
        "document_sha256": item["document_sha256"],
        "chunk_index": item["chunk_index"],
        "char_start": item["char_start"],
        "char_end": item["char_end"],
        "passage": item["passage"],
        "score": 0.0,
        "citation": item["citation"],
    }


def _apply_second_hop(
    prompt: str,
    manifest: Mapping[str, Any],
    hops: list[dict[str, Any]],
    retrieve: Callable[[str], list[Any]] | None,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """One more local lexical retrieval when the question's terms are missing.

    The retriever must be an in-process lexical or SQLite search. This does
    not construct a vector index and does not claim semantic retrieval.
    """
    from skeleton.app.offline_grounding import MAX_EVIDENCE_HITS, prepare_evidence

    citations = manifest.get("citations")
    context = manifest.get("context")
    if not isinstance(citations, list) or not isinstance(context, str):
        raise LocalReviewError("grounded review requires supplied local citations")
    owned = dict(manifest)
    if retrieve is None:
        return owned, context, hops
    passages = [
        item["passage"]
        for item in citations
        if isinstance(item, Mapping) and isinstance(item.get("passage"), str)
    ]
    missing = _missing_question_terms(prompt, passages)
    if not missing:
        return owned, context, hops
    query = " ".join(missing)
    if len(query.encode("utf-8")) > 1024:
        query = query.encode("utf-8")[:1024].decode("utf-8", errors="ignore").strip()
    if not query:
        raise LocalReviewError("second retrieval hop failed closed")
    try:
        found = retrieve(query)
    except LocalReviewError:
        raise
    except Exception as exc:
        raise LocalReviewError("second retrieval hop failed closed") from exc
    if not isinstance(found, list):
        raise LocalReviewError("second retrieval hop failed closed")
    known = {
        item.get("citation")
        for item in citations
        if isinstance(item, Mapping)
    }
    fresh: list[dict[str, Any]] = []
    for hit in found:
        if not isinstance(hit, Mapping):
            raise LocalReviewError("second retrieval hop failed closed")
        citation = hit.get("citation")
        if isinstance(citation, str) and citation not in known:
            fresh.append(dict(hit))
            known.add(citation)
    room = MAX_EVIDENCE_HITS - len(citations)
    if fresh and room <= 0:
        raise LocalReviewError("second retrieval hop exceeds the local evidence cap")
    recorded = list(hops)
    if not fresh:
        recorded.append({
            "hop": 2,
            "query": query,
            "passage_ids": list(recorded[0]["passage_ids"]),
        })
        return owned, context, recorded
    merged = [
        _hit_from_citation(item)
        for item in citations
        if isinstance(item, Mapping)
    ] + fresh[:room]
    try:
        updated = prepare_evidence(
            prompt,
            str(manifest["request_digest"]),
            merged,
            str(manifest["model_digest"]),
            str(manifest["tokenizer_digest"]),
        )
    except LocalReviewError:
        raise
    except Exception as exc:
        raise LocalReviewError("second retrieval hop failed closed") from exc
    recorded.append({
        "hop": 2,
        "query": query,
        "passage_ids": [item["citation"] for item in updated["citations"]],
    })
    return updated, updated["context"], recorded


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
    ledger: LocalReviewLedger | None = None,
    cancel: threading.Event | None = None,
    retrieve: Callable[[str], list[Any]] | None = None,
    request_identity: str | None = None,
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
    if request_identity is not None and (
        not isinstance(request_identity, str)
        or len(request_identity) != 64
        or any(char not in "0123456789abcdef" for char in request_identity)
    ):
        raise LocalReviewError("reviewed request identity is invalid")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise LocalReviewError("cancellation requires the original operation event")
    if ledger is not None and not isinstance(ledger, LocalReviewLedger):
        raise LocalReviewError("review ledger is invalid")
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
    # Fit is checked on the full stage prompt. Nothing is shortened to squeeze
    # the cooperation policy, the untrusted evidence, or the system instructions
    # into the activated context.
    first_share = _stage_share(remaining, len(stages), ceiling, model_limit)
    _assert_stage_context(
        adapter, instructions, history,
        _stage_user_prompt(state, grounding_context), first_share,
    )
    if cancel is not None and cancel.is_set():
        raise asyncio.CancelledError()
    reserved = False
    try:
        if ledger is not None:
            ledger.begin(
                operation_id,
                output_tokens=max_output_tokens,
                attempts=len(stages),
                cost_usd=0.0,
            )
            reserved = True
        hopped = False
        retrieval_hops: list[dict[str, Any]] | None = None
        if evidence_manifest is not None:
            retrieval_hops = [{
                "hop": 1,
                "query": prompt.strip(),
                "passage_ids": list(snapshot),
            }]
        for index, _stage in enumerate(stages):
            if cancel is not None and cancel.is_set():
                raise asyncio.CancelledError()
            if datetime.now(UTC).timestamp() >= deadline:
                raise LocalReviewError("parent review deadline elapsed before the next stage")
            if (
                not hopped
                and stages[index][1] == "draft"
                and evidence_manifest is not None
                and retrieval_hops is not None
            ):
                evidence_manifest, grounding_context, retrieval_hops = _apply_second_hop(
                    prompt.strip(), evidence_manifest, retrieval_hops, retrieve,
                )
                hopped = True
            share = _stage_share(remaining, len(stages) - index, ceiling, model_limit)
            user_prompt = _stage_user_prompt(state, grounding_context)
            _assert_stage_context(adapter, instructions, history, user_prompt, share)
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
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError()
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
        if evidence_manifest is None and decision["source_verified"] is not False:
            raise LocalReviewError("ungrounded review was labeled source-verified")
        if decision["published"] and decision["source_verified"] is not True and evidence_manifest is not None:
            raise LocalReviewError("grounded publication is missing its evidence verdict")
        if decision.get("independent_review_certified") is not False:
            raise LocalReviewError("critique was treated as verification")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "published": decision["published"],
            "verification_disposition": decision["verification_disposition"],
            "verification_outcome": decision["verification_outcome"],
            "independent_review_certified": False,
            "critique_is_verification": False,
            "source_verified": bool(decision["source_verified"]),
            "faithfulness_disposition": decision["faithfulness_disposition"],
            "sentence_attributions": decision["sentence_attributions"],
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
        if request_identity is not None:
            receipt["request_identity"] = request_identity
        if retrieval_hops is not None:
            receipt["retrieval_hops"] = retrieval_hops
        encoded = canonical(receipt)
        if len(encoded.encode("utf-8")) > 700_000:
            raise LocalReviewError("cooperation receipt exceeds its storage bound")
        # Re-parse so callers cannot mutate the recorded receipt.
        frozen = json.loads(encoded)
        digest_value = _receipt_digest(frozen)
        if ledger is not None and reserved:
            ledger.settle(
                operation_id,
                digest_value,
                published=bool(decision["published"]),
            )
            if ledger.rows[operation_id].get("cancelled"):
                raise asyncio.CancelledError()
        result = LocalCooperationResult(
            text=decision["text"],
            published=bool(decision["published"]) and not (
                ledger is not None and ledger.rows[operation_id].get("cancelled")
            ),
            verification_disposition=str(decision["verification_disposition"]),
            verification_outcome=str(decision["verification_outcome"]),
            input_tokens=consumed_input,
            output_tokens=consumed_output,
            execution_receipt_digest=digest_value,
            receipt=frozen,
        )
    except asyncio.CancelledError:
        # Stop stays on the original operation. The charge is not returned
        # and no partial stage becomes the canonical answer.
        if ledger is not None and reserved:
            ledger.cancel(operation_id)
        raise
    return result


__all__ = [
    "RECEIPT_SCHEMA",
    "LocalCooperationResult",
    "LocalReviewError",
    "LocalReviewLedger",
    "bind_cooperation_digest",
    "compose_offline_request_digest",
    "decide_local_publication",
    "evidence_snapshot",
    "reviewed_request_identity",
    "run_local_cooperation",
]
