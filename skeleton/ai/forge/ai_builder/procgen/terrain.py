"""Terrain pipeline: base noise -> erosion-lite -> moisture -> biomes, plus an FLGB receipt.

The receipt reuses ``skeleton.game.generation.terrain_generation``
(``TerrainChunkRequest`` / ``TerrainChunkReceipt``) so downstream consumers
that already speak the FLGB-14 contract can verify a chunk by digest.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from skeleton.game.generation.terrain_generation import TerrainChunkReceipt, TerrainChunkRequest

from .biomes import DEFAULT_BIOMES, BiomeMap, BiomeTable, classify
from .canonical import digest
from .erosion import ErosionReport, erode
from .errors import ProcgenError
from .heightmap import Heightmap
from .noise import diamond_square, radial_falloff, resample, value_noise
from .rng import Streams

METHODS = ("value", "diamond_square")


@dataclass(frozen=True)
class TerrainConfig:
    width: int = 64
    height: int = 64
    method: str = "value"
    scale: float = 16.0
    octaves: int = 4
    persistence: float = 0.5
    roughness: float = 0.55
    island: float = 0.0          # 0 = no falloff, 1 = strong island mask
    thermal_iterations: int = 6
    talus: float = 0.02
    droplets: int = 200
    moisture_scale: float = 24.0
    biomes: BiomeTable = field(default=DEFAULT_BIOMES)
    world_id: str = "forge-procgen"

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ProcgenError(f"terrain method must be one of {METHODS}")
        for name in ("width", "height"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or not 8 <= v <= 512:
                raise ProcgenError(f"terrain {name} must be an int in [8, 512]")
        for name, lower, upper in (
            ("scale", 1.0, 4096.0),
            ("moisture_scale", 1.0, 4096.0),
            ("persistence", 0.0, 1.0),
            ("roughness", 0.0, 1.0),
            ("island", 0.0, 1.0),
            ("talus", 0.0, 1.0),
        ):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or (value <= lower if name in ("persistence", "roughness") else value < lower)
                    or (value >= upper if name in ("roughness", "talus") else value > upper)):
                raise ProcgenError(f"terrain {name} must be finite and bounded")
        for name, lower, upper in (
            ("octaves", 1, 12), ("thermal_iterations", 0, 200),
            ("droplets", 0, 100000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ProcgenError(f"terrain {name} exceeds bounded iteration range")
        # Bound integrated work rather than allowing many independently legal
        # settings to produce runaway CPU iteration and memory pressure.
        cells = self.width * self.height
        if (cells * (1 + self.octaves + self.thermal_iterations) > 20_000_000
                or self.droplets * 32 > 2_000_000):
            raise ProcgenError("terrain integrated execution budget exceeded")
        if (not isinstance(self.biomes, BiomeTable)
                or type(self.world_id) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,127}", self.world_id) is None):
            raise ProcgenError("terrain requires typed biome table and bounded world identity")

    def as_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "method": self.method, "scale": self.scale,
                "octaves": self.octaves, "persistence": self.persistence, "roughness": self.roughness,
                "island": self.island, "thermal_iterations": self.thermal_iterations, "talus": self.talus,
                "droplets": self.droplets, "moisture_scale": self.moisture_scale,
                "biomes": self.biomes.digest()[:16]}


@dataclass(frozen=True)
class Terrain:
    height: Heightmap
    moisture: Heightmap
    biomes: BiomeMap
    erosion: ErosionReport
    receipt: TerrainChunkReceipt
    request: TerrainChunkRequest
    config: TerrainConfig

    def biome_at(self, u: float, v: float) -> str:
        """Biome at normalised coordinates, for mapping layout space onto terrain."""
        x = min(int(u * self.biomes.width), self.biomes.width - 1)
        y = min(int(v * self.biomes.height), self.biomes.height - 1)
        return self.biomes.at(max(x, 0), max(y, 0))

    def walkable_fraction(self) -> float:
        mask = self.biomes.walkable_mask(self.config.biomes)
        return sum(mask) / len(mask)

    def as_dict(self) -> dict:
        return {"config": self.config.as_dict(), "height": self.height.to_dict(),
                "moisture": self.moisture.to_dict(), "biome_counts": self.biomes.counts(),
                "erosion": self.erosion.as_dict(), "walkable_fraction": self.walkable_fraction(),
                "receipt": {"request_digest": self.receipt.request_digest,
                            "height_digest": self.receipt.height_digest,
                            "material_digest": self.receipt.material_digest,
                            "collision_digest": self.receipt.collision_digest}}


def _base(cfg: TerrainConfig, streams: Streams) -> Heightmap:
    if cfg.method == "value":
        return value_noise(cfg.width, cfg.height, streams.stream("terrain/height"), scale=cfg.scale,
                           octaves=cfg.octaves, persistence=cfg.persistence)
    side = max(cfg.width, cfg.height) - 1
    exponent = max(1, (side - 1).bit_length())
    ds = diamond_square(exponent, streams.stream("terrain/height"), roughness=cfg.roughness)
    return resample(ds, cfg.width, cfg.height).normalized()


def generate_terrain(streams: Streams, cfg: TerrainConfig = TerrainConfig()) -> Terrain:
    if not isinstance(streams, Streams) or not isinstance(cfg, TerrainConfig):
        raise ProcgenError("typed terrain source and finite configuration required")
    base = _base(cfg, streams)
    if cfg.island > 0:
        base = radial_falloff(base, strength=cfg.island)
    height, report = erode(base, streams.stream("terrain/erosion"), thermal_iterations=cfg.thermal_iterations,
                           talus=cfg.talus, droplet_count=cfg.droplets)
    height = height.quantized()
    moisture = value_noise(cfg.width, cfg.height, streams.stream("terrain/moisture"),
                           scale=cfg.moisture_scale, octaves=3).quantized()
    bmap = classify(height, moisture, cfg.biomes)
    request = TerrainChunkRequest(world_id=cfg.world_id, chunk_x=0, chunk_y=0,
                                  resolution=max(cfg.width, cfg.height), seed_digest=streams.digest("terrain"),
                                  biome_digest=cfg.biomes.digest())
    receipt = TerrainChunkReceipt(request_digest=request.request_digest, height_digest=height.digest(),
                                  material_digest=bmap.digest(),
                                  collision_digest=digest(list(bmap.walkable_mask(cfg.biomes))))
    return Terrain(height, moisture, bmap, report, receipt, request, cfg)
