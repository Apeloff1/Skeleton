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
import re
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


def raw_sha256(path,witness):
    """Witness the entire container, not just its selected data member."""
    h=hashlib.sha256()
    with source_stream(path,None,witness) as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def plan(path,member=None,*,expected_sha=None):
    if expected_sha is not None and (not isinstance(expected_sha,str)
            or not re.fullmatch(r"[a-f0-9]{64}",expected_sha)):
        raise ValueError("expected dataset SHA-256 must be lowercase hex")
    path=Path(path)
    witness=fingerprint(path)
    source_sha=raw_sha256(path,witness)
    if expected_sha is not None and source_sha!=expected_sha:
        raise ValueError("raw dataset SHA-256 differs")
    chain=ZERO;rows=count=0
    for count0,(raw,n) in enumerate(pages(path,member,witness)):
        if len(parse_page(raw))!=n:raise ValueError("page validation")
        chain=chain_step(chain,hashlib.sha256(raw).hexdigest(),count0,n)
        rows+=n;count=count0+1
    if not rows:raise ValueError("empty dataset")
    if raw_sha256(path,witness)!=source_sha:
        raise ValueError("raw dataset changed during projection")
    return {"file_identity":witness,"expected_rows":rows,"expected_chain":chain,"pages":count,
            "input_sha256":source_sha,"expected_sha_matched":expected_sha is not None}


def _inspection_identity(info,member):
    raw=json.dumps(["skeleton.dragon.dataset-inspection.v1",member,
                    info["input_sha256"],info["expected_rows"],info["expected_chain"],info["pages"]],
                   ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect_dataset(path,member=None,*,expected_sha=None):
    """Inspect a separately supplied file without opening dataset storage."""
    info=plan(path,member,expected_sha=expected_sha)
    return {"schema":"skeleton.dragon.dataset-inspection.v1",
            "inspection_digest":_inspection_identity(info,member),
            "input_sha256":info["input_sha256"],
            "expected_sha_matched":info["expected_sha_matched"],
            "expected_rows":info["expected_rows"],"expected_chain":info["expected_chain"],
            "pages":info["pages"],"container_member_selected":member is not None,
            "network_executed":False,"storage_written":False,"rights_reviewed":False}


def ingest(shard,path,*,member=None,dataset,source,observation_digest,label,
           rights_acknowledged,grant_seconds=86400,corpus=None,expected_sha=None,
           expected_inspection=None,shard_factory=None):
    if (shard is None)==(shard_factory is None):
        raise ValueError("exactly one dataset shard or shard factory required")
    if rights_acknowledged is not True:
        raise ValueError("explicit data-retention rights required")
    path=Path(path)
    if expected_inspection is not None and (not isinstance(expected_inspection,str)
            or not re.fullmatch(r"[a-f0-9]{64}",expected_inspection)):
        raise ValueError("expected inspection digest must be lowercase hex")
    info=plan(path,member,expected_sha=expected_sha)
    inspection=_inspection_identity(info,member)
    if expected_inspection is not None and expected_inspection!=inspection:
        raise ValueError("dataset inspection digest differs; storage untouched")
    if shard is None:shard=shard_factory()
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
    if ((rows,chain,count)!=(info["expected_rows"],info["expected_chain"],info["pages"])
            or raw_sha256(path,info["file_identity"])!=info["input_sha256"]):
        raise ValueError("dataset changed between passes; never seal")
    final=shard.seal(version)
    return {**final,"pages_verified":count,"input_sha256":info["input_sha256"],
            "inspection_digest":inspection,"expected_inspection_matched":expected_inspection is not None,
            "expected_sha_matched":info["expected_sha_matched"],"network_executed":False,
            "physical_capacity_verified":False,"rights_reviewed":False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-json",help="Private operator-owned scope JSON file")
    parser.add_argument("--game")
    parser.add_argument("--source")
    parser.add_argument("--observation-digest")
    parser.add_argument("--dataset")
    parser.add_argument("--label")
    parser.add_argument("--inspect-only",action="store_true")
    parser.add_argument("--expected-inspection",help="Exact digest of prior read-only inspection")
    parser.add_argument("--path",required=True)
    parser.add_argument("--member")
    parser.add_argument("--expected-sha",help="Optional expected SHA-256 of the entire local file")
    parser.add_argument("--grant-seconds",type=int,default=86400)
    parser.add_argument("--acknowledge-retention-rights",action="store_true")
    args=parser.parse_args(argv)
    scope_fields=(args.scope_json,args.game,args.source,args.observation_digest,args.dataset,args.label)
    if args.inspect_only:
        if any(x is not None for x in scope_fields+(args.expected_inspection,)) or args.acknowledge_retention_rights:
            parser.error("inspection cannot include storage scope or import authority")
        print(json.dumps(inspect_dataset(args.path,args.member,expected_sha=args.expected_sha),sort_keys=True))
        return 0
    if not all(scope_fields):parser.error("import requires explicit scope and dataset binding")
    if not args.acknowledge_retention_rights:parser.error("explicit retention acknowledgement is required")
    scope_path=Path(args.scope_json)
    fingerprint(scope_path)
    st=scope_path.stat()
    if st.st_size>4096 or os.name=="posix" and (st.st_uid!=os.getuid() or st.st_mode&0o077):
        parser.error("private scope file required")
    scope=json.loads(scope_path.read_bytes())
    def shard_factory():
        return DatasetShard(scope,args.game,create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
    result=ingest(None,args.path,shard_factory=shard_factory,member=args.member,dataset=args.dataset,source=args.source,
        observation_digest=args.observation_digest,label=args.label,grant_seconds=args.grant_seconds,
        rights_acknowledged=True,expected_sha=args.expected_sha,expected_inspection=args.expected_inspection)
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
