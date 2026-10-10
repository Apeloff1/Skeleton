"""Bounded, explainable evidence logic. Unknown is not false or permission.

These are software reasoning aids, not claims of calibrated model reasoning.
Deictic references require explicit bindings; source text cannot supply policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping


class Truth(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


def conjunction(values: tuple[Truth, ...]) -> Truth:
    if not values or len(values) > 64 or any(not isinstance(v, Truth) for v in values):
        raise ValueError("invalid logic operands")
    if Truth.FALSE in values:
        return Truth.FALSE
    if Truth.CONFLICT in values:
        return Truth.CONFLICT
    return Truth.UNKNOWN if Truth.UNKNOWN in values else Truth.TRUE


def disjunction(values: tuple[Truth, ...]) -> Truth:
    if not values or len(values) > 64 or any(not isinstance(v, Truth) for v in values):
        raise ValueError("invalid logic operands")
    if Truth.TRUE in values:
        return Truth.TRUE
    if Truth.CONFLICT in values:
        return Truth.CONFLICT
    return Truth.UNKNOWN if Truth.UNKNOWN in values else Truth.FALSE


def negate(value: Truth) -> Truth:
    if not isinstance(value, Truth):
        raise ValueError("invalid truth")
    return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE,
            Truth.UNKNOWN: Truth.UNKNOWN, Truth.CONFLICT: Truth.CONFLICT}[value]


def _text(value: str, maximum: int = 128) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError("invalid matrix identifier")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    key: str
    truth: Truth
    evidence_ref: str
    expires_at: float

    def __post_init__(self) -> None:
        _text(self.key)
        _text(self.evidence_ref, 256)
        if not isinstance(self.truth, Truth) or isinstance(self.expires_at, bool) or not isfinite(self.expires_at):
            raise ValueError("invalid evidence fact")


@dataclass(frozen=True, slots=True)
class MatrixRule:
    rule_id: str
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    required_slots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.rule_id)
        if not self.all_of and not self.any_of:
            raise ValueError("rule requires evidence predicates")
        for values in (self.all_of, self.any_of, self.unless, self.required_slots):
            if len(values) > 32 or len(set(values)) != len(values):
                raise ValueError("invalid matrix rule size")
            for value in values:
                _text(value)
        if any(s not in QUESTION_SLOTS for s in self.required_slots):
            raise ValueError("unsupported question slot")


QUESTION_SLOTS = frozenset(("when", "how", "why", "what", "where", "that", "this", "there"))


@dataclass(frozen=True, slots=True)
class MatrixDecision:
    rule_id: str
    truth: Truth
    eligible: bool
    found: tuple[str, ...]
    missing: tuple[str, ...]
    incomplete: tuple[str, ...]
    search_queries: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def evaluate_matrix(rule: MatrixRule, facts: tuple[EvidenceFact, ...],
                    bindings: Mapping[str, str], *, now: float,
                    genre: str, era: str, engine: str) -> MatrixDecision:
    if isinstance(now, bool) or not isfinite(now) or len(facts) > 256 or len(bindings) > 32:
        raise ValueError("matrix budget exceeded")
    for value in (genre, era, engine):
        _text(value, 64)
    if len({f.key for f in facts}) != len(facts):
        raise ValueError("duplicate facts must be reconciled explicitly")
    by_key = {f.key: f for f in facts}
    for key, value in bindings.items():
        if key not in QUESTION_SLOTS:
            raise ValueError("unknown question binding")
        _text(value, 256)
    needed = tuple(dict.fromkeys(rule.all_of + rule.any_of + rule.unless))
    found = tuple(k for k in needed if k in by_key and by_key[k].expires_at > now)
    missing = tuple(k for k in needed if k not in by_key)
    incomplete = tuple(k for k in needed if k in by_key and (
        by_key[k].expires_at <= now or by_key[k].truth in (Truth.UNKNOWN, Truth.CONFLICT)))
    slot_gaps = tuple(s for s in rule.required_slots if s not in bindings)
    def state(key: str) -> Truth:
        return by_key[key].truth if key in found else Truth.UNKNOWN
    parts = []
    if rule.all_of:
        parts.append(conjunction(tuple(state(k) for k in rule.all_of)))
    if rule.any_of:
        parts.append(disjunction(tuple(state(k) for k in rule.any_of)))
    # Unknown exception status prevents eligibility, even if another branch succeeds.
    if rule.unless:
        parts.append(conjunction(tuple(negate(state(k)) for k in rule.unless)))
    if slot_gaps:
        parts.append(Truth.UNKNOWN)
    truth = conjunction(tuple(parts))
    gaps = tuple(dict.fromkeys(missing + incomplete + slot_gaps))
    queries = tuple(f"{genre} {era} {engine} {gap} primary evidence" for gap in gaps[:16])
    return MatrixDecision(rule.rule_id, truth, truth is Truth.TRUE, found, missing,
                          incomplete + slot_gaps, queries,
                          tuple(sorted({by_key[k].evidence_ref for k in found})))


EXCEPTION_MATRIX = {
    "resource_pressure": ("checkpoint_then_defer", False, 0),
    "foreground_interrupt": ("checkpoint_then_yield", False, 0),
    "transient_network": ("bounded_backoff", True, 2),
    "source_changed": ("invalidate_and_reacquire", False, 0),
    "missing_evidence": ("acquire_primary_evidence", False, 0),
    "contradiction": ("independent_review", False, 0),
    "privacy": ("deny_and_redact", False, 0),
    "rights": ("block_release_human_review", False, 0),
    "corruption": ("quarantine_rebuild_projection", False, 0),
    "unsupported_engine": ("report_capability_gap", False, 0),
}


def exception_action(category: str, attempts: int) -> tuple[str, bool]:
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise ValueError("invalid retry count")
    action, retryable, maximum = EXCEPTION_MATRIX.get(category, ("stop_operator_review", False, 0))
    return action, retryable and attempts < maximum
