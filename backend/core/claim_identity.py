"""Conservative semantic identity for empirical claims.

Claim identity is deliberately stricter than semantic similarity. Two statements
may be topically similar without being interchangeable evidence propositions.
This engine provides:

* deterministic canonical fingerprints for exact truth-state identity;
* polarity, relation, quantity and unit preservation;
* lexical similarity only as a review signal;
* no model/embedding authority and no automatic merge from fuzzy similarity.

The design prefers duplicate storage over silently merging materially different
scientific claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable


_NEGATION = {"no", "not", "never", "none", "without", "fails", "failed", "cannot", "can't", "doesn't", "isn't", "aren't"}
_RELATIONS = (
    "causes", "cause", "increases", "increase", "decreases", "decrease",
    "reduces", "reduce", "improves", "improve", "worsens", "worsen",
    "predicts", "predict", "correlates", "correlate", "associated",
    "equals", "equal", "exceeds", "exceed", "contains", "produces", "produce",
    "is", "are", "was", "were",
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
    text = text.casefold().replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"(?<=\d)\s*%", " percent", text)
    text = re.sub(r"[^a-z0-9.%+\-/]+", " ", text)
    return " ".join(text.split())


def _stem(token: str) -> str:
    # Intentionally tiny deterministic morphology; aggressive stemming can merge
    # scientific terms that must remain distinct.
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def fingerprint_claim(claim: str) -> ClaimFingerprint:
    claim = " ".join(str(claim).split()).strip()
    if not claim:
        raise ValueError("claim cannot be blank")
    normalized = _clean(claim)
    raw_tokens = normalized.split()
    polarity = "negative" if any(token in _NEGATION for token in raw_tokens) else "positive"
    relation = next((rel for rel in _RELATIONS if re.search(rf"\b{re.escape(rel)}\b", normalized)), "unspecified")
    quantities = tuple(re.findall(r"(?<![a-z])[-+]?\d+(?:\.\d+)?", normalized))
    units: list[str] = []
    for token in raw_tokens:
        canonical = _UNIT_ALIASES.get(token)
        if canonical and canonical not in units:
            units.append(canonical)
    content = tuple(sorted(dict.fromkeys(
        _stem(token) for token in raw_tokens
        if token not in _STOP and token not in _NEGATION and token not in _UNIT_ALIASES
        and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", token)
    )))
    identity_payload = {
        "polarity": polarity,
        "relation": _stem(relation),
        "quantities": quantities,
        "units": tuple(units),
        "content_tokens": content,
    }
    return ClaimFingerprint(
        claim=claim,
        normalized=normalized,
        polarity=polarity,
        relation=_stem(relation),
        quantities=quantities,
        units=tuple(units),
        content_tokens=content,
        identity_sha256=_sha(identity_payload),
    )


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ClaimIdentityEngine:
    def compare(self, left: str, right: str) -> ClaimMatch:
        a, b = fingerprint_claim(left), fingerprint_claim(right)
        identity_equal = a.identity_sha256 == b.identity_sha256
        reasons: list[str] = []
        if a.polarity != b.polarity:
            reasons.append("polarity_differs")
        if a.relation != b.relation:
            reasons.append("relation_differs")
        if a.quantities != b.quantities:
            reasons.append("quantities_differ")
        if a.units != b.units:
            reasons.append("units_differ")
        lexical = round(_jaccard(a.content_tokens, b.content_tokens), 6)
        structurally_compatible = not reasons
        if identity_equal:
            disposition = "same_identity"
        elif structurally_compatible and lexical >= 0.80:
            disposition = "review_equivalence_candidate"
            reasons.append("high_lexical_similarity_requires_review")
        elif lexical >= 0.60:
            disposition = "related_not_equivalent"
        else:
            disposition = "distinct"
        payload = {
            "left_sha256": a.identity_sha256,
            "right_sha256": b.identity_sha256,
            "identity_equal": identity_equal,
            "structurally_compatible": structurally_compatible,
            "lexical_similarity": lexical,
            "disposition": disposition,
            "reasons": tuple(reasons),
        }
        return ClaimMatch(
            a.identity_sha256, b.identity_sha256, identity_equal, structurally_compatible,
            lexical, disposition, tuple(reasons), _sha(payload),
        )

    @staticmethod
    def canonical_id(claim: str) -> str:
        return fingerprint_claim(claim).identity_sha256

    @staticmethod
    def verify(match: ClaimMatch) -> bool:
        payload = {
            "left_sha256": match.left_sha256,
            "right_sha256": match.right_sha256,
            "identity_equal": match.identity_equal,
            "structurally_compatible": match.structurally_compatible,
            "lexical_similarity": match.lexical_similarity,
            "disposition": match.disposition,
            "reasons": match.reasons,
        }
        return _sha(payload) == match.attestation_sha256
