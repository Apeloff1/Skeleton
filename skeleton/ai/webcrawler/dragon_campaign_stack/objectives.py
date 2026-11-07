"""Explicit, finite research objectives with evidence-coverage targets.

Objectives are authored by the operator, never synthesized from page text,
and cannot add a URL, grant crawler rights or make source text trustworthy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import re

from .contracts import CampaignMandate, bounded_text, digest, finite, integer


_ID = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z", re.ASCII)
_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
_STAGES = frozenset(("discovery", "collection", "verification", "review"))
_DOMAINS = frozenset(("fact", "method", "timeline", "source", "counterexample", "implementation"))
_STOP = frozenset(("and", "the", "for", "with", "from", "this", "that", "which", "their"))


@dataclass(frozen=True)
class ResearchObjective:
    objective_id: str
    question: str
    dimension: str
    stage: str
    priority: float
    minimum_reviewable_passages: int
    minimum_attested_groups: int
    max_source_age_seconds: int
    required_terms: tuple[str, ...] = ()
    blocked_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.objective_id, str) or not _ID.fullmatch(self.objective_id):
            raise ValueError("invalid objective identity")
        bounded_text(self.question, "objective question", 512)
        if self.dimension not in _DOMAINS or self.stage not in _STAGES:
            raise ValueError("unsupported research objective")
        finite(self.priority, "priority", 0, 1)
        integer(self.minimum_reviewable_passages, "passage target", 1, 32)
        integer(self.minimum_attested_groups, "independence target", 1, 16)
        integer(self.max_source_age_seconds, "age policy", 60, 86400)
        if not isinstance(self.required_terms, tuple) or not isinstance(self.blocked_terms, tuple):
            raise ValueError("objective term lists must be frozen")
        if len(self.required_terms) > 16 or len(self.blocked_terms) > 16:
            raise ValueError("objective term capacity exceeded")
        for family in (self.required_terms, self.blocked_terms):
            if len(set(family)) != len(family):
                raise ValueError("duplicate normalized objective terms")
            for term in family:
                if not isinstance(term, str) or not re.fullmatch(r"[\w-]{2,48}", term) or term != term.casefold():
                    raise ValueError("objective terms must be normalized")
        if set(self.required_terms) & set(self.blocked_terms):
            raise ValueError("contradictory objective term filters")


@dataclass(frozen=True)
class ObjectivePlan:
    mandate_digest: str
    objectives: tuple[ResearchObjective, ...]
    normalized_terms: tuple[str, ...]
    stages: tuple[str, ...]
    request_scope: tuple[str, ...]
    plan_digest: str
    authorized_to_acquire: bool = False


def compile_objectives(
    mandate: CampaignMandate,
    objectives: Iterable[ResearchObjective],
    *,
    now: float,
    authorized: bool,
    max_objectives: int = 32,
) -> ObjectivePlan:
    mandate.admit(now=now, authorized=authorized)
    integer(max_objectives, "objective count", 1, 64)
    rows = tuple(objectives)
    if not rows or len(rows) > max_objectives:
        raise ValueError("a finite objective set is required")
    seen: set[str] = set()
    terms = set()
    for item in rows:
        if not isinstance(item, ResearchObjective):
            raise TypeError("typed research objectives required")
        if item.objective_id in seen:
            raise ValueError("duplicate research objective ID")
        seen.add(item.objective_id)
        tokens = {word.casefold() for word in _WORD.findall(item.question)}
        if not tokens - _STOP:
            raise ValueError("objective has no research-bearing terms")
        terms.update(tokens - _STOP)
        terms.update(item.required_terms)
    if len(terms) > 256:
        raise ValueError("objective token universe exceeded")
    sorted_rows = tuple(sorted(rows, key=lambda row: (-row.priority, row.objective_id)))
    payload = {
        "mandate": mandate.fingerprint,
        "objectives": [asdict(x) for x in sorted_rows],
        "terms": sorted(terms),
        "hosts": mandate.scope.allowed_hosts,
        "stages": sorted({x.stage for x in rows}),
    }
    return ObjectivePlan(
        mandate_digest=mandate.fingerprint,
        objectives=sorted_rows,
        normalized_terms=tuple(sorted(terms)),
        stages=tuple(sorted({x.stage for x in rows})),
        request_scope=mandate.scope.allowed_hosts,
        plan_digest=digest(payload),
    )


def objective_matches(
    objective: ResearchObjective,
    text: str,
) -> bool:
    """Lexical compatibility only; never factual or legal assessment."""
    if not isinstance(objective, ResearchObjective):
        raise TypeError("research objective required")
    if not isinstance(text, str) or len(text.encode("utf-8")) > 24_000:
        raise ValueError("unbounded evidence text")
    words = {word.casefold() for word in _WORD.findall(text)}
    question = {
        token.casefold() for token in _WORD.findall(objective.question)
        if token.casefold() not in _STOP
    }
    return (
        bool(words & (question | set(objective.required_terms)))
        and all(term in words for term in objective.required_terms)
        and not any(term in words for term in objective.blocked_terms)
    )
