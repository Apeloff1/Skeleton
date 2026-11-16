"""Measured configured-device capacity preflight and non-sparse scratch I/O.

Never equates free space or bounded scratch throughput with sustained maximum
ingestion capacity. No writes unless the independent scratch acknowledgement
is explicit. All paths come from existing configured storage inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from uuid import uuid4

from core import dragon_ecosystem_custody as ecosystem
from core import dragon_graph_deployment as custody
from core.dragon_owner_shards import _private

BLOCK=1024*1024
MAX_DEVICES=64
MAX_PER_DEVICE=256*BLOCK
MAX_TOTAL_SCRATCH=4*1024*BLOCK


def _devices():
    groups={}
    for plane,path in ecosystem._enumerate():
        path=Path(path);stat=path.stat();device=stat.st_dev
        if device not in groups:
            if len(groups)>=MAX_DEVICES:raise ValueError("configured device count cap")
            groups[device]={"device":device,"folder":path.parent,"files":0,
                            "configured_bytes":0,"planes":set()}
        item=groups[device];item["files"]+=1;item["configured_bytes"]+=stat.st_size
        item["planes"].add(plane)
    return groups


def plan(*,growth_factor=2):
    if type(growth_factor) is not int or not 1<=growth_factor<=1000:
        raise ValueError("growth factor bound")
    groups=_devices();rows=[]
    for device,g in sorted(groups.items()):
        usage=shutil.disk_usage(g["folder"])
        extra=g["configured_bytes"]*(growth_factor-1)
        rows.append({"device":device,"files":g["files"],"planes":sorted(g["planes"]),
                     "configured_bytes":g["configured_bytes"],"device_total_bytes":usage.total,
                     "device_free_bytes":usage.free,"additional_required_bytes":extra,
                     "reserve_bytes":custody.RESERVE,"growth_headroom_sufficient":usage.free>=extra+custody.RESERVE})
    return {"growth_factor":growth_factor,"devices":rows,
            "growth_headroom_sufficient":all(r["growth_headroom_sufficient"] for r in rows),
            "physical_maximum_capacity_verified":False,"production_throughput_verified":False}


def _probe(folder,size,device):
    folder=custody._dir(folder)
    if folder.stat().st_dev!=device:raise custody.DeploymentHeld("device topology changed")
    custody._require_space([(folder,size)])
    path=folder/(".dragon-capacity-"+uuid4().hex)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    identity=None
    try:
        identity=_private(path)[1]
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)!=identity:raise custody.DeploymentHeld("scratch identity changed")
        expected=hashlib.sha256();start=time.perf_counter()
        with os.fdopen(fd,"wb") as out:
            fd=-1;left=size
            while left:
                data=os.urandom(min(BLOCK,left));out.write(data);expected.update(data);left-=len(data)
            out.flush();os.fsync(out.fileno())
        write=max(time.perf_counter()-start,1e-9)
        start=time.perf_counter();actual=custody._fingerprint(path)
        read=max(time.perf_counter()-start,1e-9)
        if actual!={"bytes":size,"sha256":expected.hexdigest()}:
            raise custody.DeploymentHeld("device probe readback differs")
        result={"device":device,"bytes":size,"write_fsync_seconds":write,
                "read_hash_seconds":read,"write_mib_s":size/BLOCK/write,"read_mib_s":size/BLOCK/read,
                "readback_verified":True}
    finally:
        if fd!=-1:os.close(fd)
        if identity is None or _private(path)[1]!=identity:
            raise custody.DeploymentHeld("scratch identity cleanup held")
        path.unlink();custody._sync_dir(folder)
    return {**result,"cleanup_verified":True}


def qualify(*,growth_factor=2,bytes_per_device=16*BLOCK,rounds=3,scratch_acknowledged=False):
    if scratch_acknowledged is not True:raise ValueError("explicit scratch I/O permission required")
    if type(bytes_per_device) is not int or not BLOCK<=bytes_per_device<=MAX_PER_DEVICE or type(rounds) is not int or not 1<=rounds<=16:
        raise ValueError("scratch work bounds")
    baseline=plan(growth_factor=growth_factor);groups=_devices()
    if set(groups)!={x["device"] for x in baseline["devices"]}:
        raise custody.DeploymentHeld("configured device inventory changed")
    if len(groups)*rounds*bytes_per_device>MAX_TOTAL_SCRATCH:raise ValueError("aggregate scratch work cap")
    probes=[]
    for device,g in sorted(groups.items()):
        for ordinal in range(rounds):
            probes.append({"round":ordinal,**_probe(g["folder"],bytes_per_device,device)})
    final=plan(growth_factor=growth_factor)
    if [(x["device"],x["configured_bytes"],x["files"]) for x in baseline["devices"]] != [
            (x["device"],x["configured_bytes"],x["files"]) for x in final["devices"]]:
        raise custody.DeploymentHeld("configured storage inventory changed during probe")
    return {**final,"probes":probes,"scratch_bytes_verified":sum(x["bytes"] for x in probes),
            "bounded_device_io_verified":True,"power_loss_verified":False,
            "production_ingestion_throughput_verified":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--growth-factor",type=int,default=2)
    p.add_argument("--probe",action="store_true")
    p.add_argument("--bytes-per-device",type=int,default=16*BLOCK)
    p.add_argument("--rounds",type=int,default=3)
    p.add_argument("--acknowledge-scratch-writes",action="store_true")
    a=p.parse_args(argv)
    if a.probe:
        result=qualify(growth_factor=a.growth_factor,bytes_per_device=a.bytes_per_device,
                       rounds=a.rounds,scratch_acknowledged=a.acknowledge_scratch_writes)
    else:result=plan(growth_factor=a.growth_factor)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
