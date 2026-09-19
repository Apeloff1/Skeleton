"""Spine 1.0 facade (GB-20). Vertebral path-33. No artifacts/Spine copy."""

from __future__ import annotations

from skeleton.spine.articulation import all_rom_ok, clamp_to_rom, rom_for_segment
from skeleton.spine.capabilities import capabilities
from skeleton.spine.cards import spine_card
from skeleton.spine.chain import SpineChain, assert_chain_integrity, default_chain
from skeleton.spine.compare import ChainDiff, diff_chains, similarity
from skeleton.spine.constraint_solver import project_rom, satisfy
from skeleton.spine.digest import chain_digest, digests_equal, stable_neutral_digest
from skeleton.spine.engine import SpineEngine
from skeleton.spine.kinematics import end_effector, forward_frames
from skeleton.spine.law import (
    CERVICAL_N,
    COCCYX_N,
    DOF_PER_SEGMENT,
    LAYER,
    LUMBAR_N,
    PACKET,
    SACRAL_N,
    SEGMENT_N,
    THORACIC_N,
    TOPOLOGY_KIND,
    VERSION,
    VERTEBRA_N,
)
from skeleton.spine.load_path import build_axial_path, is_conserved
from skeleton.spine.metrics import compute_metrics
from skeleton.spine.posture import build_posture, list_postures
from skeleton.spine.serialize import chain_from_dict, chain_to_dict, roundtrip_ok
from skeleton.spine.taxonomy import REGION_COUNTS, Region, VertebraId, all_labels
from skeleton.spine.topology import is_path_graph, spine_graph
from skeleton.spine.vertebra import Pose6, Vertebra, ZERO_POSE

__all__ = [
    "CERVICAL_N",
    "COCCYX_N",
    "ChainDiff",
    "DOF_PER_SEGMENT",
    "LAYER",
    "LUMBAR_N",
    "PACKET",
    "Pose6",
    "REGION_COUNTS",
    "Region",
    "SACRAL_N",
    "SEGMENT_N",
    "SpineChain",
    "SpineEngine",
    "THORACIC_N",
    "TOPOLOGY_KIND",
    "VERSION",
    "VERTEBRA_N",
    "Vertebra",
    "VertebraId",
    "ZERO_POSE",
    "all_labels",
    "all_rom_ok",
    "assert_chain_integrity",
    "build_axial_path",
    "build_posture",
    "capabilities",
    "chain_digest",
    "chain_from_dict",
    "chain_to_dict",
    "clamp_to_rom",
    "compute_metrics",
    "default_chain",
    "diff_chains",
    "digests_equal",
    "end_effector",
    "forward_frames",
    "is_conserved",
    "is_path_graph",
    "list_postures",
    "project_rom",
    "rom_for_segment",
    "roundtrip_ok",
    "satisfy",
    "similarity",
    "spine_card",
    "spine_graph",
    "stable_neutral_digest",
]
