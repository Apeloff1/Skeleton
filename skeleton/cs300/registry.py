"""Dispatch a CS-300 layer to its stratum module."""
from __future__ import annotations

import importlib
from typing import Any


def admit(layer_id: str, card: dict[str, Any]) -> dict[str, Any]:
    ordinal = int(layer_id.rsplit("-", 1)[1])
    stratum = (ordinal - 1) // 10 + 1
    module = importlib.import_module(f"skeleton.cs300.strata.s{stratum:02d}")
    return module.admit(layer_id, card)
