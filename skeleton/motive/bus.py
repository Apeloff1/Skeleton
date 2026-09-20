"""Thin Spine bus. Does not import skeleton.spine or artifacts.Spine."""

from __future__ import annotations

import sys

from skeleton.motive.cards import motive_card
from skeleton.motive.law import SPINE_BUS


FORBIDDEN = ("skeleton.spine", "artifacts.Spine")


def assert_thin_bus() -> None:
    for name in FORBIDDEN:
        if name in sys.modules:
            raise RuntimeError(name)


def spine_bus_card() -> dict:
    assert_thin_bus()
    return motive_card(
        kind="bus",
        hit=1,
        law="thin Spine bus",
        extra={"bus": SPINE_BUS, "spine_imported": 0},
    )
