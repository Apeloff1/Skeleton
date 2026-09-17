"""More shafts."""
from __future__ import annotations
from typing import Any

class ShaftWaveError(ValueError):
    pass

def sh_00_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_00"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_01_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_01"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_02_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_02"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_03_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_03"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_04_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_04"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_05_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_05"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_06_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_06"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_07_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_07"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_08_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_08"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_09_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_09"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_10_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_10"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt

def sh_11_go(state: dict[str, Any], dest: int) -> dict[str, Any]:
    nxt = dict(state)
    if dest < 0 or dest > 3:
        raise ShaftWaveError("floor")
    nxt["shaft"] = "sh_11"
    nxt["floor"] = int(dest)
    nxt["stored_prose"] = 0
    return nxt
