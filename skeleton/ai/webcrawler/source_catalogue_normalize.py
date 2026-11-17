"""Normalize reviewed publisher exports into the canonical Dragon source row.

No HTTP client, auth token, scraper, or dispatch capability. Output locators
come from explicit observed URL fields, except the Game Census page mapping
documented by that publisher. No fabricated game IDs or URL multiplication.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .source_catalogue_bulk import _row, _unique_pairs, _publish_new
from .source_catalogue_index import MAX_EXPORT_BYTES, MAX_SOURCES, _hash_file, _hex, _signature
from .source_navigation import _root

MODES = ("explicit-csv","wikidata-csv","github-page","itch-catalogue",
         "browser-census-jsonl","game-census-csv","crosswalk-csv")
MAX_ARRAY_BYTES = 16 * 1024**2
MAX_LINE = 64 * 1024
MAX_INPUT_ROWS = MAX_SOURCES * 2
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.~-]{0,399}\Z")
POSITIVE_ID = re.compile(r"[1-9][0-9]{0,12}\Z")
CROSSWALK = {
    "URL_IGDB":("game-discovery","reference","video game identity catalogue"),
    "URL_STEAMID":("game-discovery","reference","steam game store catalogue"),
    "URL_METACRITIC":("history-media","reference","game reviews history release"),
    "URL_HLTB":("game-worlds","reference","game progression playthrough duration"),
    "URL_WIKIPEDIA":("history-media","reference","game history reference"),
}
CENSUS_PUBLISHER = "https://thegamecensus.com/data"


def _source(name,url,family="game-discovery",kind="reference",tags="game project metadata catalogue"):
    return {"name":name,"url":url,"family":family,"kind":kind,"tags":tags}


def _json_file(path):
    if path.stat().st_size > MAX_ARRAY_BYTES:
        raise ValueError("publisher JSON array bound; use independently pinned pages")
    with path.open("rb") as file:
        raw=file.read(MAX_ARRAY_BYTES+1)
    if len(raw)>MAX_ARRAY_BYTES:
        raise ValueError("publisher JSON array bound")
    return json.loads(raw,object_pairs_hook=_unique_pairs)


def _lines(path):
    with path.open("rb") as file:
        for number in range(MAX_INPUT_ROWS+1):
            line=file.readline(MAX_LINE+1)
            if not line:
                return
            if len(line)>MAX_LINE:
                raise ValueError("source normalization line bound")
            if number==MAX_INPUT_ROWS:
                raise ValueError("source normalization row bound")
            if line.strip():
                yield json.loads(line,object_pairs_hook=_unique_pairs)


def _csv_rows(path,required):
    # Limit field lengths and row widths; restore the process-wide setting.
    previous=csv.field_size_limit(16384)
    try:
        with path.open("r",encoding="utf-8-sig",newline="") as file:
            reader=csv.DictReader(file,strict=True)
            fields=reader.fieldnames
            if (not fields or len(fields)>64 or len(set(fields))!=len(fields)
                    or not required<=set(fields)):
                raise ValueError("publisher CSV header")
            for number,row in enumerate(reader):
                if number>=MAX_INPUT_ROWS:
                    raise ValueError("publisher CSV row bound")
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("publisher CSV column mismatch")
                yield row
    finally:
        csv.field_size_limit(previous)


def _entries(path,mode,publisher):
    if mode=="github-page":
        data=_json_file(path)
        if not isinstance(data,dict) or not isinstance(data.get("items"),list) or len(data["items"])>100:
            raise ValueError("GitHub search page schema")
        for record in data["items"]:
            if not isinstance(record,dict):
                raise ValueError("GitHub repository row")
            name,url=record.get("full_name"),record.get("html_url")
            if (record.get("private") is not False or record.get("archived") is not False
                    or not isinstance(name,str) or not isinstance(url,str)
                    or url!="https://github.com/"+name):
                yield None,False
            else:
                yield _source(name,url,"engine-tools","documentation","game development repository metadata"),False
    elif mode=="itch-catalogue":
        data=_json_file(path)
        if not isinstance(data,list) or len(data)>10000:
            raise ValueError("itch catalogue page schema")
        for record in data:
            if not isinstance(record,dict):
                raise ValueError("itch catalogue row schema")
            url=record.get("url")
            if (record.get("nsfw")!="No" or not isinstance(url,str)
                    or not re.fullmatch(r"https://[a-z0-9-]+\.itch\.io/[A-Za-z0-9_.~-]+/?",url)):
                yield None,False
            else:
                yield _source(record.get("name"),url,tags="indie game itch io project catalogue"),False
    elif mode=="browser-census-jsonl":
        for record in _lines(path):
            if not isinstance(record,dict):
                raise ValueError("browser census row schema")
            yield _source(record.get("title"),record.get("url"),
                          tags="browser game independent project historical sighting"),False
    elif mode=="explicit-csv":
        for record in _csv_rows(path,{"name","url"}):
            yield _source(record["name"],record["url"]),False
    elif mode=="wikidata-csv":
        for record in _csv_rows(path,{"gameLabel","website"}):
            yield _source(record["gameLabel"],record["website"],
                          tags="wikidata game identity official website candidate"),False
    elif mode=="game-census-csv":
        if publisher!=CENSUS_PUBLISHER:
            raise ValueError("documented locator mapping restricted to Game Census publisher")
        # This exact index explicitly contains public pages and provides
        # their canonical slug. Other CSVs (e.g. sales calibration) may not.
        required={"app_id","name","slug","release_date","is_free",
                  "total_positive","total_negative","health_tier"}
        for record in _csv_rows(path,required):
            slug=record["slug"]
            if not SLUG.fullmatch(slug) or not POSITIVE_ID.fullmatch(record["app_id"]):
                yield None,True
            else:
                yield _source(record["name"],"https://thegamecensus.com/game/"+slug,
                             tags="game census steam game analytics review player metadata"),True
    elif mode=="crosswalk-csv":
        for record in _csv_rows(path,{"GAME_TITLE",*CROSSWALK}):
            found=False
            for column,(family,kind,tags) in CROSSWALK.items():
                if record[column]:
                    found=True
                    # Do not convert a bare ID, slug or partial host into a URL.
                    yield _source(record["GAME_TITLE"],record[column],family,kind,tags),False
            if not found:
                yield None,False
    else:
        raise ValueError("unknown source normalization mode")


def normalize(path,output,receipt,*,mode,publisher,rights_reference,input_sha256):
    if mode not in MODES:
        raise ValueError("source adapter mode")
    _root(publisher)
    _hex(input_sha256)
    if (not isinstance(rights_reference,str) or not rights_reference.strip()
            or len(rights_reference)>512 or any(ord(c)<32 or ord(c)==127 for c in rights_reference)):
        raise ValueError("operator metadata rights reference")
    path,output,receipt=map(Path,(path,output,receipt))
    if len({path.resolve(),output.resolve(),receipt.resolve()})!=3:
        raise ValueError("source normalization paths must be distinct")
    if output.exists() or receipt.exists() or output.is_symlink() or receipt.is_symlink():
        raise FileExistsError("source normalization output already exists")
    actual,source_signature=_hash_file(path,MAX_EXPORT_BYTES)
    if actual!=input_sha256:
        raise ValueError("source normalization input digest mismatch")
    count=Counter()
    h=hashlib.sha256()
    size=0
    fd,temporary=tempfile.mkstemp(prefix=".dragon-normalized-",dir=output.parent)
    try:
        with os.fdopen(fd,"wb") as file:
            for record,derived in _entries(path,mode,publisher):
                count["inputs"]+=1
                if count["inputs"]>MAX_INPUT_ROWS*len(CROSSWALK):
                    raise ValueError("source normalization candidate bound")
                if record is None:
                    count["held"]+=1
                    continue
                try:
                    _row(record)
                except (ValueError,TypeError):
                    count["held"]+=1
                    continue
                payload=json.dumps(record,ensure_ascii=True,sort_keys=True,
                    separators=(",",":")).encode("ascii")+b"\n"
                size+=len(payload)
                if size>MAX_EXPORT_BYTES or count["written"]>=MAX_SOURCES:
                    raise ValueError("source normalization output bound")
                file.write(payload)
                h.update(payload)
                count["written"]+=1
                count["publisher_documented_mapping" if derived else "explicit_url"]+=1
            file.flush()
            os.fsync(file.fileno())
        if _hash_file(path,MAX_EXPORT_BYTES)!=(actual,source_signature) or _signature(path)!=source_signature:
            raise ValueError("source normalization input changed")
        if not count["written"]:
            raise ValueError("source normalization produced no eligible locators")
        result={"schema":"skeleton.dragon.source-normalization.v1","mode":mode,
                "publisher":publisher,"rights_reference":rights_reference,
                "input_sha256":actual,"output_sha256":h.hexdigest(),
                "output_bytes":size,"counts":dict(count),
                "index_export":{"path":str(output.resolve()),"sha256":h.hexdigest(),
                                "publisher":publisher,"rights_reference":rights_reference},
                "unique_source_count_claimed":False,"network_authorized":False,
                "rights_verified":False,"access_verified":False}
        os.link(temporary,output)
        _publish_new(receipt,json.dumps(result,ensure_ascii=True,sort_keys=True,
                     indent=2).encode("ascii")+b"\n")
        return result
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--input-sha256",required=True)
    p.add_argument("--mode",choices=MODES,required=True)
    p.add_argument("--publisher",required=True)
    p.add_argument("--rights-reference",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    args=p.parse_args(argv)
    print(json.dumps(normalize(args.input,args.output,args.receipt,mode=args.mode,
          publisher=args.publisher,rights_reference=args.rights_reference,
          input_sha256=args.input_sha256),sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
