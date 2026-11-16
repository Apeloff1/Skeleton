"""Small bounded offline evidence reranker for the canonical context owner.

Hybrid reciprocal-rank fusion uses lexical relevance, optional independently
supplied semantic ranks, source authority and evidence coverage. No embeddings,
network requests, or access grants are created. The exact verified excerpts
and the source snapshot remain the owner's authority.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import islice
import json
import math
import re
import unicodedata

from .evidence_packing import Excerpt, Scope, MAX_EXCERPTS, MAX_BYTES

_WORD = re.compile(r"[^\W_]+(?:[_-][^\W_]+)*", re.UNICODE)
_MAX_QUERY_BYTES = 8192
_MAX_TERMS = 256
_MAX_CHANNELS = 4


def _pin(x):
    if type(x) is not str or len(x)!=64 or any(c not in "0123456789abcdef" for c in x):
        raise ValueError("SHA256 pin required")


def _int(x,lo,hi):
    if type(x) is not int or not lo<=x<=hi:
        raise ValueError("bounded numeric value required")


def _digest(x):
    return sha256(json.dumps(x,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode("ascii")).hexdigest()


def _terms(text):
    # Normalized for ranking only; never change original source bytes.
    normalized=unicodedata.normalize("NFKC",text).casefold()
    return [match.group(0)[:128] for match in _WORD.finditer(normalized)]


@dataclass(frozen=True,slots=True)
class RankedChannel:
    scope_sha256: str
    channel_sha256: str
    ranking: tuple[str,...]
    weight: int=1

    def __post_init__(self):
        _pin(self.scope_sha256)
        _pin(self.channel_sha256)
        _int(self.weight,1,4)
        if type(self.ranking) is not tuple or len(self.ranking)>MAX_EXCERPTS:
            raise ValueError("finite unique ranking required")
        for x in self.ranking:
            _pin(x)
        if len(set(self.ranking))!=len(self.ranking):
            raise ValueError("duplicate rank identity")


@dataclass(frozen=True,slots=True)
class Reranked:
    scope_sha256: str
    ranked: tuple[Excerpt,...]
    excluded: tuple[tuple[str,str],...]
    lexical_matched: int
    channel_count: int
    receipt_sha256: str


def rerank(query:str, excerpts, *, scope:Scope,
           query_text_sha256:str, channels:tuple[RankedChannel,...]=(),
           revoked_sources:frozenset[str], revoked_revisions:frozenset[str],
           rrf_constant:int=20) -> Reranked:
    """Re-rank intact authorized excerpts; zero semantic evidence is explicit.

    BM25 is bounded to caller-supplied excerpts, not the worldwide corpus.
    Reciprocal-rank fusion avoids mixing arbitrary cosine and lexical scales.
    All available conflicting/required rows survive for evidence packing;
    this layer does not silently truncate to a top-k answer.
    """
    if type(scope) is not Scope or type(query) is not str or not query.strip():
        raise ValueError("typed scope and nonempty query required")
    if len(query)>_MAX_QUERY_BYTES or len(query.encode("utf-8"))>_MAX_QUERY_BYTES:
        raise ValueError("query exceeds local rank budget")
    _pin(query_text_sha256)
    if sha256(query.encode("utf-8")).hexdigest()!=query_text_sha256:
        raise ValueError("query text digest mismatch")
    _int(rrf_constant,1,128)
    query_terms=tuple(dict.fromkeys(_terms(query)))
    if not query_terms or len(query_terms)>_MAX_TERMS:
        raise ValueError("unsupported query term count")
    rows=tuple(islice(excerpts,MAX_EXCERPTS+1))
    if len(rows)>MAX_EXCERPTS or any(type(x) is not Excerpt for x in rows):
        raise ValueError("bounded typed evidence input required")
    if sum(len(x.text.encode("utf-8")) for x in rows)>MAX_BYTES:
        raise ValueError("aggregate evidence bytes exceeded")
    identities={x.identity:x for x in rows}
    if len(identities)!=len(rows):
        raise ValueError("duplicate evidence identity")
    for revoked in (revoked_sources,revoked_revisions):
        if type(revoked) is not frozenset or len(revoked)>100_000:
            raise ValueError("bounded revocation set required")
        for x in revoked:
            _pin(x)
    if type(channels) is not tuple or len(channels)>_MAX_CHANNELS or any(type(x) is not RankedChannel for x in channels):
        raise ValueError("bounded ranked channels required")
    if len({x.channel_sha256 for x in channels})!=len(channels):
        raise ValueError("duplicate rank channel")
    for channel in channels:
        if channel.scope_sha256!=scope.identity or not set(channel.ranking).issubset(identities):
            raise ValueError("different snapshot or unknown channel member")
    excluded={}
    live={}
    for identity,x in identities.items():
        if x.source_sha256 in revoked_sources or x.revision_sha256 in revoked_revisions:
            excluded[identity]="revoked"
        elif x.valid_from>scope.as_of or (x.valid_until is not None and scope.as_of>=x.valid_until):
            excluded[identity]="outside_as_of"
        else:
            live[identity]=x
    terms=set(query_terms)
    lengths={}
    freqs={}
    df=Counter()
    for identity,x in live.items():
        words=_terms(x.text)
        lengths[identity]=len(words)
        counts=Counter(word for word in words if word in terms)
        freqs[identity]=counts
        df.update(counts.keys())
    n=len(live)
    average=max(1,sum(lengths.values())/max(1,n))
    lexical={}
    for identity,counts in freqs.items():
        score=0.0
        length_norm=1.2*(0.25+0.75*lengths[identity]/average)
        for term in query_terms:
            tf=counts.get(term,0)
            if tf:
                idf=math.log1p((n-df[term]+0.5)/(df[term]+0.5))
                score+=idf*tf*2.2/(tf+length_norm)
        if score>0:
            lexical[identity]=int(score*1_000_000)
    lex_order=sorted(lexical,key=lambda x:(-lexical[x],x))
    fused={x:0 for x in live}
    for i,identity in enumerate(lex_order,1):
        fused[identity]+=1_000_000//(rrf_constant+i)
    for channel in sorted(channels,key=lambda c:c.channel_sha256):
        kept=(identity for identity in channel.ranking if identity in live)
        for i,identity in enumerate(kept,1):
            fused[identity]+=channel.weight*1_000_000//(rrf_constant+i)
    # Normalize ranking only over this finite request. Include the upstream
    # relevance signal as a weak tie-break rather than letting it swamp RRF.
    best=max(fused.values(),default=0)
    ranked=[]
    for identity,x in live.items():
        relevance=0 if not best else fused[identity]*9500//best
        relevance+=x.relevance_bp//20
        ranked.append(replace(x,relevance_bp=relevance))
    ranked.sort(key=lambda x:(-x.relevance_bp,-x.authority_bp,x.identity))
    receipt=_digest({"scope":scope.identity,"query_text":query_text_sha256,
                     "rrf":rrf_constant,"channels":[[c.channel_sha256,c.weight,c.ranking]
                     for c in sorted(channels,key=lambda c:c.channel_sha256)],
                     "source_inputs":[[k,x.relevance_bp,x.authority_bp]
                     for k,x in sorted(identities.items())],
                     "lexical":lex_order,"ranked":[[x.identity,x.relevance_bp] for x in ranked],
                     "excluded":sorted(excluded.items())})
    return Reranked(scope.identity,tuple(ranked),tuple(sorted(excluded.items())),
                    len(lex_order),len(channels),receipt)


def prepare_ranked_request(request, *, scope:Scope, excerpts, budget,
                           count_request, required_claims:tuple[str,...],
                           revoked_sources:frozenset[str],
                           revoked_revisions:frozenset[str],
                           channels:tuple[RankedChannel,...]=(),
                           max_tokenizer_calls:int=160):
    """Compose the hybrid ranker with the existing canonical packer.

    No sealed context is mutated, all evidence remains reference data, and
    the caller must revalidate source authorization and seal before inference.
    """
    from .local import LocalInferenceRequest, LocalInputBudget
    from .evidence_packing import prepare_evidence_request

    if type(request) is not LocalInferenceRequest or type(budget) is not LocalInputBudget:
        raise ValueError("canonical typed request and budget required")
    if type(scope) is not Scope or request.context_digest is not None or scope.query_sha256!=request.digest:
        raise ValueError("ranking is bound to the original unsealed request")
    rank=rerank(request.prompt,excerpts,scope=scope,
                query_text_sha256=sha256(request.prompt.encode("utf-8")).hexdigest(),
                channels=channels,revoked_sources=revoked_sources,
                revoked_revisions=revoked_revisions)
    prepared,packing=prepare_evidence_request(request,scope=scope,excerpts=rank.ranked,
                      budget=budget,count_request=count_request,required_claims=required_claims,
                      revoked_sources=revoked_sources,revoked_revisions=revoked_revisions,
                      max_tokenizer_calls=max_tokenizer_calls)
    return prepared,packing,rank
