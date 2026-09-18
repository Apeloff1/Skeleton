"""Historical game-engine sandboxes for Jeeves.

This is deliberately separate from skeleton.forge.eras. Forge eras describe
gameplay dialects; this module describes the engine technology envelope used
to build and test that game. Sandboxes are in-memory, deterministic, bounded,
snapshot-addressed, and caller-driven. AI output may propose patches, but it
cannot bypass validation or promotion gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

SCHEMA_VERSION = 1
MAX_FILES = 96
MAX_FILE_BYTES = 128_000
MAX_TREE_BYTES = 1_000_000


class GameEngineLabError(ValueError):
    """Fail-closed game-engine laboratory error."""


class EngineEra(str, Enum):
    PONG = "pong_discrete_1972"
    ARCADE = "vector_sprite_1977"
    EIGHT_BIT = "eight_bit_tile_1983"
    SIXTEEN_BIT = "sixteen_bit_raster_1989"
    EARLY_3D = "early_3d_software_1993"
    FIXED_3D = "fixed_function_3d_1996"
    SHADER = "shader_console_2001"
    HD = "hd_programmable_2005"
    OPEN_WORLD = "deferred_open_world_2013"
    MODERN = "data_oriented_modern_2020"
    NEXT = "next_hybrid_2027"


class NumericMode(str, Enum):
    INTEGER = "integer_pixels"
    FIXED8 = "fixed_8_8"
    FIXED16 = "fixed_16_16"
    FLOAT32 = "float32"
    FLOAT64 = "float64"


@dataclass(frozen=True, slots=True)
class EngineEraProfile:
    era: EngineEra
    start_year: int
    end_year: int | None
    render_path: str
    physics_model: str
    entity_model: str
    numeric_mode: NumericMode
    tick_hz: int
    memory_kib: int
    entity_budget: int
    draw_budget: int
    capabilities: tuple[str, ...]
    constraints: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.start_year < 1970:
            raise GameEngineLabError("invalid era start year")
        if self.end_year is not None and self.end_year < self.start_year:
            raise GameEngineLabError("invalid era end year")
        if self.tick_hz <= 0 or self.memory_kib <= 0 or self.entity_budget <= 0 or self.draw_budget <= 0:
            raise GameEngineLabError("era budgets and tick rate must be positive")


def _p(era, start, end, render, physics, entities, numeric, tick, memory, entity_budget, draw_budget, caps, limits):
    return EngineEraProfile(
        era, start, end, render, physics, entities, numeric, tick, memory,
        entity_budget, draw_budget, tuple(caps), tuple(limits)
    )


ERA_PROFILES: Mapping[EngineEra, EngineEraProfile] = MappingProxyType({
    EngineEra.PONG: _p(
        EngineEra.PONG, 1972, 1976, "scanline primitives",
        "2D kinematics and bounds", "fixed slots", NumericMode.INTEGER, 60,
        16, 16, 32, ("aabb", "bounds", "fixed_step", "score"),
        ("integer coordinates", "tiny scene", "no dynamic allocation"),
    ),
    EngineEra.ARCADE: _p(
        EngineEra.ARCADE, 1977, 1982, "vector and sprite command list",
        "2D kinematics and object broadphase", "object table", NumericMode.FIXED8,
        60, 64, 64, 128, ("aabb", "world_wrap", "sprite_priority"),
        ("small RAM", "bounded objects", "single threaded"),
    ),
    EngineEra.EIGHT_BIT: _p(
        EngineEra.EIGHT_BIT, 1983, 1988, "tilemap and sprites",
        "tile collision and fixed-point actors", "paged actor table",
        NumericMode.FIXED8, 60, 128, 96, 192,
        ("tilemap", "aabb", "platformer", "camera_scroll"),
        ("scanline sprite limits", "banked content", "fixed-point math"),
    ),
    EngineEra.SIXTEEN_BIT: _p(
        EngineEra.SIXTEEN_BIT, 1989, 1993, "multiplane raster and sprites",
        "fixed-point 2D rigid-lite", "object pool", NumericMode.FIXED16, 60,
        512, 256, 512, ("parallax", "aabb", "slopes", "object_pool"),
        ("DMA windows", "bounded VRAM", "fixed-point hot paths"),
    ),
    EngineEra.EARLY_3D: _p(
        EngineEra.EARLY_3D, 1993, 1995, "software raster and BSP",
        "AABB world collision", "sector entities", NumericMode.FIXED16, 35,
        4096, 512, 1200, ("bsp", "raycast", "aabb", "sector_portals"),
        ("CPU-bound raster", "coarse collision", "low transform budget"),
    ),
    EngineEra.FIXED_3D: _p(
        EngineEra.FIXED_3D, 1996, 2000, "fixed-function transform light texture",
        "3D rigid-lite and spatial partition", "scene graph objects",
        NumericMode.FLOAT32, 30, 16_384, 1024, 3000,
        ("scene_graph", "frustum_cull", "aabb", "sphere", "raycast"),
        ("state-change cost", "limited texture memory", "coarse rigid bodies"),
    ),
    EngineEra.SHADER: _p(
        EngineEra.SHADER, 2001, 2004, "programmable vertex and pixel shaders",
        "rigid bodies and character controller", "scene graph and managers",
        NumericMode.FLOAT32, 60, 64_000, 4096, 6000,
        ("shaders", "skeletal_animation", "rigid_body", "streaming"),
        ("manual batching", "tight budgets", "platform-specific paths"),
    ),
    EngineEra.HD: _p(
        EngineEra.HD, 2005, 2012, "HDR programmable forward and deferred",
        "constraint rigid bodies and broadphase", "scene graph plus components",
        NumericMode.FLOAT32, 60, 512_000, 20_000, 15_000,
        ("deferred_lighting", "constraints", "streaming", "jobs"),
        ("CPU GPU synchronization", "streaming stalls", "fragmentation"),
    ),
    EngineEra.OPEN_WORLD: _p(
        EngineEra.OPEN_WORLD, 2013, 2019, "PBR deferred and forward-plus",
        "multithread rigid bodies plus nav and vehicles", "streamed components",
        NumericMode.FLOAT32, 60, 8_000_000, 100_000, 50_000,
        ("pbr", "streaming_world", "jobs", "navmesh", "lod"),
        ("frame pacing", "asset streaming", "cross-platform scaling"),
    ),
    EngineEra.MODERN: _p(
        EngineEra.MODERN, 2020, 2026, "GPU-driven PBR and ray features",
        "parallel deterministic islands and rollback", "data-oriented ECS",
        NumericMode.FLOAT32, 120, 16_000_000, 1_000_000, 250_000,
        ("ecs", "gpu_driven", "rollback", "ray_queries", "virtual_geometry"),
        ("content scale", "deterministic parallelism", "latency budgets"),
    ),
    EngineEra.NEXT: _p(
        EngineEra.NEXT, 2027, None, "adaptive neural and analytic hybrid",
        "multi-rate deterministic simulation graph", "schema-first ECS graph",
        NumericMode.FLOAT64, 240, 32_000_000, 5_000_000, 1_000_000,
        ("ecs", "multi_rate", "rollback", "procedural_world", "evidence_gates"),
        ("cross-accelerator reproducibility", "bounded learned components"),
    ),
})


def list_engine_eras() -> tuple[EngineEraProfile, ...]:
    return tuple(ERA_PROFILES[era] for era in EngineEra)


def engine_era_profile(era: EngineEra | str) -> EngineEraProfile:
    try:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    except ValueError as exc:
        raise GameEngineLabError(f"unknown engine era: {era!r}") from exc
    return ERA_PROFILES[key]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GameEngineLabError("sandbox path must be non-empty")
    clean = value.replace(chr(92), "/").strip("/")
    parts = clean.split("/")
    if any(part in {"", ".", ".."} for part in parts) or ":" in parts[0]:
        raise GameEngineLabError(f"unsafe sandbox path: {value!r}")
    return clean


@dataclass(frozen=True, slots=True)
class SandboxPatch:
    path: str
    content: str | None
    expected_file_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        if self.content is not None:
            if not isinstance(self.content, str):
                raise GameEngineLabError("patch content must be text")
            if len(self.content.encode()) > MAX_FILE_BYTES:
                raise GameEngineLabError("patch exceeds file size limit")
        if self.expected_file_digest is not None:
            digest = self.expected_file_digest.lower()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise GameEngineLabError("expected digest must be SHA-256 hex")
            object.__setattr__(self, "expected_file_digest", digest)


@dataclass(frozen=True, slots=True)
class SandboxSnapshot:
    schema_version: int
    era: EngineEra
    sequence: int
    parent_digest: str | None
    tree_digest: str
    files: tuple[tuple[str, str], ...]


class VirtualFileTree:
    __slots__ = ("_files",)

    def __init__(self, files: Mapping[str, str] | None = None) -> None:
        clean: dict[str, str] = {}
        for raw, content in (files or {}).items():
            name = _path(raw)
            if name in clean:
                raise GameEngineLabError(f"duplicate path: {name}")
            if not isinstance(content, str):
                raise GameEngineLabError("sandbox files must contain text")
            if len(content.encode()) > MAX_FILE_BYTES:
                raise GameEngineLabError(f"file too large: {name}")
            clean[name] = content
        if len(clean) > MAX_FILES or sum(len(v.encode()) for v in clean.values()) > MAX_TREE_BYTES:
            raise GameEngineLabError("sandbox tree exceeds bounded capacity")
        self._files = clean

    @property
    def files(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self._files))

    @property
    def digest(self) -> str:
        return _sha(_canonical([(p, _sha(self._files[p])) for p in sorted(self._files)]))

    def read(self, path: str) -> str:
        try:
            return self._files[_path(path)]
        except KeyError as exc:
            raise GameEngineLabError(f"sandbox file not found: {path}") from exc

    def file_digest(self, path: str) -> str | None:
        value = self._files.get(_path(path))
        return None if value is None else _sha(value)

    def apply(self, patches: Iterable[SandboxPatch]) -> "VirtualFileTree":
        out = dict(self._files)
        touched: set[str] = set()
        for patch in patches:
            if patch.path in touched:
                raise GameEngineLabError(f"duplicate patch target: {patch.path}")
            touched.add(patch.path)
            current = out.get(patch.path)
            digest = None if current is None else _sha(current)
            if patch.expected_file_digest is not None and digest != patch.expected_file_digest:
                raise GameEngineLabError(f"stale patch for {patch.path}")
            if patch.content is None:
                if current is None:
                    raise GameEngineLabError(f"cannot delete missing file: {patch.path}")
                del out[patch.path]
            else:
                out[patch.path] = patch.content
        return VirtualFileTree(out)

    def snapshot(self, era: EngineEra, sequence: int, parent_digest: str | None = None) -> SandboxSnapshot:
        if sequence < 0:
            raise GameEngineLabError("snapshot sequence must be non-negative")
        return SandboxSnapshot(
            SCHEMA_VERSION, era, sequence, parent_digest, self.digest,
            tuple((p, self._files[p]) for p in sorted(self._files)),
        )

    @classmethod
    def restore(cls, snapshot: SandboxSnapshot) -> "VirtualFileTree":
        if snapshot.schema_version != SCHEMA_VERSION:
            raise GameEngineLabError("unsupported snapshot schema")
        tree = cls(dict(snapshot.files))
        if tree.digest != snapshot.tree_digest:
            raise GameEngineLabError("snapshot digest mismatch")
        return tree


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float


@dataclass(slots=True)
class Body:
    body_id: str
    position: Vec2
    velocity: Vec2 = Vec2(0.0, 0.0)
    half_extent: Vec2 = Vec2(0.5, 0.5)
    restitution: float = 1.0
    static: bool = False

    def __post_init__(self) -> None:
        if not self.body_id:
            raise GameEngineLabError("body id must be non-empty")
        if self.half_extent.x <= 0 or self.half_extent.y <= 0:
            raise GameEngineLabError("body extents must be positive")
        if not 0 <= self.restitution <= 1:
            raise GameEngineLabError("restitution must be within [0, 1]")


def _q(mode: NumericMode, value: float) -> float:
    if not math.isfinite(value):
        raise GameEngineLabError("physics state must be finite")
    if mode is NumericMode.INTEGER:
        return float(round(value))
    if mode is NumericMode.FIXED8:
        return round(value * 256) / 256
    if mode is NumericMode.FIXED16:
        return round(value * 65536) / 65536
    if mode is NumericMode.FLOAT32:
        return struct.unpack("!f", struct.pack("!f", value))[0]
    return float(value)


class EraPhysicsRuntime:
    """Deterministic fixed-step AABB kernel parameterized by engine era."""

    def __init__(self, profile: EngineEraProfile, width=320.0, height=240.0, gravity=Vec2(0.0, 0.0)):
        if width <= 0 or height <= 0:
            raise GameEngineLabError("world bounds must be positive")
        self.profile = profile
        self.width = float(width)
        self.height = float(height)
        self.gravity = gravity
        self.tick = 0
        self._bodies: dict[str, Body] = {}

    @property
    def bodies(self) -> tuple[Body, ...]:
        return tuple(self._bodies[k] for k in sorted(self._bodies))

    def spawn(self, body: Body) -> None:
        if body.body_id in self._bodies:
            raise GameEngineLabError("duplicate body id")
        if len(self._bodies) >= self.profile.entity_budget:
            raise GameEngineLabError("engine-era entity budget exceeded")
        body.position = Vec2(_q(self.profile.numeric_mode, body.position.x), _q(self.profile.numeric_mode, body.position.y))
        body.velocity = Vec2(_q(self.profile.numeric_mode, body.velocity.x), _q(self.profile.numeric_mode, body.velocity.y))
        self._bodies[body.body_id] = body

    def step(self, count=1) -> None:
        if not isinstance(count, int) or not 1 <= count <= 100_000:
            raise GameEngineLabError("step count out of range")
        dt = 1.0 / self.profile.tick_hz
        for _ in range(count):
            for key in sorted(self._bodies):
                body = self._bodies[key]
                if body.static:
                    continue
                vx = body.velocity.x + self.gravity.x * dt
                vy = body.velocity.y + self.gravity.y * dt
                body.velocity = Vec2(_q(self.profile.numeric_mode, vx), _q(self.profile.numeric_mode, vy))
                body.position = Vec2(
                    _q(self.profile.numeric_mode, body.position.x + vx * dt),
                    _q(self.profile.numeric_mode, body.position.y + vy * dt),
                )
                self._bounds(body)
            self._pairs()
            self.tick += 1

    def _bounds(self, body: Body) -> None:
        px, py = body.position.x, body.position.y
        vx, vy = body.velocity.x, body.velocity.y
        hx, hy = body.half_extent.x, body.half_extent.y
        if px - hx < 0:
            px, vx = hx, abs(vx) * body.restitution
        elif px + hx > self.width:
            px, vx = self.width - hx, -abs(vx) * body.restitution
        if py - hy < 0:
            py, vy = hy, abs(vy) * body.restitution
        elif py + hy > self.height:
            py, vy = self.height - hy, -abs(vy) * body.restitution
        body.position = Vec2(_q(self.profile.numeric_mode, px), _q(self.profile.numeric_mode, py))
        body.velocity = Vec2(_q(self.profile.numeric_mode, vx), _q(self.profile.numeric_mode, vy))

    def _pairs(self) -> None:
        ids = sorted(self._bodies)
        for i, aid in enumerate(ids):
            a = self._bodies[aid]
            for bid in ids[i + 1:]:
                b = self._bodies[bid]
                ox = a.half_extent.x + b.half_extent.x - abs(a.position.x - b.position.x)
                oy = a.half_extent.y + b.half_extent.y - abs(a.position.y - b.position.y)
                if ox <= 0 or oy <= 0 or (a.static and b.static):
                    continue
                axis = "x" if ox <= oy else "y"
                penetration = ox if axis == "x" else oy
                av = a.position.x if axis == "x" else a.position.y
                bv = b.position.x if axis == "x" else b.position.y
                sign = -1.0 if av < bv else 1.0
                self._separate(a, b, penetration, sign, axis)

    def _separate(self, a: Body, b: Body, p: float, sign: float, axis: str) -> None:
        ma = p if b.static else p / 2
        mb = p if a.static else p / 2
        mode = self.profile.numeric_mode
        if not a.static:
            if axis == "x":
                a.position = replace(a.position, x=_q(mode, a.position.x + sign * ma))
                a.velocity = replace(a.velocity, x=_q(mode, -a.velocity.x * a.restitution))
            else:
                a.position = replace(a.position, y=_q(mode, a.position.y + sign * ma))
                a.velocity = replace(a.velocity, y=_q(mode, -a.velocity.y * a.restitution))
        if not b.static:
            if axis == "x":
                b.position = replace(b.position, x=_q(mode, b.position.x - sign * mb))
                b.velocity = replace(b.velocity, x=_q(mode, -b.velocity.x * b.restitution))
            else:
                b.position = replace(b.position, y=_q(mode, b.position.y - sign * mb))
                b.velocity = replace(b.velocity, y=_q(mode, -b.velocity.y * b.restitution))

    def fingerprint(self) -> str:
        return _sha(_canonical({
            "era": self.profile.era.value,
            "tick": self.tick,
            "bodies": [
                (b.body_id, b.position.x, b.position.y, b.velocity.x, b.velocity.y)
                for b in self.bodies
            ],
        }))


REQUIRED_PATHS = frozenset({
    "engine/manifest.json",
    "engine/physics.json",
    "engine/render.json",
    "engine/runtime.py",
    "game/main.scene.json",
    "tests/acceptance.json",
})


def build_engine_file_tree(era: EngineEra | str, gameplay_dialect: str | None = None) -> VirtualFileTree:
    p = engine_era_profile(era)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "engine_era": p.era.value,
        "years": [p.start_year, p.end_year],
        "gameplay_dialect": gameplay_dialect,
        "render_path": p.render_path,
        "physics_model": p.physics_model,
        "entity_model": p.entity_model,
        "numeric_mode": p.numeric_mode.value,
        "tick_hz": p.tick_hz,
        "budgets": {"memory_kib": p.memory_kib, "entities": p.entity_budget, "draw": p.draw_budget},
        "capabilities": list(p.capabilities),
        "constraints": list(p.constraints),
    }
    physics = {
        "tick_hz": p.tick_hz, "numeric_mode": p.numeric_mode.value,
        "ordering": "body_id_lexicographic", "collision": ["bounds", "aabb"], "deterministic": True,
    }
    render = {"path": p.render_path, "draw_budget": p.draw_budget, "stable_order": True}
    scene = {"name": "main", "engine_era": p.era.value, "systems": ["input", "simulation", "render", "audio"]}
    acceptance = {"required": ["tree", "manifest", "snapshot", "tamper", "stale_patch", "replay", "bounds", "collision"]}
    runtime = (
        '"""Generated sandbox facade. Authoritative runtime lives in skeleton.jeeves.game_engine_lab."""\n'
        f'ENGINE_ERA = "{p.era.value}"\nTICK_HZ = {p.tick_hz}\nNUMERIC_MODE = "{p.numeric_mode.value}"\n'
    )
    return VirtualFileTree({
        "engine/manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "engine/physics.json": json.dumps(physics, indent=2, sort_keys=True) + "\n",
        "engine/render.json": json.dumps(render, indent=2, sort_keys=True) + "\n",
        "engine/runtime.py": runtime,
        "game/main.scene.json": json.dumps(scene, indent=2, sort_keys=True) + "\n",
        "tests/acceptance.json": json.dumps(acceptance, indent=2, sort_keys=True) + "\n",
    })


@dataclass(frozen=True, slots=True)
class Probe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    era: EngineEra
    tree_digest: str
    probes: tuple[Probe, ...]

    @property
    def score(self) -> float:
        return sum(p.passed for p in self.probes) / max(1, len(self.probes))

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(p.passed for p in self.probes)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.probes if not p.passed)


class EngineAdversary:
    def evaluate(self, profile: EngineEraProfile, tree: VirtualFileTree) -> QualityReport:
        probes: list[Probe] = []
        missing = sorted(REQUIRED_PATHS - set(tree.files))
        probes.append(Probe("tree", not missing, "complete" if not missing else f"missing={missing}"))
        try:
            m = json.loads(tree.read("engine/manifest.json"))
            ok = (
                m.get("schema_version") == SCHEMA_VERSION
                and m.get("engine_era") == profile.era.value
                and m.get("tick_hz") == profile.tick_hz
                and m.get("numeric_mode") == profile.numeric_mode.value
                and m.get("budgets", {}).get("entities") == profile.entity_budget
            )
        except (GameEngineLabError, json.JSONDecodeError, AttributeError):
            ok = False
        probes.append(Probe("manifest", ok, "profile match" if ok else "profile mismatch"))

        snap = tree.snapshot(profile.era, 0)
        probes.append(Probe("snapshot", VirtualFileTree.restore(snap).digest == tree.digest, "digest roundtrip"))
        forged_files = list(snap.files)
        if forged_files:
            name, content = forged_files[0]
            forged_files[0] = (name, content + "forged")
        forged = replace(snap, files=tuple(forged_files))
        try:
            VirtualFileTree.restore(forged)
            tamper = False
        except GameEngineLabError:
            tamper = True
        probes.append(Probe("tamper", tamper, "tamper rejected" if tamper else "tamper accepted"))

        try:
            tree.apply([SandboxPatch("engine/manifest.json", tree.read("engine/manifest.json"), "0" * 64)])
            stale = False
        except GameEngineLabError:
            stale = True
        probes.append(Probe("stale_patch", stale, "stale patch rejected" if stale else "stale patch accepted"))

        def fixture():
            r = EraPhysicsRuntime(profile, 320, 200)
            r.spawn(Body("ball", Vec2(20, 40), Vec2(180, 90), Vec2(2, 2)))
            r.spawn(Body("wall", Vec2(160, 100), Vec2(0.0, 0.0), Vec2(8, 30), static=True))
            return r

        a, b = fixture(), fixture()
        a.step(240)
        b.step(240)
        probes.append(Probe("replay", a.fingerprint() == b.fingerprint(), "deterministic replay"))
        bounded = all(
            body.half_extent.x <= body.position.x <= a.width - body.half_extent.x
            and body.half_extent.y <= body.position.y <= a.height - body.half_extent.y
            for body in a.bodies
        )
        probes.append(Probe("bounds", bounded, "world containment"))

        pair = EraPhysicsRuntime(profile, 100, 100)
        pair.spawn(Body("a", Vec2(45, 50), Vec2(20, 0), Vec2(6, 6)))
        pair.spawn(Body("b", Vec2(55, 50), Vec2(-20, 0), Vec2(6, 6)))
        pair.step()
        pa, pb = pair.bodies
        ox = pa.half_extent.x + pb.half_extent.x - abs(pa.position.x - pb.position.x)
        oy = pa.half_extent.y + pb.half_extent.y - abs(pa.position.y - pb.position.y)
        probes.append(Probe("collision", ox <= 0.001 or oy <= 0.001, "pair separation"))
        return QualityReport(profile.era, tree.digest, tuple(probes))


@dataclass(frozen=True, slots=True)
class EngineSandbox:
    profile: EngineEraProfile
    tree: VirtualFileTree
    gameplay_dialect: str | None = None
    sequence: int = 0
    snapshots: tuple[SandboxSnapshot, ...] = ()

    def snapshot(self) -> "EngineSandbox":
        parent = self.snapshots[-1].tree_digest if self.snapshots else None
        snap = self.tree.snapshot(self.profile.era, self.sequence, parent)
        return replace(self, sequence=self.sequence + 1, snapshots=self.snapshots + (snap,))

    def restore(self, index=-1) -> "EngineSandbox":
        if not self.snapshots:
            raise GameEngineLabError("sandbox has no snapshots")
        try:
            snap = self.snapshots[index]
        except IndexError as exc:
            raise GameEngineLabError("snapshot index out of range") from exc
        if snap.era is not self.profile.era:
            raise GameEngineLabError("snapshot era mismatch")
        return replace(self, tree=VirtualFileTree.restore(snap), sequence=snap.sequence + 1)

    def apply(self, patches: Iterable[SandboxPatch]) -> "EngineSandbox":
        return replace(self, tree=self.tree.apply(patches))

    def runtime(self, width=320.0, height=240.0, gravity=Vec2(0.0, 0.0)) -> EraPhysicsRuntime:
        return EraPhysicsRuntime(self.profile, width, height, gravity)


@dataclass(frozen=True, slots=True)
class ImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    remaining_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImprovementResult:
    sandbox: EngineSandbox
    report: QualityReport
    rounds: tuple[ImprovementRound, ...]
    promoted: bool


Improver = Callable[[EngineSandbox, QualityReport], Iterable[SandboxPatch]]


class GameEngineEraLab:
    """Jeeves-facing registry, sandbox factory, evaluator and promotion loop."""

    def __init__(self, adversary: EngineAdversary | None = None):
        self.adversary = adversary or EngineAdversary()

    def create(self, era: EngineEra | str, gameplay_dialect: str | None = None) -> EngineSandbox:
        profile = engine_era_profile(era)
        return EngineSandbox(
            profile, build_engine_file_tree(profile.era, gameplay_dialect), gameplay_dialect
        ).snapshot()

    def evaluate(self, sandbox: EngineSandbox) -> QualityReport:
        return self.adversary.evaluate(sandbox.profile, sandbox.tree)

    def canonical_repair(self, sandbox: EngineSandbox, report: QualityReport) -> tuple[SandboxPatch, ...]:
        if report.passed or not {"tree", "manifest"}.intersection(report.failed):
            return ()
        canonical = build_engine_file_tree(sandbox.profile.era, sandbox.gameplay_dialect)
        patches = []
        for path in sorted(REQUIRED_PATHS):
            try:
                current = sandbox.tree.read(path)
            except GameEngineLabError:
                current = None
            wanted = canonical.read(path)
            if current != wanted:
                patches.append(SandboxPatch(path, wanted, sandbox.tree.file_digest(path)))
        return tuple(patches)

    def adversarial_improve(
        self,
        sandbox: EngineSandbox,
        target=1.0,
        max_rounds=8,
        improver: Improver | None = None,
    ) -> ImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError("target must be within (0, 1]")
        if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 64:
            raise GameEngineLabError("max_rounds must be within [1, 64]")
        current = sandbox
        report = self.evaluate(current)
        rounds: list[ImprovementRound] = []
        if report.score >= target and report.passed:
            return ImprovementResult(current, report, (), True)
        strategy = improver or self.canonical_repair
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
            rounds.append(ImprovementRound(
                index, current.tree.digest, candidate.tree.digest,
                report.score, next_report.score, accepted, next_report.failed
            ))
            if not accepted:
                break
            current = candidate.snapshot()
            report = next_report
            if report.score >= target and report.passed:
                break
        return ImprovementResult(current, report, tuple(rounds), report.score >= target and report.passed)


def build_game_engine_sandbox(era: EngineEra | str, gameplay_dialect: str | None = None) -> EngineSandbox:
    return GameEngineEraLab().create(era, gameplay_dialect)
