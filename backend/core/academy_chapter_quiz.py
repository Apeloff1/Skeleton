"""Source-bound offline Academy self-study questions.

The renderer is deterministic and never calls a model, runs chapter code,
or invents facts. All correct answers and distractors are excerpts or terms
already present in the admitted lesson. This is self-study, not a protected
exam, certification or competitive score.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

VERSION = "academy-source-quiz-v1"
MAX_BODY_BYTES = 1024 * 1024
MAX_SECTIONS = 128
MAX_GLOSSARY = 128
MAX_QUESTIONS = 10
_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)


class EvidenceUnavailable(ValueError):
    """The chapter lacks enough distinct evidence to form a real quiz."""


class SourceChanged(ValueError):
    """The caller's source or assessment receipt no longer matches."""


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()


def _text(value, max_length: int) -> str | None:
    if type(value) is not str or not 1 <= len(value) <= max_length:
        return None
    if not value.strip() or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        return None
    return value


def _valid_sha(value) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def validate_identity(item_type, item_id, chapter_idx) -> tuple[str, str, int]:
    if item_type not in ("book", "bible", "track", "subject", "manual"):
        raise ValueError("unsupported reading item")
    if type(item_id) is not str or not _ID.fullmatch(item_id):
        raise ValueError("invalid reading item identity")
    if type(chapter_idx) is not int or not 0 <= chapter_idx <= 10000:
        raise ValueError("invalid chapter index")
    return item_type, item_id, chapter_idx


def cache_identity(item_type: str, item_id: str, chapter_idx: int) -> dict:
    validate_identity(item_type, item_id, chapter_idx)
    return {"book_id": item_id if item_type == "book" else f"{item_type}:{item_id}",
            "chapter_idx": chapter_idx}


@dataclass(frozen=True)
class ChapterSource:
    name: str
    body: str
    sections: tuple[tuple[str, str], ...]
    glossary: tuple[tuple[str, str], ...]

    @property
    def digest(self) -> str:
        return _hash({"format": "academy-chapter-source-v1", "name": self.name,
                      "body": self.body, "sections": self.sections, "glossary": self.glossary})


def chapter_source(doc: dict) -> ChapterSource:
    if type(doc) is not dict:
        raise EvidenceUnavailable("chapter unavailable")
    name = _text(doc.get("chapter_name"), 512) or "Chapter"
    body = _text(doc.get("body_md"), MAX_BODY_BYTES)
    if body is None or len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise EvidenceUnavailable("chapter body exceeds evidence budget")
    raw_sections = doc.get("sections") or []
    raw_glossary = doc.get("glossary_structured") or []
    if (type(raw_sections) is not list or len(raw_sections) > MAX_SECTIONS
            or type(raw_glossary) is not list or len(raw_glossary) > MAX_GLOSSARY):
        raise EvidenceUnavailable("chapter structure exceeds evidence budget")
    sections = []
    seen = set()
    for row in raw_sections:
        if type(row) is not dict:
            continue
        title = _text(row.get("title"), 256)
        text = _text(row.get("text"), MAX_BODY_BYTES)
        if title is None or text is None or title.casefold() in seen:
            continue
        # Reject detached structured excerpts: the assessment must bind to
        # the actual displayed body as well as the structured companion rows.
        if text not in body or title not in body:
            continue
        seen.add(title.casefold())
        sections.append((title, text))
    glossary = []
    seen = set()
    for row in raw_glossary:
        if type(row) is not dict:
            continue
        term = _text(row.get("term"), 128)
        definition = _text(row.get("definition"), 512)
        if term is None or definition is None or term.casefold() in seen:
            continue
        if term not in body or definition not in body:
            continue
        seen.add(term.casefold())
        glossary.append((term, definition))
    return ChapterSource(name, body, tuple(sections), tuple(glossary))


def chapter_view(doc: dict) -> dict:
    """Provide a receipt without mutating legacy cached records."""
    try:
        source = chapter_source(doc)
        return {**doc, "source_sha256": source.digest, "source_receipt_available": True}
    except (EvidenceUnavailable, UnicodeError):
        return {**doc, "source_sha256": None, "source_receipt_available": False}


_PROFILE_KEYS = ("ac_comp_quiz", "ac_comp_term", "ac_comp_glossary",
                 "ac_diff_abstract", "ac_rev_drill", "ac_rev_hint")


def profile_for(dna) -> dict[str, int]:
    if dna is None:
        dna = {}
    if type(dna) is not dict or len(dna) > 200:
        raise ValueError("invalid quiz profile")
    profile = {}
    for key in _PROFILE_KEYS:
        val = dna.get(key, 1.0)
        if type(val) not in (int, float) or not math.isfinite(val) or not 0 <= val <= 3:
            raise ValueError("invalid quiz preference")
        # Quantized finite controls; non-assessment sliders do not alter an
        # assessment's identity. No prompt injection or unbounded cache keys.
        profile[key] = round(float(val) * 4)
    return profile


def _score(seed: str, namespace: str, value: str) -> str:
    return _hash([seed, namespace, value])


def _options(correct: str, pool: list[str], seed: str, ident: str) -> tuple[list[str], int] | None:
    choices = {}
    canonical = correct.strip().casefold()
    for option in pool:
        if option.strip().casefold() != canonical:
            choices.setdefault(option.strip().casefold(), option)
    if len(choices) < 3:
        return None
    wrong = sorted(choices.values(), key=lambda x: _score(seed, ident + ":distractor", x))[:3]
    rows = sorted([correct, *wrong], key=lambda x: _score(seed, ident + ":option", x))
    return rows, rows.index(correct)


def _excerpt(text: str) -> str | None:
    # Pick a bounded first complete prose sentence, not executable code.
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or stripped.startswith(("#", "|", ">", "-", "*", "`")):
            continue
        for pos, char in enumerate(stripped[:240]):
            if char in ".!?" and 38 <= pos <= 239 and (pos + 1 == len(stripped) or stripped[pos + 1].isspace()):
                result = stripped[:pos + 1]
                if result.count("`") < 2 and "://" not in result:
                    return result
    return None


def build_quiz(source: ChapterSource, item_type: str, item_id: str, chapter_idx: int,
               mastery_dna=None, *, expected_source_sha256: str | None = None) -> dict:
    validate_identity(item_type, item_id, chapter_idx)
    digest = source.digest
    if expected_source_sha256 is not None:
        if not _valid_sha(expected_source_sha256):
            raise ValueError("invalid source receipt")
        if expected_source_sha256 != digest:
            raise SourceChanged("chapter source changed")
    profile = profile_for(mastery_dna)
    seed = _hash([VERSION, item_type, item_id, chapter_idx, digest, profile])
    pool: list[dict] = []
    used: set[str] = set()

    def emit(kind: str, label: str, question: str, answer: str, alternatives: list[str], evidence: str):
        ident = _hash([kind, label, question, answer])
        normalized = question.casefold()
        if normalized in used or evidence not in source.body:
            return
        choice = _options(answer, alternatives, seed, ident)
        if choice is None:
            return
        options, answer_idx = choice
        used.add(normalized)
        pool.append({"id": ident[:24], "kind": kind, "q": question, "options": options,
                     "answer_idx": answer_idx, "explanation": "The chapter records this exact evidence.",
                     "evidence": {"label": label, "excerpt": evidence, "source_sha256": digest}})

    terms = [term for term, _ in source.glossary]
    defs = [definition for _, definition in source.glossary]
    for term, definition in source.glossary:
        emit("term_definition", "Glossary: " + term, f"Which definition is paired with {term} in this chapter?",
             definition, defs, definition)
        if sum(value.strip().casefold() == definition.strip().casefold() for value in defs) == 1:
            emit("definition_term", "Glossary: " + term, f"Which term matches this definition: {definition}",
                 term, terms, definition)

    excerpts = [(title, excerpt) for title, text in source.sections if (excerpt := _excerpt(text))]
    excerpt_pool = [excerpt for _, excerpt in excerpts]
    for title, excerpt in excerpts:
        if sum(excerpt in text for _, text in source.sections) != 1:
            continue
        # All distractors are excerpts from other sections; the location
        # question avoids asserting that any alternative is factually false.
        emit("section_evidence", title,
             f"Which excerpt appears in the section “{title}”?",
             excerpt, excerpt_pool, excerpt)

    if len(pool) < 5:
        raise EvidenceUnavailable("not enough distinct chapter evidence for five questions")
    target = min(MAX_QUESTIONS, 5 + max(0, profile["ac_comp_quiz"] - 4) // 2,
                 len(pool))
    groups = {
        "term_definition": 4 + profile["ac_comp_glossary"],
        "definition_term": 4 + profile["ac_comp_term"] + profile["ac_rev_drill"] // 2,
        "section_evidence": 4 + profile["ac_diff_abstract"],
    }
    # Weighted round-robin over deterministic per-kind ranks; ensure diversity
    # whenever the chapter offers multiple distinct question types.
    ranked = {kind: sorted([row for row in pool if row["kind"] == kind],
                            key=lambda row: _score(seed, "question", row["id"]))
              for kind in groups}
    selected = []
    served = {kind: 0 for kind in groups}
    while len(selected) < target:
        available = [kind for kind, rows in ranked.items() if rows]
        if not available:
            break
        kind = min(available, key=lambda k: (served[k] / groups[k], _score(seed, "kind", k)))
        row = ranked[kind].pop(0)
        if profile["ac_rev_hint"] >= 8:
            row["hint"] = "Review " + row["evidence"]["label"]
        selected.append(row)
        served[kind] += 1
    receipt = _hash({"version": VERSION, "identity": [item_type, item_id, chapter_idx],
                     "source_sha256": digest, "profile": profile, "questions": selected})
    return {"version": VERSION, "assessment_sha256": receipt, "source_sha256": digest,
            "profile": profile, "questions": selected, "cached": False,
            "offline_generated": True, "assessment_kind": "self_study",
            "certification_qualified": False}


def grade_quiz(quiz: dict, assessment_sha256: str, answers: list) -> dict:
    if not _valid_sha(assessment_sha256) or assessment_sha256 != quiz["assessment_sha256"]:
        raise SourceChanged("assessment receipt changed")
    questions = quiz["questions"]
    if type(answers) is not list or len(answers) != len(questions) or any(
        type(answer) is not int or not 0 <= answer <= 3 for answer in answers
    ):
        raise ValueError("complete valid answer inventory required")
    results = [{"question_id": row["id"], "correct": answer == row["answer_idx"]}
               for row, answer in zip(questions, answers)]
    correct = sum(result["correct"] for result in results)
    return {"assessment_sha256": assessment_sha256, "source_sha256": quiz["source_sha256"],
            "correct": correct, "total": len(results), "score": round(correct / len(results) * 100, 2),
            "results": results, "assessment_kind": "self_study", "certification_qualified": False}
