"""Process-local memory book. No model is bound."""

from __future__ import annotations

import tempfile
from pathlib import Path

from skeleton.local_ai.memory_book import MemoryBook

_book: MemoryBook | None = None
_directory: Path | None = None


def book() -> MemoryBook:
    """Return the process-local book, creating it on first use."""
    global _book, _directory
    if _book is None:
        _directory = Path(tempfile.mkdtemp(prefix="skeleton-memory-book-"))
        _book = MemoryBook(_directory / "memory.md")
    return _book


def store(fact: str) -> None:
    book().remember(fact)
