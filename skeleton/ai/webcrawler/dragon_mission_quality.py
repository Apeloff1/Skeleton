"""Highest-utility crawler quality operations (mission ranks 01–10).

This is a deterministic pre-ingestion inspection plane. Input strings are
external data, never instructions. Scanners emit review signals, not proof of
malice or factual truth. Rights are explicit grants, never inferred from
public availability, robots, or a permissive content type.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
from urllib.parse import urlsplit
import re

from .core import CrawlDocument, canonicalize_url


@dataclass(frozen=True)
class RightsGrant:
    """Positive, scoped permission to process *this* immutable content."""
    content_hash: str
    canonical_url: str
    purpose: str
    grantor: str
    evidence_reference: str
    valid_until: float


@dataclass(frozen=True)
class TextRisk:
    risk: str
    start: int
    end: int
    detail: str


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class RankedPassage:
    span: TextSpan
    query_coverage: float
    weighted_score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    content_hashes: tuple[str, ...]
    documents: tuple[str, ...]
    approximate_similarity: float


@dataclass(frozen=True)
class InformationQuality:
    tokens: int
    distinct_terms: int
    unique_ratio: float
    repetitive_line_fraction: float
    low_information: bool


_WORD = re.compile(r"\b[\w]+\b", flags=re.UNICODE)
_URL = re.compile(r"https?://[^\s<>'\"\]]+", re.I)
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_INJECTION = (
    ("override_instructions", re.compile(r"\b(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions\b", re.I)),
    ("role_spoofing", re.compile(r"(?:\[im_start\]|<\|im_start\|>|\[INST\]|<<SYS>>)", re.I)),
    ("secret_exfiltration", re.compile(r"\b(?:send|post|upload|exfiltrate)\b.{0,90}\b(?:passwords?|api\s*keys?|secrets?|credentials?)\b", re.I | re.S)),
    ("tool_authority", re.compile(r"\b(?:execute|run)\s+(?:the\s+)?(?:shell|terminal|python|command)\b", re.I)),
)
_TEMPORAL = re.compile(r"(?<!\d)(?:18|19|20|21)\d{2}(?!\d)")
_MODAL = re.compile(r"\b(?:might|may|could|possibly|allegedly|reportedly|unconfirmed)\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|no|without|cannot|denied|refuted|disproved)\b", re.I)
_STOP = frozenset({"the","and","for","with","that","this","from","have","into","about","while","than","then","you","your","are","was","were","been","their","they","its","our"})


def _words(text: str) -> tuple[str, ...]:
    return tuple(w.casefold() for w in _WORD.findall(text) if len(w) > 1)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _verify_text(text: str, maximum: int = 4_000_000) -> None:
    if not isinstance(text, str) or len(text.encode("utf-8")) > maximum:
        raise ValueError("invalid or oversized text")


# 01. Training rights are explicit and bound to the exact version.
def require_training_grant(
    doc: CrawlDocument, grant: RightsGrant | None, *,
    purpose: str, now: float,
) -> str:
    if not isinstance(doc, CrawlDocument):
        raise ValueError("captured CrawlDocument required")
    if grant is None:
        raise PermissionError("unlicensed crawler content cannot enter training")
    if not isinstance(grant, RightsGrant) or not isinstance(purpose, str) or not purpose:
        raise ValueError("invalid training grant")
    if not isinstance(now, (int, float)) or isinstance(now, bool) or not isfinite(now) or now < 0:
        raise ValueError("invalid training authorization time")
    if not isinstance(grant.valid_until, (int, float)) or isinstance(grant.valid_until, bool) or not isfinite(grant.valid_until):
        raise ValueError("invalid grant expiry")
    if not grant.grantor or not grant.evidence_reference or any(
        len(x) > 1024 for x in (grant.grantor, grant.evidence_reference)
    ):
        raise ValueError("grant evidence required")
    try:
        canonical = canonicalize_url(doc.canonical_url)
    except (ValueError, UnicodeError) as error:
        raise ValueError("invalid document source") from error
    if canonical != doc.canonical_url or grant.canonical_url != canonical:
        raise PermissionError("training grant does not cover this source")
    if _digest(doc.text) != doc.content_hash or grant.content_hash != doc.content_hash:
        raise PermissionError("training grant does not cover this revision")
    if grant.purpose != purpose or now > grant.valid_until:
        raise PermissionError("training grant purpose or expiry mismatch")
    return _digest("|".join((
        "training-rights-v1", grant.content_hash, canonical, grant.purpose,
        grant.grantor, grant.evidence_reference, str(grant.valid_until),
    )))


# 02. Prompt-injection quarantine suggestions; the raw page has no authority.
def scan_untrusted_instructions(text: str, *, limit: int = 100) -> tuple[TextRisk, ...]:
    _verify_text(text)
    if not 1 <= limit <= 1000:
        raise ValueError("invalid inspection capacity")
    matches = [
        TextRisk(name, m.start(), m.end(), "untrusted page instruction pattern")
        for name, pattern in _INJECTION for m in pattern.finditer(text)
    ]
    return tuple(sorted(matches, key=lambda x: (x.start, x.end, x.risk))[:limit])


# 03. Stable sensitive-data minimization without shifting passage identities.
def mask_personal_data(text: str, *, limit: int = 10000) -> tuple[str, tuple[TextRisk, ...]]:
    _verify_text(text)
    if not 1 <= limit <= 100000:
        raise ValueError("invalid redaction capacity")
    matched = [
        TextRisk(name, match.start(), match.end(), "sensitive pattern")
        for name, pattern in (("email", _EMAIL), ("phone", _PHONE))
        for match in pattern.finditer(text)
    ]
    matched.sort(key=lambda r: (r.start, -(r.end-r.start), r.risk))
    output = list(text)
    applied: list[TextRisk] = []
    used_until = 0
    for risk in matched:
        if risk.start < used_until:
            continue
        if len(applied) >= limit:
            raise ValueError("redaction limit exceeded")
        for i in range(risk.start, risk.end):
            if not text[i].isspace():
                output[i] = "█"
        applied.append(risk)
        used_until = risk.end
    return "".join(output), tuple(applied)


# 04. Offset-stable, bounded text segmentation for the extraction pipeline.
def segment_passages(
    text: str, *, max_chars: int = 600, overlap: int = 60,
    max_segments: int = 10000,
) -> tuple[TextSpan, ...]:
    _verify_text(text)
    if not 32 <= max_chars <= 100000 or not 0 <= overlap < max_chars:
        raise ValueError("invalid passage segmentation")
    if not 1 <= max_segments <= 100000:
        raise ValueError("invalid segment budget")
    n = len(text)
    if not n:
        return ()
    spans: list[TextSpan] = []
    start = 0
    while start < n:
        end = min(n, start+max_chars)
        if end < n:
            last_space = max(text.rfind(" ", start+max_chars//2, end),
                             text.rfind("\n", start+max_chars//2, end))
            if last_space > start:
                end = last_space + 1
        if text[start:end].strip():
            if len(spans) >= max_segments:
                raise ValueError("passage budget exceeded")
            spans.append(TextSpan(start, end, text[start:end]))
        if end == n:
            break
        next_start = max(start+1, end-overlap)
        start = next_start
    return tuple(spans)


# 05. Query-led passage ranking retains exact source character spans.
def rank_query_passages(
    text: str, query: str, *, limit: int = 8, max_chars: int = 600,
) -> tuple[RankedPassage, ...]:
    _verify_text(text)
    if not isinstance(query, str) or not query.strip() or len(query) > 512:
        raise ValueError("invalid research query")
    if not 1 <= limit <= 100:
        raise ValueError("invalid passage ranking limit")
    terms = frozenset(w for w in _words(query) if w not in _STOP)
    if not terms:
        return ()
    result: list[RankedPassage] = []
    for span in segment_passages(text, max_chars=max_chars):
        words = _words(span.text)
        found = tuple(sorted(terms & set(words)))
        if not found:
            continue
        coverage = len(found)/len(terms)
        density = len(found)/max(1,len(set(words)))
        score = round(.85*coverage + .15*density, 8)
        result.append(RankedPassage(span, round(coverage,8), score, found))
    return tuple(sorted(result, key=lambda p: (
        -p.weighted_score, p.span.start, p.span.end
    ))[:limit])


# 06. Exact duplicate detection before retrieval or training inclusion.
def exact_revision_groups(
    docs: Iterable[CrawlDocument], *, max_documents: int = 10000,
) -> tuple[DuplicateGroup, ...]:
    items = tuple(docs)
    if not 1 <= max_documents <= 100000 or len(items) > max_documents:
        raise ValueError("exact duplicate scan budget exceeded")
    grouped: dict[str, set[str]] = {}
    for doc in items:
        if not isinstance(doc, CrawlDocument) or _digest(doc.text) != doc.content_hash:
            raise ValueError("unverified duplicate input")
        grouped.setdefault(doc.content_hash, set()).add(doc.canonical_url)
    return tuple(DuplicateGroup(key, tuple(sorted(urls)), 1.0)
                 for key, urls in sorted(grouped.items()) if len(urls) > 1)


# 07. Similarity-based mirrored content alert; never a proof of shared ownership.
def near_duplicate_groups(
    docs: Iterable[CrawlDocument], *, threshold: float = .85,
    max_documents: int = 256, max_words: int = 8000,
) -> tuple[DuplicateGroup, ...]:
    items = tuple(docs)
    if not isinstance(threshold,(int,float)) or isinstance(threshold,bool) or not isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("invalid similarity threshold")
    if not 1 <= max_documents <= 2000 or len(items) > max_documents:
        raise ValueError("near duplicate budget exceeded")
    if not 1 <= max_words <= 20000:
        raise ValueError("invalid token scan budget")
    sets = []
    for doc in items:
        if not isinstance(doc, CrawlDocument) or _digest(doc.text) != doc.content_hash:
            raise ValueError("unverified near duplicate input")
        words = _words(doc.text)[:max_words]
        shingle = frozenset(tuple(words[i:i+5]) for i in range(max(0,len(words)-4)))
        sets.append(shingle)
    parent = list(range(len(items)))
    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            a,b = sets[i],sets[j]
            union = len(a|b)
            similarity = len(a&b)/union if union else 0
            if similarity >= threshold and union:
                ri,rj=root(i),root(j)
                parent[max(ri,rj)] = min(ri,rj)
    groups: dict[int,list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(root(i), []).append(i)
    result: list[DuplicateGroup] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        hashes = tuple(sorted({items[i].content_hash for i in members}))
        urls = tuple(sorted({items[i].canonical_url for i in members}))
        min_sim = min((len(sets[i]&sets[j])/len(sets[i]|sets[j])
                       for pos,i in enumerate(members) for j in members[pos+1:]
                       if sets[i]|sets[j]), default=1.0)
        result.append(DuplicateGroup("|".join(hashes), urls, round(min_sim,8)))
    return tuple(sorted(result,key=lambda g:g.documents))


# 08. An actionable low-information flag (no hallucinated quality scores).
def measure_information_quality(
    text: str, *, min_words: int = 100,
    max_repetition: float = .65,
) -> InformationQuality:
    _verify_text(text)
    if not 1 <= min_words <= 100000 or not isinstance(max_repetition,(int,float)) or not isfinite(max_repetition) or not 0 <= max_repetition <= 1:
        raise ValueError("invalid information-quality policy")
    words = _words(text)
    diverse = len(set(words))
    lines = [line.casefold().strip() for line in text.splitlines() if line.strip()]
    repeated = (len(lines)-len(set(lines)))/len(lines) if lines else 0.0
    ratio = diverse/len(words) if words else 0.0
    return InformationQuality(len(words),diverse,round(ratio,6),
                              round(repeated,6),
                              len(words)<min_words or repeated>max_repetition)


# 09. Surface negation, hedging and refutation as review triggers, not verdicts.
def locate_uncertainty_cues(
    text: str, *, max_cues: int = 1000,
) -> tuple[TextRisk, ...]:
    _verify_text(text)
    if not 1 <= max_cues <= 10000:
        raise ValueError("invalid uncertainty scan budget")
    found = [TextRisk(kind, m.start(), m.end(), "requires contextual interpretation")
             for kind, pattern in (("negation",_NEGATION),("hedge",_MODAL))
             for m in pattern.finditer(text)]
    return tuple(sorted(found,key=lambda x:(x.start,x.risk))[:max_cues])


# 10. Discover candidate citation identities for later external verification.
def extract_citation_candidates(
    text: str, *, limit: int = 1000,
) -> tuple[str, ...]:
    _verify_text(text)
    if not 1 <= limit <= 10000:
        raise ValueError("invalid citation capacity")
    found: set[str] = set()
    for match in _DOI.finditer(text):
        found.add("doi:"+match.group(0).rstrip(".,;").lower())
    for match in _URL.finditer(text):
        raw = match.group(0).rstrip(".,;)")
        try:
            canonical = canonicalize_url(raw)
        except (ValueError, UnicodeError):
            continue
        parsed=urlsplit(canonical)
        if parsed.username is None and parsed.password is None:
            found.add(canonical)
    if len(found)>limit:
        raise ValueError("citation capacity exceeded")
    return tuple(sorted(found))
