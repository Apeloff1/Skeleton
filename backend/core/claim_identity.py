"""Conservative semantic identity for empirical claims.

Claim identity is stricter than semantic similarity. Two statements may concern
the same topic while asserting different empirical propositions. The fingerprint
preserves polarity, normalized relation family, quantities, units and content
anchors. Fuzzy similarity remains review-only and never shares truth state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable


_NEGATION = {"no", "not", "never", "none", "without", "fails", "failed", "cannot", "can't", "doesn't", "isn't", "aren't", "wasn't", "weren't"}
_RELATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("cause", r"\b(cause|causes|caused|causing|leads? to|led to)\b"),
    ("increase", r"\b(increase|increases|increased|increasing|raise|raises|raised|higher)\b"),
    ("decrease", r"\b(decrease|decreases|decreased|decreasing|reduce|reduces|reduced|lower|lowers|lowered)\b"),
    ("improve", r"\b(improve|improves|improved|improving)\b"),
    ("worsen", r"\b(worsen|worsens|worsened|worsening)\b"),
    ("predict", r"\b(predict|predicts|predicted|predicting|forecast|forecasts|forecasted)\b"),
    ("associate", r"\b(associate|associated|association|correlate|correlates|correlated|correlation)\b"),
    ("equal", r"\b(equal|equals|equaled|equivalent)\b"),
    ("exceed", r"\b(exceed|exceeds|exceeded|greater than|higher than)\b"),
    ("contain", r"\b(contain|contains|contained|include|includes|included)\b"),
    ("produce", r"\b(produce|produces|produced|generate|generates|generated)\b"),
    ("copula", r"\b(is|are|was|were)\b"),
)
_STOP = {
    "a", "an", "the", "this", "that", "these", "those", "of", "for", "to", "from",
    "by", "with", "in", "on", "at", "as", "and", "or", "but", "than", "measured",
}
_UNIT_ALIASES = {
    "%": "percent", "percent": "percent", "percentage": "percent",
    "ms": "millisecond", "millisecond": "millisecond", "milliseconds": "millisecond",
    "s": "second", "sec": "second", "second": "second", "seconds": "second",
    "kg": "kilogram", "kilogram": "kilogram", "kilograms": "kilogram",
    "g": "gram", "gram": "gram", "grams": "gram",
    "mb": "megabyte", "megabyte": "megabyte", "megabytes": "megabyte",
    "gb": "gigabyte", "gigabyte": "gigabyte", "gigabytes": "gigabyte",
}


@dataclass(frozen=True, slots=True)
class ClaimFingerprint:
    claim: str
    normalized: str
    polarity: str
    relation: str
    quantities: tuple[str, ...]
    units: tuple[str, ...]
    content_tokens: tuple[str, ...]
    identity_sha256: str


@dataclass(frozen=True, slots=True)
class ClaimMatch:
    left_sha256: str
    right_sha256: str
    identity_equal: bool
    structurally_compatible: bool
    lexical_similarity: float
    disposition: str
    reasons: tuple[str, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _clean(text: str) -> str:
    """Normalize claim text in linear time while preserving decimal points."""
    text = text.casefold().replace("−", "-").replace("–", "-").replace("—", "-")
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789+-/")
    cleaned: list[str] = []
    last = len(text) - 1
    for idx, ch in enumerate(text):
        if ch == "%":
            cleaned.append(" percent ")
            continue
        if ch == ".":
            is_decimal = idx > 0 and idx < last and text[idx - 1].isdigit() and text[idx + 1].isdigit()
            cleaned.append("." if is_decimal else " ")
            continue
        cleaned.append(ch if ch in allowed else " ")
    return " ".join("".join(cleaned).split())


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"): return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"): return token[:-3]
    if len(token) > 4 and token.endswith("ed"): return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"): return token[:-1]
    return token


def _relation(normalized: str) -> str:
    for family, pattern in _RELATION_PATTERNS:
        if re.search(pattern, normalized): return family
    return "unspecified"


def fingerprint_claim(claim: str) -> ClaimFingerprint:
    claim = " ".join(str(claim).split()).strip()
    if not claim: raise ValueError("claim cannot be blank")
    normalized = _clean(claim); raw_tokens = normalized.split()
    polarity = "negative" if any(token in _NEGATION for token in raw_tokens) else "positive"
    relation = _relation(normalized)
    quantities = tuple(re.findall(r"(?<![a-z])[-+]?\d+(?:\.\d+)?", normalized))
    units: list[str] = []
    for token in raw_tokens:
        canonical = _UNIT_ALIASES.get(token)
        if canonical and canonical not in units: units.append(canonical)
    content = tuple(sorted(dict.fromkeys(
        _stem(token) for token in raw_tokens
        if token not in _STOP and token not in _NEGATION and token not in _UNIT_ALIASES
        and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", token)
    )))
    identity_payload = {"polarity": polarity, "relation": relation, "quantities": quantities,
                        "units": tuple(units), "content_tokens": content}
    return ClaimFingerprint(claim, normalized, polarity, relation, quantities, tuple(units), content, _sha(identity_payload))


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


class ClaimIdentityEngine:
    def compare(self, left: str, right: str) -> ClaimMatch:
        a, b = fingerprint_claim(left), fingerprint_claim(right)
        identity_equal = a.identity_sha256 == b.identity_sha256
        reasons: list[str] = []
        if a.polarity != b.polarity: reasons.append("polarity_differs")
        if a.relation != b.relation: reasons.append("relation_differs")
        if a.quantities != b.quantities: reasons.append("quantities_differ")
        if a.units != b.units: reasons.append("units_differ")
        lexical = round(_jaccard(a.content_tokens, b.content_tokens), 6)
        structurally_compatible = not reasons
        if identity_equal:
            disposition = "same_identity"
        elif structurally_compatible and lexical >= 0.80:
            disposition = "review_equivalence_candidate"; reasons.append("high_lexical_similarity_requires_review")
        elif lexical >= 0.60:
            disposition = "related_not_equivalent"
        else:
            disposition = "distinct"
        payload = {"left_sha256": a.identity_sha256, "right_sha256": b.identity_sha256,
                   "identity_equal": identity_equal, "structurally_compatible": structurally_compatible,
                   "lexical_similarity": lexical, "disposition": disposition, "reasons": tuple(reasons)}
        return ClaimMatch(a.identity_sha256, b.identity_sha256, identity_equal, structurally_compatible,
                          lexical, disposition, tuple(reasons), _sha(payload))

    @staticmethod
    def canonical_id(claim: str) -> str:
        return fingerprint_claim(claim).identity_sha256

    @staticmethod
    def verify(match: ClaimMatch) -> bool:
        payload = {"left_sha256": match.left_sha256, "right_sha256": match.right_sha256,
                   "identity_equal": match.identity_equal, "structurally_compatible": match.structurally_compatible,
                   "lexical_similarity": match.lexical_similarity, "disposition": match.disposition,
                   "reasons": match.reasons}
        return _sha(payload) == match.attestation_sha256
