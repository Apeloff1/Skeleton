"""Bounded prompt envelope. Lower-trust retrieval never becomes instructions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .budgets import Quota
from .contracts import require_text
from .errors import deny


@dataclass(frozen=True, slots=True)
class ContextSlice:
    text: str
    source_sha: str
    cited: bool
    approved: bool = False

    @classmethod
    def from_text(cls, text: str, *, approved: bool, cited: bool = True) -> "ContextSlice":
        require_text(text, maximum=32768, field="context-source")
        return cls(text, hashlib.sha256(text.encode("utf-8")).hexdigest(), cited, approved)


def compose_user_context(
    question: str,
    *,
    quota: Quota,
    evidence: tuple[ContextSlice, ...] = (),
    system_reserve_tokens: int = 256,
) -> str:
    """Conservative byte bound, never a claim of exact model tokenization.

    The model-native tokenizer must independently enforce its own context cap.
    """
    require_text(question, maximum=quota.input_bytes, field="question")
    if len(question.encode("utf-8")) > quota.input_bytes:
        deny("question-bytes")
    if type(evidence) is not tuple or len(evidence) > 32:
        deny("context-count")
    parts = [question]
    for item in evidence:
        if not isinstance(item, ContextSlice) or not item.approved or not item.cited:
            deny("context-unapproved")
        if hashlib.sha256(item.text.encode("utf-8")).hexdigest() != item.source_sha:
            deny("context-digest")
        if "<<<" in item.text or ">>>" in item.text:
            deny("context-delimiters")
        parts.append("<<<UNTRUSTED_SOURCE sha256=" + item.source_sha + ">>>\n"
                     + item.text + "\n<<<END_UNTRUSTED_SOURCE>>>")
    result = "\n\n".join(parts)
    # UTF-8 bytes are an operational admission ceiling, not a tokenizer estimate.
    if len(result.encode("utf-8")) > (quota.context_tokens - quota.output_tokens
                                      - system_reserve_tokens) * 2:
        deny("context-overflow")
    return result
