"""Operator-run physical storage acceptance, not a simulated capacity claim.

Receipt is emitted only after real random-byte writes, reopen/readback, owner
isolation and deletion on every configured physical device. It qualifies the
measured probe workload, not maximum storage capacity or failure independence.
The private operator is trusted; this is not a remote attestation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from uuid import uuid4

from core.dragon_hoarder_bulk import BulkArchive,Volume,StorageHeld,GIB
from core.dragon_hoarder_manifests import ManifestArchive

MIN_PROBE=16*1024**2
MAX_PROBE=GIB
CHUNK=2*1024**2
MAX_AGE=7*86400
SCHEMA="dragon.physical-qualification.v1"


def topology(archive):
    return [{"name":v.name,"dev":v.root.stat().st_dev,"inode":v.root.stat().st_ino,
             "root":str(v.root),"budget":v.payload_budget,"reserve":v.free_reserve}
            for v in sorted(archive.bulk.volumes.values(),key=lambda x:x.name)]


def open_backup():
    raw=os.environ.get("SKL_DRAGON_HOARDER_BACKUP_VOLUMES_JSON","").strip()
    path=Path(os.environ.get("SKL_DRAGON_HOARDER_BACKUP_MANIFEST_PATH",""))
    if not raw or len(raw)>262144 or not path.is_absolute():
        raise StorageHeld("configure independent backup volumes")
    specs=json.loads(raw)
    if not isinstance(specs,list) or not 1<=len(specs)<=256:
        raise ValueError("backup volume count")
    volumes=[]
    bootstrap=os.getenv("SKL_DRAGON_HOARDER_BOOTSTRAP")=="1"
    for item in specs:
        if not isinstance(item,dict) or not {"name","root","payload_budget"}<=set(item) or set(item)-{"name","root","payload_budget","free_reserve"}:
            raise ValueError("backup volume specification")
        vol=Volume(**{**item,"root":Path(item["root"])})
        if not bootstrap and not (vol.root/"hoarder-payload-v1.sqlite3").is_file():
            raise StorageHeld("backup volume uninitialized")
        volumes.append(vol)
    if not bootstrap and not path.is_file():raise StorageHeld("backup manifest uninitialized")
    return ManifestArchive(path,BulkArchive(tuple(volumes)))


def independent(primary,backup):
    a=topology(primary);b=topology(backup)
    if {v["dev"] for v in a}&{v["dev"] for v in b}:
        raise StorageHeld("primary and backup payload devices must differ")
    if primary.path.resolve()==backup.path.resolve() or primary.path.stat().st_dev==backup.path.stat().st_dev:
        raise StorageHeld("primary and backup ledger devices must differ")
    return {"primary":a,"backup":b,"primary_ledger_device":primary.path.stat().st_dev,
            "backup_ledger_device":backup.path.stat().st_dev}


def _receipt_path():
    raw=os.environ.get("SKL_DRAGON_HOARDER_QUALIFICATION_PATH","").strip()
    path=Path(raw)
    if not raw or not path.is_absolute() or path.parent.resolve(strict=True)!=path.parent or path.is_symlink():
        raise StorageHeld("private qualification path required")
    parent=path.parent.stat()
    if os.name=="posix" and (parent.st_uid!=os.getuid() or parent.st_mode&0o077):
        raise StorageHeld("qualification directory is not private")
    return path


def _probe(archive,volume,probe_bytes,scope):
    start=time.monotonic()
    n=probe_bytes//CHUNK
    receipts=[]
    write_seconds=read_seconds=0.0
    result=None
    try:
        # Bounded concurrency: real incompressible unique objects on this volume.
        def write(ordinal):
            raw=os.urandom(CHUNK)
            receipt=archive.bulk.put(volume,scope,raw)
            if receipt.digest!=hashlib.sha256(raw).hexdigest():raise StorageHeld("write witness")
            return receipt
        t=time.monotonic()
        # Sequential receipt collection ensures every successful write remains
        # accounted for even if a subsequent block fails.
        for ordinal in range(n):
            receipts.append(write(ordinal))
        write_seconds=time.monotonic()-t
        reopened=BulkArchive(tuple(archive.bulk.volumes.values()))
        def read(receipt):
            raw=reopened.read(scope,receipt)
            if len(raw)!=CHUNK or hashlib.sha256(raw).hexdigest()!=receipt.digest:
                raise StorageHeld("reopen witness")
            return len(raw)
        t=time.monotonic()
        with ThreadPoolExecutor(max_workers=2) as executor:
            read_bytes=sum(executor.map(read,receipts))
        read_seconds=time.monotonic()-t
        denied=False
        try:reopened.read({**scope,"owner_id":"unrelated-probe"},receipts[0])
        except (StorageHeld,ValueError,LookupError):denied=True
        if not denied or read_bytes!=probe_bytes:raise StorageHeld("probe isolation or length")
        result={"volume":volume,"bytes_written":probe_bytes,"bytes_verified_after_reopen":read_bytes,
                "blocks":n,"owner_isolation":True,"write_seconds":round(write_seconds,6),
                "read_seconds":round(read_seconds,6)}
    finally:
        for receipt in receipts:
            if not archive.bulk.erase_unreferenced(scope,receipt):
                raise StorageHeld("probe cleanup not confirmed")
            if archive.bulk.lookup(receipt.volume,scope,receipt.digest) is not None:
                raise StorageHeld("probe remains")
    if result is None:raise StorageHeld("probe incomplete")
    return {**result,"logical_cleanup_verified":True,"elapsed_seconds":round(time.monotonic()-start,6)}


def run_probe(primary,backup,*,probe_bytes=64*1024**2):
    if type(probe_bytes) is not int or not MIN_PROBE<=probe_bytes<=MAX_PROBE or probe_bytes%CHUNK:
        raise ValueError("probe bytes must be an integral 2 MiB block count")
    config=independent(primary,backup)
    path=_receipt_path()
    # Invalidate earlier receipt before starting new physical acceptance.
    if path.exists():path.unlink()
    scope={"tenant_id":"dragon-qualification-"+uuid4().hex,"owner_id":"operator-probe"}
    details=[]
    for lane,archive in (("primary",primary),("backup",backup)):
        for volume in sorted(archive.bulk.volumes):
            details.append({"lane":lane,**_probe(archive,volume,probe_bytes,scope)})
    result={"schema":SCHEMA,"created_at":int(time.time()),"topology":config,
            "probe_bytes_per_volume":probe_bytes,"devices":details,
            "max_capacity_verified":False,"physical_secure_erasure":False,
            "crash_power_loss_verified":False,"failure_domain_independence_verified":False}
    if independent(primary,backup)!=config:raise StorageHeld("topology changed during probe")
    raw=json.dumps(result,sort_keys=True,separators=(",",":")).encode()
    temp=path.parent/("."+path.name+"."+uuid4().hex)
    fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
        if os.name=="posix":
            directory=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
    finally:
        if temp.exists():temp.unlink()
    return result


def require_probe(primary,backup):
    path=_receipt_path()
    st=path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size>2*1024*1024 or st.st_nlink!=1 or os.name=="posix" and (st.st_mode&0o077 or st.st_uid!=os.getuid()):
        raise StorageHeld("qualification receipt custody")
    value=json.loads(path.read_bytes())
    now=int(time.time())
    if value.get("schema")!=SCHEMA or type(value.get("created_at")) is not int or not 0<=now-value["created_at"]<=MAX_AGE:
        raise StorageHeld("physical qualification missing or stale")
    topology_now=independent(primary,backup)
    if value.get("topology")!=topology_now:raise StorageHeld("qualification topology changed")
    expected={(lane,v["name"]) for lane in ("primary","backup") for v in topology_now[lane]}
    rows=value.get("devices")
    n=value.get("probe_bytes_per_volume")
    if type(n) is not int or not MIN_PROBE<=n<=MAX_PROBE or not isinstance(rows,list) or len(rows)!=len(expected):
        raise StorageHeld("probe incomplete")
    if {(x.get("lane"),x.get("volume")) for x in rows}!=expected or any(
        x.get("bytes_written")!=n or x.get("bytes_verified_after_reopen")!=n or x.get("owner_isolation") is not True
        or x.get("logical_cleanup_verified") is not True for x in rows):
        raise StorageHeld("probe evidence differs")
    return {"qualified_at":value["created_at"],"probe_bytes_per_volume":n,
            "receipt_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"max_capacity_verified":False}


def main():
    from core.dragon_hoarder_copy import _archive
    parser=argparse.ArgumentParser(description="Run actual Hoarder physical device qualification.")
    parser.add_argument("--probe-mib",type=int,default=64)
    args=parser.parse_args()
    print(json.dumps(run_probe(_archive(),open_backup(),probe_bytes=args.probe_mib*1024**2),indent=2))


if __name__=="__main__":main()
