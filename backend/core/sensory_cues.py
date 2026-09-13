"""Device-neutral sensory cue model mined from Hyperforge audio semantics.

Rather than coupling runtime state to WebAudio, this module emits normalized cues
that web/native renderers can map to sound, haptics, VFX, or accessibility output.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class CueKind(StrEnum):
    AMBIENCE = "ambience"
    RING = "ring"
    CRASH = "crash"
    FINISH = "finish"
    UI = "ui"


@dataclass(frozen=True, slots=True)
class SensoryCue:
    kind: CueKind
    intensity: float
    pitch: float = 0.0
    layer: str = "sfx"
    metadata: tuple[tuple[str, float], ...] = ()


def ambience(speed: float, lift: float) -> SensoryCue:
    amount = _clamp((speed - 12.0) / 80.0)
    thermal = 1.0 if lift > 2.0 else 0.0
    return SensoryCue(
        CueKind.AMBIENCE,
        intensity=0.04 + amount * 0.42,
        pitch=280.0 + amount * 1400.0,
        layer="ambience",
        metadata=(("thermal", thermal), ("speed_norm", amount)),
    )


def ring(combo: int) -> SensoryCue:
    safe_combo = max(0, min(int(combo), 8))
    return SensoryCue(CueKind.RING, intensity=0.16, pitch=440.0 + safe_combo * 48.0)


def crash(severity: float = 1.0) -> SensoryCue:
    return SensoryCue(CueKind.CRASH, intensity=_clamp(severity), pitch=70.0)


def finish() -> tuple[SensoryCue, ...]:
    return (
        SensoryCue(CueKind.FINISH, 0.18, 392.0),
        SensoryCue(CueKind.FINISH, 0.16, 494.0),
        SensoryCue(CueKind.FINISH, 0.20, 587.0),
    )


def ui() -> SensoryCue:
    return SensoryCue(CueKind.UI, 0.08, 620.0)
