"""Physical, non-production scratch qualification of Hoarder variable chunks.

Run under an explicitly selected private directory. Both fixed and
content-defined representations are written, fsynced by SQLite, reopened and
verified across exact payloads. This does not modify the configured archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

from core.dragon_content_chunks import lengths,split
from core.dragon_hoarder_bulk import BulkArchive,Volume,GIB
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK

MIB=1024*1024
MAX_WORK=4*GIB
SCOPE={"owner_id":"chunk-qualification","tenant_id":"scratch-only"}


def fixture(family,revision,size):
    # Deterministic high-entropy source with a small inserted revision. Its
    # bytes are actual allocations, not sparse files or zero-filled samples.
    baseline=hashlib.shake_256(f"dragon-family-{family}".encode()).digest(size)
    if revision==0:return baseline
    patch=hashlib.shake_256(f"revision-{family}-{revision}".encode()).digest(257+revision*17)
    offset=size//3
    return baseline[:offset]+patch+baseline[offset:]


def trial(root,*,families,revisions,size,adaptive):
    volume=root/"volume";volume.mkdir(mode=0o700)
    ledger=root/"manifests.sqlite3"
    spec=Volume("scratch",volume,max(GIB,families*revisions*(size+1024)*2))
    def reopen():
        return ManifestArchive(ledger,BulkArchive((spec,)))
    archive=reopen()
    receipts=[];logical=0;write_start=time.perf_counter()
    for family in range(families):
        for revision in range(revisions):
            raw=fixture(family,revision,size);logical+=len(raw)
            checksum=hashlib.sha256(raw).hexdigest()
            layout=lengths(raw) if adaptive else None
            begun=archive.begin(SCOPE,logical_key=f"family-{family}",operation=f"revision-{revision}",
                expected_hash=checksum,expected_bytes=len(raw),chunk_lengths=layout)
            parts=split(raw,layout) if adaptive else (raw[i:i+BLOCK] for i in range(0,len(raw),BLOCK))
            for ordinal,part in enumerate(parts):
                archive.append(SCOPE,begun["manifest"],ordinal,part)
            receipt=archive.seal(SCOPE,begun["manifest"])
            if receipt["sha256"]!=checksum or receipt["bytes"]!=len(raw):
                raise RuntimeError("write witness differs")
            receipts.append((family,revision,receipt))
    write=max(time.perf_counter()-write_start,1e-9)
    archive=reopen()
    read_start=time.perf_counter()
    for family,revision,row in receipts:
        data=b"".join(archive.read_chunk(SCOPE,row["manifest"],i) for i in range(row["chunks"]))
        if data!=fixture(family,revision,size) or hashlib.sha256(data).hexdigest()!=row["sha256"]:
            raise RuntimeError("physical revision reconstruction differs")
    read=max(time.perf_counter()-read_start,1e-9)
    usage=archive.usage(SCOPE)
    physical=0
    for file in (ledger,volume/"hoarder-payload-v1.sqlite3"):
        with sqlite3.connect(file) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("physical SQLite integrity failed")
            if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
                raise RuntimeError("physical checkpoint busy")
        physical+=file.stat().st_size
    # Abort one revision and perform ledger-aware collection; every remaining
    # reference must read identically even if chunks were shared.
    removed=receipts[0][2]["manifest"];archive.abort(SCOPE,removed)
    while True:
        result=archive.collect_manifest(SCOPE,removed,limit=128)
        if not result["remaining"]:break
    for family,revision,row in receipts[1:]:
        actual=b"".join(archive.read_chunk(SCOPE,row["manifest"],i) for i in range(row["chunks"]))
        if actual!=fixture(family,revision,size):
            raise RuntimeError("shared reference damaged by collection")
    return {"logical_bytes":logical,"physical_database_bytes":physical,
        "unique_raw_bytes":usage["unique_raw_bytes"],"unique_compressed_bytes":usage["unique_compressed_bytes"],
        "unique_chunks":usage["unique_chunks"],"manifests":len(receipts),
        "write_seconds":round(write,6),"read_seconds":round(read,6),
        "write_mib_s":round(logical/MIB/write,4),"read_mib_s":round(logical/MIB/read,4),
        "restart_readback_verified":True,"reference_collection_verified":True}


def qualify(directory,*,families=4,revisions=3,size=512*1024,scratch_acknowledged=False):
    if scratch_acknowledged is not True:raise ValueError("explicit scratch writes required")
    if (type(families) is not int or not 1<=families<=256 or type(revisions) is not int
            or not 2<=revisions<=16 or type(size) is not int or not 256*1024<=size<=3*MIB
            or families*revisions*(size+1024)*2>MAX_WORK):
        raise ValueError("qualification workload bound")
    directory=Path(directory).resolve(strict=True)
    if not directory.is_dir():raise ValueError("scratch directory required")
    required=2*GIB+families*revisions*(size+1024)*6
    if shutil.disk_usage(directory).free<required:
        raise OSError("qualification scratch reserve held")
    with tempfile.TemporaryDirectory(prefix="dragon-physical-",dir=directory) as temp:
        root=Path(temp)
        fixed=root/"fixed";fixed.mkdir(mode=0o700)
        adaptive=root/"adaptive";adaptive.mkdir(mode=0o700)
        legacy=trial(fixed,families=families,revisions=revisions,size=size,adaptive=False)
        cdc=trial(adaptive,families=families,revisions=revisions,size=size,adaptive=True)
    receipt={"families":families,"revisions":revisions,"base_bytes_per_family":size,
        "legacy_fixed":legacy,"content_defined":cdc,
        "compressed_payload_bytes_saved":legacy["unique_compressed_bytes"]-cdc["unique_compressed_bytes"],
        "physical_database_bytes_saved":legacy["physical_database_bytes"]-cdc["physical_database_bytes"],
        "tested_device":directory.stat().st_dev,"scratch_cleanup_verified":not root.exists(),
        "power_loss_verified":False,"production_workload_verified":False,"production_archive_modified":False}
    canonical=json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False)
    return {**receipt,"receipt":hashlib.sha256(canonical.encode()).hexdigest()}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch-directory",required=True)
    p.add_argument("--families",type=int,default=4)
    p.add_argument("--revisions",type=int,default=3)
    p.add_argument("--size",type=int,default=512*1024)
    p.add_argument("--acknowledge-scratch-writes",action="store_true")
    a=p.parse_args(argv)
    result=qualify(a.scratch_directory,families=a.families,revisions=a.revisions,size=a.size,
                   scratch_acknowledged=a.acknowledge_scratch_writes)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
