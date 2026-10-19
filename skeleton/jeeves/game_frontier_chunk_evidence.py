"""Content-addressed per-chunk evidence for game meshes and GDD build frames.

Produces portable receipts, not extra world authority or a second evidence
store. An independent verifier must recompute from source mesh/FrameReceipt;
stored booleans or hashes alone never establish integrity. Each chunk records
specific claims, source IDs, prior-frame movement, independent A/B checks and
signed-GDD note anchors. Native GPU/render evidence is not implied.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
from typing import Mapping

from .game_frontier_production import Vec3
from .game_frontier_chunks import (
    MeshChunk, chunk_mesh, verify_chunks,
)
from .game_frontier_frame_coherence import (
    FrameChunk, FrameReceipt, GDDSource, verify_frame,
)


class ChunkEvidenceError(ValueError):
    pass


def _hash(payload: object) -> str:
    try:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ChunkEvidenceError("chunk receipt is not canonical JSON") from exc
    return sha256(data.encode()).hexdigest()


def _sealed(payload: dict) -> dict:
    result = dict(payload)
    result["receipt_digest"] = _hash(payload)
    return result


def _source_digest(vertices: tuple[Vec3,...],
                   faces: tuple[tuple[int,int,int],...], era: str) -> str:
    return _hash({
        "era": era,
        "vertices": [[v.x,v.y,v.z] for v in vertices],
        "triangles": faces,
    })


def _bounds(vertices: tuple[Vec3,...]) -> list[list[float]]:
    if not vertices:
        return []
    return [
        [min(getattr(p, c) for p in vertices),
         max(getattr(p, c) for p in vertices)]
        for c in ("x","y","z")
    ]


def build_mesh_chunk_receipts(
    vertices: tuple[Vec3,...],
    faces: tuple[tuple[int,int,int],...],
    *, era: str,
    size_m: float = 32.,
    max_faces_per_chunk: int = 20000,
    chunks: tuple[MeshChunk,...] | None = None,
) -> dict:
    """Record mesh face coverage and independently verified chunk provenance.

    Verifier A rehashes serialized chunk payloads. Verifier B checks every
    mapped source vertex, exact source-face topology, spatial centroid and
    global face coverage via the existing independent geometry verifier.
    """
    supplied = chunks if chunks is not None else chunk_mesh(
        vertices,faces,era=era,chunk_size_m=size_m,
        max_faces_per_chunk=max_faces_per_chunk)
    aggregate = verify_chunks(supplied,vertices,faces,era=era)
    if not aggregate.approved_by_both:
        raise ChunkEvidenceError("mesh chunk integrity/topology/coverage rejected")
    identity = _source_digest(vertices,faces,aggregate.era)
    receipts=[]
    count_faces=Counter()
    for index, chunk in enumerate(supplied):
        payload=chunk.source_payload()
        a=(_hash(payload)==chunk.content_digest and
           chunk.engine_era==aggregate.era)
        mapped=[]
        b=(len(chunk.faces)==len(chunk.source_face_ids) and
           len(chunk.vertex_indices)==len(chunk.vertices) and
           len(set(chunk.vertex_indices))==len(chunk.vertex_indices))
        for local, global_index in zip(chunk.vertices,chunk.vertex_indices):
            if not 0<=global_index<len(vertices) or local!=vertices[global_index]:
                b=False
        for source_index, local_face in zip(chunk.source_face_ids,chunk.faces):
            if not 0<=source_index<len(faces) or any(
                type(v) is not int or not 0<=v<len(chunk.vertex_indices)
                for v in local_face
            ):
                b=False
                continue
            global_face=tuple(chunk.vertex_indices[i] for i in local_face)
            original=faces[source_index]
            centroid=(
                sum(vertices[i].x for i in original)/3,
                sum(vertices[i].y for i in original)/3,
            )
            if (global_face!=original or
                (math.floor(centroid[0]/chunk.size_m),
                 math.floor(centroid[1]/chunk.size_m))!=(chunk.chunk_x,chunk.chunk_y)):
                b=False
            mapped.append(source_index)
            count_faces[source_index]+=1
        if not a or not b:
            raise ChunkEvidenceError(f"mesh evidence rejected at chunk {index}")
        record={
            "schema":"skeleton.game.mesh_chunk_receipt.v1",
            "index":index,"era":aggregate.era,
            "chunk_xy":[chunk.chunk_x,chunk.chunk_y],
            "source_geometry_digest":identity,
            "source_chunk_digest":chunk.content_digest,
            "source_face_ids":mapped,
            "source_vertex_ids":list(chunk.vertex_indices),
            "face_count":len(mapped),"vertex_count":len(chunk.vertices),
            "bounds_xyz_m":_bounds(chunk.vertices),
            "verifier_a":{
                "passed":a,"method":"recompute_sha256_of_chunk_payload",
                "evidence_digest":_hash(payload),
            },
            "verifier_b":{
                "passed":b,"method":"source_vertex_face_centroid_reconstruction",
                "source_faces_digest":_hash([faces[i] for i in mapped]),
            },
            "authority":"verified_mesh_candidate_not_native_render_proof",
        }
        receipts.append(_sealed(record))
    coverage=(len(count_faces)==len(faces) and
              all(count_faces[i]==1 for i in range(len(faces))))
    if not coverage:
        raise ChunkEvidenceError("mesh source triangles missing or repeated")
    return _sealed({
        "schema":"skeleton.game.mesh_chunk_evidence_bundle.v1",
        "era":aggregate.era,"source_geometry_digest":identity,
        "source_vertex_count":len(vertices),"source_triangle_count":len(faces),
        "chunk_count":len(receipts),"receipts":receipts,
        "verifier_a":aggregate.authenticated,
        "verifier_b":(aggregate.topology_reconstructed and
                      aggregate.full_coverage and aggregate.bounds_valid),
        "coverage_exactly_once":coverage,
        "authority":"source_mesh_evidence_only_not_native_engine_certification",
    })


def verify_mesh_chunk_receipts(
    evidence: Mapping,
    vertices: tuple[Vec3,...], faces: tuple[tuple[int,int,int],...],
    *, era: str, size_m: float = 32.,
    chunks: tuple[MeshChunk,...] | None = None,
    max_faces_per_chunk: int = 20000,
) -> tuple[bool,bool]:
    """Recompute both verifiers from original source; do not trust flags."""
    if not isinstance(evidence,Mapping):
        return False,False
    original={k:v for k,v in evidence.items() if k!="receipt_digest"}
    if evidence.get("receipt_digest")!=_hash(original):
        return False,False
    try:
        rebuilt=build_mesh_chunk_receipts(
            vertices,faces,era=era,size_m=size_m,
            max_faces_per_chunk=max_faces_per_chunk,chunks=chunks)
    except (ChunkEvidenceError,ValueError,TypeError,IndexError):
        return False,False
    if evidence==rebuilt:
        return True,True
    stored=evidence.get("receipts",[])
    current=rebuilt["receipts"]
    verifier_a=(len(stored)==len(current) and
                all(isinstance(row,Mapping) and
                    row.get("source_chunk_digest")==expected["source_chunk_digest"] and
                    row.get("verifier_a")==expected["verifier_a"]
                    for row,expected in zip(stored,current)))
    return verifier_a,False


def _objects(frame: FrameReceipt) -> dict[str,tuple[FrameChunk,object]]:
    return {item.entity_id:(chunk,item)
            for chunk in frame.chunks for item in chunk.objects}


def _prior_integrity(previous_evidence: Mapping,
                     previous: FrameReceipt, gdd: GDDSource) -> bool:
    if not isinstance(previous_evidence, Mapping):
        return False
    try:
        original={k:v for k,v in previous_evidence.items() if k!="receipt_digest"}
        return (previous_evidence.get("receipt_digest")==_hash(original) and
                previous_evidence.get("schema")==
                   "skeleton.game.frame_chunk_evidence_bundle.v1" and
                previous_evidence.get("source_frame_digest")==previous.receipt_digest and
                previous_evidence.get("signed_gdd_digest")==gdd.source_digest and
                previous_evidence.get("verifier_a") is True and
                previous_evidence.get("verifier_b") is True and
                isinstance(previous_evidence.get("receipts"),list) and
                [row.get("source_chunk_digest") for row in previous_evidence["receipts"]]==
                    [c.content_digest for c in previous.chunks] and
                all(isinstance(row,Mapping) and
                    row.get("receipt_digest")==_hash({
                        k:v for k,v in row.items() if k!="receipt_digest"
                    }) for row in previous_evidence["receipts"]))
    except (TypeError,ValueError,KeyError,AttributeError):
        return False


def build_frame_chunk_receipts(
    frame: FrameReceipt,
    gdd: GDDSource, *,
    previous: FrameReceipt | None = None,
    previous_evidence: Mapping | None = None,
    chunk_size_m: float = 32.,
    max_speed_mps: float = 500.,
) -> dict:
    """Document per-chunk source, movements, notes and two verifiers.

    A authenticates the source FrameChunk; B independently validates chunk
    partition/movement, GDD law links and transitions using source records.
    Earlier bundle is optional for legacy frames; if present it must match
    the preceding frame and is cryptographically linked.
    """
    if (previous_evidence is not None and
        (previous is None or
         not _prior_integrity(previous_evidence,previous,gdd))):
        raise ChunkEvidenceError("prior chunk evidence is not linked to verified frame")
    a,b=verify_frame(frame,gdd,previous=previous,
                     chunk_size_m=chunk_size_m,max_speed_mps=max_speed_mps)
    if not a or not b:
        raise ChunkEvidenceError("frame A/B verifiers refused evidence")
    old=_objects(previous) if previous else {}
    now=_objects(frame)
    if len(now)!=sum(len(c.objects) for c in frame.chunks):
        raise ChunkEvidenceError("source frame contains duplicate entity IDs")
    note_links=[]
    for note in frame.note_from_previous:
        if not 0<=note.world_law_index<len(gdd.world_laws):
            raise ChunkEvidenceError("note refers to nonexistent GDD law")
        note_links.append({
            "world_law_index":note.world_law_index,
            "world_law_digest":_hash(gdd.world_laws[note.world_law_index]),
            "note_digest":_hash(note.__dict__),
            "review_status":note.author_kind,
            "category":note.category,
        })
    notes_root=_hash(note_links)
    receipts=[]
    incoming=0
    outgoing=0
    for index,chunk in enumerate(frame.chunks):
        source=chunk.payload()
        a_check=_hash(source)==chunk.content_digest
        ids=[item.entity_id for item in chunk.objects]
        b_check=(len(set(ids))==len(ids) and
                 all((math.floor(item.position.x/chunk_size_m),
                      math.floor(item.position.y/chunk_size_m))==chunk.chunk_key
                     for item in chunk.objects))
        changed=[]
        arrivals=[]
        departures=[]
        stable=0
        for item in chunk.objects:
            if item.entity_id not in old:
                if previous is not None:
                    b_check=False
                arrivals.append(item.entity_id)
                continue
            prior_chunk,prior_item=old[item.entity_id]
            diff=item.position-prior_item.position
            displacement=math.sqrt(diff.dot(diff))
            if prior_chunk.chunk_key!=chunk.chunk_key:
                arrivals.append(item.entity_id)
                incoming+=1
            elif displacement>1e-12:
                changed.append(item.entity_id)
            else:
                stable+=1
            if item.source_digest!=prior_item.source_digest:
                b_check=False
        if previous:
            for prior_chunk in previous.chunks:
                if prior_chunk.chunk_key!=chunk.chunk_key:
                    continue
                for item in prior_chunk.objects:
                    newer=now.get(item.entity_id)
                    if newer is None:
                        b_check=False
                    elif newer[0].chunk_key!=chunk.chunk_key:
                        departures.append(item.entity_id)
                        outgoing+=1
        if not a_check or not b_check:
            raise ChunkEvidenceError("chunk source content or transition disagrees")
        record=_sealed({
            "schema":"skeleton.game.frame_chunk_receipt.v1",
            "frame_index":frame.frame_index,"fps":frame.fps,
            "chunk_xy":list(chunk.chunk_key),"index":index,
            "source_frame_digest":frame.receipt_digest,
            "source_chunk_digest":chunk.content_digest,
            "signed_gdd_digest":gdd.source_digest,
            "source_entities":ids,
            "source_asset_digests":[item.source_digest for item in chunk.objects],
            "object_count":len(chunk.objects),
            "world_bounds_xyz_m":_bounds(tuple(item.position for item in chunk.objects)),
            "unchanged_entities":stable,
            "moved_within_chunk":sorted(changed),
            "arriving_entities":sorted(arrivals),
            "departing_entities":sorted(departures),
            "prior_frame_digest":previous.receipt_digest if previous else None,
            "gdd_between_frame_notes_digest":notes_root,
            "gdd_world_law_links":note_links,
            "verifier_a":{
                "passed":a_check,
                "method":"independent_chunk_sha256_payload",
                "recomputed_digest":_hash(source),
            },
            "verifier_b":{
                "passed":b_check,
                "method":"geometry_partition_entity_identity_temporal_GDD",
                "movement_source_digest":_hash([
                    [item.entity_id,
                     list(old[item.entity_id][0].chunk_key) if item.entity_id in old else None,
                     list(chunk.chunk_key),
                     item.source_digest]
                    for item in chunk.objects]),
            },
            "authority":"source_frame_chunk_candidate_not_native_renderer_proof",
        })
        receipts.append(record)
    if previous:
        earlier_keys={obj.entity_id:ch.chunk_key for ch in previous.chunks
                      for obj in ch.objects}
        expected=sum(1 for ch in frame.chunks for obj in ch.objects
                     if earlier_keys[obj.entity_id]!=ch.chunk_key)
        if expected!=incoming or expected!=outgoing:
            raise ChunkEvidenceError("chunk migration receipts fail conservation")
    root=_sealed({
        "schema":"skeleton.game.frame_chunk_evidence_bundle.v1",
        "frame_index":frame.frame_index,"fps":frame.fps,
        "source_frame_digest":frame.receipt_digest,
        "previous_frame_digest":previous.receipt_digest if previous else None,
        "previous_evidence_digest":(
            previous_evidence["receipt_digest"] if previous_evidence else None),
        "signed_gdd_digest":gdd.source_digest,
        "chunk_count":len(receipts),"object_count":len(now),
        "cross_chunk_migrations":incoming,
        "chunk_receipts":len(receipts),
        "source_note_count":len(note_links),
        "gdd_note_links_digest":notes_root,
        "receipts":receipts,
        "verifier_a":a,"verifier_b":b,
        "authority":"dual_checked_frame_chunks_GDD_candidate_not_native_proof",
    })
    return root


def verify_frame_chunk_receipts(
    evidence: Mapping, frame: FrameReceipt, gdd: GDDSource, *,
    previous: FrameReceipt | None = None,
    previous_evidence: Mapping | None = None,
    chunk_size_m: float = 32., max_speed_mps: float = 500.,
) -> tuple[bool,bool]:
    """Independently replay provenance and transitions, compare exact receipts."""
    if not isinstance(evidence,Mapping):
        return False,False
    try:
        original={k:v for k,v in evidence.items() if k!="receipt_digest"}
        a=evidence.get("receipt_digest")==_hash(original)
        for row in evidence.get("receipts",[]):
            a=a and isinstance(row,Mapping) and row.get("receipt_digest")==_hash(
                {k:v for k,v in row.items() if k!="receipt_digest"})
        expected=build_frame_chunk_receipts(
            frame,gdd,previous=previous,
            previous_evidence=previous_evidence,
            chunk_size_m=chunk_size_m,max_speed_mps=max_speed_mps)
        b=evidence==expected
        return bool(a),bool(b)
    except (ChunkEvidenceError,KeyError,TypeError,ValueError,AttributeError):
        return False,False
