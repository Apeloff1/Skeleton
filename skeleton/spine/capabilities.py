"""GB-36-shaped capability card for Spine 1.0."""

from __future__ import annotations

from typing import Any

from skeleton.spine.law import (
    CITATION,
    DOF_PER_SEGMENT,
    LAYER,
    PACKET,
    SEGMENT_N,
    TOPOLOGY_KIND,
    VERTEBRA_N,
    VERSION,
)


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "vertebra_n": VERTEBRA_N,
            "segment_n": SEGMENT_N,
            "dof_per_segment": DOF_PER_SEGMENT,
            "topology": TOPOLOGY_KIND,
            "articulation": "rom-bounded",
            "load_path": "axial-conserved",
            "digest": "spine-blake16",
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "vertebra-count-mismatch",
            "rom-violation",
            "load-path-open",
            "digest-drift",
            "topology-cycle",
            "stored_prose-nonzero",
            "artifact-tree-copied",
            "articulation-singular",
            "segment-gap",
            "region-boundary-break",
        ],
        "obs": [
            "vertebra_n",
            "segment_n",
            "rom_ok",
            "load_residual",
            "digest",
            "curvature_lordosis",
            "curvature_kyphosis",
            "stability_margin",
        ],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
