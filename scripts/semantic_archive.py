"""Operate local semantic retrieval over the existing offline file library."""
from __future__ import annotations
import argparse,json
from pathlib import Path

from skeleton.app.offline_library import OfflineDocumentLibrary
from skeleton.app.offline_archive_semantic import ArchiveSemanticSearch,ArchiveSemanticPolicy
from skeleton.retrieval.semantic_config import load_semantic_ranker
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy,DiskANN


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library",type=Path,required=True)
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--config-sha256",required=True)
    p.add_argument("--leaf-chars",type=int,default=320)
    p.add_argument("--halo-chars",type=int,default=160)
    sub=p.add_subparsers(dest="action",required=True)
    b=sub.add_parser("build")
    b.add_argument("--root",type=Path,required=True);b.add_argument("--generation",required=True)
    b.add_argument("--shards",type=int,default=8);b.add_argument("--workers",type=int,default=4)
    b.add_argument("--max-index-bytes",type=int,required=True)
    b.add_argument("--previous",type=Path);b.add_argument("--previous-sha256");b.add_argument("--previous-source-snapshot")
    q=sub.add_parser("search")
    q.add_argument("--index",type=Path,required=True);q.add_argument("--manifest-sha256",required=True)
    q.add_argument("--query-file",type=Path,required=True);q.add_argument("--limit",type=int,default=6)
    a=p.parse_args(argv)
    if a.library.is_symlink() or not a.library.is_file():p.error("existing local file library required")
    ranker=load_semantic_ranker(a.config,a.config_sha256)
    policy=ArchiveSemanticPolicy(leaf_chars=a.leaf_chars,halo_chars=a.halo_chars)
    with OfflineDocumentLibrary(a.library) as library:
        adapter=ArchiveSemanticSearch(library,ranker,policy)
        if a.action=="build":
            if any((a.previous,a.previous_sha256,a.previous_source_snapshot)) and not all((a.previous,a.previous_sha256,a.previous_source_snapshot)):p.error("explicit previous generation pins required")
            previous=DiskANN(a.previous,a.previous_sha256,expected_space=adapter.space,expected_snapshot=a.previous_source_snapshot) if a.previous else None
            result=adapter.build(a.root,a.generation,DiskANNPolicy(shards=a.shards,workers=a.workers,max_index_bytes=a.max_index_bytes),previous=previous)
        else:
            with a.query_file.open("rb") as handle:raw=handle.read(4097)
            if not 1<=len(raw)<=4096:p.error("bounded query file required")
            adapter.attach(a.index,a.manifest_sha256)
            hits,proof=adapter.search(raw.decode(),limit=a.limit)
            result={"hits":hits,"receipt":proof}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":raise SystemExit(main())
