"""Explicit operator CLI for the local memory embedding bank.

Never downloads artifacts, executes model code, or writes to a remote service.
Use a private database belonging to the exact loaded model/tokenizer scope.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.jeeves_approved_memory import ApprovedMemory, MemoryRejected
from skeleton.app.jeeves_memory_vectors import (
    ASSET_SCHEMA, MAX_FILE_BYTES, MAX_ROW_BYTES, MAX_VOCAB, MAX_DIM, MIN_DIM,
    MemoryVectorIndex, _stable_token, _vector, _normalize, _decode_json,
)

MAX_CONVERSION_INPUT = 512 * 1024 * 1024
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _validated_sha(value: str) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise MemoryRejected("expected a lowercase SHA-256")
    return value


def _canonical_line(value) -> bytes:
    line=(json.dumps(value, ensure_ascii=False, allow_nan=False,
                     separators=(",",":"), sort_keys=True)+"\n").encode("utf-8")
    if len(line)>MAX_ROW_BYTES:
        raise MemoryRejected("converted row too large")
    return line


def convert_text_vectors(source: Path, destination: Path, *, source_sha256: str,
                         name: str, dimensions: int, header: bool,
                         max_rows: int, approved: bool,
                         skip_unrepresentable: bool=False) -> dict:
    """Normalize plain whitespace-separated learned vectors into sorted JSONL.

    Use an owner-private temporary SQLite ordering stage, not an unbounded
    in-memory vocabulary or executable serialization. No overwrite and no
    partial target on a handled error. Source pin is checked over all bytes.
    A normalized duplicate is rejected rather than silently choosing a vector.
    """
    source_sha256=_validated_sha(source_sha256)
    if (approved is not True or type(header) is not bool or type(skip_unrepresentable) is not bool or
            type(dimensions) is not int or not MIN_DIM<=dimensions<=MAX_DIM or
            type(max_rows) is not int or not 1<=max_rows<=MAX_VOCAB or
            type(name) is not str or not name.strip() or "\x00" in name
            or len(name.encode("utf-8"))>200 or destination.exists()):
        raise MemoryRejected("invalid explicit vector conversion request")
    before=source.lstat()
    if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=MAX_CONVERSION_INPUT:
        raise MemoryRejected("conversion requires a bounded regular text file")
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    fd=os.open(source,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0))
    with os.fdopen(fd,"rb") as handle,tempfile.TemporaryDirectory(prefix="jeeves-vector-convert-") as stage:
        if identity(os.fstat(handle.fileno()))!=identity(before):
            raise MemoryRejected("conversion source changed while opening")
        db=sqlite3.connect(str(Path(stage)/"sort.sqlite3"))
        output_hash=sha256();input_hash=sha256()
        seen=0;admitted=0;consumed=0;expected_rows=None;unsupported=0;collisions=0
        def read_line():
            nonlocal consumed
            raw=handle.readline(MAX_ROW_BYTES+1)
            consumed+=len(raw)
            if len(raw)>MAX_ROW_BYTES or consumed>MAX_CONVERSION_INPUT:
                raise MemoryRejected("conversion source exceeds bounded input")
            input_hash.update(raw)
            return raw
        try:
            db.execute("CREATE TABLE words(token TEXT PRIMARY KEY,line BLOB NOT NULL) WITHOUT ROWID")
            if header:
                fields=read_line().decode("utf-8","strict").split()
                if len(fields)!=2 or not all(x.isascii() and x.isdecimal() for x in fields):
                    raise MemoryRejected("invalid explicit word-vector header")
                expected_rows,advertised=map(int,fields)
                if expected_rows<1 or advertised!=dimensions:
                    raise MemoryRejected("header count or dimension mismatch")
            while True:
                raw=read_line()
                if not raw:
                    break
                parts=raw.decode("utf-8","strict").split()
                if len(parts)!=dimensions+1:
                    raise MemoryRejected("vector row dimension mismatch")
                seen+=1
                # For frequency-sorted inventories, keep only an explicit
                # bounded prefix; the entire source is still hashed/read.
                values=_vector(tuple(float(x) for x in parts[1:]),dimensions)
                try:
                    token=_stable_token(_normalize(parts[0]))
                except MemoryRejected:
                    if not skip_unrepresentable:
                        raise
                    unsupported+=1
                    continue
                if admitted<max_rows:
                    line=_canonical_line([token,list(values)])
                    try:
                        db.execute("INSERT INTO words VALUES(?,?)",(token,line))
                    except sqlite3.IntegrityError:
                        if not skip_unrepresentable:
                            raise
                        # In explicit lossy mode retain the first canonical
                        # token, never silently average distinct vectors.
                        collisions+=1
                        continue
                    admitted+=1
            if (not admitted or (expected_rows is not None and seen!=expected_rows)
                    or consumed!=before.st_size or input_hash.hexdigest()!=source_sha256
                    or identity(os.fstat(handle.fileno()))!=identity(before)
                    or identity(source.lstat())!=identity(before)):
                raise MemoryRejected("conversion source inventory or digest mismatch")
            db.commit()
            header_bytes=_canonical_line({"schema":ASSET_SCHEMA,"dimensions":dimensions,
                                         "model_name":name.strip(),"vocabulary":admitted})
            # Stage and fsync output before atomic exclusive publication.
            # os.link fails if the requested destination already exists.
            out_size=0
            dst_parent=destination.parent
            if not dst_parent.is_dir():
                raise MemoryRejected("destination parent does not exist")
            tmp_fd,tmp_name=tempfile.mkstemp(prefix=".jeeves-vectors-",dir=dst_parent)
            tmp=Path(tmp_name)
            try:
                with os.fdopen(tmp_fd,"wb") as out:
                    def write(line):
                        nonlocal out_size
                        out_size+=len(line)
                        if out_size>MAX_FILE_BYTES:
                            raise MemoryRejected("converted asset exceeds install byte budget")
                        output_hash.update(line);out.write(line)
                    write(header_bytes)
                    for (line,) in db.execute("SELECT line FROM words ORDER BY token"):
                        write(line)
                    out.flush();os.fsync(out.fileno())
                os.link(tmp,destination)
            finally:
                tmp.unlink(missing_ok=True)
        except (sqlite3.IntegrityError,UnicodeError,ValueError,OverflowError):
            raise MemoryRejected("malformed vector row or duplicate admitted token") from None
        finally:
            db.close()
    return {"schema":ASSET_SCHEMA,"source_sha256":source_sha256,
            "asset_sha256":output_hash.hexdigest(),"dimensions":dimensions,
            "input_rows":seen,"admitted_rows":admitted,"bytes":out_size,
            "unsupported_tokens_skipped":unsupported,"admitted_prefix_collisions_skipped":collisions,
            "lossy_token_conversion":skip_unrepresentable,
            "network_used":False,"semantic_quality_certified":False}


def _print(value):
    print(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False))


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    convert=sub.add_parser("convert")
    convert.add_argument("--source",type=Path,required=True)
    convert.add_argument("--destination",type=Path,required=True)
    convert.add_argument("--source-sha256",required=True)
    convert.add_argument("--name",required=True)
    convert.add_argument("--dimensions",type=int,required=True)
    convert.add_argument("--header",action="store_true")
    convert.add_argument("--max-rows",type=int,default=MAX_VOCAB)
    convert.add_argument("--approve",action="store_true")
    convert.add_argument("--skip-unrepresentable",action="store_true",
                         help="Explicitly skip nonword tokens and keep first normalized duplicate.")
    for command in ("status","install","refresh","uninstall"):
        p=sub.add_parser(command)
        p.add_argument("--database",type=Path,required=True)
        p.add_argument("--model-digest",required=True)
        p.add_argument("--tokenizer-digest",required=True)
        if command!="status":
            p.add_argument("--approve",action="store_true")
            p.add_argument("--asset-sha256",required=True)
        if command=="install":
            p.add_argument("--asset",type=Path,required=True)
            p.add_argument("--expected-prior")
        if command=="refresh":
            p.add_argument("--limit",type=int,default=64)
            p.add_argument("--cursor")
    args=parser.parse_args(argv)
    try:
        if args.command=="convert":
            _print(convert_text_vectors(args.source,args.destination,
                source_sha256=args.source_sha256,name=args.name,dimensions=args.dimensions,
                header=args.header,max_rows=args.max_rows,approved=args.approve,
                skip_unrepresentable=args.skip_unrepresentable))
            return 0
        model=_validated_sha(args.model_digest)
        tokenizer=_validated_sha(args.tokenizer_digest)
        # Do not silently manufacture a new chat database on a typo.
        if not args.database.is_file():
            raise MemoryRejected("existing canonical chat database required")
        with OfflineChatStore(args.database) as store:
            index=MemoryVectorIndex(ApprovedMemory(store,model,tokenizer))
            if args.command=="status":
                result=index.status()
            elif args.command=="install":
                result=index.install(args.asset,args.asset_sha256,approved=args.approve,
                                     expected_prior=args.expected_prior)
            elif args.command=="refresh":
                result=index.refresh(cursor=args.cursor,limit=args.limit,approved=args.approve,
                                     expected_asset=args.asset_sha256)
            else:
                result=index.uninstall(args.asset_sha256,approved=args.approve)
            _print(result)
        return 0
    except (MemoryRejected,OSError,ValueError,sqlite3.Error,OverflowError):
        print("Vector operation held: approval, source identity, storage or format was rejected.",
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
