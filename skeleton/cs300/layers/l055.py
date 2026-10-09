"""CS300-055 ladder build. stored_prose stays 0."""
from __future__ import annotations

from typing import Any

from skeleton.cs300.contract import run

LAYER_ID = "CS300-055"
KEY = "zero_copy_kernel"
ORDINAL = 55


def build(card: dict[str, Any]) -> dict[str, Any]:
    return run(LAYER_ID, KEY, ORDINAL, card)
