"""Deterministic host-fair, objective-aware real crawler frontier scheduler.

The canonical CrawlRun remains the ONLY transport and persistence authority.
This scheduler chooses an existing, already-admitted due frontier row; it never
enqueues URLs, evaluates untrusted HTML instructions, issues a worker lease,
reserves bytes, changes grants, bypasses live robots or opens a network socket.

The balanced strategy favors hosts with fewer captured documents, bounded
URL/query lexical affinity, retries with lower pressure and breadth-first
progress. Default FIFO stays identical for existing sessions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from urllib.parse import unquote, urlsplit

from .frontier_coverage import build_coverage_index, score_indexed_candidate
from .adaptive_navigation import adaptive_priority, origin_health
from .information_portfolio import build_information_portfolio, marginal_yield
from .dragon_companion import CompanionProfile
from .navigation_backlog import deliberate


_TOKEN = re.compile(r"[a-z0-9]{2,64}")
_MAX_ROWS = 512
_MAX_TERMS = 32


@dataclass(frozen=True)
class FrontierDecision:
    url: str
    host: str
    eligible_urls: int
    host_captured_documents: int
    objective_url_affinity: float
    fairness_score: float
    algorithm: str
    canonical_runner_admission_required: bool = True
    actual_dispatch_authorized: bool = False
    curriculum_base_score: float | None = None
    curriculum_quest: str | None = None
    discourse: dict | None = None


def _lexical_terms(text: str) -> frozenset[str]:
    # No decoded page bodies or source instructions are inputs. URI path and
    # operator-requested query alone are used as advisory dispatch ordering.
    return frozenset(_TOKEN.findall(text.casefold()))


def choose_frontier(
    frontier: list[dict], *, sources: dict, host_ready: dict,
    query: str, now: float, strategy: str = "fifo", events=None,
    measurements=None, robots=None, remaining_requests=None, companion=None,
) -> tuple[dict | None, FrontierDecision | None]:
    if strategy not in ("fifo", "balanced", "coverage", "companion", "companion_curiosity",
                        "companion_scholar", "companion_guardian"):
        raise ValueError("unknown bounded frontier scheduling algorithm")
    if strategy.startswith("companion") and not isinstance(companion, CompanionProfile):
        raise ValueError("companion strategy requires canonical evidence profile")
    if (not isinstance(frontier, list) or len(frontier) > _MAX_ROWS
            or not isinstance(sources, dict)
            or not isinstance(host_ready, dict)
            or not isinstance(query, str) or len(query) > 1024
            or isinstance(now, bool) or not isinstance(now, (int, float))
            or not math.isfinite(now)):
        raise ValueError("invalid canonical frontier scheduling inputs")
    terms = set(tuple(sorted(_lexical_terms(query)))[:_MAX_TERMS])
    counted = Counter()
    for source in sources.values():
        if not isinstance(source, dict):
            raise ValueError("invalid canonical source row")
        host = urlsplit(source["canonical_url"]).hostname
        counted[host] += 1
    # FIFO remains strictly compatible. Outcome-driven scores apply only to
    # the two explicit adaptive selection strategies, not eligibility.
    health_by_host = {}
    eligible = []
    for ordinal, row in enumerate(frontier):
        if not isinstance(row, dict):
            raise ValueError("invalid frontier entry")
        url, depth, attempts = row["url"], row["depth"], row["attempts"]
        p = urlsplit(url)
        host = p.hostname
        if host is None:
            raise ValueError("canonical frontier URL has no host")
        due = max(row["ready_at"], host_ready.get(host, 0))
        if due > now:
            continue
        url_terms = _lexical_terms(unquote(p.path, errors="replace"))
        overlap = (len(terms & url_terms) / len(terms)) if terms else 0.0
        # Captured host distribution, not unverified page importance.
        # The score has a strict 0..1 envelope and no external effects.
        score = round(
            .42 / (1 + counted[host])
            + .28 * overlap
            + .19 / (1 + depth)
            + .11 / (1 + attempts),
            8,
        )
        if events is not None and strategy == "balanced":
            if host not in health_by_host:
                health_by_host[host] = origin_health(events, host)
            score = adaptive_priority(score, health_by_host[host], coverage_cost=False)
        eligible.append((
            ordinal, row, host, overlap, score, due,
        ))
    if not eligible:
        return None, None
    curriculum_base = None
    discourse = None
    if strategy == "fifo":
        index, row, host, overlap, score, _due = eligible[0]
    elif strategy == "balanced":
        index, row, host, overlap, score, _due = min(
            eligible,
            key=lambda x: (
                -x[4], x[1]["attempts"], x[1]["depth"],
                x[5], x[2], x[1]["url"], x[0],
            ),
        )
    else:
        ranked = []
        index = build_coverage_index(sources=sources, query=query)
        portfolio = None
        if measurements is not None and robots is not None:
            portfolio = build_information_portfolio(coverage=index, sources=sources,
                frontier=frontier, measurements=measurements, robots=robots, now=now)
        for candidate in eligible:
            ordinal, row, host, overlap, _score, due = candidate
            scorecard = score_indexed_candidate(
                row["url"], index=index,
                depth=row["depth"], attempts=row["attempts"],
            )
            score = scorecard.score
            if portfolio is not None:
                estimate = marginal_yield(row, portfolio=portfolio, ordinal=ordinal,
                    eligible_count=len(eligible), remaining_requests=remaining_requests)
                # Absolute coverage remains an exploration backstop when URL
                # metadata is sparse; measured marginal yield dominates.
                score = .20 * score + .80 * estimate.priority
            elif events is not None:
                if candidate[2] not in health_by_host:
                    health_by_host[candidate[2]] = origin_health(events, candidate[2])
                score = adaptive_priority(score, health_by_host[candidate[2]], coverage_cost=False)
            base = score
            exchange = None
            if strategy.startswith("companion"):
                exchange = deliberate(row, profile=companion, base=score, query=query)
                score = exchange.final_priority
            ranked.append((score, due, ordinal, candidate, base, exchange))
        _coverage, _due, _ordinal, selected, base, exchange = min(
            ranked, key=lambda x: (
                -x[0], x[1], x[3][2], x[3][1]["url"], x[2],
            ),
        )
        index, row, host, overlap, score, _due = selected
        score = _coverage
        if strategy.startswith("companion"):
            curriculum_base = base
            discourse = exchange.receipt()
    return row, FrontierDecision(
        url=row["url"], host=host, eligible_urls=len(eligible),
        host_captured_documents=counted[host],
        objective_url_affinity=round(overlap, 8),
        fairness_score=score, algorithm=strategy,
        curriculum_base_score=curriculum_base,
        curriculum_quest=companion.quest if curriculum_base is not None else None,
        discourse=discourse,
    )
