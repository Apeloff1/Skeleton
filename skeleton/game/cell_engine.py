"""Sixteen floor cells in one engine. Kind-specific ticks. Extract once."""

from __future__ import annotations

import hashlib
from typing import Any


class CellEngineError(ValueError):
    pass


def _spec(index: int) -> dict[str, Any]:
    if index < 0 or index > 15:
        raise CellEngineError("index")
    floor, ri = divmod(index, 4)
    if floor == 0 and ri == 0:
        kind = "spawn"
    elif floor == 3 and ri == 3:
        kind = "extract"
    elif ri == 3:
        kind = "stair"
    else:
        kind = ("scavenge", "heat", "forge", "sleep", "dream", "lock")[index % 6]
    return {
        "index": index,
        "floor": floor,
        "ri": ri,
        "id": f"f{floor}r{ri}",
        "kind": kind,
        "tiles": 6 + (index % 4),
        "locked": kind == "lock",
    }


def _roll(seed: int, cell_id: str, label: str) -> int:
    material = f"{int(seed)}:{cell_id}:{label}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def blank(index: int, seed: int) -> dict[str, Any]:
    spec = _spec(index)
    return {
        "id": spec["id"],
        "kind": spec["kind"],
        "floor": spec["floor"],
        "index": index,
        "heat": _roll(seed, spec["id"], "h") % 8,
        "scrap": index % 3,
        "locked": spec["locked"],
        "extracted": 0,
        "occupancy": [0] * spec["tiles"],
        "stored_prose": 0,
    }


def tick(state: dict[str, Any], verb: str, *, seed: int, t: int) -> dict[str, Any]:
    nxt = dict(state)
    kind = str(nxt.get("kind") or "")
    heat = int(nxt.get("heat", 0))
    scrap = int(nxt.get("scrap", 0))
    name = str(verb or "").strip().lower()
    cell_id = str(nxt.get("id") or "f0r0")
    if kind == "spawn":
        if name == "heat":
            heat = min(16, heat + 2)
        elif name == "wait":
            heat = max(0, heat - 1)
        elif name == "extract":
            raise CellEngineError("not extract")
        else:
            heat = min(16, heat + (_roll(seed, cell_id, f"t{t}") % 2))
    elif kind == "extract":
        if name == "extract":
            if heat < 8:
                raise CellEngineError("heat")
            if int(nxt.get("extracted", 0)) >= 1:
                raise CellEngineError("once")
            nxt["extracted"] = 1
            heat = max(0, heat - 8)
        elif name == "heat":
            heat = min(16, heat + 3)
    elif kind == "lock":
        if name == "unlock":
            nxt["locked"] = False
            nxt["key"] = 1
        elif nxt.get("locked", True) and name not in {"wait"}:
            raise CellEngineError("locked")
        elif name == "heat":
            heat = min(16, heat + 1)
    elif kind == "stair":
        if name == "climb":
            nxt["floor"] = min(3, int(nxt.get("floor", 0)) + 1)
        elif name == "drop":
            nxt["floor"] = max(0, int(nxt.get("floor", 0)) - 1)
        elif name == "heat":
            heat = min(16, heat + 1)
    elif kind == "dream":
        if name == "dream":
            nxt["dreams"] = int(nxt.get("dreams", 0)) + 1
            heat = (heat + (seed % 3)) % 16
        elif name == "wake" and int(nxt.get("dreams", 0)) < 1:
            raise CellEngineError("wake")
        elif name == "heat":
            heat = min(16, heat + 1)
    elif kind == "sleep":
        if name == "sleep":
            nxt["slept"] = int(nxt.get("slept", 0)) + 1
            heat = max(0, heat - 4)
        elif name == "dream":
            if int(nxt.get("slept", 0)) < 1:
                raise CellEngineError("dream")
            nxt["dreams"] = int(nxt.get("dreams", 0)) + 1
        elif name == "heat":
            heat = min(16, heat + 1)
    elif kind == "forge":
        if name == "craft":
            if scrap < 1:
                raise CellEngineError("scrap")
            scrap -= 1
            nxt["parts"] = int(nxt.get("parts", 0)) + 1
            heat = min(16, heat + 2)
        elif name == "scavenge":
            scrap += 1
        elif name == "heat":
            heat = min(16, heat + 2)
    else:
        if name == "scavenge":
            scrap += 1
            heat = min(16, heat + 1)
        elif name == "heat":
            heat = min(16, heat + 2)
        elif name == "wait":
            heat = max(0, heat - 1)
    nxt["heat"] = heat
    nxt["scrap"] = scrap
    nxt["verb"] = name
    nxt["t"] = t
    nxt["stored_prose"] = 0
    return nxt


def inspect(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": state.get("id"),
        "kind": state.get("kind"),
        "floor": int(state.get("floor", 0)),
        "heat": int(state.get("heat", 0)),
        "extracted": int(state.get("extracted", 0)),
        "stored_prose": 0,
    }


def run_cell(index: int, seed: int, verbs: list[str]) -> dict[str, Any]:
    state = blank(index, seed)
    frames = [inspect(state)]
    for t, verb in enumerate(verbs):
        try:
            state = tick(state, verb, seed=seed, t=t)
        except CellEngineError:
            pass
        frames.append(inspect(state))
    return {"kind": "cell_run", "id": state.get("id"), "n": len(frames), "final": inspect(state), "stored_prose": 0}


def census() -> dict[str, Any]:
    rows = [_spec(i) for i in range(16)]
    return {"kind": "cell_census", "n": len(rows), "cells": rows, "stored_prose": 0}


def tour(seed: int) -> dict[str, Any]:
    frames = []
    extracted = 0
    for index in range(16):
        spec = _spec(index)
        verbs = ["heat", "wait"]
        if spec["kind"] == "scavenge":
            verbs = ["scavenge", "heat"]
        elif spec["kind"] == "extract":
            verbs = ["heat", "heat", "extract"]
        elif spec["kind"] == "lock":
            verbs = ["unlock", "enter"]
        elif spec["kind"] == "dream":
            verbs = ["dream", "wake"]
        elif spec["kind"] == "sleep":
            verbs = ["sleep", "dream"]
        elif spec["kind"] == "forge":
            verbs = ["scavenge", "craft"]
        elif spec["kind"] == "stair":
            verbs = ["climb", "heat"]
        run = run_cell(index, seed, verbs)
        extracted = int(run["final"].get("extracted", 0))
        frames.append(run["final"])
    return {
        "kind": "cell_tour",
        "seed": int(seed),
        "n": len(frames),
        "frames": frames,
        "extracted": extracted,
        "sota_ready": False,
        "stored_prose": 0,
    }
