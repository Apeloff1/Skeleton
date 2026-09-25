"""Result rendering — human-friendly output for fused/ranked lists.

CLI demos shouldn't each format. The renderer emits numbered text
lines or basic HTML segments with score/plane/preview tags.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

from skeleton.retrieval.fusion import ScoredResult


def _preview(item: ScoredResult) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    raw = metadata.get("preview") or metadata.get("text") or item.content or ""
    if not isinstance(raw, str):
        raw = str(raw)
    return raw[:80] + "..." if len(raw) > 80 else raw


def _label(item: ScoredResult) -> str:
    return item.plane or item.provenance or "result"


class ResultRenderer:
    """Render ScoredResult tuples for terminal or HTML embedding."""

    @staticmethod
    def to_text(items: Sequence[ScoredResult]) -> str:
        lines: list[str] = []
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"[{idx}] {item.fragment_id} «{_label(item)}» score={item.score} {_preview(item)}"
            )
        return "\n".join(lines)

    @staticmethod
    def to_html(items: Sequence[ScoredResult]) -> str:
        parts = ['<ol class="retrieval-results">']
        for item in items:
            parts.append(
                f'<li data-score="{item.score:.4f}" data-source="{escape(_label(item), quote=True)}">'
                f"{escape(item.fragment_id)}"
                "</li>"
            )
        parts.append("</ol>")
        return "".join(parts)
