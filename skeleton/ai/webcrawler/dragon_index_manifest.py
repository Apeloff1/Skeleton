"""Materialized per-session treasury posting segments.

The segment is a disposable, bounded derivative of authorized text, stored in
the same session row as the capture. It is not an authority, a backup, a new
source grant, or anonymous data. Hashes of lexical tokens remain sensitive
derived data. A policy revision, grant revocation, parser change or checkpoint
mismatch invalidates the segment; a read always checks source authority first.
"""
from __future__ import annotations

import base64
import binascii
from collections import Counter
import hashlib
import json
import math
import re
import zlib

from .dragon_treasury import PARSER, MAX_TERMS, MAX_SECTIONS, ParsedVersion, materialized_digest, parse_retained_text

SCHEMA="skeleton.dragon.index-manifest.v1"
MAX_RAW=2*1024*1024
MAX_COMPRESSED=1024*1024
MAX_SOURCES=64
MAX_SIGNATURE=96
_HEX=re.compile(r"[a-f0-9]{64}\Z")
_TERM=re.compile(r"[a-f0-9]{32}\Z")


def _sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def _json(value)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")


def _hex(value)->bool:
    return isinstance(value,str) and _HEX.fullmatch(value) is not None


def _serialize(parsed:ParsedVersion)->dict:
    return {"terms":sorted(parsed.terms.items()),"sections":list(parsed.section_hashes),
            "signature":[format(n,"016x") for n in sorted(parsed.signature)],
            "numbers":list(parsed.numbers),"projection_digest":parsed.digest}


def _deserialize(row:dict,text_hash:str)->ParsedVersion:
    if (not isinstance(row,dict) or set(row)!={"terms","sections","signature","numbers","projection_digest"}
            or not _hex(row["projection_digest"])):
        raise ValueError("invalid index posting record")
    terms,sections,signature,numbers=(row[k] for k in ("terms","sections","signature","numbers"))
    if (not isinstance(terms,list) or len(terms)>MAX_TERMS
            or not isinstance(sections,list) or len(sections)>MAX_SECTIONS or not all(_hex(x) for x in sections)
            or not isinstance(signature,list) or len(signature)>MAX_SIGNATURE
            or not all(isinstance(x,str) and re.fullmatch(r"[0-9a-f]{16}",x) for x in signature)
            or signature!=sorted(set(signature))
            or not isinstance(numbers,list) or len(numbers)>MAX_TERMS
            or not all(isinstance(x,str) and _TERM.fullmatch(x) for x in numbers)):
        raise ValueError("invalid posting geometry")
    counts=Counter()
    previous=""
    for pair in terms:
        if (not isinstance(pair,list) or len(pair)!=2 or not isinstance(pair[0],str)
                or not _TERM.fullmatch(pair[0]) or pair[0]<=previous
                or type(pair[1]) is not int or not 1<=pair[1]<=MAX_TERMS):
            raise ValueError("invalid term frequency")
        counts[pair[0]]=pair[1]
        previous=pair[0]
    if sum(counts.values())>MAX_TERMS:
        raise ValueError("term budget exceeded")
    values=frozenset(int(x,16) for x in signature)
    digest=materialized_digest(text_hash=text_hash,terms=counts,sections=tuple(sections),
                               signature=values,numbers=tuple(numbers))
    if digest!=row["projection_digest"]:
        raise ValueError("posting projection digest mismatch")
    return ParsedVersion(counts,tuple(sections),values,tuple(numbers),digest)


def build_manifest(snapshot:dict,grant:dict,*,now:float,policies:dict|None=None)->dict:
    """Materialize newest authorized grant members without renewing the grant.

    Maintenance supplies current policies; a policy change only subtracts
    members. The original grant digest and expiry remain immutable.
    """
    from .dragon_archive_grant import validate_grant, archive_expiry
    validate_grant(grant)
    if (snapshot.get("snapshot_digest")!=grant["snapshot_digest"]
            or type(now) not in (int,float) or not math.isfinite(now)
            or not grant["issued_at"]<=now<grant["expires_at"]):
        raise ValueError("manifest not bound to active grant")
    if not set(grant["members"])<=set(snapshot["sources"]):
        raise ValueError("manifest grant contains absent source")
    ordered=sorted(grant["members"],key=lambda sid:(-snapshot["sources"][sid]["fetched_at"],sid))
    entries={}
    raw_size=2
    for sid in ordered:
        source=snapshot["sources"][sid]
        member=grant["members"][sid]
        if policies is not None:
            policy=policies.get(sid,{"version":0,"enabled":True})
            if archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],
                              source=source,policy=policy,now=now) is None:
                continue
        text=source["text"]
        actual=_sha(text.encode("utf-8"))
        if actual!=member["text_digest"] or actual!=source["preserved_text_hash"]:
            raise ValueError("manifest source changed")
        entry={"text_digest":actual,"policy_version":member["policy_version"],
               "posting":_serialize(parse_retained_text(text))}
        # Exact canonical JSON byte accounting, not repeated compression
        # of every accumulated prefix.
        cost=len(_json(sid))+1+len(_json(entry))+int(bool(entries))
        if raw_size+cost>MAX_RAW:
            continue
        entries[sid]=entry
        raw_size+=cost
    raw=_json(entries)
    compressed=zlib.compress(raw,level=1)
    if len(compressed)>MAX_COMPRESSED:
        # Keep an actually fitting newest prefix. Compression need not be
        # monotone, so do not claim optimal packing.
        items=list(entries.items())
        low,high=0,len(items)
        best_raw,best_blob=_json({}),zlib.compress(_json({}),level=1)
        while high-low>1:
            mid=(low+high)//2
            candidate=_json(dict(items[:mid]))
            blob=zlib.compress(candidate,level=1)
            if len(blob)<=MAX_COMPRESSED:
                low=mid
                best_raw,best_blob=candidate,blob
            else:
                high=mid
        entries=dict(items[:low])
        raw,compressed=best_raw,best_blob
    if len(raw)>MAX_RAW or len(compressed)>MAX_COMPRESSED:
        raise ValueError("index capacity cannot fit empty segment")
    return {"schema":SCHEMA,"parser":PARSER,"snapshot_digest":grant["snapshot_digest"],
            "grant_digest":_sha(_json(grant)),"created_at":now,"expires_at":grant["expires_at"],
            "source_count":len(entries),"eligible_count":len(ordered),
            "raw_bytes":len(raw),"raw_sha256":_sha(raw),
            "segment":base64.b64encode(compressed).decode("ascii")}


def load_manifest(manifest:object,grant:dict|None,*,snapshot_digest:str,now:float)->dict[str,tuple[dict,ParsedVersion]]:
    """Validate and decode; return no entries on expired or outdated custody."""
    from .dragon_archive_grant import validate_grant
    if manifest is None or grant is None:
        return {}
    validate_grant(grant)
    if (not isinstance(manifest,dict)
            or set(manifest)!={"schema","parser","snapshot_digest","grant_digest","created_at","expires_at",
                              "source_count","eligible_count","raw_bytes","raw_sha256","segment"}
            or manifest["schema"]!=SCHEMA):
        raise ValueError("invalid index manifest schema")
    if (manifest["parser"]!=PARSER or manifest["snapshot_digest"]!=snapshot_digest
            or grant["snapshot_digest"]!=snapshot_digest or manifest["grant_digest"]!=_sha(_json(grant))
            or manifest["expires_at"]!=grant["expires_at"] or not grant["issued_at"]<=now<grant["expires_at"]):
        return {}
    if (type(manifest["created_at"]) not in (float,int) or not grant["issued_at"]<=manifest["created_at"]<=now
            or type(manifest["source_count"]) is not int or type(manifest["eligible_count"]) is not int
            or not 0<=manifest["source_count"]<=manifest["eligible_count"]==len(grant["members"])<=MAX_SOURCES
            or type(manifest["raw_bytes"]) is not int or not 2<=manifest["raw_bytes"]<=MAX_RAW
            or not _hex(manifest["raw_sha256"]) or not isinstance(manifest["segment"],str)
            or len(manifest["segment"])>((MAX_COMPRESSED+2)//3)*4):
        raise ValueError("invalid index manifest bound")
    try:
        blob=base64.b64decode(manifest["segment"],validate=True)
        if len(blob)>MAX_COMPRESSED:
            raise ValueError("compressed posting bound")
        decoder=zlib.decompressobj()
        raw=decoder.decompress(blob,manifest["raw_bytes"]+1)
        if (len(raw)!=manifest["raw_bytes"] or not decoder.eof or decoder.unconsumed_tail
                or decoder.unused_data or _sha(raw)!=manifest["raw_sha256"]):
            raise ValueError("invalid bounded posting segment")
        entries=json.loads(raw.decode("ascii"))
    except (ValueError,UnicodeError,binascii.Error,zlib.error,RecursionError) as exc:
        raise ValueError("index segment integrity failure") from exc
    if (not isinstance(entries,dict) or len(entries)!=manifest["source_count"]
            or _json(entries)!=raw):
        raise ValueError("non-canonical posting segment")
    result={}
    for sid,entry in entries.items():
        if not _hex(sid) or sid not in grant["members"] or not isinstance(entry,dict):
            raise ValueError("index segment contains an ungranted source")
        member=grant["members"][sid]
        if (set(entry)!={"text_digest","policy_version","posting"}
                or entry["text_digest"]!=member["text_digest"]
                or type(entry["policy_version"]) is not int
                or entry["policy_version"]!=member["policy_version"]):
            raise ValueError("index source policy binding mismatch")
        result[sid]=(member,_deserialize(entry["posting"],member["text_digest"]))
    return result


def usable_posting(entries:dict,source:dict,policy:dict)->ParsedVersion|None:
    """Caller already checked current/archival use with live permission."""
    item=entries.get(source["source_id"])
    if item is None:
        return None
    member,posting=item
    if (not policy["enabled"] or policy["version"]!=member["policy_version"]
            or source["preserved_text_hash"]!=member["text_digest"]
            or _sha(source["text"].encode("utf-8"))!=member["text_digest"]):
        return None
    return posting


def same_manifest_projection(previous:object, expected:dict, grant:dict, *, now:float)->bool:
    """Compare actual decoded bytes with an independently derived projection."""
    if not isinstance(previous,dict):
        return False
    try:
        loaded=load_manifest(previous,grant,snapshot_digest=grant["snapshot_digest"],now=now)
    except (ValueError,TypeError,KeyError,RecursionError):
        return False
    return (len(loaded)==expected["source_count"]
            and all(previous.get(key)==expected[key] for key in
                    ("schema","parser","snapshot_digest","grant_digest","expires_at",
                     "source_count","eligible_count","raw_bytes","raw_sha256")))


def manifest_matches_grant(manifest:object,grant:dict,*,snapshot_digest:str)->bool:
    """Header identity check only; decoding and per-member checks still required."""
    return (isinstance(manifest,dict) and manifest.get("schema")==SCHEMA
            and manifest.get("parser")==PARSER
            and manifest.get("snapshot_digest")==snapshot_digest==grant["snapshot_digest"]
            and manifest.get("grant_digest")==_sha(_json(grant))
            and manifest.get("expires_at")==grant["expires_at"])
