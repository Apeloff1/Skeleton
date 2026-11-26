"""Measure actual serial versus batch CDC archive operations with identical bytes.

The existing archive ledger, physical volume implementation, durable writes,
digest checks and readback are used. No production archive is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

from core.dragon_content_chunks import lengths,split
from core.dragon_hoarder_bulk import BulkArchive,Volume,GIB
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_chunk_qualification import fixture

SCOPE={"owner_id":"batch-qualification","tenant_id":"scratch-only"}
MIB=1024*1024
MAX_LOGICAL=2*GIB


def _trial(root,*,families,revisions,size,batch,family_start=0):
    root.mkdir(mode=0o700)
    # One volume per physical filesystem is a production invariant. A CI
    # scratch folder cannot simulate independent devices with two directories.
    paths=[root/"volume-a"]
    for path in paths:path.mkdir(mode=0o700)
    specs=tuple(Volume("volume-"+str(i),path,GIB+families*revisions*(size+1024))
                for i,path in enumerate(paths))
    ledger=root/"manifest.sqlite3"
    def open_store():return ManifestArchive(ledger,BulkArchive(specs))
    store=open_store();records=[];calls=0;logical=0;write=0.;seal=0.
    for family in range(family_start,family_start+families):
        for revision in range(revisions):
            raw=fixture(family,revision,size)
            layout=lengths(raw);parts=list(split(raw,layout))
            checksum=hashlib.sha256(raw).hexdigest()
            identifier=store.begin(SCOPE,logical_key="family-"+str(family),operation="revision-"+str(revision),
                expected_hash=checksum,expected_bytes=len(raw),chunk_lengths=layout)["manifest"]
            start=time.perf_counter()
            if batch:
                for offset in range(0,len(parts),128):
                    store.append_many(SCOPE,identifier,offset,parts[offset:offset+128]);calls+=1
            else:
                for i,part in enumerate(parts):
                    store.append(SCOPE,identifier,i,part);calls+=1
            write+=time.perf_counter()-start
            start=time.perf_counter()
            receipt=store.seal(SCOPE,identifier)
            seal+=time.perf_counter()-start
            if receipt["sha256"]!=checksum or receipt["bytes"]!=len(raw):
                raise RuntimeError("archive publication witness changed")
            records.append((family,revision,identifier,checksum,len(parts)))
            logical+=len(raw)
    store=open_store()
    read=0.;read_calls=0
    for family,revision,identifier,checksum,count in records:
        start=time.perf_counter()
        if batch:
            raw=store.read_document(SCOPE,identifier);read_calls+=1
        else:
            raw=b"".join(store.read_chunk(SCOPE,identifier,i) for i in range(count));read_calls+=count
        read+=time.perf_counter()-start
        if hashlib.sha256(raw).hexdigest()!=checksum or raw!=fixture(family,revision,size):
            raise RuntimeError("restart readback differs")
    # Both trials exercise deletion of one live manifest and ensure that
    # deduplicated objects needed by the remaining revisions survive it.
    _,_,removed,_,_=records[0]
    store.abort(SCOPE,removed)
    while store.collect_manifest(SCOPE,removed,limit=128)["remaining"]:
        pass
    for family,revision,identifier,checksum,_ in records[1:]:
        raw=store.read_document(SCOPE,identifier)
        if raw!=fixture(family,revision,size) or hashlib.sha256(raw).hexdigest()!=checksum:
            raise RuntimeError("reference-aware collection changed another revision")
    usage=store.usage(SCOPE);physical=0
    for file in [ledger]+[path/"hoarder-payload-v1.sqlite3" for path in paths]:
        with sqlite3.connect(file) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("archive integrity check failed")
            if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
                raise RuntimeError("archive WAL checkpoint held")
        physical+=file.stat().st_size
    return {"logical_bytes":logical,"manifest_count":len(records),"append_api_calls":calls,
        "read_api_calls":read_calls,"write_seconds":round(write,6),"seal_seconds":round(seal,6),
        "read_seconds":round(read,6),"write_mib_s":round(logical/MIB/max(write,1e-9),6),
        "read_mib_s":round(logical/MIB/max(read,1e-9),6),"post_collection_unique_chunks":usage["unique_chunks"],
        "post_collection_compressed_bytes":usage["unique_compressed_bytes"],
        "physical_database_bytes":physical,"restart_readback_verified":True,
        "reference_collection_verified":True,"integrity_check_verified":True}


def qualify(folder,*,families=8,revisions=3,size=512*1024,family_start=0,approved=False):
    if approved is not True:raise ValueError("explicit scratch writes required")
    if (type(families) is not int or not 1<=families<=256 or type(revisions) is not int
            or not 2<=revisions<=16 or type(size) is not int or not 256*1024<=size<=3*MIB
            or type(family_start) is not int or not 0<=family_start<=1000000-families
            or families*revisions*(size+1024)*2>MAX_LOGICAL):
        raise ValueError("qualification workload bound")
    folder=Path(folder).resolve(strict=True)
    free=shutil.disk_usage(folder).free
    if free<2*GIB+families*revisions*(size+1024)*8:
        raise OSError("scratch reserve held")
    with tempfile.TemporaryDirectory(prefix="dragon-batch-",dir=folder) as temp:
        root=Path(temp)
        serial=_trial(root/"serial",families=families,revisions=revisions,size=size,batch=False,family_start=family_start)
        batched=_trial(root/"batched",families=families,revisions=revisions,size=size,batch=True,family_start=family_start)
    for key in ("logical_bytes","manifest_count","post_collection_unique_chunks","post_collection_compressed_bytes"):
        if serial[key]!=batched[key]:raise RuntimeError("archive equivalence differs")
    result={"schema":"skeleton.dragon.batch-io-qualification.v1","families":families,"family_start":family_start,"revisions":revisions,
        "serial":serial,"batched":batched,"append_call_reduction":serial["append_api_calls"]-batched["append_api_calls"],
        "read_call_reduction":serial["read_api_calls"]-batched["read_api_calls"],
        "write_speed_ratio":round(batched["write_mib_s"]/max(serial["write_mib_s"],1e-9),6),
        "read_speed_ratio":round(batched["read_mib_s"]/max(serial["read_mib_s"],1e-9),6),
        "same_device":folder.stat().st_dev,"scratch_cleanup_verified":not root.exists(),
        "production_capacity_verified":False,"production_archive_modified":False,
        "power_loss_verified":False,"independent_devices_verified":False}
    return {**result,"receipt":hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":")).encode()).hexdigest()}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch-directory",required=True);p.add_argument("--families",type=int,default=8)
    p.add_argument("--revisions",type=int,default=3);p.add_argument("--size",type=int,default=512*1024)
    p.add_argument("--family-start",type=int,default=0)
    p.add_argument("--acknowledge-scratch-writes",action="store_true")
    a=p.parse_args(argv)
    result=qualify(a.scratch_directory,families=a.families,revisions=a.revisions,size=a.size,
                   family_start=a.family_start,approved=a.acknowledge_scratch_writes)
    print("DRAGON_BATCH_COMPARATIVE_RECEIPT "+json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
