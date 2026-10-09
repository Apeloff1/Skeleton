"""CS300-128 ladder build. stored_prose stays 0."""
from __future__ import annotations

from typing import Any

from skeleton.cs300.contract import run

LAYER_ID = "CS300-128"
KEY = "semantic_compression_research"
ORDINAL = 128


def build(card: dict[str, Any]) -> dict[str, Any]:
    return run(LAYER_ID, KEY, ORDINAL, card)
