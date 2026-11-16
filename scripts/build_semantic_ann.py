"""Build an immutable disk ANN from the private Jeeves reference library."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.retrieval.semantic_config import load_semantic_ranker
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",type=Path,required=True)
    p.add_argument("--model-digest",required=True)
    p.add_argument("--tokenizer-digest",required=True)
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--config-sha256",required=True)
    p.add_argument("--index-root",type=Path,required=True)
    p.add_argument("--generation",required=True)
    p.add_argument("--shards",type=int,default=8)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--max-rows",type=int,default=10_000_000)
    p.add_argument("--max-index-bytes",type=int,required=True)
    a=p.parse_args(argv)
    if not a.database.is_file() or a.database.is_symlink():
        p.error("existing canonical private database required")
    ranker=load_semantic_ranker(a.config,a.config_sha256)
    policy=DiskANNPolicy(shards=a.shards,workers=a.workers,max_rows=a.max_rows,max_index_bytes=a.max_index_bytes)
    with OfflineChatStore(a.database) as store:
        library=OfflineKnowledgeLibrary(store,a.model_digest,a.tokenizer_digest,semantic_ranker=ranker)
        receipt=library.build_semantic_ann(a.index_root,a.generation,policy)
        library.attach_semantic_ann(receipt["path"],receipt["manifest_sha256"])
        receipt["source_snapshot"]=library.semantic_source_snapshot()
        receipt["status"]="verified_local_generation_not_quality_certified"
        print(json.dumps(receipt,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
