"""Named extra predicates."""
from __future__ import annotations
from typing import Any

class PredWaveError(ValueError):
    pass

def pred_00(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("heat", 0)) >= 1

def pred_01(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("sleep", 0)) >= 1

def pred_02(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("scrap", 0)) >= 1

def pred_03(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("key", 0)) >= 1

def pred_04(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("coil", 0)) >= 1

def pred_05(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("alert", 0)) >= 1

def pred_06(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("xp", 0)) >= 1

def pred_07(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("floor", 0)) >= 1

def pred_08(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("hp", 0)) >= 1

def pred_09(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("tokens", 0)) >= 1

def pred_10(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("extracted", 0)) >= 1

def pred_11(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("warp_count", 0)) >= 1

def pred_12(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("slept", 0)) >= 1

def pred_13(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("saved", 0)) >= 1

def pred_14(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("parts", 0)) >= 1

def pred_15(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        raise PredWaveError("state")
    return int(state.get("bait", 0)) >= 1
