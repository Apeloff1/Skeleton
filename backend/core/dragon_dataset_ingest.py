"""Streaming offline ingestion of licensed game-data JSONL and ZIP members.

Designed for EVE SDE-style releases: no archive extraction, credentialed API,
arbitrary network request, or in-memory loading of a multi-gigabyte dataset.
Two passes compute the expected immutable chain, then import exact pages.
The parent dataset must already be bound to a catalogue observation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import stat
import zipfile

from core.dragon_game_datasets import DatasetShard,parse_page,chain_step,ZERO,MAX_PAGE,MAX_ROWS,MAX_RECORD,MAX_VERSION_ROWS

MAX_INPUT=512*1024**3
MAX_MEMBERS=16_384
MAX_RATIO=512


def fingerprint(path):
    if not path.is_absolute() or path.resolve(strict=True)!=path:
        raise ValueError("canonical input path required")
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or not 1<=info.st_size<=MAX_INPUT:
        raise ValueError("input file bounds")
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns


def _member_name(value):
    if (not isinstance(value,str) or not 1<=len(value)<=512 or "\\" in value or "\0" in value
            or value.startswith("/") or any(x in {"",".",".."} for x in value.split("/"))):
        raise ValueError("unsafe archive member")
    name=PurePosixPath(value)
    if name.suffix.lower() not in {".jsonl",".ndjson"}:
        raise ValueError("select one JSONL data member")
    return value


@contextmanager
def source_stream(path,member,expected):
    if fingerprint(path)!=expected:
        raise ValueError("input identity changed")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags)
    try:
        with os.fdopen(fd,"rb") as raw:
            fd=None
            st=os.fstat(raw.fileno())
            if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=expected:
                raise ValueError("input identity changed at open")
            if member is None:
                yield raw
            else:
                member=_member_name(member)
                with zipfile.ZipFile(raw) as archive:
                    infos=archive.infolist()
                    if len(infos)>MAX_MEMBERS:
                        raise ValueError("archive inventory bound")
                    matching=[x for x in infos if x.filename==member]
                    if len(matching)!=1:
                        raise ValueError("archive member must be unique")
                    entry=matching[0]
                    mode=(entry.external_attr>>16)&0o170000
                    if (entry.is_dir() or mode not in {0,stat.S_IFREG} or entry.flag_bits&1
                            or not 1<=entry.file_size<=MAX_INPUT or not 1<=entry.compress_size<=MAX_INPUT
                            or entry.file_size>MAX_RATIO*entry.compress_size
                            or entry.compress_type not in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}):
                        raise ValueError("unsafe or oversized archive member")
                    with archive.open(entry,"r") as stream:
                        yield stream
            st=os.fstat(raw.fileno())
            if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=expected:
                raise ValueError("source changed during ingest")
    finally:
        if fd is not None:os.close(fd)


def pages(path,member,witness):
    """The same exact normalized newline convention in both passes."""
    total_bytes=total_rows=0
    buffered=[]
    byte_count=0
    with source_stream(path,member,witness) as stream:
        while True:
            line=stream.readline(MAX_RECORD+3)
            if not line:break
            total_bytes+=len(line)
            if total_bytes>MAX_INPUT or len(line)>MAX_RECORD+2:
                raise ValueError("input record or expanded-byte bound")
            line=line.rstrip(b"\r\n")
            if not line.strip() or len(line)>MAX_RECORD:
                raise ValueError("empty or oversize record")
            blob=line+b"\n"
            if buffered and (len(buffered)>=MAX_ROWS or byte_count+len(blob)>MAX_PAGE):
                yield b"".join(buffered),len(buffered)
                buffered=[];byte_count=0
            buffered.append(blob);byte_count+=len(blob);total_rows+=1
            if total_rows>MAX_VERSION_ROWS:
                raise ValueError("version row cap; partition dataset")
        if buffered:yield b"".join(buffered),len(buffered)


def plan(path,member=None):
    path=Path(path)
    witness=fingerprint(path)
    chain=ZERO;rows=count=0
    for count0,(raw,n) in enumerate(pages(path,member,witness)):
        if len(parse_page(raw))!=n:raise ValueError("page validation")
        chain=chain_step(chain,hashlib.sha256(raw).hexdigest(),count0,n)
        rows+=n;count=count0+1
    if not rows:raise ValueError("empty dataset")
    return {"file_identity":witness,"expected_rows":rows,"expected_chain":chain,"pages":count}


def ingest(shard,path,*,member=None,dataset,source,observation_digest,label,
           rights_acknowledged,grant_seconds=86400,corpus=None):
    if rights_acknowledged is not True:
        raise ValueError("explicit data-retention rights required")
    path=Path(path)
    info=plan(path,member)
    receipt=shard.begin(dataset=dataset,source=source,observation_digest=observation_digest,
        label=label,expected_rows=info["expected_rows"],expected_chain=info["expected_chain"],
        grant_seconds=grant_seconds,rights_acknowledged=True,corpus=corpus)
    version=receipt["id"]
    chain=ZERO;rows=0;count=0
    for ordinal,(raw,n) in enumerate(pages(path,member,info["file_identity"])):
        chain=chain_step(chain,hashlib.sha256(raw).hexdigest(),ordinal,n)
        ack=shard.append(version,ordinal,raw)
        if ack["chain"]!=chain or ack["rows"]!=n or ack["page_hash"]!=hashlib.sha256(raw).hexdigest():
            raise ValueError("dataset page witness changed")
        rows+=n;count=ordinal+1
    if (rows,chain,count)!=(info["expected_rows"],info["expected_chain"],info["pages"]):
        raise ValueError("dataset changed between passes; never seal")
    final=shard.seal(version)
    return {**final,"pages_verified":count,"network_executed":False,
            "physical_capacity_verified":False,"rights_reviewed":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-json",required=True,help="Private operator-owned scope JSON file")
    parser.add_argument("--game",required=True)
    parser.add_argument("--source",required=True)
    parser.add_argument("--observation-digest",required=True)
    parser.add_argument("--dataset",required=True)
    parser.add_argument("--label",required=True)
    parser.add_argument("--path",required=True)
    parser.add_argument("--member")
    parser.add_argument("--grant-seconds",type=int,default=86400)
    parser.add_argument("--acknowledge-retention-rights",action="store_true")
    args=parser.parse_args()
    if not args.acknowledge_retention_rights:parser.error("explicit retention acknowledgement is required")
    scope_path=Path(args.scope_json)
    fingerprint(scope_path)
    st=scope_path.stat()
    if st.st_size>4096 or os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
        parser.error("private scope file required")
    scope=json.loads(scope_path.read_bytes())
    shard=DatasetShard(scope,args.game,create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
    result=ingest(shard,args.path,member=args.member,dataset=args.dataset,source=args.source,
        observation_digest=args.observation_digest,label=args.label,grant_seconds=args.grant_seconds,
        rights_acknowledged=True)
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
