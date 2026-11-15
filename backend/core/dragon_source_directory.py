"""Curated public discovery lead federation.

A directory is not a game, a crawl grant, a license, a live endpoint receipt,
a reviewed source, or a provider integration. Bind selected locators to an
explicit owner game identity or to a named game/franchise profile, then enqueue
only catalogue observations via the existing durable release import path.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from core.dragon_game_corpus import GameCorpus,clean,digest,game_id,key,source_url,_id
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES,view_mode
from core.dragon_hoarder_bulk import owner_key
from core.dragon_release_discovery import PROVIDERS
from core.dragon_release_queue import ReleaseQueue

MAX_ROWS=20000
MAX_GROUPS=256
MAX_PAGE=100
MAX_SELECT=64
SLUG=re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
DATA=Path(__file__).with_name("dragon_source_directory.json")
# Preserve the original two design-profile identities. Other franchise
# profiles are deliberately separate from their individual instalments.
PRESET_IDENTITIES={
    "eve":("developer","eve-online","EVE Online"),
    "gta-vi":("publisher","gta-vi","Grand Theft Auto VI"),
    "gta-v":("publisher","grand-theft-auto-v","Grand Theft Auto V"),
    "warcraft":("publisher","world-of-warcraft","World of Warcraft"),
    "fallout":("independent","fallout-franchise","Fallout franchise"),
    "mario":("independent","super-mario-franchise","Super Mario franchise"),
}
FRANCHISE={"fallout","mario"}


def _slug(value):
    if not isinstance(value,str) or not SLUG.fullmatch(value):raise ValueError("directory scope")
    return value


def _pairs(items):
    result={}
    for k,v in items:
        if k in result:raise ValueError("directory duplicate field")
        result[k]=v
    return result


@lru_cache(maxsize=1)
def _load():
    raw=DATA.read_bytes()
    if not 1<=len(raw)<=8*1024*1024:raise ValueError("directory byte bound")
    document=json.loads(raw,object_pairs_hook=_pairs)
    if not isinstance(document,dict) or set(document)!={"schema","description","groups"} or document["schema"]!="dragon.source-directory.v1":
        raise ValueError("directory schema")
    groups=document["groups"]
    if not isinstance(groups,list) or not 1<=len(groups)<=MAX_GROUPS:raise ValueError("directory group quota")
    index={};rows={};ordered=[]
    for g in groups:
        if not isinstance(g,dict) or set(g)!={"id","domain","game","title","leads"}:raise ValueError("directory group schema")
        gid=_slug(g["id"]);domain=_slug(g["domain"])
        if gid in index:raise ValueError("duplicate group")
        ident=PRESET_IDENTITIES.get(gid)
        if (g["game"] is None)!=(g["title"] is None) or (ident is None)!=(g["game"] is None):
            raise ValueError("directory preset identity")
        if ident is not None:
            key(g["game"]);clean(g["title"],256)
        if not isinstance(g["leads"],list) or not g["leads"]:raise ValueError("directory leads")
        local=set();families={}
        for lead in g["leads"]:
            if not isinstance(lead,dict) or set(lead)!={"label","url","provider","kind"}:raise ValueError("directory lead schema")
            label=clean(lead["label"],160);url=source_url(lead["url"]);kind=lead["kind"];provider=lead["provider"]
            if provider not in PROVIDERS or kind not in SOURCE_CLASSES or url in local:raise ValueError("invalid or duplicate lead")
            local.add(url)
            family=SOURCE_CLASSES[kind].family
            families[family]=families.get(family,0)+1
            lid=digest([gid,url,provider,kind])
            if lid in rows:raise ValueError("duplicate lead identity")
            row={"lead_id":lid,"group":gid,"domain":domain,"label":label,"url":url,
                 "provider":provider,"kind":kind,"family":family,"view_mode":view_mode(kind),
                 "scope":"franchise" if gid in FRANCHISE else "game" if ident else "multi_game_directory",
                 "verified":False,"network_authorized":False}
            rows[lid]=row;ordered.append(lid)
            if len(rows)>MAX_ROWS:raise ValueError("directory route quota")
        index[gid]={"id":gid,"domain":domain,"title":ident[2] if ident else None,
                    "scope":"franchise" if gid in FRANCHISE else "game" if ident else "multi_game_directory",
                    "leads":len(local),"families":families,
                    "preset_game_id":game_id(ident[0],ident[1]) if ident else None}
    return hashlib.sha256(raw).hexdigest(),index,rows,tuple(sorted(ordered))


def summary():
    revision,groups,rows,_=_load()
    return {"revision":revision,"groups":[dict(groups[k]) for k in sorted(groups)],
            "total_leads":len(rows),"distinct_origins":len({r["url"].split("/")[2] for r in rows.values()}),
            "source_classes":len(SOURCE_CLASSES),"families":len(FAMILIES),
            "catalogue_only":True,"network_authorized":False,"training_allowed":False}


def page(*,group=None,domain=None,family=None,kind=None,q=None,after=None,limit=32):
    revision,groups,rows,ordered=_load()
    if type(limit) is not int or not 1<=limit<=MAX_PAGE:raise ValueError("directory page")
    if group is not None and group not in groups:raise ValueError("unknown group")
    if domain is not None and domain not in {g["domain"] for g in groups.values()}:raise ValueError("unknown domain")
    if family is not None and family not in FAMILIES:raise ValueError("unknown family")
    if kind is not None and kind not in SOURCE_CLASSES:raise ValueError("unknown kind")
    terms=[]
    if q is not None:
        terms=re.findall(r"[^\W_]+",clean(q,256).casefold())[:16]
        if not terms:raise ValueError("directory search tokens")
    fingerprint=digest([revision,group,domain,family,kind,terms])
    lower=""
    if after is not None:
        if not isinstance(after,str) or len(after)!=129 or after[64]!=":" or after[:64]!=fingerprint:
            raise ValueError("directory cursor mismatch")
        lower=_id(after[65:])
    matches=[]
    for lid in ordered:
        if lid<=lower:continue
        row=rows[lid]
        if any(expected is not None and row[field]!=expected for field,expected in
               (("group",group),("domain",domain),("family",family),("kind",kind))):continue
        haystack=" ".join(str(row[k]).replace("_"," ").replace("-"," ") for k in
              ("label","url","provider","kind","family","group","domain")).casefold()
        if any(t not in haystack for t in terms):continue
        matches.append(dict(row))
        if len(matches)>limit:break
    cursor=fingerprint+":"+matches[limit-1]["lead_id"] if len(matches)>limit else None
    return {"revision":revision,"leads":matches[:limit],"next_cursor":cursor,
            "catalogue_only":True,"network_authorized":False,"training_allowed":False}


def _target(path,scope,game):
    owner=owner_key(scope);game=_id(game)
    with GameCorpus(path)._db() as db:
        row=db.execute("SELECT namespace,external_id,title FROM games WHERE owner=? AND id=?",(owner,game)).fetchone()
    if row is None:raise LookupError("target game unavailable")
    if row["namespace"] not in PROVIDERS:raise ValueError("target namespace not supported by normalized release imports")
    if game_id(row["namespace"],row["external_id"])!=game:raise ValueError("target game identity differs")
    return row["namespace"],row["external_id"],row["title"]


def enqueue(path,scope,*,operation,group,lead_ids,game=None,use_preset=False,acknowledged=False):
    if acknowledged is not True or type(use_preset) is not bool:
        raise ValueError("explicit catalogue binding required")
    if not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation:
        raise ValueError("operation")
    revision,groups,rows,_=_load()
    if group not in groups or not isinstance(lead_ids,list) or not 1<=len(lead_ids)<=MAX_SELECT:
        raise ValueError("directory selection")
    ids=[_id(x) for x in lead_ids]
    if len(set(ids))!=len(ids):raise ValueError("duplicate selection")
    try:selection=[rows[x] for x in sorted(ids)]
    except KeyError as exc:raise ValueError("unknown lead") from exc
    if any(r["group"]!=group for r in selection):raise ValueError("mixed-group binding")
    if use_preset:
        if game is not None or group not in PRESET_IDENTITIES:raise ValueError("preset game identity required")
        namespace,external,title=PRESET_IDENTITIES[group]
    else:
        if game is None:raise ValueError("explicit existing game required")
        namespace,external,title=_target(path,scope,game)
    links=[{"url":r["url"],"kind":r["kind"],"language":"und"} for r in selection]
    entries=[{"id":external,"title":title,"stage":"unknown","links":links[i:i+8]} for i in range(0,len(links),8)]
    raw=json.dumps({"schema":"dragon.game-feed.v1","provider":namespace,"entries":entries},
        ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    # Keep the operation key stable across retries, letting the queue reject
    # an attempt to reuse it with different normalized observations. Sorting
    # selection makes reordering the same IDs idempotent.
    stable_operation="directory:"+digest(operation)
    receipt=ReleaseQueue(path).enqueue(scope,raw=raw,adapter="manifest",operation=stable_operation)
    return {**receipt,"game_id":game_id(namespace,external),"directory_revision":revision,
            "selected":len(ids),"capture_granted":False,"source_verified":False,"training_allowed":False}
