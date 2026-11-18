"""Partitioned deep archive and grant-bound routing index contracts."""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from .dragon_treasury_vault import identity,hash_identity,finite
from .dragon_companion import _lexemes

SHARDS=1024
SLOTS=1024
MAX_EXPEDITIONS=SHARDS*SLOTS
MAX_SOURCES=64
MAX_TERMS=8192
TERMS_PER_SOURCE=128
PAGE=32
SCHEMA="skeleton.dragon.deep-archive.v1"
INDEX="skeleton.dragon.deep-index.v1"


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


def partition(scope,identifier):
    if (not identity(identifier) or set(scope)!={"tenant_id","owner_id"}
            or not all(isinstance(x,str) and 1<=len(x)<=200 for x in scope.values())):
        raise ValueError("invalid partition identity")
    shard=int(digest(identifier)[:8],16)%SHARDS
    return shard,digest({"scope":scope,"partition":shard,"kind":"dragon-deep"})


def marker(scope,identifier,operation,request_digest,witness,now):
    shard,key=partition(scope,identifier)
    return validate_marker({"schema":SCHEMA,"partition":shard,"quota_id":key,
        "operation":operation,"request_digest":request_digest,"snapshot_digest":witness,
        "accepted_at":now,"state":"pending","released":False,"retry_at":now},scope,identifier)


def validate_marker(value,scope,identifier):
    if (not isinstance(value,dict) or set(value)!={"schema","partition","quota_id","operation",
            "request_digest","snapshot_digest","accepted_at","state","released","retry_at"}
            or value["schema"]!=SCHEMA or type(value["partition"]) is not int
            or (value["partition"],value["quota_id"])!=partition(scope,identifier)
            or not all(hash_identity(value[k]) for k in ("operation","request_digest","snapshot_digest"))
            or not finite(value["accepted_at"]) or not finite(value["retry_at"])
            or value["retry_at"]<value["accepted_at"] or value["state"] not in ("pending","archived")
            or type(value["released"]) is not bool or value["state"]=="pending" and value["released"]):
        raise ValueError("invalid deep custody marker")
    return value


def public_marker(m):
    return {k:m[k] for k in ("partition","snapshot_digest","accepted_at","state","released")}


def token(scope,word):
    return digest({"scope":scope,"word":word,"domain":"deep-route-v1"})


def query_terms(scope,query):
    if not isinstance(query,str) or not 1<=len(query)<=512:
        raise ValueError("invalid query")
    terms=tuple(dict.fromkeys(_lexemes(query)))[:32]
    if not terms:
        raise ValueError("query has no lexical terms")
    return terms,[token(scope,t) for t in terms]


def build_index(scope,snapshot,grant,policies,now,allowed=None):
    """Bounded term routing, not a full global relevance index."""
    from .dragon_archive_grant import archive_expiry,validate_grant
    validate_grant(grant)
    sources=snapshot["sources"]
    if len(sources)>MAX_SOURCES or grant["snapshot_digest"]!=snapshot["snapshot_digest"]:
        raise ValueError("source bound")
    tokens=set()
    count=truncated=0
    for sid in sorted(sources if allowed is None else allowed):
        source=sources[sid]
        if archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                policy=policies.get(sid,{"enabled":True,"version":0}),now=now) is None:
            continue
        words=Counter(_lexemes(source["title"]+" "+source["text"]))
        title=list(dict.fromkeys(_lexemes(source["title"])))
        # Source-fair budget and deterministic lexical ranking.
        terms=list(dict.fromkeys(title+sorted(words,key=lambda x:(-words[x],x))))
        truncated+=int(len(terms)>TERMS_PER_SOURCE)
        tokens.update(token(scope,t) for t in terms[:TERMS_PER_SOURCE])
        count+=1
    body={"schema":INDEX,"snapshot_digest":snapshot["snapshot_digest"],"grant_digest":digest(grant),
          "policy_digest":digest(policies),"expires_at":grant["expires_at"],"tokens":sorted(tokens),
          "eligible_sources":count,"truncated_sources":truncated}
    if len(tokens)>MAX_TERMS:
        raise ValueError("routing bound")
    return {**body,"digest":digest(body)}


def validate_index(value,snapshot,grant,policies,now):
    if (not isinstance(value,dict) or set(value)!={"schema","snapshot_digest","grant_digest","policy_digest",
            "expires_at","tokens","eligible_sources","truncated_sources","digest"}
            or value["schema"]!=INDEX or value["snapshot_digest"]!=snapshot["snapshot_digest"]
            or value["grant_digest"]!=digest(grant) or value["policy_digest"]!=digest(policies)
            or value["expires_at"]!=grant["expires_at"] or value["expires_at"]<=now
            or not isinstance(value["tokens"],list) or len(value["tokens"])>MAX_TERMS
            or not all(hash_identity(x) for x in value["tokens"])
            or value["tokens"]!=sorted(set(value["tokens"]))
            or type(value["eligible_sources"]) is not int or not 0<=value["eligible_sources"]<=MAX_SOURCES
            or type(value["truncated_sources"]) is not int or not 0<=value["truncated_sources"]<=value["eligible_sources"]
            or value["digest"]!=digest({k:v for k,v in value.items() if k!="digest"})):
        raise ValueError("stale routing index")
    return value


def cursor(scope,query,after):
    return digest({"scope":scope,"query":query})+":"+after


def decode_cursor(scope,query,value):
    if value is None:
        return None
    if not isinstance(value,str) or len(value)>193:
        raise ValueError("invalid cursor")
    _,sep,after=value.partition(":")
    if not sep or not identity(after) or value!=cursor(scope,query,after):
        raise ValueError("cursor mismatch")
    return after


def search_options(*,partition_id=None,order="relevance",match="any"):
    if (partition_id is not None and (type(partition_id) is not int or not 0<=partition_id<SHARDS)
            or order not in {"relevance","archive_newest","archive_oldest"}
            or match not in {"any","all"}):
        raise ValueError("invalid deep archive search options")
    return {"partition":partition_id,"order":order,"match":match}


def search_cursor(scope,query,options,*,identifier,accepted_at=None):
    if not identity(identifier):
        raise ValueError("invalid archive search cursor identity")
    if options==search_options():
        return cursor(scope,query,identifier)
    prefix=digest({"scope":scope,"query":query,"options":options,"schema":"deep-search-v2"})
    if options["order"]=="relevance":
        return prefix+":"+identifier
    if not finite(accepted_at):
        raise ValueError("invalid archive search cursor time")
    # float.hex preserves the exact sort field rather than a rounded display
    # timestamp. Parsing never supplies authority; all results are live fenced.
    return prefix+":"+float(accepted_at).hex()+":"+identifier


def search_boundary(scope,query,options,value):
    if value is None:
        return None
    if options==search_options():
        return (decode_cursor(scope,query,value),None)
    if not isinstance(value,str) or len(value)>240:
        raise ValueError("invalid archive search cursor")
    parts=value.split(":")
    if options["order"]=="relevance":
        if len(parts)!=2:
            raise ValueError("invalid archive cursor geometry")
        after,accepted=parts[1],None
    else:
        if len(parts)!=3:
            raise ValueError("invalid temporal cursor geometry")
        after=parts[2]
        try:
            accepted=float.fromhex(parts[1])
        except (ValueError,OverflowError) as exc:
            raise ValueError("invalid temporal cursor timestamp") from exc
    if value!=search_cursor(scope,query,options,identifier=after,accepted_at=accepted):
        raise ValueError("archive query, filter or sort changed")
    return after,accepted


def search_predicate(scope,tokens,now,options,boundary):
    if not tokens or len(tokens)>32 or not all(hash_identity(x) for x in tokens):
        raise ValueError("invalid indexed query terms")
    predicate={**scope,"status":{"$in":["budget_exhausted","completed"]},
        "deep_archive.released":True,"deep_index.expires_at":{"$gt":now},
        "deep_index.tokens":{"$all" if options["match"]=="all" else "$in":tokens}}
    if options["partition"] is not None:
        predicate["deep_archive.partition"]=options["partition"]
    order=options["order"]
    if order=="relevance":
        sort=[("_id",1)]
        if boundary:
            predicate["_id"]={"$gt":boundary[0]}
    else:
        direction=-1 if order=="archive_newest" else 1
        compare="$lt" if direction==-1 else "$gt"
        sort=[("deep_archive.accepted_at",direction),("_id",1)]
        if boundary:
            after,accepted=boundary
            predicate["$or"]=[{"deep_archive.accepted_at":{compare:accepted}},
                {"deep_archive.accepted_at":accepted,"_id":{"$gt":after}}]
    return predicate,sort


def rank_exact(scope,snapshot,grant,policies,now,terms,allowed,*,require_all=False):
    """Exact source-level token coverage. No raw text in candidate metadata."""
    from .dragon_archive_grant import archive_expiry
    wanted=set(terms)
    result=[]
    for sid in sorted(allowed):
        s=snapshot["sources"][sid]
        policy=policies.get(sid,{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=s,policy=policy,now=now)
        if expiry is None:
            continue
        counts=Counter(_lexemes(s["title"]+" "+s["text"]))
        overlap=wanted.intersection(counts)
        if overlap and (not require_all or overlap==wanted):
            result.append({"source_id":sid,"preserved_text_hash":s["preserved_text_hash"],
                "captured_at":s["fetched_at"],"valid_until":expiry,"matched_terms":len(overlap),
                "term_frequency":sum(min(8,counts[t]) for t in overlap),"policy_version":policy["version"]})
    return result
