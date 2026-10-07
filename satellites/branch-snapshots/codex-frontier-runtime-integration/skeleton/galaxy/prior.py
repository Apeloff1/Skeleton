"""Decoder prior device card — CPU canonical, GPU if the mouth is there.

Does not download weights. If neo.transformer reports cuda/mps, the
prior blend tilts 0.10 toward the mouth hidden energy. Otherwise the
existing Jaccard decoder is the whole path.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from skeleton.galaxy.atoms import Atom
from skeleton.galaxy.decoder import KnowledgeDecoder


def _device_of(neo) -> str:
    xf = getattr(neo, "transformer", None) if neo is not None else None
    if xf is None:
        return "cpu"
    return str(getattr(xf, "device", "cpu") or "cpu")


def _hidden_energy(neo, query: str) -> float:
    if neo is None:
        return 0.0
    fn = getattr(neo, "_hidden", None)
    if not callable(fn):
        xf = getattr(neo, "transformer", None)
        fn = getattr(xf, "hidden", None) if xf is not None else None
    if not callable(fn):
        return 0.0
    try:
        vec = list(fn(query) or [])
    except Exception:
        return 0.0
    if not vec:
        return 0.0
    return sum(abs(float(x)) for x in vec[:16]) / max(1, min(16, len(vec)))


def blend(query: str, bank: Iterable[Atom], *, neo: Any = None, decoder: Optional[KnowledgeDecoder] = None) -> Dict[str, Any]:
    dec = decoder or KnowledgeDecoder()
    device = _device_of(neo)
    card = dec.decode(query, bank)
    energy = _hidden_energy(neo, query)
    gpu = device not in {"cpu", "", "None"}
    if gpu and energy > 0:
        card["blend"] = round(min(0.55, float(card.get("blend") or 0.35) + 0.10), 4)
        card["prior"] = "gpu-hidden"
    else:
        card["prior"] = "cpu-jaccard"
    card["device"] = device
    card["hidden_energy"] = round(energy, 6)
    card["stored_prose"] = 0
    return card
