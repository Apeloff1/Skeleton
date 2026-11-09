"""Procedural generators for the AI builder: terrain, dungeons, keys, encounters, loot.

Entry point: :func:`fill_plan`. Everything is deterministic from a seed via
named substreams (:class:`Streams`); the same seed yields byte-identical
plans (:func:`canonical_bytes`). Opt-in validation lives in :mod:`.checks`.
"""
from __future__ import annotations

from .biomes import DEFAULT_BIOMES, BiomeBand, BiomeMap, BiomeTable, classify, table_from
from .bsp import BspConfig, bsp_layout
from .canonical import canonical_bytes, digest
from .checks import (RULES, check_procgen, check_procgen_loot, check_procgen_pacing,
                     check_procgen_layout, check_procgen_reachability, damage_curve, score_plan_procgen)
from .config import ProcgenConfig
from .encounters import (DEFAULT_ROLES, EncounterConfig, EncounterPlan, PacingCurve, Role,
                         pacing_report, place_encounters, spike_threshold)
from .erosion import erode
from .errors import ProcgenError
from .fill import ProcgenResult, build_layout, fill_plan, generate
from .graph_rooms import GraphConfig, graph_layout
from .heightmap import Heightmap
from .completability import CompletabilityVerdict, ProcgenCompletabilitySolver
from .keys import Solution, gates, key_distances, lock_gates, place_locks, softlocks, solve, solve_layout
from .layout import Corridor, Door, Layout, Rect, Room, tile_links
from .metrics import LayoutLimits, layout_metrics, metric_violations
from .loot import (CurrencyDrop, EconomyLootSource, LootConfig, LootEntry, LootPlan, LootSource,
                   place_loot, risk_value_correlation)
from .noise import diamond_square, value_noise
from .rng import GENERATOR_VERSION, Streams
from .tiles import assert_tiles_match, tile_reach_without_keys, tile_report
from .terrain import Terrain, TerrainConfig, generate_terrain

__all__ = [n for n in dir() if not n.startswith("_")]
