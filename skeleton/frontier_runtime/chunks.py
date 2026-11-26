"""Spatial chunk membership with a membership list and an inverse index.

After a committed step every actor id appears in exactly one chunk. The
membership list and the inverse index are built separately and then compared.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


class ChunkPartitionError(ValueError):
    """Raised when chunk membership and the inverse index disagree."""


@dataclass(frozen=True)
class ChunkPartition:
    membership: tuple[tuple[str, tuple[str, ...]], ...]
    inverse: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "membership": [[chunk_id, list(actor_ids)] for chunk_id, actor_ids in self.membership],
            "inverse": [[actor_id, chunk_id] for actor_id, chunk_id in self.inverse],
        }


def chunk_id_for(position: tuple[float, float, float], chunk_size_m: float) -> str:
    if not chunk_size_m > 0 or not math.isfinite(chunk_size_m):
        raise ChunkPartitionError("chunk size must be positive")
    ix = math.floor(position[0] / chunk_size_m)
    iy = math.floor(position[1] / chunk_size_m)
    iz = math.floor(position[2] / chunk_size_m)
    return f"{ix}:{iy}:{iz}"


def partition_actors(
    actors: tuple[tuple[str, tuple[float, float, float]], ...],
    *,
    chunk_size_m: float,
) -> ChunkPartition:
    """Build both indexes from positions, then require them to agree."""
    membership: dict[str, list[str]] = {}
    inverse: dict[str, str] = {}
    for actor_id, position in actors:
        if actor_id in inverse:
            raise ChunkPartitionError(f"duplicate actor id {actor_id}")
        chunk_id = chunk_id_for(position, chunk_size_m)
        inverse[actor_id] = chunk_id
        membership.setdefault(chunk_id, []).append(actor_id)
    listed = tuple(
        (chunk_id, tuple(sorted(actor_ids)))
        for chunk_id, actor_ids in sorted(membership.items())
    )
    inverted = tuple(sorted(inverse.items()))
    partition = ChunkPartition(listed, inverted)
    verify_dual_chunks(partition)
    return partition


def verify_dual_chunks(partition: ChunkPartition | dict[str, object]) -> None:
    """Re-check that the membership list and the inverse index describe one set.

    Every actor is in exactly one chunk, and each direction names the other.
    """
    if isinstance(partition, ChunkPartition):
        membership = partition.membership
        inverse_pairs = partition.inverse
    elif isinstance(partition, dict):
        raw_members = partition.get("membership")
        raw_inverse = partition.get("inverse")
        if not isinstance(raw_members, list) or not isinstance(raw_inverse, list):
            raise ChunkPartitionError("chunk partition shape is invalid")
        membership = tuple(
            (str(chunk_id), tuple(str(actor_id) for actor_id in actor_ids))
            for chunk_id, actor_ids in raw_members
        )
        inverse_pairs = tuple((str(actor_id), str(chunk_id)) for actor_id, chunk_id in raw_inverse)
    else:
        raise ChunkPartitionError("chunk partition required")

    seen: list[str] = []
    from_members: dict[str, str] = {}
    for chunk_id, actor_ids in membership:
        if not actor_ids:
            raise ChunkPartitionError("empty chunk in membership list")
        for actor_id in actor_ids:
            if actor_id in from_members:
                raise ChunkPartitionError(f"actor {actor_id} is in more than one chunk")
            from_members[actor_id] = chunk_id
            seen.append(actor_id)
    from_inverse = dict(inverse_pairs)
    if len(from_inverse) != len(inverse_pairs):
        raise ChunkPartitionError("inverse index repeats an actor")
    if from_members != from_inverse:
        raise ChunkPartitionError("membership list and inverse index disagree")
    if len(seen) != len(from_members):
        raise ChunkPartitionError("actor is not a member of exactly one chunk")
