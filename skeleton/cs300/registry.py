"""Dispatch a CS-300 layer to its stratum module."""
from __future__ import annotations

import importlib
from typing import Any


def admit(layer_id: str, card: dict[str, Any]) -> dict[str, Any]:
    ordinal = int(layer_id.rsplit("-", 1)[1])
    stratum = (ordinal - 1) // 10 + 1
    if stratum == 1:
        module = importlib.import_module("skeleton.cs300.strata.s01")
    elif stratum == 2:
        module = importlib.import_module("skeleton.cs300.strata.s02")
    elif stratum == 3:
        module = importlib.import_module("skeleton.cs300.strata.s03")
    elif stratum == 4:
        module = importlib.import_module("skeleton.cs300.strata.s04")
    elif stratum == 5:
        module = importlib.import_module("skeleton.cs300.strata.s05")
    elif stratum == 6:
        module = importlib.import_module("skeleton.cs300.strata.s06")
    elif stratum == 7:
        module = importlib.import_module("skeleton.cs300.strata.s07")
    elif stratum == 8:
        module = importlib.import_module("skeleton.cs300.strata.s08")
    elif stratum == 9:
        module = importlib.import_module("skeleton.cs300.strata.s09")
    elif stratum == 10:
        module = importlib.import_module("skeleton.cs300.strata.s10")
    elif stratum == 11:
        module = importlib.import_module("skeleton.cs300.strata.s11")
    elif stratum == 12:
        module = importlib.import_module("skeleton.cs300.strata.s12")
    elif stratum == 13:
        module = importlib.import_module("skeleton.cs300.strata.s13")
    elif stratum == 14:
        module = importlib.import_module("skeleton.cs300.strata.s14")
    elif stratum == 15:
        module = importlib.import_module("skeleton.cs300.strata.s15")
    elif stratum == 16:
        module = importlib.import_module("skeleton.cs300.strata.s16")
    elif stratum == 17:
        module = importlib.import_module("skeleton.cs300.strata.s17")
    elif stratum == 18:
        module = importlib.import_module("skeleton.cs300.strata.s18")
    elif stratum == 19:
        module = importlib.import_module("skeleton.cs300.strata.s19")
    elif stratum == 20:
        module = importlib.import_module("skeleton.cs300.strata.s20")
    elif stratum == 21:
        module = importlib.import_module("skeleton.cs300.strata.s21")
    elif stratum == 22:
        module = importlib.import_module("skeleton.cs300.strata.s22")
    elif stratum == 23:
        module = importlib.import_module("skeleton.cs300.strata.s23")
    elif stratum == 24:
        module = importlib.import_module("skeleton.cs300.strata.s24")
    elif stratum == 25:
        module = importlib.import_module("skeleton.cs300.strata.s25")
    elif stratum == 26:
        module = importlib.import_module("skeleton.cs300.strata.s26")
    elif stratum == 27:
        module = importlib.import_module("skeleton.cs300.strata.s27")
    elif stratum == 28:
        module = importlib.import_module("skeleton.cs300.strata.s28")
    elif stratum == 29:
        module = importlib.import_module("skeleton.cs300.strata.s29")
    elif stratum == 30:
        module = importlib.import_module("skeleton.cs300.strata.s30")
    else:
        raise ValueError("unregistered CS-300 stratum")
    return module.admit(layer_id, card)
