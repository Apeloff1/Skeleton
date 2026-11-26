"""Read and create PDF files. Text is stored with PDF literal strings and Tj.

No model is bound.
"""

from __future__ import annotations

from skeleton.local_ai.office_pack import MAX_PAGES, OfficeRejected, build_pdf, read_pdf

__all__ = ["OfficeRejected", "generate", "read_text"]


def generate(pages: int) -> bytes:
    """Return a real PDF with pages labeled ``Page 1`` through ``Page N``."""
    if isinstance(pages, bool) or not isinstance(pages, int):
        raise OfficeRejected("pages must be an int")
    if pages < 1 or pages > MAX_PAGES:
        raise OfficeRejected(f"pages must be from 1 to {MAX_PAGES}")
    labels = [f"Page {index}" for index in range(1, pages + 1)]
    return build_pdf(labels)


def read_text(data: bytes) -> list[str]:
    """Return one string for each ``(...) Tj`` text operator, in order."""
    return read_pdf(data)
