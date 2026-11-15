"""Bounded source and score contracts for GameForge's model-assisted review.

A model review and structural simulation are advisory observations, not native
playability, security or release evidence. A gate may only pass the exact
complete candidate that was observed.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

MAX_ARTIFACT_CHARS = 24_000
MAX_REVIEW_CHARS = 8_192
MAX_ARTIFACT_NODES = 8_192
MAX_ARTIFACT_DEPTH = 24


def _reject_constant(_: str) -> Any:
    raise ValueError("nonfinite JSON value")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def checked_json(text: str, *, maximum: int = MAX_ARTIFACT_CHARS) -> Any:
    """Parse the full bounded document; no substring extraction or NaN."""
    if type(text) is not str or not 0 < len(text) <= maximum:
        raise ValueError("JSON document outside review budget")
    try:
        text.encode("utf-8")
        obj = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid JSON document") from exc
    pending = [(obj, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_ARTIFACT_DEPTH or count > MAX_ARTIFACT_NODES:
            raise ValueError("JSON document exceeds structural budget")
        if type(item) is dict:
            if len(item) > MAX_ARTIFACT_NODES - count - len(pending):
                raise ValueError("JSON document exceeds structural budget")
            for key in item:
                try:
                    key.encode("utf-8")
                except UnicodeError as exc:
                    raise ValueError("invalid JSON key") from exc
            pending.extend((value, depth + 1) for value in item.values())
        elif type(item) is list:
            if len(item) > MAX_ARTIFACT_NODES - count - len(pending):
                raise ValueError("JSON document exceeds structural budget")
            pending.extend((value, depth + 1) for value in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite JSON value")
        elif type(item) is str:
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError("invalid JSON text") from exc
    return obj


def artifact_text(value: Any) -> tuple[str, Any]:
    """Normalize an artifact once without coercing untrusted Python objects."""
    if type(value) is str:
        text = value
    elif type(value) in (dict, list):
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False, sort_keys=True)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("invalid artifact JSON") from exc
    else:
        raise ValueError("artifact must be a JSON object or array")
    parsed = checked_json(text)
    if type(parsed) not in (dict, list) or not parsed:
        raise ValueError("artifact must be a nonempty JSON object or array")
    return text, parsed


def source_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _score(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("review score is not an integer from zero to 100")
    return value


def review_scores(text: str, expected_factors: list[str]) -> tuple[int, dict[str, int], str]:
    obj = checked_json(text, maximum=MAX_REVIEW_CHARS)
    if type(obj) is not dict or set(obj) != {"overall", "factors", "feedback"}:
        raise ValueError("review lacks its exact contract")
    factors = obj["factors"]
    if type(factors) is not dict or set(factors) != set(expected_factors):
        raise ValueError("review does not cover every quality factor")
    feedback = obj["feedback"]
    if type(feedback) is not str or len(feedback) > 2_000:
        raise ValueError("review feedback is invalid")
    return _score(obj["overall"]), {key: _score(factors[key]) for key in expected_factors}, feedback


def compatible_rewrite(original: Any, proposed: Any) -> bool:
    """Reject missing object keys, changed field kinds and removed array entries.

    Existing arrays may gain entries; the existing prefix must keep its shape.
    This is a structural guard, not proof of semantic equivalence.
    """
    pending = [(original, proposed)]
    while pending:
        left, right = pending.pop()
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            if left.keys() != right.keys():
                return False
            pending.extend((left[key], right[key]) for key in left)
        elif type(left) is list:
            if len(right) < len(left):
                return False
            pending.extend(zip(left, right))
    return True
