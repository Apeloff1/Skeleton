"""P1 visual world-model adapter contract.

Candidate-only. Defines the evidence shape a real 3D reconstruction
adapter must produce. Does not load weights or call external models.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


class P1WorldModelError(ValueError):
    pass


@dataclass(frozen=True)
class WorldModelEvidence:
    """Evidence a P1 adapter must attach before any runtime admission."""

    source_digest: str
    mesh_vertex_count: int
    mesh_triangle_count: int
    reconstruction_digest: str
    adapter_id: str

    def __post_init__(self) -> None:
        for label, value in (("source", self.source_digest), ("reconstruction", self.reconstruction_digest)):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise P1WorldModelError(f"{label}_digest must be lowercase SHA-256")
        if self.mesh_vertex_count < 3 or self.mesh_triangle_count < 1:
            raise P1WorldModelError("mesh must have at least 3 vertices and 1 triangle")
        if not self.adapter_id or len(self.adapter_id) > 80:
            raise P1WorldModelError("adapter_id required")


def world_model_receipt(evidence: WorldModelEvidence) -> str:
    """Content-address the evidence. No model is invoked."""
    payload = json.dumps(
        {
            "adapter": evidence.adapter_id,
            "source": evidence.source_digest,
            "verts": evidence.mesh_vertex_count,
            "tris": evidence.mesh_triangle_count,
            "recon": evidence.reconstruction_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()
