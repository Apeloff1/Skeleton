"""10× scale without visual/seed multipliers: 1,024,000 spatial foundations.

Index nesting:
  base: 10,240 separately composed root/regime/bridge crossings
  game form: 10 actually executable genre adapters
  architecture: 10 actual spatial rule systems
  progression: 12 executable continuation contracts
  result: 1,024,000 mode-and-spatial-bound foundations,
          12,288,000 advanced configurations.

Previous v1 indices are unchanged and remain separately addressable.
The new exact namespace is composed; not independently handwritten stories.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError, STRUCTURED_FOUNDATIONS
from .original_world_million_compiler import (
    AdvancedWorld, advanced_for, PLAY_FORM_COUNT, ARC_COUNT,
    MODE_FOUNDATIONS, ADVANCED_CONFIGURATIONS,
)
from .original_world_tenfold_architectures import (
    ARCHITECTURES, ARCHITECTURE_BY_ID, WorldArchitecture,
)

TENFOLD_VERSION = "original-world-architecture-forge.v1"
ARCHITECTURE_COUNT = len(ARCHITECTURES)
SPATIAL_FOUNDATIONS = MODE_FOUNDATIONS * ARCHITECTURE_COUNT
TENFOLD_CONFIGURATIONS = SPATIAL_FOUNDATIONS * ARC_COUNT
PROVENANCE = "composed-authored-law-genre-spatial-progression"


@dataclass(frozen=True)
class SpatialFoundation:
    index: int
    source: AdvancedWorld
    architecture: WorldArchitecture
    mode_id: str
    design_id: str
    provenance: str = PROVENANCE

    def as_dict(self) -> dict:
        return {
            "index": str(self.index),
            "source_mode_index": str(self.source.mode.mode_index),
            "base_foundation_index": str(self.source.mode.base.foundation_index),
            "genre": self.source.mode.form.form_id,
            "architecture": {
                "id": self.architecture.architecture_id,
                "title": self.architecture.title,
                "spatial_contract": self.architecture.spatial_contract,
                "transit_constraint": self.architecture.transit_constraint,
                "hazard_model": self.architecture.hazard_model,
                "intervention": self.architecture.intervention,
                "progression_effect": self.architecture.progression_effect,
            },
            "mode_id": self.mode_id,
            "design_id": self.design_id,
            "provenance": self.provenance,
            "readiness": "bounded-topological-reference-runtime",
        }


@dataclass(frozen=True)
class TenfoldWorld:
    index: int
    tenfold_id: str
    design_id: str
    spatial: SpatialFoundation
    advanced: AdvancedWorld
    provenance: str = PROVENANCE
    implementation_status: str = "bounded-composed-reference-game"

    def as_dict(self) -> dict:
        return {
            "index": str(self.index),
            "tenfold_id": self.tenfold_id,
            "design_id": self.design_id,
            "spatial": self.spatial.as_dict(),
            "advanced_index": str(self.advanced.index),
            "progression_id": self.advanced.arc.arc_id,
            "source_root": self.advanced.mode.base.root.root_id,
            "authored_bridge": self.advanced.mode.base.coupling,
            "source_genre": self.advanced.mode.form.form_id,
            "provenance": self.provenance,
            "implementation_status": self.implementation_status,
            "version": TENFOLD_VERSION,
        }


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def spatial_at(index: int) -> SpatialFoundation:
    if type(index) is not int or not 0 <= index < SPATIAL_FOUNDATIONS:
        raise FoundationError("spatial foundation index out of range")
    source_mode, architecture_i = divmod(index, ARCHITECTURE_COUNT)
    base_i, form_i = divmod(source_mode, PLAY_FORM_COUNT)
    from .original_world_play_forms import PLAY_FORMS, PROGRESSION_LAWS
    source = advanced_for(base_i, PLAY_FORMS[form_i].form_id,
                          PROGRESSION_LAWS[0].arc_id)
    architecture = ARCHITECTURES[architecture_i]
    signature = {
        "version": TENFOLD_VERSION, "base": source.mode.base.design_id,
        "genre": source.mode.form.form_id,
        "space": architecture.architecture_id,
    }
    return SpatialFoundation(
        index, source, architecture,
        f"space-{source.mode.mode_id}-{architecture.architecture_id}",
        _digest(signature),
    )


def tenfold_at(index: int) -> TenfoldWorld:
    if type(index) is not int or not 0 <= index < TENFOLD_CONFIGURATIONS:
        raise FoundationError("tenfold configuration index out of range")
    spatial_i, arc_i = divmod(index, ARC_COUNT)
    spatial = spatial_at(spatial_i)
    from .original_world_play_forms import PROGRESSION_LAWS
    original = spatial.source
    advanced = advanced_for(
        original.mode.base.foundation_index, original.mode.form.form_id,
        PROGRESSION_LAWS[arc_i].arc_id,
    )
    design_id = _digest({
        "version": TENFOLD_VERSION,
        "space_design_id": spatial.design_id,
        "original_advanced_design_id": advanced.design_id,
    })
    return TenfoldWorld(index, f"worldx10-{index:08d}",
                        design_id, spatial, advanced)


def tenfold_for(base: int, form: str, architecture: str,
                progression: str) -> TenfoldWorld:
    if type(base) is not int or not 0 <= base < STRUCTURED_FOUNDATIONS:
        raise FoundationError("unknown original causal foundation")
    from .original_world_play_forms import FORM_BY_ID, ARC_BY_ID, PLAY_FORMS, PROGRESSION_LAWS
    if form not in FORM_BY_ID or architecture not in ARCHITECTURE_BY_ID or progression not in ARC_BY_ID:
        raise FoundationError("unknown genre, spatial law or progression")
    form_i = next(i for i, f in enumerate(PLAY_FORMS) if f.form_id == form)
    arch_i = next(i for i, a in enumerate(ARCHITECTURES) if a.architecture_id == architecture)
    arc_i = next(i for i, a in enumerate(PROGRESSION_LAWS) if a.arc_id == progression)
    return tenfold_at(((base * PLAY_FORM_COUNT + form_i)
                       * ARCHITECTURE_COUNT + arch_i) * ARC_COUNT + arc_i)


def tenfold_from_id(identifier: str) -> TenfoldWorld:
    if not isinstance(identifier, str) or not identifier.startswith("worldx10-"):
        raise FoundationError("invalid spatial world identifier")
    index = identifier[len("worldx10-"):]
    if len(index) != 8 or not index.isascii() or not index.isdecimal():
        raise FoundationError("invalid canonical spatial world identifier")
    world = tenfold_at(int(index))
    if world.tenfold_id != identifier:
        raise FoundationError("noncanonical spatial world identifier")
    return world


def tenfold_from_seed(seed: str) -> TenfoldWorld:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise FoundationError("seed must contain 1–4096 UTF-8 bytes")
    rank = int.from_bytes(sha256((TENFOLD_VERSION + ":" + seed).encode()).digest(), "big")
    return tenfold_at(rank % TENFOLD_CONFIGURATIONS)


def page_tenfold(*, start: int = 0, limit: int = 24):
    if (type(start) is not int or type(limit) is not int or
            not 0 <= start <= TENFOLD_CONFIGURATIONS or
            not 1 <= limit <= 256):
        raise FoundationError("invalid bounded spatial world page")
    for index in range(start, min(TENFOLD_CONFIGURATIONS, start + limit)):
        yield tenfold_at(index)


def tenfold_inventory() -> dict:
    return {
        "version": TENFOLD_VERSION,
        "authored_root_world_premises": 1424,
        "causal_composed_source_foundations": STRUCTURED_FOUNDATIONS,
        "gameplay_forms": PLAY_FORM_COUNT,
        "architecture_laws_with_executable_transit": ARCHITECTURE_COUNT,
        "continuation_contracts": ARC_COUNT,
        "spatial_gameplay_foundation_entries": SPATIAL_FOUNDATIONS,
        "full_gameplay_configuration_entries": TENFOLD_CONFIGURATIONS,
        "old_102400_foundation_and_1228800_configuration_indices_unchanged": True,
        "structural_gameplay_not_cosmetic_multiplier": True,
        "separately_written_worlds_added_by_composition": 0,
        "styles_eras_console_targets_random_seeds_counted": 0,
        "native_games_certified": 0,
        "provenance": PROVENANCE,
    }


assert SPATIAL_FOUNDATIONS == 1_024_000
assert TENFOLD_CONFIGURATIONS == 12_288_000
