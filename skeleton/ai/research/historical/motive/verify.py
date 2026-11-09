"""Accept checks for GB-21."""

from __future__ import annotations

from typing import Any

from skeleton.motive.bus import assert_thin_bus
from skeleton.motive.capabilities import capabilities
from skeleton.motive.engine import MotiveEngine
from skeleton.motive.heart import heart
from skeleton.motive.ops import map_s_s_is_s, omega_sigma_iso_id
from skeleton.motive.space import sphere


def check_iso() -> None:
    if not omega_sigma_iso_id(sphere()):
        raise AssertionError("iso")


def check_map_ss() -> None:
    if not map_s_s_is_s():
        raise AssertionError("map-ss")


def check_heart() -> None:
    if heart() != 1:
        raise AssertionError("heart")


def check_bus() -> None:
    assert_thin_bus()


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)


def check_engine() -> None:
    card = MotiveEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_iso, check_map_ss, check_heart, check_bus, check_capabilities, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 6}
