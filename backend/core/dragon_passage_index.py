"""Versioned, policy-bound lexical passage routing and exact span reranking.

Persisted features are scope-hashed (not secret/encrypted) and contain no raw
text. Each record binds the original snapshot, grant, source policy and exact
Unicode offsets. They are search hints; no source authority comes from this
index. This is sparse retrieval, not a trained dense-embedding model.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math

from core.dragon_hybrid_rank import words,STOP
from skeleton.ai.webcrawler.dragon_archive_scale import digest
from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity,finite

SCHEMA="skeleton.dragon.passage-route.v1"
WIDTH=768
STRIDE=640
MAX_PER_SOURCE=12
MAX_SOURCES=64
MAX_PASSAGES=MAX_SOURCES*MAX_PER_SOURCE
KEYS_PER_PASSAGE=12
MAX_KEYS=MAX_PASSAGES*KEYS_PER_PASSAGE
MAX_TEXT=24000


def ranges(text):
    if not isinstance(text,str) or not text or len(text)>MAX_TEXT:
        raise ValueError("source text bound")
    if len(text)<=WIDTH:
        return [(0,len(text))]
    # Adapt stride so a long source gets representation across its entire
    # length, not just the first paragraphs. The bounded route is sampled.
    stride=max(STRIDE,math.ceil((len(text)-WIDTH)/(MAX_PER_SOURCE-1)))
    starts=list(range(0,len(text)-WIDTH+1,stride))
    if starts[-1]!=len(text)-WIDTH:
        starts.append(len(text)-WIDTH)
    return [(start,start+WIDTH) for start in starts]


def _token(scope,kind,term):
    return digest({"scope":scope,"domain":SCHEMA,"kind":kind,"term":term})


def _terms(text):
    tokens=words(text)
    lex=Counter(w for w in tokens if len(w)>2 and w not in STOP)
    pairs=Counter(a+" "+b for a,b in zip(tokens,tokens[1:])
                  if a not in STOP and b not in STOP and len(a)>2 and len(b)>2)
    return lex,pairs


def _keys(scope,text):
    lex,pairs=_terms(text)
    # Deterministic rare-word and phrase selection; avoids ubiquitous words
    # dominating candidate discovery. No irreversible authority from features.
    rare=sorted(lex,key=lambda w:(lex[w],-len(w),w))[:8]
    phrases=sorted(pairs,key=lambda w:(pairs[w],-len(w),w))[:4]
    return sorted({_token(scope,"w",w) for w in rare}|{_token(scope,"p",w) for w in phrases})


def query_keys(scope,query):
    if not isinstance(query,str) or not 1<=len(query)<=512:
        raise ValueError("query bound")
    lex,pairs=_terms(query)
    return sorted({_token(scope,"w",w) for w in list(lex)[:32]}|
                  {_token(scope,"p",w) for w in list(pairs)[:32]})


def build_passage_route(scope,snapshot,grant,policies,now,allowed):
    if len(allowed)>MAX_SOURCES:
        raise ValueError("source count")
    records=[]
    tokens=set()
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        policy=policies.get(sid,{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,policy=policy,now=now)
        if expiry is None or not source["text"]:
            continue
        text=source["text"]
        for start,end in ranges(text):
            passage=text[start:end]
            keys=_keys(scope,passage)
            if not keys:
                continue
            tokens.update(keys)
            records.append({"source_id":sid,"start":start,"end":end,
                "passage_digest":hashlib.sha256(passage.encode()).hexdigest(),
                "keys":keys,"expires_at":expiry})
    if len(records)>MAX_PASSAGES or len(tokens)>MAX_KEYS:
        raise ValueError("passage routing bound")
    value={"schema":SCHEMA,"snapshot_digest":snapshot["snapshot_digest"],
           "grant_digest":digest(grant),"policy_digest":digest(policies),
           "expires_at":grant["expires_at"],"tokens":sorted(tokens),"records":records}
    return {**value,"digest":digest(value)}


def validate_passage_route(value,snapshot,grant,policies,now):
    if (not isinstance(value,dict) or set(value)!={"schema","snapshot_digest","grant_digest","policy_digest",
            "expires_at","tokens","records","digest"} or value["schema"]!=SCHEMA
            or value["snapshot_digest"]!=snapshot["snapshot_digest"]
            or value["grant_digest"]!=digest(grant) or value["policy_digest"]!=digest(policies)
            or value["expires_at"]!=grant["expires_at"] or value["expires_at"]<=now
            or not isinstance(value["tokens"],list) or len(value["tokens"])>MAX_KEYS
            or not all(hash_identity(x) for x in value["tokens"]) or value["tokens"]!=sorted(set(value["tokens"]))
            or not isinstance(value["records"],list) or len(value["records"])>MAX_PASSAGES
            or value["digest"]!=digest({k:v for k,v in value.items() if k!="digest"})):
        raise ValueError("passage index invalid")
    merged=set()
    ids=set()
    for row in value["records"]:
        if (not isinstance(row,dict) or set(row)!={"source_id","start","end","passage_digest","keys","expires_at"}
                or not hash_identity(row["source_id"]) or row["source_id"] not in snapshot["sources"]
                or type(row["start"]) is not int or type(row["end"]) is not int
                or not 0<=row["start"]<row["end"]<=MAX_TEXT or row["end"]-row["start"]>WIDTH
                or not hash_identity(row["passage_digest"]) or not finite(row["expires_at"])
                or not isinstance(row["keys"],list) or not 1<=len(row["keys"])<=KEYS_PER_PASSAGE
                or not all(hash_identity(k) for k in row["keys"]) or row["keys"]!=sorted(set(row["keys"]))):
            raise ValueError("passage index record invalid")
        key=(row["source_id"],row["start"],row["end"])
        if key in ids:
            raise ValueError("duplicate passage")
        ids.add(key)
        merged.update(row["keys"])
    if merged!=set(value["tokens"]):
        raise ValueError("passage keys inconsistent")
    return value


def rank_passage_offsets(scope,query,snapshot,grant,policies,now,index,allowed):
    """Reparse matched exact spans and independently qualify their authority."""
    validate_passage_route(index,snapshot,grant,policies,now)
    keys=set(query_keys(scope,query))
    wanted=set(words(query))-STOP or set(words(query))
    hits=[]
    for row in index["records"]:
        sid=row["source_id"]
        if sid not in allowed or row["expires_at"]<=now or not keys.intersection(row["keys"]):
            continue
        source=snapshot["sources"][sid]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                              policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
        if expiry is None or expiry!=row["expires_at"] or row["end"]>len(source["text"]):
            continue
        passage=source["text"][row["start"]:row["end"]]
        if hashlib.sha256(passage.encode()).hexdigest()!=row["passage_digest"]:
            raise ValueError("passage witness mismatch")
        counts=Counter(words(passage))
        overlap=wanted.intersection(counts)
        if not overlap:
            continue
        hits.append({"source_id":sid,"start":row["start"],"end":row["end"],
            "passage_digest":row["passage_digest"],"matched_terms":len(overlap),
            "score":round(len(overlap)/max(1,len(wanted))+
                        .05*sum(min(4,counts[t]) for t in overlap)+.02*len(keys.intersection(row["keys"])),6),
            "valid_until":expiry})
    return sorted(hits,key=lambda x:(-x["score"],x["source_id"],x["start"]))[:32]
