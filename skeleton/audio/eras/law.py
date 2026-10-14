"""ERA-5120 law. Game-audio eras. pipeline.py and vol156 not forked."""

from __future__ import annotations

PACKET = "ERA-5120"
LAYER = "audio.eras"
VERSION = "5120.1"
PARENT = "#80"
CITATION = "docs/lineage/audio_eras_batch5120.md"
STORED_PROSE = 0
HEAT_DROP = 0.90
CAPABILITY_COUNT = 5120
ERAS = (
    "pong", "psg", "sid", "fm", "wave", "tracker", "cdda", "stream",
    "spatial", "stem", "bus", "voice", "ambient", "sting", "occlude", "export",
)
