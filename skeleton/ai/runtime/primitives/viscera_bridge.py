"""Thin viscera_card. Must not import skeleton.viscera or artifacts.Viscera."""

from __future__ import annotations

import sys
from typing import Any

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.errors import VisceraImportError
from skeleton.primitives.law import CITATION


FORBIDDEN_MODULES = (
    "skeleton.viscera",
    "artifacts.Viscera",
    "Viscera",
)


def assert_no_viscera_import() -> None:
    for name in FORBIDDEN_MODULES:
        if name in sys.modules:
            raise VisceraImportError(name)


def viscera_card(*, G: float, law: str, cite: str = CITATION, root: str) -> dict[str, Any]:
    assert_no_viscera_import()
    return primitive_card(
        kind="witness",
        hit=1 if root else 0,
        law=law,
        citation=cite,
        extra={"G": G, "root": root, "bridge": "viscera_card"},
    )
