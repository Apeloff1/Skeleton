"""Frame-by-frame, per-chunk double verification and signed-GDD context.

This is an engine-neutral *build progress* reference that can be called at every
render frame (30/50/60/120 Hz). It does not claim any native engine already
calls it on every rendered frame. Output is immutable receipts for the
canonical Jeeves/Forge owner. The GDD remains the existing signed story-bible;
AI suggestions NEVER mutate the signed canon or self-approve.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from skeleton.ai.game_builder.story_canon_fabric import validate_story_bible
from .game_frontier_production import Vec3


class FrameCoherenceError(ValueError):
    pass


def digest(value: object) -> str:
    try:
        encoded=json.dumps(value,sort_keys=True,separators=(",",":"),
                           ensure_ascii=True,allow_nan=False).encode()
    except (TypeError,ValueError,OverflowError) as exc:
        raise FrameCoherenceError("frame content must be canonical finite JSON") from exc
    return sha256(encoded).hexdigest()


def sha(value: str) -> bool:
    return type(value) is str and len(value)==64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class GDDSource:
    project_id: str
    source_digest: str
    phase: str
    world_laws: tuple[str, ...]
    title: str
    authority: str = "signed_story_bible_read_only"

    def __post_init__(self) -> None:
        if not self.project_id or not sha(self.source_digest):
            raise FrameCoherenceError("verified signed GDD source required")
        if not self.world_laws or any(not law or len(law)>500 for law in self.world_laws):
            raise FrameCoherenceError("GDD must declare bounded world laws")


def bind_signed_gdd(story_bible: dict) -> GDDSource:
    """Call the existing *canonical* signed story bible validator."""
    try:
        validate_story_bible(story_bible)
    except (TypeError,ValueError,KeyError,AssertionError) as exc:
        raise FrameCoherenceError("unverified or conflicting signed GDD") from exc
    return GDDSource(story_bible["project"],story_bible["digest"],
                     story_bible["phase"],tuple(story_bible["world"]["laws"]),
                     story_bible["title"])


@dataclass(frozen=True)
class FrameObject:
    entity_id: str
    position: Vec3
    velocity: Vec3
    source_digest: str

    def __post_init__(self) -> None:
        if not self.entity_id or len(self.entity_id)>128 or not sha(self.source_digest):
            raise FrameCoherenceError("frame object requires provenance and identity")
        for v in (self.position.x,self.position.y,self.position.z,
                  self.velocity.x,self.velocity.y,self.velocity.z):
            if type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e8:
                raise FrameCoherenceError("nonfinite frame geometry")


@dataclass(frozen=True)
class FrameChunk:
    frame: int
    chunk_key: tuple[int,int]
    objects: tuple[FrameObject,...]
    content_digest: str

    def payload(self) -> dict:
        return {
            "frame":self.frame,
            "cell":list(self.chunk_key),
            "entities":[{
                "id":o.entity_id,
                "position":[o.position.x,o.position.y,o.position.z],
                "velocity":[o.velocity.x,o.velocity.y,o.velocity.z],
                "source":o.source_digest,
            } for o in self.objects],
        }


@dataclass(frozen=True)
class GDDFrameNote:
    world_law_index: int
    category: str
    text: str
    author_kind: str = "ai_proposal"

    def __post_init__(self) -> None:
        if type(self.world_law_index) is not int or self.world_law_index<0:
            raise FrameCoherenceError("signed GDD world law index required")
        if self.category not in ("design_context","collision",
                                  "continuity","weather","narrative","quality"):
            raise FrameCoherenceError("unsupported between-frame note")
        if self.author_kind not in ("ai_proposal","human_reviewed","engine_observation"):
            raise FrameCoherenceError("no note may claim canonical GDD authority")
        if type(self.text) is not str or not 1<=len(self.text)<=1000:
            raise FrameCoherenceError("bounded frame note required")


@dataclass(frozen=True)
class FrameReceipt:
    frame_index: int
    time_ns: int
    fps: int
    gdd_digest: str
    previous_digest: str | None
    chunks: tuple[FrameChunk,...]
    note_from_previous: tuple[GDDFrameNote,...]
    verifier_a_integrity: bool
    verifier_b_coherence: bool
    verified: bool
    receipt_digest: str
    authority: str = "verified_candidate_not_admitted_gameplay"

    def payload(self) -> dict:
        return {
            "frame":self.frame_index,"clock_ns":self.time_ns,"fps":self.fps,
            "gdd_digest":self.gdd_digest,"prior":self.previous_digest,
            "chunks":[{"digest":c.content_digest,"payload":c.payload()}
                      for c in self.chunks],
            "notes":[n.__dict__ for n in self.note_from_previous],
            "a":self.verifier_a_integrity,"b":self.verifier_b_coherence,
            "verified":self.verified,"authority":self.authority,
        }


def _cell(o: FrameObject, chunk_size_m: float) -> tuple[int,int]:
    return math.floor(o.position.x/chunk_size_m),math.floor(o.position.y/chunk_size_m)


def _verify_transition(previous: FrameReceipt | None,
                       objects: Sequence[FrameObject],
                       fps: int,time_ns: int,gdd: GDDSource,
                       max_speed_mps: float) -> bool:
    if previous is None:
        return True
    if previous.gdd_digest!=gdd.source_digest or previous.fps!=fps or (
        time_ns <= previous.time_ns or previous.frame_index<0):
        return False
    dt=(time_ns-previous.time_ns)/1e9
    if not 0 < dt <= 1.05/fps:
        return False
    earlier={o.entity_id:o for c in previous.chunks for o in c.objects}
    now={o.entity_id:o for o in objects}
    # Entity duplication is already forbidden; spawn/removal is not silently
    # accepted. The caller must authorize changed entity sets separately.
    if set(earlier)!=set(now):
        return False
    for key,obj in now.items():
        old=earlier[key]
        if old.source_digest!=obj.source_digest:
            return False
        delta=obj.position-old.position
        v=obj.velocity
        vv=math.sqrt(v.dot(v))
        oldv=math.sqrt(old.velocity.dot(old.velocity))
        distance=math.sqrt(delta.dot(delta))
        if vv>max_speed_mps or oldv>max_speed_mps:
            return False
        # Conservative trapezoidal movement coherence with bounded physics
        # acceleration tolerance; does not claim accurate integration.
        limit=(max(vv,oldv)+.5)*dt + .02
        if distance>limit:
            return False
    return True


def verify_frame(receipt: FrameReceipt,gdd: GDDSource, *,
                 previous: FrameReceipt | None = None,
                 chunk_size_m: float = 32.,
                 max_speed_mps: float = 500.) -> tuple[bool,bool]:
    """Independent A content-hash verifier and B temporal+GDD verifier.

    Neither verifier merely trusts the receipt's stored booleans.
    """
    if not sha(receipt.receipt_digest):
        return False,False
    a=(digest(receipt.payload())==receipt.receipt_digest and
       all(digest(c.payload())==c.content_digest for c in receipt.chunks))
    if not receipt.verified or not receipt.verifier_a_integrity or not receipt.verifier_b_coherence:
        a=False
    if receipt.fps not in (30,50,60,120) or receipt.gdd_digest!=gdd.source_digest:
        return a,False
    if previous is None:
        continuity=(receipt.frame_index==0 and receipt.previous_digest is None
                    and not receipt.note_from_previous and receipt.time_ns==0)
    else:
        continuity=(previous.verified and
                    receipt.frame_index==previous.frame_index+1 and
                    receipt.previous_digest==previous.receipt_digest)
    all_objects=[x for c in receipt.chunks for x in c.objects]
    unique=(len(all_objects)==len(set(x.entity_id for x in all_objects)))
    unique_cells=(len(receipt.chunks)==len(set(c.chunk_key for c in receipt.chunks)))
    correct_partition=all(
        c.frame==receipt.frame_index and
        all(_cell(x,chunk_size_m)==c.chunk_key for x in c.objects)
        for c in receipt.chunks)
    notes_valid=all(n.world_law_index<len(gdd.world_laws) for n in receipt.note_from_previous)
    notes_valid=notes_valid and len(receipt.note_from_previous)<=32
    temporal=_verify_transition(previous,all_objects,receipt.fps,receipt.time_ns,
                                gdd,max_speed_mps)
    b=(continuity and unique and unique_cells and correct_partition
       and notes_valid and temporal)
    return a,b


def advance_frame(
    *, frame_index: int, fps: int,
    gdd: GDDSource, objects: tuple[FrameObject,...],
    previous: FrameReceipt | None = None,
    notes: tuple[GDDFrameNote,...] = (),
    chunk_size_m: float = 32.,
    max_speed_mps: float = 500.,
) -> FrameReceipt:
    if type(frame_index) is not int or not 0<=frame_index<=10_000_000:
        raise FrameCoherenceError("bounded monotone frame index required")
    if fps not in (30,50,60,120):
        raise FrameCoherenceError("unsupported presentation frame rate")
    if type(chunk_size_m) not in (int,float) or not math.isfinite(chunk_size_m) or not .1<=chunk_size_m<=1e5:
        raise FrameCoherenceError("chunk size invalid")
    if type(max_speed_mps) not in (int,float) or not 0<max_speed_mps<=1e5:
        raise FrameCoherenceError("bounded velocity envelope required")
    if not 1<=len(objects)<=65536 or len(notes)>32:
        raise FrameCoherenceError("frame object or context budget exceeded")
    groups:dict[tuple[int,int],list[FrameObject]]={}
    for o in objects:
        if not isinstance(o,FrameObject):
            raise FrameCoherenceError("typed object state required")
        groups.setdefault(_cell(o,chunk_size_m),[]).append(o)
    chunks=[]
    for key,items in sorted(groups.items()):
        items=tuple(sorted(items,key=lambda o:o.entity_id))
        partial=FrameChunk(frame_index,key,items,"")
        chunks.append(FrameChunk(frame_index,key,items,digest(partial.payload())))
    t_ns=round(frame_index*1e9/fps)
    candidate=FrameReceipt(
        frame_index,t_ns,fps,gdd.source_digest,
        previous.receipt_digest if previous else None,
        tuple(chunks),notes,True,True,True,"",
    )
    if previous is not None and (
        not previous.verified or not previous.verifier_a_integrity or
        not previous.verifier_b_coherence or
        digest(previous.payload())!=previous.receipt_digest or
        any(digest(c.payload())!=c.content_digest for c in previous.chunks)
    ):
        raise FrameCoherenceError("cannot continue an unverified or corrupted frame")
    # Create the final receipt digest over its complete source payload.
    sealed=FrameReceipt(
        frame_index,t_ns,fps,gdd.source_digest,
        candidate.previous_digest,tuple(chunks),notes,True,True,True,
        digest(candidate.payload()),
    )
    v_a,v_b=verify_frame(sealed,gdd,previous=previous,chunk_size_m=chunk_size_m,
                         max_speed_mps=max_speed_mps)
    if not v_a or not v_b:
        raise FrameCoherenceError(
            "double verification blocked frame advancement: "
            f"content={v_a} temporal_canon={v_b}")
    return sealed


def ai_design_context(gdd: GDDSource, frames: Sequence[FrameReceipt], *,
                      max_notes: int = 32) -> dict:
    """Provenance-limited model prompt context assembled from verified notes.

    This function does not call a model; the existing provider runtime retains
    inference and context authority. AI cannot promote itself into GDD canon.
    """
    if type(max_notes) is not int or not 1<=max_notes<=128:
        raise FrameCoherenceError("context limit invalid")
    if not frames:
        raise FrameCoherenceError("verified frame history required")
    prior=None
    collected=[]
    for receipt in frames:
        a,b=verify_frame(receipt,gdd,previous=prior)
        if not (a and b):
            raise FrameCoherenceError("AI context cannot use corrupted frame history")
        for note in receipt.note_from_previous:
            collected.append({
                "frame":receipt.frame_index,
                "source_world_law_index":note.world_law_index,
                "source_world_law":gdd.world_laws[note.world_law_index],
                "category":note.category,"note":note.text,
                "review_status":note.author_kind,
                "frame_receipt_digest":receipt.receipt_digest,
            })
        prior=receipt
    selected=collected[-max_notes:]
    return {
        "schema":"skeleton.jeeves.frame_gdd_context.v1",
        "project":gdd.project_id,"gdd_digest":gdd.source_digest,
        "final_verified_frame":frames[-1].frame_index,
        "final_frame_digest":frames[-1].receipt_digest,
        "notes":selected,
        "truncated":len(collected)>len(selected),
        "requires_human_canon_approval":True,
        "authority":"proposed_ai_context_not_signed_gdd",
    }


@dataclass(frozen=True)
class FrameContextCursor:
    """Compact, content-addressed AI context carried between verified frames.

    Stores at most 64 notes instead of rescanning a full day/month of frames.
    Native durable owner must persist and revalidate the cursor, never treat
    it as a second authoritative GDD or frame state.
    """
    gdd_digest: str
    last_frame_index: int
    last_receipt_digest: str
    recent_notes: tuple[dict, ...]
    total_note_count: int
    cursor_digest: str

    def payload(self) -> dict:
        return {
            "gdd":self.gdd_digest,"frame":self.last_frame_index,
            "head":self.last_receipt_digest,"notes":list(self.recent_notes),
            "total_notes":self.total_note_count,
        }


def advance_context_cursor(
    gdd: GDDSource,
    frame: FrameReceipt, *,
    previous_frame: FrameReceipt | None = None,
    previous_cursor: FrameContextCursor | None = None,
    max_notes: int = 32,
) -> FrameContextCursor:
    """Incremental O(frame notes) context with independently checked lineage."""
    if type(max_notes) is not int or not 1<=max_notes<=64:
        raise FrameCoherenceError("bounded context budget required")
    if (previous_frame is None) != (previous_cursor is None):
        raise FrameCoherenceError("cursor and previous frame must be paired")
    if previous_cursor:
        if (previous_cursor.gdd_digest!=gdd.source_digest or
            previous_cursor.last_receipt_digest!=previous_frame.receipt_digest or
            previous_cursor.last_frame_index!=previous_frame.frame_index or
            digest(previous_cursor.payload())!=previous_cursor.cursor_digest):
            raise FrameCoherenceError("provenance or checkpoint cursor drift")
        if (digest(previous_frame.payload())!=previous_frame.receipt_digest or
            not previous_frame.verified):
            raise FrameCoherenceError("prior receipt integrity missing")
    a,b=verify_frame(frame,gdd,previous=previous_frame)
    if not a or not b:
        raise FrameCoherenceError("AI cursor may advance only after double verification")
    notes=list(previous_cursor.recent_notes) if previous_cursor else []
    for note in frame.note_from_previous:
        notes.append({
            "frame":frame.frame_index,
            "source_world_law_index":note.world_law_index,
            "source_world_law":gdd.world_laws[note.world_law_index],
            "category":note.category,
            "note":note.text,
            "review_status":note.author_kind,
            "frame_receipt_digest":frame.receipt_digest,
        })
    total=(previous_cursor.total_note_count if previous_cursor else 0) + len(
        frame.note_from_previous)
    cursor=FrameContextCursor(gdd.source_digest,frame.frame_index,
                               frame.receipt_digest,tuple(notes[-max_notes:]),total,"")
    return FrameContextCursor(
        cursor.gdd_digest,cursor.last_frame_index,cursor.last_receipt_digest,
        cursor.recent_notes,cursor.total_note_count,digest(cursor.payload()))


def cursor_ai_context(cursor: FrameContextCursor,gdd: GDDSource) -> dict:
    if (cursor.gdd_digest!=gdd.source_digest or
        digest(cursor.payload())!=cursor.cursor_digest):
        raise FrameCoherenceError("invalid cached signed-GDD context")
    return {
        "schema":"skeleton.jeeves.frame_gdd_context.v1",
        "project":gdd.project_id,"gdd_digest":gdd.source_digest,
        "final_verified_frame":cursor.last_frame_index,
        "final_frame_digest":cursor.last_receipt_digest,
        "notes":list(cursor.recent_notes),
        "truncated":cursor.total_note_count>len(cursor.recent_notes),
        "total_notes":cursor.total_note_count,
        "context_cursor_digest":cursor.cursor_digest,
        "requires_human_canon_approval":True,
        "authority":"proposed_ai_context_not_signed_gdd",
    }
