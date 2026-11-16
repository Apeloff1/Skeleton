"""Bounded real local-model deliberation over immutable conversation context.

Two independently executed text-only candidates: direct analysis and
counterpoint. No candidate is fed into the other, converted into an
instruction, committed to history, or treated as an independent truth judge.
The existing inference engine and model authority execute both candidates.
"""
from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import time
import re

from skeleton.app.local_ai import OfflineAISession, OfflineAIError
from skeleton.app.offline_grounding import audit_answer_citations, audit_answer_faithfulness

SCHEMA = "skeleton.jeeves.deliberation-review.v1"
MAX_CANDIDATE_TOKENS = 128
MAX_TOTAL_TOKENS = 256
MAX_SECONDS = 45
_STRATEGIES = (
    ("direct", "Review approach: answer the request directly and identify key assumptions."),
    ("counterpoint", "Review approach: examine an alternative explanation or solution; identify uncertainty and failure modes."),
)
_ADAPTIVE_STRATEGIES = _STRATEGIES + (
    ("decompose", "Review approach: decompose the task into independently checkable subproblems before finalizing."),
    ("recompute", "Review approach: independently recompute the result and check the explicit output contract."),
)



def _hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def _stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _pin(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _request(question, instruction):
    return question + "\n\n" + instruction


def _comparison(candidates):
    """Surface disagreement and evidence audits, never a fabricated winner."""
    direct, other = candidates
    return {
        "identical_output": direct["output_sha256"] == other["output_sha256"],
        "both_returned_text": True,
        "candidate_count": 2,
        "distinct_strategy_count": 2,
        "independent_model_count": 1,
        "answer_selected": False,
        "semantic_truth_verified": False,
        "selection_authority": "operator-review-only",
    }


async def deliberate(backend, question, *, history, instructions, revision,
                     model_digest, tokenizer_digest, output_tokens,
                     require_full_history, evidence=None, recheck=None, adaptive=None,
                     history_policy="recent"):
    """Execute both strategies with a shared cooperative wall/token budget.

    The HTTP owner holds the existing single-model lease and checks the
    durable conversation/source snapshot on each side of execution.
    """
    if (type(question) is not str or not question.strip()
            or len(question.encode("utf-8")) > 1024
            or type(output_tokens) is not int
            or not 1 <= output_tokens <= MAX_CANDIDATE_TOKENS
            or type(history) is not tuple or type(instructions) is not str
            or type(revision) is not int or revision < 0
            or not _pin(model_digest) or not _pin(tokenizer_digest)
            or type(require_full_history) is not bool or not callable(recheck)):
        raise OfflineAIError("invalid bounded deliberation request")
    if history_policy not in ("recent", "relevance") or (history_policy == "relevance" and require_full_history):
        raise OfflineAIError("relevance packing requires explicit lossy review context")
    if backend.model_digest != model_digest:
        raise OfflineAIError("deliberation model identity changed")
    question = question.strip()
    context = None if evidence is None else evidence["context"]
    policy = None
    if adaptive is not None:
        from skeleton.app.jeeves_constraints import normalize_policy, prompt_suffix, assess, digest
        try:
            policy = normalize_policy(adaptive, output_tokens)
        except ValueError as exc:
            raise OfflineAIError("invalid adaptive reasoning policy") from exc
    if policy is not None and policy["contract"]["kind"] == "source_quotes":
        if evidence is None:
            raise OfflineAIError("exact source quote contract requires grounded review")
        origins = {c["document_id"] for c in evidence["citations"]}
        if len(origins) < policy["contract"]["minimum_distinct_sources"]:
            raise OfflineAIError("insufficient admitted source diversity")
    candidates = []
    reserved = 0
    stop_reason = "strategy_limit"
    deadline = time.monotonic() + MAX_SECONDS
    strategies = _STRATEGIES if policy is None else _ADAPTIVE_STRATEGIES[:policy["max_attempts"]]
    total_budget = MAX_TOTAL_TOKENS if policy is None else policy["maximum_reserved_tokens"]
    for mode, suffix in strategies:
        if reserved + output_tokens > total_budget:
            stop_reason = "token_budget"
            break
        if policy is not None:
            suffix += prompt_suffix(policy)
            # Only a fixed verifier diagnostic may guide the next independent
            # attempt. Never use candidate output as an instruction.
            if candidates and policy["contract"]["kind"] != "review":
                previous = candidates[-1]["verification"]["code"]
                if previous not in ("numeric_mismatch", "invalid_numeric_format",
                                    "invalid_artifact_schema", "invalid_source_quotes"):
                    raise OfflineAIError("unexpected verifier diagnostic")
                suffix += " Prior independent verification failed (" + previous + "). Recompute independently."
        reserved += output_tokens
        recheck()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deliberation deadline exceeded")
        session = OfflineAISession(backend)
        if session.tokenizer_digest != tokenizer_digest:
            raise OfflineAIError("deliberation tokenizer identity changed")
        session.history = history
        session.instructions = instructions
        prompt = _request(question, suffix)
        packing = None
        if history_policy == "relevance":
            from skeleton.app.jeeves_history_pack import pack_history
            def fits(trial):
                session.history = trial
                try:
                    trial_report = session.preview_context(prompt, output_tokens, grounding_context=context)
                except OfflineAIError:
                    return False
                return trial_report["fits_full_history"] is True
            try:
                selected, packing = pack_history(question, history, fits=fits)
            except ValueError as exc:
                raise OfflineAIError("relevance context admission failed") from exc
            session.history = selected
        preview = session.preview_context(prompt, output_tokens, grounding_context=context)
        if (require_full_history or history_policy == "relevance") and not preview["fits_full_history"]:
            raise OfflineAIError("deliberation cannot fit full conversation context")
        # Separate ephemeral session per candidate: no candidate-generated
        # history or mutated instructions enter the second inference.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deliberation deadline exceeded")
        answer = await asyncio.wait_for(session.ask(
            prompt, max_output_tokens=output_tokens, grounding_context=context,
            require_full_history=require_full_history or history_policy == "relevance",
        ), timeout=remaining)
        recheck()
        if time.monotonic() > deadline:
            raise TimeoutError("deliberation deadline exceeded")
        if (answer.model_digest != model_digest or not _pin(answer.execution_receipt_digest)
                or type(answer.output_tokens) is not int
                or not 0 <= answer.output_tokens <= output_tokens
                or type(answer.input_tokens) is not int or answer.input_tokens < 1
                or not isinstance(answer.text, str) or not answer.text.strip()
                or len(answer.text.encode("utf-8")) > 16384):
            raise OfflineAIError("deliberation returned an unbound candidate")
        row = {
            "strategy": mode, "strategy_text": suffix, "text": answer.text,
            "output_sha256": _hash(answer.text), "question_variant_sha256": _hash(prompt),
            "execution_receipt_digest": answer.execution_receipt_digest,
            "input_tokens": answer.input_tokens, "output_tokens": answer.output_tokens,
            "estimated_history_retained": preview["retained_history_messages"],
            "citation_audit": None if evidence is None else audit_answer_citations(answer.text, evidence),
            "faithfulness": None if evidence is None else audit_answer_faithfulness(answer.text, evidence),
        }
        if packing is not None:
            row["history_packing"] = packing
        if policy is not None:
            row["verification"] = assess(answer.text, policy["contract"], evidence=evidence)
        candidates.append(row)
        if policy is not None and row["verification"]["passed"]:
            stop_reason = "explicit_contract_passed"
            break
    recheck()
    if not candidates:
        raise OfflineAIError("no admitted reasoning candidate")
    comparison = _comparison(candidates) if policy is None else {
        "identical_output": len({row["output_sha256"] for row in candidates}) == 1,
        "candidate_count": len(candidates), "distinct_strategy_count": len(candidates),
        "independent_model_count": 1, "answer_selected": False,
        "semantic_truth_verified": False,
        "selection_authority": "operator-review-only",
    }
    report = {
        "schema": SCHEMA, "question_sha256": _hash(question), "session_revision": revision,
        "model_digest": model_digest, "tokenizer_digest": tokenizer_digest,
        "candidate_output_budget": output_tokens,
        "reserved_total_output_tokens": reserved,
        "actual_total_output_tokens": sum(row["output_tokens"] for row in candidates),
        "require_full_history": require_full_history, "generation_performed": True,
        "history_policy": history_policy,
        "grounding_context_sha256": None if evidence is None else evidence["context_sha256"],
        "evidence_sources": [] if evidence is None else evidence["citations"],
        "candidates": candidates, "comparison": comparison,
        "transcript_committed": False, "tool_execution_authorized": False,
        "automatic_retry": False, "memory_saved": False,
    }
    if policy is not None:
        report["schema"] = "skeleton.jeeves.adaptive-review.v1"
        report["adaptive"] = {
            "policy": policy, "policy_sha256": digest(policy),
            "stop_reason": stop_reason,
            "maximum_reserved_tokens": total_budget,
            "attempts": len(candidates),
            "contract_passed": any(row["verification"]["passed"] for row in candidates),
            "contract_scope_only": True, "candidate_text_reinjected": False,
        }
    from skeleton.app.jeeves_candidate_challenge import examine
    report["candidate_challenge"] = examine(candidates)
    report["report_sha256"] = _hash(_stable(report))
    return report
