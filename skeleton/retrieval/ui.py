"""Result rendering — human-friendly output for fused/ranked lists.

CLI demos shouldn't each format. The renderer emits numbered text
lines or basic HTML segments with score/source/preview tags.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult


class ResultRenderer:
    """Render ScoredResult tuples for terminal or HTML embedding."""

    @staticmethod
    def to_text(items: Sequence[ScoredResult]) -> str:
        lines: list = []
        for idx, item in enumerate(items, start=1):
            preview = item.metadata.get("preview", "")
            preview = preview[:80] + "..." if len(preview) > 80 else preview
            lines.append(
                f"[{idx}] {item.item_id} «{item.source}» score={item.score} {preview}"
            )
        return "\n".join(lines)

    @staticmethod
    def to_html(items: Sequence[ScoredResult]) -> str:
        parts = ["<ol class=\"retrieval-results\">"]
        for item in items:
            parts.append(
                f'<li data-score="{item.score:.4f}" data-source="{item.source}">'
                f"{item.item_id}"
                "</li>"
            )
        parts.append("</ol>")
        return "".join(parts)
