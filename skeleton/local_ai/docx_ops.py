"""Create and read Word documents from paragraph text. No model is bound."""

from __future__ import annotations

from skeleton.local_ai.office_pack import OfficeRejected, build_docx, read_docx

__all__ = ["OfficeRejected", "create_doc", "read_paragraphs"]


def create_doc(paragraphs: list[str]) -> bytes:
    return build_docx(paragraphs)


def read_paragraphs(data: bytes) -> list[str]:
    return read_docx(data)
