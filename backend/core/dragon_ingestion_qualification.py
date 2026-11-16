"""Real synthetic canonical ingestion load qualification on private scratch.

Never opens a production corpus. Each worker writes a new independent store
using the actual lead graph page/FTS path, verifies sealed page identity,
owner isolation, SQLite integrity and restart readback. Results are measured,
not extrapolated production capacity or live acquisition evidence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time

from core.dragon_graph_deployment import _dir,_require_space
from core.dragon_lead_graph import LeadGraph,MAX_PAGE_ROWS,ZERO
from core.dragon_game_corpus import digest

MAX_WORKERS=8
MAX_ROWS_PER_WORKER=250_000
MAX_ROWS_TOTAL=1_000_000
# Conservative planning reserve, not a promise of worst-case disk usage.
PLANNING_BYTES_PER_ROW=128*1024


def _pages(worker,rows):
    for start in range(0,rows,MAX_PAGE_ROWS):
        size=min(MAX_PAGE_ROWS,rows-start)
        raw=b"".join(json.dumps({"appid":str(100000001+worker*MAX_ROWS_PER_WORKER+i),
            "title":f"Dragon qualification fixture {worker} {i}"},
            sort_keys=True,separators=(",",":")).encode()+b"\n" for i in range(start,start+size))
        yield raw,size


def _p95(values):
    values=sorted(values)
    return values[max(0,math.ceil(len(values)*.95)-1)]


def _worker(directory,worker,rows):
    path=directory/f"store-{worker}.sqlite3"
    scope={"tenant_id":"disposable-qualification","owner_id":f"worker-{worker}"}
    other={"tenant_id":"disposable-qualification","owner_id":"foreign"}
    started=time.perf_counter()
    graph=LeadGraph(path)
    graph.configure(scope,enabled=True,acknowledged=True)
    source=hashlib.sha256()
    for raw,_ in _pages(worker,rows):source.update(raw)
    snapshot=graph.begin(scope,target_id="steam-fronkon",projection="steam",
        source_sha=source.hexdigest(),expected_rows=rows,rights_ref="synthetic qualification only",
        grant_seconds=86400,acknowledged=True)
    sid=snapshot["snapshot_id"];chain=ZERO;latencies=[];last=None
    for ordinal,(raw,n) in enumerate(_pages(worker,rows)):
        before=chain;page_hash=hashlib.sha256(raw).hexdigest();t=time.perf_counter()
        receipt=graph.append(scope,sid,ordinal=ordinal,raw=raw,sha256=page_hash,previous_chain=before)
        latencies.append(time.perf_counter()-t)
        chain=digest([before,ordinal,page_hash,n])
        if receipt["chain"]!=chain or receipt["rows"]!=n:
            raise RuntimeError("synthetic canonical page receipt differs")
        last=(ordinal,raw,page_hash,before,chain)
    final=graph.seal(scope,sid,chain)
    graph=LeadGraph(path)
    readback=graph.snapshot(scope,sid)
    if (final["state"]!="sealed" or readback["state"]!="sealed" or readback["rows"]!=rows
            or readback["chain"]!=chain):
        raise RuntimeError("synthetic restart readback differs")
    ordinal,raw,page_hash,before,expected=last
    replay=graph.append(scope,sid,ordinal=ordinal,raw=raw,sha256=page_hash,previous_chain=before)
    if not replay["replayed"] or replay["chain"]!=expected:raise RuntimeError("page replay differs")
    try:graph.snapshot(other,sid)
    except LookupError:pass
    else:raise RuntimeError("foreign owner snapshot visible")
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchall()!=[("ok",)]:
            raise RuntimeError("scratch database integrity differs")
        node_count=db.execute("SELECT COUNT(*) FROM lead_nodes").fetchone()[0]
        indexed=db.execute("SELECT COUNT(*) FROM lead_fts").fetchone()[0]
        if node_count<rows*17 or indexed!=node_count:
            raise RuntimeError("synthetic graph or FTS cardinality differs")
    elapsed=max(time.perf_counter()-started,1e-9)
    physical_bytes=sum(p.stat().st_size for p in directory.glob(path.name+"*") if p.is_file())
    return {"worker":worker,"rows":rows,"nodes":node_count,"fts_rows":indexed,
            "pages":len(latencies),"sealed_chain":chain,"elapsed_seconds":elapsed,
            "rows_per_second":rows/elapsed,"page_p95_seconds":_p95(latencies),
            "database_and_sidecar_bytes":physical_bytes,"restart_readback_verified":True,
            "owner_isolation_verified":True,"page_replay_verified":True}


def qualify(root,*,workers=2,rows_per_worker=1024,scratch_acknowledged=False):
    if scratch_acknowledged is not True:raise ValueError("explicit disposable scratch writes required")
    if (type(workers) is not int or not 1<=workers<=MAX_WORKERS
            or type(rows_per_worker) is not int or not 1<=rows_per_worker<=MAX_ROWS_PER_WORKER
            or workers*rows_per_worker>MAX_ROWS_TOTAL):
        raise ValueError("synthetic qualification workload bounds")
    root=_dir(Path(root))
    planned=workers*rows_per_worker*PLANNING_BYTES_PER_ROW
    space=_require_space([(root,planned)])
    start=time.perf_counter()
    with TemporaryDirectory(prefix="dragon-ingestion-fixture-",dir=root) as temp:
        directory=Path(temp)
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="dragon-qual") as pool:
            tasks=[pool.submit(_worker,directory,worker,rows_per_worker) for worker in range(workers)]
            results=[task.result() for task in tasks]
        elapsed=max(time.perf_counter()-start,1e-9)
    rows=sum(x["rows"] for x in results)
    return {"workers":results,"rows":rows,"nodes":sum(x["nodes"] for x in results),
            "elapsed_seconds":elapsed,"aggregate_rows_per_second":rows/elapsed,
            "scratch_bytes_planned":planned,"devices":space,"cleanup_verified":not directory.exists(),
            "synthetic_canonical_ingestion_verified":True,"production_topology_verified":False,
            "production_maximum_capacity_verified":False,"live_network_executed":False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch-root",required=True,type=Path)
    p.add_argument("--workers",type=int,default=2);p.add_argument("--rows-per-worker",type=int,default=1024)
    p.add_argument("--acknowledge-disposable-scratch",action="store_true")
    args=p.parse_args(argv)
    print(json.dumps(qualify(args.scratch_root,workers=args.workers,rows_per_worker=args.rows_per_worker,
                            scratch_acknowledged=args.acknowledge_disposable_scratch),sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
