"""Build an immutable disk ANN from the private Jeeves reference library."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.retrieval.semantic_config import load_semantic_ranker
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy,DiskANN


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",type=Path,required=True)
    p.add_argument("--model-digest",required=True)
    p.add_argument("--tokenizer-digest",required=True)
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--config-sha256",required=True)
    p.add_argument("--index-root",type=Path,required=True)
    p.add_argument("--generation")
    p.add_argument("--managed-refresh",action="store_true")
    p.add_argument("--shards",type=int,default=8)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--worker-mode",choices=("thread","process"),default="thread")
    p.add_argument("--max-rows",type=int,default=10_000_000)
    p.add_argument("--max-index-bytes",type=int,required=True)
    p.add_argument("--previous-index",type=Path)
    p.add_argument("--previous-manifest-sha256")
    p.add_argument("--previous-source-snapshot")
    a=p.parse_args(argv)
    if any((a.previous_index,a.previous_manifest_sha256,a.previous_source_snapshot)) and not all((a.previous_index,a.previous_manifest_sha256,a.previous_source_snapshot)):
        p.error("all three exact previous-generation inputs are required")
    if bool(a.generation)==bool(a.managed_refresh) or (a.managed_refresh and a.previous_index):
        p.error("choose named immutable generation or managed refresh; managed mode owns prior selection")
    if not a.database.is_file() or a.database.is_symlink():
        p.error("existing canonical private database required")
    ranker=load_semantic_ranker(a.config,a.config_sha256)
    policy=DiskANNPolicy(shards=a.shards,workers=a.workers,worker_mode=a.worker_mode,max_rows=a.max_rows,max_index_bytes=a.max_index_bytes)
    with OfflineChatStore(a.database) as store:
        library=OfflineKnowledgeLibrary(store,a.model_digest,a.tokenizer_digest,semantic_ranker=ranker)
        if a.managed_refresh:
            from skeleton.app.offline_semantic_journal import SemanticIndexJournal
            receipt=SemanticIndexJournal(library,a.index_root).refresh(policy)
        else:
            previous=DiskANN(a.previous_index,a.previous_manifest_sha256,expected_space=ranker.identity,expected_snapshot=a.previous_source_snapshot) if a.previous_index else None
            receipt=library.build_semantic_ann(a.index_root,a.generation,policy,previous=previous)
            library.attach_semantic_ann(receipt["path"],receipt["manifest_sha256"])
        receipt["source_snapshot"]=library.semantic_source_snapshot()
        receipt["status"]="verified_local_generation_not_quality_certified"
        print(json.dumps(receipt,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
