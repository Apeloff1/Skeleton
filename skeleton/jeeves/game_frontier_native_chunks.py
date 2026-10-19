"""Independent source/observed chunk partition verification for Godot captures.

Captures are untrusted telemetry reports, not GPU/physics attestations. The
native exporter records its observed actor positions and chunk membership.
This module independently reconstructs membership, checks exact coverage and
bounds, and emits an immutable, content-addressed comparison receipt.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import math
from typing import Mapping


class NativeChunkError(ValueError):
    pass


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def _point(x: object) -> tuple[float,float,float]:
    if (not isinstance(x,list) or len(x)!=3 or
        any(type(v) not in (float,int) or not math.isfinite(v)
            or abs(v)>1e8 for v in x)):
        raise NativeChunkError("native game XYZ is nonfinite or invalid")
    return float(x[0]),float(x[1]),float(x[2])


def inspect_native_chunks(sample: Mapping, *, expected_chunk_size_m: float = 32.,
                          require_native_partition: bool = False) -> dict:
    """Reconstruct observed chunk memberships; independently compare v2 proof.

    A hashes the original reported actor/chunk source. B calculates partition
    independently and checks no actor missing/duplicated. A successful return
    proves internal consistency of a *client report*, not its native origin.
    """
    if (type(expected_chunk_size_m) not in (int,float) or
        not math.isfinite(expected_chunk_size_m) or
        not .1<=expected_chunk_size_m<=1e5 or
        not isinstance(sample,Mapping)):
        raise NativeChunkError("valid bounded typed source required")
    units=float(expected_chunk_size_m)
    actors=sample.get("actors")
    if not isinstance(actors,list) or not 1<=len(actors)<=256:
        raise NativeChunkError("native game actor count 1..256 required")
    groups=defaultdict(list)
    all_ids=set()
    for actor in actors:
        if not isinstance(actor,Mapping):
            raise NativeChunkError("malformed native source actor")
        name=actor.get("id")
        if type(name) is not str or not name or len(name)>128 or name in all_ids:
            raise NativeChunkError("duplicate/invalid native actor ID")
        all_ids.add(name)
        x,y,z=_point(actor.get("world_xyz_m"))
        _point(actor.get("velocity_xyz_mps"))
        contacts=actor.get("contact_count")
        if contacts is not None and (type(contacts) is not int or
                                    not 0<=contacts<=64):
            raise NativeChunkError("native contact count outside budget")
        kind=actor.get("source_kind")
        if kind is not None and kind not in (
            "native_rigid_reference","generated_source_proxy"):
            raise NativeChunkError("unknown native actor observation kind")
        groups[(math.floor(x/units),math.floor(y/units))].append(name)
    expected=[
        {"chunk_xy":[cx,cy],"actor_ids":sorted(groups[(cx,cy)])}
        for cx,cy in sorted(groups)]
    stored=sample.get("native_chunks")
    if stored is None:
        if require_native_partition:
            raise NativeChunkError("explicit native chunk partition required")
        native_matches=None
    else:
        if (sample.get("native_chunk_size_m")!=units or
            not isinstance(stored,list) or len(stored)>256):
            raise NativeChunkError("native chunk resolution incompatible")
        if stored!=expected:
            raise NativeChunkError("native chunk partition disagrees with actor physics")
        native_matches=True
    source={
        "schema":"skeleton.game.native_chunk_inspection.v1",
        "native_tick":sample.get("native_tick"),
        "fps":sample.get("fps"),
        "source_candidate_digest":sample.get("scene_candidate_digest"),
        "actor_source_digest":_digest(actors),
        "native_partition_digest":_digest(stored) if stored is not None else None,
        "chunk_size_m":units,
        "chunks":expected,"actor_count":len(actors),
        "chunk_count":len(expected),
        "verifier_a_rehashed_native_source":True,
        "verifier_b_partition_exactly_once":len(all_ids)==len(actors),
        "native_partition_confirmed":native_matches,
        "authority":"reported_native_physics_partition_not_GPU_attestation",
    }
    source["receipt_digest"]=_digest(source)
    return source
