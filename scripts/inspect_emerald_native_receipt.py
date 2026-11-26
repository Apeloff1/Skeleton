"""Validate evidence from an actual Unreal qualification run; never synthesize success."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import math

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/"frontend/src/features/Jeeves/companion/emeraldAssetPin.json"
HASH=re.compile(r"[a-f0-9]{64}")
RUN=re.compile(r"[a-f0-9]{32}")

def digest(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size==0:
        raise ValueError("missing evidence: "+str(path))
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def inspect(receipt_path, model_sha):
    r=json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    run=r.get("run_id","")
    if not isinstance(run,str) or not RUN.fullmatch(run) or receipt_path.name!="qualification_"+run+".json":
        raise ValueError("run identity invalid")
    if r.get("source_sha256")!=model_sha:
        raise ValueError("wrong source asset")
    rt=r.get("runtime") or {}
    native=r.get("engine_compiled") is True and r.get("editor_import_passed") is True
    runtime=native and r.get("engine_rehearsal_passed") is True and rt.get("run_id")==run and rt.get("source_sha256")==model_sha and rt.get("rehearsal_completed") is True and rt.get("completed_clips")==8 and type(rt.get("samples")) is int and rt["samples"]>=60
    adapter=str(rt.get("adapter",""))
    nv=str(r.get("nvidia_inventory",""))
    rtx=runtime and r.get("rtx_capability_reported") is True and bool(re.search(r"NVIDIA.*RTX",adapter,re.I)) and bool(re.search(r"RTX",nv,re.I)) and "D3D12" in str(rt.get("rhi","")).upper() and all(rt.get(k) is True for k in ("raytracing_supported","raytracing_cvar","lumen_hwrt_cvar"))
    trace=False
    if rtx:
        for field,name in (("trace_sha256","gpu_"+run+".utrace"),("gpu_log_sha256","gpu_"+run+".log")):
            d=r.get(field)
            if not isinstance(d,str) or not HASH.fullmatch(d) or digest(receipt_path.parent/name)!=d:
                raise ValueError("trace/log identity mismatch")
        trace=True
    fps=rt.get("mean_wall_fps");p95=rt.get("p95_wall_frame_ms")
    numeric=lambda x: type(x) in (int,float) and math.isfinite(x)
    tick=runtime and numeric(fps) and numeric(p95) and fps>=30 and 0<p95<=1000/30 and r.get("engine_tick_30fps") is True
    # This tool checks custody and consistency only, not independent authenticity or
    # actual GPU command execution. Human-reviewed GPU captures and artistic review
    # remain separate. Never accept boolean assertions from the bundle as proof.
    return {"run_id":run,"artifact_identity":True,"compile_import_reported":native,"runtime_rehearsal_reported":runtime,"rtx_capability_reported":rtx,"trace_log_integrity":trace,"engine_tick_30fps_reported":tick,"physical_ray_dispatch_verified":False,"artist_approved":False,"release_qualified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("receipt",type=Path);a=p.parse_args()
    pin=json.loads(PIN.read_text(encoding="utf-8"))["native"]
    print(json.dumps(inspect(a.receipt,pin["modelSha256"]),indent=2))

if __name__=="__main__":
    main()
