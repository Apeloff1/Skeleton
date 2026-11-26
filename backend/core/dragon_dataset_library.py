"""Source-controlled public dataset/discovery target registry.

A target may be a public dump, authenticated API documentation, bibliography
or a directory, not necessarily a downloadable dataset. No credentials, arbitrary
download paths, training approval, or network permission derive from this file.
"""
from functools import lru_cache
import json
import re
from pathlib import Path
from core.dragon_game_corpus import clean,source_url,digest

DATA=Path(__file__).with_name("dragon_public_dataset_library.json")
MAX_TARGETS=4096
ACCESS={"public_download","manual_download","credential_required","policy_review","landing_only","noncommercial_only"}
CADENCE={"daily":86400,"weekly":604800,"monthly":2592000,"historical":None}
ADAPTERS={"steam_csv","steam_json","documentation","directory","wikidata_jsonl","sqlite_metadata","dat_metadata","sql_metadata","csv_metadata","modrinth_json","jsonl_metadata","eve_sde"}
DOMAINS={"games","preservation","mods","game-data","competitive","media","research","development"}
SLUG=re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")

def _no_duplicates(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError("duplicate dataset registry field")
        out[k]=v
    return out

@lru_cache(maxsize=1)
def _library():
    raw=DATA.read_bytes()
    if not 1<=len(raw)<=4*1024*1024:raise ValueError("dataset library bytes")
    doc=json.loads(raw,object_pairs_hook=_no_duplicates)
    if not isinstance(doc,dict) or set(doc)!={"schema","description","targets"} or doc["schema"]!="dragon.dataset-library.v1":
        raise ValueError("dataset library schema")
    targets=doc["targets"]
    if not isinstance(targets,list) or not 1<=len(targets)<=MAX_TARGETS:raise ValueError("dataset library count")
    rows={}
    for item in targets:
        if not isinstance(item,dict) or set(item)!={"id","domain","url","adapter","advertised_rows","access","cadence","notes"}:
            raise ValueError("dataset target record")
        identity=item["id"]
        if not isinstance(identity,str) or not SLUG.fullmatch(identity) or identity in rows:
            raise ValueError("dataset target identity")
        if item["domain"] not in DOMAINS or item["adapter"] not in ADAPTERS or item["access"] not in ACCESS or item["cadence"] not in CADENCE:
            raise ValueError("dataset target classification")
        n=item["advertised_rows"]
        if n is not None and (type(n) is not int or not 1<=n<=10**12):raise ValueError("dataset count hint")
        rows[identity]={**item,"url":source_url(item["url"]),"notes":clean(item["notes"],512),
                        "review_seconds":CADENCE[item["cadence"]],
                        "network_authorized":False,"license_verified":False,
                        "download_verified":False,"training_allowed":False}
    return digest(doc),rows

def target(identity):
    if not isinstance(identity,str):raise ValueError("dataset identity")
    try:return dict(_library()[1][identity])
    except KeyError as exc:raise LookupError("dataset target absent") from exc

def library(*,domain=None,access=None,q=None,after=None,limit=32):
    rev,items=_library()
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("dataset page")
    if domain is not None and domain not in DOMAINS:raise ValueError("dataset domain")
    if access is not None and access not in ACCESS:raise ValueError("dataset access")
    terms=clean(q,256).casefold().split() if q is not None else []
    stamp=digest([rev,domain,access,terms])
    lower=""
    if after is not None:
        if not isinstance(after,str) or not after.startswith(stamp+":") or after[65:] not in items:
            raise ValueError("dataset cursor mismatch")
        lower=after[65:]
    selected=[]
    for k in sorted(items):
        if k<=lower:continue
        row=items[k]
        if domain is not None and row["domain"]!=domain or access is not None and row["access"]!=access:continue
        if any(x not in " ".join(str(v) for v in row.values()).casefold() for x in terms):continue
        selected.append(dict(row))
        if len(selected)>limit:break
    return {"revision":rev,"targets":selected[:limit],"next_cursor":stamp+":"+selected[limit-1]["id"] if len(selected)>limit else None,
            "total_targets":len(items),"network_authorized":False,"license_verified":False,"training_allowed":False}

def census():
    from collections import Counter
    rev,items=_library()
    return {"revision":rev,"targets":len(items),"domains":dict(Counter(r["domain"] for r in items.values())),
            "access":dict(Counter(r["access"] for r in items.values())),
            "implemented_projection_adapters":["steam_csv","steam_json","modrinth_json","normalized_jsonl"],
            "advertised_counts_overlap":True,"network_authorized":False}
