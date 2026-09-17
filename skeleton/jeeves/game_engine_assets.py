"""Era-specific asset and project compiler for Jeeves game-engine sandboxes.

The engine runtimes model how each hardware generation behaves. This module
models how a project is *built* for those generations: primitive tables,
vector lists, palettes/tiles, software-3D BSP data, fixed-function materials,
shader-era programs, HD render assets, streamed cells, data-oriented prefab
tables, and bounded next-era procedural policy descriptors.

All outputs are deterministic text assets inside VirtualFileTree. No generated
Python or model output is executed as authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
    SandboxSnapshot,
    VirtualFileTree,
)
from .game_engine_runtime import (
    EngineFamily,
    ExecutableGameEngineLab,
    RoutedEngineSandbox,
)


class AssetFormatFamily(str, Enum):
    DISCRETE = "discrete_primitives"
    VECTOR = "vector_sprite"
    TILE8 = "tile_palette_8bit"
    RASTER16 = "multiplane_16bit"
    SOFTWARE3D = "software_bsp"
    FIXED3D = "fixed_function_mesh"
    SHADER3D = "programmable_shader"
    HD = "hd_deferred"
    STREAMED = "streamed_pbr"
    GPU = "gpu_data_oriented"
    HYBRID = "bounded_hybrid"


@dataclass(frozen=True, slots=True)
class AssetBudget:
    max_files: int
    max_asset_bytes: int
    max_palette_colors: int
    max_texture_dimension: int
    max_world_cells: int
    max_mesh_vertices: int
    max_audio_channels: int

    def __post_init__(self) -> None:
        values = (
            self.max_files,
            self.max_asset_bytes,
            self.max_palette_colors,
            self.max_texture_dimension,
            self.max_world_cells,
            self.max_mesh_vertices,
            self.max_audio_channels,
        )
        if any(not isinstance(value, int) or value <= 0 for value in values):
            raise GameEngineLabError("asset budgets must be positive integers")


@dataclass(frozen=True, slots=True)
class EraAssetContract:
    era: EngineEra
    format_family: AssetFormatFamily
    budget: AssetBudget
    required_paths: tuple[str, ...]


ERA_ASSET_CONTRACTS: Mapping[EngineEra, EraAssetContract] = {
    EngineEra.PONG: EraAssetContract(
        EngineEra.PONG,
        AssetFormatFamily.DISCRETE,
        AssetBudget(8, 8_192, 2, 1, 1, 8, 1),
        ("assets/primitives.json", "assets/tones.json"),
    ),
    EngineEra.ARCADE: EraAssetContract(
        EngineEra.ARCADE,
        AssetFormatFamily.VECTOR,
        AssetBudget(10, 24_576, 8, 16, 1, 128, 3),
        ("assets/vectors.json", "assets/sprites.json", "assets/tones.json"),
    ),
    EngineEra.EIGHT_BIT: EraAssetContract(
        EngineEra.EIGHT_BIT,
        AssetFormatFamily.TILE8,
        AssetBudget(12, 65_536, 32, 8, 4, 256, 4),
        (
            "assets/palette.json",
            "assets/tiles.json",
            "assets/tilemap.json",
            "assets/apu.json",
        ),
    ),
    EngineEra.SIXTEEN_BIT: EraAssetContract(
        EngineEra.SIXTEEN_BIT,
        AssetFormatFamily.RASTER16,
        AssetBudget(14, 262_144, 256, 16, 8, 2_048, 8),
        (
            "assets/palette.json",
            "assets/tiles16.json",
            "assets/planes.json",
            "assets/pcm_bank.json",
        ),
    ),
    EngineEra.EARLY_3D: EraAssetContract(
        EngineEra.EARLY_3D,
        AssetFormatFamily.SOFTWARE3D,
        AssetBudget(16, 1_048_576, 256, 64, 16, 8_192, 8),
        (
            "assets/bsp.json",
            "assets/software_textures.json",
            "assets/sfx_bank.json",
        ),
    ),
    EngineEra.FIXED_3D: EraAssetContract(
        EngineEra.FIXED_3D,
        AssetFormatFamily.FIXED3D,
        AssetBudget(18, 4_194_304, 256, 256, 16, 32_768, 16),
        (
            "assets/meshes.json",
            "assets/fixed_materials.json",
            "assets/texture_pages.json",
        ),
    ),
    EngineEra.SHADER: EraAssetContract(
        EngineEra.SHADER,
        AssetFormatFamily.SHADER3D,
        AssetBudget(20, 16_777_216, 1_024, 512, 24, 65_536, 32),
        (
            "assets/meshes.json",
            "assets/shader_materials.json",
            "assets/skeletons.json",
        ),
    ),
    EngineEra.HD: EraAssetContract(
        EngineEra.HD,
        AssetFormatFamily.HD,
        AssetBudget(24, 134_217_728, 4_096, 2_048, 32, 250_000, 64),
        (
            "assets/meshes.json",
            "assets/pbr_materials.json",
            "assets/render_targets.json",
        ),
    ),
    EngineEra.OPEN_WORLD: EraAssetContract(
        EngineEra.OPEN_WORLD,
        AssetFormatFamily.STREAMED,
        AssetBudget(48, 536_870_912, 8_192, 4_096, 49, 1_000_000, 128),
        (
            "assets/pbr_materials.json",
            "assets/world_index.json",
            "assets/lod_policy.json",
        ),
    ),
    EngineEra.MODERN: EraAssetContract(
        EngineEra.MODERN,
        AssetFormatFamily.GPU,
        AssetBudget(64, 1_073_741_824, 16_384, 8_192, 81, 5_000_000, 256),
        (
            "assets/ecs_prefabs.json",
            "assets/virtual_geometry.json",
            "assets/world_index.json",
        ),
    ),
    EngineEra.NEXT: EraAssetContract(
        EngineEra.NEXT,
        AssetFormatFamily.HYBRID,
        AssetBudget(72, 2_147_483_648, 32_768, 16_384, 81, 10_000_000, 512),
        (
            "assets/ecs_prefabs.json",
            "assets/virtual_geometry.json",
            "assets/world_index.json",
            "assets/procedural_rules.json",
        ),
    ),
}


def era_asset_contract(era: EngineEra | str) -> EraAssetContract:
    try:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    except ValueError as exc:
        raise GameEngineLabError(f"unknown engine era: {era!r}") from exc
    return ERA_ASSET_CONTRACTS[key]


def _safe_project_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GameEngineLabError("project_id must be non-empty")
    clean = value.strip()
    if len(clean) > 64:
        raise GameEngineLabError("project_id exceeds 64 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(char not in allowed for char in clean):
        raise GameEngineLabError(
            "project_id may contain only letters, digits, '-' and '_'"
        )
    return clean


@dataclass(frozen=True, slots=True)
class GameProjectSpec:
    project_id: str
    era: EngineEra
    title: str
    gameplay_dialect: str = "extraction_now"
    seed: int = 0
    complexity: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _safe_project_id(self.project_id))
        if not isinstance(self.era, EngineEra):
            try:
                object.__setattr__(self, "era", EngineEra(str(self.era)))
            except ValueError as exc:
                raise GameEngineLabError("unknown project engine era") from exc
        if not isinstance(self.title, str) or not self.title.strip():
            raise GameEngineLabError("title must be non-empty")
        if len(self.title.strip()) > 128:
            raise GameEngineLabError("title exceeds 128 characters")
        object.__setattr__(self, "title", self.title.strip())
        if (
            not isinstance(self.gameplay_dialect, str)
            or not self.gameplay_dialect.strip()
            or len(self.gameplay_dialect) > 128
        ):
            raise GameEngineLabError("invalid gameplay_dialect")
        object.__setattr__(self, "gameplay_dialect", self.gameplay_dialect.strip())
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise GameEngineLabError("seed must be an integer")
        if not isinstance(self.complexity, int) or not 1 <= self.complexity <= 8:
            raise GameEngineLabError("complexity must be within [1, 8]")


@dataclass(frozen=True, slots=True)
class AssetArtifact:
    path: str
    kind: str
    byte_size: int
    digest: str


@dataclass(frozen=True, slots=True)
class ProjectQualityProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ProjectQualityReport:
    era: EngineEra
    tree_digest: str
    probes: tuple[ProjectQualityProbe, ...]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(probe.passed for probe in self.probes)

    @property
    def score(self) -> float:
        return sum(probe.passed for probe in self.probes) / max(1, len(self.probes))

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(probe.name for probe in self.probes if not probe.passed)


@dataclass(frozen=True, slots=True)
class CompiledEngineProject:
    spec: GameProjectSpec
    sandbox: RoutedEngineSandbox
    artifacts: tuple[AssetArtifact, ...]
    snapshot: SandboxSnapshot
    manifest_digest: str
    bundle_digest: str

    def restore(self) -> "CompiledEngineProject":
        tree = VirtualFileTree.restore(self.snapshot)
        return replace(self, sandbox=self.sandbox.with_tree(tree))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _unit(seed: int, label: str) -> float:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _int(seed: int, label: str, low: int, high: int) -> int:
    if high < low:
        raise GameEngineLabError("invalid deterministic integer bounds")
    span = high - low + 1
    return low + int(_unit(seed, label) * span) % span


def _palette(spec: GameProjectSpec, colors: int) -> list[str]:
    return [
        "#{:02x}{:02x}{:02x}".format(
            _int(spec.seed, f"palette:{index}:r", 0, 255),
            _int(spec.seed, f"palette:{index}:g", 0, 255),
            _int(spec.seed, f"palette:{index}:b", 0, 255),
        )
        for index in range(colors)
    ]


def _mesh(spec: GameProjectSpec, vertices: int = 8) -> dict[str, object]:
    points = []
    for index in range(vertices):
        angle = (math.tau * index) / vertices
        radius = 1.0 + _unit(spec.seed, f"mesh:{index}") * 0.25
        points.append(
            [
                round(math.cos(angle) * radius, 6),
                round((_unit(spec.seed, f"mesh:y:{index}") - 0.5) * 2.0, 6),
                round(math.sin(angle) * radius, 6),
            ]
        )
    triangles = [
        [0, index, index + 1]
        for index in range(1, max(2, vertices - 1))
    ]
    return {"vertices": points, "triangles": triangles}


def _world_cells(spec: GameProjectSpec, count: int) -> tuple[dict[str, object], ...]:
    side = max(1, math.ceil(math.sqrt(count)))
    cells = []
    for index in range(count):
        x = index % side
        z = index // side
        cells.append(
            {
                "id": f"cell_{x}_{z}",
                "x": x,
                "z": z,
                "seed": _int(spec.seed, f"cell:{x}:{z}", 0, 2**31 - 1),
                "density": round(_unit(spec.seed, f"density:{x}:{z}"), 6),
            }
        )
    return tuple(cells)


class EraAssetCompiler:
    """Compile a project intent into a historically appropriate sandbox tree."""

    def __init__(self, engine_lab: ExecutableGameEngineLab | None = None) -> None:
        self.engine_lab = engine_lab or ExecutableGameEngineLab()

    def _documents(self, spec: GameProjectSpec) -> dict[str, object]:
        contract = era_asset_contract(spec.era)
        complexity = spec.complexity
        seed = spec.seed

        if spec.era is EngineEra.PONG:
            return {
                "assets/primitives.json": {
                    "format": "scanline_rects_v1",
                    "palette": ["#000000", "#ffffff"],
                    "objects": [
                        {"id": "left_paddle", "kind": "rect", "w": 4, "h": 32},
                        {"id": "right_paddle", "kind": "rect", "w": 4, "h": 32},
                        {"id": "ball", "kind": "rect", "w": 4, "h": 4},
                    ],
                },
                "assets/tones.json": {
                    "format": "single_square_v1",
                    "channels": 1,
                    "tones": [220, 440, 660],
                },
            }

        if spec.era is EngineEra.ARCADE:
            vectors = [
                [
                    round(math.cos(index * math.tau / 6), 6),
                    round(math.sin(index * math.tau / 6), 6),
                ]
                for index in range(6)
            ]
            return {
                "assets/vectors.json": {
                    "format": "vector_list_v1",
                    "ship": vectors,
                    "brightness_levels": 8,
                },
                "assets/sprites.json": {
                    "format": "indexed_sprite_v1",
                    "palette": _palette(spec, 8),
                    "sprites": [
                        {"id": f"sprite_{index}", "w": 8, "h": 8}
                        for index in range(2 + complexity)
                    ],
                },
                "assets/tones.json": {
                    "format": "three_voice_v1",
                    "channels": 3,
                    "tones": [
                        _int(seed, f"tone:{index}", 110, 1_200)
                        for index in range(3)
                    ],
                },
            }

        if spec.era is EngineEra.EIGHT_BIT:
            tile_count = min(64, 8 + complexity * 4)
            tiles = [
                [
                    _int(seed, f"tile:{tile}:{pixel}", 0, 3)
                    for pixel in range(64)
                ]
                for tile in range(tile_count)
            ]
            map_w, map_h = 16, 15
            return {
                "assets/palette.json": {
                    "format": "indexed_palette_v1",
                    "colors": _palette(spec, 32),
                    "subpalettes": 8,
                },
                "assets/tiles.json": {
                    "format": "chr_2bpp_descriptor_v1",
                    "tile_size": [8, 8],
                    "tiles": tiles,
                },
                "assets/tilemap.json": {
                    "format": "name_table_v1",
                    "width": map_w,
                    "height": map_h,
                    "tiles": [
                        _int(seed, f"map:{index}", 0, tile_count - 1)
                        for index in range(map_w * map_h)
                    ],
                },
                "assets/apu.json": {
                    "format": "apu_patch_v1",
                    "channels": ["pulse_a", "pulse_b", "triangle", "noise"],
                },
            }

        if spec.era is EngineEra.SIXTEEN_BIT:
            tile_count = 16 + complexity * 8
            return {
                "assets/palette.json": {
                    "format": "rgb555_palette_v1",
                    "colors": _palette(spec, min(256, 32 + complexity * 16)),
                },
                "assets/tiles16.json": {
                    "format": "tile_4bpp_descriptor_v1",
                    "tile_size": [8, 8],
                    "tile_count": tile_count,
                    "compression": "rle_descriptor",
                },
                "assets/planes.json": {
                    "format": "multiplane_tilemap_v1",
                    "planes": [
                        {"id": "background", "scroll_ratio": 0.25},
                        {"id": "midground", "scroll_ratio": 0.5},
                        {"id": "gameplay", "scroll_ratio": 1.0},
                    ],
                },
                "assets/pcm_bank.json": {
                    "format": "pcm_bank_v1",
                    "voices": 8,
                    "samples": [
                        {"id": f"sfx_{index}", "frames": 64 + index * 16}
                        for index in range(2 + complexity)
                    ],
                },
            }

        mesh = _mesh(spec, min(32, 8 + complexity * 2))

        if spec.era is EngineEra.EARLY_3D:
            return {
                "assets/bsp.json": {
                    "format": "bsp_sector_v1",
                    "planes": [
                        {"normal": [1, 0, 0], "distance": 0},
                        {"normal": [0, 0, 1], "distance": 8},
                    ],
                    "mesh": mesh,
                },
                "assets/software_textures.json": {
                    "format": "indexed_64_texture_v1",
                    "palette": _palette(spec, 64),
                    "texture_count": 2 + complexity,
                },
                "assets/sfx_bank.json": {
                    "format": "mono_sfx_bank_v1",
                    "sample_rate": 11_025,
                    "clips": 3 + complexity,
                },
            }

        if spec.era is EngineEra.FIXED_3D:
            return {
                "assets/meshes.json": {
                    "format": "indexed_mesh_v1",
                    "meshes": [{"id": "primary", **mesh}],
                },
                "assets/fixed_materials.json": {
                    "format": "fixed_tl_material_v1",
                    "materials": [
                        {
                            "id": f"material_{index}",
                            "blend": "opaque",
                            "lighting": True,
                            "texture_page": index % 2,
                        }
                        for index in range(2 + complexity)
                    ],
                },
                "assets/texture_pages.json": {
                    "format": "texture_page_v1",
                    "dimension": min(contract.budget.max_texture_dimension, 64 * complexity),
                    "pages": 2,
                },
            }

        if spec.era is EngineEra.SHADER:
            return {
                "assets/meshes.json": {
                    "format": "skinned_mesh_v1",
                    "meshes": [{"id": "hero", **mesh}],
                },
                "assets/shader_materials.json": {
                    "format": "shader_material_v1",
                    "materials": [
                        {
                            "id": "lit",
                            "vertex_ops": ["transform", "normal"],
                            "pixel_ops": ["texture", "lambert", "fog"],
                        },
                        {
                            "id": "skinned",
                            "vertex_ops": ["skin", "transform", "normal"],
                            "pixel_ops": ["texture", "lambert"],
                        },
                    ],
                },
                "assets/skeletons.json": {
                    "format": "bone_hierarchy_v1",
                    "bones": [
                        {"id": index, "parent": index - 1 if index else None}
                        for index in range(min(48, 4 + complexity * 4))
                    ],
                },
            }

        if spec.era is EngineEra.HD:
            return {
                "assets/meshes.json": {
                    "format": "hd_indexed_mesh_v1",
                    "meshes": [{"id": "hero", **mesh}],
                },
                "assets/pbr_materials.json": {
                    "format": "pbr_material_v1",
                    "materials": [
                        {
                            "id": f"pbr_{index}",
                            "roughness": round(_unit(seed, f"rough:{index}"), 6),
                            "metallic": round(_unit(seed, f"metal:{index}"), 6),
                        }
                        for index in range(2 + complexity)
                    ],
                },
                "assets/render_targets.json": {
                    "format": "deferred_targets_v1",
                    "targets": ["albedo", "normal", "material", "depth", "hdr"],
                },
            }

        cell_count = min(contract.budget.max_world_cells, (1 + complexity * 2) ** 2)
        cells = _world_cells(spec, cell_count)
        world_docs: dict[str, object] = {
            "assets/pbr_materials.json": {
                "format": "streamed_pbr_material_v1",
                "material_count": 4 + complexity * 2,
            },
            "assets/world_index.json": {
                "format": "streamed_world_index_v1",
                "cells": [cell["id"] for cell in cells],
                "stable_order": True,
            },
        }

        for cell in cells:
            world_docs[f"assets/world/{cell['id']}.json"] = {
                "format": "world_cell_v1",
                **cell,
                "objects": 2 + _int(seed, f"objects:{cell['id']}", 0, complexity * 2),
            }

        if spec.era is EngineEra.OPEN_WORLD:
            world_docs["assets/lod_policy.json"] = {
                "format": "lod_policy_v1",
                "bands": [0.25, 0.5, 0.75, 1.0],
                "hysteresis": 0.05,
            }
            return world_docs

        world_docs.pop("assets/pbr_materials.json")
        world_docs["assets/ecs_prefabs.json"] = {
            "format": "ecs_prefab_v1",
            "components": ["position", "velocity", "mesh", "material", "cell"],
            "prefabs": [
                {"id": f"prefab_{index}", "mesh": index % 4, "material": index % 6}
                for index in range(4 + complexity)
            ],
        }
        world_docs["assets/virtual_geometry.json"] = {
            "format": "virtual_geometry_v1",
            "clusters": 64 * complexity,
            "cluster_vertices": 64,
            "stable_cluster_order": True,
        }

        if spec.era is EngineEra.NEXT:
            world_docs["assets/procedural_rules.json"] = {
                "format": "bounded_procedural_rules_v1",
                "executable_code": False,
                "rules": [
                    {
                        "id": f"rule_{index}",
                        "weight": round(_unit(seed, f"rule:{index}"), 6),
                        "operation": ["scatter", "cluster", "exclude"][index % 3],
                    }
                    for index in range(3 + complexity)
                ],
            }
        return world_docs

    def _encode_documents(
        self,
        documents: Mapping[str, object],
    ) -> dict[str, str]:
        return {
            path: json.dumps(payload, indent=2, sort_keys=True) + "\n"
            for path, payload in documents.items()
        }

    def _artifact_rows(self, files: Mapping[str, str]) -> tuple[AssetArtifact, ...]:
        return tuple(
            AssetArtifact(
                path=path,
                kind=json.loads(content).get("format", "project_metadata"),
                byte_size=len(content.encode("utf-8")),
                digest=_sha_text(content),
            )
            for path, content in sorted(files.items())
        )

    def _bundle_digest(self, artifacts: Iterable[AssetArtifact]) -> str:
        return _sha_text(
            _canonical(
                [
                    (artifact.path, artifact.kind, artifact.byte_size, artifact.digest)
                    for artifact in artifacts
                ]
            )
        )

    def compile(self, spec: GameProjectSpec) -> CompiledEngineProject:
        contract = era_asset_contract(spec.era)
        sandbox = self.engine_lab.create(spec.era, spec.gameplay_dialect)
        documents = self._documents(spec)
        encoded = self._encode_documents(documents)
        asset_bytes = sum(len(content.encode("utf-8")) for content in encoded.values())
        if len(encoded) > contract.budget.max_files:
            raise GameEngineLabError("compiled asset file budget exceeded")
        if asset_bytes > contract.budget.max_asset_bytes:
            raise GameEngineLabError("compiled asset byte budget exceeded")

        artifacts = self._artifact_rows(encoded)
        bundle_digest = self._bundle_digest(artifacts)
        manifest = {
            "schema_version": 1,
            "project_id": spec.project_id,
            "title": spec.title,
            "engine_era": spec.era.value,
            "engine_family": sandbox.family.value,
            "asset_format": contract.format_family.value,
            "gameplay_dialect": spec.gameplay_dialect,
            "seed": spec.seed,
            "complexity": spec.complexity,
            "asset_bytes": asset_bytes,
            "bundle_digest": bundle_digest,
            "artifacts": [
                {
                    "path": artifact.path,
                    "kind": artifact.kind,
                    "bytes": artifact.byte_size,
                    "digest": artifact.digest,
                }
                for artifact in artifacts
            ],
        }
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        spec_text = json.dumps(
            {
                "project_id": spec.project_id,
                "title": spec.title,
                "era": spec.era.value,
                "gameplay_dialect": spec.gameplay_dialect,
                "seed": spec.seed,
                "complexity": spec.complexity,
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
        all_files = {
            **encoded,
            "project/spec.json": spec_text,
            "project/manifest.json": manifest_text,
        }
        patches = tuple(
            SandboxPatch(path, content)
            for path, content in sorted(all_files.items())
        )
        compiled = sandbox.apply(patches)
        snapshot = compiled.tree.snapshot(spec.era, 0, None)
        project = CompiledEngineProject(
            spec=spec,
            sandbox=compiled,
            artifacts=artifacts,
            snapshot=snapshot,
            manifest_digest=_sha_text(manifest_text),
            bundle_digest=bundle_digest,
        )
        report = ProjectAdversary(self).evaluate(project)
        if not report.passed:
            raise GameEngineLabError(
                f"compiled project failed validation: {report.failed}"
            )
        return project

    def canonical_asset_files(self, spec: GameProjectSpec) -> dict[str, str]:
        return self._encode_documents(self._documents(spec))


class ProjectAdversary:
    """Validate era format, digests, budgets, engine integrity, and replayability."""

    def __init__(self, compiler: EraAssetCompiler | None = None) -> None:
        self.compiler = compiler or EraAssetCompiler()

    def evaluate(self, project: CompiledEngineProject) -> ProjectQualityReport:
        contract = era_asset_contract(project.spec.era)
        tree = project.sandbox.tree
        probes: list[ProjectQualityProbe] = []

        missing = sorted(set(contract.required_paths) - set(tree.files))
        probes.append(
            ProjectQualityProbe(
                "era_contract",
                not missing,
                "required era assets present" if not missing else f"missing={missing}",
            )
        )

        try:
            manifest = json.loads(tree.read("project/manifest.json"))
        except (GameEngineLabError, json.JSONDecodeError):
            manifest = None
        manifest_ok = (
            isinstance(manifest, dict)
            and manifest.get("engine_era") == project.spec.era.value
            and manifest.get("engine_family") == project.sandbox.family.value
            and manifest.get("asset_format") == contract.format_family.value
            and manifest.get("bundle_digest") == project.bundle_digest
        )
        probes.append(
            ProjectQualityProbe(
                "manifest",
                manifest_ok,
                "project manifest bound to era/family/bundle",
            )
        )

        artifact_ok = True
        total_bytes = 0
        for artifact in project.artifacts:
            try:
                content = tree.read(artifact.path)
            except GameEngineLabError:
                artifact_ok = False
                continue
            size = len(content.encode("utf-8"))
            total_bytes += size
            if size != artifact.byte_size or _sha_text(content) != artifact.digest:
                artifact_ok = False
        probes.append(
            ProjectQualityProbe(
                "artifact_digests",
                artifact_ok,
                "artifact bytes match manifest digests",
            )
        )
        budget_ok = (
            len(project.artifacts) <= contract.budget.max_files
            and total_bytes <= contract.budget.max_asset_bytes
        )
        probes.append(
            ProjectQualityProbe(
                "asset_budget",
                budget_ok,
                f"files={len(project.artifacts)} bytes={total_bytes}",
            )
        )

        engine_report = self.compiler.engine_lab.evaluate(project.sandbox)
        probes.append(
            ProjectQualityProbe(
                "engine_integrity",
                bool(engine_report.passed),
                f"engine_score={engine_report.score:.6f}",
            )
        )

        try:
            restored = project.restore()
            snapshot_ok = restored.sandbox.tree.digest == project.sandbox.tree.digest
        except GameEngineLabError:
            snapshot_ok = False
        probes.append(
            ProjectQualityProbe(
                "snapshot",
                snapshot_ok,
                "compiled tree snapshot roundtrip",
            )
        )

        try:
            rebuilt = self.compiler.compile(project.spec)
            deterministic = (
                rebuilt.bundle_digest == project.bundle_digest
                and rebuilt.sandbox.tree.digest == project.sandbox.tree.digest
            )
        except GameEngineLabError:
            deterministic = False
        probes.append(
            ProjectQualityProbe(
                "deterministic_build",
                deterministic,
                "same spec rebuilds byte-identically",
            )
        )
        return ProjectQualityReport(
            project.spec.era,
            project.sandbox.tree.digest,
            tuple(probes),
        )


@dataclass(frozen=True, slots=True)
class ProjectImprovementRound:
    index: int
    before_score: float
    candidate_score: float
    accepted: bool
    before_digest: str
    candidate_digest: str
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectImprovementResult:
    project: CompiledEngineProject
    report: ProjectQualityReport
    rounds: tuple[ProjectImprovementRound, ...]
    promoted: bool


class EngineProjectLab:
    """Compile, attack, repair, and snapshot complete era-specific projects."""

    def __init__(
        self,
        engine_lab: ExecutableGameEngineLab | None = None,
    ) -> None:
        self.compiler = EraAssetCompiler(engine_lab)
        self.adversary = ProjectAdversary(self.compiler)

    def compile(self, spec: GameProjectSpec) -> CompiledEngineProject:
        return self.compiler.compile(spec)

    def evaluate(self, project: CompiledEngineProject) -> ProjectQualityReport:
        return self.adversary.evaluate(project)

    def _rebuild_project(
        self,
        project: CompiledEngineProject,
        tree: VirtualFileTree,
    ) -> CompiledEngineProject:
        canonical = self.compiler.compile(project.spec)
        artifacts = canonical.artifacts
        bundle_digest = canonical.bundle_digest
        manifest_text = tree.read("project/manifest.json")
        snapshot = tree.snapshot(project.spec.era, project.snapshot.sequence + 1, project.snapshot.tree_digest)
        return CompiledEngineProject(
            project.spec,
            project.sandbox.with_tree(tree),
            artifacts,
            snapshot,
            _sha_text(manifest_text),
            bundle_digest,
        )

    def canonical_repair(
        self,
        project: CompiledEngineProject,
        report: ProjectQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = self.compiler.compile(project.spec)
        canonical_paths = {
            artifact.path for artifact in canonical.artifacts
        } | {"project/spec.json", "project/manifest.json"}
        patches: list[SandboxPatch] = []
        for path in sorted(canonical_paths):
            wanted = canonical.sandbox.tree.read(path)
            current = project.sandbox.tree.files.get(path)
            if current != wanted:
                patches.append(
                    SandboxPatch(
                        path,
                        wanted,
                        project.sandbox.tree.file_digest(path),
                    )
                )
        return tuple(patches)

    def adversarial_improve(
        self,
        project: CompiledEngineProject,
        *,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> ProjectImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError("target must be within (0, 1]")
        if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 32:
            raise GameEngineLabError("max_rounds must be within [1, 32]")
        current = project
        report = self.evaluate(current)
        rounds: list[ProjectImprovementRound] = []
        if report.passed and report.score >= target:
            return ProjectImprovementResult(current, report, (), True)
        strategy = improver or self.canonical_repair
        for index in range(1, max_rounds + 1):
            patches = tuple(strategy(current, report))
            if not patches:
                break
            try:
                candidate_tree = current.sandbox.tree.apply(patches)
                candidate = self._rebuild_project(current, candidate_tree)
                next_report = self.evaluate(candidate)
            except GameEngineLabError:
                break
            accepted = (
                candidate.sandbox.tree.digest != current.sandbox.tree.digest
                and next_report.score >= report.score
                and len(next_report.failed) <= len(report.failed)
            )
            rounds.append(
                ProjectImprovementRound(
                    index,
                    report.score,
                    next_report.score,
                    accepted,
                    current.sandbox.tree.digest,
                    candidate.sandbox.tree.digest,
                    next_report.failed,
                )
            )
            if not accepted:
                break
            current = candidate
            report = next_report
            if report.passed and report.score >= target:
                break
        return ProjectImprovementResult(
            current,
            report,
            tuple(rounds),
            report.passed and report.score >= target,
        )


def build_game_project_spec(
    era: EngineEra | str,
    *,
    project_id: str,
    title: str,
    gameplay_dialect: str = "extraction_now",
    seed: int = 0,
    complexity: int = 1,
) -> GameProjectSpec:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    return GameProjectSpec(
        project_id,
        key,
        title,
        gameplay_dialect,
        seed,
        complexity,
    )
