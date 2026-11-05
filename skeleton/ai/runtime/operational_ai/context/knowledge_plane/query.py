"""Bounded FTS5 queries. Never execute user-supplied FTS syntax directly."""
from __future__ import annotations
import re
from .contracts import KnowledgeError, KnowledgePolicy

_TERM = re.compile(r'[^\W_]{2,48}', re.UNICODE)


def terms(question: str, policy: KnowledgePolicy) -> tuple[str, ...]:
    if (type(question) is not str or not question.strip() or
        len(question) > policy.max_query_chars or any(ord(c) < 32 and c not in '\n\t' for c in question)):
        raise KnowledgeError('invalid bounded knowledge query')
    unique = []
    for match in _TERM.finditer(question.casefold()):
        value = match.group()
        if value not in unique:
            unique.append(value)
        if len(unique) >= policy.max_query_terms: break
    return tuple(unique)


def fts_expression(question: str, policy: KnowledgePolicy) -> str:
    words = terms(question, policy)
    # Each term is individually quoted, preventing FTS operators, NEAR,
    # wildcards, unclosed quotes and boolean query expansion from user text.
    return ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)
