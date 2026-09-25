"""Retrieval dedupe — collapse near-identical candidates before ranking.

MMR-style simplification: if two results share an item/fragment id or the
same source signature, keep the higher score and discard the weaker.

- :class:`Deduper` — exact + prefix-match elimination
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult


class Deduper:
    """Eliminate duplicate ids and same-signature candidates."""

    def __init__(self, *, signature_length: int = 48) -> None:
        if isinstance(signature_length, bool) or not isinstance(signature_length, int) or signature_length < 1:
            raise ValueError("signature_length must be a positive integer")
        self._sig_len = signature_length

    def dedupe(self, items: Sequence[ScoredResult]) -> Tuple[ScoredResult, ...]:
        seen_ids: set[str] = set()
        seen_sigs: set[str] = set()
        out: list[ScoredResult] = []
        ordered = sorted(
            (_require_scored(item) for item in items),
            key=lambda item: (-item.score, _identity(item)),
        )
        for item in ordered:
            identity = _identity(item)
            if not identity:
                raise ValueError("result id is required")
            if identity in seen_ids:
                continue
            signature = _signature(item, self._sig_len)
            if signature and signature in seen_sigs:
                continue
            if identity:
                seen_ids.add(identity)
            if signature:
                seen_sigs.add(signature)
            out.append(item)
        return tuple(out)


def _require_scored(item: ScoredResult) -> ScoredResult:
    if not hasattr(item, "score"):
        raise ValueError("result score is required")
    value = item.score
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("result score must be finite")
    return item


def _identity(item: ScoredResult) -> str:
    for attr in ("item_id", "fragment_id"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _signature(item: ScoredResult, sig_len: int) -> str:
    metadata = getattr(item, "metadata", None)
    text = ""
    if isinstance(metadata, dict):
        raw = metadata.get("text") or metadata.get("preview") or ""
        if isinstance(raw, str):
            text = raw
    if not text:
        content = getattr(item, "content", "")
        if isinstance(content, str):
            text = content
    if text.strip():
        return text.strip()[:sig_len]
    source = getattr(item, "source", None) or getattr(item, "provenance", "") or ""
    identity = _identity(item)
    if not source and not identity:
        return ""
    return f"{source}:{identity}"
