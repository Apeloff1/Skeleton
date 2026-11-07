"""GB-20 law. Vertebral count frozen at 33 (7C+12T+5L+5S+4Co)."""

from __future__ import annotations

PACKET = "GB-20"
LAYER = "spine"
VERSION = "1.0"
PARENT = "#80"
CITATION = "docs/lineage/spine.md"
VERTEBRA_N = 33
CERVICAL_N = 7
THORACIC_N = 12
LUMBAR_N = 5
SACRAL_N = 5
COCCYX_N = 4
SEGMENT_N = VERTEBRA_N - 1  # 32 motion segments
STORED_PROSE = 0
SKIP_CYCLES = ("cite", "feed")
DOF_PER_SEGMENT = 6  # rx, ry, rz, tx, ty, tz
MAX_LOAD_N = 5000.0  # Newtons, fail-closed ceiling
DIGEST_ALGO = "spine-blake16"
TOPOLOGY_KIND = "path-33"
