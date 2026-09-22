"""Executable HD-to-next engine eras for the Jeeves engine laboratory.

These runtimes model the architectural transitions that matter to Jeeves:
deferred/HDR rendering, streamed worlds, data-oriented ECS execution,
deterministic rollback, GPU-style command preparation, and a bounded adaptive
policy plane.  Sandbox data is compiled and validated; sandbox Python is never
executed as authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
    VirtualFileTree,
    build_engine_file_tree,
    engine_era_profile,
)
from .game_engine_legacy import InputButton, InputFrame
from .game_engine_render_graph import (
    RenderGraphEvidence,
    execute_render_graph,
    render_graph_spec,
)

MODERN_ERAS = (
    EngineEra.HD,
    EngineEra.OPEN_WORLD,
    EngineEra.MODERN,
    EngineEra.NEXT,
)


@dataclass(frozen=True, slots=True)
class ModernHardwareSpec:
    era: EngineEra
    viewport: tuple[int, int]
    render_passes: tuple[str, ...]
    job_lanes: int
    max_stream_cells: int
    rollback_capable: bool
    gpu_driven: bool
    ray_queries: bool
    adaptive_policy: bool


MODERN_HARDWARE: Mapping[EngineEra, ModernHardwareSpec] = {
    EngineEra.HD: ModernHardwareSpec(
        EngineEra.HD,
        (1280, 720),
        ("depth_prepass", "gbuffer", "lighting", "transparent", "post"),
        4,
        1,
        False,
        False,
        False,
        False,
    ),
    EngineEra.OPEN_WORLD: ModernHardwareSpec(
        EngineEra.OPEN_WORLD,
        (1920, 1080),
        ("shadow", "depth_prepass", "gbuffer", "lighting", "transparent", "post"),
        8,
        49,
        False,
        False,
        False,
        False,
    ),
    EngineEra.MODERN: ModernHardwareSpec(
        EngineEra.MODERN,
        (2560, 1440),
        ("cull", "virtual_geometry", "gbuffer", "ray_queries", "lighting", "post"),
        16,
        121,
        True,
        True,
        True,
        False,
    ),
    EngineEra.NEXT: ModernHardwareSpec(
        EngineEra.NEXT,
        (3840, 2160),
        (
            "cull",
            "virtual_geometry",
            "adaptive_material",
            "ray_queries",
            "lighting",
            "post",
        ),
        32,
        169,
        True,
        True,
        True,
        True,
    ),
}


MODERN_TUNING: Mapping[EngineEra, Mapping[str, tuple[float, float, float]]] = {
    EngineEra.HD: {
        "move_speed": (0.75, 0.1, 2.0),
        "drag": (0.92, 0.70, 0.995),
        "lod_distance": (80.0, 20.0, 200.0),
    },
    EngineEra.OPEN_WORLD: {
        "move_speed": (0.90, 0.1, 2.5),
        "drag": (0.94, 0.70, 0.998),
        "stream_radius": (2.0, 1.0, 3.0),
        "lod_distance": (160.0, 40.0, 400.0),
    },
    EngineEra.MODERN: {
        "move_speed": (1.10, 0.1, 3.0),
        "drag": (0.96, 0.75, 0.999),
        "stream_radius": (3.0, 1.0, 5.0),
        "lod_distance": (260.0, 60.0, 600.0),
        "rollback_window": (120.0, 8.0, 240.0),
    },
    EngineEra.NEXT: {
        "move_speed": (1.20, 0.1, 3.5),
        "drag": (0.97, 0.75, 0.9995),
        "stream_radius": (4.0, 1.0, 6.0),
        "lod_distance": (360.0, 80.0, 900.0),
        "rollback_window": (180.0, 8.0, 360.0),
        "adaptive_gain": (0.12, 0.0, 0.35),
    },
}


def modern_hardware(era: EngineEra | str) -> ModernHardwareSpec:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    try:
        return MODERN_HARDWARE[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"modern runtime unavailable for {key.value}"
        ) from exc


def default_modern_tuning(era: EngineEra | str) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    modern_hardware(key)
    return {
        name: values[0]
        for name, values in MODERN_TUNING[key].items()
    }


def normalize_modern_tuning(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    bounds = MODERN_TUNING.get(key)
    if bounds is None:
        raise GameEngineLabError(
            f"modern runtime unavailable for {key.value}"
        )
    source = default_modern_tuning(key) if tuning is None else dict(tuning)
    if set(source) != set(bounds):
        raise GameEngineLabError("modern tuning keys mismatch")
    normalized: dict[str, float] = {}
    for name, (_, low, high) in bounds.items():
        raw = source[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise GameEngineLabError(
                f"modern tuning {name} must be numeric"
            )
        value = float(raw)
        if not math.isfinite(value) or not low <= value <= high:
            raise GameEngineLabError(
                f"modern tuning {name} outside [{low}, {high}]"
            )
        normalized[name] = value
    return normalized


def compile_modern_tuning(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> dict[str, float]:
    try:
        payload = json.loads(tree.read("engine/modern_tuning.json"))
    except (GameEngineLabError, json.JSONDecodeError) as exc:
        raise GameEngineLabError("modern tuning missing or invalid") from exc
    if not isinstance(payload, dict):
        raise GameEngineLabError("modern tuning must be a JSON object")
    return normalize_modern_tuning(era, payload)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class AdaptivePolicy:
    """Bounded deterministic policy; not executable model code."""

    coefficients: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if len(self.coefficients) != 4:
            raise GameEngineLabError("adaptive policy requires four coefficients")
        for value in self.coefficients:
            if not math.isfinite(value) or not -1.0 <= value <= 1.0:
                raise GameEngineLabError(
                    "adaptive policy coefficients must be finite within [-1, 1]"
                )

    def evaluate(self, features: tuple[float, float, float, float]) -> float:
        total = sum(
            coefficient * feature
            for coefficient, feature in zip(self.coefficients, features)
        )
        return math.tanh(total)


DEFAULT_ADAPTIVE_POLICY = AdaptivePolicy((0.25, -0.10, 0.15, 0.05))


def compile_adaptive_policy(tree: VirtualFileTree) -> AdaptivePolicy:
    try:
        payload = json.loads(tree.read("engine/adaptive_policy.json"))
    except (GameEngineLabError, json.JSONDecodeError) as exc:
        raise GameEngineLabError("adaptive policy missing or invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise GameEngineLabError("unsupported adaptive policy schema")
    raw = payload.get("coefficients")
    if not isinstance(raw, list) or len(raw) != 4:
        raise GameEngineLabError("adaptive policy coefficients malformed")
    try:
        values = tuple(float(value) for value in raw)
    except (TypeError, ValueError) as exc:
        raise GameEngineLabError("adaptive policy coefficients malformed") from exc
    return AdaptivePolicy(values)


@dataclass(slots=True)
class EcsEntity:
    entity_id: int
    cell_x: int
    cell_z: int
    x: float
    z: float
    vx: float
    vz: float
    material: int
    mesh: int
    active: bool = True


@dataclass(frozen=True, slots=True)
class ModernSnapshot:
    era: EngineEra
    tick: int
    state: tuple[tuple[str, object], ...]
    digest: str


@dataclass(frozen=True, slots=True)
class RenderInstance:
    entity_id: int
    material: int
    mesh: int
    distance: float
    lod: int


@dataclass(frozen=True, slots=True)
class ModernFrame:
    era: EngineEra
    tick: int
    passes: tuple[str, ...]
    instances: tuple[RenderInstance, ...]
    loaded_cells: tuple[tuple[int, int], ...]
    jobs: tuple[str, ...]
    state_digest: str
    rollback_depth: int
    render_graph_digest: str = ""
    final_image_digest: str = ""


class ModernMachine:
    CELL_SIZE = 64.0

    def __init__(
        self,
        era: EngineEra,
        tuning: Mapping[str, object] | None = None,
        policy: AdaptivePolicy | None = None,
    ) -> None:
        if era not in MODERN_ERAS:
            raise GameEngineLabError(
                f"modern machine unavailable for {era.value}"
            )
        self.profile = engine_era_profile(era)
        self.spec = modern_hardware(era)
        self.tuning = normalize_modern_tuning(era, tuning)
        if self.spec.adaptive_policy:
            self.policy = policy or DEFAULT_ADAPTIVE_POLICY
        elif policy is not None:
            raise GameEngineLabError("adaptive policy unsupported for this era")
        else:
            self.policy = None
        self.tick = 0
        self.player_x = 0.0
        self.player_z = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.entities: dict[int, EcsEntity] = {}
        self.loaded_cells: set[tuple[int, int]] = set()
        self._rollback: list[ModernSnapshot] = []
        self._seed_world()
        self._update_streaming()

    def _seed_world(self) -> None:
        entity_id = 1
        extent = 1 if self.profile.era is EngineEra.HD else 6
        for cell_z in range(-extent, extent + 1):
            for cell_x in range(-extent, extent + 1):
                for local in range(4):
                    if len(self.entities) >= min(self.profile.entity_budget, 512):
                        return
                    self.entities[entity_id] = EcsEntity(
                        entity_id,
                        cell_x,
                        cell_z,
                        cell_x * self.CELL_SIZE + 8 + local * 11,
                        cell_z * self.CELL_SIZE + 8 + local * 7,
                        0.02 * ((entity_id % 3) - 1),
                        0.02 * ((entity_id % 5) - 2),
                        entity_id % 7,
                        entity_id % 5,
                    )
                    entity_id += 1

    def _stream_radius(self) -> int:
        if self.profile.era is EngineEra.HD:
            return 0
        return int(round(self.tuning["stream_radius"]))

    def _update_streaming(self) -> None:
        cx = math.floor(self.player_x / self.CELL_SIZE)
        cz = math.floor(self.player_z / self.CELL_SIZE)
        radius = self._stream_radius()
        cells = [
            (x, z)
            for z in range(cz - radius, cz + radius + 1)
            for x in range(cx - radius, cx + radius + 1)
        ]
        cells.sort(
            key=lambda cell: (
                abs(cell[0] - cx) + abs(cell[1] - cz),
                cell[1],
                cell[0],
            )
        )
        self.loaded_cells = set(cells[: self.spec.max_stream_cells])

    def _capture_rollback(self) -> None:
        if not self.spec.rollback_capable:
            return
        window = int(round(self.tuning["rollback_window"]))
        self._rollback.append(self.snapshot())
        if len(self._rollback) > window:
            del self._rollback[: len(self._rollback) - window]

    def step(self, frame: InputFrame | None = None) -> ModernFrame:
        frame = InputFrame(self.tick) if frame is None else frame
        if frame.tick != self.tick:
            raise GameEngineLabError(
                f"input tick mismatch: expected {self.tick}, got {frame.tick}"
            )
        self._capture_rollback()
        jobs = self._execute_jobs(frame)
        instances = self._prepare_render_instances()
        render_evidence = (
            self.execute_render_graph(
                instances
            )
        )
        packet = ModernFrame(
            self.profile.era,
            self.tick,
            self.spec.render_passes,
            instances,
            tuple(sorted(self.loaded_cells)),
            jobs,
            self.fingerprint(),
            len(self._rollback),
            render_evidence.graph_digest,
            render_evidence.final_digest,
        )
        self.tick += 1
        return packet

    def run(self, frames: Iterable[InputFrame]) -> tuple[ModernFrame, ...]:
        return tuple(self.step(frame) for frame in frames)

    def execute_render_graph(
        self,
        instances: tuple[
            RenderInstance,
            ...,
        ] | None = None,
    ) -> RenderGraphEvidence:
        """Execute the era's bounded resource graph for current frame state."""
        active_instances = (
            self._prepare_render_instances()
            if instances is None
            else instances
        )
        instance_payload = tuple(
            (
                item.entity_id,
                item.material,
                item.mesh,
                item.distance,
                item.lod,
            )
            for item
            in active_instances
        )
        frame_constants = {
            "tick": self.tick,
            "viewport":
                self.spec.viewport,
            "player": (
                round(
                    self.player_x,
                    12,
                ),
                round(
                    self.player_z,
                    12,
                ),
            ),
            "velocity": (
                round(
                    self.vx,
                    12,
                ),
                round(
                    self.vz,
                    12,
                ),
            ),
            "gpu_driven":
                self.spec.gpu_driven,
            "ray_queries":
                self.spec.ray_queries,
            "adaptive_policy":
                self.spec.adaptive_policy,
        }
        streaming_state = tuple(
            sorted(
                self.loaded_cells
            )
        )
        return execute_render_graph(
            self.profile.era,
            instances=
                instance_payload,
            frame_constants=
                frame_constants,
            streaming_state=
                streaming_state,
        )

    def _execute_jobs(self, frame: InputFrame) -> tuple[str, ...]:
        jobs = (
            "input",
            "adaptive_policy" if self.spec.adaptive_policy else "control",
            "physics",
            "streaming",
            "visibility",
            "render_prepare",
        )
        self._apply_input(frame)
        self._integrate_entities()
        self._update_streaming()
        return jobs

    def _apply_input(self, frame: InputFrame) -> None:
        ax = 0.0
        az = 0.0
        if frame.pressed(InputButton.LEFT):
            ax -= self.tuning["move_speed"]
        if frame.pressed(InputButton.RIGHT):
            ax += self.tuning["move_speed"]
        if frame.pressed(InputButton.UP):
            az += self.tuning["move_speed"]
        if frame.pressed(InputButton.DOWN):
            az -= self.tuning["move_speed"]
        if self.policy is not None:
            features = (
                max(-1.0, min(1.0, self.vx)),
                max(-1.0, min(1.0, self.vz)),
                1.0 if frame.pressed(InputButton.FIRE) else 0.0,
                (self.tick % 120) / 120.0,
            )
            adjustment = self.policy.evaluate(features) * self.tuning["adaptive_gain"]
            ax += adjustment
            az -= adjustment * 0.5
        drag = self.tuning["drag"]
        self.vx = (self.vx + ax / self.profile.tick_hz) * drag
        self.vz = (self.vz + az / self.profile.tick_hz) * drag
        self.player_x += self.vx
        self.player_z += self.vz

    def _integrate_entities(self) -> None:
        # Stable archetype/entity ordering models deterministic job reduction.
        for entity_id in sorted(self.entities):
            entity = self.entities[entity_id]
            if not entity.active:
                continue
            entity.x += entity.vx
            entity.z += entity.vz
            entity.cell_x = math.floor(entity.x / self.CELL_SIZE)
            entity.cell_z = math.floor(entity.z / self.CELL_SIZE)

    def _prepare_render_instances(self) -> tuple[RenderInstance, ...]:
        visible: list[RenderInstance] = []
        lod_distance = self.tuning["lod_distance"]
        for entity_id in sorted(self.entities):
            entity = self.entities[entity_id]
            if not entity.active or (entity.cell_x, entity.cell_z) not in self.loaded_cells:
                continue
            dx = entity.x - self.player_x
            dz = entity.z - self.player_z
            distance = math.hypot(dx, dz)
            if distance > lod_distance:
                continue
            lod = 0 if distance < lod_distance * 0.33 else 1 if distance < lod_distance * 0.66 else 2
            visible.append(
                RenderInstance(
                    entity.entity_id,
                    entity.material,
                    entity.mesh,
                    round(distance, 6),
                    lod,
                )
            )
        if self.spec.gpu_driven:
            visible.sort(
                key=lambda row: (
                    row.material,
                    row.mesh,
                    row.lod,
                    row.entity_id,
                )
            )
        else:
            visible.sort(
                key=lambda row: (
                    row.distance,
                    row.material,
                    row.entity_id,
                )
            )
        return tuple(visible[: self.profile.draw_budget])

    def snapshot(self) -> ModernSnapshot:
        state = tuple(sorted(self._export_state().items()))
        payload = {
            "era": self.profile.era.value,
            "tick": self.tick,
            "state": state,
        }
        return ModernSnapshot(
            self.profile.era,
            self.tick,
            state,
            _digest(payload),
        )

    def restore(self, snapshot: ModernSnapshot) -> None:
        if snapshot.era is not self.profile.era:
            raise GameEngineLabError("modern snapshot era mismatch")
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "state": snapshot.state,
        }
        if _digest(payload) != snapshot.digest:
            raise GameEngineLabError("modern snapshot digest mismatch")
        self.tick = snapshot.tick
        self._import_state(dict(snapshot.state))

    @property
    def rollback_depth(self) -> int:
        return len(
            self._rollback
        )

    def clear_rollback_history(self) -> None:
        """Discard speculative history after authoritative save/load time travel."""
        self._rollback.clear()

    def rollback(self, frames: int) -> None:
        if not self.spec.rollback_capable:
            raise GameEngineLabError("rollback unavailable for this engine era")
        if not isinstance(frames, int) or frames <= 0 or frames > len(self._rollback):
            raise GameEngineLabError("rollback distance unavailable")
        snapshot = self._rollback[-frames]
        self.restore(snapshot)
        self._rollback = self._rollback[: -frames]

    def fingerprint(self) -> str:
        return _digest(
            {
                "era": self.profile.era.value,
                "tick": self.tick,
                "state": tuple(sorted(self._export_state().items())),
            }
        )

    def _export_state(self) -> dict[str, object]:
        return {
            "player": (
                round(self.player_x, 12),
                round(self.player_z, 12),
                round(self.vx, 12),
                round(self.vz, 12),
            ),
            "loaded_cells": tuple(sorted(self.loaded_cells)),
            "entities": tuple(
                (
                    entity.entity_id,
                    entity.cell_x,
                    entity.cell_z,
                    round(entity.x, 12),
                    round(entity.z, 12),
                    round(entity.vx, 12),
                    round(entity.vz, 12),
                    entity.material,
                    entity.mesh,
                    entity.active,
                )
                for entity in (self.entities[key] for key in sorted(self.entities))
            ),
        }

    def _import_state(self, state: Mapping[str, object]) -> None:
        player = state["player"]
        self.player_x = float(player[0])
        self.player_z = float(player[1])
        self.vx = float(player[2])
        self.vz = float(player[3])
        self.loaded_cells = {
            (int(cell[0]), int(cell[1]))
            for cell in state["loaded_cells"]
        }
        self.entities = {}
        for raw in state["entities"]:
            entity = EcsEntity(
                int(raw[0]),
                int(raw[1]),
                int(raw[2]),
                float(raw[3]),
                float(raw[4]),
                float(raw[5]),
                float(raw[6]),
                int(raw[7]),
                int(raw[8]),
                bool(raw[9]),
            )
            self.entities[entity.entity_id] = entity


class HdDeferredMachine(ModernMachine):
    def __init__(self, tuning: Mapping[str, object] | None = None) -> None:
        super().__init__(EngineEra.HD, tuning)


class OpenWorldMachine(ModernMachine):
    def __init__(self, tuning: Mapping[str, object] | None = None) -> None:
        super().__init__(EngineEra.OPEN_WORLD, tuning)


class DataOrientedMachine(ModernMachine):
    def __init__(self, tuning: Mapping[str, object] | None = None) -> None:
        super().__init__(EngineEra.MODERN, tuning)


class NextHybridMachine(ModernMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
        policy: AdaptivePolicy | None = None,
    ) -> None:
        super().__init__(EngineEra.NEXT, tuning, policy)


def create_modern_machine(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
    policy: AdaptivePolicy | None = None,
) -> ModernMachine:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    if key is EngineEra.HD:
        if policy is not None:
            raise GameEngineLabError("adaptive policy unsupported for HD era")
        return HdDeferredMachine(tuning)
    if key is EngineEra.OPEN_WORLD:
        if policy is not None:
            raise GameEngineLabError("adaptive policy unsupported for open-world era")
        return OpenWorldMachine(tuning)
    if key is EngineEra.MODERN:
        if policy is not None:
            raise GameEngineLabError("adaptive policy unsupported for modern era")
        return DataOrientedMachine(tuning)
    if key is EngineEra.NEXT:
        return NextHybridMachine(tuning, policy)
    raise GameEngineLabError(
        f"modern runtime unavailable for {key.value}"
    )


def build_modern_engine_tree(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> VirtualFileTree:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    spec = modern_hardware(key)
    profile = engine_era_profile(key)
    base = build_engine_file_tree(key, gameplay_dialect)
    documents: dict[str, object] = {
        "engine/modern_pipeline.json": {
            "viewport": list(spec.viewport),
            "passes": list(spec.render_passes),
            "gpu_driven": spec.gpu_driven,
            "ray_queries": spec.ray_queries,
            "draw_budget": profile.draw_budget,
        },
        "engine/render_graph.json":
            render_graph_spec(
                key
            ).document(),
        "engine/ecs_schema.json": {
            "schema_version": 1,
            "components": [
                "position",
                "velocity",
                "cell",
                "material",
                "mesh",
                "active",
            ],
            "stable_entity_order": True,
        },
        "engine/jobs.json": {
            "lanes": spec.job_lanes,
            "deterministic_reduction": True,
            "order": [
                "input",
                "control",
                "physics",
                "streaming",
                "visibility",
                "render_prepare",
            ],
        },
        "engine/streaming.json": {
            "cell_size": ModernMachine.CELL_SIZE,
            "max_loaded_cells": spec.max_stream_cells,
            "bounded": True,
        },
        "engine/modern_tuning.json": default_modern_tuning(key),
        "tests/modern_acceptance.json": {
            "required": [
                "determinism",
                "render_passes",
                "render_graph",
                "streaming_bound",
                "snapshot",
                "rollback_contract",
                "policy_boundary",
            ]
        },
    }
    patches = [
        SandboxPatch(
            path,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        for path, payload in documents.items()
    ]
    patches.append(
        SandboxPatch(
            "engine/modern_runtime.py",
            (
                f'ENGINE_ERA = "{key.value}"\n'
                f'MACHINE = "{create_modern_machine(key).__class__.__name__}"\n'
            ),
        )
    )
    if spec.adaptive_policy:
        patches.append(
            SandboxPatch(
                "engine/adaptive_policy.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "bounded_linear_tanh",
                        "coefficients": list(DEFAULT_ADAPTIVE_POLICY.coefficients),
                        "executable_code": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        )
    return base.apply(patches)


def create_modern_machine_from_tree(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> ModernMachine:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    tuning = compile_modern_tuning(key, tree)
    policy = compile_adaptive_policy(tree) if key is EngineEra.NEXT else None
    return create_modern_machine(key, tuning, policy)


@dataclass(frozen=True, slots=True)
class ModernProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ModernQualityReport:
    era: EngineEra
    probes: tuple[ModernProbe, ...]

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    @property
    def score(self) -> float:
        return sum(probe.passed for probe in self.probes) / max(1, len(self.probes))

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class ModernEngineAdversary:
    def _script(self, count: int = 160) -> tuple[InputFrame, ...]:
        frames = []
        for tick in range(count):
            buttons = InputButton.NONE
            if tick % 50 < 30:
                buttons |= InputButton.UP | InputButton.RIGHT
            if tick % 47 == 0:
                buttons |= InputButton.FIRE
            frames.append(InputFrame(tick, buttons))
        return tuple(frames)

    def evaluate(
        self,
        era: EngineEra | str,
        tree: VirtualFileTree | None = None,
    ) -> ModernQualityReport:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
        spec = modern_hardware(key)
        active = tree or build_modern_engine_tree(key, "immersive_sim")
        required = {
            "engine/modern_pipeline.json",
            "engine/render_graph.json",
            "engine/ecs_schema.json",
            "engine/jobs.json",
            "engine/streaming.json",
            "engine/modern_tuning.json",
            "engine/modern_runtime.py",
            "tests/modern_acceptance.json",
        }
        if key is EngineEra.NEXT:
            required.add("engine/adaptive_policy.json")
        tree_ok = required <= set(active.files)
        probes = [
            ModernProbe(
                "file_tree",
                tree_ok,
                "modern runtime tree present" if tree_ok else "modern runtime files missing",
            )
        ]
        try:
            tuning = compile_modern_tuning(key, active)
            policy = compile_adaptive_policy(active) if key is EngineEra.NEXT else None
        except GameEngineLabError as exc:
            tuning = None
            policy = None
            detail = str(exc)
        else:
            detail = "bounded configuration compiled"
        probes.append(ModernProbe("configuration", tuning is not None, detail))
        if not tree_ok or tuning is None:
            probes.extend(
                ModernProbe(name, False, "runtime not compilable")
                for name in (
                    "determinism",
                    "render_passes",
                    "render_graph",
                    "streaming_bound",
                    "snapshot",
                    "rollback_contract",
                    "policy_boundary",
                )
            )
            return ModernQualityReport(key, tuple(probes))

        script = self._script()
        first = create_modern_machine(key, tuning, policy)
        second = create_modern_machine(key, tuning, policy)
        first_packets = first.run(script)
        second_packets = second.run(script)
        probes.append(
            ModernProbe(
                "determinism",
                first.fingerprint() == second.fingerprint()
                and first_packets == second_packets,
                "identical input replays",
            )
        )
        probes.append(
            ModernProbe(
                "render_passes",
                all(packet.passes == spec.render_passes for packet in first_packets),
                "era-specific render graph",
            )
        )
        graph_spec = render_graph_spec(
            key
        )
        graph_document_ok = False
        try:
            graph_document = json.loads(
                active.read(
                    "engine/render_graph.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ):
            graph_document = None
        else:
            graph_document_ok = (
                graph_document
                == graph_spec.document()
            )
        graph_passes = tuple(
            item.name
            for item
            in graph_spec.passes
        )
        render_graph_ok = (
            graph_document_ok
            and graph_passes
            == spec.render_passes
            and all(
                len(
                    packet.render_graph_digest
                )
                == 64
                and len(
                    packet.final_image_digest
                )
                == 64
                for packet
                in first_packets
            )
        )
        probes.append(
            ModernProbe(
                "render_graph",
                render_graph_ok,
                "bounded resource dependencies execute to deterministic final evidence",
            )
        )
        probes.append(
            ModernProbe(
                "streaming_bound",
                all(
                    len(packet.loaded_cells) <= spec.max_stream_cells
                    for packet in first_packets
                ),
                "loaded cells remain bounded",
            )
        )

        snap_machine = create_modern_machine(key, tuning, policy)
        snap_machine.run(self._script(32))
        snapshot = snap_machine.snapshot()
        before = snap_machine.fingerprint()
        snap_machine.run(
            tuple(
                InputFrame(32 + index, InputButton.LEFT)
                for index in range(10)
            )
        )
        snap_machine.restore(snapshot)
        probes.append(
            ModernProbe(
                "snapshot",
                snap_machine.fingerprint() == before,
                "modern state roundtrip",
            )
        )

        rollback_ok = True
        if spec.rollback_capable:
            rb = create_modern_machine(key, tuning, policy)
            rb.run(self._script(20))
            expected_tick = rb.tick - 5
            rb.rollback(5)
            rollback_ok = rb.tick == expected_tick
        else:
            rb = create_modern_machine(key, tuning, policy)
            try:
                rb.rollback(1)
            except GameEngineLabError:
                rollback_ok = True
            else:
                rollback_ok = False
        probes.append(
            ModernProbe(
                "rollback_contract",
                rollback_ok,
                "rollback follows era capability",
            )
        )

        policy_ok = (
            (key is EngineEra.NEXT and policy is not None and spec.adaptive_policy)
            or (key is not EngineEra.NEXT and policy is None and not spec.adaptive_policy)
        )
        probes.append(
            ModernProbe(
                "policy_boundary",
                policy_ok,
                "adaptive data plane is era-gated",
            )
        )
        return ModernQualityReport(key, tuple(probes))


@dataclass(frozen=True, slots=True)
class ModernEngineSandbox:
    era: EngineEra
    tree: VirtualFileTree
    gameplay_dialect: str | None = None

    def apply(self, patches: Iterable[SandboxPatch]) -> "ModernEngineSandbox":
        return ModernEngineSandbox(
            self.era,
            self.tree.apply(patches),
            self.gameplay_dialect,
        )

    def machine(self) -> ModernMachine:
        return create_modern_machine_from_tree(self.era, self.tree)


@dataclass(frozen=True, slots=True)
class ModernImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModernImprovementResult:
    sandbox: ModernEngineSandbox
    report: ModernQualityReport
    rounds: tuple[ModernImprovementRound, ...]
    promoted: bool


class ModernEngineLab:
    def __init__(
        self,
        adversary: ModernEngineAdversary | None = None,
    ) -> None:
        self.adversary = adversary or ModernEngineAdversary()

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> ModernEngineSandbox:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
        modern_hardware(key)
        return ModernEngineSandbox(
            key,
            build_modern_engine_tree(key, gameplay_dialect),
            gameplay_dialect,
        )

    def evaluate(self, sandbox: ModernEngineSandbox) -> ModernQualityReport:
        return self.adversary.evaluate(sandbox.era, sandbox.tree)

    def canonical_repair(
        self,
        sandbox: ModernEngineSandbox,
        report: ModernQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = build_modern_engine_tree(
            sandbox.era,
            sandbox.gameplay_dialect,
        )
        protected = {
            "engine/modern_pipeline.json",
            "engine/render_graph.json",
            "engine/ecs_schema.json",
            "engine/jobs.json",
            "engine/streaming.json",
            "engine/modern_tuning.json",
            "engine/modern_runtime.py",
            "tests/modern_acceptance.json",
        }
        if sandbox.era is EngineEra.NEXT:
            protected.add("engine/adaptive_policy.json")
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
        sandbox: ModernEngineSandbox,
        *,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> ModernImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError("target must be within (0, 1]")
        if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 32:
            raise GameEngineLabError("max_rounds must be within [1, 32]")
        current = sandbox
        report = self.evaluate(current)
        rounds: list[ModernImprovementRound] = []
        strategy = improver or self.canonical_repair
        if report.passed and report.score >= target:
            return ModernImprovementResult(current, report, (), True)
        for index in range(1, max_rounds + 1):
            patches = tuple(strategy(current, report))
            if not patches:
                break
            candidate = current.apply(patches)
            next_report = self.evaluate(candidate)
            accepted = (
                candidate.tree.digest != current.tree.digest
                and next_report.score >= report.score
                and len(next_report.failed) <= len(report.failed)
            )
            rounds.append(
                ModernImprovementRound(
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
            if report.passed and report.score >= target:
                break
        return ModernImprovementResult(
            current,
            report,
            tuple(rounds),
            report.passed and report.score >= target,
        )
