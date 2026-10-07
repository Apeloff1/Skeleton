"""Executable legacy game engines for the Jeeves historical engine laboratory.

The first four technology eras are real deterministic machines rather than
metadata-only profiles. AI changes stay data-only: a sandbox may patch bounded
tuning JSON, but arbitrary sandbox Python is never executed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import IntFlag
from typing import Iterable, Mapping, Sequence

from .game_engine_lab import (
    EngineEra,
    EngineEraProfile,
    GameEngineLabError,
    NumericMode,
    SandboxPatch,
    VirtualFileTree,
    build_engine_file_tree,
    engine_era_profile,
)

LEGACY_ERAS = (
    EngineEra.PONG,
    EngineEra.ARCADE,
    EngineEra.EIGHT_BIT,
    EngineEra.SIXTEEN_BIT,
)


class InputButton(IntFlag):
    NONE = 0
    UP = 1 << 0
    DOWN = 1 << 1
    LEFT = 1 << 2
    RIGHT = 1 << 3
    FIRE = 1 << 4
    START = 1 << 5
    A = 1 << 6
    B = 1 << 7
    C = 1 << 8


@dataclass(frozen=True, slots=True)
class InputFrame:
    tick: int
    buttons: InputButton = InputButton.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.tick, int) or self.tick < 0:
            raise GameEngineLabError("input tick must be a non-negative integer")
        if not isinstance(self.buttons, InputButton):
            object.__setattr__(self, "buttons", InputButton(int(self.buttons)))

    def pressed(self, button: InputButton) -> bool:
        return bool(self.buttons & button)


@dataclass(frozen=True, slots=True)
class DrawCommand:
    kind: str
    layer: int
    values: tuple[int | float | str, ...]

    def __post_init__(self) -> None:
        if self.kind not in {"rect", "line", "sprite", "tile", "plane"}:
            raise GameEngineLabError(f"unsupported draw command: {self.kind}")
        if not isinstance(self.layer, int):
            raise GameEngineLabError("draw layer must be an integer")


@dataclass(frozen=True, slots=True)
class AudioEvent:
    channel: int
    waveform: str
    frequency_hz: int
    frames: int
    volume: int = 15
    priority: int = 0

    def __post_init__(self) -> None:
        if self.waveform not in {"square", "triangle", "noise", "pcm"}:
            raise GameEngineLabError("unsupported legacy waveform")
        if self.channel < 0 or self.frequency_hz <= 0 or self.frames <= 0:
            raise GameEngineLabError("invalid audio event")
        if not 0 <= self.volume <= 15:
            raise GameEngineLabError("legacy volume must be within [0, 15]")


@dataclass(frozen=True, slots=True)
class LegacyHardwareSpec:
    era: EngineEra
    width: int
    height: int
    palette_size: int
    max_audio_voices: int
    max_sprites_per_scanline: int | None
    coordinate_fraction_bits: int
    renderer: str
    input_bits: int


LEGACY_HARDWARE: Mapping[EngineEra, LegacyHardwareSpec] = {
    EngineEra.PONG: LegacyHardwareSpec(
        EngineEra.PONG, 256, 224, 2, 1, None, 0, "scanline_primitives", 6
    ),
    EngineEra.ARCADE: LegacyHardwareSpec(
        EngineEra.ARCADE, 320, 240, 8, 3, None, 8, "vector_sprite_list", 7
    ),
    EngineEra.EIGHT_BIT: LegacyHardwareSpec(
        EngineEra.EIGHT_BIT, 256, 240, 32, 4, 8, 8, "tile_sprite_ppu", 8
    ),
    EngineEra.SIXTEEN_BIT: LegacyHardwareSpec(
        EngineEra.SIXTEEN_BIT, 320, 224, 256, 8, 32, 16, "multiplane_raster", 9
    ),
}

# (default, minimum, maximum). This deliberately small surface is the only
# data an AI is allowed to tune in the executable legacy machines.
LEGACY_TUNING: Mapping[EngineEra, Mapping[str, tuple[float, float, float]]] = {
    EngineEra.PONG: {
        "paddle_speed": (4.0, 1.0, 8.0),
        "ball_speed_x": (3.0, 1.0, 6.0),
        "ball_speed_y": (2.0, 0.5, 5.0),
    },
    EngineEra.ARCADE: {
        "thrust": (0.18, 0.05, 0.40),
        "drag": (0.992, 0.95, 0.999),
        "shot_speed": (4.0, 2.0, 8.0),
        "fire_cooldown": (6.0, 2.0, 20.0),
    },
    EngineEra.EIGHT_BIT: {
        "run_speed": (1.5, 0.5, 3.0),
        "jump_impulse": (4.5, 2.0, 7.0),
        "gravity": (0.25, 0.10, 0.60),
        "fall_speed": (5.0, 2.0, 8.0),
    },
    EngineEra.SIXTEEN_BIT: {
        "acceleration": (0.22, 0.05, 0.50),
        "friction": (0.90, 0.70, 0.98),
        "max_speed": (3.0, 1.0, 6.0),
        "jump_impulse": (5.5, 2.5, 8.0),
        "gravity": (0.28, 0.10, 0.70),
    },
}


def legacy_hardware(era: EngineEra | str) -> LegacyHardwareSpec:
    try:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    except ValueError as exc:
        raise GameEngineLabError(f"unknown engine era: {era!r}") from exc
    try:
        return LEGACY_HARDWARE[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"engine era is not implemented by legacy runtime: {key.value}"
        ) from exc


def default_legacy_tuning(era: EngineEra | str) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    try:
        bounds = LEGACY_TUNING[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"engine era is not implemented by legacy runtime: {key.value}"
        ) from exc
    return {name: values[0] for name, values in bounds.items()}


def normalize_legacy_tuning(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    bounds = LEGACY_TUNING.get(key)
    if bounds is None:
        raise GameEngineLabError(
            f"engine era is not implemented by legacy runtime: {key.value}"
        )
    source = default_legacy_tuning(key) if tuning is None else dict(tuning)
    if set(source) != set(bounds):
        missing = sorted(set(bounds) - set(source))
        extra = sorted(set(source) - set(bounds))
        raise GameEngineLabError(
            f"legacy tuning keys mismatch: missing={missing} extra={extra}"
        )
    out: dict[str, float] = {}
    for name, (_, low, high) in bounds.items():
        raw = source[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise GameEngineLabError(f"legacy tuning {name} must be numeric")
        value = float(raw)
        if not math.isfinite(value) or not low <= value <= high:
            raise GameEngineLabError(
                f"legacy tuning {name} outside [{low}, {high}]"
            )
        out[name] = value
    return out


def compile_legacy_tuning(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> dict[str, float]:
    try:
        payload = json.loads(tree.read("engine/legacy_tuning.json"))
    except (GameEngineLabError, json.JSONDecodeError) as exc:
        raise GameEngineLabError("legacy tuning file missing or invalid") from exc
    if not isinstance(payload, dict):
        raise GameEngineLabError("legacy tuning must be a JSON object")
    return normalize_legacy_tuning(era, payload)


def _quantize(profile: EngineEraProfile, value: float) -> float:
    if not math.isfinite(value):
        raise GameEngineLabError("machine numeric state must be finite")
    if profile.numeric_mode is NumericMode.INTEGER:
        return float(round(value))
    if profile.numeric_mode is NumericMode.FIXED8:
        return round(value * 256.0) / 256.0
    if profile.numeric_mode is NumericMode.FIXED16:
        return round(value * 65536.0) / 65536.0
    return float(value)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LegacySnapshot:
    era: EngineEra
    tick: int
    state: tuple[tuple[str, object], ...]
    digest: str


@dataclass(frozen=True, slots=True)
class FramePacket:
    era: EngineEra
    tick: int
    draw_commands: tuple[DrawCommand, ...]
    audio_events: tuple[AudioEvent, ...]
    state_digest: str
    dropped_draws: int = 0
    dropped_audio: int = 0


class AudioMixer:
    def __init__(self, spec: LegacyHardwareSpec) -> None:
        self.spec = spec
        self._pending: list[AudioEvent] = []
        self.dropped = 0

    def emit(self, event: AudioEvent) -> None:
        self._pending.append(event)

    def flush(self) -> tuple[AudioEvent, ...]:
        ordered = sorted(
            self._pending,
            key=lambda event: (
                -event.priority,
                event.channel,
                event.frequency_hz,
                event.waveform,
            ),
        )
        kept: list[AudioEvent] = []
        used_channels: set[int] = set()
        for event in ordered:
            if (
                event.channel >= self.spec.max_audio_voices
                or event.channel in used_channels
            ):
                self.dropped += 1
                continue
            used_channels.add(event.channel)
            kept.append(event)
            if len(kept) >= self.spec.max_audio_voices:
                self.dropped += max(0, len(ordered) - len(kept))
                break
        self._pending.clear()
        return tuple(sorted(kept, key=lambda event: event.channel))


class CommandRenderer:
    def __init__(
        self,
        profile: EngineEraProfile,
        spec: LegacyHardwareSpec,
    ) -> None:
        self.profile = profile
        self.spec = spec
        self._commands: list[DrawCommand] = []
        self.dropped = 0

    def emit(self, command: DrawCommand) -> None:
        if len(self._commands) >= self.profile.draw_budget:
            self.dropped += 1
            return
        self._commands.append(command)

    def flush(self) -> tuple[DrawCommand, ...]:
        commands = sorted(
            self._commands,
            key=lambda command: (
                command.layer,
                command.kind,
                command.values,
            ),
        )
        self._commands.clear()
        if self.spec.max_sprites_per_scanline is None:
            return tuple(commands)
        return self._apply_scanline_sprite_limit(commands)

    def _apply_scanline_sprite_limit(
        self,
        commands: Sequence[DrawCommand],
    ) -> tuple[DrawCommand, ...]:
        limit = self.spec.max_sprites_per_scanline
        assert limit is not None
        sprite_rows: dict[int, int] = {}
        kept: list[DrawCommand] = []
        for command in commands:
            if command.kind != "sprite":
                kept.append(command)
                continue
            y = int(command.values[1]) if len(command.values) > 1 else 0
            row = max(0, min(self.spec.height - 1, y))
            count = sprite_rows.get(row, 0)
            if count >= limit:
                self.dropped += 1
                continue
            sprite_rows[row] = count + 1
            kept.append(command)
        return tuple(kept)


class LegacyMachine:
    """Fixed-step machine with bounded I/O and deterministic snapshots."""

    def __init__(
        self,
        era: EngineEra,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        if era not in LEGACY_ERAS:
            raise GameEngineLabError(
                f"legacy machine unavailable for {era.value}"
            )
        self.profile = engine_era_profile(era)
        self.spec = legacy_hardware(era)
        self.tuning = normalize_legacy_tuning(era, tuning)
        self.tick = 0
        self.renderer = CommandRenderer(self.profile, self.spec)
        self.audio = AudioMixer(self.spec)

    def step(self, frame: InputFrame | None = None) -> FramePacket:
        if frame is None:
            frame = InputFrame(self.tick)
        if frame.tick != self.tick:
            raise GameEngineLabError(
                f"input tick mismatch: expected {self.tick}, got {frame.tick}"
            )
        self._update(frame)
        self._render()
        draws = self.renderer.flush()
        audio = self.audio.flush()
        packet = FramePacket(
            self.profile.era,
            self.tick,
            draws,
            audio,
            self.fingerprint(),
            self.renderer.dropped,
            self.audio.dropped,
        )
        self.tick += 1
        return packet

    def run(
        self,
        frames: Iterable[InputFrame],
    ) -> tuple[FramePacket, ...]:
        return tuple(self.step(frame) for frame in frames)

    def snapshot(self) -> LegacySnapshot:
        state = tuple(sorted(self._export_state().items()))
        payload = {
            "era": self.profile.era.value,
            "tick": self.tick,
            "state": state,
        }
        return LegacySnapshot(
            self.profile.era,
            self.tick,
            state,
            _digest(payload),
        )

    def restore(self, snapshot: LegacySnapshot) -> None:
        if snapshot.era is not self.profile.era:
            raise GameEngineLabError("legacy snapshot era mismatch")
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "state": snapshot.state,
        }
        if _digest(payload) != snapshot.digest:
            raise GameEngineLabError("legacy snapshot digest mismatch")
        self.tick = snapshot.tick
        self._import_state(dict(snapshot.state))

    def fingerprint(self) -> str:
        return _digest(
            {
                "era": self.profile.era.value,
                "tick": self.tick,
                "state": tuple(sorted(self._export_state().items())),
            }
        )

    def _update(self, frame: InputFrame) -> None:
        raise NotImplementedError

    def _render(self) -> None:
        raise NotImplementedError

    def _export_state(self) -> dict[str, object]:
        raise NotImplementedError

    def _import_state(self, state: Mapping[str, object]) -> None:
        raise NotImplementedError


class PongMachine(LegacyMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(EngineEra.PONG, tuning)
        self.left_y = 112.0
        self.right_y = 112.0
        self.ball_x = 128.0
        self.ball_y = 112.0
        self.ball_vx = self.tuning["ball_speed_x"]
        self.ball_vy = self.tuning["ball_speed_y"]
        self.left_score = 0
        self.right_score = 0

    def _update(self, frame: InputFrame) -> None:
        move = self.tuning["paddle_speed"]
        if frame.pressed(InputButton.UP):
            self.left_y -= move
        if frame.pressed(InputButton.DOWN):
            self.left_y += move
        if frame.pressed(InputButton.A):
            self.right_y -= move
        if frame.pressed(InputButton.B):
            self.right_y += move
        self.left_y = _quantize(
            self.profile,
            min(max(self.left_y, 18.0), self.spec.height - 18.0),
        )
        self.right_y = _quantize(
            self.profile,
            min(max(self.right_y, 18.0), self.spec.height - 18.0),
        )
        self.ball_x = _quantize(
            self.profile,
            self.ball_x + self.ball_vx,
        )
        self.ball_y = _quantize(
            self.profile,
            self.ball_y + self.ball_vy,
        )
        if self.ball_y <= 2 or self.ball_y >= self.spec.height - 2:
            self.ball_vy = -self.ball_vy
            self.ball_y = min(max(self.ball_y, 2), self.spec.height - 2)
            self.audio.emit(
                AudioEvent(0, "square", 440, 2, priority=1)
            )
        if (
            self.ball_vx < 0
            and self.ball_x <= 12
            and abs(self.ball_y - self.left_y) <= 18
        ):
            self.ball_x = 12.0
            self.ball_vx = abs(self.ball_vx)
            self.audio.emit(
                AudioEvent(0, "square", 660, 2, priority=2)
            )
        elif (
            self.ball_vx > 0
            and self.ball_x >= self.spec.width - 12
            and abs(self.ball_y - self.right_y) <= 18
        ):
            self.ball_x = float(self.spec.width - 12)
            self.ball_vx = -abs(self.ball_vx)
            self.audio.emit(
                AudioEvent(0, "square", 660, 2, priority=2)
            )
        if self.ball_x < 0:
            self.right_score += 1
            self._serve(1.0)
        elif self.ball_x > self.spec.width:
            self.left_score += 1
            self._serve(-1.0)

    def _serve(self, direction: float) -> None:
        self.ball_x = float(self.spec.width // 2)
        self.ball_y = float(self.spec.height // 2)
        self.ball_vx = self.tuning["ball_speed_x"] * direction
        vertical = self.tuning["ball_speed_y"]
        self.ball_vy = (
            vertical
            if (self.left_score + self.right_score) % 2 == 0
            else -vertical
        )
        self.audio.emit(
            AudioEvent(0, "square", 220, 8, priority=3)
        )

    def _render(self) -> None:
        self.renderer.emit(
            DrawCommand(
                "rect",
                0,
                (0, 0, self.spec.width, self.spec.height, 0),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "line",
                1,
                (
                    self.spec.width // 2,
                    0,
                    self.spec.width // 2,
                    self.spec.height,
                    1,
                ),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "rect",
                2,
                (8, int(self.left_y) - 16, 4, 32, 1),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "rect",
                2,
                (
                    self.spec.width - 12,
                    int(self.right_y) - 16,
                    4,
                    32,
                    1,
                ),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "rect",
                3,
                (
                    int(self.ball_x) - 2,
                    int(self.ball_y) - 2,
                    4,
                    4,
                    1,
                ),
            )
        )

    def _export_state(self) -> dict[str, object]:
        return {
            "ball_vx": self.ball_vx,
            "ball_vy": self.ball_vy,
            "ball_x": self.ball_x,
            "ball_y": self.ball_y,
            "left_score": self.left_score,
            "left_y": self.left_y,
            "right_score": self.right_score,
            "right_y": self.right_y,
        }

    def _import_state(self, state: Mapping[str, object]) -> None:
        self.ball_vx = float(state["ball_vx"])
        self.ball_vy = float(state["ball_vy"])
        self.ball_x = float(state["ball_x"])
        self.ball_y = float(state["ball_y"])
        self.left_score = int(state["left_score"])
        self.left_y = float(state["left_y"])
        self.right_score = int(state["right_score"])
        self.right_y = float(state["right_y"])


class VectorArcadeMachine(LegacyMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(EngineEra.ARCADE, tuning)
        self.ship_x = 160.0
        self.ship_y = 120.0
        self.angle = 0
        self.vx = 0.0
        self.vy = 0.0
        self.shots: list[
            tuple[float, float, float, float, int]
        ] = []
        self.fire_cooldown = 0

    def _update(self, frame: InputFrame) -> None:
        if frame.pressed(InputButton.LEFT):
            self.angle = (self.angle - 8) % 360
        if frame.pressed(InputButton.RIGHT):
            self.angle = (self.angle + 8) % 360
        radians = math.radians(self.angle)
        if frame.pressed(InputButton.UP):
            self.vx += (
                math.cos(radians) * self.tuning["thrust"]
            )
            self.vy += (
                math.sin(radians) * self.tuning["thrust"]
            )
        self.vx = _quantize(
            self.profile,
            self.vx * self.tuning["drag"],
        )
        self.vy = _quantize(
            self.profile,
            self.vy * self.tuning["drag"],
        )
        self.ship_x = _quantize(
            self.profile,
            (self.ship_x + self.vx) % self.spec.width,
        )
        self.ship_y = _quantize(
            self.profile,
            (self.ship_y + self.vy) % self.spec.height,
        )
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if (
            frame.pressed(InputButton.FIRE)
            and self.fire_cooldown == 0
            and len(self.shots) < 12
        ):
            speed = self.tuning["shot_speed"]
            self.shots.append(
                (
                    self.ship_x,
                    self.ship_y,
                    math.cos(radians) * speed,
                    math.sin(radians) * speed,
                    45,
                )
            )
            self.fire_cooldown = int(
                round(self.tuning["fire_cooldown"])
            )
            self.audio.emit(
                AudioEvent(1, "square", 880, 3, priority=2)
            )
        next_shots = []
        for x, y, vx, vy, life in self.shots:
            if life > 1:
                next_shots.append(
                    (
                        _quantize(
                            self.profile,
                            (x + vx) % self.spec.width,
                        ),
                        _quantize(
                            self.profile,
                            (y + vy) % self.spec.height,
                        ),
                        vx,
                        vy,
                        life - 1,
                    )
                )
        self.shots = next_shots

    def _render(self) -> None:
        radians = math.radians(self.angle)
        nose = (
            self.ship_x + math.cos(radians) * 9,
            self.ship_y + math.sin(radians) * 9,
        )
        left = (
            self.ship_x + math.cos(radians + 2.5) * 7,
            self.ship_y + math.sin(radians + 2.5) * 7,
        )
        right = (
            self.ship_x + math.cos(radians - 2.5) * 7,
            self.ship_y + math.sin(radians - 2.5) * 7,
        )
        for start, end in (
            (nose, left),
            (left, right),
            (right, nose),
        ):
            self.renderer.emit(
                DrawCommand(
                    "line",
                    2,
                    (
                        round(start[0], 3),
                        round(start[1], 3),
                        round(end[0], 3),
                        round(end[1], 3),
                        7,
                    ),
                )
            )
        for x, y, *_ in self.shots:
            self.renderer.emit(
                DrawCommand(
                    "line",
                    3,
                    (x, y, x + 1, y + 1, 7),
                )
            )

    def _export_state(self) -> dict[str, object]:
        return {
            "angle": self.angle,
            "fire_cooldown": self.fire_cooldown,
            "ship_x": self.ship_x,
            "ship_y": self.ship_y,
            "shots": tuple(
                tuple(value for value in shot)
                for shot in self.shots
            ),
            "vx": self.vx,
            "vy": self.vy,
        }

    def _import_state(self, state: Mapping[str, object]) -> None:
        self.angle = int(state["angle"])
        self.fire_cooldown = int(state["fire_cooldown"])
        self.ship_x = float(state["ship_x"])
        self.ship_y = float(state["ship_y"])
        self.vx = float(state["vx"])
        self.vy = float(state["vy"])
        self.shots = [
            tuple(shot)
            for shot in state["shots"]
        ]


class EightBitTileMachine(LegacyMachine):
    TILE = 16
    MAP_W = 16
    MAP_H = 15

    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(EngineEra.EIGHT_BIT, tuning)
        self.map = tuple(
            1
            if (
                y == self.MAP_H - 1
                or (y == 11 and 5 <= x <= 9)
            )
            else 0
            for y in range(self.MAP_H)
            for x in range(self.MAP_W)
        )
        self.x = 32.0
        self.y = 160.0
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.camera_x = 0

    def _solid(self, px: float, py: float) -> bool:
        tx = int(px // self.TILE)
        ty = int(py // self.TILE)
        if (
            tx < 0
            or tx >= self.MAP_W
            or ty < 0
            or ty >= self.MAP_H
        ):
            return True
        return bool(self.map[ty * self.MAP_W + tx])

    def _update(self, frame: InputFrame) -> None:
        target = 0.0
        if frame.pressed(InputButton.LEFT):
            target -= self.tuning["run_speed"]
        if frame.pressed(InputButton.RIGHT):
            target += self.tuning["run_speed"]
        self.vx = _quantize(self.profile, target)
        if frame.pressed(InputButton.A) and self.on_ground:
            self.vy = -self.tuning["jump_impulse"]
            self.on_ground = False
            self.audio.emit(
                AudioEvent(0, "square", 520, 4, priority=2)
            )
        self.vy = _quantize(
            self.profile,
            min(
                self.vy + self.tuning["gravity"],
                self.tuning["fall_speed"],
            ),
        )
        nx = _quantize(self.profile, self.x + self.vx)
        if not (
            self._solid(nx - 6, self.y)
            or self._solid(nx + 6, self.y)
        ):
            self.x = nx
        ny = _quantize(self.profile, self.y + self.vy)
        foot = ny + 8
        head = ny - 8
        if self.vy >= 0 and (
            self._solid(self.x - 5, foot)
            or self._solid(self.x + 5, foot)
        ):
            self.y = float(
                int(foot // self.TILE) * self.TILE - 8
            )
            self.vy = 0.0
            self.on_ground = True
        elif self.vy < 0 and (
            self._solid(self.x - 5, head)
            or self._solid(self.x + 5, head)
        ):
            self.vy = 0.0
        else:
            self.y = ny
            self.on_ground = False
        self.camera_x = max(
            0,
            min(
                self.MAP_W * self.TILE - self.spec.width,
                int(self.x) - self.spec.width // 2,
            ),
        )

    def _render(self) -> None:
        for ty in range(self.MAP_H):
            for tx in range(self.MAP_W):
                tile = self.map[ty * self.MAP_W + tx]
                if tile:
                    self.renderer.emit(
                        DrawCommand(
                            "tile",
                            0,
                            (tx, ty, tile),
                        )
                    )
        self.renderer.emit(
            DrawCommand(
                "sprite",
                2,
                (
                    int(self.x) - self.camera_x,
                    int(self.y),
                    1,
                    0,
                ),
            )
        )

    def _export_state(self) -> dict[str, object]:
        return {
            "camera_x": self.camera_x,
            "on_ground": self.on_ground,
            "vx": self.vx,
            "vy": self.vy,
            "x": self.x,
            "y": self.y,
        }

    def _import_state(self, state: Mapping[str, object]) -> None:
        self.camera_x = int(state["camera_x"])
        self.on_ground = bool(state["on_ground"])
        self.vx = float(state["vx"])
        self.vy = float(state["vy"])
        self.x = float(state["x"])
        self.y = float(state["y"])


@dataclass(slots=True)
class PooledActor:
    active: bool = False
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    sprite: int = 0


class SixteenBitRasterMachine(LegacyMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(EngineEra.SIXTEEN_BIT, tuning)
        self.player_x = 48.0
        self.player_y = 160.0
        self.vx = 0.0
        self.vy = 0.0
        self.scroll_x = 0.0
        self.actors = [
            PooledActor()
            for _ in range(48)
        ]
        for index in range(8):
            self.actors[index] = PooledActor(
                True,
                120.0 + index * 24.0,
                176.0,
                -0.25 if index % 2 else 0.25,
                0.0,
                10 + index,
            )

    def _update(self, frame: InputFrame) -> None:
        acceleration = self.tuning["acceleration"]
        if frame.pressed(InputButton.LEFT):
            self.vx -= acceleration
        if frame.pressed(InputButton.RIGHT):
            self.vx += acceleration
        max_speed = self.tuning["max_speed"]
        self.vx = max(
            -max_speed,
            min(
                max_speed,
                self.vx * self.tuning["friction"],
            ),
        )
        if (
            frame.pressed(InputButton.A)
            and self.player_y >= 176.0
        ):
            self.vy = -self.tuning["jump_impulse"]
            self.audio.emit(
                AudioEvent(0, "square", 660, 4, priority=2)
            )
        self.vy = min(
            self.tuning["max_speed"] * 2.0,
            self.vy + self.tuning["gravity"],
        )
        self.player_x = _quantize(
            self.profile,
            max(8.0, self.player_x + self.vx),
        )
        self.player_y = _quantize(
            self.profile,
            min(176.0, self.player_y + self.vy),
        )
        if self.player_y >= 176.0:
            self.vy = 0.0
        self.scroll_x = _quantize(
            self.profile,
            max(0.0, self.player_x - 96.0),
        )
        for actor in self.actors:
            if not actor.active:
                continue
            actor.x = _quantize(
                self.profile,
                actor.x + actor.vx,
            )
            if actor.x < self.scroll_x - 32:
                actor.x = (
                    self.scroll_x + self.spec.width + 32
                )

    def _render(self) -> None:
        self.renderer.emit(
            DrawCommand(
                "plane",
                0,
                (0, round(self.scroll_x * 0.25, 4), "sky"),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "plane",
                1,
                (
                    1,
                    round(self.scroll_x * 0.50, 4),
                    "mountains",
                ),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "plane",
                2,
                (2, round(self.scroll_x, 4), "ground"),
            )
        )
        self.renderer.emit(
            DrawCommand(
                "sprite",
                4,
                (
                    round(self.player_x - self.scroll_x, 4),
                    round(self.player_y, 4),
                    1,
                    0,
                ),
            )
        )
        for actor in self.actors:
            if not actor.active:
                continue
            screen_x = actor.x - self.scroll_x
            if -16 <= screen_x <= self.spec.width + 16:
                self.renderer.emit(
                    DrawCommand(
                        "sprite",
                        3,
                        (
                            round(screen_x, 4),
                            round(actor.y, 4),
                            actor.sprite,
                            0,
                        ),
                    )
                )

    def _export_state(self) -> dict[str, object]:
        return {
            "actors": tuple(
                (
                    actor.active,
                    actor.x,
                    actor.y,
                    actor.vx,
                    actor.vy,
                    actor.sprite,
                )
                for actor in self.actors
            ),
            "player_x": self.player_x,
            "player_y": self.player_y,
            "scroll_x": self.scroll_x,
            "vx": self.vx,
            "vy": self.vy,
        }

    def _import_state(self, state: Mapping[str, object]) -> None:
        self.player_x = float(state["player_x"])
        self.player_y = float(state["player_y"])
        self.scroll_x = float(state["scroll_x"])
        self.vx = float(state["vx"])
        self.vy = float(state["vy"])
        self.actors = [
            PooledActor(
                bool(actor[0]),
                float(actor[1]),
                float(actor[2]),
                float(actor[3]),
                float(actor[4]),
                int(actor[5]),
            )
            for actor in state["actors"]
        ]


def create_legacy_machine(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> LegacyMachine:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    if key is EngineEra.PONG:
        return PongMachine(tuning)
    if key is EngineEra.ARCADE:
        return VectorArcadeMachine(tuning)
    if key is EngineEra.EIGHT_BIT:
        return EightBitTileMachine(tuning)
    if key is EngineEra.SIXTEEN_BIT:
        return SixteenBitRasterMachine(tuning)
    raise GameEngineLabError(
        f"engine era is not implemented by legacy runtime: {key.value}"
    )


def create_legacy_machine_from_tree(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> LegacyMachine:
    return create_legacy_machine(
        era,
        compile_legacy_tuning(era, tree),
    )


def build_legacy_engine_tree(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> VirtualFileTree:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    spec = legacy_hardware(key)
    profile = engine_era_profile(key)
    base = build_engine_file_tree(
        key,
        gameplay_dialect,
    )
    patches = [
        SandboxPatch(
            "engine/input.json",
            json.dumps(
                {
                    "bits": spec.input_bits,
                    "buttons": [
                        button.name
                        for button in InputButton
                        if button is not InputButton.NONE
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "engine/audio.json",
            json.dumps(
                {
                    "max_voices": spec.max_audio_voices,
                    "volume_steps": 16,
                    "deterministic_priority": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "engine/legacy_renderer.json",
            json.dumps(
                {
                    "renderer": spec.renderer,
                    "viewport": [spec.width, spec.height],
                    "palette_size": spec.palette_size,
                    "draw_budget": profile.draw_budget,
                    "scanline_sprite_limit":
                        spec.max_sprites_per_scanline,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "engine/legacy_runtime.py",
            (
                f'ENGINE_ERA = "{key.value}"\n'
                f'MACHINE = "{create_legacy_machine(key).__class__.__name__}"\n'
            ),
        ),
        SandboxPatch(
            "engine/legacy_tuning.json",
            json.dumps(
                default_legacy_tuning(key),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
    ]
    return base.apply(patches)


@dataclass(frozen=True, slots=True)
class LegacyProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class LegacyQualityReport:
    era: EngineEra
    probes: tuple[LegacyProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    @property
    def score(self) -> float:
        return sum(
            probe.passed
            for probe in self.probes
        ) / max(1, len(self.probes))

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class LegacyEngineAdversary:
    """Replay/budget/snapshot tournament for legacy machines."""

    def _script(
        self,
        length: int = 180,
    ) -> tuple[InputFrame, ...]:
        frames = []
        for tick in range(length):
            buttons = InputButton.NONE
            if tick % 40 < 16:
                buttons |= InputButton.RIGHT
            if tick % 53 == 0:
                buttons |= InputButton.A | InputButton.FIRE
            if 80 <= tick < 95:
                buttons |= InputButton.LEFT
            frames.append(
                InputFrame(tick, buttons)
            )
        return tuple(frames)

    def evaluate(
        self,
        era: EngineEra | str,
        tree: VirtualFileTree | None = None,
    ) -> LegacyQualityReport:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        spec = legacy_hardware(key)
        active_tree = (
            tree
            or build_legacy_engine_tree(
                key,
                "arcade_golden_age",
            )
        )
        required = {
            "engine/input.json",
            "engine/audio.json",
            "engine/legacy_renderer.json",
            "engine/legacy_runtime.py",
            "engine/legacy_tuning.json",
        }
        tree_ok = required <= set(active_tree.files)
        probes = [
            LegacyProbe(
                "file_tree",
                tree_ok,
                (
                    "era runtime tree present"
                    if tree_ok
                    else "legacy runtime files missing"
                ),
            )
        ]
        try:
            tuning = compile_legacy_tuning(
                key,
                active_tree,
            )
        except GameEngineLabError as exc:
            tuning = None
            tuning_detail = str(exc)
        else:
            tuning_detail = "bounded tuning compiled"
        probes.append(
            LegacyProbe(
                "tuning",
                tuning is not None,
                tuning_detail,
            )
        )
        if not tree_ok or tuning is None:
            probes.extend(
                [
                    LegacyProbe(
                        "determinism",
                        False,
                        "runtime not compilable",
                    ),
                    LegacyProbe(
                        "draw_budget",
                        False,
                        "runtime not compilable",
                    ),
                    LegacyProbe(
                        "audio_budget",
                        False,
                        "runtime not compilable",
                    ),
                    LegacyProbe(
                        "snapshot",
                        False,
                        "runtime not compilable",
                    ),
                ]
            )
            return LegacyQualityReport(
                key,
                tuple(probes),
            )

        script = self._script()
        first = create_legacy_machine(key, tuning)
        second = create_legacy_machine(key, tuning)
        first_packets = first.run(script)
        second_packets = second.run(script)
        probes.append(
            LegacyProbe(
                "determinism",
                (
                    first.fingerprint()
                    == second.fingerprint()
                    and first_packets == second_packets
                ),
                "identical input replays",
            )
        )
        probes.append(
            LegacyProbe(
                "draw_budget",
                all(
                    len(packet.draw_commands)
                    <= first.profile.draw_budget
                    for packet in first_packets
                ),
                "bounded command buffers",
            )
        )
        probes.append(
            LegacyProbe(
                "audio_budget",
                all(
                    len(packet.audio_events)
                    <= spec.max_audio_voices
                    for packet in first_packets
                ),
                "bounded audio voices",
            )
        )

        snapshot_machine = create_legacy_machine(
            key,
            tuning,
        )
        prefix = self._script(60)
        snapshot_machine.run(prefix)
        snapshot = snapshot_machine.snapshot()
        before = snapshot_machine.fingerprint()
        snapshot_machine.run(
            tuple(
                InputFrame(
                    60 + index,
                    InputButton.LEFT,
                )
                for index in range(20)
            )
        )
        snapshot_machine.restore(snapshot)
        probes.append(
            LegacyProbe(
                "snapshot",
                snapshot_machine.fingerprint() == before,
                "state roundtrip",
            )
        )
        return LegacyQualityReport(
            key,
            tuple(probes),
        )


@dataclass(frozen=True, slots=True)
class LegacyEngineSandbox:
    era: EngineEra
    tree: VirtualFileTree
    gameplay_dialect: str | None = None

    def apply(
        self,
        patches: Iterable[SandboxPatch],
    ) -> "LegacyEngineSandbox":
        return LegacyEngineSandbox(
            self.era,
            self.tree.apply(patches),
            self.gameplay_dialect,
        )

    def machine(self) -> LegacyMachine:
        return create_legacy_machine_from_tree(
            self.era,
            self.tree,
        )


@dataclass(frozen=True, slots=True)
class LegacyImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LegacyImprovementResult:
    sandbox: LegacyEngineSandbox
    report: LegacyQualityReport
    rounds: tuple[LegacyImprovementRound, ...]
    promoted: bool


class LegacyEngineLab:
    """Safe compiler/evaluator loop for AI-manipulated legacy trees."""

    def __init__(
        self,
        adversary: LegacyEngineAdversary | None = None,
    ) -> None:
        self.adversary = (
            adversary
            or LegacyEngineAdversary()
        )

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> LegacyEngineSandbox:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        legacy_hardware(key)
        return LegacyEngineSandbox(
            key,
            build_legacy_engine_tree(
                key,
                gameplay_dialect,
            ),
            gameplay_dialect,
        )

    def evaluate(
        self,
        sandbox: LegacyEngineSandbox,
    ) -> LegacyQualityReport:
        return self.adversary.evaluate(
            sandbox.era,
            sandbox.tree,
        )

    def canonical_repair(
        self,
        sandbox: LegacyEngineSandbox,
        report: LegacyQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = build_legacy_engine_tree(
            sandbox.era,
            sandbox.gameplay_dialect,
        )
        protected = {
            "engine/input.json",
            "engine/audio.json",
            "engine/legacy_renderer.json",
            "engine/legacy_runtime.py",
            "engine/legacy_tuning.json",
        }
        patches: list[SandboxPatch] = []
        for path in sorted(protected):
            wanted = canonical.read(path)
            try:
                current = sandbox.tree.read(path)
            except GameEngineLabError:
                current = None
            if current != wanted:
                patches.append(
                    SandboxPatch(
                        path,
                        wanted,
                        sandbox.tree.file_digest(path),
                    )
                )
        return tuple(patches)

    def adversarial_improve(
        self,
        sandbox: LegacyEngineSandbox,
        *,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> LegacyImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError(
                "target must be within (0, 1]"
            )
        if (
            not isinstance(max_rounds, int)
            or not 1 <= max_rounds <= 32
        ):
            raise GameEngineLabError(
                "max_rounds must be within [1, 32]"
            )
        current = sandbox
        report = self.evaluate(current)
        rounds: list[LegacyImprovementRound] = []
        if (
            report.passed
            and report.score >= target
        ):
            return LegacyImprovementResult(
                current,
                report,
                (),
                True,
            )
        strategy = (
            improver
            or self.canonical_repair
        )
        for index in range(
            1,
            max_rounds + 1,
        ):
            patches = tuple(
                strategy(current, report)
            )
            if not patches:
                break
            candidate = current.apply(patches)
            next_report = self.evaluate(candidate)
            accepted = (
                candidate.tree.digest
                != current.tree.digest
                and next_report.score
                >= report.score
                and len(next_report.failed)
                <= len(report.failed)
            )
            rounds.append(
                LegacyImprovementRound(
                    index,
                    current.tree.digest,
                    candidate.tree.digest,
                    report.score,
                    next_report.score,
                    accepted,
                    next_report.failed,
                )
            )
            if not accepted:
                break
            current = candidate
            report = next_report
            if (
                report.passed
                and report.score >= target
            ):
                break
        return LegacyImprovementResult(
            current,
            report,
            tuple(rounds),
            (
                report.passed
                and report.score >= target
            ),
        )
