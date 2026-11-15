"""Request-local HOAG/Wiki crawler evidence pointers.

Never insert crawler text into the process-wide galaxy shelf, derive rules,
or grant historical context authority. The caller must first perform the
canonical owner-scoped live retrieval. The result records routing provenance
only; canonical chat dependencies remain authoritative.
"""
from __future__ import annotations

from datetime import datetime
import math
from .dragon_treasury_vault import identity,hash_identity

SCHEMA="skeleton.dragon.hoag-wiki-catalog.v1"


def _stamp(value):
    if isinstance(value,str):
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        if parsed.tzinfo is None:raise ValueError("naive evidence deadline")
        value=parsed.timestamp()
    if type(value) not in (float,int) or not math.isfinite(value) or value<0:
        raise ValueError("invalid evidence deadline")
    return value


def _base(session,source,expiry,now):
    if not identity(session) or not hash_identity(source) or _stamp(expiry)<=now:
        raise ValueError("invalid or expired crawler citation")
    return {"session_id":session,"source_id":source,"citation":"dragon-crawl://"+session+"/"+source,
            "valid_until":_stamp(expiry),"review_state":"unreviewed_external_evidence","stored_prose":0}


def current_catalog(projection,*,now):
    docs,refs=projection["documents"],projection["references"]
    if not isinstance(docs,list) or not isinstance(refs,list) or len(docs)!=len(refs) or len(refs)>8:
        raise ValueError("invalid canonical current projection")
    records=[]
    for document,reference in zip(docs,refs):
        source=reference["source_id"]
        session=reference["session_id"]
        row=_base(session,source,document["valid_until"],now)
        if (document["source_id"]!=source or document["source_ref"]!=row["citation"]
                or document["authority"]!="external_evidence_only"
                or document.get("source_use_version")!=reference.get("source_use_version")
                or not hash_identity(document["content_digest"])):
            raise ValueError("current citation custody mismatch")
        records.append({**row,"plane":"current","passage_digest":document["content_digest"],
                        "source_use_version":reference.get("source_use_version",0),
                        "model_context_authorized":True})
    return envelope("current",records,now,None)


def history_catalog(projection,*,now):
    if (projection["schema"]!="skeleton.dragon.deep-search.v1" or projection["history_only"] is not True
            or projection["source_text_returned"] is not False or projection["model_context_permission"] is not False
            or projection["wiki_approval"] is not False or not isinstance(projection["matches"],list)
            or len(projection["matches"])>32):
        raise ValueError("historical authority differs")
    rows=[]
    for hit in projection["matches"]:
        row=_base(hit["session_id"],hit["source_id"],hit["valid_until"],now)
        if (type(hit["version"]) is not int or hit["version"]<1 or not hash_identity(hit["snapshot_digest"])
                or not hash_identity(hit["preserved_text_hash"])
                or type(hit["matched_terms"]) is not int or not 1<=hit["matched_terms"]<=32
                or type(hit["policy_version"]) is not int or hit["policy_version"]<0):
            raise ValueError("historical citation custody differs")
        rows.append({**row,"plane":"historic","version":hit["version"],"snapshot_digest":hit["snapshot_digest"],
                     "preserved_text_hash":hit["preserved_text_hash"],"source_use_version":hit["policy_version"],
                     "matched_terms":hit["matched_terms"],"captured_at":_stamp(hit["captured_at"]),
                     **({"archived_at":_stamp(hit["archived_at"]),"partition":hit["partition"]}
                        if "archived_at" in hit and type(hit.get("partition")) is int and 0<=hit["partition"]<1024 else {}),
                     "model_context_authorized":False})
    from .dragon_archive_scale import search_options
    options=search_options(**{"partition_id":projection.get("search_options",{}).get("partition"),
        "order":projection.get("search_options",{}).get("order","relevance"),
        "match":projection.get("search_options",{}).get("match","any")})
    return {**envelope("historic",rows,now,projection["next_cursor"]),"search_options":options}


def envelope(mode,rows,now,cursor):
    if len({r["citation"] for r in rows})!=len(rows):
        raise ValueError("duplicate crawler citation")
    return {"schema":SCHEMA,"nucleus":"wiki","mode":mode,"as_of_unix":now,
            "valid_until":min([now+60,*[r["valid_until"] for r in rows]]),
            "pointers":rows,"next_cursor":cursor,"request_local":True,
            "stored_prose":0,"knowledge_promoted":False,"network_executed":False}


def validate_current_binding(projection,*,now):
    """Ensure the exact request-local Wiki receipt matches the canonical chat evidence.

    The receipt has no persistent authority. Existing source dependency
    revalidation remains required before inference, resume and reuse.
    """
    receipt=projection.get("hoag_wiki")
    if not isinstance(receipt,dict) or receipt.get("schema")!=SCHEMA or receipt.get("mode")!="current":
        raise ValueError("missing current Wiki provenance")
    issued=_stamp(receipt.get("as_of_unix"))
    if issued>now or _stamp(receipt.get("valid_until"))<=now:
        raise ValueError("Wiki provenance expired")
    expected=current_catalog(projection,now=issued)
    if expected!=receipt:
        raise ValueError("Wiki provenance differs from live crawler projection")
    if any(row["valid_until"]<=now for row in expected["pointers"]):
        raise ValueError("crawler evidence expired")
    return {row["citation"]:row["passage_digest"] for row in expected["pointers"]}
