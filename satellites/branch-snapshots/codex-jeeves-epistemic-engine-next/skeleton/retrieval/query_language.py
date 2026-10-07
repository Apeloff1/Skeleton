"""Query language for retrieval — structured parsing of filter syntax.

Raw strings enter; structured filters exit. Supports negation, quoted
phrases, and field qualification (``tag:x``, ``-bad``, ``\"exact phrase\"``)
like every serious search box.

- :class:`QueryTerm` — text/field/phrase with optional negation
- :class:`QueryParser` — parse() → list of terms
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import List, Optional, Tuple

from skeleton.kernel.errors import RetrievalError


@dataclass(frozen=True)
class QueryTerm:
    raw: str
    field: Optional[str] = None  # e.g. "tag", "site"
    phrase: bool = False
    negated: bool = False


class QueryParser:
    """Lexer over the filter language; tolerant of leftovers."""

    @staticmethod
    def parse(query: str) -> Tuple[QueryTerm, ...]:
        try:
            tokens = shlex.split(query)
        except ValueError:
            raise RetrievalError(
                "unbalanced quotes in query", context={"query": query}
            )
        terms: List[QueryTerm] = []
        for token in tokens:
            negated = token.startswith("-")
            if negated:
                token = token[1:]
            if not token:
                continue
            if ":" in token:
                field_name, _, value = token.partition(":")
                terms.append(
                    QueryTerm(raw=value, field=field_name, negated=negated)
                )
            else:
                phrase = " " in token
                terms.append(
                    QueryTerm(raw=token, phrase=phrase, negated=negated)
                )
        return tuple(terms)

    @staticmethod
    def rebuild(terms: Tuple[QueryTerm, ...]) -> str:
        """Serialise terms back to a canonical string (useful for logging)."""
        parts: List[str] = []
        for term in terms:
            piece = term.raw
            if term.field:
                piece = f"{term.field}:{piece}"
            if term.phrase:
                piece = f'"{piece}"'
            if term.negated:
                piece = f"-{piece}"
            parts.append(piece)
        return " ".join(parts)
