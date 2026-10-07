"""Live teacher mouth binding — real-time lip-sync and viseme binding.

Provides a binding layer that maps audio phoneme streams to mouth
shape targets (visemes) in real time, with smoothing, anticipation,
and blend-shape interpolation for live teacher/agent avatars.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


VISeme_MAP: Dict[str, str] = {
    "AA": "ah", "AE": "ah", "AH": "ah", "AO": "oh", "AW": "oh",
    "AY": "ay", "B": "mb", "CH": "ch", "D": "t", "DH": "th",
    "EH": "eh", "ER": "er", "EY": "ay", "F": "f", "G": "k",
    "HH": "sil", "IH": "ih", "IY": "ee", "JH": "ch", "K": "k",
    "L": "l", "M": "mb", "N": "t", "NG": "k", "OW": "oh",
    "OY": "oh", "P": "mb", "R": "er", "S": "s", "SH": "ch",
    "T": "t", "TH": "th", "UH": "oh", "UW": "oo", "V": "f",
    "W": "oo", "Y": "ee", "Z": "s", "ZH": "ch", "sil": "sil",
}


@dataclass
class MouthTarget:
    viseme: str
    weight: float = 1.0
    blend_shapes: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"viseme": self.viseme, "weight": round(self.weight, 4), "blend_shapes": self.blend_shapes}


class LiveMouthBinding:
    """Real-time mouth shape binding from phoneme stream."""

    def __init__(self, smoothing_window: int = 3, anticipation_ms: float = 60.0):
        self.smoothing_window = smoothing_window
        self.anticipation_ms = anticipation_ms
        self._history: List[Tuple[float, str]] = []
        self._current_viseme = "sil"
        self._current_weight = 0.0
        self._last_update = 0.0

    def feed_phoneme(self, phoneme: str, timestamp_ms: float, confidence: float = 1.0) -> MouthTarget:
        viseme = VISeme_MAP.get(phoneme.upper(), "sil")
        self._history.append((timestamp_ms, viseme))
        # Trim history
        cutoff = timestamp_ms - 200.0
        self._history = [(t, v) for t, v in self._history if t >= cutoff]
        # Smoothing: majority vote in window
        window = [(t, v) for t, v in self._history if t >= timestamp_ms - self.smoothing_window * 40]
        if not window:
            return MouthTarget(viseme="sil", weight=0.0)
        counts: Dict[str, int] = {}
        for _, v in window:
            counts[v] = counts.get(v, 0) + 1
        best = max(counts, key=counts.get)
        weight = min(1.0, counts[best] / len(window)) * confidence
        # Anticipation: if next phoneme is known and different, start blending
        blend = self._compute_blend_shapes(best, weight)
        self._current_viseme = best
        self._current_weight = weight
        self._last_update = timestamp_ms
        return MouthTarget(viseme=best, weight=weight, blend_shapes=blend)

    def _compute_blend_shapes(self, viseme: str, weight: float) -> Dict[str, float]:
        # Standard blend shape mapping
        shapes: Dict[str, float] = {}
        if viseme == "sil":
            shapes["jaw_open"] = 0.0
            shapes["lip_round"] = 0.0
            shapes["lip_wide"] = 0.0
        elif viseme in ("ah", "eh", "ih"):
            shapes["jaw_open"] = 0.6 * weight
            shapes["lip_round"] = 0.0
            shapes["lip_wide"] = 0.3 * weight
        elif viseme in ("ee", "ay"):
            shapes["jaw_open"] = 0.2 * weight
            shapes["lip_round"] = 0.0
            shapes["lip_wide"] = 0.8 * weight
        elif viseme in ("oh", "oo"):
            shapes["jaw_open"] = 0.4 * weight
            shapes["lip_round"] = 0.9 * weight
            shapes["lip_wide"] = 0.0
        elif viseme in ("mb", "f"):
            shapes["jaw_open"] = 0.0
            shapes["lip_round"] = 0.2 * weight
            shapes["lip_wide"] = 0.0
            shapes["lip_pucker"] = 0.8 * weight if viseme == "mb" else 0.0
        elif viseme in ("s", "ch", "th", "t", "k"):
            shapes["jaw_open"] = 0.1 * weight
            shapes["teeth_show"] = 0.5 * weight if viseme in ("s", "th") else 0.0
            shapes["tongue_up"] = 0.6 * weight if viseme in ("t", "th") else 0.0
        else:
            shapes["jaw_open"] = 0.3 * weight
        return shapes

    def current(self) -> MouthTarget:
        return MouthTarget(viseme=self._current_viseme, weight=self._current_weight)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "live-mouth-binding-card",
            "current_viseme": self._current_viseme,
            "current_weight": round(self._current_weight, 4),
            "history_len": len(self._history),
            "smoothing_window": self.smoothing_window,
            "anticipation_ms": self.anticipation_ms,
            "stored_prose": 0,
        }
