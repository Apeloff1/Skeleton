"""Measure actual disk ANN construction and recall against streaming exact search.

Synthetic deterministic vectors independently exercise disk capacity and
approximation error; this is not pretrained model quality or production-scale
qualification. The operator selects a private local target and strict budgets.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import heapq
import json
import math
from pathlib import Path
import platform
import statistics
import time

from skeleton.retrieval.disk_semantic_ann import DiskANN,DiskANNPolicy,build_generation
from skeleton.retrieval.learned_embeddings import SpanEmbedding,_digest
from skeleton.retrieval.semantic_long_context import SemanticSpan
from skeleton.app.offline_resources import probe_local_resources


def _vector(seed,ordinal,dimension):
    import numpy as np
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,ordinal])))
    vector=rng.standard_normal(dimension,dtype=np.float32)
    return vector/np.linalg.norm(vector)


def _leaf(ordinal):
    text=f"Synthetic disk capacity diagnostic record {ordinal}."
    pin=sha256(text.encode()).hexdigest()
    return SemanticSpan(str(ordinal),pin,0,0,len(text),text,text,0,len(text))


def _rss():
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if platform.system()=="Darwin" else value*1024)
    except (ImportError,OSError):
        return None


def qualify(root,name,*,rows,dimension,queries,k,seed,policy,interrupt=None):
    import numpy as np
    if not isinstance(policy,DiskANNPolicy):
        raise TypeError("explicit qualification disk policy required")
    for value,lo,hi in ((rows,32,min(policy.max_rows,10_000_000)),(dimension,2,1024),
        (queries,1,32),(k,1,min(32,policy.global_candidate_limit)),(seed,0,2**32-1)):
        if type(value) is not int or not lo<=value<=hi:raise ValueError("invalid scale diagnostic geometry")
    if k>rows or queries>rows or rows*queries*dimension>20_000_000_000:
        raise ValueError("exact qualification arithmetic envelope exceeded")
    root=Path(root)
    start=probe_local_resources(root)
    manifest_identity={"schema":"skeleton.synthetic-disk-ann.v1","seed":seed,"rows":rows,
                       "dimension":dimension,"numpy":np.__version__}
    space=_digest(["synthetic-not-pretrained",manifest_identity])
    snapshot=_digest(manifest_identity)
    def source():
        for ordinal in range(rows):
            if interrupt:interrupt()
            vector=_vector(seed,ordinal,dimension)
            yield _leaf(ordinal),SpanEmbedding(tuple(map(float,vector)),())
    began=time.perf_counter()
    made=build_generation(root,name,source(),space=space,source_snapshot=snapshot,
                      dimension=dimension,policy=policy,interrupt=interrupt)
    build_seconds=time.perf_counter()-began
    started=time.perf_counter()
    index=DiskANN(made["path"],made["manifest_sha256"],expected_space=space,expected_snapshot=snapshot)
    admission_seconds=time.perf_counter()-started
    sampled=[i*rows//queries for i in range(queries)]
    tests=[]
    for ordinal in sampled:
        if interrupt:interrupt()
        query=_vector(seed,ordinal,dimension)
        # No lexical match: diagnose the actual learned-vector-style ANN
        # channel independently of identifier and sparse candidate paths.
        started=time.perf_counter()
        observed,receipt=index.search("unrelated abstract conceptual request",tuple(map(float,query)),limit=k)
        approximate_seconds=time.perf_counter()-started
        started=time.perf_counter()
        heap=[]
        for i in range(rows):
            if interrupt and i%1024==0:interrupt()
            sim=float(np.clip(_vector(seed,i,dimension)@query,-1,1))
            key=(sim,-i)
            if len(heap)<k:heapq.heappush(heap,key)
            elif key>heap[0]:heapq.heapreplace(heap,key)
        exact_seconds=time.perf_counter()-started
        exact={str(-i) for _,i in heap}
        found={x.source_id for x in observed}
        tests.append({"query_ordinal":ordinal,"recall_at_k":len(exact&found)/k,
            "self_retrieved":str(ordinal) in found,"candidate_count":len(observed),
            "approximate_seconds":approximate_seconds,"streamed_exact_seconds":exact_seconds,
            "shards_searched":receipt["shards_searched"],
            "candidate_truncation":receipt["bucket_or_shard_truncation"]})
        if receipt["shards_searched"]!=policy.shards:raise RuntimeError("partial shard qualification is invalid")
    finish=probe_local_resources(root)
    report={"schema":"skeleton.semantic-disk-scale.v1","measurement_kind":"real_disk_synthetic_vector_diagnostic",
        "manifest_sha256":made["manifest_sha256"],"rows":rows,"dimension":dimension,"queries":queries,"k":k,
        "policy":asdict(policy),"index_bytes":made["bytes"],"bytes_per_row":made["bytes"]/rows,
        "build_seconds":build_seconds,"rows_per_second":rows/max(build_seconds,1e-9),
        "admission_seconds":admission_seconds,"parent_peak_rss_bytes":_rss(),
        "host":platform.machine(),"available_ram_before":start.available_ram_bytes,
        "available_ram_after":finish.available_ram_bytes,"disk_free_before":start.free_disk_bytes,
        "disk_free_after":finish.free_disk_bytes,
        "mean_recall_at_k":statistics.mean(x["recall_at_k"] for x in tests),
        "minimum_recall_at_k":min(x["recall_at_k"] for x in tests),
        "median_approximate_seconds":statistics.median(x["approximate_seconds"] for x in tests),
        "median_streamed_exact_seconds":statistics.median(x["streamed_exact_seconds"] for x in tests),
        "rows_detail":tests,"pretrained_quality_certified":False,"production_scale_certified":False}
    report["report_sha256"]=_digest(report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True);p.add_argument("--generation",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--rows",type=int,default=2048);p.add_argument("--dimension",type=int,default=64)
    p.add_argument("--queries",type=int,default=4);p.add_argument("--k",type=int,default=5)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--shards",type=int,default=4);p.add_argument("--workers",type=int,default=2)
    p.add_argument("--worker-mode",choices=("thread","process"),default="thread")
    p.add_argument("--max-index-bytes",type=int,required=True)
    a=p.parse_args(argv)
    policy=DiskANNPolicy(shards=a.shards,workers=a.workers,worker_mode=a.worker_mode,
        max_rows=a.rows,max_index_bytes=a.max_index_bytes)
    report=qualify(a.root,a.generation,rows=a.rows,dimension=a.dimension,queries=a.queries,k=a.k,seed=a.seed,policy=policy)
    with a.output.open("x",encoding="utf-8") as handle:json.dump(report,handle,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k not in {"rows_detail","policy"}},sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
