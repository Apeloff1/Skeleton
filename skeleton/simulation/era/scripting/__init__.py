"""STU-ERAS systems scripting for eras and rooms data.

Pure, deterministic, stdlib-only. No network, no provider calls, no forge
writes: this package only validates and loads era/room data so that forge
and level tooling can consume it through a single canonical schema.
"""

from __future__ import annotations

from skeleton.simulation.era.scripting.schema import (
    SCHEMA_VERSION,
    EraSpec,
    ExitSpec,
    RoomSpec,
    SchemaError,
)
from skeleton.simulation.era.scripting.compose import (
    compose_era,
    load_composed,
    merge_era,
    merge_room,
    resolve_room,
)
from skeleton.simulation.era.scripting.loader import (
    load_era,
    load_era_json,
    load_eras,
)

__all__ = [
    "SCHEMA_VERSION",
    "EraSpec",
    "ExitSpec",
    "RoomSpec",
    "SchemaError",
    "compose_era",
    "load_composed",
    "merge_era",
    "merge_room",
    "resolve_room",
    "load_era",
    "load_era_json",
    "load_eras",
]
