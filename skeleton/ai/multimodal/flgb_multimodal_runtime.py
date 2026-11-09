"""FLGB-08 deterministic multimodal artifact, grounding, retrieval, and fallback contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Sequence

MAX_ID_CHARS=256
MAX_MEDIA_BYTES=10_000_000_000
MAX_DIMENSION=262_144
MAX_DURATION_MS=7*24*60*60*1000
MAX_SAMPLE_RATE=768_000
MAX_CHANNELS=64
MAX_PAGES=100_000
MAX_FRAMES=1_000_000
MAX_TEXT_CHARS=10_000_000
MAX_CONTEXT_ITEMS=16_384
MAX_SCORE_PPM=1_000_000

class MultimodalContractError(ValueError):
    """Fail-closed FLGB-08 contract error."""

def _is_int(v:Any)->bool: return isinstance(v,int) and not isinstance(v,bool)

def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v):
        raise MultimodalContractError(f"invalid {name}")
    return v

def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise MultimodalContractError(f"invalid {name}")
    return v

def digest_json(v:Any)->str:
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise MultimodalContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ImageArtifact:
    artifact_id:str
    content_digest:str
    mime_type:str
    width:int
    height:int
    byte_size:int
    provenance_digest:str
    rights_digest:str

    def __post_init__(self)->None:
        require_id(self.artifact_id,"artifact_id"); require_digest(self.content_digest,"content_digest"); require_digest(self.provenance_digest,"provenance_digest"); require_digest(self.rights_digest,"rights_digest")
        if self.mime_type not in {"image/png","image/jpeg","image/webp","image/gif","image/avif"}: raise MultimodalContractError("unsupported image MIME type")
        for name in ("width","height"):
            value=getattr(self,name)
            if not _is_int(value) or not 1<=value<=MAX_DIMENSION: raise MultimodalContractError(f"invalid {name}")
        if not _is_int(self.byte_size) or not 1<=self.byte_size<=MAX_MEDIA_BYTES: raise MultimodalContractError("invalid byte_size")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class DocumentPage:
    document_id:str
    page_index:int
    page_image_digest:str
    layout_digest:str
    provenance_digest:str

    def __post_init__(self)->None:
        require_id(self.document_id,"document_id")
        if not _is_int(self.page_index) or not 0<=self.page_index<MAX_PAGES: raise MultimodalContractError("invalid page_index")
        for name in ("page_image_digest","layout_digest","provenance_digest"): require_digest(getattr(self,name),name)

    @property
    def digest(self)->str: return digest_json(self.__dict__)

def validate_document_pages(pages:Sequence[DocumentPage])->tuple[DocumentPage,...]:
    if not pages or len(pages)>MAX_PAGES: raise MultimodalContractError("document page count out of bounds")
    doc_ids={p.document_id for p in pages}
    if len(doc_ids)!=1: raise MultimodalContractError("cross-document page set")
    ordered=tuple(sorted(pages,key=lambda p:p.page_index))
    if [p.page_index for p in ordered]!=list(range(len(ordered))): raise MultimodalContractError("document pages must be contiguous")
    return ordered

@dataclass(frozen=True)
class OCRRequest:
    request_id:str
    image_digest:str
    language_hints:tuple[str,...]
    max_output_chars:int
    untrusted_input:bool=True

    def __post_init__(self)->None:
        require_id(self.request_id,"request_id"); require_digest(self.image_digest,"image_digest")
        hints=tuple(sorted(self.language_hints))
        if len(set(hints))!=len(hints) or len(hints)>64: raise MultimodalContractError("invalid language_hints")
        for hint in hints: require_id(hint,"language_hint")
        object.__setattr__(self,"language_hints",hints)
        if not _is_int(self.max_output_chars) or not 1<=self.max_output_chars<=MAX_TEXT_CHARS: raise MultimodalContractError("invalid max_output_chars")
        if self.untrusted_input is not True: raise MultimodalContractError("OCR input must remain untrusted")

@dataclass(frozen=True)
class OCRReceipt:
    request_id:str
    text_digest:str
    output_chars:int
    engine_digest:str

    def __post_init__(self)->None:
        require_id(self.request_id,"request_id"); require_digest(self.text_digest,"text_digest"); require_digest(self.engine_digest,"engine_digest")
        if not _is_int(self.output_chars) or not 0<=self.output_chars<=MAX_TEXT_CHARS: raise MultimodalContractError("invalid OCR output_chars")

@dataclass(frozen=True)
class SpeechArtifact:
    artifact_id:str
    content_digest:str
    mime_type:str
    duration_ms:int
    sample_rate_hz:int
    channels:int
    provenance_digest:str
    consent_digest:str

    def __post_init__(self)->None:
        require_id(self.artifact_id,"artifact_id"); require_digest(self.content_digest,"content_digest"); require_digest(self.provenance_digest,"provenance_digest"); require_digest(self.consent_digest,"consent_digest")
        if self.mime_type not in {"audio/wav","audio/mpeg","audio/ogg","audio/flac","audio/mp4"}: raise MultimodalContractError("unsupported audio MIME type")
        if not _is_int(self.duration_ms) or not 1<=self.duration_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid duration_ms")
        if not _is_int(self.sample_rate_hz) or not 1<=self.sample_rate_hz<=MAX_SAMPLE_RATE: raise MultimodalContractError("invalid sample_rate_hz")
        if not _is_int(self.channels) or not 1<=self.channels<=MAX_CHANNELS: raise MultimodalContractError("invalid channels")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class SpeechSynthesisRequest:
    request_id:str
    text_digest:str
    voice_id:str
    voice_rights_digest:str
    output_format:str
    max_duration_ms:int

    def __post_init__(self)->None:
        require_id(self.request_id,"request_id"); require_digest(self.text_digest,"text_digest"); require_id(self.voice_id,"voice_id"); require_digest(self.voice_rights_digest,"voice_rights_digest")
        if self.output_format not in {"wav","mp3","ogg","flac"}: raise MultimodalContractError("invalid synthesis format")
        if not _is_int(self.max_duration_ms) or not 1<=self.max_duration_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid max_duration_ms")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

@dataclass(frozen=True)
class AudioSegment:
    segment_id:str
    start_ms:int
    end_ms:int
    label:str
    score_ppm:int
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.segment_id,"segment_id"); require_id(self.label,"label"); require_digest(self.evidence_digest,"evidence_digest")
        if not _is_int(self.start_ms) or not _is_int(self.end_ms) or not 0<=self.start_ms<self.end_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid audio segment range")
        if not _is_int(self.score_ppm) or not 0<=self.score_ppm<=MAX_SCORE_PPM: raise MultimodalContractError("invalid score_ppm")

def validate_audio_segments(segments:Sequence[AudioSegment],duration_ms:int)->tuple[AudioSegment,...]:
    if not _is_int(duration_ms) or not 1<=duration_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid duration_ms")
    ids=[s.segment_id for s in segments]
    if len(set(ids))!=len(ids): raise MultimodalContractError("duplicate audio segment")
    if any(s.end_ms>duration_ms for s in segments): raise MultimodalContractError("audio segment exceeds artifact duration")
    return tuple(sorted(segments,key=lambda s:(s.start_ms,s.end_ms,s.segment_id)))

@dataclass(frozen=True)
class VideoArtifact:
    artifact_id:str
    content_digest:str
    duration_ms:int
    frame_count:int
    provenance_digest:str
    rights_digest:str

    def __post_init__(self)->None:
        require_id(self.artifact_id,"artifact_id"); require_digest(self.content_digest,"content_digest"); require_digest(self.provenance_digest,"provenance_digest"); require_digest(self.rights_digest,"rights_digest")
        if not _is_int(self.duration_ms) or not 1<=self.duration_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid video duration")
        if not _is_int(self.frame_count) or not 1<=self.frame_count<=MAX_FRAMES: raise MultimodalContractError("invalid frame_count")

def sample_video(video:VideoArtifact,max_frames:int)->tuple[int,...]:
    if not _is_int(max_frames) or not 1<=max_frames<=MAX_FRAMES: raise MultimodalContractError("invalid max_frames")
    count=min(video.frame_count,max_frames)
    if count==1: return (0,)
    return tuple((i*(video.frame_count-1))//(count-1) for i in range(count))

@dataclass(frozen=True)
class TemporalGrounding:
    grounding_id:str
    artifact_digest:str
    start_ms:int
    end_ms:int
    claim_digest:str
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.grounding_id,"grounding_id"); require_digest(self.artifact_digest,"artifact_digest"); require_digest(self.claim_digest,"claim_digest"); require_digest(self.evidence_digest,"evidence_digest")
        if not _is_int(self.start_ms) or not _is_int(self.end_ms) or not 0<=self.start_ms<self.end_ms<=MAX_DURATION_MS: raise MultimodalContractError("invalid grounding range")

@dataclass(frozen=True)
class CrossModalCandidate:
    candidate_id:str
    modality:str
    artifact_digest:str
    provenance_digest:str
    semantic_ppm:int
    temporal_ppm:int=MAX_SCORE_PPM

    def __post_init__(self)->None:
        require_id(self.candidate_id,"candidate_id")
        if self.modality not in {"text","image","document","audio","video"}: raise MultimodalContractError("invalid modality")
        require_digest(self.artifact_digest,"artifact_digest"); require_digest(self.provenance_digest,"provenance_digest")
        for name in ("semantic_ppm","temporal_ppm"):
            v=getattr(self,name)
            if not _is_int(v) or not 0<=v<=MAX_SCORE_PPM: raise MultimodalContractError(f"invalid {name}")

def rank_cross_modal(candidates:Sequence[CrossModalCandidate],limit:int=20)->tuple[CrossModalCandidate,...]:
    if not _is_int(limit) or not 1<=limit<=10000: raise MultimodalContractError("invalid retrieval limit")
    ids=[c.candidate_id for c in candidates]
    if len(set(ids))!=len(ids): raise MultimodalContractError("duplicate cross-modal candidate")
    return tuple(sorted(candidates,key=lambda c:(-(c.semantic_ppm*3+c.temporal_ppm),c.candidate_id))[:limit])

@dataclass(frozen=True)
class MultimodalContextItem:
    item_id:str
    modality:str
    artifact_digest:str
    token_cost:int
    byte_cost:int
    priority:int=0
    mandatory:bool=False

    def __post_init__(self)->None:
        require_id(self.item_id,"item_id")
        if self.modality not in {"text","image","document","audio","video"}: raise MultimodalContractError("invalid context modality")
        require_digest(self.artifact_digest,"artifact_digest")
        if not _is_int(self.token_cost) or self.token_cost<0: raise MultimodalContractError("invalid token_cost")
        if not _is_int(self.byte_cost) or not 0<=self.byte_cost<=MAX_MEDIA_BYTES: raise MultimodalContractError("invalid byte_cost")
        if not _is_int(self.priority): raise MultimodalContractError("invalid priority")
        if not isinstance(self.mandatory,bool): raise MultimodalContractError("mandatory must be boolean")

def compile_multimodal_context(items:Sequence[MultimodalContextItem],token_budget:int,byte_budget:int)->tuple[str,...]:
    if len(items)>MAX_CONTEXT_ITEMS: raise MultimodalContractError("context item budget exceeded")
    if not _is_int(token_budget) or token_budget<0 or not _is_int(byte_budget) or byte_budget<0: raise MultimodalContractError("invalid context budgets")
    ids=[i.item_id for i in items]
    if len(set(ids))!=len(ids): raise MultimodalContractError("duplicate context item")
    required=sorted((i for i in items if i.mandatory),key=lambda i:(-i.priority,i.item_id))
    used_tokens=sum(i.token_cost for i in required); used_bytes=sum(i.byte_cost for i in required)
    if used_tokens>token_budget or used_bytes>byte_budget: raise MultimodalContractError("mandatory multimodal context exceeds budget")
    selected=list(required)
    for item in sorted((i for i in items if not i.mandatory),key=lambda i:(-i.priority,i.token_cost,i.byte_cost,i.item_id)):
        if used_tokens+item.token_cost<=token_budget and used_bytes+item.byte_cost<=byte_budget:
            selected.append(item); used_tokens+=item.token_cost; used_bytes+=item.byte_cost
    return tuple(i.item_id for i in selected)

@dataclass(frozen=True)
class ArtifactAlignment:
    alignment_id:str
    left_artifact_digest:str
    right_artifact_digest:str
    relation:str
    score_ppm:int
    evidence_digest:str

    def __post_init__(self)->None:
        require_id(self.alignment_id,"alignment_id"); require_digest(self.left_artifact_digest,"left_artifact_digest"); require_digest(self.right_artifact_digest,"right_artifact_digest"); require_digest(self.evidence_digest,"evidence_digest")
        if self.left_artifact_digest==self.right_artifact_digest: raise MultimodalContractError("alignment requires distinct artifacts")
        if self.relation not in {"same-event","derived-from","describes","transcript-of","frame-of","supports"}: raise MultimodalContractError("invalid alignment relation")
        if not _is_int(self.score_ppm) or not 0<=self.score_ppm<=MAX_SCORE_PPM: raise MultimodalContractError("invalid alignment score")

@dataclass(frozen=True)
class FallbackOption:
    modality:str
    capability:str
    available:bool
    quality_ppm:int

    def __post_init__(self)->None:
        if self.modality not in {"text","image","document","audio","video"}: raise MultimodalContractError("invalid fallback modality")
        require_id(self.capability,"capability")
        if not isinstance(self.available,bool): raise MultimodalContractError("available must be boolean")
        if not _is_int(self.quality_ppm) or not 0<=self.quality_ppm<=MAX_SCORE_PPM: raise MultimodalContractError("invalid fallback quality")

def choose_fallback(options:Sequence[FallbackOption],allowed_capabilities:Sequence[str])->FallbackOption:
    allowed=set(allowed_capabilities)
    if len(allowed)!=len(tuple(allowed_capabilities)): raise MultimodalContractError("duplicate allowed capability")
    for cap in allowed: require_id(cap,"allowed_capability")
    eligible=[o for o in options if o.available and o.capability in allowed]
    if not eligible: raise MultimodalContractError("no authorized modality fallback")
    return sorted(eligible,key=lambda o:(-o.quality_ppm,o.modality,o.capability))[0]
