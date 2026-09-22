"""Deterministic software reference rasterizer for Jeeves historical engines.

This is not a fourth 3D runtime family. It is a small executable reference
backend used to validate the rendering semantics already owned by the
historical 3D machines:

* software-painter mode models early 3D with no depth buffer;
* fixed-function mode adds z testing and vertex-light style Lambert shading;
* programmable mode adds deterministic tint/fog operations.

The rasterizer intentionally works at bounded validation resolutions. It
performs real near-plane clipping, perspective projection, edge-function
triangle coverage, perspective-safe depth interpolation, depth testing,
overdraw accounting, and stable framebuffer hashing.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .game_engine_lab import GameEngineLabError

MAX_RASTER_WIDTH = 320
MAX_RASTER_HEIGHT = 240
MAX_RASTER_TRIANGLES = 4096
MAX_RASTER_PIXELS = MAX_RASTER_WIDTH * MAX_RASTER_HEIGHT


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            f"{label} must be finite"
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


class RasterPipeline(str, Enum):
    PAINTER = "software_painter"
    FIXED = "fixed_function"
    PROGRAMMABLE = "programmable"


@dataclass(frozen=True, slots=True)
class RenderVertex:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        _finite(self.x, "vertex x")
        _finite(self.y, "vertex y")
        _finite(self.z, "vertex z")

    def lerp(
        self,
        other: "RenderVertex",
        alpha: float,
    ) -> "RenderVertex":
        alpha = _clamp(
            _finite(
                alpha,
                "vertex interpolation",
            ),
            0.0,
            1.0,
        )
        return RenderVertex(
            self.x
            + (
                other.x
                - self.x
            )
            * alpha,
            self.y
            + (
                other.y
                - self.y
            )
            * alpha,
            self.z
            + (
                other.z
                - self.z
            )
            * alpha,
        )


@dataclass(frozen=True, slots=True)
class RenderTriangle:
    object_id: str
    material: int
    vertices: tuple[
        RenderVertex,
        RenderVertex,
        RenderVertex,
    ]
    shader: str = "fixed"
    shader_phase: float = 0.0

    def __post_init__(self) -> None:
        if (
            not self.object_id
            or len(self.object_id) > 64
        ):
            raise GameEngineLabError(
                "render object id must be bounded"
            )
        if (
            type(self.material) is not int
            or not 0 <= self.material <= 65535
        ):
            raise GameEngineLabError(
                "render material outside unsigned-16 range"
            )
        if len(self.vertices) != 3:
            raise GameEngineLabError(
                "render triangle requires exactly three vertices"
            )
        _finite(
            self.shader_phase,
            "render shader phase",
        )


@dataclass(frozen=True, slots=True)
class RasterConfig:
    width: int
    height: int
    near: float
    far: float
    fov_y_deg: float
    pipeline: RasterPipeline
    light_direction: RenderVertex = RenderVertex(
        -0.3,
        -0.6,
        -1.0,
    )
    fog_start: float = 0.65

    def __post_init__(self) -> None:
        if (
            type(self.width) is not int
            or type(self.height) is not int
            or not 8 <= self.width <= MAX_RASTER_WIDTH
            or not 8 <= self.height <= MAX_RASTER_HEIGHT
        ):
            raise GameEngineLabError(
                "raster dimensions outside bounded validation range"
            )
        near = _finite(
            self.near,
            "near plane",
        )
        far = _finite(
            self.far,
            "far plane",
        )
        if (
            near <= 0
            or far <= near
        ):
            raise GameEngineLabError(
                "raster near/far planes invalid"
            )
        fov = _finite(
            self.fov_y_deg,
            "vertical field of view",
        )
        if not 10 <= fov <= 150:
            raise GameEngineLabError(
                "raster field of view outside [10, 150]"
            )
        fog = _finite(
            self.fog_start,
            "fog start",
        )
        if not 0 <= fog <= 1:
            raise GameEngineLabError(
                "fog start must be within [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class RasterStats:
    submitted_triangles: int
    clipped_triangles: int
    culled_triangles: int
    rasterized_triangles: int
    covered_pixels: int
    shaded_fragments: int
    depth_rejected_fragments: int
    overdraw_fragments: int
    min_depth: float | None
    max_depth: float | None


@dataclass(frozen=True, slots=True)
class RasterFrame:
    width: int
    height: int
    digest: str
    color_digest: str
    depth_digest: str
    stats: RasterStats
    material_histogram: tuple[
        tuple[int, int],
        ...,
    ]


@dataclass(frozen=True, slots=True)
class _ScreenVertex:
    x: float
    y: float
    z: float
    reciprocal_z: float


@dataclass(frozen=True, slots=True)
class _PreparedTriangle:
    object_id: str
    material: int
    shader: str
    shader_phase: float
    screen: tuple[
        _ScreenVertex,
        _ScreenVertex,
        _ScreenVertex,
    ]
    intensity: float
    average_depth: float


def _normalize(vertex: RenderVertex) -> RenderVertex:
    length = math.sqrt(
        vertex.x * vertex.x
        + vertex.y * vertex.y
        + vertex.z * vertex.z
    )
    if length <= 1e-12:
        return RenderVertex(
            0.0,
            0.0,
            0.0,
        )
    return RenderVertex(
        vertex.x / length,
        vertex.y / length,
        vertex.z / length,
    )


def _sub(
    left: RenderVertex,
    right: RenderVertex,
) -> RenderVertex:
    return RenderVertex(
        left.x - right.x,
        left.y - right.y,
        left.z - right.z,
    )


def _cross(
    left: RenderVertex,
    right: RenderVertex,
) -> RenderVertex:
    return RenderVertex(
        left.y * right.z
        - left.z * right.y,
        left.z * right.x
        - left.x * right.z,
        left.x * right.y
        - left.y * right.x,
    )


def _dot(
    left: RenderVertex,
    right: RenderVertex,
) -> float:
    return (
        left.x * right.x
        + left.y * right.y
        + left.z * right.z
    )


def _polygon_clip_z(
    vertices: tuple[RenderVertex, ...],
    *,
    plane: float,
    keep_greater: bool,
) -> tuple[RenderVertex, ...]:
    if not vertices:
        return ()

    def inside(
        vertex: RenderVertex,
    ) -> bool:
        return (
            vertex.z >= plane
            if keep_greater
            else vertex.z <= plane
        )

    output: list[
        RenderVertex
    ] = []
    previous = vertices[-1]
    previous_inside = inside(
        previous
    )
    for current in vertices:
        current_inside = inside(
            current
        )
        if (
            current_inside
            != previous_inside
        ):
            denominator = (
                current.z
                - previous.z
            )
            alpha = (
                0.0
                if abs(
                    denominator
                ) <= 1e-12
                else (
                    plane
                    - previous.z
                )
                / denominator
            )
            output.append(
                previous.lerp(
                    current,
                    alpha,
                )
            )
        if current_inside:
            output.append(
                current
            )
        previous = current
        previous_inside = (
            current_inside
        )
    return tuple(output)


def clip_triangle(
    triangle: RenderTriangle,
    near: float,
    far: float,
) -> tuple[RenderTriangle, ...]:
    """Clip one triangle against near/far planes and fan-triangulate."""

    polygon = _polygon_clip_z(
        triangle.vertices,
        plane=near,
        keep_greater=True,
    )
    polygon = _polygon_clip_z(
        polygon,
        plane=far,
        keep_greater=False,
    )
    if len(polygon) < 3:
        return ()
    first = polygon[0]
    result = []
    for index in range(
        1,
        len(polygon) - 1,
    ):
        result.append(
            RenderTriangle(
                triangle.object_id,
                triangle.material,
                (
                    first,
                    polygon[index],
                    polygon[
                        index + 1
                    ],
                ),
                triangle.shader,
                triangle.shader_phase,
            )
        )
    return tuple(result)


def _project(
    vertex: RenderVertex,
    config: RasterConfig,
) -> _ScreenVertex:
    if vertex.z <= 0:
        raise GameEngineLabError(
            "cannot project non-positive camera depth"
        )
    aspect = (
        config.width
        / config.height
    )
    focal_y = (
        1.0
        / math.tan(
            math.radians(
                config.fov_y_deg
            )
            * 0.5
        )
    )
    focal_x = (
        focal_y
        / aspect
    )
    ndc_x = (
        vertex.x
        * focal_x
        / vertex.z
    )
    ndc_y = (
        vertex.y
        * focal_y
        / vertex.z
    )
    return _ScreenVertex(
        (
            ndc_x
            * 0.5
            + 0.5
        )
        * (
            config.width
            - 1
        ),
        (
            0.5
            - ndc_y
            * 0.5
        )
        * (
            config.height
            - 1
        ),
        vertex.z,
        1.0 / vertex.z,
    )


def _edge(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    px: float,
    py: float,
) -> float:
    return (
        (
            px - ax
        )
        * (
            by - ay
        )
        - (
            py - ay
        )
        * (
            bx - ax
        )
    )


def _face_intensity(
    triangle: RenderTriangle,
    light: RenderVertex,
) -> float:
    a, b, c = (
        triangle.vertices
    )
    normal = _normalize(
        _cross(
            _sub(b, a),
            _sub(c, a),
        )
    )
    light = _normalize(
        light
    )
    diffuse = abs(
        _dot(
            normal,
            RenderVertex(
                -light.x,
                -light.y,
                -light.z,
            ),
        )
    )
    return _clamp(
        0.2
        + 0.8
        * diffuse,
        0.0,
        1.0,
    )


def _prepare(
    triangle: RenderTriangle,
    config: RasterConfig,
) -> _PreparedTriangle | None:
    screen = tuple(
        _project(
            vertex,
            config,
        )
        for vertex
        in triangle.vertices
    )
    area = _edge(
        screen[0].x,
        screen[0].y,
        screen[1].x,
        screen[1].y,
        screen[2].x,
        screen[2].y,
    )
    if abs(area) <= 1e-9:
        return None
    intensity = (
        1.0
        if config.pipeline
        is RasterPipeline.PAINTER
        else _face_intensity(
            triangle,
            config.light_direction,
        )
    )
    return _PreparedTriangle(
        triangle.object_id,
        triangle.material,
        triangle.shader,
        triangle.shader_phase,
        screen,  # type: ignore[arg-type]
        intensity,
        sum(
            vertex.z
            for vertex
            in triangle.vertices
        )
        / 3.0,
    )


def _material_base(
    material: int,
) -> tuple[int, int, int]:
    # Stable high-contrast pseudo-palette derived only from material identity.
    return (
        48
        + (
            material * 97
            + 31
        )
        % 192,
        48
        + (
            material * 57
            + 83
        )
        % 192,
        48
        + (
            material * 131
            + 17
        )
        % 192,
    )


def _shade(
    triangle: _PreparedTriangle,
    depth: float,
    config: RasterConfig,
) -> tuple[int, int, int]:
    red, green, blue = (
        _material_base(
            triangle.material
        )
    )
    intensity = (
        triangle.intensity
    )
    red *= intensity
    green *= intensity
    blue *= intensity

    if (
        config.pipeline
        is RasterPipeline.PROGRAMMABLE
    ):
        # The historical programmable reference implements a bounded subset
        # matching ShaderProgram's tint/fog-style operations.
        if (
            triangle.shader
            == "skinned"
        ):
            phase_wave = math.sin(
                triangle.shader_phase
                * 4.0
            )
            phase_pulse = (
                0.85
                + 0.15
                * (
                    phase_wave
                    + 1.0
                )
                * 0.5
            )
            red = (
                red
                * 1.06
                * phase_pulse
                + 18.0
                * (
                    phase_wave
                    + 1.0
                )
                * 0.5
            )
            green *= (
                0.92
                + 0.08
                * (
                    1.0
                    - phase_wave
                )
                * 0.5
            )
            blue = (
                blue
                * (
                    0.90
                    + 0.10
                    * (
                        1.0
                        - phase_wave
                    )
                    * 0.5
                )
                + 12.0
                * (
                    1.0
                    - phase_wave
                )
                * 0.5
            )
        normalized_depth = _clamp(
            (
                depth
                - config.near
            )
            / (
                config.far
                - config.near
            ),
            0.0,
            1.0,
        )
        fog = _clamp(
            (
                normalized_depth
                - config.fog_start
            )
            / max(
                1e-9,
                1.0
                - config.fog_start
            ),
            0.0,
            1.0,
        )
        fog_color = (
            96.0,
            112.0,
            128.0,
        )
        red = (
            red
            * (
                1.0
                - fog
            )
            + fog_color[0]
            * fog
        )
        green = (
            green
            * (
                1.0
                - fog
            )
            + fog_color[1]
            * fog
        )
        blue = (
            blue
            * (
                1.0
                - fog
            )
            + fog_color[2]
            * fog
        )

    return (
        int(
            round(
                _clamp(
                    red,
                    0.0,
                    255.0,
                )
            )
        ),
        int(
            round(
                _clamp(
                    green,
                    0.0,
                    255.0,
                )
            )
        ),
        int(
            round(
                _clamp(
                    blue,
                    0.0,
                    255.0,
                )
            )
        ),
    )


class ReferenceRasterizer:
    """Bounded deterministic triangle rasterizer with real fragment tests."""

    def __init__(
        self,
        config: RasterConfig,
    ) -> None:
        self.config = config
        pixel_count = (
            config.width
            * config.height
        )
        if (
            pixel_count
            > MAX_RASTER_PIXELS
        ):
            raise GameEngineLabError(
                "raster pixel budget exceeded"
            )

    def render(
        self,
        triangles: Iterable[
            RenderTriangle
        ],
    ) -> RasterFrame:
        values = tuple(
            triangles
        )
        if (
            len(values)
            > MAX_RASTER_TRIANGLES
        ):
            raise GameEngineLabError(
                "raster triangle budget exceeded"
            )

        clipped: list[
            RenderTriangle
        ] = []
        clipped_count = 0
        for triangle in values:
            pieces = clip_triangle(
                triangle,
                self.config.near,
                self.config.far,
            )
            if (
                len(pieces) != 1
                or (
                    pieces
                    and pieces[0]
                    != triangle
                )
            ):
                clipped_count += 1
            clipped.extend(pieces)

        prepared: list[
            _PreparedTriangle
        ] = []
        culled = 0
        for triangle in clipped:
            item = _prepare(
                triangle,
                self.config,
            )
            if item is None:
                culled += 1
                continue
            prepared.append(
                item
            )

        if (
            self.config.pipeline
            is RasterPipeline.PAINTER
        ):
            # Back-to-front ordering models painter semantics. Stable tie
            # breakers make coplanar content deterministic.
            prepared.sort(
                key=lambda value: (
                    -value.average_depth,
                    value.object_id,
                    value.material,
                    value.shader,
                )
            )

        width = self.config.width
        height = self.config.height
        count = (
            width * height
        )
        colors = bytearray(
            count * 3
        )
        materials = [
            -1
            for _ in range(
                count
            )
        ]
        depths = [
            math.inf
            for _ in range(
                count
            )
        ]
        touched = [
            0
            for _ in range(
                count
            )
        ]
        shaded = 0
        depth_rejected = 0
        overdraw = 0
        rasterized = 0

        for triangle in prepared:
            v0, v1, v2 = (
                triangle.screen
            )
            area = _edge(
                v0.x,
                v0.y,
                v1.x,
                v1.y,
                v2.x,
                v2.y,
            )
            if abs(area) <= 1e-9:
                continue
            min_x = max(
                0,
                int(
                    math.floor(
                        min(
                            v0.x,
                            v1.x,
                            v2.x,
                        )
                    )
                ),
            )
            max_x = min(
                width - 1,
                int(
                    math.ceil(
                        max(
                            v0.x,
                            v1.x,
                            v2.x,
                        )
                    )
                ),
            )
            min_y = max(
                0,
                int(
                    math.floor(
                        min(
                            v0.y,
                            v1.y,
                            v2.y,
                        )
                    )
                ),
            )
            max_y = min(
                height - 1,
                int(
                    math.ceil(
                        max(
                            v0.y,
                            v1.y,
                            v2.y,
                        )
                    )
                ),
            )
            if (
                max_x < min_x
                or max_y < min_y
            ):
                continue

            drew_any = False
            for y in range(
                min_y,
                max_y + 1,
            ):
                py = (
                    y + 0.5
                )
                for x in range(
                    min_x,
                    max_x + 1,
                ):
                    px = (
                        x + 0.5
                    )
                    w0 = _edge(
                        v1.x,
                        v1.y,
                        v2.x,
                        v2.y,
                        px,
                        py,
                    )
                    w1 = _edge(
                        v2.x,
                        v2.y,
                        v0.x,
                        v0.y,
                        px,
                        py,
                    )
                    w2 = _edge(
                        v0.x,
                        v0.y,
                        v1.x,
                        v1.y,
                        px,
                        py,
                    )
                    if area > 0:
                        inside = (
                            w0 >= 0
                            and w1 >= 0
                            and w2 >= 0
                        )
                    else:
                        inside = (
                            w0 <= 0
                            and w1 <= 0
                            and w2 <= 0
                        )
                    if not inside:
                        continue
                    w0 /= area
                    w1 /= area
                    w2 /= area

                    reciprocal_depth = (
                        w0
                        * v0.reciprocal_z
                        + w1
                        * v1.reciprocal_z
                        + w2
                        * v2.reciprocal_z
                    )
                    if (
                        reciprocal_depth
                        <= 1e-12
                    ):
                        continue
                    depth = (
                        1.0
                        / reciprocal_depth
                    )
                    index = (
                        y * width
                        + x
                    )
                    if touched[index]:
                        overdraw += 1
                    touched[index] += 1

                    depth_test = (
                        self.config.pipeline
                        is not RasterPipeline.PAINTER
                    )
                    if (
                        depth_test
                        and depth
                        >= depths[index]
                    ):
                        depth_rejected += 1
                        continue

                    color = _shade(
                        triangle,
                        depth,
                        self.config,
                    )
                    offset = (
                        index * 3
                    )
                    colors[offset] = (
                        color[0]
                    )
                    colors[
                        offset + 1
                    ] = color[1]
                    colors[
                        offset + 2
                    ] = color[2]
                    materials[index] = (
                        triangle.material
                    )
                    depths[index] = (
                        depth
                    )
                    shaded += 1
                    drew_any = True
            if drew_any:
                rasterized += 1

        covered_indices = [
            index
            for index, material
            in enumerate(materials)
            if material >= 0
        ]
        finite_depths = [
            depths[index]
            for index
            in covered_indices
            if math.isfinite(
                depths[index]
            )
        ]
        histogram: dict[
            int,
            int,
        ] = {}
        for index in covered_indices:
            material = (
                materials[index]
            )
            histogram[material] = (
                histogram.get(
                    material,
                    0,
                )
                + 1
            )

        depth_bytes = bytearray()
        for depth in depths:
            if math.isfinite(depth):
                quantized = int(
                    round(
                        _clamp(
                            (
                                depth
                                - self.config.near
                            )
                            / (
                                self.config.far
                                - self.config.near
                            ),
                            0.0,
                            1.0,
                        )
                        * 16_777_215
                    )
                )
            else:
                quantized = (
                    16_777_215
                )
            depth_bytes.extend(
                (
                    (
                        quantized
                        >> 16
                    )
                    & 0xFF,
                    (
                        quantized
                        >> 8
                    )
                    & 0xFF,
                    quantized
                    & 0xFF,
                )
            )

        color_digest = (
            hashlib.sha256(
                bytes(colors)
            ).hexdigest()
        )
        depth_digest = (
            hashlib.sha256(
                bytes(depth_bytes)
            ).hexdigest()
        )
        stats = RasterStats(
            submitted_triangles=
                len(values),
            clipped_triangles=
                clipped_count,
            culled_triangles=culled,
            rasterized_triangles=
                rasterized,
            covered_pixels=
                len(
                    covered_indices
                ),
            shaded_fragments=shaded,
            depth_rejected_fragments=
                depth_rejected,
            overdraw_fragments=
                overdraw,
            min_depth=(
                round(
                    min(
                        finite_depths
                    ),
                    8,
                )
                if finite_depths
                else None
            ),
            max_depth=(
                round(
                    max(
                        finite_depths
                    ),
                    8,
                )
                if finite_depths
                else None
            ),
        )
        histogram_tuple = tuple(
            sorted(
                histogram.items()
            )
        )
        identity = (
            f"{self.config.pipeline.value}|"
            f"{width}x{height}|"
            f"{color_digest}|"
            f"{depth_digest}|"
            f"{stats}|"
            f"{histogram_tuple}"
        )
        return RasterFrame(
            width,
            height,
            hashlib.sha256(
                identity.encode(
                    "utf-8"
                )
            ).hexdigest(),
            color_digest,
            depth_digest,
            stats,
            histogram_tuple,
        )


def render_reference_scene(
    triangles: Iterable[
        RenderTriangle
    ],
    *,
    width: int,
    height: int,
    near: float,
    far: float,
    fov_y_deg: float,
    pipeline: RasterPipeline,
) -> RasterFrame:
    return ReferenceRasterizer(
        RasterConfig(
            width=width,
            height=height,
            near=near,
            far=far,
            fov_y_deg=fov_y_deg,
            pipeline=pipeline,
        )
    ).render(
        triangles
    )
