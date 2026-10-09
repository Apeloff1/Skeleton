"""CS300-245 ladder build. stored_prose stays 0."""
from __future__ import annotations

from typing import Any

from skeleton.cs300.contract import run

LAYER_ID = "CS300-245"
KEY = "model_predictive_control"
ORDINAL = 245


def build(card: dict[str, Any]) -> dict[str, Any]:
    return run(LAYER_ID, KEY, ORDINAL, card)
