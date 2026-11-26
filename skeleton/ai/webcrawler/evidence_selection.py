"""Bounded novelty-aware retrieval over already-authorized exact passages.

Selection never modifies the immutable text, score, span, or source reference.
Similar content is a correlation signal, not proof of falsehood, copying, or
independence. Distinct numeric or negated statements remain eligible; only
exact duplicates and near-identical spans of the same capture are suppressed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
import unicodedata
from urllib.parse import urlsplit

MAX_CANDIDATES = 512
MAX_RESULTS = 8
MAX_CHARS = 4096
MAX_TOKENS = 256
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,256}")


@dataclass(frozen=True)
class _Candidate:
    ordinal: int
    row: dict
    source_id: str
    content_hash: str
    passage_hash: str
    host: str
    start: int
    end: int
    lexical: float
    timestamp: float
    shingles: frozenset[bytes]


def _shingles(text: str) -> frozenset[bytes]:
    # Normalization is an ephemeral comparison view only. Exact retained
    # passage bytes and original offsets remain the returned evidence.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = []
    for word in _WORD.finditer(normalized):
        token = word.group()
        if _CJK.fullmatch(token):
            tokens.extend(token[i:i + 2] for i in range(len(token) - 1))
        else:
            tokens.append(token[:96])
        if len(tokens) >= MAX_TOKENS:
            break
    tokens = tokens[:MAX_TOKENS]
    if len(tokens) < 5:
        # Do not conflate short quotations that share ordinary words.
        return frozenset()
    return frozenset(hashlib.blake2b(
        "\x1f".join(tokens[i:i + 3]).encode("utf-8"), digest_size=12,
        person=b"dragon-pass",
    ).digest() for i in range(len(tokens) - 2))


def _identifier(value: object, bound: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= bound:
        raise ValueError("invalid evidence identity")
    return value


def _candidate(ordinal: int, row: dict) -> _Candidate:
    if not isinstance(row, dict):
        raise ValueError("invalid evidence candidate")
    source_id = _identifier(row.get("source_id"), 128)
    content_hash = _identifier(row.get("content_hash"), 64)
    passage_hash = _identifier(row.get("passage_hash"), 64)
    url = _identifier(row.get("canonical_url"), 4096)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid evidence origin")
    start, end = row.get("start"), row.get("end")
    text = row.get("text")
    lexical = row.get("lexical_score")
    timestamp = row.get("capture_timestamp", 0.0)
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= 2_097_152
            or not isinstance(text, str) or len(text) != end - start or len(text) > MAX_CHARS
            or hashlib.sha256(text.encode("utf-8")).hexdigest() != passage_hash
            or isinstance(lexical, bool) or not isinstance(lexical, (float, int))
            or not math.isfinite(lexical) or not 0 <= lexical <= 1
            or isinstance(timestamp, bool) or not isinstance(timestamp, (float, int))
            or not math.isfinite(timestamp) or timestamp < 0):
        raise ValueError("evidence candidate is not an exact finite passage")
    return _Candidate(ordinal, row, source_id, content_hash, passage_hash, parsed.hostname,
                      start, end, float(lexical), float(timestamp), _shingles(text))


def _overlap(left: _Candidate, right: _Candidate) -> float:
    if left.source_id != right.source_id:
        return 0.0
    shared = max(0, min(left.end, right.end) - max(left.start, right.start))
    return shared / min(left.end - left.start, right.end - right.start)


def _similarity(left: _Candidate, right: _Candidate) -> float:
    # Jaccard over bounded lexical shingles; no model or source authority.
    if not left.shingles or not right.shingles:
        return _overlap(left, right)
    intersection = len(left.shingles & right.shingles)
    union = len(left.shingles) + len(right.shingles) - intersection
    return max(_overlap(left, right), intersection / union)


def select_diverse_evidence(rows: list[dict], *, limit: int = 8,
                            distinct_sources: bool = False) -> list[dict]:
    """Greedy deterministic marginal utility with bounded redundancy costs.

    The first result is highest lexical relevance. Later results prefer new
    text and origins, weighted by relevance rather than fabricated trust.
    Actual score and evidence are unchanged. No similarity threshold can
    silently mark a source reviewed or independent.
    """
    if (not isinstance(rows, list) or len(rows) > MAX_CANDIDATES
            or type(limit) is not int or not 1 <= limit <= MAX_RESULTS
            or type(distinct_sources) is not bool):
        raise ValueError("evidence selection bounds exceeded")
    candidates = [_candidate(i, row) for i, row in enumerate(rows)]
    candidates.sort(key=lambda c: (-c.lexical, -c.timestamp, c.source_id,
                                   c.start, c.end, c.ordinal))
    chosen: list[_Candidate] = []
    passage_ids: set[str] = set()
    content_ids: set[str] = set()
    source_ids: set[str] = set()
    origins: set[str] = set()
    max_similarity = [0.0] * len(rows)
    while len(chosen) < limit:
        winner = None
        best_key = None
        for candidate in candidates:
            if candidate.passage_hash in passage_ids:
                continue
            if distinct_sources and (candidate.source_id in source_ids
                                     or candidate.content_hash in content_ids):
                continue
            if any(_overlap(candidate, prior) >= .85 for prior in chosen):
                continue
            novelty = 1 - max_similarity[candidate.ordinal]
            # The first result is unmodified lexical relevance. A diverse
            # lower-relevance result can never receive an artificial score
            # higher than its own original lexical relevance.
            utility = candidate.lexical if not chosen else candidate.lexical * (
                .70 + .20 * novelty + .06 * (candidate.host not in origins)
                + .04 * (candidate.source_id not in source_ids)
            )
            key = (-round(utility, 12), -candidate.lexical, -candidate.timestamp,
                   candidate.source_id, candidate.start, candidate.end, candidate.ordinal)
            if best_key is None or key < best_key:
                best_key, winner = key, candidate
        if winner is None:
            break
        chosen.append(winner)
        passage_ids.add(winner.passage_hash)
        source_ids.add(winner.source_id)
        content_ids.add(winner.content_hash)
        origins.add(winner.host)
        for candidate in candidates:
            if candidate.passage_hash not in passage_ids:
                max_similarity[candidate.ordinal] = max(max_similarity[candidate.ordinal],
                                                        _similarity(candidate, winner))
    return [candidate.row for candidate in chosen]
