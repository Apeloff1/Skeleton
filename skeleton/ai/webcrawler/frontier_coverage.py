"""Deterministic multilingual URL coverage scoring for the canonical crawler.

This analysis may only REORDER pre-existing admitted frontier rows. It cannot
add URLs, permit hosts, alter grants, execute fetches, change robots rules,
waive source rights, or update the canonical CrawlRun snapshot. All measured
coverage is based on canonical URL metadata, never source body instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
from urllib.parse import unquote, urlsplit

MAX_SOURCE_URLS = 128
MAX_TERM_COUNT = 32
MAX_URL_CHARS = 4096
_WORD = re.compile(r"[^\W_]{2,64}", flags=re.UNICODE)
_NUMERIC = re.compile(r"^(?:\d{1,18}|[a-f0-9]{16,64})$", re.I)
_UUID = re.compile(r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$", re.I)
_CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,64}")
_MAX_CANDIDATE_DEPTH = 3
_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "what",
    "when", "where", "which", "how", "about", "into", "are", "was",
})
_ALPHA = re.compile(r"^[^\W\d_]+$", re.UNICODE)


@dataclass(frozen=True)
class CoveragePriority:
    url: str
    host: str
    url_family: str
    captured_host_sources: int
    captured_url_family_sources: int
    query_term_count: int
    candidate_term_count: int
    operator_term_overlap: float
    uncovered_operator_overlap: float
    score: float
    algorithm: str = "url_only_coverage_v1"
    source_content_inspected: bool = False
    source_content_trusted: bool = False
    request_dispatched: bool = False
    admission_required: bool = True


def _validate_url(url: object) -> str:
    if not isinstance(url, str) or not 1 <= len(url) <= MAX_URL_CHARS:
        raise ValueError("URL coverage requires a finite canonical URL")
    try:
        p = urlsplit(url)
        host = p.hostname
    except ValueError as exc:
        raise ValueError("malformed URL origin") from exc
    if (p.scheme not in ("http", "https") or not host
            or p.username is not None or p.password is not None):
        raise ValueError("URL coverage cannot evaluate unadmitted source URL")
    return host


def _unicode_terms(source: str) -> frozenset[str]:
    """Finite operator/URL tokens with bounded CJK sliding bigrams."""
    norm = unicodedata.normalize("NFKC", source).casefold()
    terms = set()
    for match in _WORD.findall(norm):
        if match not in _STOP and len(match) <= 64:
            terms.add(match)
    for chunk in _CJK.findall(norm):
        terms.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return frozenset(terms)


def _url_tokens(url: str) -> frozenset[str]:
    parsed = urlsplit(url)
    path = unquote(parsed.path, encoding="utf-8", errors="replace")
    # Query *values* can contain access tokens or tracking strings. Never
    # let them influence prioritization or persist in scoring diagnostics.
    query_names = "&".join(
        part.partition("=")[0] for part in parsed.query.split("&")[:64]
    )
    return _unicode_terms(path + " " + query_names)


def _family(url: str) -> str:
    parsed = urlsplit(url)
    paths = []
    for segment in parsed.path.split("/"):
        value = unquote(segment, encoding="utf-8", errors="replace").casefold()
        paths.append("{id}" if _NUMERIC.fullmatch(value) or _UUID.fullmatch(value) else value[:128])
    # Ignore pagination values for family attribution, retain capped keys.
    keys = sorted({part.partition("=")[0].casefold()[:64]
                   for part in parsed.query.split("&")[:32] if part})
    return (parsed.scheme + "://" + parsed.netloc.casefold() + "/"
            + "/".join(paths) + "?" + ",".join(keys))[:2048]


def measure_frontier_coverage(
    url: str, *, sources: dict, query: str,
    depth: int, attempts: int,
) -> CoveragePriority:
    """Rank *one already admitted* candidate without reading external text.

    Source URL distribution helps prioritize underrepresented portions of
    a permitted crawl. This is not a model-generated expansion and cannot
    be called to issue a request.
    """
    host = _validate_url(url)
    if (not isinstance(sources, dict) or len(sources) > MAX_SOURCE_URLS
            or not isinstance(query, str) or len(query) > 1024
            or type(depth) is not int or not 0 <= depth <= _MAX_CANDIDATE_DEPTH
            or type(attempts) is not int or not 0 <= attempts <= 128):
        raise ValueError("frontier coverage input capacity exceeded")
    query_terms = sorted(_unicode_terms(query))[:MAX_TERM_COUNT]
    wanted = frozenset(query_terms)
    observed = set()
    by_host = by_family = 0
    family = _family(url)
    for source in sources.values():
        if not isinstance(source, dict):
            raise ValueError("invalid retained source metadata")
        source_url = source.get("canonical_url")
        source_host = _validate_url(source_url)
        observed.update(_url_tokens(source_url) & wanted)
        if source_host == host:
            by_host += 1
        if _family(source_url) == family:
            by_family += 1
    tokens = _url_tokens(url)
    overlap = len(tokens & wanted) / len(wanted) if wanted else 0.0
    unmet = wanted - observed
    unmet_overlap = len(tokens & unmet) / len(unmet) if unmet else 0.0
    score = (
        .24 / (1 + by_host)
        + .18 / (1 + by_family)
        + .28 * unmet_overlap
        + .17 * overlap
        + .08 / (1 + depth)
        + .05 / (1 + attempts)
    )
    if not math.isfinite(score) or not 0 <= score <= 1.0 + 1e-10:
        raise ValueError("invalid bounded coverage priority")
    return CoveragePriority(
        url=url, host=host, url_family=family,
        captured_host_sources=by_host,
        captured_url_family_sources=by_family,
        query_term_count=len(wanted),
        candidate_term_count=len(tokens),
        operator_term_overlap=round(overlap, 8),
        uncovered_operator_overlap=round(unmet_overlap, 8),
        score=round(score, 8),
    )
