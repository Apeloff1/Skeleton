"""Deterministic, operator-authorized query expansion for bounded Dragon research.

Variants are derived only from an operator-authored research objective. Web
content cannot introduce questions, URLs, credentials, hosts, instructions or
new research purposes. The output is lexical retrieval intent, never a
permission to acquire a document or to contact a remote service.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import re

from .contracts import CampaignMandate, digest, integer
from .objectives import ObjectivePlan, ResearchObjective

_TOKEN = re.compile(r"[^\W_]{2,}", re.UNICODE)
# Exact operator constraints use a boundary-aware tokenizer that preserves
# hyphens and underscores in normalized operator terms. Broad query ranking
# uses _TOKEN; these are deliberately separate concerns.
_CONSTRAINT_TOKEN = re.compile(r"(?<![\w-])[\w-]{2,48}(?![\w-])", re.UNICODE)


def passage_matches_operator_terms(
    text: str, required: tuple[str, ...], blocked: tuple[str, ...],
) -> bool:
    """A soft query may suggest candidates, but a hard filter is mandatory.

    No case-insensitive substring matching: "audit" must not match
    "auditing"; "source-id" is one token, not two independent tokens.
    This function only checks literal terms in current retained passage
    text, never semantic equivalence or page-level rights.
    """
    if not isinstance(text, str):
        raise TypeError("source text must be a literal string")
    if len(text.encode("utf-8")) > 24_000:
        raise ValueError("objective passage text exceeds local bound")
    if not isinstance(required, tuple) or not isinstance(blocked, tuple):
        raise TypeError("objective term filters must be immutable")
    if len(required) > 16 or len(blocked) > 16:
        raise ValueError("operator term filter capacity exceeded")
    for token in required + blocked:
        if (
            not isinstance(token, str)
            or re.fullmatch(r"[\w-]{2,48}", token) is None
            or token != token.casefold()
        ):
            raise ValueError("invalid normalized operator term")
    tokens = set(_CONSTRAINT_TOKEN.findall(text.casefold()))
    return all(term in tokens for term in required) and not any(
        term in tokens for term in blocked
    )
_NOISE = frozenset({
    "the", "with", "from", "that", "this", "and", "for", "when",
    "were", "have", "what", "which", "where", "about", "does",
    "are", "can", "how", "was", "into", "their", "there", "they",
})


@dataclass(frozen=True)
class QueryVariant:
    objective_id: str
    family: str
    terms: tuple[str, ...]
    query: str
    priority: float
    weight: float
    ordinal: int
    retrieval_only: bool = True
    required_terms: tuple[str, ...] = ()
    blocked_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.terms or len(self.terms) > 16:
            raise ValueError("query term capacity exceeded")
        if " ".join(self.terms) != self.query:
            raise ValueError("unbound query terms")
        if self.family not in ("core", "required", "focused", "intersection"):
            raise ValueError("invalid query family")
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("invalid query order")
        # Validate even directly constructed query receipts: compiler-created
        # variants carry these immutable hard constraints into both rankers.
        passage_matches_operator_terms("", self.required_terms, self.blocked_terms)
        if set(self.required_terms) & set(self.blocked_terms):
            raise ValueError("contradictory objective term constraints")
        if len(set(self.required_terms)) != len(self.required_terms) or (
            len(set(self.blocked_terms)) != len(self.blocked_terms)
        ):
            raise ValueError("duplicate operator term constraint")


@dataclass(frozen=True)
class QueryLattice:
    mandate_digest: str
    objective_plan_digest: str
    queries: tuple[QueryVariant, ...]
    objective_queries: tuple[tuple[str, int], ...]
    total_terms: int
    excluded_terms: tuple[str, ...]
    lattice_digest: str
    may_crawl: bool = False
    may_promote_knowledge: bool = False


def _words(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        token.casefold() for token in _TOKEN.findall(value)
        if token.casefold() not in _NOISE
    ))


def _patterns(objective: ResearchObjective, cap: int) -> tuple[tuple[str, tuple[str, ...]], ...]:
    words = _words(objective.question)
    required = tuple(objective.required_terms)
    blocked = set(objective.blocked_terms)
    # Never silently drop explicit required terms to fit a retrieval query.
    if len(required) > 16:
        raise ValueError("required term capacity exceeded")
    selected = [term for term in words if term not in blocked]
    patterns = []
    if selected:
        patterns.append(("core", tuple(selected[:min(cap, 8)])))
    if required:
        patterns.append(("required", required))
    if selected:
        for start in range(0, min(len(selected), cap * 2), cap):
            focus = tuple(selected[start:start + cap])
            if focus:
                patterns.append(("focused", focus))
    if selected and required:
        intersection = tuple(dict.fromkeys(required + tuple(selected[:max(0, cap - len(required))])))
        if len(intersection) <= 16:
            patterns.append(("intersection", intersection))
    return tuple(patterns)


def compile_query_lattice(
    mandate: CampaignMandate,
    plan: ObjectivePlan,
    *,
    now: float,
    authorized: bool,
    max_variants_per_objective: int = 4,
    max_total_variants: int = 96,
    terms_per_variant: int = 6,
) -> QueryLattice:
    mandate.admit(now=now, authorized=authorized)
    if not isinstance(plan, ObjectivePlan) or plan.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign objective plan")
    integer(max_variants_per_objective, "variants per objective", 1, 8)
    integer(max_total_variants, "query lattice capacity", 1, 128)
    integer(terms_per_variant, "query width", 2, 12)
    if len(plan.objectives) > 64:
        raise ValueError("invalid objective universe")
    rows = []
    observed = []
    all_blocked = set()
    for objective in plan.objectives:
        if not isinstance(objective, ResearchObjective):
            raise TypeError("typed objective required")
        all_blocked.update(objective.blocked_terms)
        patterns = _patterns(objective, terms_per_variant)
        seen = set()
        count = 0
        for family, terms in patterns:
            terms = tuple(x for x in terms if x not in objective.blocked_terms)
            if not terms or terms in seen:
                continue
            if len(rows) >= max_total_variants:
                raise ValueError("query lattice capacity exceeded")
            seen.add(terms)
            ordinal = count
            count += 1
            rows.append(QueryVariant(
                objective_id=objective.objective_id,
                family=family, terms=terms, query=" ".join(terms),
                priority=objective.priority,
                weight=round(objective.priority * (1.0 if family == "required" else
                    0.95 if family == "intersection" else
                    0.8 if family == "core" else 0.65), 8),
                ordinal=ordinal,
                required_terms=tuple(objective.required_terms),
                blocked_terms=tuple(objective.blocked_terms),
            ))
            if count >= max_variants_per_objective:
                break
        if not count:
            raise ValueError("objective has no safe retrieval query")
        observed.append((objective.objective_id, count))
    rows.sort(key=lambda x: (-x.weight, x.objective_id, x.ordinal, x.query))
    payload = {
        "mandate": mandate.fingerprint,
        "plan": plan.plan_digest,
        "queries": [asdict(x) for x in rows],
        "blocked_terms": sorted(all_blocked),
    }
    return QueryLattice(
        mandate_digest=mandate.fingerprint,
        objective_plan_digest=plan.plan_digest,
        queries=tuple(rows),
        objective_queries=tuple(sorted(observed)),
        total_terms=sum(len(row.terms) for row in rows),
        excluded_terms=tuple(sorted(all_blocked)),
        lattice_digest=digest(payload),
    )
