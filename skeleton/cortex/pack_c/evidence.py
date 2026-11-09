"""Pack C evidence digests for audit."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Iterable, List

from skeleton.cortex.pack_c.scenarios import SCENARIO_CATALOG
from skeleton.cortex.pack_c.depth_matrix import DEPTH_BANDS
from skeleton.cortex.pack_c.queue_lattice import QUEUE_LATTICE
from skeleton.cortex.pack_c.contracts import PackCManifest


@dataclass
class PackCEvidence:
    def digest(self) -> str:
        man = PackCManifest().as_dict()
        raw = f"{man}|{len(SCENARIO_CATALOG)}|{len(DEPTH_BANDS)}|{len(QUEUE_LATTICE)}"
        return sha256(raw.encode()).hexdigest()

    def summary(self) -> Dict[str, Any]:
        return {
            "scenarios": len(SCENARIO_CATALOG),
            "depth_bands": len(DEPTH_BANDS),
            "queue_cells": len(QUEUE_LATTICE),
            "digest": self.digest(),
            "locks": PackCManifest().as_dict()["locks"],
        }
