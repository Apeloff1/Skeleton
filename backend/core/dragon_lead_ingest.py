"""Local, operator-authorized bulk dataset projection into Dragon's lead graph.

Usage: python -m core.dragon_lead_ingest --target steam-fronkon --format steam-csv
  --input /absolute/games.csv --tenant ... --owner ... --rights-reference ...
  --acknowledge-metadata-rights

Never downloads, installs, or extracts game assets. Only AppID/title or bounded
explicit normalized locator rows are retained. Two deterministic passes bind
source bytes, row count, and page chain. Resume by replaying exact pages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re

from core.dragon_dataset_ingest import fingerprint,source_stream
from core.dragon_lead_graph import LeadGraph,MAX_PAGE_ROWS,MAX_SNAPSHOT_ROWS,MAX_PAGE_BYTES,ZERO,parse_page
from core.dragon_corpus_runtime import _path
from core.dragon_game_corpus import clean,digest

MAX_COLUMNS=256
MAX_FIELD=4*1024*1024
CHUNK=1024*1024

def _source_hash(path,witness):
    h=hashlib.sha256()
    with source_stream(path,None,witness) as raw:
        for block in iter(lambda:raw.read(CHUNK),b""):h.update(block)
    return h.hexdigest()

def _pick_header(headers,choices):
    found=[h for h in headers if isinstance(h,str) and h.strip().casefold().replace("_","") in choices]
    if len(found)!=1:raise ValueError("ambiguous or missing input column")
    return found[0]

def _steam_row(appid,title):
    if type(appid) is int:appid=str(appid)
    if not isinstance(appid,str) or not re.fullmatch(r"[1-9][0-9]{1,11}",appid.strip()):
        raise ValueError("invalid provider AppID; source row not silently skipped")
    return {"appid":appid.strip(),"title":clean(title,256)}

def steam_csv(raw):
    old=csv.field_size_limit(MAX_FIELD)
    try:
        # newline="" preserves RFC 4180 embedded newlines; text wrapper is
        # detachable, so source_stream still verifies its file witness.
        text=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict")
        try:
            reader=csv.DictReader(text)
            columns=reader.fieldnames
            if not columns or len(columns)>MAX_COLUMNS or len(set(columns))!=len(columns):
                raise ValueError("invalid Steam CSV header")
            app=_pick_header(columns,{"appid","app id","steamappid"})
            title=_pick_header(columns,{"name","title"})
            for row in reader:
                if None in row or row[app] is None or row[title] is None:raise ValueError("malformed Steam CSV row")
                yield _steam_row(row[app],row[title])
        finally:text.detach()
    finally:csv.field_size_limit(old)

def steam_parquet(raw):
    # Optional local reader only. No remote path/URI or auto-install.
    try:import pyarrow.parquet as pq
    except ImportError as exc:raise RuntimeError("Install an approved pyarrow build or supply the CSV export") from exc
    f=pq.ParquetFile(raw)
    app=_pick_header(f.schema_arrow.names,{"appid","app id","steamappid"})
    title=_pick_header(f.schema_arrow.names,{"name","title"})
    if f.metadata.num_rows>MAX_SNAPSHOT_ROWS:raise ValueError("Parquet row cap")
    for batch in f.iter_batches(batch_size=MAX_PAGE_ROWS,columns=[app,title],use_threads=False):
        for row in batch.to_pylist():yield _steam_row(row[app],row[title])

def steam_json(raw):
    # The Fronkon-style JSON is a massive mapping keyed by AppID. Do not
    # json.load the export; optional ijson parses incrementally.
    try:import ijson
    except ImportError as exc:raise RuntimeError("Install approved ijson or use the CSV export") from exc
    for appid,record in ijson.kvitems(raw,""):
        if not isinstance(record,dict):raise ValueError("invalid Steam JSON record")
        yield _steam_row(appid,record.get("name"))

def normalized_jsonl(raw,projection):
    while True:
        line=raw.readline(8194)
        if not line:break
        if len(line)>8192 or not line.strip():raise ValueError("invalid normalized line")
        yield parse_page(line,projection)[0]

def pages(path,witness,format,projection):
    with source_stream(path,None,witness) as stream:
        if format=="steam-csv":rows=steam_csv(stream)
        elif format=="steam-parquet":rows=steam_parquet(stream)
        elif format=="steam-json":rows=steam_json(stream)
        else:rows=normalized_jsonl(stream,projection)
        while True:
            selected=list(itertools.islice(rows,MAX_PAGE_ROWS))
            if not selected:break
            raw=b"".join(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()+b"\n" for r in selected)
            if len(raw)>MAX_PAGE_BYTES:raise ValueError("normalized projection page cap")
            yield raw,len(selected)

def qualify(path,format,projection):
    witness=fingerprint(path)
    raw_sha=_source_hash(path,witness)
    count=0;chain=ZERO;n=0
    for ordinal,(raw,size) in enumerate(pages(path,witness,format,projection)):
        count+=size
        if count>MAX_SNAPSHOT_ROWS:raise ValueError("dataset row cap")
        chain=digest([chain,ordinal,hashlib.sha256(raw).hexdigest(),size]);n+=1
    if count==0:raise ValueError("empty dataset")
    return witness,raw_sha,count,chain,n

def ingest(graph,scope,*,path,format,projection,target,rights_reference,grant_seconds,expected_sha=None):
    witness,raw_sha,count,final_chain,total_pages=qualify(path,format,projection)
    if expected_sha is not None and raw_sha!=expected_sha:raise ValueError("input dataset SHA-256 differs")
    begun=graph.begin(scope,target_id=target,projection=projection,source_sha=raw_sha,expected_rows=count,
                      rights_ref=rights_reference,grant_seconds=grant_seconds,acknowledged=True)
    sid=begun["snapshot_id"]
    if begun["state"]=="sealed":
        if begun["chain"]!=final_chain:raise ValueError("sealed snapshot differs")
        return {**begun,"already_sealed":True,"verified_pages":total_pages}
    chain=ZERO;seen=0
    for ordinal,(raw,size) in enumerate(pages(path,witness,format,projection)):
        h=hashlib.sha256(raw).hexdigest()
        receipt=graph.append(scope,sid,ordinal=ordinal,raw=raw,sha256=h,previous_chain=chain)
        chain=digest([chain,ordinal,h,size])
        if receipt["chain"]!=chain or receipt["rows"]!=size:raise ValueError("page receipt differs")
        seen+=size
    if seen!=count or chain!=final_chain or _source_hash(path,witness)!=raw_sha:
        raise ValueError("dataset changed across projection passes; snapshot unsealed")
    return {**graph.seal(scope,sid,chain),"verified_pages":total_pages,"input_sha256":raw_sha}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",required=True)
    parser.add_argument("--format",choices=["steam-csv","steam-parquet","steam-json","normalized-jsonl"],required=True)
    parser.add_argument("--projection",choices=["steam","modrinth","locator"],default="steam")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--expected-sha",default=None)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--owner",required=True)
    parser.add_argument("--rights-reference",required=True)
    parser.add_argument("--grant-seconds",type=int,default=7*86400)
    parser.add_argument("--acknowledge-metadata-rights",action="store_true")
    args=parser.parse_args(argv)
    if not args.acknowledge_metadata_rights:parser.error("explicit metadata rights acknowledgement required")
    if args.format!="normalized-jsonl" and args.projection!="steam":parser.error("Steam file format requires Steam projection")
    scope={"tenant_id":args.tenant,"owner_id":args.owner}
    graph=LeadGraph(_path(create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1"))
    # The graph must have been enabled by its owner/editor. No automatic
    # permission, source grant, or activation of live crawling.
    receipt=ingest(graph,scope,path=args.input.expanduser().absolute(),format=args.format,
                   projection=args.projection,target=args.target,rights_reference=args.rights_reference,
                   grant_seconds=args.grant_seconds,expected_sha=args.expected_sha)
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
