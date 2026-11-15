"""Read exact, source-controlled Steam candidate identity shards.

The manifest contains public mirror metadata, not confirmed current Steam
releases or a source license. Only a reviewed, finite owner grant can project
the bundle into persisted leads. A shard is verified against its Git blob
identity at read time; its SHA-256 is also recorded in the normalized witness.
No provider fetching or guessed AppIDs occurs.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from core.dragon_game_corpus import clean,digest

ROOT=Path(__file__).with_name("dragon_catalogue_snapshots")
MAX_SHARDS=4096
MAX_SHARD_BYTES=4*1024*1024
MAX_SHARD_ROWS=10000
MAX_BUNDLE_ROWS=20_000_000
HEX40=re.compile(r"[a-f0-9]{40}\Z")
TARGET="steam-appid-mirror"
SOURCE="https://github.com/jsnli/steamappidlist/blob/master/data/games_appid.json"

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError("duplicate bundle manifest key")
        out[k]=v
    return out

@lru_cache(maxsize=1)
def inventory():
    manifest=ROOT/"steam-manifest.json"
    if manifest.is_symlink():raise ValueError("bundle manifest symlink")
    raw=manifest.read_bytes()
    if not 1<=len(raw)<=2*1024*1024:raise ValueError("bundle manifest bytes")
    meta=json.loads(raw,object_pairs_hook=_pairs)
    if (not isinstance(meta,dict) or meta.get("schema")!="dragon.steam-identity-snapshot.v2"
        or meta.get("source_repository")!="jsnli/steamappidlist" or meta.get("source_path")!="data/games_appid.json"
        or meta.get("fields")!=["appid","name"] or meta.get("source_use_status")!="review_required"
        or not isinstance(meta.get("source_blob"),str) or not HEX40.fullmatch(meta["source_blob"])):
        raise ValueError("bundle manifest schema")
    shards=meta.get("shards")
    if not isinstance(shards,list) or not 1<=len(shards)<=MAX_SHARDS:raise ValueError("bundle shard count")
    offset=0;last=0;starts=[];records=[]
    for i,r in enumerate(shards):
        if not isinstance(r,dict) or set(r)!={"file","count","first","last","git_blob"}:
            raise ValueError("bundle shard descriptor")
        if r["file"]!=f"steam-games-{i:03d}.jsonl" or not isinstance(r["git_blob"],str) or not HEX40.fullmatch(r["git_blob"]):
            raise ValueError("bundle shard identity")
        count=r["count"];first=r["first"];end=r["last"]
        if type(count) is not int or not 1<=count<=MAX_SHARD_ROWS or type(first) is not int or type(end) is not int or not last<first<=end<10**12:
            raise ValueError("bundle range")
        starts.append(offset);offset+=count;last=end
        records.append(dict(r))
    if offset>MAX_BUNDLE_ROWS or meta.get("accepted")!=offset or type(meta.get("source_records")) is not int or type(meta.get("excluded")) is not int or meta["source_records"]-meta["excluded"]!=offset:
        raise ValueError("bundle census mismatch")
    return hashlib.sha256(raw).hexdigest(),meta["source_blob"],offset,tuple(starts),tuple(records)

@lru_cache(maxsize=2)
def _shard(revision,index):
    current,_,_,_,records=inventory()
    if revision!=current or type(index) is not int or not 0<=index<len(records):
        raise ValueError("bundle revision or shard")
    record=records[index];file=ROOT/record["file"]
    if file.is_symlink():raise ValueError("bundle shard symlink")
    raw=file.read_bytes()
    if not 1<=len(raw)<=MAX_SHARD_BYTES:raise ValueError("bundle shard byte bound")
    blob=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw,usedforsecurity=False).hexdigest()
    if blob!=record["git_blob"]:raise ValueError("bundle Git blob mismatch")
    lines=raw.splitlines()
    if len(lines)!=record["count"]:raise ValueError("bundle row count differs")
    out=[];last=0
    for line in lines:
        if not 1<=len(line)<=8192:raise ValueError("bundle line bytes")
        row=json.loads(line)
        if not isinstance(row,list) or len(row)!=2 or type(row[0]) is not int or not last<row[0]<10**12:
            raise ValueError("bundle AppID ordering")
        title=clean(row[1],256)
        out.append((str(row[0]),title));last=row[0]
    if int(out[0][0])!=record["first"] or last!=record["last"]:
        raise ValueError("bundle shard range differs")
    return hashlib.sha256(raw).hexdigest(),tuple(out)

def page(offset,limit):
    revision,source_blob,total,starts,records=inventory()
    if type(offset) is not int or not 0<=offset<=total or type(limit) is not int or not 1<=limit<=128:
        raise ValueError("bundle page bound")
    out=[];witnesses=[];cursor=offset
    while cursor<total and len(out)<limit:
        i=bisect_right(starts,cursor)-1
        sha,rows=_shard(revision,i)
        start=cursor-starts[i];n=min(limit-len(out),len(rows)-start)
        out.extend({"appid":appid,"title":title} for appid,title in rows[start:start+n])
        witnesses.append([records[i]["git_blob"],sha,start,n])
        cursor+=n
    return out,digest([revision,source_blob,witnesses])

def summary():
    revision,blob,total,_,shards=inventory()
    return {"bundle_revision":revision,"source_blob":blob,"title_identity_candidates":total,
            "store_locator_floor":total,"gross_optional_route_candidates":total*17,
            "shards":len(shards),"source_rights_verified":False,"source_verified":False,
            "network_authorized":False,"source_url":SOURCE}


def normalized_page(ordinal,rows_per_page=128):
    if type(ordinal) is not int or ordinal<0 or rows_per_page!=128:
        raise ValueError("bundle ordinal")
    rows,witness=page(ordinal*rows_per_page,rows_per_page)
    if not rows:raise ValueError("bundle page unavailable")
    raw=b"".join(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()+b"\n" for row in rows)
    return raw,witness
