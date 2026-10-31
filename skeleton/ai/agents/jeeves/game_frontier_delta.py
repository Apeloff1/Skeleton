"""Compact, independently replayable deltas over verified game frames.

The full frame source remains authoritative. A delta encodes changed
kinematics and a bounded set of touched/retired chunk cells. Reconstruction
checks full source frame SHA and both GDD verifiers; neither compressed data
nor the model is allowed to modify canonical world law.
"""
from __future__ import annotations
import json
import math
from typing import Mapping

from .game_frontier_frame_coherence import (
    FrameReceipt, FrameObject, GDDFrameNote, GDDSource,
    advance_frame, verify_frame, digest,
)
from .game_frontier_production import Vec3


class FrameDeltaError(ValueError):
    pass


def _entities(frame: FrameReceipt | None) -> dict[str, FrameObject]:
    return ({o.entity_id:o for c in frame.chunks for o in c.objects}
            if frame is not None else {})


def _position(o: FrameObject) -> dict:
    return {"id":o.entity_id,
            "position":[o.position.x,o.position.y,o.position.z],
            "velocity":[o.velocity.x,o.velocity.y,o.velocity.z],
            "source":o.source_digest}


def _cell(o: FrameObject, dimension: float) -> tuple[int,int]:
    return (math.floor(o.position.x/dimension),math.floor(o.position.y/dimension))


def create_frame_delta(
    frame: FrameReceipt, gdd: GDDSource, *,
    previous: FrameReceipt | None = None,
    chunk_size_m: float = 32.,
    max_speed_mps: float = 500.,
) -> dict:
    if (not isinstance(frame,FrameReceipt) or
        not isinstance(gdd,GDDSource) or
        not all(verify_frame(frame,gdd,previous=previous,
                             chunk_size_m=chunk_size_m,max_speed_mps=max_speed_mps))):
        raise FrameDeltaError("double verified source frame required")
    before=_entities(previous)
    after=_entities(frame)
    if (len(after)!=sum(len(c.objects) for c in frame.chunks) or
        previous is not None and set(before)!=set(after)):
        raise FrameDeltaError("unauthorized actor birth/deletion or duplicate")
    changed=[_position(after[key]) for key in sorted(after)
             if key not in before or _position(after[key])!=_position(before[key])]
    old_cells={}
    new_cells={}
    for entity in before.values():
        old_cells.setdefault(_cell(entity,chunk_size_m),set()).add(entity.entity_id)
    for entity in after.values():
        new_cells.setdefault(_cell(entity,chunk_size_m),set()).add(entity.entity_id)
    affected={item["id"] for item in changed}
    touched=[]
    for key in sorted(set(old_cells)|set(new_cells)):
        prior=old_cells.get(key,set())
        current=new_cells.get(key,set())
        modified=sorted(current.intersection(affected))
        if prior!=current or modified or previous is None:
            touched.append({
                "chunk_xy":list(key),
                "before":sorted(prior),"after":sorted(current),
                "changed_entities":modified,
                "retired":bool(prior and not current),
            })
    raw={
        "schema":"skeleton.game.frame_delta.v1",
        "gdd_digest":gdd.source_digest,"frame_index":frame.frame_index,
        "fps":frame.fps,"time_ns":frame.time_ns,
        "chunk_size_m":float(chunk_size_m),
        "previous_frame_digest":previous.receipt_digest if previous else None,
        "source_frame_digest":frame.receipt_digest,
        "object_count":len(after),"unchanged_count":len(after)-len(changed),
        "changed_objects":changed,"touched_chunks":touched,
        "notes":[n.__dict__ for n in frame.note_from_previous],
        "authority":"verified_source_delta_not_engine_state_mutation",
    }
    return {**raw,"receipt_digest":digest(raw)}


def restore_frame_delta(
    delta: Mapping, gdd: GDDSource, *,
    previous: FrameReceipt | None = None,
    max_speed_mps: float = 500.,
) -> FrameReceipt:
    """Reconstruct exact typed frame and both independent GDD checks."""
    if not isinstance(delta,Mapping):
        raise FrameDeltaError("typed content addressed delta required")
    bare={k:v for k,v in delta.items() if k!="receipt_digest"}
    if (delta.get("schema")!="skeleton.game.frame_delta.v1" or
        digest(bare)!=delta.get("receipt_digest") or
        delta.get("gdd_digest")!=gdd.source_digest or
        delta.get("previous_frame_digest")!=
            (previous.receipt_digest if previous else None) or
        delta.get("authority")!="verified_source_delta_not_engine_state_mutation"):
        raise FrameDeltaError("delta custody or prior-frame continuity rejected")
    try:
        chunk_size=float(delta["chunk_size_m"])
        actors=_entities(previous)
        changed=delta["changed_objects"]
        if not isinstance(changed,list) or len(changed)>65536:
            raise FrameDeltaError("bounded changed actor list required")
        seen=set()
        for item in changed:
            name=item["id"]
            if name in seen or type(name) is not str:
                raise FrameDeltaError("duplicate actor update")
            seen.add(name)
            actors[name]=FrameObject(
                name,Vec3(*item["position"]),Vec3(*item["velocity"]),
                item["source"])
        if len(actors)!=delta["object_count"]:
            raise FrameDeltaError("delta entity coverage mismatch")
        notes=tuple(GDDFrameNote(
            entry["world_law_index"],entry["category"],entry["text"],
            entry["author_kind"]) for entry in delta["notes"])
        frame=advance_frame(
            frame_index=delta["frame_index"],fps=delta["fps"],
            gdd=gdd,objects=tuple(actors.values()),
            previous=previous,notes=notes,
            chunk_size_m=chunk_size,max_speed_mps=max_speed_mps)
        expected=create_frame_delta(
            frame,gdd,previous=previous,
            chunk_size_m=chunk_size,max_speed_mps=max_speed_mps)
        if (frame.receipt_digest!=delta["source_frame_digest"] or
            frame.time_ns!=delta["time_ns"] or expected!=delta):
            raise FrameDeltaError("delta cannot reproduce exact source frame")
        return frame
    except (KeyError,TypeError,ValueError,IndexError,AttributeError) as error:
        if isinstance(error,FrameDeltaError):
            raise
        raise FrameDeltaError("malformed or incoherent replay delta") from error


def verify_frame_delta(
    delta: Mapping, source: FrameReceipt, gdd: GDDSource, *,
    previous: FrameReceipt | None = None,
    chunk_size_m: float = 32.,
    max_speed_mps: float = 500.,
) -> tuple[bool,bool]:
    """A checks receipt hash; B independently restores and compares source."""
    try:
        if not isinstance(delta,Mapping):
            return False,False
        verified_a=digest({k:v for k,v in delta.items()
                           if k!="receipt_digest"})==delta.get("receipt_digest")
        frame=restore_frame_delta(
            delta,gdd,previous=previous,max_speed_mps=max_speed_mps)
        return verified_a,bool(
            frame==source and
            delta["chunk_size_m"]==float(chunk_size_m))
    except (FrameDeltaError,ValueError,KeyError,TypeError,AttributeError):
        return False,False
