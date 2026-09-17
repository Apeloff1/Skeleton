"""Shaft travel. Adjacent free, skip-floor needs coil. Extract unique."""

from __future__ import annotations

from typing import Any


class ShaftError(ValueError):
    pass


def can_travel(state: dict[str, Any], dest: int) -> bool:
    here = int(state.get("floor", 0))
    if dest < 0 or dest > 3 or dest == here:
        return False
    if abs(here - dest) > 1:
        return int(state.get("coil", 0)) >= 1
    return True


def travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    if not can_travel(state, dest):
        raise ShaftError(f"{state.get('floor')}->{dest}")
    nxt = dict(state)
    here = int(nxt.get("floor", 0))
    if here == 3 and int(nxt.get("extracted", 0)) >= 1 and dest != 3:
        raise ShaftError("already extracted")
    nxt["floor"] = int(dest)
    nxt["id"] = f"f{int(dest)}r0"
    if dest == 3:
        nxt["extract_ready"] = 1
    nxt["stored_prose"] = 0
    return nxt
