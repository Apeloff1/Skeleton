"""Deterministic historical audio systems for Jeeves game projects.

Existing repository music APIs generate composition specifications and the
HyperForge browser demo owns a WebAudio graph. This module does neither. It is
the bounded, deterministic game-runtime audio authority used by historical
engine sandboxes.

The capability ladder grows from one-voice mono beeps through PSG/chiptune,
PCM stereo, distance/pan mixing, surround buses, streamed open-world audio,
and modern object-spatial control. The mixer produces deterministic control
frames and voice state rather than host audio-device side effects.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import RoutedEngineSandbox


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _finite(
    value: float,
    name: str,
) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            f"{name} must be finite"
        )
    return result


def _clamp(
    value: float,
    low: float,
    high: float,
) -> float:
    return min(
        high,
        max(
            low,
            value,
        ),
    )


class Waveform(str, Enum):
    SQUARE = "square"
    TRIANGLE = "triangle"
    NOISE = "noise"
    WAVETABLE = "wavetable"
    PCM = "pcm"
    STREAM = "stream"


class SpatialMode(str, Enum):
    MONO = "mono"
    PAN = "pan"
    DISTANCE = "distance_pan"
    SURROUND = "surround"
    OBJECT = "object_spatial"


@dataclass(frozen=True, slots=True)
class AudioPosition:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        _finite(
            self.x,
            "audio x",
        )
        _finite(
            self.y,
            "audio y",
        )
        _finite(
            self.z,
            "audio z",
        )

    def distance_to(
        self,
        other: "AudioPosition",
    ) -> float:
        return math.sqrt(
            (
                self.x
                - other.x
            ) ** 2
            + (
                self.y
                - other.y
            ) ** 2
            + (
                self.z
                - other.z
            ) ** 2
        )


@dataclass(frozen=True, slots=True)
class AudioEraPolicy:
    era: EngineEra
    max_voices: int
    sample_rate: int
    output_channels: int
    bit_depth: int
    waveforms: tuple[Waveform, ...]
    spatial_mode: SpatialMode
    streaming: bool
    dsp_effects: tuple[str, ...]
    max_buses: int
    max_events_per_tick: int
    max_distance: float
    voice_stealing: bool

    def __post_init__(self) -> None:
        for value in (
            self.max_voices,
            self.sample_rate,
            self.output_channels,
            self.bit_depth,
            self.max_buses,
            self.max_events_per_tick,
        ):
            if value < 1:
                raise GameEngineLabError(
                    "audio policy positive bounds required"
                )
        if not self.waveforms:
            raise GameEngineLabError(
                "audio policy requires waveforms"
            )
        if self.max_distance <= 0:
            raise GameEngineLabError(
                "audio max distance must be positive"
            )


def _policy(
    era: EngineEra,
    voices: int,
    sample_rate: int,
    channels: int,
    bit_depth: int,
    waveforms: tuple[Waveform, ...],
    spatial: SpatialMode,
    streaming: bool,
    effects: tuple[str, ...],
    buses: int,
    events: int,
    distance: float,
    stealing: bool,
) -> AudioEraPolicy:
    return AudioEraPolicy(
        era,
        voices,
        sample_rate,
        channels,
        bit_depth,
        waveforms,
        spatial,
        streaming,
        effects,
        buses,
        events,
        distance,
        stealing,
    )


AUDIO_POLICIES: Mapping[
    EngineEra,
    AudioEraPolicy,
] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        1,
        8_000,
        1,
        1,
        (Waveform.SQUARE,),
        SpatialMode.MONO,
        False,
        (),
        1,
        2,
        1.0,
        False,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        4,
        11_025,
        1,
        4,
        (
            Waveform.SQUARE,
            Waveform.NOISE,
        ),
        SpatialMode.MONO,
        False,
        (),
        1,
        8,
        1.0,
        True,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        5,
        22_050,
        1,
        4,
        (
            Waveform.SQUARE,
            Waveform.TRIANGLE,
            Waveform.NOISE,
            Waveform.PCM,
        ),
        SpatialMode.MONO,
        False,
        ("envelope",),
        2,
        12,
        1.0,
        True,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        8,
        32_000,
        2,
        8,
        (
            Waveform.WAVETABLE,
            Waveform.PCM,
            Waveform.NOISE,
        ),
        SpatialMode.PAN,
        False,
        (
            "envelope",
            "echo",
        ),
        4,
        24,
        1.0,
        True,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        24,
        32_000,
        2,
        16,
        (
            Waveform.WAVETABLE,
            Waveform.PCM,
            Waveform.NOISE,
        ),
        SpatialMode.PAN,
        True,
        (
            "reverb_send",
            "lowpass",
        ),
        8,
        48,
        100.0,
        True,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        32,
        44_100,
        2,
        16,
        (
            Waveform.PCM,
            Waveform.STREAM,
            Waveform.WAVETABLE,
        ),
        SpatialMode.DISTANCE,
        True,
        (
            "reverb",
            "lowpass",
            "highpass",
        ),
        12,
        64,
        150.0,
        True,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        48,
        48_000,
        2,
        16,
        (
            Waveform.PCM,
            Waveform.STREAM,
            Waveform.WAVETABLE,
        ),
        SpatialMode.DISTANCE,
        True,
        (
            "reverb",
            "delay",
            "eq",
            "compressor",
        ),
        16,
        96,
        200.0,
        True,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        64,
        48_000,
        6,
        24,
        (
            Waveform.PCM,
            Waveform.STREAM,
            Waveform.WAVETABLE,
        ),
        SpatialMode.SURROUND,
        True,
        (
            "reverb",
            "delay",
            "eq",
            "compressor",
            "limiter",
            "occlusion_lowpass",
        ),
        24,
        128,
        250.0,
        True,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        128,
        48_000,
        6,
        24,
        (
            Waveform.PCM,
            Waveform.STREAM,
            Waveform.WAVETABLE,
        ),
        SpatialMode.SURROUND,
        True,
        (
            "reverb",
            "delay",
            "eq",
            "compressor",
            "limiter",
            "occlusion_lowpass",
            "zone_send",
        ),
        32,
        256,
        500.0,
        True,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        256,
        96_000,
        8,
        24,
        (
            Waveform.PCM,
            Waveform.STREAM,
            Waveform.WAVETABLE,
        ),
        SpatialMode.OBJECT,
        True,
        (
            "reverb",
            "convolution",
            "delay",
            "eq",
            "compressor",
            "limiter",
            "occlusion",
            "doppler",
        ),
        64,
        512,
        1_000.0,
        True,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        512,
        192_000,
        8,
        32,
        tuple(Waveform),
        SpatialMode.OBJECT,
        True,
        (
            "reverb",
            "convolution",
            "delay",
            "eq",
            "compressor",
            "limiter",
            "occlusion",
            "doppler",
            "path_reflection",
            "adaptive_mix",
        ),
        128,
        1_024,
        2_000.0,
        True,
    ),
}


def audio_policy(
    era: EngineEra | str,
) -> AudioEraPolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return AUDIO_POLICIES[key]


@dataclass(frozen=True, slots=True)
class SoundRecipe:
    sound_id: str
    waveform: Waveform
    frequency_hz: float
    gain: float
    duration_ticks: int
    priority: int = 0
    looping: bool = False
    pan: float = 0.0
    position: AudioPosition = AudioPosition()

    def __post_init__(self) -> None:
        if (
            not self.sound_id
            or len(self.sound_id) > 64
            or not all(
                char.isalnum()
                or char in "_.-"
                for char in self.sound_id
            )
        ):
            raise GameEngineLabError(
                "sound id must be bounded and path-safe"
            )
        if not isinstance(
            self.waveform,
            Waveform,
        ):
            object.__setattr__(
                self,
                "waveform",
                Waveform(
                    str(self.waveform)
                ),
            )
        frequency = _finite(
            self.frequency_hz,
            "frequency",
        )
        if not 0 <= frequency <= 48_000:
            raise GameEngineLabError(
                "sound frequency outside [0, 48000]"
            )
        gain = _finite(
            self.gain,
            "gain",
        )
        if not 0 <= gain <= 4:
            raise GameEngineLabError(
                "sound gain outside [0, 4]"
            )
        if (
            type(self.duration_ticks)
            is not int
            or not 1
            <= self.duration_ticks
            <= 100_000
        ):
            raise GameEngineLabError(
                "sound duration ticks outside [1, 100000]"
            )
        if (
            type(self.priority)
            is not int
            or not -128
            <= self.priority
            <= 127
        ):
            raise GameEngineLabError(
                "sound priority outside signed byte range"
            )
        pan = _finite(
            self.pan,
            "pan",
        )
        if not -1 <= pan <= 1:
            raise GameEngineLabError(
                "sound pan outside [-1, 1]"
            )


@dataclass(frozen=True, slots=True)
class AudioSceneSource:
    listener: AudioPosition
    sounds: tuple[SoundRecipe, ...]

    def __post_init__(self) -> None:
        if not self.sounds:
            raise GameEngineLabError(
                "audio scene requires sounds"
            )


def validate_audio_source(
    era: EngineEra | str,
    source: AudioSceneSource,
) -> None:
    policy = audio_policy(
        era
    )
    ids = [
        sound.sound_id
        for sound in source.sounds
    ]
    if len(ids) != len(set(ids)):
        raise GameEngineLabError(
            "sound ids must be unique"
        )
    if (
        len(source.sounds)
        > policy.max_events_per_tick
    ):
        raise GameEngineLabError(
            "audio source count exceeds era event budget"
        )
    for sound in source.sounds:
        if (
            sound.waveform
            not in policy.waveforms
        ):
            raise GameEngineLabError(
                f"{sound.waveform.value} unavailable in {policy.era.value}"
            )
        if (
            policy.spatial_mode
            is SpatialMode.MONO
            and abs(sound.pan) > 1e-12
        ):
            raise GameEngineLabError(
                "pan unavailable in mono era"
            )
        if (
            sound.waveform
            is Waveform.STREAM
            and not policy.streaming
        ):
            raise GameEngineLabError(
                "streaming audio unavailable in this era"
            )


@dataclass(slots=True)
class ActiveVoice:
    sound_id: str
    waveform: Waveform
    frequency_hz: float
    gain: float
    remaining_ticks: int
    duration_ticks: int
    priority: int
    looping: bool
    pan: float
    position: AudioPosition
    started_tick: int

    def state(
        self,
    ) -> tuple[object, ...]:
        return (
            self.waveform.value,
            self.frequency_hz,
            self.gain,
            self.remaining_ticks,
            self.duration_ticks,
            self.priority,
            self.looping,
            self.pan,
            self.position.x,
            self.position.y,
            self.position.z,
            self.started_tick,
        )


@dataclass(frozen=True, slots=True)
class AudioFrame:
    era: EngineEra
    tick: int
    channels: tuple[float, ...]
    active_voices: tuple[str, ...]
    started: tuple[str, ...]
    stolen: tuple[str, ...]
    rejected: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    era: EngineEra
    tick: int
    listener: AudioPosition
    voices: tuple[
        tuple[str, tuple[object, ...]],
        ...,
    ]
    digest: str


class HistoricalAudioMixer:
    """Deterministic control-rate mixer with bounded voice allocation."""

    def __init__(
        self,
        era: EngineEra | str,
        *,
        listener: AudioPosition = AudioPosition(),
    ) -> None:
        self.policy = audio_policy(
            era
        )
        self.listener = listener
        self.tick = 0
        self._voices: dict[
            str,
            ActiveVoice,
        ] = {}

    @property
    def voices(
        self,
    ) -> tuple[
        ActiveVoice,
        ...,
    ]:
        return tuple(
            self._voices[key]
            for key in sorted(
                self._voices
            )
        )

    def move_listener(
        self,
        position: AudioPosition,
    ) -> None:
        self.listener = position

    def _victim(
        self,
    ) -> ActiveVoice | None:
        if not self._voices:
            return None
        return min(
            self._voices.values(),
            key=lambda voice: (
                voice.priority,
                voice.started_tick,
                voice.sound_id,
            ),
        )

    def trigger(
        self,
        recipe: SoundRecipe,
    ) -> tuple[
        bool,
        str | None,
    ]:
        if (
            recipe.waveform
            not in self.policy.waveforms
        ):
            raise GameEngineLabError(
                "sound waveform unavailable in mixer era"
            )
        if recipe.sound_id in self._voices:
            del self._voices[
                recipe.sound_id
            ]
        stolen: str | None = None
        if (
            len(self._voices)
            >= self.policy.max_voices
        ):
            if not self.policy.voice_stealing:
                return (
                    False,
                    None,
                )
            victim = self._victim()
            if victim is None:
                return (
                    False,
                    None,
                )
            if (
                recipe.priority
                < victim.priority
            ):
                return (
                    False,
                    None,
                )
            stolen = (
                victim.sound_id
            )
            del self._voices[
                victim.sound_id
            ]
        self._voices[
            recipe.sound_id
        ] = ActiveVoice(
            recipe.sound_id,
            recipe.waveform,
            recipe.frequency_hz,
            recipe.gain,
            recipe.duration_ticks,
            recipe.duration_ticks,
            recipe.priority,
            recipe.looping,
            recipe.pan,
            recipe.position,
            self.tick,
        )
        return (
            True,
            stolen,
        )

    def _distance_gain(
        self,
        voice: ActiveVoice,
    ) -> float:
        if self.policy.spatial_mode in {
            SpatialMode.MONO,
            SpatialMode.PAN,
        }:
            return 1.0
        distance = (
            voice.position.distance_to(
                self.listener
            )
        )
        normalized = _clamp(
            distance
            / self.policy.max_distance,
            0.0,
            1.0,
        )
        return (
            1.0
            / (
                1.0
                + 3.0
                * normalized
                * normalized
            )
        )

    def _pan(
        self,
        voice: ActiveVoice,
    ) -> float:
        if (
            self.policy.spatial_mode
            is SpatialMode.MONO
        ):
            return 0.0
        if (
            self.policy.spatial_mode
            is SpatialMode.PAN
        ):
            return voice.pan
        relative_x = (
            voice.position.x
            - self.listener.x
        )
        divisor = max(
            1.0,
            self.policy.max_distance
            * 0.25,
        )
        return _clamp(
            voice.pan
            + relative_x
            / divisor,
            -1.0,
            1.0,
        )

    def _voice_channels(
        self,
        voice: ActiveVoice,
    ) -> tuple[float, ...]:
        gain = (
            voice.gain
            * self._distance_gain(
                voice
            )
        )
        channels = (
            self.policy.output_channels
        )
        if channels == 1:
            return (
                round(
                    gain,
                    12,
                ),
            )

        pan = self._pan(
            voice
        )
        left = (
            gain
            * (1.0 - pan)
            * 0.5
        )
        right = (
            gain
            * (1.0 + pan)
            * 0.5
        )
        if channels == 2:
            return (
                round(left, 12),
                round(right, 12),
            )

        relative_z = (
            voice.position.z
            - self.listener.z
        )
        rear = _clamp(
            (
                -relative_z
                / max(
                    1.0,
                    self.policy.max_distance
                    * 0.25,
                )
                + 1.0
            )
            * 0.5,
            0.0,
            1.0,
        )
        front = (
            1.0 - rear
        )
        center = (
            gain
            * front
            * (
                1.0
                - abs(pan)
            )
            * 0.5
        )
        lfe = (
            gain * 0.1
        )
        surround_left = (
            left * rear
        )
        surround_right = (
            right * rear
        )
        values = [
            left * front,
            right * front,
            center,
            lfe,
            surround_left,
            surround_right,
        ]
        while len(values) < channels:
            object_index = (
                len(values) - 6
            )
            if object_index == 0:
                values.append(
                    gain
                    * (
                        0.5
                        + 0.5
                        * pan
                    )
                )
            else:
                values.append(
                    gain
                    * (
                        0.5
                        - 0.5
                        * pan
                    )
                )
        return tuple(
            round(
                value,
                12,
            )
            for value
            in values[:channels]
        )

    def mix_tick(
        self,
        events: Iterable[
            SoundRecipe
        ] = (),
    ) -> AudioFrame:
        event_values = tuple(
            events
        )
        if (
            len(event_values)
            > self.policy.max_events_per_tick
        ):
            raise GameEngineLabError(
                "audio event budget exceeded"
            )
        started: list[str] = []
        stolen: list[str] = []
        rejected: list[str] = []
        for recipe in sorted(
            event_values,
            key=lambda value: (
                -value.priority,
                value.sound_id,
            ),
        ):
            accepted, victim = (
                self.trigger(
                    recipe
                )
            )
            if accepted:
                started.append(
                    recipe.sound_id
                )
                if victim is not None:
                    stolen.append(
                        victim
                    )
            else:
                rejected.append(
                    recipe.sound_id
                )

        mixed = [
            0.0
            for _ in range(
                self.policy.output_channels
            )
        ]
        for voice in self.voices:
            channel_values = (
                self._voice_channels(
                    voice
                )
            )
            for index, value in enumerate(
                channel_values
            ):
                mixed[index] += value
        channels = tuple(
            round(
                _clamp(
                    value,
                    -1.0,
                    1.0,
                ),
                12,
            )
            for value
            in mixed
        )
        active = tuple(
            voice.sound_id
            for voice in self.voices
        )
        payload = {
            "era": self.policy.era.value,
            "tick": self.tick,
            "channels": channels,
            "active": active,
            "started": started,
            "stolen": stolen,
            "rejected": rejected,
        }
        frame = AudioFrame(
            self.policy.era,
            self.tick,
            channels,
            active,
            tuple(started),
            tuple(stolen),
            tuple(rejected),
            _digest(payload),
        )

        expired: list[str] = []
        for voice in self.voices:
            voice.remaining_ticks -= 1
            if (
                voice.remaining_ticks
                <= 0
            ):
                if voice.looping:
                    voice.remaining_ticks = (
                        voice.duration_ticks
                    )
                else:
                    expired.append(
                        voice.sound_id
                    )
        for sound_id in expired:
            self._voices.pop(
                sound_id,
                None,
            )
        self.tick += 1
        return frame

    def run(
        self,
        schedule: Mapping[
            int,
            tuple[SoundRecipe, ...],
        ],
        ticks: int,
    ) -> tuple[
        AudioFrame,
        ...,
    ]:
        if (
            type(ticks) is not int
            or not 0 <= ticks <= 100_000
        ):
            raise GameEngineLabError(
                "audio tick count outside [0, 100000]"
            )
        frames: list[
            AudioFrame
        ] = []
        for _ in range(ticks):
            frames.append(
                self.mix_tick(
                    schedule.get(
                        self.tick,
                        (),
                    )
                )
            )
        return tuple(frames)

    def snapshot(self) -> AudioSnapshot:
        voices = tuple(
            (
                voice.sound_id,
                voice.state(),
            )
            for voice
            in self.voices
        )
        payload = {
            "era": self.policy.era.value,
            "tick": self.tick,
            "listener": (
                self.listener.x,
                self.listener.y,
                self.listener.z,
            ),
            "voices": voices,
        }
        return AudioSnapshot(
            self.policy.era,
            self.tick,
            self.listener,
            voices,
            _digest(payload),
        )

    def restore(
        self,
        snapshot: AudioSnapshot,
    ) -> None:
        if (
            snapshot.era
            is not self.policy.era
        ):
            raise GameEngineLabError(
                "audio snapshot era mismatch"
            )
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "listener": (
                snapshot.listener.x,
                snapshot.listener.y,
                snapshot.listener.z,
            ),
            "voices":
                snapshot.voices,
        }
        if (
            _digest(payload)
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "audio snapshot digest mismatch"
            )
        restored: dict[
            str,
            ActiveVoice,
        ] = {}
        for sound_id, state in (
            snapshot.voices
        ):
            restored[sound_id] = (
                ActiveVoice(
                    sound_id,
                    Waveform(
                        str(state[0])
                    ),
                    float(state[1]),
                    float(state[2]),
                    int(state[3]),
                    int(state[4]),
                    int(state[5]),
                    bool(state[6]),
                    float(state[7]),
                    AudioPosition(
                        float(state[8]),
                        float(state[9]),
                        float(state[10]),
                    ),
                    int(state[11]),
                )
            )
        if (
            len(restored)
            > self.policy.max_voices
        ):
            raise GameEngineLabError(
                "audio snapshot exceeds voice budget"
            )
        self.tick = (
            snapshot.tick
        )
        self.listener = (
            snapshot.listener
        )
        self._voices = restored

    def fingerprint(self) -> str:
        return self.snapshot().digest


def _sound_document(
    sound: SoundRecipe,
) -> dict[str, object]:
    return {
        "sound_id": sound.sound_id,
        "waveform":
            sound.waveform.value,
        "frequency_hz":
            sound.frequency_hz,
        "gain": sound.gain,
        "duration_ticks":
            sound.duration_ticks,
        "priority":
            sound.priority,
        "looping":
            sound.looping,
        "pan": sound.pan,
        "position": [
            sound.position.x,
            sound.position.y,
            sound.position.z,
        ],
    }


def _source_document(
    source: AudioSceneSource,
) -> dict[str, object]:
    return {
        "listener": [
            source.listener.x,
            source.listener.y,
            source.listener.z,
        ],
        "sounds": [
            _sound_document(
                sound
            )
            for sound in source.sounds
        ],
    }


def _policy_document(
    policy: AudioEraPolicy,
) -> dict[str, object]:
    return {
        "engine_era":
            policy.era.value,
        "max_voices":
            policy.max_voices,
        "sample_rate":
            policy.sample_rate,
        "output_channels":
            policy.output_channels,
        "bit_depth":
            policy.bit_depth,
        "waveforms": [
            waveform.value
            for waveform
            in policy.waveforms
        ],
        "spatial_mode":
            policy.spatial_mode.value,
        "streaming":
            policy.streaming,
        "dsp_effects":
            list(
                policy.dsp_effects
            ),
        "max_buses":
            policy.max_buses,
        "max_events_per_tick":
            policy.max_events_per_tick,
        "max_distance":
            policy.max_distance,
        "voice_stealing":
            policy.voice_stealing,
    }


@dataclass(frozen=True, slots=True)
class AudioBuild:
    era: EngineEra
    source_digest: str
    policy_digest: str
    manifest_digest: str
    source_document: dict[
        str,
        object,
    ]

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era":
                self.era.value,
            "source_digest":
                self.source_digest,
            "policy_digest":
                self.policy_digest,
            "manifest_digest":
                self.manifest_digest,
            "host_audio_side_effects":
                False,
        }


def compile_audio_build(
    era: EngineEra | str,
    source: AudioSceneSource,
) -> AudioBuild:
    policy = audio_policy(
        era
    )
    validate_audio_source(
        policy.era,
        source,
    )
    source_doc = (
        _source_document(
            source
        )
    )
    policy_doc = (
        _policy_document(
            policy
        )
    )
    source_digest = _digest(
        source_doc
    )
    policy_digest = _digest(
        policy_doc
    )
    identity = {
        "schema_version": 1,
        "engine_era":
            policy.era.value,
        "source_digest":
            source_digest,
        "policy_digest":
            policy_digest,
    }
    return AudioBuild(
        policy.era,
        source_digest,
        policy_digest,
        _digest(identity),
        source_doc,
    )


def audio_build_patches(
    build: AudioBuild,
) -> tuple[SandboxPatch, ...]:
    return (
        SandboxPatch(
            "audio/compiled/manifest.json",
            json.dumps(
                build.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "audio/compiled/policy.json",
            json.dumps(
                _policy_document(
                    audio_policy(
                        build.era
                    )
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "audio/compiled/scene.json",
            json.dumps(
                build.source_document,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
    )


def attach_audio_build(
    sandbox: RoutedEngineSandbox,
    source: AudioSceneSource,
) -> RoutedEngineSandbox:
    build = compile_audio_build(
        sandbox.era,
        source,
    )
    patches = tuple(
        SandboxPatch(
            patch.path,
            patch.content,
            sandbox.tree.file_digest(
                patch.path
            ),
        )
        for patch
        in audio_build_patches(
            build
        )
    )
    return sandbox.apply(
        patches
    )


def canonical_audio_patches(
    sandbox: RoutedEngineSandbox,
    source: AudioSceneSource,
) -> tuple[SandboxPatch, ...]:
    build = compile_audio_build(
        sandbox.era,
        source,
    )
    expected = {
        patch.path: patch.content
        for patch
        in audio_build_patches(
            build
        )
    }
    existing = {
        path
        for path in sandbox.tree.files
        if path.startswith(
            "audio/compiled/"
        )
    }
    patches: list[
        SandboxPatch
    ] = []
    for path in sorted(
        set(expected)
        | existing
    ):
        wanted = expected.get(
            path
        )
        try:
            current = sandbox.tree.read(
                path
            )
        except GameEngineLabError:
            current = None
        if current == wanted:
            continue
        patches.append(
            SandboxPatch(
                path,
                wanted,
                sandbox.tree.file_digest(
                    path
                ),
            )
        )
    return tuple(patches)


@dataclass(frozen=True, slots=True)
class AudioProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AudioQualityReport:
    era: EngineEra
    probes: tuple[
        AudioProbe,
        ...,
    ]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(
            probe.passed
            for probe in self.probes
        )

    @property
    def score(self) -> float:
        return sum(
            probe.passed
            for probe in self.probes
        ) / max(
            1,
            len(self.probes),
        )

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class AudioAdversary:
    """Attest compiled audio and deterministic voice/mix behavior."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        source: AudioSceneSource,
    ) -> AudioQualityReport:
        try:
            expected = compile_audio_build(
                sandbox.era,
                source,
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "audio/compiled/manifest.json"
                )
            )
            policy_doc = json.loads(
                sandbox.tree.read(
                    "audio/compiled/policy.json"
                )
            )
            scene_doc = json.loads(
                sandbox.tree.read(
                    "audio/compiled/scene.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            detail = str(exc)
            return AudioQualityReport(
                sandbox.era,
                tuple(
                    AudioProbe(
                        name,
                        False,
                        detail,
                    )
                    for name in (
                        "manifest",
                        "inventory",
                        "integrity",
                        "replay",
                        "snapshot",
                        "voice_budget",
                        "spatial",
                    )
                ),
            )

        expected_paths = {
            patch.path
            for patch
            in audio_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path in sandbox.tree.files
            if path.startswith(
                "audio/compiled/"
            )
        }
        manifest_ok = (
            manifest
            == expected.manifest()
        )
        inventory_ok = (
            expected_paths
            == actual_paths
        )
        integrity_ok = (
            policy_doc
            == _policy_document(
                audio_policy(
                    sandbox.era
                )
            )
            and scene_doc
            == expected.source_document
        )

        def replay():
            mixer = HistoricalAudioMixer(
                sandbox.era,
                listener=source.listener,
            )
            schedule = {
                index * 3: (
                    sound,
                )
                for index, sound
                in enumerate(
                    source.sounds
                )
            }
            frames = mixer.run(
                schedule,
                64,
            )
            return (
                frames,
                mixer.fingerprint(),
            )

        replay_ok = (
            replay()
            == replay()
        )

        snap_mixer = HistoricalAudioMixer(
            sandbox.era,
            listener=source.listener,
        )
        first_sound = (
            source.sounds[0]
        )
        snap_mixer.mix_tick(
            (first_sound,)
        )
        snapshot = (
            snap_mixer.snapshot()
        )
        before = (
            snap_mixer.fingerprint()
        )
        snap_mixer.run(
            {},
            5,
        )
        snap_mixer.restore(
            snapshot
        )
        snapshot_ok = (
            snap_mixer.fingerprint()
            == before
        )

        policy = audio_policy(
            sandbox.era
        )
        stress = HistoricalAudioMixer(
            sandbox.era,
            listener=source.listener,
        )
        stress_events = tuple(
            SoundRecipe(
                f"stress_{index}",
                policy.waveforms[0],
                220.0
                + index,
                0.1,
                10,
                priority=min(
                    index,
                    127,
                ),
                position=
                    source.listener,
            )
            for index in range(
                min(
                    policy.max_events_per_tick,
                    policy.max_voices + 4,
                )
            )
        )
        stress.mix_tick(
            stress_events
        )
        voice_budget_ok = (
            len(stress.voices)
            <= policy.max_voices
        )

        spatial_mixer = (
            HistoricalAudioMixer(
                sandbox.era,
                listener=AudioPosition(),
            )
        )
        spatial_sound = (
            SoundRecipe(
                "spatial_probe",
                policy.waveforms[0],
                440.0,
                0.5,
                4,
                pan=(
                    0.0
                    if policy.spatial_mode
                    is SpatialMode.MONO
                    else 0.6
                ),
                position=AudioPosition(
                    25.0,
                    0.0,
                    -10.0,
                ),
            )
        )
        spatial_frame = (
            spatial_mixer.mix_tick(
                (spatial_sound,)
            )
        )
        if (
            policy.spatial_mode
            is SpatialMode.MONO
        ):
            spatial_ok = (
                len(
                    spatial_frame.channels
                )
                == 1
            )
        else:
            spatial_ok = (
                len(
                    spatial_frame.channels
                )
                == policy.output_channels
                and len(
                    set(
                        spatial_frame.channels
                    )
                )
                > 1
            )

        return AudioQualityReport(
            sandbox.era,
            (
                AudioProbe(
                    "manifest",
                    manifest_ok,
                    "canonical audio manifest",
                ),
                AudioProbe(
                    "inventory",
                    inventory_ok,
                    "exact compiled audio inventory",
                ),
                AudioProbe(
                    "integrity",
                    integrity_ok,
                    "audio policy and scene attested",
                ),
                AudioProbe(
                    "replay",
                    replay_ok,
                    "deterministic audio control replay",
                ),
                AudioProbe(
                    "snapshot",
                    snapshot_ok,
                    "voice state snapshot roundtrip",
                ),
                AudioProbe(
                    "voice_budget",
                    voice_budget_ok,
                    "bounded deterministic voice allocation",
                ),
                AudioProbe(
                    "spatial",
                    spatial_ok,
                    policy.spatial_mode.value,
                ),
            ),
        )


def canonical_audio_source(
    era: EngineEra | str,
) -> AudioSceneSource:
    policy = audio_policy(
        era
    )
    primary = (
        Waveform.SQUARE
        if Waveform.SQUARE
        in policy.waveforms
        else policy.waveforms[0]
    )
    secondary = (
        Waveform.NOISE
        if Waveform.NOISE
        in policy.waveforms
        else primary
    )
    spatial = (
        policy.spatial_mode
        is not SpatialMode.MONO
    )
    values = [
        SoundRecipe(
            "ui_confirm",
            primary,
            440.0,
            0.35,
            6,
            priority=4,
            pan=(
                -0.25
                if spatial
                else 0.0
            ),
            position=AudioPosition(
                -10.0,
                0.0,
                5.0,
            ),
        ),
    ]
    if (
        policy.max_events_per_tick
        >= 2
    ):
        values.append(
            SoundRecipe(
                "impact",
                secondary,
                110.0,
                0.5,
                10,
                priority=8,
                pan=(
                    0.35
                    if spatial
                    else 0.0
                ),
                position=AudioPosition(
                    20.0,
                    0.0,
                    -15.0,
                ),
            )
        )
    if (
        policy.streaming
        and Waveform.STREAM
        in policy.waveforms
    ):
        values.append(
            SoundRecipe(
                "music_stream",
                Waveform.STREAM,
                0.0,
                0.2,
                120,
                priority=1,
                looping=True,
                position=AudioPosition(),
            )
        )
    return AudioSceneSource(
        listener=AudioPosition(),
        sounds=tuple(values),
    )
