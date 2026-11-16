"""Measure local semantic retrieval against BM25 through an explicit pinned holdout."""
from __future__ import annotations
import argparse,json,sqlite3,threading
from pathlib import Path

from skeleton.retrieval.learned_embeddings import _read_pinned
from skeleton.retrieval.semantic_config import load_semantic_ranker
from skeleton.retrieval.semantic_long_context import document_spans
from skeleton.retrieval.semantic_vector_cache import DerivedVectorCache
from skeleton.retrieval.semantic_eval import evaluate
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--config-sha256",required=True)
    p.add_argument("--holdout",type=Path,required=True)
    p.add_argument("--holdout-sha256",required=True)
    p.add_argument("--k",type=int,default=5)
    p.add_argument("--repeats",type=int,default=2)
    a=p.parse_args(argv)
    ranker=load_semantic_ranker(a.config,a.config_sha256)
    data=json.loads(_read_pinned(a.holdout,a.holdout_sha256,64*1024**2))
    if not isinstance(data,dict) or set(data)!={"documents","questions"} or not isinstance(data["documents"],list) or not 1<=len(data["documents"])<=4096:
        p.error("explicit bounded holdout corpus required")
    spans=[]
    seen=set()
    total=0
    for doc in data["documents"]:
        if not isinstance(doc,dict) or set(doc)!={"id","sha256","text"} or not isinstance(doc["id"],str) or doc["id"] in seen or not isinstance(doc["text"],str):
            p.error("invalid or duplicate holdout source")
        seen.add(doc["id"])
        total+=len(doc["text"])
        if total>ranker.policy.max_source_chars:
            p.error("holdout corpus exceeds configured semantic capacity")
        for span in document_spans(doc["id"],doc["sha256"],doc["text"],
                [(i,start,end,text) for i,(start,end,text) in enumerate(OfflineKnowledgeLibrary._chunks(doc["text"]))],ranker.policy):
            spans.append(span)
            if len(spans)>ranker.policy.max_spans:
                p.error("holdout exceeds semantic span limit")
    db=sqlite3.connect(":memory:",isolation_level=None)
    try:
        cache=DerivedVectorCache(db,threading.RLock(),a.holdout_sha256,
             dimension=ranker.encoder.policy.dimension,segments=ranker.policy.segments,max_bytes=ranker.policy.max_vector_bytes)
        report=evaluate(ranker,spans,data["questions"],holdout_sha256=a.holdout_sha256,k=a.k,repeats=a.repeats,cache=cache)
        print(json.dumps(report,sort_keys=True,allow_nan=False))
    finally:
        db.close()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
