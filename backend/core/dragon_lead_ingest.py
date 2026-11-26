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
import threading

from core.dragon_dataset_ingest import fingerprint,source_stream
from core.dragon_lead_graph import LeadGraph,MAX_PAGE_ROWS,MAX_SNAPSHOT_ROWS,MAX_PAGE_BYTES,ZERO,parse_page
from core.dragon_corpus_runtime import _path
from core.dragon_game_corpus import clean,digest

MAX_COLUMNS=256
MAX_FIELD=4*1024*1024
MAX_RECORD_CHARS=8*1024*1024
_CSV_LOCK=threading.RLock()
CHUNK=1024*1024
FORMATS={
    "steam-csv":"steam", "steam-parquet":"steam", "steam-json":"steam",
    "modrinth-json":"modrinth", "wikidata-csv":"locator", "locator-csv":"locator",
    "steam-tsv":"steam", "wikidata-tsv":"locator", "locator-tsv":"locator",
    "wikidata-sparql-json":"locator", "normalized-jsonl":None,
}
PROJECTIONS=frozenset({"steam","modrinth","locator"})

def _validate_format(format,projection):
    if (not isinstance(format,str) or format not in FORMATS
            or not isinstance(projection,str) or projection not in PROJECTIONS
            or FORMATS[format] is not None and FORMATS[format]!=projection):
        raise ValueError("unsupported or mismatched dataset projection")

def _unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError("duplicate JSON export field")
        result[key]=value
    return result

def _reject_constant(value):
    raise ValueError("nonfinite JSON export number")

def _expected_hash(value):
    if value is not None and (not isinstance(value,str)
            or not re.fullmatch(r"[a-f0-9]{64}",value)):
        raise ValueError("expected SHA-256 must be canonical lowercase hex")
    return value

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

class _RecordLines:
    """Bound each logical CSV record, including quoted multiline fields."""
    def __init__(self,text):
        self.text=text
        self.remaining=MAX_RECORD_CHARS
    def __iter__(self):
        return self
    def __next__(self):
        line=self.text.readline(self.remaining+1)
        if not line:raise StopIteration
        self.remaining-=len(line)
        if self.remaining<0:raise ValueError("tabular logical record exceeds character bound")
        return line

def _tabular_rows(raw,*,delimiter=","):
    if delimiter not in {",","\t"}:raise ValueError("unsupported delimiter")
    text=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict")
    lines=_RecordLines(text)
    reader=csv.reader(lines,delimiter=delimiter,strict=True)
    def next_record():
        lines.remaining=MAX_RECORD_CHARS
        # csv.field_size_limit is process global. Restrict this module's
        # critical section to one record and always restore the old limit.
        with _CSV_LOCK:
            old=csv.field_size_limit(MAX_FIELD)
            try:return next(reader)
            except csv.Error as exc:raise ValueError("malformed tabular export") from exc
            finally:csv.field_size_limit(old)
    try:
        try:header=next_record()
        except StopIteration:raise ValueError("missing tabular header") from None
        if (not 1<=len(header)<=MAX_COLUMNS
                or any(not name.strip() or len(name)>256 for name in header)
                or len({name.strip().casefold() for name in header})!=len(header)):
            raise ValueError("invalid or ambiguous tabular header")
        yield header
        while True:
            try:record=next_record()
            except StopIteration:break
            if len(record)!=len(header):
                raise ValueError("tabular row width differs from header")
            yield dict(zip(header,record,strict=True))
    finally:text.detach()

def steam_csv(raw,*,delimiter=","):
    records=_tabular_rows(raw,delimiter=delimiter)
    try:
        columns=next(records)
        app=_pick_header(columns,{"appid","app id","steamappid"})
        title=_pick_header(columns,{"name","title"})
        for row in records:
            yield _steam_row(row[app],row[title])
    finally:records.close()

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

def modrinth_json(raw):
    """Read exported Modrinth search pages; never contact its paginated API."""
    # The search endpoint returns a bounded page. No arbitrary large object
    # allocation: callers with multiple pages use normalized JSONL.
    data=raw.read(16*1024*1024+1)
    if len(data)>16*1024*1024:raise ValueError("Modrinth search export cap")
    doc=json.loads(data,object_pairs_hook=_unique_pairs,parse_constant=_reject_constant)
    if not isinstance(doc,dict) or not isinstance(doc.get("hits"),list) or not 1<=len(doc["hits"])<=100:
        raise ValueError("Modrinth search page schema")
    for item in doc["hits"]:
        if not isinstance(item,dict):raise ValueError("Modrinth project record")
        row={"id":item.get("project_id"),"slug":item.get("slug"),"title":item.get("title"),
             "project_type":item.get("project_type") or "project"}
        yield parse_page(json.dumps(row,ensure_ascii=False).encode(),"modrinth")[0]

def wikidata_csv(raw,*,delimiter=","):
    """Consume an explicitly game-filtered local Wikidata export."""
    records=_tabular_rows(raw,delimiter=delimiter)
    try:
        fields=next(records)
        if not {"item","itemLabel"}.issubset(fields):
            raise ValueError("Wikidata filtered tabular header")
        for item in records:
            match=re.fullmatch(r"(?:https?://www\.wikidata\.org/entity/)?(Q[1-9][0-9]{0,15})",item["item"])
            if not match:raise ValueError("Wikidata entity")
            qid=match[1]
            yield {"url":"https://www.wikidata.org/wiki/"+qid,
                   "title":clean(item["itemLabel"],256),"kind":"cross_database_identifiers",
                   "subject":"wikidata:"+qid}
    finally:records.close()

def locator_csv(raw,*,delimiter=","):
    """Provider-neutral operator-supplied metadata export."""
    records=_tabular_rows(raw,delimiter=delimiter)
    try:
        columns=next(records)
        if not {"url","title","kind","subject"}.issubset(columns):
            raise ValueError("locator tabular header")
        for row in records:
            candidate={k:row[k] for k in ("url","title","kind","subject")}
            yield parse_page(json.dumps(candidate,ensure_ascii=False).encode(),"locator")[0]
    finally:records.close()

def wikidata_sparql_json(raw):
    """Read a bounded, already supplied SPARQL JSON results export.

    Only a game-filtered item/itemLabel table is accepted. No SPARQL query,
    URL from the export, remote service, or script is executed.
    """
    limit=16*1024*1024
    data=raw.read(limit+1)
    if len(data)>limit:raise ValueError("SPARQL JSON export byte cap")
    try:
        doc=json.loads(data,object_pairs_hook=_unique_pairs,parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError("SPARQL JSON nesting") from exc
    if (not isinstance(doc,dict) or not isinstance(doc.get("head"),dict)
            or not isinstance(doc.get("results"),dict)):
        raise ValueError("SPARQL JSON result schema")
    fields=doc["head"].get("vars")
    bindings=doc["results"].get("bindings")
    if (not isinstance(fields,list) or not 2<=len(fields)<=MAX_COLUMNS
            or any(not isinstance(x,str) or not 1<=len(x)<=256 for x in fields)
            or len(set(fields))!=len(fields) or not {"item","itemLabel"}.issubset(fields)
            or not isinstance(bindings,list) or not 1<=len(bindings)<=50_000):
        raise ValueError("SPARQL JSON result bounds")
    for row in bindings:
        if not isinstance(row,dict) or not set(row).issubset(fields):
            raise ValueError("SPARQL JSON binding schema")
        item=row.get("item")
        label=row.get("itemLabel")
        if (not isinstance(item,dict) or item.get("type")!="uri"
                or not isinstance(item.get("value"),str)
                or not isinstance(label,dict) or label.get("type")!="literal"
                or not isinstance(label.get("value"),str)):
            raise ValueError("SPARQL JSON item identity or label")
        match=re.fullmatch(r"https?://www\.wikidata\.org/entity/(Q[1-9][0-9]{0,15})",item["value"])
        if not match:raise ValueError("SPARQL JSON Wikidata entity")
        qid=match[1]
        yield {"url":"https://www.wikidata.org/wiki/"+qid,
               "title":clean(label["value"],256),"kind":"cross_database_identifiers",
               "subject":"wikidata:"+qid}

def normalized_jsonl(raw,projection):
    while True:
        line=raw.readline(8194)
        if not line:break
        if len(line)>8192 or not line.strip():raise ValueError("invalid normalized line")
        yield parse_page(line,projection)[0]

def pages(path,witness,format,projection):
    _validate_format(format,projection)
    with source_stream(path,None,witness) as stream:
        if format=="steam-csv":rows=steam_csv(stream)
        elif format=="steam-tsv":rows=steam_csv(stream,delimiter="\t")
        elif format=="steam-parquet":rows=steam_parquet(stream)
        elif format=="steam-json":rows=steam_json(stream)
        elif format=="modrinth-json":rows=modrinth_json(stream)
        elif format=="wikidata-csv":rows=wikidata_csv(stream)
        elif format=="wikidata-tsv":rows=wikidata_csv(stream,delimiter="\t")
        elif format=="wikidata-sparql-json":rows=wikidata_sparql_json(stream)
        elif format=="locator-csv":rows=locator_csv(stream)
        elif format=="locator-tsv":rows=locator_csv(stream,delimiter="\t")
        else:rows=normalized_jsonl(stream,projection)
        while True:
            selected=list(itertools.islice(rows,MAX_PAGE_ROWS))
            if not selected:break
            raw=b"".join(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()+b"\n" for r in selected)
            if len(raw)>MAX_PAGE_BYTES:raise ValueError("normalized projection page cap")
            # Validate the exact serialized page before any graph reservation.
            # In particular, a valid provider row is not sufficient evidence
            # that the selected normalized projection schema accepts it.
            if len(parse_page(raw,projection))!=len(selected):
                raise ValueError("normalized page row conservation")
            yield raw,len(selected)

def qualify(path,format,projection,*,expected_sha=None):
    _validate_format(format,projection)
    expected_sha=_expected_hash(expected_sha)
    witness=fingerprint(path)
    raw_sha=_source_hash(path,witness)
    if expected_sha is not None and raw_sha!=expected_sha:
        raise ValueError("input dataset SHA-256 differs")
    count=0;chain=ZERO;n=0
    for ordinal,(raw,size) in enumerate(pages(path,witness,format,projection)):
        count+=size
        if count>MAX_SNAPSHOT_ROWS:raise ValueError("dataset row cap")
        chain=digest([chain,ordinal,hashlib.sha256(raw).hexdigest(),size]);n+=1
    if count==0:raise ValueError("empty dataset")
    # A timestamp/inode witness alone is not a cryptographic byte witness.
    # Re-read the raw export after projection, before opening any write grant.
    if _source_hash(path,witness)!=raw_sha:
        raise ValueError("dataset bytes changed during qualification")
    return witness,raw_sha,count,chain,n

def _inspection_identity(format,projection,raw_sha,count,chain,n):
    # This is an integrity comparison token, not a signature or a license.
    return digest(["skeleton.dragon.offline-export-inspection.v2",
                   format,projection,raw_sha,count,chain,n])

def inspect_export(path,format,projection,*,expected_sha=None):
    """Read-only validation of a separately supplied local export.

    No graph object, target lookup, remote access, license assertion, import,
    or permanent source permission is created by this report.
    """
    _,raw_sha,count,chain,n=qualify(Path(path),format,projection,expected_sha=expected_sha)
    return {"schema":"skeleton.dragon.offline-export-inspection.v2",
            "inspection_digest":_inspection_identity(format,projection,raw_sha,count,chain,n),
            "format":format,"projection":projection,"input_sha256":raw_sha,
            "expected_sha_matched":expected_sha is not None,
            "rows":count,"page_chain":chain,"pages":n,
            "network_executed":False,"graph_written":False,
            "license_verified":False,"source_rights_verified":False}

def ingest(graph,scope,*,path,format,projection,target,rights_reference,grant_seconds,expected_sha=None,
           expected_inspection=None,graph_factory=None,authorize=None):
    if (graph is None)==(graph_factory is None):
        raise ValueError("exactly one graph or graph factory required")
    expected_inspection=_expected_hash(expected_inspection)
    witness,raw_sha,count,final_chain,total_pages=qualify(path,format,projection,expected_sha=expected_sha)
    inspection=_inspection_identity(format,projection,raw_sha,count,final_chain,total_pages)
    if expected_inspection is not None and expected_inspection!=inspection:
        raise ValueError("offline inspection digest differs; graph untouched")
    if authorize is not None:authorize()
    if graph is None:graph=graph_factory()
    if authorize is not None:authorize()
    begun=graph.begin(scope,target_id=target,projection=projection,source_sha=raw_sha,expected_rows=count,
                      rights_ref=rights_reference,grant_seconds=grant_seconds,acknowledged=True)
    sid=begun["snapshot_id"]
    if begun["state"]=="sealed":
        if begun["chain"]!=final_chain or begun["rows"]!=count:
            raise ValueError("sealed snapshot differs")
        if _source_hash(path,witness)!=raw_sha:
            raise ValueError("input dataset changed before sealed replay")
        return {**begun,"already_sealed":True,"verified_pages":total_pages,"input_sha256":raw_sha,
                "inspection_digest":inspection,"expected_inspection_matched":expected_inspection is not None}
    chain=ZERO;seen=0
    for ordinal,(raw,size) in enumerate(pages(path,witness,format,projection)):
        h=hashlib.sha256(raw).hexdigest()
        if authorize is not None:authorize()
        receipt=graph.append(scope,sid,ordinal=ordinal,raw=raw,sha256=h,previous_chain=chain)
        chain=digest([chain,ordinal,h,size])
        if receipt["chain"]!=chain or receipt["rows"]!=size:raise ValueError("page receipt differs")
        seen+=size
    if seen!=count or chain!=final_chain or _source_hash(path,witness)!=raw_sha:
        raise ValueError("dataset changed across projection passes; snapshot unsealed")
    if authorize is not None:authorize()
    return {**graph.seal(scope,sid,chain),"verified_pages":total_pages,"input_sha256":raw_sha,
            "inspection_digest":inspection,"expected_inspection_matched":expected_inspection is not None}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target")
    parser.add_argument("--inspect-only",action="store_true",help="Validate local bytes and projection without opening a graph")
    parser.add_argument("--format",choices=sorted(FORMATS),required=True)
    parser.add_argument("--projection",choices=["steam","modrinth","locator"],default="steam")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--expected-sha",default=None)
    parser.add_argument("--expected-inspection",help="Exact digest of prior offline inspection (import only)")
    parser.add_argument("--tenant")
    parser.add_argument("--owner")
    parser.add_argument("--rights-reference")
    parser.add_argument("--grant-seconds",type=int,default=7*86400)
    parser.add_argument("--acknowledge-metadata-rights",action="store_true")
    args=parser.parse_args(argv)
    try:
        _validate_format(args.format,args.projection)
        _expected_hash(args.expected_sha)
        _expected_hash(args.expected_inspection)
    except ValueError as exc:
        parser.error(str(exc))
    path=args.input.expanduser().absolute()
    if args.inspect_only:
        if any(value is not None for value in (args.target,args.tenant,args.owner,args.rights_reference,args.expected_inspection)) or args.acknowledge_metadata_rights:
            parser.error("inspection is read-only; omit graph target, scope and import grants")
        print(json.dumps(inspect_export(path,args.format,args.projection,expected_sha=args.expected_sha),sort_keys=True))
        return 0
    if not all((args.target,args.tenant,args.owner,args.rights_reference)):
        parser.error("import requires target, tenant, owner and rights reference")
    if not args.acknowledge_metadata_rights:parser.error("explicit metadata rights acknowledgement required")
    scope={"tenant_id":args.tenant,"owner_id":args.owner}
    def graph_factory():
        return LeadGraph(_path(scope=scope,create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1"))
    # The graph must have been enabled by its owner/editor. No automatic
    # permission, source grant, or activation of live crawling.
    receipt=ingest(None,scope,path=path,format=args.format,graph_factory=graph_factory,
                   projection=args.projection,target=args.target,rights_reference=args.rights_reference,
                   grant_seconds=args.grant_seconds,expected_sha=args.expected_sha,
                   expected_inspection=args.expected_inspection)
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
