"""Executable HD-through-next game-engine eras for Jeeves.

These machines model the post-shader transition as distinct deterministic
runtime architectures: HD render graphs, streamed open worlds, data-oriented
GPU-driven simulation with rollback, and a bounded hybrid next-era runtime.

AI manipulation stays data-only. Sandboxes compile bounded JSON tuning and,
for the next-era runtime, bounded policy weights. Sandbox Python is never
executed as authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
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
from .game_engine_legacy import InputButton, InputFrame

ADVANCED_ERAS = (
    EngineEra.HD,
    EngineEra.OPEN_WORLD,
    EngineEra.MODERN,
    EngineEra.NEXT,
)


@dataclass(frozen=True, slots=True)
class AdvancedHardwareSpec:
    era: EngineEra
    width: int
    height: int
    pipeline: str
    render_targets: int
    max_lights: int
    streaming: bool
    cell_size: int
    job_lanes: int
    rollback_frames: int
    gpu_driven: bool
    learned_components: bool


ADVANCED_HARDWARE: Mapping[EngineEra, AdvancedHardwareSpec] = {
    EngineEra.HD: AdvancedHardwareSpec(
        EngineEra.HD,
        1280,
        720,
        "hdr_deferred_forward",
        4,
        64,
        False,
        0,
        2,
        0,
        False,
        False,
    ),
    EngineEra.OPEN_WORLD: AdvancedHardwareSpec(
        EngineEra.OPEN_WORLD,
        1920,
        1080,
        "pbr_deferred_forward_plus",
        5,
        256,
        True,
        64,
        4,
        0,
        False,
        False,
    ),
    EngineEra.MODERN: AdvancedHardwareSpec(
        EngineEra.MODERN,
        2560,
        1440,
        "gpu_driven_pbr",
        6,
        1024,
        True,
        128,
        8,
        120,
        True,
        False,
    ),
    EngineEra.NEXT: AdvancedHardwareSpec(
        EngineEra.NEXT,
        3840,
        2160,
        "analytic_neural_hybrid",
        8,
        4096,
        True,
        256,
        16,
        240,
        True,
        True,
    ),
}


ADVANCED_TUNING: Mapping[
    EngineEra,
    Mapping[str, tuple[float, float, float]],
] = {
    EngineEra.HD: {
        "move_speed": (0.55, 0.1, 2.0),
        "yaw_step": (2.5, 0.5, 8.0),
        "exposure": (1.0, 0.25, 4.0),
        "light_cutoff": (42.0, 8.0, 100.0),
    },
    EngineEra.OPEN_WORLD: {
        "move_speed": (0.75, 0.1, 3.0),
        "yaw_step": (2.0, 0.25, 8.0),
        "stream_radius": (2.0, 1.0, 4.0),
        "lod_near": (35.0, 10.0, 80.0),
        "lod_mid": (90.0, 40.0, 180.0),
    },
    EngineEra.MODERN: {
        "move_speed": (0.9, 0.1, 4.0),
        "yaw_step": (1.5, 0.25, 6.0),
        "cull_distance": (260.0, 80.0, 600.0),
        "meshlet_size": (64.0, 16.0, 128.0),
        "rollback_window": (90.0, 30.0, 120.0),
    },
    EngineEra.NEXT: {
        "move_speed": (1.0, 0.1, 5.0),
        "yaw_step": (1.25, 0.1, 6.0),
        "cull_distance": (500.0, 100.0, 1200.0),
        "simulation_substeps": (4.0, 1.0, 8.0),
        "adaptation_rate": (0.01, 0.0, 0.05),
        "confidence_floor": (0.80, 0.50, 0.99),
    },
}


def advanced_hardware(
    era: EngineEra | str,
) -> AdvancedHardwareSpec:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    try:
        return ADVANCED_HARDWARE[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"advanced runtime unavailable for {key.value}"
        ) from exc


def default_advanced_tuning(
    era: EngineEra | str,
) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    advanced_hardware(key)
    return {
        name: values[0]
        for name, values in ADVANCED_TUNING[key].items()
    }


def normalize_advanced_tuning(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    bounds = ADVANCED_TUNING.get(key)
    if bounds is None:
        raise GameEngineLabError(
            f"advanced runtime unavailable for {key.value}"
        )
    source = (
        default_advanced_tuning(key)
        if tuning is None
        else dict(tuning)
    )
    if set(source) != set(bounds):
        missing = sorted(set(bounds) - set(source))
        extra = sorted(set(source) - set(bounds))
        raise GameEngineLabError(
            f"advanced tuning keys mismatch: missing={missing} extra={extra}"
        )
    out: dict[str, float] = {}
    for name, (_, low, high) in bounds.items():
        raw = source[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise GameEngineLabError(
                f"advanced tuning {name} must be numeric"
            )
        value = float(raw)
        if not math.isfinite(value) or not low <= value <= high:
            raise GameEngineLabError(
                f"advanced tuning {name} outside [{low}, {high}]"
            )
        out[name] = value
    return out


def compile_advanced_tuning(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> dict[str, float]:
    try:
        payload = json.loads(
            tree.read("engine/advanced_tuning.json")
        )
    except (GameEngineLabError, json.JSONDecodeError) as exc:
        raise GameEngineLabError(
            "advanced tuning missing or invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise GameEngineLabError(
            "advanced tuning must be a JSON object"
        )
    return normalize_advanced_tuning(era, payload)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _q(
    profile: EngineEraProfile,
    value: float,
) -> float:
    if not math.isfinite(value):
        raise GameEngineLabError(
            "advanced state must be finite"
        )
    if profile.numeric_mode is NumericMode.FLOAT32:
        return round(float(value), 6)
    if profile.numeric_mode is NumericMode.FLOAT64:
        return round(float(value), 12)
    if profile.numeric_mode is NumericMode.FIXED16:
        return round(value * 65536) / 65536
    return float(value)


@dataclass(frozen=True, slots=True)
class AdvancedObject:
    object_id: str
    x: float
    y: float
    z: float
    mesh: str
    material: int
    dynamic: bool = False
    radius: float = 2.0


@dataclass(frozen=True, slots=True)
class AdvancedDrawCommand:
    pass_name: str
    object_id: str
    material: int
    lod: int
    depth: float
    batch_key: tuple[object, ...]
    state_digest: str


@dataclass(frozen=True, slots=True)
class AdvancedFrame:
    era: EngineEra
    tick: int
    commands: tuple[AdvancedDrawCommand, ...]
    loaded_cells: tuple[tuple[int, int], ...]
    state_digest: str
    evidence_digest: str
    culled: int = 0
    batches: int = 0


@dataclass(frozen=True, slots=True)
class AdvancedSnapshot:
    era: EngineEra
    tick: int
    state: tuple[tuple[str, object], ...]
    digest: str


def _world_objects() -> tuple[AdvancedObject, ...]:
    rows: list[AdvancedObject] = []
    materials = (1, 2, 3, 4)
    meshes = ("crate", "tower", "rock", "vehicle")
    for cz in range(-3, 4):
        for cx in range(-3, 4):
            base_x = cx * 64 + 16
            base_z = cz * 64 + 16
            for index in range(4):
                rows.append(
                    AdvancedObject(
                        f"cell_{cx}_{cz}_{index}",
                        float(base_x + index * 10),
                        0.0,
                        float(base_z + (index % 2) * 18),
                        meshes[index],
                        materials[index],
                        dynamic=index == 3,
                        radius=3.0 + index,
                    )
                )
    return tuple(rows)


WORLD_OBJECTS = _world_objects()


class AdvancedMachine:
    """Deterministic fixed-step base for post-shader engine eras."""

    def __init__(
        self,
        era: EngineEra,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        if era not in ADVANCED_ERAS:
            raise GameEngineLabError(
                f"advanced runtime unavailable for {era.value}"
            )
        self.profile = engine_era_profile(era)
        self.spec = advanced_hardware(era)
        self.tuning = normalize_advanced_tuning(
            era,
            tuning,
        )
        self.tick = 0
        self.player_x = 0.0
        self.player_z = 0.0
        self.yaw = 0.0

    def step(
        self,
        frame: InputFrame | None = None,
    ) -> AdvancedFrame:
        if frame is None:
            frame = InputFrame(self.tick)
        if frame.tick != self.tick:
            raise GameEngineLabError(
                f"input tick mismatch: expected {self.tick}, got {frame.tick}"
            )
        self._simulate(frame)
        commands, cells, culled, batches = self._render()
        packet = AdvancedFrame(
            self.profile.era,
            self.tick,
            commands,
            cells,
            self.fingerprint(),
            self._evidence_digest(
                commands,
                cells,
                culled,
                batches,
            ),
            culled,
            batches,
        )
        self._after_frame(packet)
        self.tick += 1
        return packet

    def run(
        self,
        frames: Iterable[InputFrame],
    ) -> tuple[AdvancedFrame, ...]:
        return tuple(
            self.step(frame)
            for frame in frames
        )

    def snapshot(self) -> AdvancedSnapshot:
        state = tuple(
            sorted(
                self._export_state().items()
            )
        )
        payload = {
            "era": self.profile.era.value,
            "tick": self.tick,
            "state": state,
        }
        return AdvancedSnapshot(
            self.profile.era,
            self.tick,
            state,
            _digest(payload),
        )

    def restore(
        self,
        snapshot: AdvancedSnapshot,
    ) -> None:
        if snapshot.era is not self.profile.era:
            raise GameEngineLabError(
                "advanced snapshot era mismatch"
            )
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "state": snapshot.state,
        }
        if _digest(payload) != snapshot.digest:
            raise GameEngineLabError(
                "advanced snapshot digest mismatch"
            )
        self.tick = snapshot.tick
        self._import_state(
            dict(snapshot.state)
        )

    def fingerprint(self) -> str:
        return _digest(
            {
                "era": self.profile.era.value,
                "tick": self.tick,
                "state": tuple(
                    sorted(
                        self._export_state().items()
                    )
                ),
            }
        )

    def _move(
        self,
        frame: InputFrame,
    ) -> None:
        turn = self.tuning["yaw_step"]
        if frame.pressed(InputButton.LEFT):
            self.yaw -= turn
        if frame.pressed(InputButton.RIGHT):
            self.yaw += turn
        self.yaw = _q(
            self.profile,
            self.yaw % 360.0,
        )
        direction = 0.0
        if frame.pressed(InputButton.UP):
            direction += 1.0
        if frame.pressed(InputButton.DOWN):
            direction -= 1.0
        if direction:
            radians = math.radians(
                self.yaw
            )
            speed = (
                self.tuning["move_speed"]
                * direction
            )
            self.player_x = _q(
                self.profile,
                self.player_x
                + math.sin(radians)
                * speed,
            )
            self.player_z = _q(
                self.profile,
                self.player_z
                + math.cos(radians)
                * speed,
            )

    def _simulate(
        self,
        frame: InputFrame,
    ) -> None:
        self._move(frame)

    def _render(
        self,
    ) -> tuple[
        tuple[AdvancedDrawCommand, ...],
        tuple[tuple[int, int], ...],
        int,
        int,
    ]:
        raise NotImplementedError

    def _after_frame(
        self,
        packet: AdvancedFrame,
    ) -> None:
        del packet

    def _evidence_digest(
        self,
        commands: Sequence[AdvancedDrawCommand],
        cells: Sequence[tuple[int, int]],
        culled: int,
        batches: int,
    ) -> str:
        return _digest(
            {
                "era": self.profile.era.value,
                "tick": self.tick,
                "pipeline": self.spec.pipeline,
                "commands": len(commands),
                "cells": tuple(cells),
                "culled": culled,
                "batches": batches,
            }
        )

    def _export_state(
        self,
    ) -> dict[str, object]:
        return {
            "player_x": self.player_x,
            "player_z": self.player_z,
            "yaw": self.yaw,
        }

    def _import_state(
        self,
        state: Mapping[str, object],
    ) -> None:
        self.player_x = float(
            state["player_x"]
        )
        self.player_z = float(
            state["player_z"]
        )
        self.yaw = float(
            state["yaw"]
        )


class HDRenderGraphMachine(AdvancedMachine):
    """2005-class HDR/deferred engine with explicit render passes."""

    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.HD,
            tuning,
        )
        self.objects = (
            AdvancedObject(
                "hero",
                -2.0,
                0.0,
                14.0,
                "character",
                1,
                True,
                2.0,
            ),
            AdvancedObject(
                "building",
                8.0,
                0.0,
                35.0,
                "building",
                2,
                False,
                8.0,
            ),
            AdvancedObject(
                "vehicle",
                -12.0,
                0.0,
                28.0,
                "vehicle",
                3,
                True,
                3.0,
            ),
        )

    def _render(
        self,
    ) -> tuple[
        tuple[AdvancedDrawCommand, ...],
        tuple[tuple[int, int], ...],
        int,
        int,
    ]:
        rows: list[AdvancedDrawCommand] = []
        visible: list[
            tuple[AdvancedObject, float]
        ] = []
        for obj in self.objects:
            dx = obj.x - self.player_x
            dz = obj.z - self.player_z
            depth = math.hypot(dx, dz)
            if depth > 100.0:
                continue
            visible.append(
                (obj, depth)
            )
        for obj, depth in visible:
            rows.append(
                AdvancedDrawCommand(
                    "gbuffer",
                    obj.object_id,
                    obj.material,
                    0,
                    round(depth, 6),
                    (
                        "gbuffer",
                        obj.material,
                    ),
                    _digest(
                        {
                            "mesh": obj.mesh,
                            "material": obj.material,
                        }
                    ),
                )
            )
        rows.append(
            AdvancedDrawCommand(
                "lighting",
                "__fullscreen__",
                0,
                0,
                0.0,
                (
                    "lighting",
                    min(
                        self.spec.max_lights,
                        int(
                            self.tuning[
                                "light_cutoff"
                            ]
                        ),
                    ),
                ),
                _digest(
                    {
                        "exposure":
                            self.tuning[
                                "exposure"
                            ],
                    }
                ),
            )
        )
        rows.append(
            AdvancedDrawCommand(
                "post",
                "__fullscreen__",
                0,
                0,
                0.0,
                ("tone_map",),
                _digest(
                    {
                        "hdr": True,
                        "exposure":
                            self.tuning[
                                "exposure"
                            ],
                    }
                ),
            )
        )
        rows = rows[
            : self.profile.draw_budget
        ]
        return (
            tuple(rows),
            (),
            0,
            len(
                {
                    command.batch_key
                    for command in rows
                }
            ),
        )


class StreamedOpenWorldMachine(AdvancedMachine):
    """2013-class streamed PBR world with deterministic cell residency."""

    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.OPEN_WORLD,
            tuning,
        )
        self.objects = WORLD_OBJECTS
        self.loaded_cells: tuple[
            tuple[int, int],
            ...,
        ] = ()

    def _cells(
        self,
    ) -> tuple[tuple[int, int], ...]:
        size = self.spec.cell_size
        cx = math.floor(
            self.player_x / size
        )
        cz = math.floor(
            self.player_z / size
        )
        radius = int(
            round(
                self.tuning[
                    "stream_radius"
                ]
            )
        )
        return tuple(
            sorted(
                (
                    (x, z)
                    for z in range(
                        cz - radius,
                        cz + radius + 1,
                    )
                    for x in range(
                        cx - radius,
                        cx + radius + 1,
                    )
                )
            )
        )

    def _render(
        self,
    ) -> tuple[
        tuple[AdvancedDrawCommand, ...],
        tuple[tuple[int, int], ...],
        int,
        int,
    ]:
        cells = self._cells()
        self.loaded_cells = cells
        allowed = set(cells)
        rows: list[AdvancedDrawCommand] = []
        culled = 0
        near = self.tuning["lod_near"]
        mid = self.tuning["lod_mid"]
        size = self.spec.cell_size
        for obj in self.objects:
            cell = (
                math.floor(obj.x / size),
                math.floor(obj.z / size),
            )
            if cell not in allowed:
                culled += 1
                continue
            distance = math.hypot(
                obj.x - self.player_x,
                obj.z - self.player_z,
            )
            lod = (
                0
                if distance <= near
                else 1
                if distance <= mid
                else 2
            )
            rows.append(
                AdvancedDrawCommand(
                    "pbr",
                    obj.object_id,
                    obj.material,
                    lod,
                    round(distance, 6),
                    (
                        "pbr",
                        obj.material,
                        lod,
                    ),
                    _digest(
                        {
                            "mesh": obj.mesh,
                            "lod": lod,
                            "cell": cell,
                        }
                    ),
                )
            )
        rows.sort(
            key=lambda command: (
                command.batch_key,
                command.depth,
                command.object_id,
            )
        )
        return (
            tuple(
                rows[
                    : self.profile.draw_budget
                ]
            ),
            cells,
            culled,
            len(
                {
                    command.batch_key
                    for command in rows
                }
            ),
        )

    def _export_state(
        self,
    ) -> dict[str, object]:
        out = super()._export_state()
        out["loaded_cells"] = (
            self.loaded_cells
        )
        return out

    def _import_state(
        self,
        state: Mapping[str, object],
    ) -> None:
        super()._import_state(state)
        self.loaded_cells = tuple(
            tuple(cell)
            for cell in state[
                "loaded_cells"
            ]
        )


@dataclass(frozen=True, slots=True)
class ECSRecord:
    entity_id: int
    x: float
    z: float
    mesh: str
    material: int
    dynamic: bool


class ModernGpuMachine(AdvancedMachine):
    """2020-class data-oriented ECS with deterministic rollback."""

    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.MODERN,
            tuning,
        )
        self.entities = tuple(
            ECSRecord(
                index + 1,
                obj.x,
                obj.z,
                obj.mesh,
                obj.material,
                obj.dynamic,
            )
            for index, obj
            in enumerate(WORLD_OBJECTS)
        )
        self._rollback: list[
            AdvancedSnapshot
        ] = []

    @property
    def rollback_snapshots(
        self,
    ) -> tuple[AdvancedSnapshot, ...]:
        return tuple(self._rollback)

    def step(
        self,
        frame: InputFrame | None = None,
    ) -> AdvancedFrame:
        packet = super().step(frame)
        self._rollback.append(
            self.snapshot()
        )
        window = int(
            min(
                self.spec.rollback_frames,
                round(
                    self.tuning[
                        "rollback_window"
                    ]
                ),
            )
        )
        if len(self._rollback) > window:
            del self._rollback[
                : len(self._rollback)
                - window
            ]
        return packet

    def rollback_to_tick(
        self,
        tick: int,
    ) -> None:
        for snapshot in reversed(
            self._rollback
        ):
            if snapshot.tick == tick:
                self.restore(snapshot)
                self._rollback = [
                    item
                    for item
                    in self._rollback
                    if item.tick <= tick
                ]
                return
        raise GameEngineLabError(
            f"rollback tick unavailable: {tick}"
        )

    def _render(
        self,
    ) -> tuple[
        tuple[AdvancedDrawCommand, ...],
        tuple[tuple[int, int], ...],
        int,
        int,
    ]:
        distance_limit = self.tuning[
            "cull_distance"
        ]
        visible: list[
            tuple[ECSRecord, float]
        ] = []
        culled = 0
        for entity in self.entities:
            distance = math.hypot(
                entity.x - self.player_x,
                entity.z - self.player_z,
            )
            if distance > distance_limit:
                culled += 1
                continue
            visible.append(
                (entity, distance)
            )
        groups: dict[
            tuple[str, int],
            list[tuple[ECSRecord, float]],
        ] = {}
        for entity, distance in visible:
            groups.setdefault(
                (
                    entity.mesh,
                    entity.material,
                ),
                [],
            ).append(
                (entity, distance)
            )
        rows: list[
            AdvancedDrawCommand
        ] = []
        meshlet_size = int(
            round(
                self.tuning[
                    "meshlet_size"
                ]
            )
        )
        for group_key in sorted(groups):
            members = sorted(
                groups[group_key],
                key=lambda item:
                    item[0].entity_id,
            )
            for offset in range(
                0,
                len(members),
                max(1, meshlet_size // 16),
            ):
                chunk = members[
                    offset:
                    offset
                    + max(
                        1,
                        meshlet_size // 16,
                    )
                ]
                ids = tuple(
                    member.entity_id
                    for member, _
                    in chunk
                )
                depth = sum(
                    distance
                    for _, distance
                    in chunk
                ) / len(chunk)
                rows.append(
                    AdvancedDrawCommand(
                        "gpu_indirect",
                        "batch:"
                        + ",".join(
                            str(value)
                            for value in ids
                        ),
                        group_key[1],
                        0,
                        round(depth, 6),
                        (
                            "indirect",
                            group_key[0],
                            group_key[1],
                            len(ids),
                        ),
                        _digest(
                            {
                                "entities": ids,
                                "mesh":
                                    group_key[0],
                            }
                        ),
                    )
                )
        rows.sort(
            key=lambda command: (
                command.batch_key,
                command.object_id,
            )
        )
        size = self.spec.cell_size
        cells = tuple(
            sorted(
                {
                    (
                        math.floor(
                            entity.x / size
                        ),
                        math.floor(
                            entity.z / size
                        ),
                    )
                    for entity, _
                    in visible
                }
            )
        )
        return (
            tuple(
                rows[
                    : self.profile.draw_budget
                ]
            ),
            cells,
            culled,
            len(rows),
        )

    def _export_state(
        self,
    ) -> dict[str, object]:
        # Rollback history is recovery metadata, not simulation authority.
        # Keeping it out of the fingerprint makes restore identity stable.
        return super()._export_state()

    def _import_state(
        self,
        state: Mapping[str, object],
    ) -> None:
        super()._import_state(state)
        # Rollback history is transport metadata, not simulation authority.
        # Restoring a state intentionally starts a new bounded lineage.
        self._rollback = []


@dataclass(frozen=True, slots=True)
class HybridPolicy:
    weights: tuple[float, ...]
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise GameEngineLabError(
                "unsupported hybrid policy version"
            )
        if not 1 <= len(self.weights) <= 16:
            raise GameEngineLabError(
                "hybrid policy weight count outside [1, 16]"
            )
        for weight in self.weights:
            if (
                not math.isfinite(weight)
                or not -1.0 <= weight <= 1.0
            ):
                raise GameEngineLabError(
                    "hybrid policy weight outside [-1, 1]"
                )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "weights": self.weights,
            }
        )


DEFAULT_HYBRID_POLICY = HybridPolicy(
    (
        0.15,
        -0.05,
        0.20,
        0.10,
        -0.10,
        0.08,
    )
)


def compile_hybrid_policy(
    tree: VirtualFileTree,
) -> HybridPolicy:
    try:
        payload = json.loads(
            tree.read(
                "engine/hybrid_policy.json"
            )
        )
    except (
        GameEngineLabError,
        json.JSONDecodeError,
    ) as exc:
        raise GameEngineLabError(
            "hybrid policy missing or invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise GameEngineLabError(
            "hybrid policy must be object"
        )
    weights = payload.get("weights")
    if (
        not isinstance(weights, list)
        or any(
            isinstance(value, bool)
            or not isinstance(
                value,
                (int, float),
            )
            for value in weights
        )
    ):
        raise GameEngineLabError(
            "hybrid policy weights invalid"
        )
    return HybridPolicy(
        tuple(
            float(value)
            for value in weights
        ),
        int(payload.get("version", 0)),
    )


class NextHybridMachine(AdvancedMachine):
    """Next-era multi-rate deterministic analytic/learned hybrid."""

    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
        policy: HybridPolicy | None = None,
    ) -> None:
        super().__init__(
            EngineEra.NEXT,
            tuning,
        )
        self.policy = (
            policy
            or DEFAULT_HYBRID_POLICY
        )
        self.policy_updates = 0
        self.simulation_phase = 0
        self.confidence = 1.0

    def _simulate(
        self,
        frame: InputFrame,
    ) -> None:
        substeps = int(
            round(
                self.tuning[
                    "simulation_substeps"
                ]
            )
        )
        original_speed = self.tuning[
            "move_speed"
        ]
        per_step = (
            original_speed
            / max(1, substeps)
        )
        for _ in range(substeps):
            previous = self.tuning[
                "move_speed"
            ]
            self.tuning[
                "move_speed"
            ] = per_step
            self._move(frame)
            self.tuning[
                "move_speed"
            ] = previous
            self.simulation_phase += 1
        observation = (
            math.sin(
                math.radians(
                    self.yaw
                )
            )
            + self.player_x * 0.001
            + self.player_z * 0.001
        )
        self.confidence = max(
            self.tuning[
                "confidence_floor"
            ],
            min(
                1.0,
                1.0
                - abs(observation)
                * 0.05,
            ),
        )
        rate = self.tuning[
            "adaptation_rate"
        ]
        if rate > 0:
            next_weights = []
            for index, weight in enumerate(
                self.policy.weights
            ):
                direction = (
                    1.0
                    if (
                        index
                        + self.tick
                    )
                    % 2
                    == 0
                    else -1.0
                )
                delta = (
                    observation
                    * rate
                    * direction
                )
                next_weights.append(
                    max(
                        -1.0,
                        min(
                            1.0,
                            round(
                                weight
                                + delta,
                                12,
                            ),
                        ),
                    )
                )
            self.policy = HybridPolicy(
                tuple(next_weights)
            )
            self.policy_updates += 1

    def _render(
        self,
    ) -> tuple[
        tuple[AdvancedDrawCommand, ...],
        tuple[tuple[int, int], ...],
        int,
        int,
    ]:
        distance_limit = self.tuning[
            "cull_distance"
        ]
        visible: list[
            tuple[AdvancedObject, float]
        ] = []
        culled = 0
        for obj in WORLD_OBJECTS:
            distance = math.hypot(
                obj.x - self.player_x,
                obj.z - self.player_z,
            )
            if distance > distance_limit:
                culled += 1
                continue
            visible.append(
                (obj, distance)
            )
        rows: list[
            AdvancedDrawCommand
        ] = []
        groups: dict[
            tuple[str, int],
            list[AdvancedObject],
        ] = {}
        for obj, _ in visible:
            groups.setdefault(
                (
                    obj.mesh,
                    obj.material,
                ),
                [],
            ).append(obj)
        for key in sorted(groups):
            members = tuple(
                sorted(
                    groups[key],
                    key=lambda item:
                        item.object_id,
                )
            )
            rows.append(
                AdvancedDrawCommand(
                    "hybrid_indirect",
                    "cluster:"
                    + key[0]
                    + ":"
                    + str(key[1]),
                    key[1],
                    0,
                    round(
                        sum(
                            math.hypot(
                                obj.x
                                - self.player_x,
                                obj.z
                                - self.player_z,
                            )
                            for obj in members
                        )
                        / len(members),
                        6,
                    ),
                    (
                        "hybrid",
                        key[0],
                        key[1],
                        len(members),
                        self.policy.digest[
                            :12
                        ],
                    ),
                    _digest(
                        {
                            "policy":
                                self.policy.digest,
                            "confidence":
                                round(
                                    self.confidence,
                                    12,
                                ),
                            "entities": tuple(
                                obj.object_id
                                for obj
                                in members
                            ),
                        }
                    ),
                )
            )
        size = self.spec.cell_size
        cells = tuple(
            sorted(
                {
                    (
                        math.floor(
                            obj.x / size
                        ),
                        math.floor(
                            obj.z / size
                        ),
                    )
                    for obj, _
                    in visible
                }
            )
        )
        return (
            tuple(
                rows[
                    : self.profile.draw_budget
                ]
            ),
            cells,
            culled,
            len(rows),
        )

    def _export_state(
        self,
    ) -> dict[str, object]:
        out = super()._export_state()
        out.update(
            {
                "confidence":
                    self.confidence,
                "policy_digest":
                    self.policy.digest,
                "policy_updates":
                    self.policy_updates,
                "policy_weights":
                    self.policy.weights,
                "simulation_phase":
                    self.simulation_phase,
            }
        )
        return out

    def _import_state(
        self,
        state: Mapping[str, object],
    ) -> None:
        super()._import_state(state)
        self.confidence = float(
            state["confidence"]
        )
        self.policy_updates = int(
            state["policy_updates"]
        )
        self.policy = HybridPolicy(
            tuple(
                float(value)
                for value
                in state[
                    "policy_weights"
                ]
            )
        )
        if (
            self.policy.digest
            != state[
                "policy_digest"
            ]
        ):
            raise GameEngineLabError(
                "hybrid policy digest mismatch"
            )
        self.simulation_phase = int(
            state["simulation_phase"]
        )


def create_advanced_machine(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
    *,
    policy: HybridPolicy | None = None,
) -> AdvancedMachine:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    if key is EngineEra.HD:
        return HDRenderGraphMachine(
            tuning
        )
    if key is EngineEra.OPEN_WORLD:
        return StreamedOpenWorldMachine(
            tuning
        )
    if key is EngineEra.MODERN:
        return ModernGpuMachine(
            tuning
        )
    if key is EngineEra.NEXT:
        return NextHybridMachine(
            tuning,
            policy,
        )
    raise GameEngineLabError(
        f"advanced runtime unavailable for {key.value}"
    )


def create_advanced_machine_from_tree(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> AdvancedMachine:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    policy = (
        compile_hybrid_policy(tree)
        if key is EngineEra.NEXT
        else None
    )
    return create_advanced_machine(
        key,
        compile_advanced_tuning(
            key,
            tree,
        ),
        policy=policy,
    )


def build_advanced_engine_tree(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> VirtualFileTree:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    spec = advanced_hardware(key)
    profile = engine_era_profile(key)
    base = build_engine_file_tree(
        key,
        gameplay_dialect,
    )
    files: dict[str, str] = {
        "engine/advanced_pipeline.json":
            json.dumps(
                {
                    "pipeline":
                        spec.pipeline,
                    "viewport": [
                        spec.width,
                        spec.height,
                    ],
                    "render_targets":
                        spec.render_targets,
                    "max_lights":
                        spec.max_lights,
                    "job_lanes":
                        spec.job_lanes,
                    "gpu_driven":
                        spec.gpu_driven,
                    "draw_budget":
                        profile.draw_budget,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        "engine/streaming.json":
            json.dumps(
                {
                    "enabled":
                        spec.streaming,
                    "cell_size":
                        spec.cell_size,
                    "stable_cell_order":
                        True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        "engine/advanced_tuning.json":
            json.dumps(
                default_advanced_tuning(
                    key
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        "assets/world_cells.json":
            json.dumps(
                {
                    "objects": [
                        {
                            "id":
                                obj.object_id,
                            "x": obj.x,
                            "z": obj.z,
                            "mesh":
                                obj.mesh,
                            "material":
                                obj.material,
                            "dynamic":
                                obj.dynamic,
                        }
                        for obj
                        in WORLD_OBJECTS
                    ]
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        "engine/advanced_runtime.py":
            (
                f'ENGINE_ERA = "{key.value}"\n'
                f'MACHINE = "{create_advanced_machine(key).__class__.__name__}"\n'
            ),
    }
    if key in {
        EngineEra.MODERN,
        EngineEra.NEXT,
    }:
        files["engine/ecs_schema.json"] = (
            json.dumps(
                {
                    "schema_version": 1,
                    "components": [
                        "transform",
                        "mesh",
                        "material",
                        "dynamic",
                    ],
                    "entity_identity":
                        "stable_integer",
                    "iteration":
                        "entity_id_ascending",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        files[
            "engine/rollback.json"
        ] = (
            json.dumps(
                {
                    "enabled": True,
                    "max_frames":
                        spec.rollback_frames,
                    "snapshot_digest":
                        "sha256",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    if key is EngineEra.NEXT:
        files[
            "engine/hybrid_policy.json"
        ] = (
            json.dumps(
                {
                    "version":
                        DEFAULT_HYBRID_POLICY.version,
                    "weights":
                        list(
                            DEFAULT_HYBRID_POLICY.weights
                        ),
                    "bounded":
                        [-1.0, 1.0],
                    "code_mutation":
                        False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    patches = [
        SandboxPatch(
            path,
            content,
        )
        for path, content
        in files.items()
    ]
    return base.apply(patches)


@dataclass(frozen=True, slots=True)
class AdvancedProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AdvancedQualityReport:
    era: EngineEra
    probes: tuple[AdvancedProbe, ...]

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


class AdvancedEngineAdversary:
    """Era-specific replay, budget, rollback and policy attack suite."""

    def _script(
        self,
        length: int = 120,
    ) -> tuple[InputFrame, ...]:
        frames = []
        for tick in range(length):
            buttons = InputButton.NONE
            if tick % 32 < 20:
                buttons |= InputButton.UP
            if tick % 47 < 10:
                buttons |= InputButton.RIGHT
            if 70 <= tick < 80:
                buttons |= InputButton.LEFT
            frames.append(
                InputFrame(
                    tick,
                    buttons,
                )
            )
        return tuple(frames)

    def evaluate(
        self,
        era: EngineEra | str,
        tree: VirtualFileTree | None = None,
    ) -> AdvancedQualityReport:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        spec = advanced_hardware(key)
        active_tree = (
            tree
            or build_advanced_engine_tree(
                key,
                "action_adventure",
            )
        )
        required = {
            "engine/advanced_pipeline.json",
            "engine/streaming.json",
            "engine/advanced_tuning.json",
            "assets/world_cells.json",
            "engine/advanced_runtime.py",
        }
        if key in {
            EngineEra.MODERN,
            EngineEra.NEXT,
        }:
            required |= {
                "engine/ecs_schema.json",
                "engine/rollback.json",
            }
        if key is EngineEra.NEXT:
            required.add(
                "engine/hybrid_policy.json"
            )
        tree_ok = required <= set(
            active_tree.files
        )
        probes: list[
            AdvancedProbe
        ] = [
            AdvancedProbe(
                "file_tree",
                tree_ok,
                (
                    "advanced runtime tree present"
                    if tree_ok
                    else "advanced runtime files missing"
                ),
            )
        ]
        try:
            tuning = compile_advanced_tuning(
                key,
                active_tree,
            )
            policy = (
                compile_hybrid_policy(
                    active_tree
                )
                if key is EngineEra.NEXT
                else None
            )
        except GameEngineLabError as exc:
            tuning = None
            policy = None
            detail = str(exc)
        else:
            detail = (
                "bounded tuning and policy compiled"
                if key is EngineEra.NEXT
                else "bounded tuning compiled"
            )
        probes.append(
            AdvancedProbe(
                "compile",
                tuning is not None,
                detail,
            )
        )
        if (
            not tree_ok
            or tuning is None
        ):
            probes.extend(
                AdvancedProbe(
                    name,
                    False,
                    "runtime not compilable",
                )
                for name in (
                    "determinism",
                    "draw_budget",
                    "snapshot",
                    "pipeline",
                    "era_contract",
                )
            )
            return AdvancedQualityReport(
                key,
                tuple(probes),
            )

        script = self._script()
        first = create_advanced_machine(
            key,
            tuning,
            policy=policy,
        )
        second = create_advanced_machine(
            key,
            tuning,
            policy=policy,
        )
        first_packets = first.run(
            script
        )
        second_packets = second.run(
            script
        )
        probes.append(
            AdvancedProbe(
                "determinism",
                (
                    first.fingerprint()
                    == second.fingerprint()
                    and first_packets
                    == second_packets
                ),
                "identical input replay",
            )
        )
        probes.append(
            AdvancedProbe(
                "draw_budget",
                all(
                    len(packet.commands)
                    <= first.profile.draw_budget
                    for packet
                    in first_packets
                ),
                "bounded command buffers",
            )
        )

        snap_machine = create_advanced_machine(
            key,
            tuning,
            policy=policy,
        )
        snap_machine.run(
            self._script(24)
        )
        snapshot = snap_machine.snapshot()
        before = snap_machine.fingerprint()
        snap_machine.run(
            tuple(
                InputFrame(
                    24 + index,
                    InputButton.LEFT,
                )
                for index in range(8)
            )
        )
        snap_machine.restore(
            snapshot
        )
        probes.append(
            AdvancedProbe(
                "snapshot",
                snap_machine.fingerprint()
                == before,
                "state digest roundtrip",
            )
        )

        if key is EngineEra.HD:
            pass_names = {
                command.pass_name
                for command
                in first_packets[0].commands
            }
            pipeline_ok = {
                "gbuffer",
                "lighting",
                "post",
            } <= pass_names
            era_ok = (
                not spec.streaming
                and not spec.gpu_driven
            )
        elif key is EngineEra.OPEN_WORLD:
            pipeline_ok = all(
                tuple(
                    sorted(
                        packet.loaded_cells
                    )
                )
                == packet.loaded_cells
                and bool(
                    packet.loaded_cells
                )
                for packet
                in first_packets
            )
            era_ok = (
                spec.streaming
                and not spec.gpu_driven
            )
        elif key is EngineEra.MODERN:
            modern = first
            assert isinstance(
                modern,
                ModernGpuMachine,
            )
            rollback_ticks = tuple(
                snapshot.tick
                for snapshot
                in modern.rollback_snapshots
            )
            pipeline_ok = (
                bool(rollback_ticks)
                and len(
                    rollback_ticks
                )
                <= int(
                    tuning[
                        "rollback_window"
                    ]
                )
                and all(
                    command.pass_name
                    == "gpu_indirect"
                    for packet
                    in first_packets
                    for command
                    in packet.commands
                )
            )
            era_ok = (
                spec.streaming
                and spec.gpu_driven
                and spec.rollback_frames > 0
            )
        else:
            hybrid = first
            assert isinstance(
                hybrid,
                NextHybridMachine,
            )
            pipeline_ok = (
                hybrid.policy_updates
                == len(script)
                and hybrid.confidence
                >= tuning[
                    "confidence_floor"
                ]
                and all(
                    command.pass_name
                    == "hybrid_indirect"
                    for packet
                    in first_packets
                    for command
                    in packet.commands
                )
            )
            era_ok = (
                spec.gpu_driven
                and spec.learned_components
                and policy is not None
                and 1
                <= len(
                    policy.weights
                )
                <= 16
            )
        probes.append(
            AdvancedProbe(
                "pipeline",
                pipeline_ok,
                spec.pipeline,
            )
        )
        probes.append(
            AdvancedProbe(
                "era_contract",
                era_ok,
                (
                    "era-specific architecture enforced"
                ),
            )
        )
        return AdvancedQualityReport(
            key,
            tuple(probes),
        )


@dataclass(frozen=True, slots=True)
class AdvancedEngineSandbox:
    era: EngineEra
    tree: VirtualFileTree
    gameplay_dialect: str | None = None

    def apply(
        self,
        patches: Iterable[SandboxPatch],
    ) -> "AdvancedEngineSandbox":
        return AdvancedEngineSandbox(
            self.era,
            self.tree.apply(patches),
            self.gameplay_dialect,
        )

    def machine(
        self,
    ) -> AdvancedMachine:
        return create_advanced_machine_from_tree(
            self.era,
            self.tree,
        )


@dataclass(frozen=True, slots=True)
class AdvancedImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdvancedImprovementResult:
    sandbox: AdvancedEngineSandbox
    report: AdvancedQualityReport
    rounds: tuple[
        AdvancedImprovementRound,
        ...,
    ]
    promoted: bool


class AdvancedEngineLab:
    """Safe compiler/evaluator loop for HD-through-next sandbox trees."""

    def __init__(
        self,
        adversary: AdvancedEngineAdversary | None = None,
    ) -> None:
        self.adversary = (
            adversary
            or AdvancedEngineAdversary()
        )

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> AdvancedEngineSandbox:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        advanced_hardware(key)
        return AdvancedEngineSandbox(
            key,
            build_advanced_engine_tree(
                key,
                gameplay_dialect,
            ),
            gameplay_dialect,
        )

    def evaluate(
        self,
        sandbox: AdvancedEngineSandbox,
    ) -> AdvancedQualityReport:
        return self.adversary.evaluate(
            sandbox.era,
            sandbox.tree,
        )

    def canonical_repair(
        self,
        sandbox: AdvancedEngineSandbox,
        report: AdvancedQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = build_advanced_engine_tree(
            sandbox.era,
            sandbox.gameplay_dialect,
        )
        protected = {
            "engine/advanced_pipeline.json",
            "engine/streaming.json",
            "engine/advanced_tuning.json",
            "assets/world_cells.json",
            "engine/advanced_runtime.py",
        }
        if sandbox.era in {
            EngineEra.MODERN,
            EngineEra.NEXT,
        }:
            protected |= {
                "engine/ecs_schema.json",
                "engine/rollback.json",
            }
        if sandbox.era is EngineEra.NEXT:
            protected.add(
                "engine/hybrid_policy.json"
            )
        patches: list[
            SandboxPatch
        ] = []
        for path in sorted(protected):
            wanted = canonical.read(
                path
            )
            try:
                current = (
                    sandbox.tree.read(
                        path
                    )
                )
            except GameEngineLabError:
                current = None
            if current != wanted:
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

    def adversarial_improve(
        self,
        sandbox: AdvancedEngineSandbox,
        *,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> AdvancedImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError(
                "target must be within (0, 1]"
            )
        if (
            not isinstance(
                max_rounds,
                int,
            )
            or not 1
            <= max_rounds
            <= 32
        ):
            raise GameEngineLabError(
                "max_rounds must be within [1, 32]"
            )
        current = sandbox
        report = self.evaluate(
            current
        )
        rounds: list[
            AdvancedImprovementRound
        ] = []
        if (
            report.passed
            and report.score >= target
        ):
            return AdvancedImprovementResult(
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
                strategy(
                    current,
                    report,
                )
            )
            if not patches:
                break
            candidate = current.apply(
                patches
            )
            next_report = self.evaluate(
                candidate
            )
            accepted = (
                candidate.tree.digest
                != current.tree.digest
                and next_report.score
                >= report.score
                and len(
                    next_report.failed
                )
                <= len(
                    report.failed
                )
            )
            rounds.append(
                AdvancedImprovementRound(
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
                and report.score
                >= target
            ):
                break
        return AdvancedImprovementResult(
            current,
            report,
            tuple(rounds),
            (
                report.passed
                and report.score >= target
            ),
        )
