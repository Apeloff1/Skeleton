"""Compact learned-vector ANN postings for qualified historical passages.

Random hyperplane LSH with one-bit multiprobe; int8 cosine reranking. The
embedding identity pins local model bytes, tokenizer and pooling contract.
This is bounded approximate routing, not a global HNSW quality claim.
"""
from __future__ import annotations

import base64
import hashlib
import math

from core.dragon_passage_index import ranges
from skeleton.ai.webcrawler.dragon_archive_scale import digest
from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity,finite

SCHEMA="skeleton.dragon.dense-route.v1"
BANDS=8
BITS=8
MAX_RECORDS=32
MAX_QUERY_KEYS=BANDS*(BITS+1)
MIN_COSINE=.40


def quantize(vec):
    if not isinstance(vec,list) or not 32<=len(vec)<=1024 or not all(
            type(v) in (int,float) and math.isfinite(v) for v in vec):
        raise ValueError("embedding vector")
    norm=math.sqrt(sum(v*v for v in vec))
    if norm<=1e-12:
        raise ValueError("zero vector")
    normalized=[v/norm for v in vec]
    peak=max(abs(v) for v in normalized)
    return bytes((max(-127,min(127,round(127*v/peak)))+128) for v in normalized)


def _ints(raw):
    return [v-128 for v in raw]


def _cosine(a,b):
    if len(a)!=len(b): raise ValueError("dimension mismatch")
    x,y=_ints(a),_ints(b)
    norm=math.sqrt(sum(v*v for v in x)*sum(v*v for v in y))
    return sum(a*b for a,b in zip(x,y))/norm if norm else 0.0


def planes(model,dim):
    if not hash_identity(model) or type(dim) is not int or not 32<=dim<=1024:
        raise ValueError("model identity")
    data=hashlib.shake_256(("dragon-ann-v1:"+model+":"+str(dim)).encode()).digest(BANDS*BITS*((dim+7)//8))
    width=(dim+7)//8
    return [[1 if data[i*width+j//8]&(1<<(j%8)) else -1 for j in range(dim)]
            for i in range(BANDS*BITS)]


def codes(raw,projection):
    values=_ints(raw)
    if len(projection)!=BANDS*BITS or any(len(p)!=len(values) for p in projection):
        raise ValueError("projection shape")
    bits=[sum(v*w for v,w in zip(values,p))>=0 for p in projection]
    return [sum(int(bits[i*BITS+j])<<j for j in range(BITS)) for i in range(BANDS)]


def tokens(scope,model,codes,*,multiprobe=False):
    values=set()
    for index,code in enumerate(codes):
        candidates=[code]+([code^(1<<bit) for bit in range(BITS)] if multiprobe else [])
        for candidate in candidates:
            values.add(digest({"scope":scope,"schema":SCHEMA,"model":model,"band":index,"code":candidate}))
    return sorted(values)


def sampled_spans(snapshot,grant,policies,now,allowed):
    groups=[]
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                              policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
        if expiry is None or not source["text"]:
            continue
        windows=ranges(source["text"])
        order=list(dict.fromkeys([0,len(windows)//2,len(windows)-1]))
        groups.append([(sid,*windows[i],expiry) for i in order])
    # If 64 sources compete for 32 slots, spread across source identity order.
    if len(groups)>MAX_RECORDS:
        groups=[groups[i*len(groups)//MAX_RECORDS] for i in range(MAX_RECORDS)]
    result=[]
    for layer in range(3):
        for group in groups:
            if len(group)>layer and len(result)<MAX_RECORDS:
                result.append(group[layer])
    return result


def build(scope,snapshot,grant,policies,now,allowed,encoder,*,explicit_spans=None):
    model=encoder.identity
    dim=encoder.dimensions
    projection=planes(model,dim)
    spans=sampled_spans(snapshot,grant,policies,now,allowed) if explicit_spans is None else explicit_spans
    if len(spans)>MAX_RECORDS:raise ValueError('dense batch limit')
    records=[]
    union=set()
    for offset in range(0,len(spans),8):
        batch=spans[offset:offset+8]
        texts=[snapshot["sources"][sid]["text"][start:end] for sid,start,end,_ in batch]
        # Blank windows are not valid embedding inputs.
        selected=[(row,text) for row,text in zip(batch,texts) if text.strip()]
        if not selected: continue
        vectors=encoder.encode([text for _,text in selected])
        if len(vectors)!=len(selected): raise ValueError("batch response mismatch")
        for ((sid,start,end,expiry),text),vec in zip(selected,vectors):
            raw=quantize(vec)
            if len(raw)!=dim:raise ValueError("model dimension mismatch")
            keys=tokens(scope,model,codes(raw,projection))
            union.update(keys)
            records.append({"source_id":sid,"start":start,"end":end,"passage_digest":hashlib.sha256(text.encode()).hexdigest(),
                            "expires_at":expiry,"vector":base64.b64encode(raw).decode("ascii"),"keys":keys})
    value={"schema":SCHEMA,"model_identity":model,"dimensions":dim,"snapshot_digest":snapshot["snapshot_digest"],
           "grant_digest":digest(grant),"policy_digest":digest(policies),"expires_at":grant["expires_at"],
           "tokens":sorted(union),"records":records}
    return {**value,"digest":digest(value)}


def query(scope,query_text,encoder):
    if not isinstance(query_text,str) or not 1<=len(query_text)<=512 or not query_text.strip():
        raise ValueError("embedding query")
    raw=quantize(encoder.encode([query_text])[0])
    if len(raw)!=encoder.dimensions:raise ValueError("query dimension")
    model=encoder.identity
    return {"model_identity":model,"vector":raw,"tokens":tokens(scope,model,
                codes(raw,planes(model,len(raw))),multiprobe=True)}


def rank(scope,snapshot,grant,policies,now,allowed,index,q):
    expected={"schema","model_identity","dimensions","snapshot_digest","grant_digest","policy_digest",
              "expires_at","tokens","records","digest"}
    if (not isinstance(index,dict) or set(index)!=expected or index["schema"]!=SCHEMA
            or index["model_identity"]!=q["model_identity"] or index["dimensions"]!=len(q["vector"])
            or index["snapshot_digest"]!=snapshot["snapshot_digest"] or index["grant_digest"]!=digest(grant)
            or index["policy_digest"]!=digest(policies) or index["expires_at"]!=grant["expires_at"] or index["expires_at"]<=now
            or not isinstance(index["records"],list) or len(index["records"])>MAX_RECORDS
            or not isinstance(index["tokens"],list) or len(index["tokens"])>MAX_RECORDS*BANDS
            or index["digest"]!=digest({k:v for k,v in index.items() if k!="digest"})):
        raise ValueError("dense route invalid")
    model=q["model_identity"]
    projection=planes(model,index["dimensions"])
    union=set()
    ids=set()
    result=[]
    wanted=set(q["tokens"])
    for row in index["records"]:
        if (not isinstance(row,dict) or set(row)!={"source_id","start","end","passage_digest","expires_at","vector","keys"}
                or not hash_identity(row["source_id"]) or row["source_id"] not in snapshot["sources"]
                or type(row["start"]) is not int or type(row["end"]) is not int
                or not 0<=row["start"]<row["end"]<=24000 or row["end"]-row["start"]>768
                or not hash_identity(row["passage_digest"]) or not finite(row["expires_at"])
                or not isinstance(row["vector"],str) or len(row["vector"])>1400
                or not isinstance(row["keys"],list) or len(row["keys"])!=BANDS):
            raise ValueError("dense record invalid")
        identity=(row["source_id"],row["start"],row["end"])
        if identity in ids:raise ValueError("duplicate vector span")
        ids.add(identity)
        raw=base64.b64decode(row["vector"],validate=True)
        if len(raw)!=index["dimensions"] or tokens(scope,model,codes(raw,projection))!=row["keys"]:
            raise ValueError("vector posting witness differs")
        union.update(row["keys"])
        if not wanted.intersection(row["keys"]) or row["source_id"] not in allowed:
            continue
        source=snapshot["sources"][row["source_id"]]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                policy=policies.get(row["source_id"],{"enabled":True,"version":0}),now=now)
        if expiry is None or row["expires_at"]!=expiry or row["end"]>len(source["text"]):
            continue
        passage=source["text"][row["start"]:row["end"]]
        if hashlib.sha256(passage.encode()).hexdigest()!=row["passage_digest"]:
            raise ValueError("vector span witness differs")
        score=_cosine(q["vector"],raw)
        if score>=MIN_COSINE:
            result.append({"source_id":row["source_id"],"start":row["start"],"end":row["end"],
                           "passage_digest":row["passage_digest"],"score":round(score,7),
                           "valid_until":expiry,"preserved_text_hash":source["preserved_text_hash"]})
    if sorted(union)!=index["tokens"]:
        raise ValueError("dense route union differs")
    return sorted(result,key=lambda h:(-h["score"],h["source_id"],h["start"]))[:16]


def exhaustive_spans(snapshot,grant,policies,now,allowed):
    """Full overlapping coverage of every independently eligible retained character.

    Empty/whitespace-only windows are intentionally omitted. This is coverage
    of retained extraction, not the original website's entire byte stream.
    Batches are independently published by the durable corpus worker.
    """
    spans=[]
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                              policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
        if expiry is None:continue
        text=source["text"]
        if len(text)>24000:raise ValueError("retained source bound")
        for start in range(0,len(text),512):
            end=min(len(text),start+768)
            if text[start:end].strip():spans.append((sid,start,end,expiry))
            if end==len(text):break
    if len(spans)>64*47:raise ValueError("full coverage exceeds snapshot bounds")
    return spans
