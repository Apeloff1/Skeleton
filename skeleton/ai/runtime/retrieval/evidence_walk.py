"""Bounded, evidence-derived multi-hop retrieval with explicit abstention.

Only original verified source excerpts are candidates. Expansion uses
literal bounded terms from those excerpts, never generated instructions,
model-authored entities, network fetches or authority changes.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from dataclasses import asdict,dataclass
import hashlib
import math
import re
import time

from .learned_embeddings import _digest
from .semantic_long_context import terms

_STOP=frozenset("the a an and or to for from by is are be was were as at in on "
    "not no of that this these those it its their they them we you your "
    "what which who where when why how can could would should may might "
    "with without into using use used also only than then there about "
    "have has had all more most some such other any".split())
_IDENTIFIER=re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_.:][A-Za-z0-9]+)+|[A-Za-z]+[0-9]+")
_SPLIT=re.compile(r"\b(?:and also|as well as|and|versus|compared with|compared to)\b|[?;]+",re.I)


@dataclass(frozen=True,slots=True)
class EvidenceWalkPolicy:
    max_queries:int=6
    max_hops:int=2
    candidates_per_query:int=6
    max_evidence:int=3
    max_candidate_chars:int=600
    max_query_bytes:int=1024
    max_expansion_terms:int=2
    timeout_seconds:int=30
    min_bridge_length:int=5

    def __post_init__(self):
        for v,lo,hi in ((self.max_queries,1,12),(self.max_hops,0,3),(self.candidates_per_query,1,12),
            (self.max_evidence,1,3),(self.max_candidate_chars,32,600),(self.max_query_bytes,128,4096),
            (self.max_expansion_terms,1,4),(self.timeout_seconds,1,120),(self.min_bridge_length,3,32)):
            if type(v) is not int or not lo<=v<=hi:raise ValueError("invalid multi-hop retrieval budget")

    @property
    def digest(self):return _digest(asdict(self))


def _terms(text):
    return set(w for w in terms(text) if w not in _STOP and 2<=len(w)<=96)


def _source(hit):
    keys={"document_id","document_sha256","chunk_index","char_start","char_end","passage","citation","score","title"}
    if not isinstance(hit,dict) or set(hit)!=keys:
        raise ValueError("multi-hop requires canonical verified knowledge hit")
    if any(not isinstance(hit[k],str) or not hit[k] for k in ("document_id","document_sha256","passage","citation","title")):
        raise ValueError("invalid evidence identity")
    if not re.fullmatch(r"[0-9a-f]{64}",hit["document_sha256"]) or any(type(hit[k]) is not int for k in ("chunk_index","char_start","char_end")):
        raise ValueError("invalid evidence provenance")
    if hit["char_start"]<0 or hit["chunk_index"]<0 or hit["char_end"]-hit["char_start"]!=len(hit["passage"]):
        raise ValueError("evidence offset mismatch")
    if hit["citation"]!=f"local:{hit['document_id']}:{hit['chunk_index']}:{hit['document_sha256'][:16]}":
        raise ValueError("canonical evidence citation mismatch")
    if type(hit["score"]) not in {float,int} or not math.isfinite(hit["score"]):
        raise ValueError("invalid retrieval score")
    return (hit["document_id"],hit["document_sha256"],hit["chunk_index"])


def _facets(question):
    complete=_terms(question)
    items=[]
    for part in _SPLIT.split(question):
        part=part.strip()
        vocabulary=_terms(part)
        if len(vocabulary)>=2 and vocabulary!=complete and vocabulary not in [v for _,v in items]:
            items.append((part,vocabulary))
    return items[:3]


def walk(question,search,*,policy=EvidenceWalkPolicy(),dimension=None,embed=None,interrupt=None):
    """Retrieve root, independent clause facets and at most N exact bridge queries.

    The supplied search callable is the existing source-authorized retrieval
    owner (same scope on every call). Embedding is optional local scoring,
    not a model's assertion of entailment. Reports cite only original hits.
    """
    if not isinstance(policy,EvidenceWalkPolicy) or not callable(search) or not isinstance(question,str) or not question.strip() or len(question.encode())>policy.max_query_bytes:
        raise ValueError("bounded explicit multi-hop question required")
    if embed is not None and (not callable(embed) or type(dimension) is not int or not 2<=dimension<=4096):
        raise ValueError("explicit local query embedding geometry required")
    deadline=time.monotonic()+policy.timeout_seconds
    def check():
        if interrupt:interrupt()
        if time.monotonic()>=deadline:raise TimeoutError("multi-hop evidence deadline exhausted")
    qterms=_terms(question)
    facets=_facets(question)
    all_hits={}
    rank_mass=defaultdict(float)
    reached=defaultdict(set)
    trace=[]
    issued=set()
    pending=[(question,0,None,None)]
    for i,(facet,_) in enumerate(facets):
        pending.append((facet,0,None,i))
    while pending and len(trace)<policy.max_queries:
        check()
        query,hop,parent,facet=pending.pop(0)
        query_key=hashlib.sha256(query.encode()).hexdigest()
        if query_key in issued:continue
        issued.add(query_key)
        result=search(query,policy.candidates_per_query)
        if not isinstance(result,(list,tuple)) or len(result)>policy.candidates_per_query:
            raise ValueError("retrieval owner returned invalid candidate batch")
        keys=[]
        for pos,hit in enumerate(result,1):
            check()
            key=_source(hit)
            if len(hit["passage"])>policy.max_candidate_chars:raise ValueError("multi-hop candidate passage too large")
            if key in all_hits and all_hits[key]["citation"]!=hit["citation"]:
                raise ValueError("multi-hop source identity collision")
            if key not in all_hits or hit["score"]>all_hits[key]["score"]:
                all_hits[key]=dict(hit)
            if key in keys:continue
            keys.append(key)
            rank_mass[key]+=1/(12+pos)/(1+.35*hop)
            if facet is not None:reached[key].add(facet)
        trace.append({"query_sha256":query_key,"hop":hop,"parent_citation":parent,
                      "facet":facet,"citations":[all_hits[k]["citation"] for k in keys]})
        if hop>=policy.max_hops or len(trace)+len(pending)>=policy.max_queries:continue
        # Choose rare literal bridge terms across verified current passages.
        # Never include whole retrieved paragraphs, imperative text or URLs.
        counts=Counter(word for key in keys for word in _terms(all_hits[key]["passage"]))
        expansions=[]
        for key in keys[:3]:
            text=all_hits[key]["passage"]
            identifiers={x.casefold() for x in _IDENTIFIER.findall(text)}
            candidates=[w for w in _terms(text)-qterms if len(w)>=policy.min_bridge_length or w in identifiers]
            candidates.sort(key=lambda w:(w not in identifiers,counts[w],-len(w),w))
            for word in candidates[:policy.max_expansion_terms]:
                # Keep the original user intent in every expansion.
                expanded=question.strip()+" "+word
                if len(expanded.encode())<=policy.max_query_bytes:
                    expansions.append((expanded,hop+1,all_hits[key]["citation"],None))
        for item in expansions:
            if len(trace)+len(pending)>=policy.max_queries:break
            if hashlib.sha256(item[0].encode()).hexdigest() not in issued:
                pending.append(item)
    if not all_hits:
        return [],{"schema":"skeleton.evidence-walk.v1","status":"no_evidence","queries":trace,"semantic_entailment_verified":False}
    check()
    semantic={}
    facet_vectors=[]
    if embed is not None:
        import numpy as np
        def unit(text):
            check()
            x=np.asarray(embed(text),dtype=np.float32)
            if x.shape!=(dimension,) or not np.isfinite(x).all() or abs(float(np.linalg.norm(x))-1)>.002:
                raise ValueError("invalid local evidence ranking vector")
            return x
        query_vector=unit(question)
        facet_vectors=[unit(part) for part,_ in facets]
        for key,hit in all_hits.items():
            vector=unit(hit["passage"])
            semantic[key]=float(np.clip(vector@query_vector,-1,1))
            # Rank-only signal. It is deliberately not a support certificate.
            for i,fv in enumerate(facet_vectors):
                if float(vector@fv)>=.55:reached[key].add(i)
    selected=[]
    covered=set()
    used_words=set()
    scale=max(rank_mass.values())
    remaining=set(all_hits)
    while remaining and len(selected)<policy.max_evidence:
        check()
        def score(key):
            hit=all_hits[key]
            words=_terms(hit["passage"])
            overlap=len(words&used_words)/max(1,len(words|used_words))
            novelty=len(reached[key]-covered)
            exact=len(qterms&words)/max(1,len(qterms))
            relevance=(semantic[key]+1)/2 if key in semantic else exact
            distinct=not any(key[0]==other[0] for other in selected)
            # Rank fusion + facet coverage + source diversity.
            return (.4*rank_mass[key]/scale+.35*relevance+.15*exact+
                    .12*novelty+.04*distinct-.16*overlap,hit["citation"])
        best=max(remaining,key=score)
        selected.append(best);remaining.remove(best)
        covered.update(reached[best]);used_words.update(_terms(all_hits[best]["passage"]))
    hits=[all_hits[k] for k in selected]
    receipt={"schema":"skeleton.evidence-walk.v1","policy_sha256":policy.digest,
             "question_sha256":hashlib.sha256(question.encode()).hexdigest(),"queries":trace,
             "candidate_count":len(all_hits),"selected_citations":[h["citation"] for h in hits],
             "facet_count":len(facets),"retrieval_facets_reached":len(covered),
             "budget_exhausted":bool(pending),"semantic_entailment_verified":False,
             "status":"retrieval_only"}
    receipt["receipt_sha256"]=_digest(receipt)
    return hits,receipt
