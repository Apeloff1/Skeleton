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
_YEAR = re.compile(r"(?<!\\d)((?:19|20)\\d{2})(?!\\d)")
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
    min_relevance: float = 0.10
    min_source_score: float = 0.25
    def __post_init__(self):
        if not isinstance(self.text,str) or not self.text.strip(): raise ValueError("research query text is required")
        if isinstance(self.required_sources,bool) or not isinstance(self.required_sources,int) or self.required_sources<1: raise ValueError("required_sources must be positive")
        if not math.isfinite(self.freshness_half_life_seconds) or self.freshness_half_life_seconds<=0: raise ValueError("freshness half-life must be finite and positive")
        for name in ("diversity_weight","contradiction_weight","min_relevance","min_source_score"):
            value=getattr(self,name)
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=1: raise ValueError(f"{name} must be finite and between 0 and 1")
        if self.diversity_weight+self.contradiction_weight>1: raise ValueError("research weights exceed score budget")

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
    signal_years: tuple[int, ...] = ()

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
            signal_years=tuple(sorted({int(y) for y in _YEAR.findall(doc.title+" "+excerpt)})),
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

    def qualified(self) -> list[EvidenceObservation]:
        return [o for o in self.observations.values() if o.relevance >= self.query.min_relevance and o.source_score >= self.query.min_source_score]

    @property
    def distinct_hosts(self) -> int:
        return len({x.host for x in self.qualified()})

    def contradictions(self) -> list[Contradiction]:
        out=[]
        vals=self.qualified()
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

    def signals_by_year(self) -> dict[int, Mapping[str, object]]:
        """Aggregate qualified evidence by the years explicitly mentioned in evidence."""
        buckets: dict[int,list[EvidenceObservation]]={}
        for obs in self.qualified():
            for year in obs.signal_years:buckets.setdefault(year,[]).append(obs)
        out={}
        for year,items in sorted(buckets.items()):
            hosts={x.host for x in items}
            positive=sum(1 for x in items if x.polarity>0);negative=len(items)-positive
            out[year]={"observations":len(items),"distinct_hosts":len(hosts),
                       "mean_relevance":sum(x.relevance for x in items)/len(items),
                       "mean_source_score":sum(x.source_score for x in items)/len(items),
                       "positive":positive,"negative":negative}
        return out

    def undercovered_years(self,start_year:int,end_year:int,*,minimum_hosts:int=1) -> tuple[int,...]:
        if start_year>end_year or minimum_hosts<1:raise ValueError("invalid year coverage request")
        signals=self.signals_by_year()
        return tuple(y for y in range(start_year,end_year+1) if int(signals.get(y,{}).get("distinct_hosts",0))<minimum_hosts)

    def signals_by_decade(self) -> dict[int, Mapping[str, object]]:
        from .decade_signals import DecadeSignalSeries
        return DecadeSignalSeries(self.signals_by_year()).aggregate()

    def undercovered_decades(self,start_decade:int,end_decade:int,*,minimum_coverage:float=.5) -> tuple[int,...]:
        from .decade_signals import DecadeSignalSeries
        return DecadeSignalSeries(self.signals_by_year()).undercovered_decades(start_decade,end_decade,minimum_coverage=minimum_coverage)

    def assurance(self, *, now: float) -> Mapping[str, object]:
        ranked=self.ranked(now=now)
        relevant=[o for o in ranked if o.relevance >= self.query.min_relevance and o.source_score >= self.query.min_source_score]
        contradictions=self.contradictions()
        diversity=min(1.0, self.distinct_hosts/max(1,self.query.required_sources))
        mean_rel=sum(o.relevance for o in relevant)/max(1,len(relevant))
        mean_quality=sum(o.source_score for o in relevant)/max(1,len(relevant))
        contradiction_penalty=min(1.0,sum(c.confidence for c in contradictions)/max(1,len(relevant)))
        base_weight=max(0.0,1.0-self.query.diversity_weight)
        score=max(0.0,min(1.0,base_weight*(.55*mean_rel+.45*mean_quality)+self.query.diversity_weight*diversity-self.query.contradiction_weight*contradiction_penalty))
        return {
            "schema":"skeleton.ai.research.assurance.v1",
            "query":self.query.text,
            "score":score,
            "distinct_hosts":self.distinct_hosts,
            "required_sources":self.query.required_sources,
            "contradictions":len(contradictions),
            "sufficient":self.distinct_hosts >= self.query.required_sources and score >= .45,
        }

def frontier_priority(query: str, candidate_url: str, anchor_text: str="", *, same_host: bool=False, target_years: Iterable[int]=(), target_decades: Iterable[int]=()) -> float:
    """Cheap query-directed priority usable before a candidate has been fetched."""
    relevance=lexical_relevance(query, candidate_url.replace("/"," ")+" "+anchor_text)
    exploration=0.0 if same_host else 0.15
    years={int(x) for x in _YEAR.findall(candidate_url+" "+anchor_text)}
    target={int(y) for y in target_years}
    temporal=0.20 if target and years & target else 0.0
    decades={(y//10)*10 for y in years};wanted={int(d) for d in target_decades}
    regime=0.15 if wanted and decades & wanted else 0.0
    return relevance+exploration+temporal+regime
