"""Grounded journey — a tool receipt may support an answer only by quotation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import threading
from typing import Any

from skeleton.skills.tool_adapters.citations import Citation, citations_from_result, pack_citations
from skeleton.skills.tool_adapters.surface import GovernedToolSurface
from skeleton.skills.tool_contract import ToolExecutionRequest, ToolExecutionStatus
from skeleton.skills.tool_runtime import ToolRuntime


_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "has", "have", "had", "but", "you", "your", "its", "into", "over",
})
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_TOKEN = re.compile(r"[a-z0-9]+")
_NEGATION = frozenset({"not", "no", "never", "without", "nor"})


def _sentences(answer: str) -> tuple[str, ...]:
    cleaned = " ".join(answer.split())
    if not cleaned:
        return ()
    return tuple(part for part in _SENTENCE.split(cleaned) if part.strip())


_NEGATION = frozenset({"not", "no", "never", "without", "nor"})


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(text.lower())
        if token in _NEGATION or (len(token) > 2 and token not in _STOP)
    }


def _supports(sentence: str, citations: tuple[Citation, ...]) -> bool:
    """A sentence is supported only by one whole citation.

    Every content word has to appear in that citation, including negation.
    Partial overlap is not support: "not the maintainer" must not ride on
    a quote that only says "maintainer".
    """

    needed = _tokens(sentence)
    if not needed:
        return False
    folded = " ".join(sentence.lower().split())
    for citation in citations:
        excerpt = " ".join(citation.excerpt.lower().split())
        if folded in excerpt:
            return True
        if needed <= _tokens(citation.excerpt):
            return True
    return False


class JourneyDisposition(str, Enum):
    ANSWER = "answer"
    QUALIFIED = "qualified"
    ABSTAIN = "abstain"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class JourneyResult:
    disposition: str
    receipt_status: str
    error_code: str | None
    result_ref: str | None
    citations: tuple[Citation, ...]
    grounded_sentences: tuple[str, ...]
    ungrounded_sentences: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "receipt_status": self.receipt_status,
            "error_code": self.error_code,
            "result_ref": self.result_ref,
            "citations": [citation.to_dict() for citation in self.citations],
            "grounded_sentences": list(self.grounded_sentences),
            "ungrounded_sentences": list(self.ungrounded_sentences),
        }


@dataclass
class JourneyLedger:
    """Remember one grounded outcome per operation. A second answer conflicts."""

    entries: dict[str, JourneyResult] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def remember(self, operation_id: str, result: JourneyResult) -> JourneyResult:
        key = operation_id.strip()
        if not key:
            raise ValueError("operation_id is required")
        with self._lock:
            existing = self.entries.get(key)
            if existing is None:
                self.entries[key] = result
                return result
            if existing.to_dict() != result.to_dict():
                raise ValueError("operation_id replayed with a different grounded outcome")
            return existing


class GroundedJourney:
    """Run one admitted tool and decide whether a proposed answer may ship."""

    def __init__(
        self,
        runtime: ToolRuntime,
        surface: GovernedToolSurface,
        *,
        citation_budget: int = 200,
        ledger: JourneyLedger | None = None,
    ) -> None:
        if not isinstance(runtime, ToolRuntime):
            raise TypeError("runtime must be a ToolRuntime")
        if not isinstance(surface, GovernedToolSurface):
            raise TypeError("surface must be a GovernedToolSurface")
        if isinstance(citation_budget, bool) or not isinstance(citation_budget, int) or citation_budget < 0:
            raise ValueError("citation_budget must be a non-negative integer")
        self.runtime = runtime
        self.surface = surface
        self.citation_budget = citation_budget
        self.ledger = ledger or JourneyLedger()

    def run(self, request: ToolExecutionRequest, proposed_answer: str) -> JourneyResult:
        if not isinstance(proposed_answer, str):
            raise TypeError("proposed_answer must be a string")
        receipt = self.runtime.execute(request)
        citations: tuple[Citation, ...] = ()
        if receipt.status is ToolExecutionStatus.SUCCEEDED and receipt.result_ref:
            stored = self.surface.results.get(receipt.result_ref)
            if stored is None:
                raise RuntimeError("tool receipt points at a result the surface did not store")
            citations = pack_citations(
                citations_from_result(receipt.result_ref, stored),
                budget_tokens=self.citation_budget,
            )
        sentences = _sentences(proposed_answer)
        grounded = tuple(sentence for sentence in sentences if _supports(sentence, citations))
        ungrounded = tuple(sentence for sentence in sentences if sentence not in grounded)
        if receipt.status is not ToolExecutionStatus.SUCCEEDED:
            disposition = JourneyDisposition.BLOCK
        elif not sentences or not grounded:
            disposition = JourneyDisposition.ABSTAIN
        elif ungrounded:
            disposition = JourneyDisposition.QUALIFIED
        else:
            disposition = JourneyDisposition.ANSWER
        result = JourneyResult(
            disposition=disposition,
            receipt_status=receipt.status.value,
            error_code=receipt.error_code,
            result_ref=receipt.result_ref,
            citations=citations,
            grounded_sentences=grounded,
            ungrounded_sentences=ungrounded,
        )
        return self.ledger.remember(request.operation_id, result)


__all__ = ["GroundedJourney", "JourneyDisposition", "JourneyLedger", "JourneyResult"]
