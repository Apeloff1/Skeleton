"""Executable 1993-2004 3D engine eras for Jeeves."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping

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
from .game_engine_rendering import (
    RasterFrame,
    RasterPipeline,
    RenderTriangle,
    RenderVertex,
    render_reference_scene,
)

THREE_D_ERAS = (
    EngineEra.EARLY_3D,
    EngineEra.FIXED_3D,
    EngineEra.SHADER,
)


@dataclass(frozen=True, slots=True)
class ThreeDHardwareSpec:
    era: EngineEra
    width: int
    height: int
    z_buffer: bool
    max_lights: int
    texture_units: int
    matrix_stack: int
    max_shader_programs: int
    max_bones: int
    visibility: str
    pipeline: str


THREE_D_HARDWARE = {
    EngineEra.EARLY_3D: ThreeDHardwareSpec(
        EngineEra.EARLY_3D,
        320,
        200,
        False,
        0,
        1,
        8,
        0,
        0,
        "bsp_front_to_back",
        "software_painter",
    ),
    EngineEra.FIXED_3D: ThreeDHardwareSpec(
        EngineEra.FIXED_3D,
        640,
        480,
        True,
        8,
        2,
        32,
        0,
        0,
        "frustum_scene_graph",
        "fixed_function_tl",
    ),
    EngineEra.SHADER: ThreeDHardwareSpec(
        EngineEra.SHADER,
        640,
        480,
        True,
        8,
        4,
        64,
        16,
        48,
        "frustum_scene_graph",
        "programmable_vertex_pixel",
    ),
}

THREE_D_TUNING = {
    EngineEra.EARLY_3D: {
        "move_speed": (0.45, 0.1, 1.5),
        "yaw_step": (4.0, 1.0, 12.0),
        "near_plane": (0.5, 0.2, 2.0),
        "focal_length": (170.0, 80.0, 260.0),
    },
    EngineEra.FIXED_3D: {
        "move_speed": (0.65, 0.1, 2.0),
        "yaw_step": (3.0, 0.5, 10.0),
        "near_plane": (0.25, 0.1, 1.0),
        "far_plane": (80.0, 20.0, 200.0),
        "fov_deg": (65.0, 40.0, 100.0),
    },
    EngineEra.SHADER: {
        "move_speed": (0.8, 0.1, 2.5),
        "yaw_step": (2.5, 0.5, 10.0),
        "near_plane": (0.2, 0.05, 1.0),
        "far_plane": (120.0, 30.0, 400.0),
        "fov_deg": (70.0, 40.0, 110.0),
        "bone_wave": (0.12, 0.0, 0.5),
    },
}


def three_d_hardware(era: EngineEra | str) -> ThreeDHardwareSpec:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    try:
        return THREE_D_HARDWARE[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"3D runtime unavailable for {key.value}"
        ) from exc


def default_3d_tuning(era: EngineEra | str) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    three_d_hardware(key)
    return {
        name: values[0]
        for name, values in THREE_D_TUNING[key].items()
    }


def normalize_3d_tuning(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> dict[str, float]:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    bounds = THREE_D_TUNING.get(key)
    if bounds is None:
        raise GameEngineLabError(
            f"3D runtime unavailable for {key.value}"
        )
    source = default_3d_tuning(key) if tuning is None else dict(tuning)
    if set(source) != set(bounds):
        raise GameEngineLabError("3D tuning keys mismatch")
    out: dict[str, float] = {}
    for name, (_, low, high) in bounds.items():
        raw = source[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise GameEngineLabError(
                f"3D tuning {name} must be numeric"
            )
        value = float(raw)
        if not math.isfinite(value) or not low <= value <= high:
            raise GameEngineLabError(
                f"3D tuning {name} outside [{low}, {high}]"
            )
        out[name] = value
    return out


def compile_3d_tuning(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> dict[str, float]:
    try:
        payload = json.loads(
            tree.read("engine/3d_tuning.json")
        )
    except (
        GameEngineLabError,
        json.JSONDecodeError,
    ) as exc:
        raise GameEngineLabError(
            "3D tuning missing or invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise GameEngineLabError(
            "3D tuning must be object"
        )
    return normalize_3d_tuning(era, payload)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _q(
    profile: EngineEraProfile,
    value: float,
) -> float:
    if not math.isfinite(value):
        raise GameEngineLabError(
            "3D state must be finite"
        )
    if profile.numeric_mode is NumericMode.FIXED16:
        return round(value * 65536) / 65536
    if profile.numeric_mode is NumericMode.FIXED8:
        return round(value * 256) / 256
    if profile.numeric_mode is NumericMode.INTEGER:
        return float(round(value))
    return float(value)


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class Mesh:
    name: str
    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True, slots=True)
class SceneObject:
    object_id: str
    position: Vec3
    mesh: Mesh
    material: int = 0
    shader: str = "fixed"
    radius: float = 1.0


@dataclass(frozen=True, slots=True)
class TriangleCommand:
    object_id: str
    material: int
    points: tuple[tuple[float, float], ...]
    depth: float


@dataclass(frozen=True, slots=True)
class Draw3DCommand:
    object_id: str
    material: int
    vertex_count: int
    index_count: int
    depth: float
    state_key: tuple[int, ...]
    shader: str = "fixed"
    constants_digest: str = ""


@dataclass(frozen=True, slots=True)
class ThreeDSnapshot:
    era: EngineEra
    tick: int
    state: tuple[tuple[str, object], ...]
    digest: str


@dataclass(frozen=True, slots=True)
class ThreeDFrame:
    era: EngineEra
    tick: int
    commands: tuple[
        TriangleCommand | Draw3DCommand,
        ...,
    ]
    state_digest: str
    culled: int
    state_changes: int


def cube_mesh(name: str = "cube") -> Mesh:
    vertices = (
        Vec3(-1, -1, -1),
        Vec3(1, -1, -1),
        Vec3(1, 1, -1),
        Vec3(-1, 1, -1),
        Vec3(-1, -1, 1),
        Vec3(1, -1, 1),
        Vec3(1, 1, 1),
        Vec3(-1, 1, 1),
    )
    triangles = (
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (3, 2, 6),
        (3, 6, 7),
        (1, 5, 6),
        (1, 6, 2),
        (0, 3, 7),
        (0, 7, 4),
    )
    return Mesh(
        name,
        vertices,
        triangles,
    )


class ThreeDMachine:
    def __init__(
        self,
        era: EngineEra,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        if era not in THREE_D_ERAS:
            raise GameEngineLabError(
                f"3D machine unavailable for {era.value}"
            )
        self.profile = engine_era_profile(era)
        self.spec = three_d_hardware(era)
        self.tuning = normalize_3d_tuning(
            era,
            tuning,
        )
        self.tick = 0
        self.camera = Vec3(
            0.0,
            0.0,
            0.0,
        )
        self.yaw = 0.0

    def step(
        self,
        frame: InputFrame | None = None,
    ) -> ThreeDFrame:
        frame = (
            InputFrame(self.tick)
            if frame is None
            else frame
        )
        if frame.tick != self.tick:
            raise GameEngineLabError(
                f"input tick mismatch: expected {self.tick}, got {frame.tick}"
            )
        self._move(frame)
        commands, culled, state_changes = self._render()
        packet = ThreeDFrame(
            self.profile.era,
            self.tick,
            commands,
            self.fingerprint(),
            culled,
            state_changes,
        )
        self.tick += 1
        return packet

    def run(
        self,
        frames: Iterable[InputFrame],
    ) -> tuple[ThreeDFrame, ...]:
        return tuple(
            self.step(frame)
            for frame in frames
        )

    def _move(
        self,
        frame: InputFrame,
    ) -> None:
        if frame.pressed(InputButton.LEFT):
            self.yaw -= self.tuning["yaw_step"]
        if frame.pressed(InputButton.RIGHT):
            self.yaw += self.tuning["yaw_step"]
        radians = math.radians(self.yaw)
        amount = 0.0
        if frame.pressed(InputButton.UP):
            amount += self.tuning["move_speed"]
        if frame.pressed(InputButton.DOWN):
            amount -= self.tuning["move_speed"]
        self.camera = Vec3(
            _q(
                self.profile,
                self.camera.x
                + math.sin(radians) * amount,
            ),
            self.camera.y,
            _q(
                self.profile,
                self.camera.z
                + math.cos(radians) * amount,
            ),
        )
        self.yaw = _q(
            self.profile,
            self.yaw % 360,
        )

    def snapshot(self) -> ThreeDSnapshot:
        state = tuple(
            sorted(self._export().items())
        )
        payload = {
            "era": self.profile.era.value,
            "tick": self.tick,
            "state": state,
        }
        return ThreeDSnapshot(
            self.profile.era,
            self.tick,
            state,
            _digest(payload),
        )

    def restore(
        self,
        snapshot: ThreeDSnapshot,
    ) -> None:
        if snapshot.era is not self.profile.era:
            raise GameEngineLabError(
                "3D snapshot era mismatch"
            )
        payload = {
            "era": snapshot.era.value,
            "tick": snapshot.tick,
            "state": snapshot.state,
        }
        if _digest(payload) != snapshot.digest:
            raise GameEngineLabError(
                "3D snapshot digest mismatch"
            )
        self.tick = snapshot.tick
        self._import(
            dict(snapshot.state)
        )

    def fingerprint(self) -> str:
        return _digest(
            {
                "era": self.profile.era.value,
                "tick": self.tick,
                "state": tuple(
                    sorted(
                        self._export().items()
                    )
                ),
            }
        )

    def _export(self) -> dict[str, object]:
        return {
            "camera": (
                self.camera.x,
                self.camera.y,
                self.camera.z,
            ),
            "yaw": self.yaw,
        }

    def _import(
        self,
        state: Mapping[str, object],
    ) -> None:
        self.camera = Vec3(
            *state["camera"]
        )
        self.yaw = float(
            state["yaw"]
        )

    def _camera_space(
        self,
        point: Vec3,
    ) -> Vec3:
        dx = point.x - self.camera.x
        dy = point.y - self.camera.y
        dz = point.z - self.camera.z
        radians = math.radians(self.yaw)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        return Vec3(
            dx * cosine - dz * sine,
            dy,
            dx * sine + dz * cosine,
        )

    def reference_triangles(
        self,
    ) -> tuple[RenderTriangle, ...]:
        """Return camera-space mesh triangles for executable raster validation."""
        values: list[RenderTriangle] = []
        objects = getattr(
            self,
            "objects",
            (),
        )
        for obj in objects:
            camera_vertices: list[
                RenderVertex
            ] = []
            for vertex in obj.mesh.vertices:
                y = (
                    vertex.y
                    + obj.position.y
                )
                if (
                    self.profile.era
                    is EngineEra.SHADER
                    and obj.shader
                    == "skinned"
                ):
                    phase = float(
                        getattr(
                            self,
                            "animation_phase",
                            0.0,
                        )
                    )
                    y += (
                        math.sin(
                            phase
                            + vertex.x
                            * 0.75
                        )
                        * self.tuning[
                            "bone_wave"
                        ]
                    )
                camera = self._camera_space(
                    Vec3(
                        vertex.x
                        + obj.position.x,
                        y,
                        vertex.z
                        + obj.position.z,
                    )
                )
                camera_vertices.append(
                    RenderVertex(
                        camera.x,
                        camera.y,
                        camera.z,
                    )
                )
            for indices in obj.mesh.triangles:
                values.append(
                    RenderTriangle(
                        obj.object_id,
                        obj.material,
                        (
                            camera_vertices[
                                indices[0]
                            ],
                            camera_vertices[
                                indices[1]
                            ],
                            camera_vertices[
                                indices[2]
                            ],
                        ),
                        obj.shader,
                        (
                            float(
                                getattr(
                                    self,
                                    "animation_phase",
                                    0.0,
                                )
                            )
                            if obj.shader
                            == "skinned"
                            else 0.0
                        ),
                    )
                )
        return tuple(values)

    def reference_raster(
        self,
        *,
        width: int = 96,
    ) -> RasterFrame:
        """Rasterize current scene state through the era's historical pipeline."""
        if (
            type(width) is not int
            or not 16 <= width <= 256
        ):
            raise GameEngineLabError(
                "reference raster width outside [16, 256]"
            )
        height = max(
            16,
            int(
                round(
                    width
                    * self.spec.height
                    / self.spec.width
                )
            ),
        )
        if (
            self.profile.era
            is EngineEra.EARLY_3D
        ):
            focal = self.tuning[
                "focal_length"
            ]
            fov_y = math.degrees(
                2.0
                * math.atan(
                    self.spec.height
                    / (
                        2.0
                        * focal
                    )
                )
            )
            far = 512.0
            pipeline = (
                RasterPipeline.PAINTER
            )
        elif (
            self.profile.era
            is EngineEra.FIXED_3D
        ):
            fov_y = self.tuning[
                "fov_deg"
            ]
            far = self.tuning[
                "far_plane"
            ]
            pipeline = (
                RasterPipeline.FIXED
            )
        else:
            fov_y = self.tuning[
                "fov_deg"
            ]
            far = self.tuning[
                "far_plane"
            ]
            pipeline = (
                RasterPipeline.PROGRAMMABLE
            )
        return render_reference_scene(
            self.reference_triangles(),
            width=width,
            height=height,
            near=self.tuning[
                "near_plane"
            ],
            far=far,
            fov_y_deg=fov_y,
            pipeline=pipeline,
        )

    def _render(
        self,
    ) -> tuple[
        tuple[
            TriangleCommand | Draw3DCommand,
            ...,
        ],
        int,
        int,
    ]:
        raise NotImplementedError


class SoftwareBspMachine(ThreeDMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.EARLY_3D,
            tuning,
        )
        mesh = cube_mesh()
        self.objects = (
            SceneObject(
                "west",
                Vec3(-4, 0, 14),
                mesh,
                1,
            ),
            SceneObject(
                "east",
                Vec3(4, 0, 18),
                mesh,
                2,
            ),
            SceneObject(
                "rear",
                Vec3(0, 1, 28),
                mesh,
                3,
            ),
        )

    def _bsp_order(
        self,
    ) -> tuple[SceneObject, ...]:
        west = tuple(
            obj
            for obj in self.objects
            if obj.position.x < 0
        )
        east = tuple(
            obj
            for obj in self.objects
            if obj.position.x >= 0
        )
        return (
            east + west
            if self.camera.x < 0
            else west + east
        )

    def _render(
        self,
    ) -> tuple[
        tuple[TriangleCommand, ...],
        int,
        int,
    ]:
        focal = self.tuning[
            "focal_length"
        ]
        near = self.tuning[
            "near_plane"
        ]
        commands: list[
            TriangleCommand
        ] = []
        culled = 0
        for obj in self._bsp_order():
            camera_vertices = [
                self._camera_space(
                    Vec3(
                        vertex.x
                        + obj.position.x,
                        vertex.y
                        + obj.position.y,
                        vertex.z
                        + obj.position.z,
                    )
                )
                for vertex
                in obj.mesh.vertices
            ]
            for triangle in obj.mesh.triangles:
                vertices = [
                    camera_vertices[index]
                    for index in triangle
                ]
                depth = (
                    sum(
                        vertex.z
                        for vertex in vertices
                    )
                    / 3
                )
                if depth <= near:
                    culled += 1
                    continue
                points = tuple(
                    (
                        round(
                            self.spec.width / 2
                            + vertex.x
                            * focal
                            / vertex.z,
                            3,
                        ),
                        round(
                            self.spec.height / 2
                            - vertex.y
                            * focal
                            / vertex.z,
                            3,
                        ),
                    )
                    for vertex
                    in vertices
                )
                commands.append(
                    TriangleCommand(
                        obj.object_id,
                        obj.material,
                        points,
                        round(depth, 6),
                    )
                )
        commands.sort(
            key=lambda command: (
                -command.depth,
                command.object_id,
                command.material,
                command.points,
            )
        )
        commands = commands[
            : self.profile.draw_budget
        ]
        return (
            tuple(commands),
            culled,
            0,
        )


class FixedFunctionMachine(ThreeDMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.FIXED_3D,
            tuning,
        )
        mesh = cube_mesh()
        self.objects = (
            SceneObject(
                "crate_a",
                Vec3(-3, 0, 12),
                mesh,
                1,
            ),
            SceneObject(
                "crate_b",
                Vec3(3, 0, 16),
                mesh,
                1,
            ),
            SceneObject(
                "metal",
                Vec3(0, 2, 24),
                mesh,
                2,
            ),
            SceneObject(
                "far",
                Vec3(12, 0, 90),
                mesh,
                3,
            ),
        )

    def _visible(
        self,
        obj: SceneObject,
    ) -> Vec3 | None:
        point = self._camera_space(
            obj.position
        )
        near = self.tuning[
            "near_plane"
        ]
        far = self.tuning[
            "far_plane"
        ]
        if (
            point.z - obj.radius
            < near
            or point.z - obj.radius
            > far
        ):
            return None
        half = (
            math.tan(
                math.radians(
                    self.tuning[
                        "fov_deg"
                    ]
                )
                / 2
            )
            * point.z
        )
        if (
            abs(point.x)
            - obj.radius
            > half
        ):
            return None
        return point

    def _render(
        self,
    ) -> tuple[
        tuple[Draw3DCommand, ...],
        int,
        int,
    ]:
        rows: list[
            Draw3DCommand
        ] = []
        culled = 0
        for obj in self.objects:
            point = self._visible(obj)
            if point is None:
                culled += 1
                continue
            rows.append(
                Draw3DCommand(
                    obj.object_id,
                    obj.material,
                    len(obj.mesh.vertices),
                    len(
                        obj.mesh.triangles
                    )
                    * 3,
                    round(
                        point.z,
                        6,
                    ),
                    (
                        obj.material,
                        0,
                    ),
                    shader="fixed",
                )
            )
        rows.sort(
            key=lambda command: (
                command.state_key,
                command.depth,
                command.object_id,
            )
        )
        changes = 0
        last = None
        for row in rows:
            if row.state_key != last:
                changes += 1
                last = row.state_key
        return (
            tuple(
                rows[
                    : self.profile.draw_budget
                ]
            ),
            culled,
            changes,
        )


@dataclass(frozen=True, slots=True)
class ShaderProgram:
    name: str
    vertex_ops: tuple[str, ...]
    pixel_ops: tuple[str, ...]
    constants: int

    def __post_init__(self) -> None:
        allowed_vertex = {
            "transform",
            "skin",
            "normal",
            "wave",
        }
        allowed_pixel = {
            "texture",
            "lambert",
            "fog",
            "tint",
        }
        if (
            not set(self.vertex_ops)
            <= allowed_vertex
            or not set(
                self.pixel_ops
            )
            <= allowed_pixel
        ):
            raise GameEngineLabError(
                "unsupported shader op"
            )
        if (
            self.constants < 0
            or self.constants > 64
        ):
            raise GameEngineLabError(
                "shader constant budget exceeded"
            )


SHADERS = {
    "lit": ShaderProgram(
        "lit",
        (
            "transform",
            "normal",
        ),
        (
            "texture",
            "lambert",
            "fog",
        ),
        12,
    ),
    "skinned": ShaderProgram(
        "skinned",
        (
            "skin",
            "transform",
            "normal",
            "wave",
        ),
        (
            "texture",
            "lambert",
            "tint",
        ),
        28,
    ),
}


class ShaderConsoleMachine(ThreeDMachine):
    def __init__(
        self,
        tuning: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            EngineEra.SHADER,
            tuning,
        )
        mesh = cube_mesh()
        self.objects = (
            SceneObject(
                "hero",
                Vec3(0, 0, 10),
                mesh,
                1,
                "skinned",
            ),
            SceneObject(
                "pillar",
                Vec3(-4, 0, 18),
                mesh,
                2,
                "lit",
            ),
            SceneObject(
                "enemy",
                Vec3(5, 0, 22),
                mesh,
                3,
                "skinned",
            ),
        )
        self.animation_phase = 0.0

    def _move(
        self,
        frame: InputFrame,
    ) -> None:
        super()._move(frame)
        self.animation_phase = _q(
            self.profile,
            (
                self.animation_phase
                + 0.05
            )
            % math.tau,
        )

    def _render(
        self,
    ) -> tuple[
        tuple[Draw3DCommand, ...],
        int,
        int,
    ]:
        rows: list[
            Draw3DCommand
        ] = []
        culled = 0
        near = self.tuning[
            "near_plane"
        ]
        far = self.tuning[
            "far_plane"
        ]
        half_tangent = math.tan(
            math.radians(
                self.tuning[
                    "fov_deg"
                ]
            )
            / 2
        )
        for obj in self.objects:
            point = self._camera_space(
                obj.position
            )
            if (
                point.z < near
                or point.z > far
                or abs(point.x)
                > (
                    point.z
                    * half_tangent
                    + obj.radius
                )
            ):
                culled += 1
                continue
            program = SHADERS[
                obj.shader
            ]
            constants = {
                "phase": round(
                    self.animation_phase,
                    6,
                ),
                "wave": self.tuning[
                    "bone_wave"
                ],
                "camera": (
                    self.camera.x,
                    self.camera.y,
                    self.camera.z,
                ),
            }
            rows.append(
                Draw3DCommand(
                    obj.object_id,
                    obj.material,
                    len(obj.mesh.vertices),
                    len(
                        obj.mesh.triangles
                    )
                    * 3,
                    round(
                        point.z,
                        6,
                    ),
                    (
                        obj.material,
                        int(
                            hashlib.sha256(
                                program.name.encode("utf-8")
                            ).hexdigest()[:8],
                            16,
                        ),
                    ),
                    shader=program.name,
                    constants_digest=_digest(
                        constants
                    ),
                )
            )
        rows.sort(
            key=lambda command: (
                command.shader,
                command.state_key,
                command.depth,
                command.object_id,
            )
        )
        changes = 0
        last = None
        for row in rows:
            state = (
                row.shader,
                row.state_key,
            )
            if state != last:
                changes += 1
                last = state
        return (
            tuple(
                rows[
                    : self.profile.draw_budget
                ]
            ),
            culled,
            changes,
        )

    def _export(
        self,
    ) -> dict[str, object]:
        out = super()._export()
        out[
            "animation_phase"
        ] = self.animation_phase
        return out

    def _import(
        self,
        state: Mapping[str, object],
    ) -> None:
        super()._import(state)
        self.animation_phase = float(
            state[
                "animation_phase"
            ]
        )


def create_3d_machine(
    era: EngineEra | str,
    tuning: Mapping[str, object] | None = None,
) -> ThreeDMachine:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    if key is EngineEra.EARLY_3D:
        return SoftwareBspMachine(
            tuning
        )
    if key is EngineEra.FIXED_3D:
        return FixedFunctionMachine(
            tuning
        )
    if key is EngineEra.SHADER:
        return ShaderConsoleMachine(
            tuning
        )
    raise GameEngineLabError(
        f"3D runtime unavailable for {key.value}"
    )


def create_3d_machine_from_tree(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> ThreeDMachine:
    return create_3d_machine(
        era,
        compile_3d_tuning(
            era,
            tree,
        ),
    )


def build_3d_engine_tree(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> VirtualFileTree:
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    spec = three_d_hardware(key)
    profile = engine_era_profile(key)
    base = build_engine_file_tree(
        key,
        gameplay_dialect,
    )
    files = {
        "engine/3d_pipeline.json": {
            "pipeline": spec.pipeline,
            "z_buffer": spec.z_buffer,
            "texture_units":
                spec.texture_units,
            "max_lights":
                spec.max_lights,
            "matrix_stack":
                spec.matrix_stack,
            "draw_budget":
                profile.draw_budget,
        },
        "engine/visibility.json": {
            "mode": spec.visibility,
            "near_clip":
                default_3d_tuning(
                    key
                )[
                    "near_plane"
                ],
        },
        "engine/3d_tuning.json":
            default_3d_tuning(key),
        "assets/scene3d.json": {
            "mesh": "cube",
            "objects": 3,
            "coordinate_system":
                "x_right_y_up_z_forward",
        },
    }
    patches = [
        SandboxPatch(
            path,
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        for path, payload
        in files.items()
    ]
    patches.append(
        SandboxPatch(
            "engine/3d_runtime.py",
            (
                f'ENGINE_ERA = "{key.value}"\n'
                f'MACHINE = "{create_3d_machine(key).__class__.__name__}"\n'
            ),
        )
    )
    if key is EngineEra.SHADER:
        patches.append(
            SandboxPatch(
                "engine/shaders.json",
                json.dumps(
                    {
                        name: {
                            "vertex_ops":
                                list(
                                    program.vertex_ops
                                ),
                            "pixel_ops":
                                list(
                                    program.pixel_ops
                                ),
                            "constants":
                                program.constants,
                        }
                        for name, program
                        in SHADERS.items()
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        )
    return base.apply(patches)


@dataclass(frozen=True, slots=True)
class ThreeDProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ThreeDQualityReport:
    era: EngineEra
    probes: tuple[
        ThreeDProbe,
        ...,
    ]

    @property
    def passed(self) -> bool:
        return all(
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
    def failed(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe in self.probes
            if not probe.passed
        )


class ThreeDEngineAdversary:
    def _script(
        self,
        count: int = 120,
    ) -> tuple[InputFrame, ...]:
        frames = []
        for tick in range(count):
            buttons = (
                InputButton.UP
                if tick % 30 < 18
                else InputButton.NONE
            )
            if tick % 20 < 8:
                buttons |= (
                    InputButton.RIGHT
                )
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
    ) -> ThreeDQualityReport:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        spec = three_d_hardware(key)
        active = (
            tree
            or build_3d_engine_tree(
                key,
                "boomer_shooter",
            )
        )
        required = {
            "engine/3d_pipeline.json",
            "engine/visibility.json",
            "engine/3d_tuning.json",
            "assets/scene3d.json",
            "engine/3d_runtime.py",
        }
        if key is EngineEra.SHADER:
            required.add(
                "engine/shaders.json"
            )
        tree_ok = required <= set(
            active.files
        )
        probes = [
            ThreeDProbe(
                "file_tree",
                tree_ok,
                (
                    "3D runtime tree present"
                    if tree_ok
                    else "3D runtime files missing"
                ),
            )
        ]
        try:
            tuning = compile_3d_tuning(
                key,
                active,
            )
        except GameEngineLabError as exc:
            tuning = None
            detail = str(exc)
        else:
            detail = (
                "bounded 3D tuning compiled"
            )
        probes.append(
            ThreeDProbe(
                "tuning",
                tuning is not None,
                detail,
            )
        )
        if not tree_ok or tuning is None:
            probes.extend(
                ThreeDProbe(
                    name,
                    False,
                    "runtime not compilable",
                )
                for name in (
                    "determinism",
                    "draw_budget",
                    "snapshot",
                    "pipeline",
                    "raster",
                )
            )
            return ThreeDQualityReport(
                key,
                tuple(probes),
            )

        script = self._script()
        first = create_3d_machine(
            key,
            tuning,
        )
        second = create_3d_machine(
            key,
            tuning,
        )
        first_packets = first.run(
            script
        )
        second_packets = second.run(
            script
        )
        probes.append(
            ThreeDProbe(
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
            ThreeDProbe(
                "draw_budget",
                all(
                    len(packet.commands)
                    <= first.profile.draw_budget
                    for packet
                    in first_packets
                ),
                "bounded 3D command buffers",
            )
        )

        snapshot_machine = create_3d_machine(
            key,
            tuning,
        )
        snapshot_machine.run(
            self._script(40)
        )
        snapshot = snapshot_machine.snapshot()
        before = snapshot_machine.fingerprint()
        snapshot_machine.run(
            tuple(
                InputFrame(
                    40 + index,
                    InputButton.LEFT,
                )
                for index in range(10)
            )
        )
        snapshot_machine.restore(
            snapshot
        )
        probes.append(
            ThreeDProbe(
                "snapshot",
                (
                    snapshot_machine.fingerprint()
                    == before
                ),
                "3D state roundtrip",
            )
        )

        if key is EngineEra.EARLY_3D:
            order_ok = all(
                all(
                    frame.commands[index].depth
                    >= frame.commands[
                        index + 1
                    ].depth
                    for index
                    in range(
                        len(
                            frame.commands
                        )
                        - 1
                    )
                )
                for frame
                in first_packets
            )
            probes.append(
                ThreeDProbe(
                    "pipeline",
                    (
                        order_ok
                        and not spec.z_buffer
                    ),
                    (
                        "BSP/painter ordering "
                        "without z buffer"
                    ),
                )
            )
        elif key is EngineEra.FIXED_3D:
            probes.append(
                ThreeDProbe(
                    "pipeline",
                    (
                        spec.z_buffer
                        and all(
                            isinstance(
                                command,
                                Draw3DCommand,
                            )
                            and command.shader
                            == "fixed"
                            for frame
                            in first_packets
                            for command
                            in frame.commands
                        )
                    ),
                    (
                        "fixed-function "
                        "z-buffer pipeline"
                    ),
                )
            )
        else:
            probes.append(
                ThreeDProbe(
                    "pipeline",
                    (
                        spec.z_buffer
                        and all(
                            isinstance(
                                command,
                                Draw3DCommand,
                            )
                            and command.shader
                            in SHADERS
                            and len(
                                command.constants_digest
                            )
                            == 64
                            for frame
                            in first_packets
                            for command
                            in frame.commands
                        )
                    ),
                    (
                        "bounded programmable "
                        "shader pipeline"
                    ),
                )
            )
        raster_first = create_3d_machine(
            key,
            tuning,
        ).reference_raster()
        raster_second = create_3d_machine(
            key,
            tuning,
        ).reference_raster()
        raster_ok = (
            raster_first
            == raster_second
            and len(
                raster_first.digest
            )
            == 64
            and raster_first.stats.covered_pixels
            > 0
            and raster_first.stats.rasterized_triangles
            > 0
            and raster_first.stats.min_depth
            is not None
            and raster_first.stats.max_depth
            is not None
        )
        if (
            key is EngineEra.EARLY_3D
        ):
            raster_ok = (
                raster_ok
                and raster_first.stats.depth_rejected_fragments
                == 0
            )
        probes.append(
            ThreeDProbe(
                "raster",
                raster_ok,
                (
                    "deterministic reference framebuffer "
                    f"{raster_first.stats.covered_pixels}px "
                    f"depth_rejects={raster_first.stats.depth_rejected_fragments}"
                ),
            )
        )
        return ThreeDQualityReport(
            key,
            tuple(probes),
        )


@dataclass(frozen=True, slots=True)
class ThreeDEngineSandbox:
    era: EngineEra
    tree: VirtualFileTree
    gameplay_dialect: str | None = None

    def apply(
        self,
        patches: Iterable[SandboxPatch],
    ) -> "ThreeDEngineSandbox":
        return ThreeDEngineSandbox(
            self.era,
            self.tree.apply(patches),
            self.gameplay_dialect,
        )

    def machine(self) -> ThreeDMachine:
        return create_3d_machine_from_tree(
            self.era,
            self.tree,
        )


@dataclass(frozen=True, slots=True)
class ThreeDImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThreeDImprovementResult:
    sandbox: ThreeDEngineSandbox
    report: ThreeDQualityReport
    rounds: tuple[
        ThreeDImprovementRound,
        ...,
    ]
    promoted: bool


class ThreeDEngineLab:
    def __init__(
        self,
        adversary:
            ThreeDEngineAdversary
            | None = None,
    ) -> None:
        self.adversary = (
            adversary
            or ThreeDEngineAdversary()
        )

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect:
            str | None = None,
    ) -> ThreeDEngineSandbox:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
        three_d_hardware(key)
        return ThreeDEngineSandbox(
            key,
            build_3d_engine_tree(
                key,
                gameplay_dialect,
            ),
            gameplay_dialect,
        )

    def evaluate(
        self,
        sandbox: ThreeDEngineSandbox,
    ) -> ThreeDQualityReport:
        return self.adversary.evaluate(
            sandbox.era,
            sandbox.tree,
        )

    def canonical_repair(
        self,
        sandbox: ThreeDEngineSandbox,
        report: ThreeDQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = build_3d_engine_tree(
            sandbox.era,
            sandbox.gameplay_dialect,
        )
        protected = {
            "engine/3d_pipeline.json",
            "engine/visibility.json",
            "engine/3d_tuning.json",
            "assets/scene3d.json",
            "engine/3d_runtime.py",
        }
        if (
            sandbox.era
            is EngineEra.SHADER
        ):
            protected.add(
                "engine/shaders.json"
            )
        patches: list[
            SandboxPatch
        ] = []
        for path in sorted(protected):
            wanted = canonical.read(path)
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
        sandbox: ThreeDEngineSandbox,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> ThreeDImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError(
                "target must be within (0, 1]"
            )
        current = sandbox
        report = self.evaluate(
            current
        )
        rounds: list[
            ThreeDImprovementRound
        ] = []
        strategy = (
            improver
            or self.canonical_repair
        )
        if (
            report.passed
            and report.score >= target
        ):
            return ThreeDImprovementResult(
                current,
                report,
                (),
                True,
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
                ThreeDImprovementRound(
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
        return ThreeDImprovementResult(
            current,
            report,
            tuple(rounds),
            (
                report.passed
                and report.score >= target
            ),
        )
