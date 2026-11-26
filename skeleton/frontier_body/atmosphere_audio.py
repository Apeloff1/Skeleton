"""Atmosphere-driven mixer buses and a deterministic PCM preview.

Delay, gain, and low-pass values come from ``sample_atmosphere`` and
``mix_environment_audio``. Occlusion is not the boolean flag on that model.
It is the energy blocked by capsule segments that pass between the source and
the listener. Full occlusion reproduces the existing model's 0.35 gain factor
(``1 - 0.65 * occlusion``). Partial blockers scale that factor linearly.

Buses, in stable order, are ``ambience``, ``weather``, ``occlusion``, and
``ui``. Ambience uses the tide-surf cue, weather uses the rain cue, occlusion
carries the distance-and-fog source, and ui is dry and undelayed.

``parameter_stream`` and ``render_pcm_preview`` share one mix of a frame.
Repeating the same frames yields the same automation rows and the same int16
samples. The preview is synthesized here: no WAVE asset and no audio library.
The preview low-pass is limited to 45% of the preview sample rate so the
one-pole filter is realizable; the automation stream keeps the model's cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions,
    AtmosphereSample,
    AudioEnvironment,
    CelestialCycle,
    EcosystemError,
    mix_environment_audio,
    sample_atmosphere,
    sample_tides,
)
from skeleton.jeeves.game_frontier_production import FrontierProductionError, Vec3


BUS_NAMES = ("ambience", "weather", "occlusion", "ui")
PREVIEW_SAMPLE_RATE = 8000
PREVIEW_SAMPLES_PER_FRAME = 64
PREVIEW_HEADROOM = 0.2
_OCCLUSION_GAIN = 0.65
_CLOSEST = 1e-8


class AudioMixError(ValueError):
    """Rejected atmosphere, blocker, or preview input."""


def _real(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise AudioMixError(f"{label} must be finite")
    if not lo <= float(value) <= hi:
        raise AudioMixError(f"{label} must lie in [{lo}, {hi}]")
    return float(value)


@dataclass(frozen=True)
class BlockerSegment:
    """Finite capsule between two points. ``transmission`` is the energy that passes."""

    start: Vec3
    end: Vec3
    transmission: float = 0.0
    thickness_m: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.start, Vec3) or not isinstance(self.end, Vec3):
            raise AudioMixError("blocker endpoints must be positions")
        object.__setattr__(self, "transmission", _real(self.transmission, "transmission", 0, 1))
        object.__setattr__(self, "thickness_m", _real(self.thickness_m, "thickness_m", 0, 100))


@dataclass(frozen=True)
class AtmosphereAudioFrame:
    game_time_s: float
    air: AirConditions
    source: Vec3
    listener: Vec3
    intensity: float = 1.0
    blockers: tuple[BlockerSegment, ...] = ()
    tide: CelestialCycle | None = None
    ui_gain: float = 0.0

    def __post_init__(self) -> None:
        _real(self.game_time_s, "game_time_s", 0, 1e12)
        if not isinstance(self.air, AirConditions):
            raise AudioMixError("audio frame requires air conditions")
        if not isinstance(self.source, Vec3) or not isinstance(self.listener, Vec3):
            raise AudioMixError("source and listener must be positions")
        _real(self.intensity, "intensity", 0, 100000)
        _real(self.ui_gain, "ui_gain", 0, 4)
        if self.tide is not None and not isinstance(self.tide, CelestialCycle):
            raise AudioMixError("tide must be a celestial cycle")
        if type(self.blockers) is not tuple or any(not isinstance(item, BlockerSegment) for item in self.blockers):
            raise AudioMixError("blockers must be a tuple of segments")
        if len(self.blockers) > 256:
            raise AudioMixError("blocker count exceeds the mix budget")


@dataclass(frozen=True)
class AudioParameterSample:
    game_time_s: float
    bus: str
    delay_s: float
    gain: float
    low_pass_hz: float
    occlusion: float


def _dot(a: Vec3, b: Vec3) -> float:
    return a.dot(b)


def _segment_distance(p0: Vec3, p1: Vec3, q0: Vec3, q1: Vec3) -> float:
    """Shortest distance between two finite segments (Ericson)."""

    u = p1 - p0
    v = q1 - q0
    w = p0 - q0
    a = _dot(u, u)
    b = _dot(u, v)
    c = _dot(v, v)
    d = _dot(u, w)
    e = _dot(v, w)
    if a <= _CLOSEST and c <= _CLOSEST:
        delta = w
        return math.sqrt(_dot(delta, delta))
    if a <= _CLOSEST:
        s_num, s_den = 0.0, 1.0
        t_num, t_den = e, c
    elif c <= _CLOSEST:
        t_num, t_den = 0.0, 1.0
        s_num, s_den = -d, a
    else:
        denom = a * c - b * b
        s_den = denom
        t_den = denom
        if denom < _CLOSEST:
            s_num = 0.0
            s_den = 1.0
            t_num = e
            t_den = c
        else:
            s_num = b * e - c * d
            t_num = a * e - b * d
            if s_num < 0.0:
                s_num = 0.0
                t_num = e
                t_den = c
            elif s_num > s_den:
                s_num = s_den
                t_num = e + b
                t_den = c
    if t_num < 0.0:
        t_num = 0.0
        if -d < 0.0:
            s_num = 0.0
        elif -d > a:
            s_num = s_den
        else:
            s_num = -d
            s_den = a if a > _CLOSEST else 1.0
    elif t_num > t_den:
        t_num = t_den
        if (-d + b) < 0.0:
            s_num = 0.0
        elif (-d + b) > a:
            s_num = s_den
        else:
            s_num = -d + b
            s_den = a if a > _CLOSEST else 1.0
    sc = 0.0 if abs(s_num) <= _CLOSEST else s_num / s_den
    tc = 0.0 if abs(t_num) <= _CLOSEST else t_num / t_den
    delta = w + u.scaled(sc) - v.scaled(tc)
    return math.sqrt(max(0.0, _dot(delta, delta)))


def blocker_occlusion(source: Vec3, listener: Vec3, blockers: tuple[BlockerSegment, ...]) -> float:
    """Return 0 for a clear path and 1 when every hit blocker transmits nothing.

    A blocker hits when the shortest distance between the source-listener
    segment and the blocker segment is within the blocker's thickness.
    Occlusion is ``1 - product(transmission of hits)``. Misses contribute
    nothing. A zero-length listener path is clear.
    """

    if not isinstance(source, Vec3) or not isinstance(listener, Vec3):
        raise AudioMixError("occlusion requires a source and a listener")
    if type(blockers) is not tuple or any(not isinstance(item, BlockerSegment) for item in blockers):
        raise AudioMixError("occlusion blockers must be a tuple of segments")
    span = listener - source
    if span.dot(span) <= _CLOSEST:
        return 0.0
    passed = 1.0
    for blocker in blockers:
        distance = _segment_distance(source, listener, blocker.start, blocker.end)
        if distance <= blocker.thickness_m:
            passed *= blocker.transmission
    return 1.0 - passed


def _distance(source: Vec3, listener: Vec3) -> float:
    delta = listener - source
    return math.sqrt(delta.dot(delta))


def _mix_frame(frame: AtmosphereAudioFrame) -> tuple[AtmosphereSample, float, dict[str, tuple[float, float, float]]]:
    if not isinstance(frame, AtmosphereAudioFrame):
        raise AudioMixError("mix requires an atmosphere audio frame")
    try:
        atmosphere = sample_atmosphere(frame.air)
        distance = _distance(frame.source, frame.listener)
        occlusion = blocker_occlusion(frame.source, frame.listener, frame.blockers)
        tide = sample_tides(frame.tide) if frame.tide is not None else None
        synergy = mix_environment_audio(AudioEnvironment(
            source_distance_m=distance,
            sound_intensity=frame.intensity,
            atmosphere=atmosphere,
            weather_rain_mm_h=frame.air.rain_mm_h,
            occluded=False,
            tide=tide,
        ))
    except (EcosystemError, FrontierProductionError) as exc:
        raise AudioMixError(str(exc)) from exc
    atten = 1.0 - _OCCLUSION_GAIN * occlusion
    buses = {
        "ambience": (synergy.delay_s, synergy.tide_surf_ambience, min(synergy.low_pass_hz, 800.0)),
        "weather": (synergy.delay_s, synergy.rain_ambience, synergy.low_pass_hz),
        "occlusion": (
            synergy.delay_s,
            max(0.0, synergy.gain) * atten,
            synergy.low_pass_hz / (1.0 + 3.0 * occlusion),
        ),
        "ui": (0.0, frame.ui_gain, 20000.0),
    }
    return atmosphere, occlusion, buses


def parameter_stream(frames: Sequence[AtmosphereAudioFrame]) -> tuple[AudioParameterSample, ...]:
    """Deterministic automation rows ordered by game time, then bus name."""

    ordered = _ordered_frames(frames)
    rows: list[AudioParameterSample] = []
    for frame in ordered:
        _atmosphere, occlusion, buses = _mix_frame(frame)
        for bus in BUS_NAMES:
            delay_s, gain, cutoff = buses[bus]
            rows.append(AudioParameterSample(
                frame.game_time_s, bus, delay_s, gain, cutoff, occlusion,
            ))
    return tuple(rows)


def _ordered_frames(frames: Sequence[AtmosphereAudioFrame]) -> tuple[AtmosphereAudioFrame, ...]:
    if isinstance(frames, (str, bytes)) or not isinstance(frames, Sequence) or not frames:
        raise AudioMixError("audio mix requires one or more frames")
    if len(frames) > 256:
        raise AudioMixError("audio frame count exceeds the mix budget")
    if any(not isinstance(frame, AtmosphereAudioFrame) for frame in frames):
        raise AudioMixError("audio frames must be typed atmosphere frames")
    indexed = list(enumerate(frames))
    indexed.sort(key=lambda item: (item[1].game_time_s, item[0]))
    return tuple(frame for _index, frame in indexed)


def _one_pole(sample: float, state: float, cutoff_hz: float, sample_rate: int) -> float:
    limited = min(max(cutoff_hz, 0.0), sample_rate * 0.45)
    if limited <= 0.0:
        return state
    alpha = 1.0 - math.exp(-2.0 * math.pi * limited / sample_rate)
    return state + alpha * (sample - state)


def _raw_sample(bus: str, source_index: int, samples_per_frame: int) -> float:
    if source_index < 0:
        return 0.0
    if bus == "ui":
        return 1.0 if source_index % samples_per_frame == 0 else 0.0
    time_s = source_index / PREVIEW_SAMPLE_RATE
    if bus == "ambience":
        return math.sin(2.0 * math.pi * 90.0 * time_s)
    if bus == "weather":
        return math.sin(2.0 * math.pi * 640.0 * time_s)
    return math.sin(2.0 * math.pi * 440.0 * time_s)


def render_pcm_preview(
    frames: Sequence[AtmosphereAudioFrame],
    *,
    samples_per_frame: int = PREVIEW_SAMPLES_PER_FRAME,
) -> tuple[int, ...]:
    """Int16 mono preview. Identical frames produce identical samples."""

    if type(samples_per_frame) is not int or isinstance(samples_per_frame, bool):
        raise AudioMixError("preview length must be an integer sample count")
    if not 8 <= samples_per_frame <= 512:
        raise AudioMixError("preview length must be 8..512 samples per frame")
    ordered = _ordered_frames(frames)
    mixed = [_mix_frame(frame) for frame in ordered]
    state = {bus: 0.0 for bus in BUS_NAMES}
    output: list[int] = []
    for frame_index, (_atmosphere, _occlusion, buses) in enumerate(mixed):
        for offset in range(samples_per_frame):
            index = frame_index * samples_per_frame + offset
            sample = 0.0
            for bus in BUS_NAMES:
                delay_s, gain, cutoff = buses[bus]
                delay_samples = int(round(delay_s * PREVIEW_SAMPLE_RATE))
                raw = _raw_sample(bus, index - delay_samples, samples_per_frame)
                state[bus] = _one_pole(raw, state[bus], cutoff, PREVIEW_SAMPLE_RATE)
                sample += state[bus] * gain
            sample *= PREVIEW_HEADROOM
            sample = max(-1.0, min(1.0, sample))
            output.append(int(round(sample * 32767.0)))
    return tuple(output)
