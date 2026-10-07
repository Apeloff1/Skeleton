"""Retrieval dedupe — collapse near-identical candidates before ranking.

MMR-style simplification: if two results share an item_id or the same
source signature, keep the higher score and discard the weaker. Fuses
against Fuser and Ranker.compose().

- :class:`Deduper` — exact + prefix-match elimination
"""

from __future__ import annotations

from typing import Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult


class Deduper:
    """Eliminate duplicate item_ids and same-signature candidates."""

    def __init__(self, *, signature_length: int = 48) -> None:
        self._sig_len = signature_length

    def dedupe(self, items: Sequence[ScoredResult]) -> Tuple[ScoredResult, ...]:
        seen_ids: set = set()
        seen_sigs: set = set()
        out: list = []
        for item in sorted(items, key=lambda s: -s.score):
            if item.item_id in seen_ids:
                continue
            sig = self._signature(item)
            if sig in seen_sigs:
                continue
            seen_ids.add(item.item_id)
            seen_sigs.add(sig)
            out.append(item)
        return tuple(out)

    def _signature(self, item: ScoredResult) -> str:
        text = item.metadata.get("text", "") or item.metadata.get("preview", "")
        if text:
            return text[: self._sig_len]
        return f"{item.source}:{item.item_id}"
