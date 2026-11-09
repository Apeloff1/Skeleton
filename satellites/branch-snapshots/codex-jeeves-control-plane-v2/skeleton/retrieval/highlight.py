"""Highlighting — mark matched query terms in chunk text for display.

Search results read better with matched spans marked. The highlighter
wraps positive (non-negated) query terms in configurable delimiters,
using the QueryTerm tuples the parser produces.
"""

from __future__ import annotations

import re
from typing import Tuple

from skeleton.retrieval.query_language import QueryTerm


class Highlighter:
    """Wrap positive query terms in open/close delimiters."""

    def __init__(self, *, open_tag: str = "<mark>", close_tag: str = "</mark>") -> None:
        self._open = open_tag
        self._close = close_tag

    def highlight(self, text: str, terms: Tuple[QueryTerm, ...]) -> str:
        positive = [t for t in terms if not t.negated and t.raw]
        if not positive:
            return text
        patterns = [re.escape(t.raw) for t in positive]
        regex = re.compile("(" + "|".join(patterns) + ")", re.IGNORECASE)
        return regex.sub(
            lambda m: f"{self._open}{m.group(0)}{self._close}", text
        )
