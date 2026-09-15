"""Gates — one door per family. Anyone can connect. Missing keys stand in.

A gate is a named socket: probe, bind, ping. Ping never raises. Bind
returns a ModelPort (Kimi, HuggingFace, Echo, or modality). The catalog
is the directory. Jeeves acquires through the door, not around it.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from skeleton.cortex.catalog import FAMILIES, by_id, catalog
from skeleton.cortex.interchange import HuggingFaceBackend, KimiBackend, probe_interchange
from skeleton.cortex.multimodal import open_modality
from skeleton.cortex.port import EchoBackend


def probe_gate(family: Dict[str, Any]) -> Dict[str, Any]:
    env = str(family.get("env") or "")
    keyed = bool(env) and bool(os.environ.get(env))
    kind = str(family.get("gate") or "local")
    live = False
    if kind == "local":
        live = True
    elif kind == "kimi":
        live = bool(os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY"))
    elif kind == "huggingface":
        live = bool(probe_interchange().get("huggingface"))
    else:
        live = keyed
    return {
        "id": family.get("id"),
        "house": family.get("house"),
        "gate": kind,
        "keyed": keyed,
        "live": live,
        "modalities": list(family.get("modalities") or ()),
        "models": list(family.get("models") or ()),
    }


def probe_all() -> List[Dict[str, Any]]:
    return [probe_gate(dict(f)) for f in FAMILIES]


def bind_gate(neo, fid: str, *, slot: str = "left", model: str | None = None, modality: str = "text") -> Dict[str, Any]:
    family = by_id(fid)
    kind = str(family.get("gate") or "local")
    mid = model or (family.get("models") or ("local",))[0]
    if modality and modality != "text":
        port = open_modality(modality, slot=slot)
        neo.bind(slot, port)
        return {"bound": 1, "slot": slot, "kind": "modality", "modality": modality, "family": family["id"]}
    if kind == "kimi":
        out = neo.bind_kimi(slot, str(mid))
        out["family"] = family["id"]
        return out
    if kind == "huggingface":
        out = neo.bind_hf(slot, str(mid))
        out["family"] = family["id"]
        return out
    if kind == "local":
        neo.bind_local(slot)
        return {"bound": 1, "slot": slot, "kind": "local", "family": family["id"]}
    neo.bind(slot, EchoBackend(slot=slot, name=str(family.get("id") or "gate")))
    return {"bound": 1, "slot": slot, "kind": "echo-standin", "family": family["id"], "model": mid}


def ping(fid: str) -> Dict[str, Any]:
    try:
        return {"ok": 1, **probe_gate(by_id(fid))}
    except Exception as exc:
        return {"ok": 0, "error": type(exc).__name__, "id": fid}
