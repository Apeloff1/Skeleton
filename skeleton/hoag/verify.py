"""Accept checks for GB-26."""

from __future__ import annotations

from typing import Any

from skeleton.hoag.capabilities import capabilities
from skeleton.hoag.engine import HoagEngine
from skeleton.hoag.law import REGION_N
from skeleton.hoag.plane import Warp, bind_mouth_body, plane_ok, region_cards


def check_regions() -> None:
    if not plane_ok() or len(region_cards()) != REGION_N:
        raise AssertionError("regions")


def check_warp_once() -> None:
    w = Warp()
    a = w.extract("x")
    b = w.extract("y")
    if a["skipped"] != 0 or b["skipped"] != 1:
        raise AssertionError("warp")


def check_bind() -> None:
    if bind_mouth_body("m", "b")["bound"] != 1:
        raise AssertionError("bind")


def check_no_pwa() -> None:
    if capabilities()["contract"]["organism_pwa"] != 0:
        raise AssertionError("pwa")


def check_engine() -> None:
    card = HoagEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_regions, check_warp_once, check_bind, check_no_pwa, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 5}
