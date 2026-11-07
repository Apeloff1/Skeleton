"""Explicit MIME dispatch for inert software package lock metadata."""
from __future__ import annotations

from .npm_lock_documents import NPM_LOCK_TYPES, extract_npm_lock
from .cargo_lock_documents import CARGO_LOCK_TYPES, extract_cargo_lock
from .go_mod_documents import GO_MOD_TYPES, extract_go_mod
from .pylock_documents import PYLOCK_TYPES, extract_pylock
from .research_projection import ResearchFormatError, ResearchProjection

PACKAGE_LOCK_TYPES=frozenset().union(
    NPM_LOCK_TYPES, CARGO_LOCK_TYPES, GO_MOD_TYPES, PYLOCK_TYPES,
)

def extract_package_lock(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    for types,parser in (
        (NPM_LOCK_TYPES,extract_npm_lock),
        (CARGO_LOCK_TYPES,extract_cargo_lock),
        (GO_MOD_TYPES,extract_go_mod),
        (PYLOCK_TYPES,extract_pylock),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported package-lock source type")
