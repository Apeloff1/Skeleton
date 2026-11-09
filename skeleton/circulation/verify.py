"""Accept checks for GB-24."""

from __future__ import annotations

from typing import Any

from skeleton.circulation.capabilities import capabilities
from skeleton.circulation.engine import CirculationEngine
from skeleton.circulation.heat import bleed, shunt_fever


def check_hot_drop() -> None:
    card = shunt_fever(1.2)
    if card["dropped"] != 1:
        raise AssertionError("hot")


def check_cool() -> None:
    card = shunt_fever(1.2, cool=True)
    if card["dropped"] != 0 or card["heat_out"] != 0.0:
        raise AssertionError("cool")


def check_bleed_below() -> None:
    card = shunt_fever(0.5)
    if card["dropped"] != 0:
        raise AssertionError("keep")
    if bleed(0.5) >= 0.90:
        raise AssertionError("bleed")


def check_capabilities() -> None:
    cap = capabilities()
    if cap["contract"]["cool_drops"] != 0:
        raise AssertionError("cap")


def check_engine() -> None:
    card = CirculationEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_hot_drop, check_cool, check_bleed_below, check_capabilities, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 5}
