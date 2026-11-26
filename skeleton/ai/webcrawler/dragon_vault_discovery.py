"""Query-guided cold-custody chamber discovery.

Only caller-authorized retained text is scanned. The result is a local
query-coverage advisory, not full-corpus BM25, independent corroboration,
a current index, or permission to fetch. Text and tokens never leave it.
"""
from __future__ import annotations

import hashlib
import json
import re
import math

from .dragon_companion import _lexemes
from .dragon_treasury_vault import identity,hash_identity,MAX_VAULT_SESSIONS

PAGE=8
MAX_SOURCES=64
MAX_TEXT_BYTES=24000
MAX_QUERY_TERMS=32
_CURSOR=re.compile(r"([a-f0-9]{64}):([0-9]{1,4})\Z")


def query_terms(query):
    if not isinstance(query,str) or not 1<=len(query)<=256 or len(query.encode("utf-8"))>1024:
        raise ValueError("invalid chamber discovery query")
    terms=tuple(dict.fromkeys(_lexemes(query)))[:MAX_QUERY_TERMS]
    if not terms:
        raise ValueError("chamber search needs lexical terms")
    return terms


def catalogue_signature(rows,*,now):
    """Bind cursors to all bounded owner rows and live grant-expiry states."""
    if (not isinstance(rows,list) or len(rows)>MAX_VAULT_SESSIONS
            or type(now) not in (int,float) or not math.isfinite(now) or now<0):
        raise ValueError("chamber catalogue exceeds bound")
    clean=[]
    previous=None
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("invalid chamber catalogue row")
        sid=row.get("_id")
        version=row.get("version")
        if (not identity(sid) or type(version) is not int or version<1
                or previous is not None and sid>=previous):
            raise ValueError("invalid chamber catalogue ordering")
        previous=sid
        grant=row.get("archive_grant")
        if grant is not None and not isinstance(grant,dict):
            raise ValueError("invalid chamber grant metadata")
        grant=grant or {}
        issued,expiry=grant.get("issued_at"),grant.get("expires_at")
        active=(type(issued) in (float,int) and type(expiry) in (float,int)
                and math.isfinite(issued) and math.isfinite(expiry) and issued<=now<expiry)
        clean.append((sid,version,expiry if active else None))
    return tuple(clean)


def digest_scope(scope,signature,terms):
    raw=json.dumps({"scope":scope,"catalogue":signature,"query":terms,"schema":"vault-discovery-v1"},
                   sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def page_offset(cursor,scope_digest,size):
    if cursor is None:
        return 0
    match=_CURSOR.fullmatch(cursor) if isinstance(cursor,str) else None
    if (match is None or match[1]!=scope_digest or str(int(match[2]))!=match[2]
            or not 0<int(match[2])<size or int(match[2])%PAGE):
        raise ValueError("chamber discovery cursor no longer matches")
    return int(match[2])


def summarize_sources(sources,terms):
    """Coverage of exact admitted source payloads, deduplicated by text digest."""
    if not isinstance(sources,list) or len(sources)>MAX_SOURCES or not terms:
        raise ValueError("invalid admitted chamber source set")
    wanted=set(terms)
    matched=set()
    distinct={}
    best=0
    count=0
    size=0
    for source in sources:
        text=source["text"]
        key=source["preserved_text_hash"]
        if (not isinstance(text,str) or not hash_identity(key)
                or len(text.encode("utf-8"))>MAX_TEXT_BYTES
                or hashlib.sha256(text.encode("utf-8")).hexdigest()!=key):
            raise ValueError("retained chamber bytes mismatch")
        encoded=text.encode("utf-8")
        size+=len(encoded)
        if size>MAX_SOURCES*MAX_TEXT_BYTES:
            raise ValueError("chamber scan byte bound exceeded")
        if key not in distinct:
            distinct[key]=wanted.intersection(_lexemes(text))
        hits=distinct[key]
        if hits:
            count+=1
            best=max(best,len(hits))
            matched.update(hits)
    return {"eligible_sources":len(sources),"matched_sources":count,
            "distinct_matching_payloads":sum(bool(x) for x in distinct.values()),
            "matched_terms":len(matched),"best_source_terms":best,"scanned_bytes":size}


def order_matches(matches):
    return sorted(matches,key=lambda r:(-r["matched_terms"],-r["best_source_terms"],
                    -r["distinct_matching_payloads"],r["session_id"]))
