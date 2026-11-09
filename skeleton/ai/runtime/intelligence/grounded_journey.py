"""Grounded journey — a tool receipt may support an answer only by quotation.

Passage faithfulness is the same rule for offline source excerpts: a sentence
ships only when one supplied passage contains every checkable atom. Partial
overlap, invented identifiers, and instructions embedded in sources do not
become support. This is a deterministic atom check, not semantic entailment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import re
import threading
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

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


_FAITHFULNESS_SCHEMA = "skeleton.intelligence.claim-faithfulness.v1"
_FAITHFULNESS_METHOD = "deterministic_atom_overlap_v1"
_VERIFIER_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
_OFFLINE_TENANT = "offline-local"
_MAX_CLAIMS = 24
_CITATION_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_:-])local:[A-Za-z0-9_-]{1,128}:[0-9]+:"
    r"[0-9a-f]{16}(?![A-Za-z0-9_:-])"
)
_CLAIM_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
_NUMBER = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.])")
_INSTRUCTION = re.compile(
    r"\b(?:ignore (?:all |any )?(?:previous|prior|above) instructions|"
    r"disregard (?:the |all )?(?:system|previous)|you are now|"
    r"new instructions?:|do not cite|reveal (?:the |your )?password|"
    r"system prompt)\b",
    re.IGNORECASE,
)
_COMPLIANCE = re.compile(
    r"\b(?:i will|i'll|as instructed|following the "
    r"(?:document|source|excerpt|passage)|obeying|i must comply)\b",
    re.IGNORECASE,
)
_HEDGE_PHRASES = (
    "i do not know",
    "i don't know",
    "i do not know",
    "sources do not establish",
    "do not establish an answer",
    "not established",
    "insufficient evidence",
    "cannot determine",
    "i am not sure",
    "i cannot tell",
)
_ATOM_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "has", "have", "had", "but", "you", "your", "its", "into", "over", "under",
    "than", "then", "also", "only", "some", "such", "each", "both", "same",
    "about", "after", "before", "there", "these", "those", "what", "when",
    "where", "which", "while", "would", "could", "should", "because", "during",
    "within", "does", "did", "been", "being", "they", "them", "their", "will",
})
_ATOM_NEGATION = frozenset({
    "not", "no", "never", "without", "nor", "neither", "cannot",
})
_HEDGE_WORDS = frozenset({
    "know", "sources", "source", "establish", "established", "answer",
    "insufficient", "evidence", "determine", "sure", "tell", "cannot", "can",
}) | _ATOM_STOP | _ATOM_NEGATION


def _fold(text: str) -> str:
    lowered = text.casefold().replace("’", "'")
    lowered = re.sub(r"n't\b", " not ", lowered)
    lowered = re.sub(r"\bcannot\b", " can not ", lowered)
    return " ".join(lowered.split())


def _numbers(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _NUMBER.finditer(text):
        token = match.group(0).replace(",", "")
        if token not in found:
            found.append(token)
    return tuple(found)


def _atoms(text: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    folded = _fold(text)
    words = {
        token
        for token in _WORD.findall(folded)
        if token not in _ATOM_STOP and token not in _ATOM_NEGATION and not token.isdigit()
    }
    negations = frozenset(token for token in _WORD.findall(folded) if token in _ATOM_NEGATION)
    return frozenset(words), negations, frozenset(_numbers(text))


def _claim_sentences(answer: str) -> tuple[str, ...]:
    parts = [part.strip() for part in _CLAIM_SPLIT.split(answer) if part.strip()]
    return tuple(parts[:_MAX_CLAIMS])


def _instruction_sentences(passage: str) -> tuple[str, ...]:
    return tuple(
        sentence for sentence in _claim_sentences(passage)
        if _INSTRUCTION.search(sentence)
    )


def _evidentiary_sentences(passage: str) -> tuple[str, ...]:
    sentences = _claim_sentences(passage) or ((passage.strip(),) if passage.strip() else ())
    kept = tuple(sentence for sentence in sentences if not _INSTRUCTION.search(sentence))
    return kept


def _is_hedge(sentence: str, words: frozenset[str], numbers: frozenset[str]) -> bool:
    if numbers or not words <= _HEDGE_WORDS:
        return False
    folded = _fold(sentence)
    return any(phrase in folded for phrase in _HEDGE_PHRASES)


_CLAUSE = re.compile(r"\s+(?:and|but|or)\s+|;\s+", re.IGNORECASE)


def _clauses(text: str) -> tuple[str, ...]:
    parts = [part.strip() for part in _CLAUSE.split(text) if part.strip()]
    return tuple(parts) or ((text.strip(),) if text.strip() else ())


def _compare_clause(sentence: str, clause: str) -> str | None:
    words, negations, numbers = _atoms(sentence)
    clause_words, clause_negations, clause_numbers = _atoms(clause)
    if not words and not numbers:
        return None
    folded = _fold(sentence)
    clause_folded = _fold(clause)
    same_polarity = negations == clause_negations
    numbers_fit = (not numbers) or numbers <= clause_numbers
    words_fit = (not words) or words <= clause_words
    if (
        folded
        and folded in clause_folded
        and same_polarity
        and numbers_fit
        and words_fit
    ):
        return "supports"
    if words and not words <= clause_words:
        return None
    if words and numbers and clause_numbers and numbers.isdisjoint(clause_numbers):
        return "contradicts_number"
    if words and negations != clause_negations and (negations or clause_negations):
        return "contradicts_polarity"
    if words_fit and numbers_fit and same_polarity and (words or numbers):
        return "supports"
    return None


def _compare(sentence: str, excerpt: str) -> str | None:
    found: str | None = None
    for clause in _clauses(excerpt):
        relation = _compare_clause(sentence, clause)
        if relation is not None and relation.startswith("contradicts"):
            return relation
        if relation == "supports" and found is None:
            found = relation
    return found


def _passage_rows(passages: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if isinstance(passages, (str, bytes)) or not isinstance(passages, Sequence):
        raise TypeError("passages must be a sequence of source records")
    if not passages:
        raise ValueError("passages must be non-empty")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in passages:
        if not isinstance(item, Mapping):
            raise TypeError("passage record must be a mapping")
        citation = item.get("citation")
        passage = item.get("passage")
        title = item.get("title")
        if not isinstance(citation, str) or not citation.strip():
            raise ValueError("passage citation must be a non-empty string")
        if not isinstance(passage, str) or not passage.strip():
            raise ValueError("passage text must be a non-empty string")
        if title is not None and not isinstance(title, str):
            raise TypeError("passage title must be a string")
        if citation in seen:
            raise ValueError("duplicate passage citation")
        seen.add(citation)
        rows.append({
            "citation": citation,
            "passage": passage,
            "title": title or citation,
            "document_id": item.get("document_id") if isinstance(item.get("document_id"), str) else citation,
        })
    return tuple(rows)


def _evidence_row(row: Mapping[str, Any], excerpt: str, relation: str) -> dict[str, str]:
    return {
        "relation": relation,
        "citation": str(row["citation"]),
        "origin_id": str(row["document_id"]),
        "content_digest": sha256(excerpt.encode("utf-8")).hexdigest(),
        "locator": "excerpt:" + excerpt[:80],
    }


def _confirm(sentence: str, evidence: list[dict[str, str]], answer_digest: str, index: int) -> str:
    from skeleton.contracts.verification import (
        ClaimKind,
        ClaimScope,
        EvidenceProducer,
        EvidenceReference,
        EvidenceRelation,
        VerificationClaim,
        VerificationRisk,
    )
    from skeleton.intelligence.verification_runtime import VerificationRuntime

    claim_id = str(uuid5(NAMESPACE_URL, f"offline-claim:{answer_digest}:{index}:{sentence}"))
    claim = VerificationClaim(
        claim_id=claim_id,
        tenant_id=_OFFLINE_TENANT,
        text=sentence,
        kind=ClaimKind.FACT,
        risk=VerificationRisk.MEDIUM,
        created_at=_VERIFIER_EPOCH,
        scope=ClaimScope(),
        generated_by_model=True,
    )
    refs: list[EvidenceReference] = []
    for item in evidence:
        relation = (
            EvidenceRelation.SUPPORTS if item["relation"] == "supports"
            else EvidenceRelation.CONTRADICTS
        )
        evidence_id = str(uuid5(
            NAMESPACE_URL,
            f"offline-evidence:{claim_id}:{item['citation']}:{relation.value}",
        ))
        refs.append(EvidenceReference(
            evidence_id=evidence_id,
            claim_id=claim_id,
            tenant_id=_OFFLINE_TENANT,
            source_id=item["citation"],
            origin_id=item["origin_id"],
            content_digest=item["content_digest"],
            locator=item["locator"],
            relation=relation,
            producer=EvidenceProducer.SOURCE,
            observed_at=_VERIFIER_EPOCH,
            scope=ClaimScope(),
        ))
    assessment = VerificationRuntime().verify(
        claim,
        evidence=tuple(refs),
        verified_at=_VERIFIER_EPOCH,
        verifier_id="claim-faithfulness:deterministic",
    )
    return assessment.outcome.value


def assess_supplied_passages(
    answer: str,
    passages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Decide which model sentences may be published against supplied passages.

    Support requires every content word, number, and negation of the sentence
    to occur together in one non-instruction passage sentence. A conflicting
    number or negation is a contradiction. Source instructions are evidence
    that the text contained an instruction, never authority to follow it.
    """

    if not isinstance(answer, str):
        raise TypeError("answer must be a string")
    rows = _passage_rows(passages)
    known = {row["citation"] for row in rows}
    instruction_passages = [
        row["citation"] for row in rows if _instruction_sentences(row["passage"])
    ]
    answer_digest = sha256(answer.encode("utf-8")).hexdigest()
    sentences = _claim_sentences(answer)
    claims: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        quoted = set(_CITATION_TOKEN.findall(sentence))
        unknown = sorted(quoted - known)
        comparable = _CITATION_TOKEN.sub(" ", sentence).strip() or sentence
        words, negations, numbers = _atoms(comparable)
        record: dict[str, Any] = {
            "index": index,
            "text": sentence,
            "status": "unsupported",
            "reason": "atom_unsupported",
            "citation": None,
            "verification_outcome": None,
        }
        if unknown:
            record["status"] = "invented_citation"
            record["reason"] = "invented_citation"
            claims.append(record)
            continue
        if _COMPLIANCE.search(comparable) and instruction_passages:
            record["status"] = "refused_instruction"
            record["reason"] = "source_instruction_not_authority"
            claims.append(record)
            continue
        if not words and not numbers and not negations:
            record["status"] = "non_factual"
            record["reason"] = "no_checkable_atom"
            claims.append(record)
            continue
        if _is_hedge(comparable, words, numbers):
            record["status"] = "hedged"
            record["reason"] = "explicit_uncertainty"
            claims.append(record)
            continue
        eligible = [
            row for row in rows
            if not quoted or row["citation"] in quoted
        ]
        support: tuple[dict[str, Any], str] | None = None
        contradiction: tuple[str, dict[str, Any], str] | None = None
        for row in eligible:
            for excerpt in _evidentiary_sentences(row["passage"]):
                found = _compare(comparable, excerpt)
                if found is None:
                    continue
                if found.startswith("contradicts"):
                    contradiction = (found, row, excerpt)
                    break
                if support is None:
                    support = (row, excerpt)
            if contradiction is not None:
                break
        if contradiction is not None:
            found, chosen, excerpt = contradiction
            evidence_rows = [_evidence_row(chosen, excerpt, "contradicts")]
            if support is not None:
                evidence_rows.append(_evidence_row(support[0], support[1], "supports"))
            outcome = _confirm(comparable, evidence_rows, answer_digest, index)
            record["status"] = "contradicted"
            record["reason"] = (
                "numeric_contradiction" if found == "contradicts_number"
                else "polarity_contradiction"
            )
            record["citation"] = chosen["citation"]
            record["verification_outcome"] = outcome
            record["source_excerpt"] = excerpt
        elif support is not None:
            chosen, excerpt = support
            outcome = _confirm(
                comparable, [_evidence_row(chosen, excerpt, "supports")],
                answer_digest, index,
            )
            record["citation"] = chosen["citation"]
            record["verification_outcome"] = outcome
            if outcome == "passed":
                record["status"] = "supported"
                record["reason"] = "atom_supported"
            else:
                record["status"] = "unsupported"
                record["reason"] = "runtime_support_missing"
        claims.append(record)

    factual = [
        claim for claim in claims
        if claim["status"] not in {"hedged", "non_factual"}
    ]
    if any(claim["status"] == "contradicted" for claim in claims):
        disposition = "contested"
    elif any(claim["status"] == "refused_instruction" for claim in claims) and not any(
        claim["status"] == "supported" for claim in claims
    ):
        disposition = "abstain"
    elif not factual or not any(claim["status"] == "supported" for claim in factual):
        disposition = "abstain"
    elif all(claim["status"] == "supported" for claim in factual):
        disposition = "supported"
    else:
        disposition = "qualified"

    published = _published_text(answer, disposition, claims, rows, bool(instruction_passages))
    return {
        "schema": _FAITHFULNESS_SCHEMA,
        "method": _FAITHFULNESS_METHOD,
        "interpretation": "deterministic_atom_check_not_semantic_nli",
        "disposition": disposition,
        "published_text": published,
        "model_text_sha256": answer_digest,
        "instruction_passages": instruction_passages,
        "claims": [
            {key: value for key, value in claim.items() if key != "source_excerpt"}
            for claim in claims
        ],
    }


def _published_text(
    answer: str,
    disposition: str,
    claims: list[dict[str, Any]],
    rows: tuple[dict[str, Any], ...],
    instructions: bool,
) -> str:
    if disposition == "supported":
        return answer
    if disposition == "qualified":
        kept = [
            claim["text"] for claim in claims
            if claim["status"] in {"supported", "hedged", "non_factual"}
        ]
        withheld = [
            claim["text"] for claim in claims
            if claim["status"] not in {"supported", "hedged", "non_factual"}
        ]
        lines = [" ".join(kept).strip()]
        if instructions:
            lines.append(
                "Instructions found inside a source were not followed and were not treated as evidence."
            )
        lines.append("Not established by the supplied sources:")
        lines.extend(f"- {text}" for text in withheld)
        return "\n".join(line for line in lines if line).strip()
    if disposition == "contested":
        lines = ["A supplied source contradicts the model draft."]
        for claim in claims:
            if claim["status"] != "contradicted":
                continue
            excerpt = claim.get("source_excerpt") or ""
            lines.append("Claim: " + claim["text"])
            lines.append(f"Source {claim['citation']}: {excerpt}")
        lines.append("The grounded answer does not adopt the contradicted draft.")
        return "\n".join(lines)
    lines = []
    if instructions:
        lines.append(
            "A source passage contained instructions. Those instructions were not followed and were not treated as evidence."
        )
    hedges = [claim["text"] for claim in claims if claim["status"] == "hedged"]
    if hedges and all(claim["status"] in {"hedged", "non_factual"} for claim in claims):
        lines.extend(hedges)
    else:
        lines.append("The supplied local sources do not establish an answer.")
    for row in rows:
        if row["citation"] in {
            citation for citation in (claim.get("citation") for claim in claims)
        }:
            continue
        excerpts = _evidentiary_sentences(row["passage"])
        if not excerpts:
            continue
        lines.append(f"{row['title']} — {row['citation']}")
        lines.append(" ".join(excerpts))
    return "\n".join(lines).strip()


__all__ = [
    "GroundedJourney",
    "JourneyDisposition",
    "JourneyLedger",
    "JourneyResult",
    "assess_supplied_passages",
]
