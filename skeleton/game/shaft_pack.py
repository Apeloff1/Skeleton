"""Named shaft travel. Floor bounds 0..3."""
from __future__ import annotations
from typing import Any

class ShaftPackError(ValueError):
    pass

def shaft_0_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_0"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_1_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_1"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_2_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_2"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_3_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_3"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_4_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_4"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_5_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_5"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_6_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_6"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def shaft_7_travel(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftPackError("floor")
    nxt["shaft"] = "shaft_7"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

TRAVEL = {
    "shaft_0": shaft_0_travel,
    "shaft_1": shaft_1_travel,
    "shaft_2": shaft_2_travel,
    "shaft_3": shaft_3_travel,
    "shaft_4": shaft_4_travel,
    "shaft_5": shaft_5_travel,
    "shaft_6": shaft_6_travel,
    "shaft_7": shaft_7_travel,
}

def travel(name: str, state: dict[str, Any], dest: int) -> dict[str, Any]:
    if name not in TRAVEL:
        raise ShaftPackError(name)
    return TRAVEL[name](state, dest)
