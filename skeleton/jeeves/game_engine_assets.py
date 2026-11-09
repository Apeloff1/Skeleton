"""Deterministic asset compiler for Jeeves historical game engines.

The engine laboratory owns runtime-era semantics while skeleton.forge.hardware
owns the broader Forge hardware catalog. This module does not replace that
catalog. It compiles bounded, engine-facing asset recipes into deterministic
text artifacts that can live inside VirtualFileTree sandboxes.

The compiler never executes source payloads. Inputs are typed recipes and all
outputs are canonical JSON with SHA-256 identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import (
    RoutedEngineSandbox,
)

MAX_ASSET_RECIPES = 64
MAX_ASSET_ID = 64
MAX_METADATA_ITEMS = 32
_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class AssetKind(str, Enum):
    PRIMITIVE = "primitive"
    VECTOR = "vector"
    SPRITE = "sprite"
    TILESET = "tileset"
    MESH = "mesh"
    TEXTURE = "texture"
    MATERIAL = "material"
    AUDIO = "audio"
    ANIMATION = "animation"


@dataclass(frozen=True, slots=True)
class SourceAsset:
    asset_id: str
    kind: AssetKind
    width: int = 1
    height: int = 1
    colors: int = 1
    triangles: int = 0
    sample_rate: int = 0
    channels: int = 0
    frames: int = 1
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _ASSET_ID_RE.fullmatch(self.asset_id):
            raise GameEngineLabError(
                "asset id must use bounded alphanumeric path-safe characters"
            )
        if not isinstance(self.kind, AssetKind):
            object.__setattr__(
                self,
                "kind",
                AssetKind(str(self.kind)),
            )
        numeric = {
            "width": self.width,
            "height": self.height,
            "colors": self.colors,
            "triangles": self.triangles,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frames": self.frames,
        }
        for name, value in numeric.items():
            if type(value) is not int or value < 0:
                raise GameEngineLabError(
                    f"asset {name} must be a non-negative integer"
                )
        if self.width < 1 or self.height < 1:
            raise GameEngineLabError(
                "asset dimensions must be positive"
            )
        if self.colors < 1 or self.frames < 1:
            raise GameEngineLabError(
                "asset colors and frames must be positive"
            )
        if len(self.metadata) > MAX_METADATA_ITEMS:
            raise GameEngineLabError(
                "asset metadata exceeds item limit"
            )
        seen: set[str] = set()
        for key, value in self.metadata:
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or not key
                or len(key) > 64
                or len(value) > 256
            ):
                raise GameEngineLabError(
                    "asset metadata must contain bounded text pairs"
                )
            if key in seen:
                raise GameEngineLabError(
                    "asset metadata keys must be unique"
                )
            seen.add(key)


@dataclass(frozen=True, slots=True)
class EraAssetPolicy:
    era: EngineEra
    allowed: tuple[AssetKind, ...]
    palette_limit: int
    max_dimension: int
    triangle_limit: int
    sample_rate: int
    audio_channels: int
    animation_frames: int
    texture_format: str
    mesh_format: str
    audio_format: str
    storage_budget_kib: int

    def __post_init__(self) -> None:
        if (
            self.palette_limit < 1
            or self.max_dimension < 1
            or self.sample_rate < 1
            or self.audio_channels < 1
            or self.animation_frames < 1
            or self.storage_budget_kib < 1
        ):
            raise GameEngineLabError(
                "asset policy limits must be positive"
            )
        if self.triangle_limit < 0:
            raise GameEngineLabError(
                "triangle limit cannot be negative"
            )


def _policy(
    era: EngineEra,
    allowed: tuple[AssetKind, ...],
    palette: int,
    dimension: int,
    triangles: int,
    sample_rate: int,
    channels: int,
    frames: int,
    texture_format: str,
    mesh_format: str,
    audio_format: str,
    storage_kib: int,
) -> EraAssetPolicy:
    return EraAssetPolicy(
        era,
        allowed,
        palette,
        dimension,
        triangles,
        sample_rate,
        channels,
        frames,
        texture_format,
        mesh_format,
        audio_format,
        storage_kib,
    )


ERA_ASSET_POLICIES: Mapping[EngineEra, EraAssetPolicy] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        (
            AssetKind.PRIMITIVE,
            AssetKind.AUDIO,
        ),
        2,
        256,
        0,
        8_000,
        1,
        1,
        "1bit_scanline",
        "scanline_primitive",
        "square_pulse",
        16,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        (
            AssetKind.PRIMITIVE,
            AssetKind.VECTOR,
            AssetKind.SPRITE,
            AssetKind.AUDIO,
        ),
        16,
        256,
        0,
        11_025,
        3,
        8,
        "indexed_sprite",
        "vector_list",
        "tone_noise",
        64,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        (
            AssetKind.SPRITE,
            AssetKind.TILESET,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        64,
        64,
        0,
        11_025,
        4,
        32,
        "indexed_2bpp",
        "none",
        "chiptune",
        1_024,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        (
            AssetKind.SPRITE,
            AssetKind.TILESET,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        512,
        128,
        0,
        32_000,
        8,
        128,
        "indexed_4bpp",
        "none",
        "pcm8_adpcm",
        6_144,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        65_536,
        256,
        3_000,
        32_000,
        8,
        256,
        "rgb555",
        "indexed_triangles",
        "midi_adpcm",
        665_600,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        16_777_216,
        512,
        10_000,
        44_100,
        16,
        512,
        "rgba8888",
        "vertex_index",
        "adpcm",
        1_433_600,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        16_777_216,
        1_024,
        30_000,
        48_000,
        32,
        1_024,
        "dxt_rgba",
        "vertex_index_skin",
        "adpcm_pcm",
        4_812_800,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        16_777_216,
        2_048,
        50_000,
        48_000,
        64,
        2_048,
        "bcn_hdr",
        "indexed_skin_lod",
        "pcm_surround",
        52_428_800,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        1_073_741_824,
        4_096,
        250_000,
        48_000,
        128,
        4_096,
        "bc7_pbr",
        "streamed_lod",
        "streamed_spatial",
        104_857_600,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        (
            AssetKind.SPRITE,
            AssetKind.MESH,
            AssetKind.TEXTURE,
            AssetKind.MATERIAL,
            AssetKind.AUDIO,
            AssetKind.ANIMATION,
        ),
        1_073_741_824,
        8_192,
        10_000_000,
        96_000,
        256,
        8_192,
        "bc7_virtual",
        "meshlet_virtual",
        "object_spatial",
        157_286_400,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        tuple(AssetKind),
        4_294_967_296,
        16_384,
        100_000_000,
        192_000,
        512,
        16_384,
        "virtual_neural_hybrid",
        "micropoly_cluster",
        "path_spatial_object",
        524_288_000,
    ),
}


def asset_policy(
    era: EngineEra | str,
) -> EraAssetPolicy:
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
    return ERA_ASSET_POLICIES[key]


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _pow2_floor(
    value: int,
) -> int:
    if value <= 1:
        return 1
    return 1 << (value.bit_length() - 1)


@dataclass(frozen=True, slots=True)
class CompiledAsset:
    asset_id: str
    kind: AssetKind
    era: EngineEra
    format: str
    width: int
    height: int
    colors: int
    triangles: int
    sample_rate: int
    channels: int
    frames: int
    estimated_bytes: int
    source_digest: str
    digest: str

    def document(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind.value,
            "engine_era": self.era.value,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "colors": self.colors,
            "triangles": self.triangles,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frames": self.frames,
            "estimated_bytes": self.estimated_bytes,
            "source_digest": self.source_digest,
            "digest": self.digest,
        }


def _source_document(
    source: SourceAsset,
) -> dict[str, object]:
    return {
        "asset_id": source.asset_id,
        "kind": source.kind.value,
        "width": source.width,
        "height": source.height,
        "colors": source.colors,
        "triangles": source.triangles,
        "sample_rate": source.sample_rate,
        "channels": source.channels,
        "frames": source.frames,
        "metadata": list(source.metadata),
    }


def _format_for(
    source: SourceAsset,
    policy: EraAssetPolicy,
) -> str:
    if source.kind in {
        AssetKind.PRIMITIVE,
        AssetKind.VECTOR,
        AssetKind.MESH,
    }:
        return policy.mesh_format
    if source.kind in {
        AssetKind.SPRITE,
        AssetKind.TILESET,
        AssetKind.TEXTURE,
        AssetKind.MATERIAL,
    }:
        return policy.texture_format
    if source.kind is AssetKind.AUDIO:
        return policy.audio_format
    if source.kind is AssetKind.ANIMATION:
        return "frame_sequence"
    raise GameEngineLabError(
        f"unsupported asset kind: {source.kind.value}"
    )


def _estimated_bytes(
    source: SourceAsset,
    *,
    width: int,
    height: int,
    colors: int,
    triangles: int,
    sample_rate: int,
    channels: int,
    frames: int,
) -> int:
    if source.kind in {
        AssetKind.PRIMITIVE,
        AssetKind.VECTOR,
    }:
        return max(
            16,
            triangles * 12
            + width
            + height,
        )
    if source.kind in {
        AssetKind.SPRITE,
        AssetKind.TILESET,
        AssetKind.TEXTURE,
        AssetKind.MATERIAL,
    }:
        bits_per_pixel = max(
            1,
            math.ceil(
                math.log2(
                    max(2, colors)
                )
            ),
        )
        return max(
            16,
            (
                width
                * height
                * bits_per_pixel
                * max(1, frames)
                + 7
            )
            // 8,
        )
    if source.kind is AssetKind.MESH:
        return max(
            32,
            triangles * 3 * 24,
        )
    if source.kind is AssetKind.AUDIO:
        seconds = max(
            1.0 / 60.0,
            frames / 60.0,
        )
        return max(
            32,
            int(
                sample_rate
                * channels
                * seconds
            ),
        )
    if source.kind is AssetKind.ANIMATION:
        return max(
            32,
            frames * 32,
        )
    return 32


class EraAssetCompiler:
    """Compile bounded semantic recipes to deterministic era artifacts."""

    def compile(
        self,
        era: EngineEra | str,
        source: SourceAsset,
    ) -> CompiledAsset:
        policy = asset_policy(era)
        if source.kind not in policy.allowed:
            raise GameEngineLabError(
                f"{source.kind.value} assets are unavailable in {policy.era.value}"
            )

        width = min(
            source.width,
            policy.max_dimension,
        )
        height = min(
            source.height,
            policy.max_dimension,
        )
        # Pixel/tile generations use power-of-two asset envelopes. Later
        # engines retain arbitrary dimensions up to the era cap.
        if policy.era in {
            EngineEra.PONG,
            EngineEra.ARCADE,
            EngineEra.EIGHT_BIT,
            EngineEra.SIXTEEN_BIT,
            EngineEra.EARLY_3D,
            EngineEra.FIXED_3D,
        }:
            width = _pow2_floor(width)
            height = _pow2_floor(height)

        colors = min(
            source.colors,
            policy.palette_limit,
        )
        triangles = min(
            source.triangles,
            policy.triangle_limit,
        )
        sample_rate = (
            min(
                source.sample_rate
                or policy.sample_rate,
                policy.sample_rate,
            )
            if source.kind is AssetKind.AUDIO
            else 0
        )
        channels = (
            min(
                max(1, source.channels),
                policy.audio_channels,
            )
            if source.kind is AssetKind.AUDIO
            else 0
        )
        frames = min(
            source.frames,
            policy.animation_frames,
        )
        source_document = _source_document(
            source
        )
        source_digest = _sha(
            source_document
        )
        format_name = _format_for(
            source,
            policy,
        )
        estimated_bytes = _estimated_bytes(
            source,
            width=width,
            height=height,
            colors=colors,
            triangles=triangles,
            sample_rate=sample_rate,
            channels=channels,
            frames=frames,
        )
        identity = {
            "asset_id": source.asset_id,
            "kind": source.kind.value,
            "engine_era": policy.era.value,
            "format": format_name,
            "width": width,
            "height": height,
            "colors": colors,
            "triangles": triangles,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": frames,
            "estimated_bytes": estimated_bytes,
            "source_digest": source_digest,
        }
        return CompiledAsset(
            source.asset_id,
            source.kind,
            policy.era,
            format_name,
            width,
            height,
            colors,
            triangles,
            sample_rate,
            channels,
            frames,
            estimated_bytes,
            source_digest,
            _sha(identity),
        )

    def compile_all(
        self,
        era: EngineEra | str,
        sources: Iterable[SourceAsset],
    ) -> tuple[CompiledAsset, ...]:
        values = tuple(sources)
        if len(values) > MAX_ASSET_RECIPES:
            raise GameEngineLabError(
                "asset recipe count exceeds compiler limit"
            )
        ids = [
            source.asset_id
            for source in values
        ]
        if len(ids) != len(set(ids)):
            raise GameEngineLabError(
                "asset ids must be unique"
            )
        compiled = tuple(
            self.compile(
                era,
                source,
            )
            for source in values
        )
        policy = asset_policy(era)
        total = sum(
            asset.estimated_bytes
            for asset in compiled
        )
        if total > (
            policy.storage_budget_kib
            * 1024
        ):
            raise GameEngineLabError(
                "compiled asset set exceeds era storage budget"
            )
        return tuple(
            sorted(
                compiled,
                key=lambda asset:
                    (
                        asset.kind.value,
                        asset.asset_id,
                    ),
            )
        )


@dataclass(frozen=True, slots=True)
class AssetBuild:
    era: EngineEra
    assets: tuple[CompiledAsset, ...]
    manifest_digest: str
    total_estimated_bytes: int

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine_era": self.era.value,
            "asset_count": len(self.assets),
            "total_estimated_bytes":
                self.total_estimated_bytes,
            "assets": [
                asset.document()
                for asset in self.assets
            ],
            "manifest_digest":
                self.manifest_digest,
        }


def compile_asset_build(
    era: EngineEra | str,
    sources: Iterable[SourceAsset],
    *,
    compiler: EraAssetCompiler | None = None,
) -> AssetBuild:
    active = compiler or EraAssetCompiler()
    compiled = active.compile_all(
        era,
        sources,
    )
    key = (
        era
        if isinstance(era, EngineEra)
        else EngineEra(str(era))
    )
    body = {
        "schema_version": 1,
        "engine_era": key.value,
        "assets": [
            asset.document()
            for asset in compiled
        ],
    }
    return AssetBuild(
        key,
        compiled,
        _sha(body),
        sum(
            asset.estimated_bytes
            for asset in compiled
        ),
    )


def _asset_extension(
    asset: CompiledAsset,
) -> str:
    mapping = {
        AssetKind.PRIMITIVE: "prim.json",
        AssetKind.VECTOR: "vec.json",
        AssetKind.SPRITE: "sprite.json",
        AssetKind.TILESET: "tiles.json",
        AssetKind.MESH: "mesh.json",
        AssetKind.TEXTURE: "tex.json",
        AssetKind.MATERIAL: "mat.json",
        AssetKind.AUDIO: "audio.json",
        AssetKind.ANIMATION: "anim.json",
    }
    return mapping[asset.kind]


def asset_build_patches(
    build: AssetBuild,
) -> tuple[SandboxPatch, ...]:
    manifest = build.manifest()
    patches: list[SandboxPatch] = [
        SandboxPatch(
            "assets/compiled/manifest.json",
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    ]
    for asset in build.assets:
        path = (
            "assets/compiled/"
            + asset.asset_id
            + "."
            + _asset_extension(asset)
        )
        patches.append(
            SandboxPatch(
                path,
                json.dumps(
                    asset.document(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        )
    return tuple(patches)


def canonical_asset_patches(
    sandbox: RoutedEngineSandbox,
    sources: Iterable[SourceAsset],
    *,
    compiler: EraAssetCompiler | None = None,
) -> tuple[SandboxPatch, ...]:
    """Repair compiled asset inventory exactly to the deterministic source build."""

    build = compile_asset_build(
        sandbox.era,
        tuple(sources),
        compiler=compiler,
    )
    expected = {
        patch.path: patch.content
        for patch in asset_build_patches(
            build
        )
    }
    existing = {
        path
        for path in sandbox.tree.files
        if path.startswith(
            "assets/compiled/"
        )
    }
    patches: list[SandboxPatch] = []
    for path in sorted(
        set(expected) | existing
    ):
        wanted = expected.get(path)
        try:
            current = sandbox.tree.read(
                path
            )
        except GameEngineLabError:
            current = None
        if wanted is None:
            patches.append(
                SandboxPatch(
                    path,
                    None,
                    sandbox.tree.file_digest(
                        path
                    ),
                )
            )
        elif current != wanted:
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


def attach_asset_build(
    sandbox: RoutedEngineSandbox,
    sources: Iterable[SourceAsset],
    *,
    compiler: EraAssetCompiler | None = None,
) -> RoutedEngineSandbox:
    build = compile_asset_build(
        sandbox.era,
        sources,
        compiler=compiler,
    )
    guarded = tuple(
        SandboxPatch(
            patch.path,
            patch.content,
            sandbox.tree.file_digest(
                patch.path
            ),
        )
        for patch
        in asset_build_patches(
            build
        )
    )
    return sandbox.apply(
        guarded
    )


@dataclass(frozen=True, slots=True)
class AssetProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AssetQualityReport:
    era: EngineEra
    probes: tuple[AssetProbe, ...]

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


class AssetCompilerAdversary:
    """Recompile, tamper-check, and budget-check a compiled asset build."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        sources: Iterable[SourceAsset],
    ) -> AssetQualityReport:
        source_values = tuple(
            sources
        )
        compiler = EraAssetCompiler()
        probes: list[AssetProbe] = []
        try:
            expected = compile_asset_build(
                sandbox.era,
                source_values,
                compiler=compiler,
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "assets/compiled/manifest.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            return AssetQualityReport(
                sandbox.era,
                (
                    AssetProbe(
                        "manifest",
                        False,
                        str(exc),
                    ),
                    AssetProbe(
                        "inventory",
                        False,
                        "asset build unavailable",
                    ),
                    AssetProbe(
                        "reproducibility",
                        False,
                        "asset build unavailable",
                    ),
                    AssetProbe(
                        "integrity",
                        False,
                        "asset build unavailable",
                    ),
                    AssetProbe(
                        "budget",
                        False,
                        "asset build unavailable",
                    ),
                ),
            )

        manifest_ok = (
            manifest.get(
                "schema_version"
            )
            == 1
            and manifest.get(
                "engine_era"
            )
            == sandbox.era.value
            and manifest.get(
                "manifest_digest"
            )
            == expected.manifest_digest
            and manifest.get(
                "asset_count"
            )
            == len(
                expected.assets
            )
            and manifest.get(
                "total_estimated_bytes"
            )
            == expected.total_estimated_bytes
            and manifest.get(
                "assets"
            )
            == [
                asset.document()
                for asset
                in expected.assets
            ]
        )
        expected_paths = {
            patch.path
            for patch
            in asset_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path
            in sandbox.tree.files
            if path.startswith(
                "assets/compiled/"
            )
        }
        inventory_ok = (
            actual_paths
            == expected_paths
        )
        probes.append(
            AssetProbe(
                "inventory",
                inventory_ok,
                (
                    "compiled inventory exact"
                    if inventory_ok
                    else "compiled inventory mismatch"
                ),
            )
        )

        probes.append(
            AssetProbe(
                "manifest",
                manifest_ok,
                (
                    "manifest matches source build"
                    if manifest_ok
                    else "manifest mismatch"
                ),
            )
        )

        second = compile_asset_build(
            sandbox.era,
            source_values,
            compiler=compiler,
        )
        reproducible = (
            expected
            == second
        )
        probes.append(
            AssetProbe(
                "reproducibility",
                reproducible,
                "deterministic compile",
            )
        )

        integrity = True
        for asset in expected.assets:
            path = (
                "assets/compiled/"
                + asset.asset_id
                + "."
                + _asset_extension(
                    asset
                )
            )
            try:
                payload = json.loads(
                    sandbox.tree.read(
                        path
                    )
                )
            except (
                GameEngineLabError,
                json.JSONDecodeError,
            ):
                integrity = False
                break
            if (
                payload
                != asset.document()
            ):
                integrity = False
                break
        probes.append(
            AssetProbe(
                "integrity",
                integrity,
                (
                    "compiled asset digests match"
                    if integrity
                    else "compiled asset mismatch"
                ),
            )
        )

        budget = (
            expected.total_estimated_bytes
            <= asset_policy(
                sandbox.era
            ).storage_budget_kib
            * 1024
        )
        probes.append(
            AssetProbe(
                "budget",
                budget,
                "era storage budget",
            )
        )
        return AssetQualityReport(
            sandbox.era,
            tuple(probes),
        )


def canonical_asset_sources(
    era: EngineEra | str,
) -> tuple[SourceAsset, ...]:
    """Small deterministic smoke pack valid for the requested era."""

    policy = asset_policy(era)
    candidates = (
        SourceAsset(
            "hero_primitive",
            AssetKind.PRIMITIVE,
            width=32,
            height=32,
            colors=2,
        ),
        SourceAsset(
            "vector_ship",
            AssetKind.VECTOR,
            width=64,
            height=64,
            colors=8,
        ),
        SourceAsset(
            "hero_sprite",
            AssetKind.SPRITE,
            width=96,
            height=96,
            colors=256,
            frames=12,
        ),
        SourceAsset(
            "world_tiles",
            AssetKind.TILESET,
            width=128,
            height=128,
            colors=512,
            frames=4,
        ),
        SourceAsset(
            "hero_mesh",
            AssetKind.MESH,
            width=1,
            height=1,
            colors=1,
            triangles=80_000,
        ),
        SourceAsset(
            "hero_texture",
            AssetKind.TEXTURE,
            width=4_096,
            height=4_096,
            colors=16_777_216,
        ),
        SourceAsset(
            "hero_material",
            AssetKind.MATERIAL,
            width=512,
            height=512,
            colors=65_536,
        ),
        SourceAsset(
            "theme_audio",
            AssetKind.AUDIO,
            sample_rate=96_000,
            channels=8,
            frames=120,
        ),
        SourceAsset(
            "hero_animation",
            AssetKind.ANIMATION,
            frames=240,
        ),
    )
    return tuple(
        source
        for source in candidates
        if source.kind
        in policy.allowed
    )
