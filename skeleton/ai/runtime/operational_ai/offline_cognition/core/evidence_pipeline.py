"""Source-bound, finite offline evidence projection. Never a model or rights authority."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import CognitionError, identifier, integer, sha, number, text, hash_bytes, fingerprint, refuse
from .sources import Source, extract_span
from .retrieval import BM25, IndexedDocument
from .math import cosine, vector, reciprocal_rank_fusion

MAX_DOCUMENTS=2048
MAX_BYTES=262144
MAX_SPANS=2048

@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    source: Source
    payload: bytes
    embedding: tuple | None = None
    embedding_model_sha256: str | None = None

    def __post_init__(self):
        if type(self.source) is not Source or self.source.approved is not True:
            refuse("typed, operator-approved source receipt required")
        if type(self.payload) is not bytes or not 1 <= len(self.payload) <= MAX_BYTES:
            refuse("bounded original source bytes required")
        if self.source.bytes_length != len(self.payload) or self.source.sha256 != hash_bytes(self.payload):
            refuse("source bytes and receipt disagree")
        try:
            decoded=self.payload.decode("utf-8","strict")
        except UnicodeError as exc:
            raise CognitionError("source UTF8 malformed") from exc
        if "\x00" in decoded:
            refuse("embedded NUL in original source")
        if self.embedding is None:
            if self.embedding_model_sha256 is not None:
                refuse("embedding model supplied without vector")
        else:
            if type(self.embedding) is not tuple:
                refuse("immutable embedding tuple required")
            vector(self.embedding)
            sha(self.embedding_model_sha256)

    @property
    def text(self):
        return self.payload.decode("utf-8","strict")

@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    source_id: str
    source_sha256: str
    start: int
    end: int
    passage_sha256: str

    def __post_init__(self):
        identifier(self.source_id)
        sha(self.source_sha256)
        integer(self.start,maximum=MAX_BYTES)
        integer(self.end,minimum=self.start+1,maximum=MAX_BYTES)
        sha(self.passage_sha256)

def partition(document, *, window_bytes=2048, overlap_bytes=128, limit=MAX_SPANS):
    """Split UTF8 on codepoint boundaries while retaining original byte offsets."""
    if type(document) is not EvidenceDocument:
        refuse("source-bound document required")
    integer(window_bytes,minimum=16,maximum=65536)
    integer(overlap_bytes,maximum=65535)
    integer(limit,minimum=1,maximum=MAX_SPANS)
    if overlap_bytes >= window_bytes:
        refuse("overlap must be smaller than passage window")
    boundaries=[0]
    for char in document.text:
        boundaries.append(boundaries[-1]+len(char.encode("utf-8")))
    spans=[]
    start=0
    last=len(boundaries)-1
    while start < last:
        end=start+1
        while end <= last and boundaries[end]-boundaries[start] <= window_bytes:
            end+=1
        end-=1
        if end<=start:
            refuse("invalid UTF8 passage step")
        lo,hi=boundaries[start],boundaries[end]
        spans.append(EvidenceSpan(document.source.source_id,document.source.sha256,
                                  lo,hi,hash_bytes(document.payload[lo:hi])))
        if len(spans)>limit:
            refuse("passage ceiling exceeded")
        if end==last:
            break
        next_start=end
        while next_start > start+1 and boundaries[end]-boundaries[next_start-1] <= overlap_bytes:
            next_start-=1
        if next_start <= start:
            refuse("partition cannot advance")
        start=next_start
    return tuple(spans)

def verify(document, span, *, tenant, subject, quoted_text=None):
    """Exact original bytes prove provenance, never semantic entailment."""
    if type(document) is not EvidenceDocument or type(span) is not EvidenceSpan:
        refuse("typed evidence source and citation required")
    if (span.source_id,span.source_sha256) != (document.source.source_id,document.source.sha256):
        refuse("source identity differs from citation")
    receipt=extract_span(document.payload,document.source,start=span.start,end=span.end,
                         tenant=tenant,subject=subject)
    if receipt["sha256"]!=span.passage_sha256:
        refuse("quoted passage digest mismatch")
    quote=document.payload[span.start:span.end].decode("utf-8","strict")
    if quoted_text is not None and (type(quoted_text) is not str or quoted_text!=quote):
        refuse("quotation does not exactly match original bytes")
    return {"source_id":span.source_id,"source_sha256":span.source_sha256,
            "start":span.start,"end":span.end,"passage_sha256":span.passage_sha256,
            "quote":quote,"exact_bytes_verified":True,
            "semantic_entailment_proved":False,"rights_independently_proved":False}

def unique_spans(spans, *, limit=MAX_SPANS):
    if type(spans) not in (tuple,list) or len(spans)>limit:
        refuse("bounded span collection required")
    seen=set()
    output=[]
    for s in spans:
        if type(s) is not EvidenceSpan:
            refuse("typed span required")
        key=(s.source_sha256,s.start,s.end,s.passage_sha256)
        if key not in seen:
            seen.add(key);output.append(s)
    return tuple(output)

def diverse_spans(rows, *, limit=10, weight=0.75):
    """Deterministic rerank penalizing original-byte overlap on the same source."""
    integer(limit,minimum=1,maximum=100)
    weight=number(weight,minimum=0,maximum=1)
    if type(rows) not in (tuple,list) or len(rows)>MAX_SPANS:
        refuse("bounded candidate rankings required")
    items=[];seen=set()
    for row in rows:
        if type(row) is not tuple or len(row)!=2 or type(row[0]) is not EvidenceSpan:
            refuse("typed (span,score) tuple required")
        span,score=row
        score=number(score,minimum=0,maximum=1)
        key=(span.source_sha256,span.start,span.end)
        if key in seen:
            refuse("duplicate rank input must be deduplicated")
        seen.add(key);items.append((span,score))
    chosen=[]
    while items and len(chosen)<limit:
        def final_score(item):
            s,relevance=item
            redundancy=max((max(0,min(s.end,c.end)-max(s.start,c.start))/
                           max(1,s.end-s.start) for c,_ in chosen
                           if c.source_sha256==s.source_sha256),default=0.0)
            return weight*relevance-(1-weight)*redundancy
        best=min(items,key=lambda x:(-final_score(x),x[0].source_id,x[0].start))
        chosen.append(best);items.remove(best)
    return tuple(s for s,_ in chosen)

class EvidenceIndex:
    """Rebuildable tenant+subject projection. No model/provider or persistent authority."""

    def __init__(self, records, *, tenant, subject):
        self.tenant=identifier(tenant);self.subject=identifier(subject)
        if type(records) not in (tuple,list) or not 1 <= len(records) <= MAX_DOCUMENTS:
            refuse("bounded evidence inventory required")
        self.documents={}
        for doc in records:
            if type(doc) is not EvidenceDocument:
                refuse("typed source receipt required")
            if (doc.source.tenant,doc.source.subject)!=(tenant,subject):
                refuse("mixed caller scope cannot be indexed")
            if doc.source.source_id in self.documents:
                refuse("duplicate source identity")
            self.documents[doc.source.source_id]=doc
        self.bm25=BM25(tuple(IndexedDocument(k,tenant,v.source.sha256,v.text)
                             for k,v in self.documents.items()))

    def lexical(self, query, *, limit=10):
        text(query,maximum=4096)
        integer(limit,minimum=1,maximum=100)
        return self.bm25.search(query,scope=self.tenant,limit=limit)

    def dense(self, query_vector, *, embedding_model_sha256, limit=10):
        sha(embedding_model_sha256)
        integer(limit,minimum=1,maximum=100)
        q=vector(query_vector)
        results=[]
        for key,doc in self.documents.items():
            if doc.embedding is None or doc.embedding_model_sha256!=embedding_model_sha256:
                refuse("real model-bound embedding missing")
            if len(doc.embedding)!=len(q):
                refuse("embedding dimensions disagree")
            results.append((key,(cosine(q,doc.embedding)+1)/2))
        return tuple(sorted(results,key=lambda x:(-x[1],x[0]))[:limit])

    def retrieve(self, query, *, mode, limit=10,
                 query_vector=None, embedding_model_sha256=None):
        if mode not in ("lexical","dense","hybrid"):
            refuse("retrieval mode not allowlisted")
        integer(limit,minimum=1,maximum=100)
        if mode=="lexical":
            if query_vector is not None or embedding_model_sha256 is not None:
                refuse("lexical-only request claimed dense data")
            ids=tuple(k for k,_ in self.lexical(query,limit=limit))
        elif mode=="dense":
            if query_vector is None:
                refuse("missing real dense vector")
            ids=tuple(k for k,_ in self.dense(
                query_vector,embedding_model_sha256=embedding_model_sha256,limit=limit))
        else:
            if query_vector is None:
                refuse("missing real hybrid vector")
            sparse=tuple(k for k,_ in self.lexical(query,limit=limit))
            dense=tuple(k for k,_ in self.dense(query_vector,
                          embedding_model_sha256=embedding_model_sha256,limit=limit))
            ids=reciprocal_rank_fusion((sparse,dense),limit=MAX_DOCUMENTS)[:limit]
        return tuple({"source_id":k,"source_sha256":self.documents[k].source.sha256,
                      "retrieval_mode":mode,"native_inference_executed":False,
                      "semantic_entailment_proved":False,"source_is_policy":False}
                     for k in ids)

    def cite(self, span, *, quoted_text=None):
        if type(span) is not EvidenceSpan or span.source_id not in self.documents:
            refuse("source not present in authorized index")
        return verify(self.documents[span.source_id],span,tenant=self.tenant,
                      subject=self.subject,quoted_text=quoted_text)

    def attribution(self, spans):
        checked=tuple(self.cite(s) for s in unique_spans(spans))
        ledger=tuple({"source_id":r["source_id"],"source_sha256":r["source_sha256"],
                      "start":r["start"],"end":r["end"],
                      "passage_sha256":r["passage_sha256"]} for r in checked)
        return {"schema":"offline-source-attribution.v1","tenant":self.tenant,
                "subject":self.subject,"citations":ledger,
                "receipt_sha256":fingerprint(list(ledger)),
                "byte_provenance_verified":True,
                "semantic_entailment_proved":False,
                "model_or_device_qualified":False}
