"""Grounded journey — a tool receipt may support an answer only by quotation.

Passage faithfulness is a hybrid of two channels. The atomic channel checks
content words, numbers, and negation directly. The semantic channel is a cross-attention
entailment network on the Jeeves cortex attention stack. A sentence ships only
when that network entails it and the atomic channel does not contradict it.
Partial overlap, unknown tokens, invented identifiers, and instructions embedded
in sources do not become support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
_FAITHFULNESS_METHOD = "hybrid_atomic_neural_v2"
_FAITHFULNESS_INTERPRETATION = "hybrid_atomic_and_neural_entailment"
_MAX_PASSAGES = 8
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
_QUANTIFIER = re.compile(
    r"\b(?:(?P<gt>greater than|more than|above|over|exceeds|exceed)|"
    r"(?P<lt>less than|fewer than|below|under)|"
    r"(?P<ge>at least|no (?:less|fewer) than)|"
    r"(?P<le>at most|no more than)|"
    r"(?P<eq>exactly))\s+"
    r"(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_QUANTIFIER_WORDS = frozenset({
    "greater", "more", "above", "over", "less", "fewer", "below", "under",
    "least", "most", "exactly", "than", "exceeds", "exceed",
})
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
_LESSONS = {
    "supported": (
        "The atom check and the cross-attention entailment check both licensed every sentence. "
        "Keep any further sentence inside those passages."
    ),
    "qualified": "Publish the licensed sentences and leave the rest unstated.",
    "abstain": (
        "Do not add content words, numbers, or citation identifiers "
        "that no supplied passage contains."
    ),
    "contested": (
        "Do not restate a number or a negation that a supplied passage, "
        "or a clash between those passages, opposes."
    ),
}


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


def _decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def _quantified(sentence: str) -> tuple[str, Decimal] | None:
    match = _QUANTIFIER.search(_fold(sentence))
    if match is None:
        return None
    kind = next(name for name in ("gt", "lt", "ge", "le", "eq") if match.group(name))
    number = _decimal(match.group("num").replace(",", ""))
    if number is None:
        return None
    return kind, number


def _satisfies(kind: str, claim: Decimal, source: Decimal) -> bool:
    if kind == "gt":
        return source > claim
    if kind == "lt":
        return source < claim
    if kind == "ge":
        return source >= claim
    if kind == "le":
        return source <= claim
    return source == claim


def _content_words(words: frozenset[str]) -> frozenset[str]:
    return frozenset(token for token in words if token not in _QUANTIFIER_WORDS)


def _compare_clause(sentence: str, clause: str) -> str | None:
    words, negations, numbers = _atoms(sentence)
    clause_words, clause_negations, clause_numbers = _atoms(clause)
    if not words and not numbers:
        return None
    quantified = _quantified(sentence)
    source_values = tuple(sorted(clause_numbers, key=Decimal))
    if quantified is not None and len(source_values) == 1:
        kind, claim_number = quantified
        content = _content_words(words)
        excerpt_content = _content_words(clause_words)
        source_number = _decimal(source_values[0])
        if content and content <= excerpt_content and source_number is not None:
            if negations != clause_negations and (negations or clause_negations):
                return "contradicts_polarity"
            return (
                "supports" if _satisfies(kind, claim_number, source_number)
                else "contradicts_number"
            )
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


def _sentence_relation(sentence: str, excerpt: str) -> str | None:
    """License every claim clause, or withhold the sentence.

    A contradicted clause does not launder a neighbouring clause the passage
    never mentions. A passage clause that merely fails to overlap is not a
    contradiction.
    """

    claim_clauses = _clauses(sentence)
    excerpt_clauses = _clauses(excerpt)
    if not claim_clauses:
        return None
    found: list[str | None] = []
    for claim_clause in claim_clauses:
        relation: str | None = None
        for excerpt_clause in excerpt_clauses:
            candidate = _compare_clause(claim_clause, excerpt_clause)
            if candidate is None:
                continue
            if candidate.startswith("contradicts"):
                relation = candidate
                break
            if relation is None:
                relation = candidate
        found.append(relation)
    contradictions = [item for item in found if item and item.startswith("contradicts")]
    if contradictions:
        if any(item is None for item in found):
            return None
        return contradictions[0]
    if found and all(item == "supports" for item in found):
        return "supports"
    return None


def _semantic_clause(sentence: str, clause: str) -> str | None:
    """Neural entailment for one clause. Unknown tokens stay neutral."""

    from skeleton.intelligence.neural_faithfulness import neural_clause_relation

    return neural_clause_relation(sentence, clause)


def _semantic_relation(sentence: str, excerpt: str) -> str | None:
    """Neural entailment across every clause. Unknown tokens do not become support."""

    claim_clauses = _clauses(sentence)
    excerpt_clauses = _clauses(excerpt)
    if not claim_clauses:
        return None
    found: list[str | None] = []
    for claim_clause in claim_clauses:
        relation: str | None = None
        for excerpt_clause in excerpt_clauses:
            candidate = _semantic_clause(claim_clause, excerpt_clause)
            if candidate is None:
                continue
            if candidate.startswith("contradicts"):
                relation = candidate
                break
            if relation is None:
                relation = candidate
        found.append(relation)
    contradictions = [item for item in found if item and item.startswith("contradicts")]
    if contradictions:
        if any(item is None for item in found):
            return None
        return contradictions[0]
    if found and all(item == "entails" for item in found):
        return "entails"
    return None


def _hybrid_relation(atomic: str | None, semantic: str | None) -> str | None:
    """Neural entailment is necessary. An atomic contradiction is sufficient to refuse."""

    if atomic and atomic.startswith("contradicts"):
        return atomic
    if semantic == "contradicts_quantity":
        return "contradicts_number"
    if semantic and semantic.startswith("contradicts"):
        return semantic
    if semantic == "entails" and atomic in {None, "supports"}:
        return "supports"
    return None


def _passage_rows(passages: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if isinstance(passages, (str, bytes)) or not isinstance(passages, Sequence):
        raise TypeError("passages must be a sequence of source records")
    if not passages:
        raise ValueError("passages must be non-empty")
    if len(passages) > _MAX_PASSAGES:
        raise ValueError("passages exceed the faithfulness budget")
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
        verifier_id="claim-faithfulness:hybrid",
    )
    return assessment.outcome.value


def _neural_trace(sentence: str, excerpt: str, relation: str) -> dict[str, object]:
    from skeleton.intelligence.neural_faithfulness import neural_score

    chosen: dict[str, object] | None = None
    for claim_clause in _clauses(sentence):
        for excerpt_clause in _clauses(excerpt):
            detail = neural_score(claim_clause, excerpt_clause)
            if relation.startswith("contradicts") and detail.get("label") == "contradiction":
                return detail
            if relation == "supports" and detail.get("label") == "entailment" and chosen is None:
                chosen = detail
    if chosen is not None:
        return chosen
    return neural_score(sentence, excerpt)


def _passage_grades(
    sentence: str,
    rows: Sequence[Mapping[str, Any]],
    quoted: set[str],
) -> list[dict[str, Any]]:
    grades: list[dict[str, Any]] = []
    for row in rows:
        if quoted and row["citation"] not in quoted:
            relation = atomic = semantic = "not_cited"
            excerpt = ""
            traced: dict[str, object] = {
                "model": "jeeves.cortex.faithfulness-nli.v2",
                "label": "not_cited",
            }
        else:
            relation = atomic = semantic = "unrelated"
            excerpt = ""
            traced = {
                "model": "jeeves.cortex.faithfulness-nli.v2",
                "label": "neutral",
            }
            for piece in _evidentiary_sentences(str(row["passage"])):
                found_atomic = _sentence_relation(sentence, piece)
                found_semantic = _semantic_relation(sentence, piece)
                found = _hybrid_relation(found_atomic, found_semantic)
                if found is None and found_atomic is None and found_semantic is None:
                    continue
                atomic = found_atomic or "unrelated"
                semantic = found_semantic or "unrelated"
                relation = found or "unrelated"
                excerpt = piece
                traced = _neural_trace(sentence, piece, relation)
                if relation.startswith("contradicts"):
                    break
        grades.append({
            "citation": row["citation"],
            "relation": relation,
            "atomic": atomic,
            "semantic": semantic,
            "neural": traced,
            "excerpt": excerpt,
            "row": row,
        })
    grades.sort(key=lambda item: (str(item["citation"]), str(item["relation"])))
    return grades


def assess_supplied_passages(
    answer: str,
    passages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Decide which model sentences may be published against supplied passages.

    The neural channel must entail the sentence, and the atomic channel must
    not contradict its words, numbers, or negation. A conflicting number,
    negation, or neural contradiction is refused. Source instructions are
    evidence that the text contained an instruction, never authority to follow it.
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
        grades = _passage_grades(comparable, rows, quoted)
        record: dict[str, Any] = {
            "index": index,
            "text": sentence,
            "status": "unsupported",
            "reason": "atom_unsupported",
            "citation": None,
            "verification_outcome": None,
            "passage_grades": [
                {
                    "citation": grade["citation"],
                    "relation": grade["relation"],
                    "atomic": grade["atomic"],
                    "semantic": grade["semantic"],
                    "neural": grade["neural"],
                }
                for grade in grades
            ],
            "_grades": grades,
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
        supports = [grade for grade in grades if grade["relation"] == "supports"]
        contradicts = [
            grade for grade in grades if str(grade["relation"]).startswith("contradicts")
        ]
        if contradicts and supports:
            evidence_rows = [
                _evidence_row(grade["row"], grade["excerpt"], "contradicts")
                for grade in contradicts
            ] + [
                _evidence_row(grade["row"], grade["excerpt"], "supports")
                for grade in supports
            ]
            record["status"] = "contradicted"
            record["reason"] = "source_clash"
            record["citation"] = contradicts[0]["citation"]
            record["verification_outcome"] = _confirm(
                comparable, evidence_rows, answer_digest, index,
            )
            record["source_excerpt"] = contradicts[0]["excerpt"]
        elif contradicts:
            chosen = contradicts[0]
            found = str(chosen["relation"])
            record["status"] = "contradicted"
            record["reason"] = (
                "numeric_contradiction" if found == "contradicts_number"
                else "semantic_contradiction" if found == "contradicts_predicate"
                else "polarity_contradiction"
            )
            record["citation"] = chosen["citation"]
            record["verification_outcome"] = _confirm(
                comparable,
                [_evidence_row(chosen["row"], chosen["excerpt"], "contradicts")],
                answer_digest,
                index,
            )
            record["source_excerpt"] = chosen["excerpt"]
        elif supports:
            chosen = supports[0]
            outcome = _confirm(
                comparable,
                [_evidence_row(chosen["row"], chosen["excerpt"], "supports")],
                answer_digest,
                index,
            )
            record["citation"] = chosen["citation"]
            record["verification_outcome"] = outcome
            if outcome == "passed":
                record["status"] = "supported"
                record["reason"] = (
                    "hybrid_supported"
                    if chosen.get("atomic") == "supports" and chosen.get("semantic") == "entails"
                    else "semantic_licensed"
                )
            else:
                record["status"] = "unsupported"
                record["reason"] = "runtime_support_missing"
        elif quoted:
            record["reason"] = "misbound_citation"
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
    supported = sum(claim["status"] == "supported" for claim in claims)
    contradicted = sum(claim["status"] == "contradicted" for claim in claims)
    withheld = sum(
        claim["status"] in {"unsupported", "invented_citation", "refused_instruction"}
        for claim in claims
    )
    if any(claim["reason"] == "source_clash" for claim in claims):
        agreement = "clash"
    elif contradicted:
        agreement = "opposed"
    elif supported:
        agreement = "aligned"
    else:
        agreement = "insufficient"
    return {
        "schema": _FAITHFULNESS_SCHEMA,
        "method": _FAITHFULNESS_METHOD,
        "interpretation": _FAITHFULNESS_INTERPRETATION,
        "disposition": disposition,
        "source_agreement": agreement,
        "published_text": published,
        "model_text_sha256": answer_digest,
        "instruction_passages": instruction_passages,
        "coverage": {
            "claims": len(claims),
            "supported": supported,
            "contradicted": contradicted,
            "withheld": withheld,
        },
        "lesson": _LESSONS[disposition],
        "claims": [
            {
                key: value for key, value in claim.items()
                if key not in {"source_excerpt", "_grades"}
            }
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
        kept = [
            claim["text"] for claim in claims
            if claim["status"] in {"supported", "hedged", "non_factual"}
        ]
        lines = [" ".join(kept).strip()] if kept else []
        fights = [
            claim for claim in claims
            if claim["status"] == "contradicted" and claim["reason"] != "source_clash"
        ]
        clashes = [claim for claim in claims if claim["reason"] == "source_clash"]
        if fights:
            lines.append("A supplied source contradicts the model draft.")
            for claim in fights:
                excerpt = claim.get("source_excerpt") or ""
                lines.append("Claim: " + claim["text"])
                lines.append(f"Source {claim['citation']}: {excerpt}")
        if clashes:
            lines.append("The supplied sources disagree, so the draft is not adopted.")
            for claim in clashes:
                lines.append("Claim: " + claim["text"])
                for grade in claim.get("_grades") or []:
                    if grade["relation"] in {"unrelated", "not_cited"} or not grade["excerpt"]:
                        continue
                    lines.append(
                        f"Source {grade['citation']} ({grade['relation']}): {grade['excerpt']}"
                    )
        lines.append("The grounded answer does not adopt the contradicted draft.")
        return "\n".join(line for line in lines if line)
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
