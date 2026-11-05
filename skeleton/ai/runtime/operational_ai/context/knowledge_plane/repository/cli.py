"""Explicit exact-source Git index and provenance audit; never auto-index repo."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .contracts import GitIndexItem,GitSourceError
from .service import index_repository
from .doctor import inspect_repository
from ..contracts import KnowledgePolicy,KnowledgeError
from ..service import KnowledgePlane
from ..path_guard import read_source
from ....orchestration.execution_spine.database import SpineDatabase
from ....orchestration.execution_spine.contracts import Identity
from ....deployment.boot.identity import PrincipalBinding,inspect_binding


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Exact-Git-object, private AI source knowledge')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--model-sha256',required=True)
    p.add_argument('--tokenizer-sha256',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    ingest=sub.add_parser('ingest')
    ingest.add_argument('--commit',required=True)
    ingest.add_argument('--manifest-root',type=Path,required=True)
    ingest.add_argument('--manifest',required=True)
    ingest.add_argument('--approve-ingest',action='store_true')
    review=sub.add_parser('doctor')
    review.add_argument('--maximum',type=int,default=32)
    args=p.parse_args(argv)
    try:
        identity=Identity(args.tenant,args.subject,args.model_sha256,args.tokenizer_sha256)
        inspect_binding(args.state_dir,PrincipalBinding(args.tenant,args.subject,
                        args.model_sha256,args.tokenizer_sha256))
        if args.action=='ingest':
            if args.approve_ingest is not True:
                raise GitSourceError('independent source indexing approval required')
            raw=read_source(args.manifest_root,args.manifest,
                 policy=KnowledgePolicy(max_document_bytes=65536))
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise GitSourceError('duplicate Git manifest key')
                    result[key]=value
                return result
            manifest=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
            if type(manifest)is not dict or set(manifest)!= {'schema','sources','commit_sha'} or manifest['schema']!='skeleton.ai.exact-Git-sources.v1' or manifest['commit_sha']!=args.commit or type(manifest['sources'])is not list:
                raise GitSourceError('invalid or mismatched exact Git import manifest')
            items=[]
            for row in manifest['sources']:
                if len(items)>=32:
                    raise GitSourceError('source manifest exceeds maximum batch')
                if type(row)is not dict or set(row)!= {'path','expected_revision','rights'}:
                    raise GitSourceError('invalid Git manifest source row')
                items.append(GitIndexItem(**row))
        with SpineDatabase(args.state_dir,readonly=args.action=='doctor') as db:
            plane=KnowledgePlane(db,identity,initialize=args.action=='ingest')
            if args.action=='ingest':
                records=index_repository(plane,repo_root=args.repo_root,commit=args.commit,
                                   items=items,approved=True,maximum=32)
                result={'sources':records,'model_calls':0}
            else:
                result=inspect_repository(plane,repo_root=args.repo_root,maximum=args.maximum)
        print(json.dumps({'status':'ok','result':result},ensure_ascii=False,sort_keys=True))
        return 0
    except Exception as exc:
        # Git paths, prompts, query results, worktree contents are private.
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
