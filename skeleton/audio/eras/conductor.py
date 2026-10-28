"""Samples one organ per era. Does not import all 5120."""

from __future__ import annotations

import importlib
from typing import Any

from skeleton.audio.eras.caps import names
from skeleton.audio.eras.law import CAPABILITY_COUNT


_REVIEWED_ERA_FIRST_MODULES = {
    "pong": "c0001_pong_001",
    "psg": "c0321_psg_001",
    "sid": "c0641_sid_001",
    "fm": "c0961_fm_001",
    "wave": "c1281_wave_001",
    "tracker": "c1601_tracker_001",
    "cdda": "c1921_cdda_001",
    "stream": "c2241_stream_001",
    "spatial": "c2561_spatial_001",
    "stem": "c2881_stem_001",
    "bus": "c3201_bus_001",
    "voice": "c3521_voice_001",
    "ambient": "c3841_ambient_001",
    "sting": "c4161_sting_001",
    "occlude": "c4481_occlude_001",
    "export": "c4801_export_001",
}


def _load_reviewed_era_organ(era: str, module: str):
    """Load only the first reviewed organ of each indexed era."""
    if _REVIEWED_ERA_FIRST_MODULES.get(era) != module:
        raise RuntimeError("era index drift or unregistered era owner")
    if era == "pong":
        return importlib.import_module("skeleton.audio.eras.caps.c0001_pong_001").Organ()
    if era == "psg":
        return importlib.import_module("skeleton.audio.eras.caps.c0321_psg_001").Organ()
    if era == "sid":
        return importlib.import_module("skeleton.audio.eras.caps.c0641_sid_001").Organ()
    if era == "fm":
        return importlib.import_module("skeleton.audio.eras.caps.c0961_fm_001").Organ()
    if era == "wave":
        return importlib.import_module("skeleton.audio.eras.caps.c1281_wave_001").Organ()
    if era == "tracker":
        return importlib.import_module("skeleton.audio.eras.caps.c1601_tracker_001").Organ()
    if era == "cdda":
        return importlib.import_module("skeleton.audio.eras.caps.c1921_cdda_001").Organ()
    if era == "stream":
        return importlib.import_module("skeleton.audio.eras.caps.c2241_stream_001").Organ()
    if era == "spatial":
        return importlib.import_module("skeleton.audio.eras.caps.c2561_spatial_001").Organ()
    if era == "stem":
        return importlib.import_module("skeleton.audio.eras.caps.c2881_stem_001").Organ()
    if era == "bus":
        return importlib.import_module("skeleton.audio.eras.caps.c3201_bus_001").Organ()
    if era == "voice":
        return importlib.import_module("skeleton.audio.eras.caps.c3521_voice_001").Organ()
    if era == "ambient":
        return importlib.import_module("skeleton.audio.eras.caps.c3841_ambient_001").Organ()
    if era == "sting":
        return importlib.import_module("skeleton.audio.eras.caps.c4161_sting_001").Organ()
    if era == "occlude":
        return importlib.import_module("skeleton.audio.eras.caps.c4481_occlude_001").Organ()
    if era == "export":
        return importlib.import_module("skeleton.audio.eras.caps.c4801_export_001").Organ()
    raise RuntimeError("unknown era")


class Conductor:
    def __init__(self) -> None:
        self.rows = names()
        if len(self.rows) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_eras(self) -> list[dict[str, Any]]:
        from skeleton.audio.eras.caps.c0001_pong_001 import EraPulse

        cards = []
        seen = set()
        for cid, era, module in self.rows:
            if era in seen:
                continue
            seen.add(era)
            organ = _load_reviewed_era_organ(era, module)
            pulse = EraPulse(1, 1, 1, 8000, 1, 0.5, pointers=("ptr:era",), cool=True)
            card = organ.admit(pulse)
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            if organ.reverse() is None:
                raise RuntimeError("reverse")
            card["id"] = cid
            cards.append(card)
        return cards
