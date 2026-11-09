"""Deterministic idle discovery ranking; discovery is not permission to crawl."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math
from .dragon_video_history import VideoVisit,canonical_video_url

@dataclass(frozen=True)
class VideoCandidate:
    url:str
    title:str
    tags:tuple[str,...]
    provider:str
    published_at:float|None=None

@dataclass(frozen=True)
class VideoProposal:
    proposal_id:str
    url:str
    title:str
    reason:str
    score:float
    shared_tags:tuple[str,...]
    requires_approval:bool=True

def rank_similar_videos(history:tuple[VideoVisit,...],candidates:tuple[VideoCandidate,...],*,
                        max_results:int=20,max_history:int=100)->tuple[VideoProposal,...]:
    if not 1<=max_results<=100 or not 1<=max_history<=500:raise ValueError('invalid discovery budget')
    watched={v.canonical_url for v in history}
    interests:dict[str,float]={}
    for rank,visit in enumerate(history[:max_history]):
        completion=visit.watched_ms/max(1,visit.duration_ms)
        weight=(.5+.5*min(1,completion))/(1+rank*.12)
        for tag in visit.tags:interests[tag]=interests.get(tag,0)+weight
    ranked=[]
    seen=set()
    for candidate in candidates[:1000]:
        try:url=canonical_video_url(candidate.url)
        except (ValueError,TypeError):continue
        if url in watched or url in seen or not candidate.title.strip() or len(candidate.title)>300:continue
        seen.add(url)
        shared=tuple(sorted(set(t.casefold().strip() for t in candidate.tags)&interests.keys()))
        if not shared:continue
        score=sum(interests[t] for t in shared)/(1+len(candidate.tags)*.05)
        if not math.isfinite(score) or score<=0:continue
        ranked.append(VideoProposal(sha256(url.encode()).hexdigest(),url,candidate.title,
            'Similar to watched topics: '+', '.join(shared[:5]),round(score,6),shared))
    ranked.sort(key=lambda p:(-p.score,p.url))
    return tuple(ranked[:max_results])
