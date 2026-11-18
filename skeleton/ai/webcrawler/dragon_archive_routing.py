"""Owner-scoped inverted routing for retained archive segments.

Search keys are derived data, never a permission or text authority. Store
one bounded deterministic routing segment alongside the original grant and
posting manifest; no second copy of source prose. Database multikey routing
avoids a full snapshot scan for each query. Exact source bytes and rights
are requalified before exposing any candidate.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from .dragon_index_manifest import load_manifest
from .dragon_companion import _lexemes
from .dragon_treasury import term_key
from .dragon_treasury_vault import hash_identity,identity

SCHEMA="skeleton.dragon.archive-routing.v1"
MAX_KEYS=4096
MAX_QUERY=32
MAX_CANDIDATES=64
MAX_RECHECK=16
MAX_RESULTS=32


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


def _scope(scope):
    if (not isinstance(scope,dict) or set(scope)!={"tenant_id","owner_id"}
            or any(not isinstance(v,str) or not 1<=len(v)<=256 for v in scope.values())):
        raise ValueError("invalid archive routing scope")
    return _digest(scope)


def scoped_key(scope,token_hash):
    # Domain separation prevents cross-owner equality, not dictionary attacks.
    return hashlib.sha256(("dragon-archive-v1:"+_scope(scope)+":"+token_hash).encode("ascii")).hexdigest()


def query_keys(scope,query):
    if not isinstance(query,str) or not 1<=len(query)<=256 or len(query.encode("utf8"))>1024:
        raise ValueError("invalid archive query")
    words=tuple(dict.fromkeys(_lexemes(query)))[:MAX_QUERY]
    if not words: raise ValueError("archive query needs lexical terms")
    return tuple(sorted({scoped_key(scope,term_key(word)) for word in words}))


def build_routing(scope,manifest,grant,*,now):
    if manifest is None or grant is None:
        return None
    entries=load_manifest(manifest,grant,snapshot_digest=grant["snapshot_digest"],now=now)
    if len(entries)!=manifest["source_count"]:
        raise ValueError("routing requires live decoded posting segment")
    df=Counter()
    tf=Counter()
    for _,posting in entries.values():
        df.update(posting.terms.keys())
        tf.update(posting.terms)
    # Rare terms first, repeated occurrence next, deterministic tie break.
    ranked=sorted(df,key=lambda key:(df[key],-tf[key],key))
    keys=sorted(scoped_key(scope,key) for key in ranked[:MAX_KEYS])
    core={"schema":SCHEMA,"scope_digest":_scope(scope),"snapshot_digest":grant["snapshot_digest"],
          "grant_digest":manifest["grant_digest"],"manifest_digest":manifest["raw_sha256"],
          "expires_at":grant["expires_at"],"source_count":len(entries),"eligible_count":manifest["eligible_count"],
          "distinct_terms":len(ranked),"keys":keys}
    return {**core,"digest":_digest(core)}


def validate_routing(value,scope,manifest,grant,*,now):
    if not isinstance(value,dict):
        return False
    try:
        expected=build_routing(scope,manifest,grant,now=now)
        return expected is not None and expected==value
    except (ValueError,TypeError,KeyError,RecursionError):
        return False


def candidate_pipeline(scope,keys,now):
    if not keys or len(keys)>MAX_QUERY or not all(hash_identity(k) for k in keys) or not math.isfinite(now):
        raise ValueError("invalid routing candidate request")
    return [
        {"$match":{**scope,"status":{"$in":["completed","budget_exhausted"]},
             "treasury_vault.state":"vaulted","deep_archive.released":{"$ne":True},"treasury_archive_route.schema":SCHEMA,
             "treasury_archive_route.expires_at":{"$gt":now},"treasury_archive_route.keys":{"$in":list(keys)}}},
        {"$project":{"_id":1,"version":1,"digest":"$treasury_archive_route.digest",
             "overlap":{"$size":{"$setIntersection":["$treasury_archive_route.keys",list(keys)]}}}},
        {"$sort":{"overlap":-1,"_id":1}},
        {"$limit":MAX_CANDIDATES+1},
    ]


def pointer(session,source,version,score,*,expiry):
    if not identity(session) or not hash_identity(source) or type(version) is not int or version<1:
        raise ValueError("invalid archive pointer")
    if type(score) is not int or score<1 or type(expiry) not in (float,int) or not math.isfinite(expiry):
        raise ValueError("invalid archive pointer weight")
    return {"session_id":session,"source_id":source,"version":version,"score":score,
            "valid_until":expiry,"citation":"dragon-crawl://"+session+"/"+source,
            "plane":"historic","review_state":"unreviewed_external_evidence",
            "model_context_authorized":False,"stored_prose":0}
