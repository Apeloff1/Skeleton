"""Mechanic-first discovery across 10,240 authored-law world compositions.

Search weights written causal clauses and player consequences, NOT style names,
marketing popularity, synthetic embeddings, or random cosmetic alternatives.
Diversified retrieval prevents the first family/domain flooding all results.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from .original_foundation_compiler import (
    FoundationError, FoundationLaw, REGIMES, ROOTS,
    STRUCTURED_FOUNDATIONS, foundation_at,
)

_DOMAIN_NAMES = frozenset(root.domain for root in ROOTS)
_OPERATOR_NAMES = frozenset(regime.operator for regime in REGIMES)
_END_POLICIES = frozenset({
    "closed", "open", "persistent", "postgame",
    "unwinnable", "branched", "looping",
})


@dataclass(frozen=True)
class FoundationHit:
    foundation: FoundationLaw
    match_score: int
    matched_tokens: tuple[str, ...]
    source_fields: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "foundation_id": self.foundation.foundation_id,
            "index": str(self.foundation.foundation_index),
            "title": self.foundation.title,
            "domain": self.foundation.domain,
            "operator": self.foundation.regime.operator,
            "root_ending": self.foundation.ending_policy,
            "regime_ending": self.foundation.secondary_ending_policy,
            "root_law": self.foundation.root.invariant,
            "regime_law": self.foundation.regime.invariant,
            "coupling": self.foundation.coupling,
            "player_lever": self.foundation.player_lever,
            "failure_pressure": self.foundation.failure_pressure,
            "match_score": self.match_score,
            "matched_tokens": list(self.matched_tokens),
            "source_fields": list(self.source_fields),
            "provenance": self.foundation.provenance,
            "status": self.foundation.implementation_status,
        }


def _validate_filters(
    domain: str | None, operator: str | None, ending: str | None,
    limit: int, query: str,
) -> tuple[str, ...]:
    if domain is not None and domain not in _DOMAIN_NAMES:
        raise FoundationError("unsupported foundation discipline filter")
    if operator is not None and operator not in _OPERATOR_NAMES:
        raise FoundationError("unknown consequence operator")
    if ending is not None and ending not in _END_POLICIES:
        raise FoundationError("unknown world ending policy")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise FoundationError("search limit must be an integer from 1 to 100")
    if not isinstance(query, str) or len(query.encode("utf-8")) > 512:
        raise FoundationError("invalid or oversized causal search phrase")
    words = tuple(dict.fromkeys(re.findall(r"[a-z0-9][a-z0-9-]{1,32}", query.casefold())))
    if len(words) > 16:
        raise FoundationError("search query has too many independent concepts")
    return words


def _score(foundation: FoundationLaw, terms: tuple[str, ...]) -> FoundationHit | None:
    fields = {
        "root_title": (foundation.root.title, 9),
        "root_law": (foundation.root.invariant, 6),
        "regime_title": (foundation.regime.title, 8),
        "regime_law": (foundation.regime.invariant, 5),
        "authored_coupling": (foundation.coupling, 7),
        "player_lever": (foundation.player_lever, 4),
        "failure_pressure": (foundation.failure_pressure, 3),
        "discipline": (foundation.root.domain, 6),
        "operator": (foundation.regime.operator, 6),
    }
    if not terms:
        return FoundationHit(foundation, 0, (), ())
    total, found, sources = 0, set(), set()
    for field, (description, weight) in fields.items():
        lower = description.casefold()
        for term in terms:
            if term in lower:
                found.add(term)
                sources.add(field)
                total += weight
    if len(found) != len(terms):
        return None
    # Distinct source fields and cross-law interactions improve relevance,
    # but no claim is made about subjective quality or native playability.
    total += len(sources) * 2
    return FoundationHit(foundation, total, terms, tuple(sorted(sources)))


def search_foundations(
    query: str = "", *, domain: str | None = None,
    operator: str | None = None, ending: str | None = None,
    limit: int = 12, diverse: bool = True,
) -> tuple[FoundationHit, ...]:
    """Deterministically filter and rank full 10,240-world registry.

    Equal text scores are resolved by exact foundation index. For diverse
    mode, candidates are distributed across root domains and regime operator
    classes rather than filling the list with near-identical one-family
    variations.
    """
    terms = _validate_filters(domain, operator, ending, limit, query)
    if type(diverse) is not bool:
        raise FoundationError("diversity must be boolean")
    candidates = []
    for index in range(STRUCTURED_FOUNDATIONS):
        law = foundation_at(index)
        if (domain is not None and law.domain != domain) or (
            operator is not None and law.regime.operator != operator
        ) or (ending is not None and law.ending_policy != ending):
            continue
        result = _score(law, terms)
        if result is not None:
            candidates.append(result)
    candidates.sort(key=lambda hit: (-hit.match_score, hit.foundation.foundation_index))
    if not diverse:
        return tuple(candidates[:limit])
    # Highest-ranked option from each combination is displayed first.
    # Even with all 10k indexed, only 160 domain/operator groups can
    # crowd one display wave; this is bounded-memory presentation after
    # exact authored-literal matching.
    buckets: dict[tuple[str, str], list[FoundationHit]] = {}
    for hit in candidates:
        key = (hit.foundation.domain, hit.foundation.regime.operator)
        buckets.setdefault(key, []).append(hit)
    groups = sorted(
        buckets, key=lambda key: (
            -buckets[key][0].match_score,
            buckets[key][0].foundation.foundation_index,
        ),
    )
    selected = []
    round_index = 0
    while len(selected) < limit:
        found = False
        for key in groups:
            if len(buckets[key]) > round_index:
                selected.append(buckets[key][round_index])
                found = True
                if len(selected) >= limit:
                    break
        if not found:
            break
        round_index += 1
    return tuple(selected)
