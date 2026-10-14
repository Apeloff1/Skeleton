"""Video Dragon: source-bound visual notes, indexed inspiration and tool leads.

Accepts authorized *already decoded* frame/annotation observations and
time-coded transcript chunks. Pixel understanding is supplied by a separate
consent-bound decoder; this module does not watch/download a video or invent
visual features. Inspiration is a research candidate, never an approved weight.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from skeleton.ai.game_builder.contracts import canonical_digest
from .video_digest import VideoKnowledgeChunk, VideoObservation,validate_observation
from .dragon_visual_features import VisualFeatureBatch
from .dragon_frame_custody import FrameBatch

HEX=re.compile(r"[0-9a-f]{64}\Z")
TERM=re.compile(r"[a-z0-9-]{2,40}")
TOOL_TERMS=frozenset((
    "editor","shader","engine","compiler","sprite","tilemap",
    "blender","godot","unity","unreal","debugger","profiling",
    "animation","physics","lighting","rigging","vfx","audio",
    "visual","pixel","ui","accessibility","testing","particles"
))

@dataclass(frozen=True)
class VisualBookmark:
    source_id:str
    source_url:str
    start_ms:int
    end_ms:int
    frame_id:str
    frame_digest:str
    visual_feature_fingerprint:str
    clip_digest:str
    note:str
    observed_terms:tuple[str,...]
    inspiring_tool_leads:tuple[str,...]
    reviewer_required:bool=True

def digest_video_inspiration(
    source_id:str, source_url:str, transcript:tuple[VideoKnowledgeChunk,...],
    decoded_visual:VisualFeatureBatch,
    descriptions:tuple[VideoObservation,...],
    source_frames:FrameBatch, *,
    consent_verified:bool,authorized:bool,max_notes:int=128,
)->dict:
    if authorized is not True or consent_verified is not True:
        raise PermissionError("independent visual capture consent required")
    if (type(source_id) is not str or not source_id.startswith("source-")
        or len(source_id)!=71 or not HEX.fullmatch(source_id[7:])
        or type(source_url) is not str or not source_url.startswith("https://")
        or len(source_url)>2048 or type(transcript) is not tuple
        or type(descriptions) is not tuple or not isinstance(source_frames,FrameBatch)
        or type(max_notes) is not int or not 1<=max_notes<=128
        or not 1<=len(descriptions)<=max_notes or len(transcript)>10_000
        or not isinstance(decoded_visual,VisualFeatureBatch)
        or not HEX.fullmatch(decoded_visual.observation_fingerprint)
        or not HEX.fullmatch(decoded_visual.source_batch_fingerprint)):
        raise ValueError("bounded canonical visual evidence required")
    if (decoded_visual.source_batch_fingerprint!=source_frames.batch_fingerprint
        or not 1<=len(source_frames.frames)<=512):
        raise ValueError("visual features not bound to original source frames")
    # Require a normalized secure source URL, not the HTTPS scheme alone.
    from urllib.parse import urlsplit
    parsed=urlsplit(source_url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("canonical video source URL required")
    frame_digests={f.frame_id:f.frame_digest for f in source_frames.frames}
    if (len(frame_digests)!=len(source_frames.frames)
        or any(not HEX.fullmatch(digest) for digest in frame_digests.values())):
        raise ValueError("invalid or duplicated source frame custody")
    feature_frames={f.source_frame_id:f.timestamp_ms for f in decoded_visual.frames}
    if len(feature_frames)!=len(decoded_visual.frames):
        raise ValueError("duplicate visual feature frame identity")
    if any(not isinstance(c,VideoKnowledgeChunk) or
           c.source_url!=source_url for c in transcript):
        raise ValueError("transcript/source identity mismatch")
    chunks=tuple(sorted(transcript,key=lambda c:(c.start_ms,c.end_ms,c.chunk_id)))
    bookmarked=[]
    seen=set()
    for o in descriptions:
        validate_observation(o)
        if o.modality not in ("frame_description","ocr","caption"):
            raise ValueError("visual notes require actual visually attributed observations")
        if (o.source_id not in frame_digests or o.source_id not in feature_frames
            or not o.start_ms<=feature_frames[o.source_id]<o.end_ms):
            raise ValueError("visual description not bound to captured frame")
        digest=frame_digests[o.source_id]
        identity=(o.source_id,o.start_ms,o.end_ms,o.modality)
        if identity in seen:
            raise ValueError("duplicate visual observation")
        seen.add(identity)
        overlaps=[c for c in chunks
                  if c.start_ms < o.end_ms and c.end_ms > o.start_ms]
        if not overlaps:
            raise ValueError("no timecode-aligned authorized video notes")
        # Never transform low-confidence OCR into an asserted fact.
        note=o.text.strip()
        if o.confidence<0.7:
            note="(Unverified visual description; inspection required) "+note
        tokens=set(TERM.findall(note.casefold()))
        tool_tags=tuple(sorted(tokens & TOOL_TERMS))
        candidate=VisualBookmark(
            source_id=source_id,source_url=source_url,
            start_ms=o.start_ms,end_ms=o.end_ms,
            frame_id=o.source_id,frame_digest=digest,
            visual_feature_fingerprint=decoded_visual.observation_fingerprint,
            clip_digest=canonical_digest(
                {"frame":digest,"notes":tuple(c.chunk_id for c in overlaps),
                 "time":(o.start_ms,o.end_ms)}),
            note=note[:400],observed_terms=tuple(sorted(tokens)[:24]),
            inspiring_tool_leads=tool_tags)
        bookmarked.append(candidate)
    bookmarked.sort(key=lambda b:(b.start_ms,b.end_ms,b.frame_id))
    notes=[vars(b) for b in bookmarked]
    body={
        "schema":"skeleton.dragon.visual_inspiration_bookmarks.v1",
        "source_id":source_id,"source_url":source_url,
        "visual_batch_fingerprint":decoded_visual.observation_fingerprint,
        "notes":notes,
        "bookmarked_clips":len(notes),
        "tool_editor_leads":sorted(set(t for b in bookmarked
                                        for t in b.inspiring_tool_leads)),
        "visual_decoder_supplied_not_run_here":True,
        "transcript_alignment_present":True,
        "independent_visual_fact_review_required":True,
        "copyright_and_capture_permission_not_implicitly_granted":True,
        "normal_weight_promotion_authorized":False,
        "hyperweight_promotion_authorized":False,
        "neural_training_authorized":False,
        "network_requests":0,
    }
    return {**body,"bookmark_digest":canonical_digest(body)}
