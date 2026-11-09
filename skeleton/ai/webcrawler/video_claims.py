"""Evidence-backed distilled claims from timed video observations."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .video_digest import VideoKnowledgeChunk

@dataclass(frozen=True)
class VideoClaim:
    claim_id:str
    source_url:str
    start_ms:int
    end_ms:int
    statement:str
    evidence_chunk_id:str
    status:str="unverified"

def propose_video_claims(chunks:tuple[VideoKnowledgeChunk,...],*,max_claims:int=1000)->tuple[VideoClaim,...]:
    """Extract traceable candidate statements, never silently assert their truth."""
    if not 1<=max_claims<=10000:raise ValueError("invalid claim budget")
    claims=[]
    for chunk in chunks:
        if len(claims)>=max_claims:break
        statement=" ".join(chunk.text.split())[:500]
        if not statement:continue
        identity=json.dumps([chunk.chunk_id,statement],separators=(",",":"),ensure_ascii=False)
        claims.append(VideoClaim(sha256(identity.encode()).hexdigest(),chunk.source_url,
                                 chunk.start_ms,chunk.end_ms,statement,chunk.chunk_id))
    return tuple(claims)
