"""10x living-system world compiler with O(1) index/rank/unrank.

Former 1,024,000 spatial foundations × ten stateful world systems =
10,240,000 living foundations. Twelve executable narrative arcs yield
122,880,000 structured game configurations. This is NOT 122.88m
independently written stories or certified native games.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_tenfold_compiler import (
    SPATIAL_FOUNDATIONS, TENFOLD_CONFIGURATIONS, SpatialFoundation,
    TenfoldWorld, spatial_at, tenfold_at,
)
from .original_world_living_systems import SYSTEMS, SYSTEM_BY_ID, LivingSystemLaw

LIVING_VERSION = "original-world-living-10x.v1"
LIVING_SYSTEM_COUNT = len(SYSTEMS)
NARRATIVE_ARCS = 12
LIVING_FOUNDATIONS = SPATIAL_FOUNDATIONS * LIVING_SYSTEM_COUNT
LIVING_CONFIGURATIONS = LIVING_FOUNDATIONS * NARRATIVE_ARCS
PROVENANCE = "composed-authored-causal-genre-space-living-arc"


@dataclass(frozen=True)
class LivingFoundation:
    index: int
    living_id: str
    design_id: str
    source: SpatialFoundation
    system: LivingSystemLaw
    provenance: str = PROVENANCE

    def as_dict(self) -> dict:
        return {
            "index": str(self.index),
            "living_id": self.living_id,
            "design_id": self.design_id,
            "source_spatial_index": str(self.source.index),
            "original_foundation": self.source.source.mode.base.foundation_id,
            "genre": self.source.source.mode.form.form_id,
            "architecture": self.source.architecture.architecture_id,
            "system": self.system.system_id,
            "world_premise": self.system.world_premise,
            "actor_model": self.system.actor_model,
            "autonomous_process": self.system.autonomous_process,
            "actions": list(self.system.commands),
            "provenance": self.provenance,
            "status": "bounded-autonomous-reference-runtime",
        }


@dataclass(frozen=True)
class LivingWorld:
    index: int
    world_id: str
    design_id: str
    foundation: LivingFoundation
    source: TenfoldWorld
    provenance: str = PROVENANCE

    def as_dict(self) -> dict:
        return {
            "index": str(self.index),
            "world_id": self.world_id,
            "design_id": self.design_id,
            "foundation": self.foundation.as_dict(),
            "source_tenfold_index": str(self.source.index),
            "source_tenfold_id": self.source.tenfold_id,
            "arc": self.source.advanced.arc.arc_id,
            "continuity": self.source.advanced.arc.continuation_policy,
            "provenance": self.provenance,
            "implementation_status": "bounded-autonomous-reference-game",
        }


def _digest(value: dict) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def living_foundation_at(index: int) -> LivingFoundation:
    if type(index) is not int or not 0 <= index < LIVING_FOUNDATIONS:
        raise FoundationError("invalid 10x living-foundation index")
    space_index, system_i = divmod(index, LIVING_SYSTEM_COUNT)
    spatial = spatial_at(space_index)
    system = SYSTEMS[system_i]
    signature = {"version": LIVING_VERSION,
                 "source": spatial.design_id, "system": system.system_id}
    return LivingFoundation(
        index, f"livingbase-{index:08d}", _digest(signature),
        spatial, system,
    )


def living_at(index: int) -> LivingWorld:
    if type(index) is not int or not 0 <= index < LIVING_CONFIGURATIONS:
        raise FoundationError("invalid 10x living-world configuration index")
    foundation_i, arc_i = divmod(index, NARRATIVE_ARCS)
    foundation = living_foundation_at(foundation_i)
    spatial_i = foundation.source.index
    tenfold = tenfold_at(spatial_i * NARRATIVE_ARCS + arc_i)
    signature = {"version": LIVING_VERSION, "source": tenfold.design_id,
                 "living_rule": foundation.design_id}
    return LivingWorld(
        index, f"livingworld-{index:09d}", _digest(signature),
        foundation, tenfold,
    )


def living_for(
    base: int, form: str, architecture: str,
    living_system: str, progression: str,
) -> LivingWorld:
    from .original_world_tenfold_compiler import tenfold_for
    from .original_world_living_systems import SYSTEM_BY_ID
    tenfold = tenfold_for(base, form, architecture, progression)
    try:
        system_i = next(i for i, law in enumerate(SYSTEMS)
                        if law.system_id == living_system)
    except StopIteration as exc:
        raise FoundationError("unknown living-world actor simulation") from exc
    spatial_index = tenfold.spatial.index
    return living_at(
        (spatial_index * LIVING_SYSTEM_COUNT + system_i) * NARRATIVE_ARCS
        + tenfold.index % NARRATIVE_ARCS
    )


def living_from_id(identifier: str) -> LivingWorld:
    if not isinstance(identifier, str) or not identifier.startswith("livingworld-"):
        raise FoundationError("noncanonical living world identifier")
    suffix = identifier[len("livingworld-"):]
    if len(suffix) != 9 or not suffix.isascii() or not suffix.isdecimal():
        raise FoundationError("invalid living-world serial")
    law = living_at(int(suffix))
    if law.world_id != identifier:
        raise FoundationError("invalid canonical world reference")
    return law


def living_from_seed(seed: str) -> LivingWorld:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise FoundationError("world seed must contain 1–4096 UTF-8 bytes")
    raw = sha256((LIVING_VERSION + ":" + seed).encode("utf-8")).digest()
    return living_at(int.from_bytes(raw, "big") % LIVING_CONFIGURATIONS)


def page_living(*, start: int = 0, limit: int = 24):
    if (type(start) is not int or type(limit) is not int
            or not 0 <= start <= LIVING_CONFIGURATIONS
            or not 1 <= limit <= 256):
        raise FoundationError("living-world page must be bounded")
    for i in range(start, min(start + limit, LIVING_CONFIGURATIONS)):
        yield living_at(i)


def living_inventory() -> dict:
    return {
        "version": LIVING_VERSION,
        "authored_original_world_roots": 1424,
        "authored_living_world_systems": LIVING_SYSTEM_COUNT,
        "authored_living_player_interventions": sum(len(s.commands) for s in SYSTEMS),
        "source_spatial_foundations": SPATIAL_FOUNDATIONS,
        "source_spatial_advanced_configurations": TENFOLD_CONFIGURATIONS,
        "living_foundations": LIVING_FOUNDATIONS,
        "living_advanced_configurations": LIVING_CONFIGURATIONS,
        "continuation_contracts": NARRATIVE_ARCS,
        "formerly_assigned_indices_unchanged": True,
        "worlds_individually_handwritten_by_composition": 0,
        "styles_hardware_seeds_eras_as_multipliers": 0,
        "certified_native_games": 0,
        "old_and_new_cardinality_is_nested_not_additive": True,
        "shared_abstract_simulation_not_bespoke_games": True,
        "provenance": PROVENANCE,
    }


assert LIVING_FOUNDATIONS == 10_240_000
assert LIVING_CONFIGURATIONS == 122_880_000
assert set(SYSTEM_BY_ID) == {s.system_id for s in SYSTEMS}
