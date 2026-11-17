"""Explicit on-device Dragon/Jeeves live and physical qualification.

No model download, cloud fallback, live crawl or production data writes.
Checks a real local-only Jeeves service and separately trained Dragon
specialist, and measures private scratch I/O on configured storage devices.
An operator chooses measurable acceptance targets and must approve both
workloads. This is a device qualification, not a release certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

from scripts.dragon_local_navigation_discourse import load_token,request_discourse
from skeleton.ai.webcrawler.navigation_semantics import digest
from core.dragon_capacity_qualification import plan as capacity_plan,qualify as capacity_qualify,_devices
from core.dragon_chunk_qualification import qualify as chunk_qualify

ROOT=Path(__file__).resolve().parents[1]
HEX=re.compile(r"[a-f0-9]{64}\Z")
MIB=1024*1024
TASKS=(
    (("flight","navigation"),(("flight","navigation","manual"),("flight","navigation","tutorial"),
        ("aerodynamics","flight"),("garden","soil"),("auction","trade"),("flight","weather")),(3,3,2,0,0,1)),
    (("rendering","shader"),(("shader","rendering","manual"),("rendering","shader","pipeline"),
        ("lighting","graphics"),("finance","market"),("garden","tree"),("rendering","texture")),(3,3,2,0,0,1)),
    (("backup","recovery"),(("backup","recovery","manual"),("restore","backup","recovery"),
        ("persistence","checkpoint"),("combat","sword"),("music","song"),("recovery","diagnostic")),(3,3,2,0,0,1)),
    (("inventory","crafting"),(("inventory","crafting","manual"),("crafting","inventory","recipes"),
        ("loot","equipment"),("physics","gravity"),("transport","rail"),("inventory","storage")),(3,3,2,0,0,1)),
)


def exact_head(expected):
    if not isinstance(expected,str) or not HEX.fullmatch(expected):
        # Git SHA-1 is forty hexadecimal characters, SHA-256 is sixty-four.
        if not isinstance(expected,str) or not re.fullmatch(r"[a-f0-9]{40}",expected):
            raise ValueError("exact git head required")
    def git(*args):
        return subprocess.run(["git","-C",str(ROOT),*args],check=True,capture_output=True,
                              text=True,timeout=15).stdout.strip()
    if git("rev-parse","HEAD")!=expected or git("status","--porcelain","--untracked-files=no"):
        raise ValueError("qualification source is not the clean expected head")
    return expected


def fixture_packet(index,nonce):
    objective,targets,labels=TASKS[index%len(TASKS)]
    # Rotate order to expose position bias; candidate IDs are synthetic and
    # do not represent actual URLs or a dispatchable crawl.
    order=list(range(len(targets)))
    shift=nonce%len(order);order=order[shift:]+order[:shift]
    rows=[];relevance={}
    for i in order:
        identifier=hashlib.sha256(f"device-fixture:{index}:{nonce}:{i}".encode()).hexdigest()
        rows.append({"id":identifier,"terms":list(targets[i]),"depth":i%3,
                     "attempts":int(i==5),"semantic":(labels[i]*300)})
        relevance[identifier]=labels[i]
    body={"snapshot_digest":digest(["device-fixture",index,nonce]),"as_of":int(time.time()),
          "objective":list(objective),"candidates":rows}
    return {**body,"packet_digest":digest(body)},relevance


def ndcg(rank,labels,k=3):
    def dcg(values):return sum((2**v-1)/math.log2(i+2) for i,v in enumerate(values[:k]))
    ideal=dcg(sorted(labels.values(),reverse=True))
    return dcg([labels[x] for x in rank])/ideal if ideal else 0.


def quantile(values,q):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(q*len(ordered))-1)]


def qualify_live(*,port,token_file,jeeves_digest,dragon_digest,rounds,min_ndcg,max_p95_seconds,approved):
    if approved is not True:raise ValueError("explicit local model qualification permission")
    if (type(rounds) is not int or not 4<=rounds<=32 or not 0<min_ndcg<=1
            or not 1<=max_p95_seconds<=900 or not HEX.fullmatch(jeeves_digest)
            or not HEX.fullmatch(dragon_digest) or jeeves_digest==dragon_digest):
        raise ValueError("live qualification bounds")
    token=load_token(token_file);runs=[];seen=set()
    nonce=int.from_bytes(os.urandom(8),"big")
    for i in range(rounds):
        packet,labels=fixture_packet(i,nonce+i)
        start=time.perf_counter()
        reply=request_discourse(port,token,packet,jeeves_digest=jeeves_digest,dragon_digest=dragon_digest)
        elapsed=time.perf_counter()-start
        receipts=reply["role_receipts"]
        if len(receipts)!=2 or len({r["execution_receipt_digest"] for r in receipts})!=2:
            raise ValueError("two distinct role executions required")
        if any(r["execution_receipt_digest"] in seen for r in receipts):
            raise ValueError("replayed execution receipt")
        seen.update(r["execution_receipt_digest"] for r in receipts)
        runs.append({"packet":packet["packet_digest"],"jeeves_execution":receipts[0]["execution_receipt_digest"],
            "dragon_execution":receipts[1]["execution_receipt_digest"],
            "jeeves_ndcg":round(ndcg(reply["advice"]["jeeves_rank"],labels),8),
            "dragon_ndcg":round(ndcg(reply["advice"]["dragon_rank"],labels),8),
            "seconds":round(elapsed,6)})
    scores={role:sum(row[role+"_ndcg"] for row in runs)/rounds for role in ("jeeves","dragon")}
    p95=quantile([row["seconds"] for row in runs],.95)
    return {"actual_loopback_service_exercised":True,"native_jeeves_receipts":rounds,
            "specialist_inference_receipts":rounds,"jeeves_model_digest":jeeves_digest,
            "dragon_model_digest":dragon_digest,"synthetic_task_ndcg":scores,"p95_seconds":p95,
            "operator_thresholds_met":min(scores.values())>=min_ndcg and p95<=max_p95_seconds,
            "runs":runs,"real_web_quality_verified":False,"independent_hardware_attestation":False}


def qualify_storage(*,families,revisions,size,min_write_mib_s,min_read_mib_s,approved):
    if approved is not True:raise ValueError("explicit private scratch permission")
    if not 1<=min_write_mib_s<=100000 or not 1<=min_read_mib_s<=100000:
        raise ValueError("storage rate threshold bounds")
    initial=capacity_plan(growth_factor=2)
    devices=_devices()
    if not devices or set(devices)!={row["device"] for row in initial["devices"]}:
        raise ValueError("no stable configured storage devices")
    if len(devices)*families*revisions*(size+1024)*2>4*1024**3:
        raise ValueError("aggregate multi-device workload bound")
    raw=capacity_qualify(growth_factor=2,bytes_per_device=32*MIB,rounds=2,scratch_acknowledged=True)
    results=[]
    for device,entry in sorted(devices.items()):
        folder=entry["folder"]
        if folder.stat().st_dev!=device:
            raise ValueError("configured device changed")
        outcome=chunk_qualify(folder,families=families,revisions=revisions,size=size,
                              scratch_acknowledged=True)
        if outcome["tested_device"]!=device or not outcome["scratch_cleanup_verified"]:
            raise ValueError("configured device scratch witness mismatch")
        cdc=outcome["content_defined"]
        results.append({"device":device,"measurement":outcome,"operator_thresholds_met":
            cdc["write_mib_s"]>=min_write_mib_s and cdc["read_mib_s"]>=min_read_mib_s})
    last=capacity_plan(growth_factor=2)
    witness=lambda p:[(r["device"],r["files"],r["configured_bytes"],r["planes"]) for r in p["devices"]]
    if witness(initial)!=witness(last):
        raise ValueError("configured storage changed during qualification")
    return {"configured_device_count":len(devices),"device_io":raw,"archive_workloads":results,
            "operator_thresholds_met":all(x["operator_thresholds_met"] for x in results),
            "production_traffic_replayed":False,"power_loss_verified":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head",required=True)
    p.add_argument("--port",type=int,required=True);p.add_argument("--token-file",required=True)
    p.add_argument("--jeeves-model-sha256",required=True);p.add_argument("--dragon-model-sha256",required=True)
    p.add_argument("--rounds",type=int,default=4);p.add_argument("--min-ndcg",type=float,required=True)
    p.add_argument("--max-p95-seconds",type=float,required=True)
    p.add_argument("--families",type=int,default=16);p.add_argument("--revisions",type=int,default=4)
    p.add_argument("--size",type=int,default=MIB)
    p.add_argument("--min-write-mib-s",type=float,required=True);p.add_argument("--min-read-mib-s",type=float,required=True)
    p.add_argument("--approve-local-inference",action="store_true")
    p.add_argument("--acknowledge-private-scratch-writes",action="store_true")
    a=p.parse_args(argv)
    if not a.approve_local_inference or not a.acknowledge_private_scratch_writes:
        p.error("explicit permission for both workloads required")
    head=exact_head(a.expected_head)
    live=qualify_live(port=a.port,token_file=a.token_file,jeeves_digest=a.jeeves_model_sha256,
        dragon_digest=a.dragon_model_sha256,rounds=a.rounds,min_ndcg=a.min_ndcg,
        max_p95_seconds=a.max_p95_seconds,approved=True)
    storage=qualify_storage(families=a.families,revisions=a.revisions,size=a.size,
        min_write_mib_s=a.min_write_mib_s,min_read_mib_s=a.min_read_mib_s,approved=True)
    if exact_head(head)!=head:raise ValueError("source identity changed")
    result={"schema":"skeleton.dragon.device-qualification.v1","head":head,
        "system":platform.system(),"machine":platform.machine(),"logical_cpus":os.cpu_count(),
        "live":live,"storage":storage,
        "operator_thresholds_met":live["operator_thresholds_met"] and storage["operator_thresholds_met"],
        "production_launch_certified":False,"network_crawl_executed":False}
    print(json.dumps({**result,"receipt":digest(result)},sort_keys=True,allow_nan=False))
    return 0 if result["operator_thresholds_met"] else 2


if __name__=="__main__":raise SystemExit(main())
