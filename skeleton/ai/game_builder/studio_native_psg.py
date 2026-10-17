"""Original console-local PSG music and game cues, never sampled commercial audio.

A portable 8-note deterministic melody is adapted to the DMG/CGB square
wave registers and 2A03 NES pulse timers. It is related by source theme,
not an impossible claim of PCM waveform identity with browser/Godot audio.
The score is pure bounded authored data; the console compiler owns hardware
register writes and the emulator owns real sound execution qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from .contracts import canonical_digest

SCHEMA = "skeleton.game_builder.original_native_psg.v1"
THEME_ROOT = {
    "forest": 220,
    "ocean": 196,
    "desert": 247,
    "space": 174,
    "arcade": 262,
}
# Original short interval design: major second, tritone and descending minor
# third interleaved with anchor notes; no borrowed theme, samples or MIDI.
_INTERVALS = (0, 2, 6, 9, 7, 4, -2, 0)


class NativePSGError(ValueError):
    """Native square-wave tone data is malformed or exceeds hardware bounds."""


@dataclass(frozen=True, slots=True)
class NativePSGScore:
    theme: str
    seed: int
    density: int
    note_hz: tuple[int, ...]
    event_hz: tuple[int, int, int]
    frames_per_note: int

    def __post_init__(self) -> None:
        if (self.theme not in THEME_ROOT or type(self.seed) is not int
                or not 0 <= self.seed <= 2**63 - 1
                or type(self.density) is not int
                or not 0 <= self.density <= 4
                or type(self.note_hz) is not tuple or len(self.note_hz) != 8
                or type(self.event_hz) is not tuple or len(self.event_hz) != 3
                or type(self.frames_per_note) is not int
                or not 6 <= self.frames_per_note <= 60
                or any(type(hz) is not int or not 90 <= hz <= 1500
                       for hz in (*self.note_hz, *self.event_hz))):
            raise NativePSGError("original PSG arrangement must be finite and hardware safe")

    def to_payload(self) -> dict:
        return {
            "schema": SCHEMA, "theme": self.theme, "seed": self.seed,
            "density": self.density,
            "note_hz": list(self.note_hz),
            "event_hz": list(self.event_hz),
            "frames_per_note": self.frames_per_note,
            "audio_played_on_emulator": False,
            "pcm_soundtrack_bitwise_equal": False,
            "physical_speaker_verified": False,
            "model_weights_updated": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())


def _frequency(root: int, semitones: int) -> int:
    result = root * 2 ** (semitones / 12)
    if not isfinite(result):
        raise NativePSGError("original sound calculation became nonfinite")
    return max(90, min(1500, int(round(result))))


def compose_native_psg(theme: str, seed: int, density: int) -> NativePSGScore:
    if (theme not in THEME_ROOT or type(seed) is not int
            or not 0 <= seed <= 2**63 - 1
            or type(density) is not int or not 0 <= density <= 4):
        raise NativePSGError("typed original theme, seed and volume density required")
    root = THEME_ROOT[theme]
    offset = seed % 5 - 2
    notes = tuple(_frequency(root, interval + offset) for interval in _INTERVALS)
    cues = (
        _frequency(root, 12 + offset),
        _frequency(root, -9 + offset),
        _frequency(root, 7 + offset),
    )
    return NativePSGScore(
        theme=theme, seed=seed, density=density,
        note_hz=notes, event_hz=cues,
        frames_per_note=max(6, 26 - density * 3),
    )


def gb_period(hz: int) -> int:
    if type(hz) is not int or not 90 <= hz <= 1500:
        raise NativePSGError("GB square-wave frequency outside 90..1500Hz")
    timer = int(round(2048 - 131072 / hz))
    if not 0 <= timer <= 2047:
        raise NativePSGError("GB wave timer register outside 11 bits")
    return timer


def nes_period(hz: int) -> int:
    if type(hz) is not int or not 90 <= hz <= 1500:
        raise NativePSGError("NES pulse frequency outside 90..1500Hz")
    timer = int(round(1789773 / (16 * hz) - 1))
    if not 8 <= timer <= 2047:
        raise NativePSGError("NES pulse timer register outside audible bounds")
    return timer


def console_psg_registers(score: NativePSGScore, target: str) -> dict:
    if not isinstance(score, NativePSGScore):
        raise NativePSGError("typed original PSG score required")
    if target in ("nintendo_game_boy", "nintendo_game_boy_color"):
        period = gb_period
    elif target == "nintendo_famicom":
        period = nes_period
    else:
        raise NativePSGError("no authentic PSG adapter for requested console")
    notes = tuple(period(hz) for hz in score.note_hz)
    events = tuple(period(hz) for hz in score.event_hz)
    return {
        "target": target,
        "note_periods": notes,
        "event_periods": events,
        "notes_low": tuple(number & 255 for number in notes),
        "notes_high": tuple(number >> 8 for number in notes),
        "events_low": tuple(number & 255 for number in events),
        "events_high": tuple(number >> 8 for number in events),
        "frames_per_note": score.frames_per_note,
        "enabled": score.density > 0,
        "score_digest": score.digest,
    }


__all__ = [
    "NativePSGScore", "NativePSGError", "compose_native_psg",
    "console_psg_registers", "gb_period", "nes_period",
]
