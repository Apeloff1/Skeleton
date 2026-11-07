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
    "load_era",
    "load_era_json",
    "load_eras",
]
