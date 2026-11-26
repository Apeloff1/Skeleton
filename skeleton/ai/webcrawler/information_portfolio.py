"""Risk-adjusted marginal information yield for admitted Dragon candidates.

URL and operator terms are features, not authority. Already captured text is
used only as a bounded lexical coverage observation. No model, network call,
untrusted source instruction, domain reputation, or new link is consulted.
The scheduler chooses one existing ready row; all hard checks remain owned
by CrawlRun. This is an original heuristic, not a calibrated Bayesian model.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .acquisition_feedback import HostEconomics, host_economics
from .frontier_coverage import CoverageIndex, _family, _unicode_terms, _url_tokens

MAX_TERMS = 32
MAX_SOURCES = 64
MAX_ROWS = 512
MAX_TEXT = 24000
_STOP = frozenset({"the", "and", "for", "with", "from", "that", "this", "about"})


@dataclass(frozen=True)
class InformationPortfolio:
    terms: tuple[str, ...]
    weights: Mapping[str, float]
    missing: Mapping[str, float]
    host_relevance: Mapping[str, tuple[int, int]]
    host_rows: Mapping[str, HostEconomics]
    source_families: Mapping[str, int]
    ready_hosts: frozenset[str]
    robots_known: frozenset[str]
    total_requests: int
    evidence_coverage: float
    corroborated_coverage: float


@dataclass(frozen=True)
class MarginalYield:
    priority: float
    relevance: float
    expected_gap_gain: float
    novelty: float
    reliability: float
    expected_cost: float
    exploration: float
    origin_diversity: float
    robots_overhead: float
    source_content_is_unverified: bool = True
    network_authority_expanded: bool = False


def _host(url: str) -> str:
    if not isinstance(url, str) or not 1 <= len(url) <= 4096:
        raise ValueError("invalid portfolio URL")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid portfolio origin")
    return parsed.hostname


def build_information_portfolio(
    *, coverage: CoverageIndex, sources: dict, frontier: list[dict],
    measurements: list[dict], robots: dict, now: float,
) -> InformationPortfolio:
    if (not isinstance(coverage, CoverageIndex) or not isinstance(sources, dict)
            or len(sources) > MAX_SOURCES or not isinstance(frontier, list)
            or len(frontier) > MAX_ROWS or not isinstance(measurements, list)
            or len(measurements) > 128 or not isinstance(robots, dict)
            or len(robots) > 32 or not math.isfinite(now)):
        raise ValueError("portfolio input outside finite scope")
    terms = tuple(sorted(coverage.wanted - _STOP))[:MAX_TERMS]
    wanted = frozenset(terms)
    document_frequency = Counter()
    host_support: dict[str, set[str]] = defaultdict(set)
    relevance_trials: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    source_families = Counter()
    # Count only unique content hashes; do not promote mirrored text into
    # independent evidence. Synthetic metadata-only fixtures have no overlap.
    unique = set()
    for source in sources.values():
        url = source["canonical_url"]
        host = _host(url)
        identity = source.get("content_hash", url)
        if identity in unique:
            continue
        unique.add(identity)
        text = source.get("text", "")
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT:
            raise ValueError("portfolio source exceeds retained evidence cap")
        observed = _unicode_terms(text) & wanted
        source_families[_family(url)] += 1
        relevance_trials[host][1] += 1
        relevance_trials[host][0] += int(bool(observed))
        for term in observed:
            host_support[term].add(host)
            document_frequency[term] += 1
    candidates = [_url_tokens(row["url"]) & wanted for row in frontier]
    candidate_frequency = Counter(term for tokens in candidates for term in tokens)
    # Inverse candidate frequency favors terms hard to reach, with a finite
    # 1..3 bound so a rare term cannot dominate the entire crawl.
    weights = {
        term: min(3., 1. + math.log((1 + len(candidates)) / (1 + candidate_frequency[term])))
        for term in terms
    }
    total_weight = sum(weights.values()) or 1.
    # First independent-origin occurrence is worth more than repetition.
    # Two distinct hostnames do NOT establish independent factual witnesses.
    missing = {term: 1.0 / (1 + len(host_support[term])) ** 2 for term in terms}
    present = sum(weights[t] for t in terms if document_frequency[t]) / total_weight
    corroborated = sum(weights[t] for t in terms if len(host_support[t]) >= 2) / total_weight
    hosts = frozenset(_host(row["url"]) for row in frontier)
    known = frozenset(origin for origin, row in robots.items()
                      if isinstance(row, dict) and row.get("text") is not None
                      and isinstance(row.get("fetched_at"), (int, float))
                      and 0 <= now - row["fetched_at"] < 86400)
    return InformationPortfolio(
        terms, MappingProxyType(weights), MappingProxyType(missing),
        MappingProxyType({key: tuple(value) for key, value in relevance_trials.items()}),
        MappingProxyType({host: host_economics(measurements, host) for host in hosts}),
        MappingProxyType(dict(source_families)), hosts, known, len(measurements),
        round(present, 8), round(corroborated, 8),
    )


def marginal_yield(row: dict, *, portfolio: InformationPortfolio,
                   ordinal: int, eligible_count: int, remaining_requests: int | None = None) -> MarginalYield:
    if (not isinstance(portfolio, InformationPortfolio) or type(ordinal) is not int
            or type(eligible_count) is not int or not 1 <= eligible_count <= MAX_ROWS
            or not 0 <= ordinal < MAX_ROWS):
        raise ValueError("invalid marginal yield candidate")
    url = row["url"]
    host = _host(url)
    depth, attempts = row["depth"], row["attempts"]
    if type(depth) is not int or not 0 <= depth <= 3 or type(attempts) is not int or not 0 <= attempts <= 3:
        raise ValueError("invalid candidate navigation metrics")
    econ = portfolio.host_rows[host]
    matches = _url_tokens(url) & frozenset(portfolio.terms)
    total = sum(portfolio.weights.values()) or 1.
    affinity = sum(portfolio.weights[t] for t in matches) / total
    gap = sum(portfolio.weights[t] * portfolio.missing[t] for t in matches) / total
    positive, trials = portfolio.host_relevance.get(host, (0, 0))
    # Weak beta prior on host-level query-hit observations. URL evidence is
    # stronger than a prior; unknown targets still retain exploration value.
    host_relevance = (1 + positive) / (2 + trials)
    relevance = .10 + .70 * affinity + .20 * host_relevance
    novelty = (.65 / (1 + portfolio.source_families.get(_family(url), 0))
               + .35 * econ.novelty_probability)
    # Shrink uncertain reliability toward the conservative prior and give
    # exploration an explicit, separately bounded term.
    reliability = max(.15, min(.95, econ.reliability - .08 * econ.uncertainty))
    exploration = min(.20, .06 * math.sqrt(math.log(2 + portfolio.total_requests)
                                           / (1 + econ.observations)))
    diversity = 1 / math.sqrt(1 + trials)
    parts = urlsplit(url)
    origin = parts.scheme + "://" + parts.netloc
    overhead = 0. if origin in portfolio.robots_known else 1.
    # Time, accepted or uncertain bytes, extra robots request, and retry cost.
    # log1p keeps these factors from suppressing all expensive but relevant
    # evidence. No source owner/site denial can be treated as a cost discount.
    cost = (1 + .22 * math.log1p(econ.mean_latency_seconds)
            + .18 * math.log1p(econ.mean_cost_bytes / 65536)
            + .42 * overhead + .20 * attempts + .05 * depth)
    gain = .45 * relevance + .35 * gap + .20 * novelty
    priority = reliability * gain / cost + exploration + .04 * diversity
    # FIFO age proxy is small and bounded. It reduces starvation without
    # inventing trusted source importance or letting an old row bypass holds.
    priority += .035 * (1 - min(ordinal, MAX_ROWS - 1) / MAX_ROWS)
    if remaining_requests is not None:
        if type(remaining_requests) is not int or not 1 <= remaining_requests <= 128:
            raise ValueError("invalid remaining request budget")
        if overhead and remaining_requests == 1:
            priority *= .10  # acquisition cannot reach content before cap
    return MarginalYield(
        round(min(1., max(0., priority)), 8), round(relevance, 8), round(gap, 8),
        round(novelty, 8), round(reliability, 8), round(cost, 8),
        round(exploration, 8), round(diversity, 8), overhead,
    )
