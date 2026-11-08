"""Exact-span quantitative discrepancy triage over retained research passages.

Two different numeric observations might refer to different dates, people,
places, baselines or measurement protocols. A lexical difference is therefore
only a candidate for a human reviewer, never a factual contradiction. Every
quantity and comparison is bound to current, untruncated, fully hash-validated
source text and the authenticated source-policy projection.

Only explicitly supported units are compared: distance, mass, duration,
percent and same-currency amounts. No exchange rates, invented conversions,
truncated numbers or unbounded regular-expression execution are used.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Iterable
import re

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion

_NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.,])"
    r"(?:(?P<symbol>[$€£])\s*)?"
    r"(?P<number>(?:0|[1-9]\d{0,11})(?:\.\d{1,4})?)"
    r"\s*(?P<unit>%|percent|kilograms?|kg|grams?|g|kilometers?|km|"
    r"meters?|miles?|mi|seconds?|secs?|minutes?|mins?|hours?|hrs?|"
    r"days?|USD|EUR|GBP)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOP = frozenset(("the", "for", "with", "from", "and", "was", "were",
                   "that", "this", "are", "has", "have", "about",
                   "they", "them", "into", "when", "where", "then", "after"))
_UNITS = {
    "kg": ("mass_kg", Decimal("1")),
    "kilogram": ("mass_kg", Decimal("1")),
    "kilograms": ("mass_kg", Decimal("1")),
    "g": ("mass_kg", Decimal("0.001")),
    "gram": ("mass_kg", Decimal("0.001")),
    "grams": ("mass_kg", Decimal("0.001")),
    "km": ("distance_m", Decimal("1000")),
    "kilometer": ("distance_m", Decimal("1000")),
    "kilometers": ("distance_m", Decimal("1000")),
    "meter": ("distance_m", Decimal("1")),
    "meters": ("distance_m", Decimal("1")),
    "mi": ("distance_m", Decimal("1609.344")),
    "mile": ("distance_m", Decimal("1609.344")),
    "miles": ("distance_m", Decimal("1609.344")),
    "second": ("time_s", Decimal("1")),
    "seconds": ("time_s", Decimal("1")),
    "sec": ("time_s", Decimal("1")),
    "secs": ("time_s", Decimal("1")),
    "minute": ("time_s", Decimal("60")),
    "minutes": ("time_s", Decimal("60")),
    "min": ("time_s", Decimal("60")),
    "mins": ("time_s", Decimal("60")),
    "hour": ("time_s", Decimal("3600")),
    "hours": ("time_s", Decimal("3600")),
    "hr": ("time_s", Decimal("3600")),
    "hrs": ("time_s", Decimal("3600")),
    "day": ("time_s", Decimal("86400")),
    "days": ("time_s", Decimal("86400")),
    "%": ("percent", Decimal("1")),
    "percent": ("percent", Decimal("1")),
    "usd": ("USD", Decimal("1")),
    "eur": ("EUR", Decimal("1")),
    "gbp": ("GBP", Decimal("1")),
}
_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}


@dataclass(frozen=True)
class NumericMention:
    source_id: str
    source_content_hash: str
    canonical_url: str
    original_passage_hash: str
    start: int
    end: int
    raw: str
    value: str
    normalized_unit: str
    normalized_value: str
    context_terms: tuple[str, ...]
    objective_ids: tuple[str, ...]
    source_review_required: bool = True


@dataclass(frozen=True)
class NumericDiscrepancy:
    left_source_id: str
    right_source_id: str
    objective_id: str
    normalized_unit: str
    left_mention_start: int
    right_mention_start: int
    left_value: str
    right_value: str
    relative_gap: float
    shared_context_terms: tuple[str, ...]
    same_source_content_hash: bool
    relationship: str = "unverified_quantitative_difference"
    human_review_required: bool = True
    factual_contradiction_established: bool = False


@dataclass(frozen=True)
class NumericSignalReport:
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    retrieval_digest: str
    mentions: tuple[NumericMention, ...]
    candidates: tuple[NumericDiscrepancy, ...]
    rejected_ambiguous_numbers: int
    examined_passages: int
    detected_unit_families: tuple[str, ...]
    report_digest: str
    publication_authorized: bool = False
    unit_conversion_accuracy_certified: bool = False
    verified_claims_count: int = 0


def _parse_number(raw: str) -> Decimal:
    value = Decimal(raw)
    if not value.is_finite() or value < 0 or value > Decimal("1e16"):
        raise ValueError("invalid bounded numeric value")
    return value


def _terms(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(
        x.casefold() for x in _TOKEN.findall(text)
        if x.casefold() not in _STOP and not x.isnumeric()
    )))


def _extract(hit, *, context_chars: int = 72) -> tuple[tuple[NumericMention, ...], int]:
    text = hit.text
    observed, rejected = [], 0
    for match in _NUMBER.finditer(text):
        number, suffix, symbol = match.group("number", "unit", "symbol")
        if not symbol and not suffix:
            rejected += 1
            continue
        if symbol and suffix:
            normalized = _UNITS.get(suffix.casefold())
            if normalized is None or normalized[0] != _SYMBOLS[symbol]:
                rejected += 1
                continue
        family, factor = (
            (_SYMBOLS[symbol], Decimal(1)) if symbol
            else _UNITS.get((suffix or "").casefold(), (None, None))
        )
        if family is None:
            rejected += 1
            continue
        try:
            value = _parse_number(number)
            result = value * factor
        except (InvalidOperation, ValueError):
            rejected += 1
            continue
        begin, end = match.span()
        context = text[max(0, begin - context_chars):min(len(text), end + context_chars)]
        observed.append(NumericMention(
            source_id=hit.source_id,
            source_content_hash=hit.source_hash,
            canonical_url=hit.canonical_url,
            original_passage_hash=hit.passage_hash,
            start=hit.start + begin, end=hit.start + end,
            raw=match.group(),
            value=format(value, "f"),
            normalized_unit=family,
            normalized_value=format(result, "f"),
            context_terms=_terms(context),
            objective_ids=hit.matched_objective_ids,
        ))
    return tuple(observed), rejected


def inspect_numeric_discrepancies(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_mentions: int = 384,
    max_comparisons: int = 512,
    context_overlap_required: int = 2,
    min_relative_gap: float = 0.01,
) -> NumericSignalReport:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_mentions, "numeric mention capacity", 1, 512)
    integer(max_comparisons, "numeric discrepancy capacity", 1, 1024)
    integer(context_overlap_required, "numeric context overlap", 1, 8)
    if not isinstance(min_relative_gap, (int, float)) or isinstance(min_relative_gap, bool):
        raise ValueError("invalid numeric difference threshold")
    if not 0 <= min_relative_gap <= 1:
        raise ValueError("invalid numeric relative gap")
    if policy.mandate_digest != mandate.fingerprint or (
        retrieval.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("foreign numerical research source")
    current = CrawlRun.from_snapshot(snapshot).snapshot()
    if any(x != current["snapshot_digest"] for x in (
        policy.source_snapshot_digest, retrieval.source_snapshot_digest,
    )):
        raise PermissionError("quantitative comparison must bind one source snapshot")
    if retrieval.excluded_sources != policy.excluded_source_ids:
        raise PermissionError("source withdrawal set changed during comparison")
    allowed = set(policy.allowed_source_ids)
    mentions = []
    dedup = set()
    rejected = 0
    for hit in retrieval.results:
        source = current["sources"].get(hit.source_id)
        if source is None or hit.source_id not in allowed:
            raise PermissionError("numeric passage source unavailable")
        text = source["text"]
        if (
            source["content_hash"] != hit.source_hash
            or source["canonical_url"] != hit.canonical_url
            or source["text_truncated"] is not False
            or source["review_state"] != "unreviewed"
            or sha256(text.encode("utf-8")).hexdigest() != source["preserved_text_hash"]
            or text[hit.start:hit.end] != hit.text
            or sha256(hit.text.encode("utf-8")).hexdigest() != hit.passage_hash
        ):
            raise PermissionError("numeric passage no longer source-anchored")
        observations, dropped = _extract(hit)
        rejected += dropped
        for observation in observations:
            key = (observation.source_id, observation.start, observation.end)
            if key in dedup:
                continue
            if len(mentions) >= max_mentions:
                raise ValueError("numeric evidence universe exceeds capacity")
            dedup.add(key)
            mentions.append(observation)
    mentions.sort(key=lambda x: (
        x.normalized_unit, x.source_id, x.start, x.end
    ))
    by_family = defaultdict(list)
    for mention in mentions:
        for objective_id in mention.objective_ids:
            by_family[(objective_id, mention.normalized_unit)].append(mention)
    discrepancies = []
    seen_pairs = set()
    for (objective_id, unit), members in sorted(by_family.items()):
        for i, left in enumerate(members):
            for right in members[i+1:]:
                if left.source_id == right.source_id:
                    continue
                shared = tuple(sorted(
                    set(left.context_terms) & set(right.context_terms)
                ))
                if len(shared) < context_overlap_required:
                    continue
                a, b = Decimal(left.normalized_value), Decimal(right.normalized_value)
                if a == b:
                    continue
                relative = abs(a - b) / max(abs(a), abs(b), Decimal(1))
                if relative < Decimal(str(min_relative_gap)):
                    continue
                source_pair = tuple(sorted((
                    (left.source_id, left.start), (right.source_id, right.start)
                )))
                identity = (objective_id, unit, source_pair)
                if identity in seen_pairs:
                    continue
                seen_pairs.add(identity)
                if len(discrepancies) >= max_comparisons:
                    raise ValueError("bounded quantitative comparison capacity exceeded")
                discrepancies.append(NumericDiscrepancy(
                    left_source_id=left.source_id,
                    right_source_id=right.source_id,
                    objective_id=objective_id,
                    normalized_unit=unit,
                    left_mention_start=left.start,
                    right_mention_start=right.start,
                    left_value=left.normalized_value,
                    right_value=right.normalized_value,
                    relative_gap=round(float(relative), 8),
                    shared_context_terms=shared,
                    same_source_content_hash=(
                        left.source_content_hash == right.source_content_hash
                    ),
                ))
    discrepancies.sort(key=lambda x: (-x.relative_gap, x.objective_id,
                                      x.normalized_unit, x.left_source_id,
                                      x.right_source_id))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current["snapshot_digest"],
        "policy": policy.policy_digest, "retrieval": retrieval.fusion_digest,
        "mentions": [asdict(x) for x in mentions],
        "candidates": [asdict(x) for x in discrepancies],
        "ambiguous": rejected,
        "limits": (max_mentions, max_comparisons,
                   context_overlap_required, min_relative_gap),
    }
    return NumericSignalReport(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=current["snapshot_digest"],
        source_policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        mentions=tuple(mentions), candidates=tuple(discrepancies),
        rejected_ambiguous_numbers=rejected,
        examined_passages=len(retrieval.results),
        detected_unit_families=tuple(sorted(
            {x.normalized_unit for x in mentions}
        )),
        report_digest=digest(payload),
    )
