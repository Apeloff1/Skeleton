"""Evidence-aware research layer over the policy-bound crawler.

Turns fetched documents into temporal observations and query-directed evidence rather
than treating the crawl corpus as an undifferentiated bag of pages.
"""
from __future__ import annotations
import hashlib, math, re
from dataclasses import dataclass, field
from typing import Iterable, Mapping
from urllib.parse import urlsplit
from .core import CrawlDocument

_WORD = re.compile(r"[a-z0-9]{2,}", re.I)
_NEG = re.compile(r"\b(?:not|never|no|false|denies?|rejects?|without)\b", re.I)

def tokens(text: str) -> frozenset[str]:
    return frozenset(x.lower() for x in _WORD.findall(text))

def lexical_relevance(query: str, text: str) -> float:
    q=tokens(query)
    if not q: return 0.0
    d=tokens(text)
    return len(q & d) / len(q)

@dataclass(frozen=True)
class ResearchQuery:
    text: str
    required_sources: int = 2
    freshness_half_life_seconds: float = 7 * 86400.0
    diversity_weight: float = 0.25
    contradiction_weight: float = 0.20

@dataclass(frozen=True)
class EvidenceObservation:
    observation_id: str
    content_hash: str
    canonical_url: str
    host: str
    fetched_at: float
    title: str
    excerpt: str
    relevance: float
    source_score: float
    polarity: int

    @classmethod
    def from_document(cls, doc: CrawlDocument, query: str) -> "EvidenceObservation":
        excerpt = doc.text[:2000]
        oid = hashlib.sha256(
            f"{doc.content_hash}\0{query.lower()}".encode()
        ).hexdigest()
        return cls(
            observation_id=oid,
            content_hash=doc.content_hash,
            canonical_url=doc.canonical_url,
            host=(urlsplit(doc.canonical_url).hostname or "").lower(),
            fetched_at=doc.fetched_at,
            title=doc.title,
            excerpt=excerpt,
            relevance=lexical_relevance(query, doc.title+" "+excerpt),
            source_score=doc.source_score,
            polarity=-1 if _NEG.search(excerpt) else 1,
        )

@dataclass(frozen=True)
class Contradiction:
    left_id: str
    right_id: str
    reason: str
    confidence: float

@dataclass
class EvidenceSet:
    query: ResearchQuery
    observations: dict[str, EvidenceObservation] = field(default_factory=dict)

    def add(self, doc: CrawlDocument) -> EvidenceObservation:
        obs=EvidenceObservation.from_document(doc, self.query.text)
        self.observations[obs.observation_id]=obs
        return obs

    @property
    def distinct_hosts(self) -> int:
        return len({x.host for x in self.observations.values()})

    def contradictions(self) -> list[Contradiction]:
        out=[]
        vals=list(self.observations.values())
        q=tokens(self.query.text)
        for i,a in enumerate(vals):
            for b in vals[i+1:]:
                if a.host == b.host or a.polarity == b.polarity:
                    continue
                overlap=tokens(a.excerpt) & tokens(b.excerpt)
                denom=max(1,len(q))
                confidence=min(1.0, len(overlap & q)/denom)
                if confidence >= 0.25:
                    out.append(Contradiction(
                        a.observation_id,b.observation_id,
                        "independent sources use opposing polarity around query terms",
                        confidence,
                    ))
        return out

    def ranked(self, *, now: float) -> list[EvidenceObservation]:
        seen_hosts:set[str]=set()
        def score(o: EvidenceObservation) -> float:
            age=max(0.0, now-o.fetched_at)
            fresh=math.pow(0.5, age/max(1.0,self.query.freshness_half_life_seconds))
            diversity=1.0 if o.host not in seen_hosts else 0.0
            return .45*o.relevance + .35*o.source_score + .15*fresh + .05*diversity
        # Host diversity is made deterministic by first selecting each host's strongest item.
        by_host={}
        for o in self.observations.values():
            old=by_host.get(o.host)
            if old is None or (o.relevance,o.source_score,o.canonical_url) > (old.relevance,old.source_score,old.canonical_url):
                by_host[o.host]=o
        leaders=sorted(by_host.values(), key=lambda o:(-score(o),o.canonical_url))
        leader_ids={o.observation_id for o in leaders}
        rest=sorted((o for o in self.observations.values() if o.observation_id not in leader_ids),
                    key=lambda o:(-score(o),o.canonical_url))
        return leaders+rest

    def assurance(self, *, now: float) -> Mapping[str, object]:
        ranked=self.ranked(now=now)
        relevant=[o for o in ranked if o.relevance > 0]
        contradictions=self.contradictions()
        diversity=min(1.0, self.distinct_hosts/max(1,self.query.required_sources))
        mean_rel=sum(o.relevance for o in relevant)/max(1,len(relevant))
        mean_quality=sum(o.source_score for o in relevant)/max(1,len(relevant))
        contradiction_penalty=min(1.0,sum(c.confidence for c in contradictions)/max(1,len(relevant)))
        score=max(0.0,min(1.0,.4*mean_rel+.35*mean_quality+.25*diversity-.2*contradiction_penalty))
        return {
            "schema":"skeleton.ai.research.assurance.v1",
            "query":self.query.text,
            "score":score,
            "distinct_hosts":self.distinct_hosts,
            "required_sources":self.query.required_sources,
            "contradictions":len(contradictions),
            "sufficient":self.distinct_hosts >= self.query.required_sources and score >= .45,
        }

def frontier_priority(query: str, candidate_url: str, anchor_text: str="", *, same_host: bool=False) -> float:
    """Cheap query-directed priority usable before a candidate has been fetched."""
    relevance=lexical_relevance(query, candidate_url.replace("/"," ")+" "+anchor_text)
    exploration=0.0 if same_host else 0.15
    return relevance+exploration
