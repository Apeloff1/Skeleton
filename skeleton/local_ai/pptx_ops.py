"""Create and read slide decks from slide text. No model is bound."""

from __future__ import annotations

from skeleton.local_ai.office_pack import OfficeRejected, build_pptx, read_pptx

__all__ = ["OfficeRejected", "create_deck", "read_slides"]


def create_deck(slides: list[str]) -> bytes:
    return build_pptx(slides)


def read_slides(data: bytes) -> list[str]:
    return read_pptx(data)
