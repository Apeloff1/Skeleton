"""Use observed host pressure to bound semantic shard fanout without dropping shards.

This is local scheduling admission, not a hard OS allocation guarantee. A
process pool may require additional interpreter/library memory. Under low
headroom the operation fails explicitly rather than silently reducing recall.
"""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy
from .offline_resources import LocalResourceSnapshot,LocalResourcePressure


@dataclass(frozen=True,slots=True)
class SemanticFanout:
    workers:int
    logical_worker_bytes:int
    logical_available_bytes:int
    all_shards_required:bool=True


def admit_semantic_fanout(snapshot,policy,dimension):
    if not isinstance(snapshot,LocalResourceSnapshot) or not isinstance(policy,DiskANNPolicy):
        raise TypeError("measured local resource snapshot and ANN policy required")
    if type(dimension) is not int or not 2<=dimension<=4096:
        raise ValueError("invalid ANN runtime dimensions")
    # Bounds cover worker candidate dictionaries, row/scalar scratch and a
    # conservative interpreter overhead. Index file data stays disk-backed.
    entries=(policy.bands*policy.probes+2*policy.max_anchor_terms)*policy.bucket_limit
    base=(128 if policy.worker_mode=="process" else 16)*1024**2
    per=base+entries*320+policy.shard_candidate_limit*(dimension*4+1024)
    # Preserve physical RAM for inference; never count swap as equivalent RAM.
    available=int(snapshot.available_ram_bytes*.30*(1-.8*snapshot.memory_pressure_ratio))
    if snapshot.should_spill_early:available//=2
    workers=min(policy.shards,policy.workers,snapshot.suggested_index_jobs,available//per)
    if workers<1:raise LocalResourcePressure("insufficient measured memory for semantic shard worker")
    return SemanticFanout(workers,per,available)
