"""Dispatch a CS-300 layer to its stratum module."""
from __future__ import annotations

import importlib
from typing import Any


def _load_stratum(stratum: int):
    """Only the thirty tracked CS300 strata may be executed."""
    if stratum == 1:
        return importlib.import_module("skeleton.cs300.strata.s01")
    if stratum == 2:
        return importlib.import_module("skeleton.cs300.strata.s02")
    if stratum == 3:
        return importlib.import_module("skeleton.cs300.strata.s03")
    if stratum == 4:
        return importlib.import_module("skeleton.cs300.strata.s04")
    if stratum == 5:
        return importlib.import_module("skeleton.cs300.strata.s05")
    if stratum == 6:
        return importlib.import_module("skeleton.cs300.strata.s06")
    if stratum == 7:
        return importlib.import_module("skeleton.cs300.strata.s07")
    if stratum == 8:
        return importlib.import_module("skeleton.cs300.strata.s08")
    if stratum == 9:
        return importlib.import_module("skeleton.cs300.strata.s09")
    if stratum == 10:
        return importlib.import_module("skeleton.cs300.strata.s10")
    if stratum == 11:
        return importlib.import_module("skeleton.cs300.strata.s11")
    if stratum == 12:
        return importlib.import_module("skeleton.cs300.strata.s12")
    if stratum == 13:
        return importlib.import_module("skeleton.cs300.strata.s13")
    if stratum == 14:
        return importlib.import_module("skeleton.cs300.strata.s14")
    if stratum == 15:
        return importlib.import_module("skeleton.cs300.strata.s15")
    if stratum == 16:
        return importlib.import_module("skeleton.cs300.strata.s16")
    if stratum == 17:
        return importlib.import_module("skeleton.cs300.strata.s17")
    if stratum == 18:
        return importlib.import_module("skeleton.cs300.strata.s18")
    if stratum == 19:
        return importlib.import_module("skeleton.cs300.strata.s19")
    if stratum == 20:
        return importlib.import_module("skeleton.cs300.strata.s20")
    if stratum == 21:
        return importlib.import_module("skeleton.cs300.strata.s21")
    if stratum == 22:
        return importlib.import_module("skeleton.cs300.strata.s22")
    if stratum == 23:
        return importlib.import_module("skeleton.cs300.strata.s23")
    if stratum == 24:
        return importlib.import_module("skeleton.cs300.strata.s24")
    if stratum == 25:
        return importlib.import_module("skeleton.cs300.strata.s25")
    if stratum == 26:
        return importlib.import_module("skeleton.cs300.strata.s26")
    if stratum == 27:
        return importlib.import_module("skeleton.cs300.strata.s27")
    if stratum == 28:
        return importlib.import_module("skeleton.cs300.strata.s28")
    if stratum == 29:
        return importlib.import_module("skeleton.cs300.strata.s29")
    if stratum == 30:
        return importlib.import_module("skeleton.cs300.strata.s30")
    raise ValueError("unregistered CS300 stratum")


def admit(layer_id: str, card: dict[str, Any]) -> dict[str, Any]:
    ordinal = int(layer_id.rsplit("-", 1)[1])
    stratum = (ordinal - 1) // 10 + 1
    module = _load_stratum(stratum)
    return module.admit(layer_id, card)
