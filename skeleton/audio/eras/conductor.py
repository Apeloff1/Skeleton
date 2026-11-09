"""Samples one organ per era. Does not import all 5120."""

from __future__ import annotations

import importlib
from types import MappingProxyType
from typing import Any

from skeleton.audio.eras.caps import names
from skeleton.audio.eras.law import CAPABILITY_COUNT

# The sampler selects only the first module for each era. Pin those exact
# generated source modules; changes to INDEX.csv fail closed rather than
# making the CSV an authority to select arbitrary Python import targets.
_ERA_LOADERS = MappingProxyType({
    "c0001_pong_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c0001_pong_001"),
    "c0321_psg_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c0321_psg_001"),
    "c0641_sid_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c0641_sid_001"),
    "c0961_fm_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c0961_fm_001"),
    "c1281_wave_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c1281_wave_001"),
    "c1601_tracker_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c1601_tracker_001"),
    "c1921_cdda_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c1921_cdda_001"),
    "c2241_stream_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c2241_stream_001"),
    "c2561_spatial_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c2561_spatial_001"),
    "c2881_stem_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c2881_stem_001"),
    "c3201_bus_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c3201_bus_001"),
    "c3521_voice_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c3521_voice_001"),
    "c3841_ambient_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c3841_ambient_001"),
    "c4161_sting_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c4161_sting_001"),
    "c4481_occlude_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c4481_occlude_001"),
    "c4801_export_001": lambda: importlib.import_module("skeleton.audio.eras.caps.c4801_export_001"),
})


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
            organ = _ERA_LOADERS[module]().Organ()
            pulse = EraPulse(1, 1, 1, 8000, 1, 0.5, pointers=("ptr:era",), cool=True)
            card = organ.admit(pulse)
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            if organ.reverse() is None:
                raise RuntimeError("reverse")
            card["id"] = cid
            cards.append(card)
        return cards
