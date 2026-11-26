"""Bounded hybrid contextual retrieval over already-authorized immutable spans.

Learned dense retrieval + BM25 + hierarchical parent centroids + late
interaction + diversity/adjacency. Parent vectors are navigation hints only;
only original exact leaf text is eligible for downstream evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import re
import unicodedata

from .learned_embeddings import LocalContextEncoder, LocalPairReranker, SpanEmbedding, _digest

_WORD=re.compile(r"[^\W_]+(?:[-_.:][^\W_]+)*",re.UNICODE)


def terms(text):
    return tuple(_WORD.findall(unicodedata.normalize("NFKC",text).casefold()))


@dataclass(frozen=True,slots=True)
class SemanticPolicy:
    max_spans:int=8192
    max_source_chars:int=16_000_000
    max_encode_calls:int=4096
    max_vector_bytes:int=256*1024**2
    context_chars:int=2000
    segments:int=4
    candidate_pool:int=64
    parent_width:int=8
    min_cosine:float=0.25
    diversity:float=0.18
    neighbor_boost:float=0.035

    def __post_init__(self):
        for v,lo,hi in ((self.max_spans,1,100000),(self.max_source_chars,64,128_000_000),
                        (self.max_encode_calls,1,100000),(self.max_vector_bytes,1024,2**31),
                        (self.context_chars,64,32768),(self.segments,1,16),
                        (self.candidate_pool,4,256),(self.parent_width,2,64)):
            if type(v) is not int or not lo<=v<=hi:
                raise ValueError("semantic retrieval resource policy outside bounds")
        for n,lo,hi in ((self.min_cosine,-1,1),(self.diversity,0,1),(self.neighbor_boost,0,0.2)):
            if type(n) not in {int,float} or not math.isfinite(n) or not lo<=n<=hi:
                raise ValueError("invalid semantic ranking policy")

    @property
    def digest(self):return _digest(asdict(self))


@dataclass(frozen=True,slots=True)
class SemanticSpan:
    source_id:str
    revision:str
    ordinal:int
    start:int
    end:int
    text:str
    context:str
    local_start:int
    local_end:int

    def __post_init__(self):
        if not isinstance(self.source_id,str) or not 1<=len(self.source_id)<=256:
            raise ValueError("semantic span source identity required")
        if not isinstance(self.revision,str) or not re.fullmatch(r"[0-9a-f]{64}",self.revision):
            raise ValueError("semantic span revision pin required")
        if any(type(x) is not int for x in (self.ordinal,self.start,self.end,self.local_start,self.local_end)):
            raise ValueError("invalid semantic span coordinates")
        if self.ordinal<0 or not 0<=self.start<self.end or not isinstance(self.text,str) or not self.text.strip():
            raise ValueError("invalid semantic leaf span")
        if not isinstance(self.context,str) or not 0<=self.local_start<self.local_end<=len(self.context) or self.context[self.local_start:self.local_end]!=self.text:
            raise ValueError("semantic context does not preserve exact leaf")

    @property
    def identity(self):
        return _digest([self.source_id,self.revision,self.ordinal,self.start,self.end,
            sha256(self.text.encode()).hexdigest(),sha256(self.context.encode()).hexdigest(),
            self.local_start,self.local_end])


def document_spans(source_id,revision,source,rows,policy):
    """Group leaves into shared context blocks with deterministic neighbor halos."""
    if not isinstance(source,str) or sha256(source.encode()).hexdigest()!=revision:
        raise ValueError("semantic document source hash mismatch")
    if not isinstance(policy,SemanticPolicy) or len(source)>policy.max_source_chars:
        raise ValueError("semantic source character ceiling exceeded")
    previous=-1
    grouping=max(1,policy.context_chars//2)
    for ordinal,start,end,text in rows:
        if type(ordinal) is not int or ordinal<=previous or not 0<=start<end<=len(source) or source[start:end]!=text:
            raise ValueError("semantic document leaf provenance mismatch")
        previous=ordinal
        if not text.strip():
            continue
        if end-start>policy.context_chars:
            raise ValueError("semantic leaf exceeds contextual encoder window")
        anchor=(start//grouping)*grouping
        left=max(0,anchor-grouping//2)
        right=min(len(source),left+policy.context_chars)
        if end>right:
            left=max(0,end-policy.context_chars)
            right=end
        yield SemanticSpan(source_id,revision,ordinal,start,end,text,source[left:right],start-left,end-left)


def _as_embedding(raw,dimension,segments):
    import numpy as np
    if not isinstance(raw,SpanEmbedding) or len(raw.dense)!=dimension or not 1<=len(raw.segments)<=segments or any(len(x)!=dimension for x in raw.segments):
        raise ValueError("semantic vector geometry mismatch")
    dense=np.asarray(raw.dense,dtype=np.float32)
    multi=np.asarray(raw.segments,dtype=np.float32)
    if not np.isfinite(dense).all() or not np.isfinite(multi).all() or abs(float(np.linalg.norm(dense))-1)>0.001 or np.any(np.abs(np.linalg.norm(multi,axis=1)-1)>0.001):
        raise ValueError("semantic vectors must be finite normalized features")
    return dense,multi


@dataclass(frozen=True,slots=True)
class PreparedSemanticQuery:
    """Request-local learned features; never accepted from public request JSON."""
    query_sha256:str
    feature_space:str
    embedding:SpanEmbedding
    issuer:object


class ContextualRanker:
    def __init__(self,encoder:LocalContextEncoder,policy:SemanticPolicy=SemanticPolicy(),*,reranker=None):
        if not isinstance(encoder,LocalContextEncoder) or not isinstance(policy,SemanticPolicy):
            raise TypeError("pinned learned encoder and retrieval policy required")
        if reranker is not None and not isinstance(reranker,LocalPairReranker):
            raise TypeError("explicit local pinned cross-encoder required")
        self.encoder,self.policy,self.reranker=encoder,policy,reranker
        self._query_issuer=object()

    @property
    def identity(self):
        return _digest([self.encoder.identity,self.policy.digest,"skeleton.hybrid-context.v1",self.reranker.identity if self.reranker else None])

    def prepare_query(self,query,*,interrupt=None):
        if not isinstance(query,str) or not query.strip() or len(query.encode())>16384:
            raise ValueError("bounded semantic query required")
        if interrupt:interrupt()
        vector=self.encoder.query(query,segments=16)
        _as_embedding(vector,self.encoder.policy.dimension,16)
        if interrupt:interrupt()
        return PreparedSemanticQuery(sha256(query.encode()).hexdigest(),self.identity,vector,self._query_issuer)

    def _prepared(self,query,prepared,interrupt=None):
        if prepared is None:
            prepared=self.prepare_query(query,interrupt=interrupt)
        if (not isinstance(prepared,PreparedSemanticQuery) or prepared.issuer is not self._query_issuer
                or prepared.feature_space!=self.identity or prepared.query_sha256!=sha256(query.encode()).hexdigest()):
            raise ValueError("prepared semantic query identity mismatch")
        return _as_embedding(prepared.embedding,self.encoder.policy.dimension,16)

    def _features(self,spans,cache,interrupt):
        p=self.policy
        dim=self.encoder.policy.dimension
        expected=len(spans)*(1+p.segments)*dim*4
        if expected>p.max_vector_bytes:
            raise MemoryError("semantic vector matrix exceeds logical budget")
        output={}
        groups=defaultdict(list)
        for span in spans:
            if interrupt:
                interrupt()
            key=span.identity
            found=cache.get(self.identity,key) if cache is not None else None
            if found is not None:
                _as_embedding(found,dim,p.segments)
                output[key]=found
            else:
                groups[span.context].append(span)
        calls=0
        for context,rows in groups.items():
            for start in range(0,len(rows),256):
                if interrupt:
                    interrupt()
                group=rows[start:start+256]
                calls+=1
                if calls>p.max_encode_calls:
                    raise ValueError("semantic contextual encoding call budget exhausted")
                try:
                    vectors=self.encoder.spans(context,[(x.local_start,x.local_end) for x in group],segments=p.segments)
                except ValueError as exc:
                    # Encoder geometry is explicit: never silently truncate,
                    # switch models or turn failed contextual vectors into hashes.
                    raise ValueError("contextual encoding failed within admitted window") from exc
                if len(vectors)!=len(group):
                    raise RuntimeError("contextual encoder output count mismatch")
                for row,vector in zip(group,vectors):
                    _as_embedding(vector,dim,p.segments)
                    output[row.identity]=vector
                    if cache is not None:
                        cache.put(self.identity,row.identity,vector)
        return output,calls

    def search(self,query,spans,*,limit=8,cache=None,prepared=None,interrupt=None):
        import numpy as np
        p=self.policy
        if not isinstance(query,str) or not query.strip() or len(query.encode())>16384:
            raise ValueError("bounded semantic query required")
        if type(limit) is not int or not 1<=limit<=min(64,p.candidate_pool):
            raise ValueError("semantic result limit exceeded")
        if not isinstance(spans,(tuple,list)) or len(spans)>p.max_spans:
            raise ValueError("semantic span count outside bounds")
        if not spans:
            return (),{"status":"empty_corpus","encoded_calls":0}
        if any(not isinstance(x,SemanticSpan) for x in spans):
            raise TypeError("authorized exact SemanticSpan records required")
        keys=[row.identity for row in spans]
        if len(set(keys))!=len(spans):
            raise ValueError("duplicate semantic span identity")
        distinct_contexts=set(row.context for row in spans)
        if sum(len(text) for text in distinct_contexts)>p.max_source_chars or any(len(text)>p.context_chars for text in distinct_contexts):
            raise ValueError("semantic contextual corpus size exceeds budget")
        if interrupt:interrupt()
        q,qmulti=self._prepared(query,prepared,interrupt)
        vectors,calls=self._features(spans,cache,interrupt)
        matrices=[_as_embedding(vectors[key],self.encoder.policy.dimension,p.segments) for key in keys]
        dense=np.stack([x[0] for x in matrices])
        cosine=np.clip(dense@q,-1,1)
        words=terms(query)
        query_terms=set(words)
        freqs=[Counter(terms(row.text)) for row in spans]
        df=Counter(term for freq in freqs for term in query_terms.intersection(freq))
        avg=sum(sum(freq.values()) for freq in freqs)/len(freqs) or 1
        lexical=[]
        for freq in freqs:
            length=sum(freq.values())
            lexical.append(sum(math.log(1+(len(freqs)-df[t]+.5)/(df[t]+.5))*
                (freq[t]*2.2)/(freq[t]+1.2*(.25+.75*length/avg)) for t in query_terms if freq[t]))
        # Protect explicit rare IDs/quoted terms; semantic neighbors alone
        # must not displace exact matches to a requested error code or SKU.
        anchors={t for t in words if any(ch.isdigit() for ch in t) or any(ch in "-_.:" for ch in t)}
        exact=[len(anchors.intersection(freq)) for freq in freqs]
        parent_groups=defaultdict(list)
        ordinals={}
        for i,row in enumerate(spans):
            identity=(row.source_id,row.revision,row.ordinal)
            if identity in ordinals:
                raise ValueError("duplicate source ordinal")
            ordinals[identity]=i
            parent_groups[(row.source_id,row.revision,row.ordinal//p.parent_width)].append(i)
        parent=[0.0]*len(spans)
        for indices in parent_groups.values():
            centroid=dense[indices].mean(axis=0)
            norm=float(np.linalg.norm(centroid))
            score=float(centroid@q)/norm if norm>1e-12 else 0.0
            for i in indices:parent[i]=score
        eligible=[i for i in range(len(spans)) if lexical[i]>0 or cosine[i]>=p.min_cosine]
        if not eligible:
            return (),{"status":"no_relevant_span","encoded_calls":calls}
        rank_sum=defaultdict(float)
        for scores,pool,weight in ((cosine,eligible,1.0),(lexical,[i for i in eligible if lexical[i]>0],1.0),
                                   (parent,eligible,0.35)):
            order=sorted(pool,key=lambda i:(-scores[i],keys[i]))[:p.candidate_pool]
            for pos,i in enumerate(order,1):rank_sum[i]+=weight/(20+pos)
        for i in sorted((j for j in eligible if exact[j]),key=lambda j:(-exact[j],-lexical[j],keys[j]))[:p.candidate_pool]:
            rank_sum[i]+=0.04
        pool=sorted(rank_sum,key=lambda i:(-exact[i],-rank_sum[i],keys[i]))[:p.candidate_pool]
        # Neighbor expansion adds only exact nearby leaves. This permits
        # antecedent/definition recovery around a selected semantic match.
        expanded=set(pool)
        for i in pool[:min(limit,8)]:
            r=spans[i]
            for delta in (-1,1):
                j=ordinals.get((r.source_id,r.revision,r.ordinal+delta))
                if j is not None and len(expanded)<p.candidate_pool*2:
                    expanded.add(j)
        # Compute late interaction only over the bounded candidate pool.
        maxsim={i:float(np.clip((qmulti@matrices[i][1].T).max(axis=1).mean(),-1,1)) for i in expanded}
        scale=max(rank_sum.values())
        base={i:0.44*(float(cosine[i])+1)/2+0.30*(maxsim[i]+1)/2+
            0.20*rank_sum[i]/scale+0.06*(parent[i]+1)/2 for i in expanded}
        cross={}
        if self.reranker is not None:
            shortlist=sorted(expanded,key=lambda i:(-exact[i],-base[i],keys[i]))[:self.reranker.policy.max_pairs]
            if interrupt:interrupt()
            observed=self.reranker.score(query,[spans[i].text for i in shortlist])
            if len(observed)!=len(shortlist):
                raise RuntimeError("cross-encoder result count mismatch")
            cross=dict(zip(shortlist,observed))
            # Rerank the evaluated shortlist only. Unscored candidates are
            # not promoted using an invented neutral model score.
            expanded=set(shortlist)
            for i in shortlist:base[i]=0.55*base[i]+0.45*cross[i]
        selected=[]
        scores={}
        remaining=set(expanded)
        while remaining and len(selected)<limit:
            if interrupt:interrupt()
            scored=[]
            for i in remaining:
                row=spans[i]
                if any(row.source_id==spans[j].source_id and row.revision==spans[j].revision and
                       max(0,min(row.end,spans[j].end)-max(row.start,spans[j].start))*3>=min(row.end-row.start,spans[j].end-spans[j].start) for j in selected):
                    continue
                redundancy=max((max(0.0,float(dense[i]@dense[j])) for j in selected),default=0.0)
                adjacent=any(spans[j].source_id==row.source_id and spans[j].revision==row.revision and abs(spans[j].ordinal-row.ordinal)==1 for j in selected)
                if i not in eligible and not adjacent:
                    continue
                score=base[i]-p.diversity*redundancy+(p.neighbor_boost if adjacent else 0)
                scored.append((i,score))
            if not scored:break
            i,score=max(scored,key=lambda pair:(exact[pair[0]],pair[1],-int(keys[pair[0]][:16],16)))
            selected.append(i)
            scores[i]=score
            remaining.remove(i)
        rows=tuple((spans[i],float(scores[i])) for i in selected)
        receipt={"schema":"skeleton.hybrid-context-retrieval.v1","encoder_sha256":self.encoder.identity,
                 "policy_sha256":p.digest,"query_sha256":sha256(query.encode()).hexdigest(),
                 "source_span_count":len(spans),"encoded_calls":calls,"query_feature_reused":prepared is not None,"candidate_count":len(expanded),
                 "selected":[{"span_sha256":keys[i],"source_revision":spans[i].revision,
                              "ordinal":spans[i].ordinal,"dense_cosine":float(cosine[i]),
                              "late_interaction":maxsim[i],"anchor_matches":exact[i],
                              "cross_encoder_score":cross.get(i)} for i in selected],
                 "cross_encoder_sha256":self.reranker.identity if self.reranker else None,
                 "cross_encoder_pairs":len(cross),
                 "semantic_entailment_verified":False}
        receipt["receipt_sha256"]=_digest(receipt)
        return rows,receipt

    def evidence_excerpt(self,query,span:SemanticSpan,*,max_chars=220,prepared=None):
        """Select real contextual token windows within the winning exact leaf.

        Preserve exact character anchors, including paraphrase hits with no
        lexical match, before the existing offline grounded-turn compiler.
        """
        import numpy as np
        if not isinstance(span,SemanticSpan) or type(max_chars) is not int or not 32<=max_chars<=600:
            raise ValueError("bounded evidence excerpt required")
        if len(span.text)<=max_chars:
            return 0,len(span.text)
        q,qmulti=self._prepared(query,prepared)
        stop=len(span.text)-max_chars
        starts=set(range(0,stop+1,max_chars//3))
        starts.update((0,stop))
        anchors=set(t for t in terms(query) if any(ch.isdigit() for ch in t) or any(ch in "-_.:" for ch in t))
        # Add exact phrase/identifier-centered candidates without altering
        # original Unicode source coordinates.
        for m in _WORD.finditer(span.text):
            if set(terms(m.group())).intersection(anchors):
                starts.add(max(0,min(stop,m.start()-max_chars//3)))
        if len(starts)>256:
            raise ValueError("semantic excerpt candidate limit exceeded")
        starts=sorted(starts)
        ranges=[(span.local_start+x,span.local_start+x+max_chars) for x in starts]
        vectors=self.encoder.spans(span.context,ranges,segments=self.policy.segments)
        ranked=[]
        qterms=set(terms(query))
        for start,vec in zip(starts,vectors):
            dense,multi=_as_embedding(vec,self.encoder.policy.dimension,self.policy.segments)
            wordset=set(terms(span.text[start:start+max_chars]))
            score=.55*float(dense@q)+.35*float((qmulti@multi.T).max(axis=1).mean())+.10*len(qterms&wordset)/max(1,len(qterms))
            ranked.append((len(anchors&wordset),score,-start))
        start=-max(ranked)[2]
        return start,start+max_chars
