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
                     require_full_history, evidence=None, recheck=None):
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
    if backend.model_digest != model_digest:
        raise OfflineAIError("deliberation model identity changed")
    question = question.strip()
    context = None if evidence is None else evidence["context"]
    candidates = []
    deadline = time.monotonic() + MAX_SECONDS
    for mode, suffix in _STRATEGIES:
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
        preview = session.preview_context(prompt, output_tokens, grounding_context=context)
        if require_full_history and not preview["fits_full_history"]:
            raise OfflineAIError("deliberation cannot fit full conversation context")
        # Separate ephemeral session per candidate: no candidate-generated
        # history or mutated instructions enter the second inference.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deliberation deadline exceeded")
        answer = await asyncio.wait_for(session.ask(
            prompt, max_output_tokens=output_tokens, grounding_context=context,
            require_full_history=require_full_history,
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
        candidates.append(row)
    recheck()
    report = {
        "schema": SCHEMA, "question_sha256": _hash(question), "session_revision": revision,
        "model_digest": model_digest, "tokenizer_digest": tokenizer_digest,
        "candidate_output_budget": output_tokens,
        "reserved_total_output_tokens": 2*output_tokens,
        "actual_total_output_tokens": sum(row["output_tokens"] for row in candidates),
        "require_full_history": require_full_history, "generation_performed": True,
        "grounding_context_sha256": None if evidence is None else evidence["context_sha256"],
        "candidates": candidates, "comparison": _comparison(candidates),
        "transcript_committed": False, "tool_execution_authorized": False,
        "automatic_retry": False, "memory_saved": False,
    }
    report["report_sha256"] = _hash(_stable(report))
    return report
