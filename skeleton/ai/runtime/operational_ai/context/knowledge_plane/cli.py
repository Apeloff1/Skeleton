"""Explicit local corpus import/query/forget/doctor CLI; no model required.

The model/tokenizer tuple and operator principal must match an existing
private-state identity binding. This command never creates a binding, calls
network resources, promotes text into tool authority or triggers inference.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .contracts import KnowledgeError
from .service import KnowledgePlane
from ...orchestration.execution_spine.contracts import Identity
from ...orchestration.execution_spine.database import SpineDatabase
from ...deployment.boot.identity import PrincipalBinding,inspect_binding


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Source-bound native AI knowledge')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--model-sha256',required=True)
    p.add_argument('--tokenizer-sha256',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    ingest=sub.add_parser('ingest')
    ingest.add_argument('--root',type=Path,required=True)
    ingest.add_argument('--source',required=True)
    ingest.add_argument('--id',required=True)
    ingest.add_argument('--title',required=True)
    ingest.add_argument('--rights',choices=['operator-authored','operator-licensed','public-domain'],required=True)
    ingest.add_argument('--kind',choices=['text/plain','text/markdown','application/json','text/x-python'],required=True)
    ingest.add_argument('--revision',type=int,required=True)
    ingest.add_argument('--approve-ingest',action='store_true')
    batch=sub.add_parser('ingest-batch')
    batch.add_argument('--root',type=Path,required=True)
    batch.add_argument('--manifest',required=True)
    batch.add_argument('--approve-ingest',action='store_true')
    verify_index=sub.add_parser('check-index')
    rebuild=sub.add_parser('rebuild-index')
    rebuild.add_argument('--approve-rebuild',action='store_true')
    query=sub.add_parser('search')
    query.add_argument('--question',required=True)
    query.add_argument('--limit',type=int,default=6)
    query.add_argument('--include-passages',action='store_true')
    inventory=sub.add_parser('list')
    inventory.add_argument('--limit',type=int,default=128)
    inventory.add_argument('--include-inactive',action='store_true')
    forget=sub.add_parser('forget')
    forget.add_argument('--id',required=True)
    forget.add_argument('--revision',type=int,required=True)
    forget.add_argument('--approve-forget',action='store_true')
    doctor=sub.add_parser('doctor')
    doctor.add_argument('--maximum',type=int,default=65536)
    return p


def main(argv:list[str]|None=None)->int:
    args=parser().parse_args(argv)
    try:
        identity=Identity(args.tenant,args.subject,args.model_sha256,args.tokenizer_sha256)
        inspect_binding(args.state_dir,PrincipalBinding(args.tenant,args.subject,
                        args.model_sha256,args.tokenizer_sha256))
        writing=args.action in ('ingest','ingest-batch','forget','check-index','rebuild-index')
        with SpineDatabase(args.state_dir,readonly=not writing) as db:
            plane=KnowledgePlane(db,identity,initialize=writing)
            if args.action=='ingest':
                result=plane.admit_file(root=args.root,relative_path=args.source,
                    doc_id=args.id,title=args.title,rights=args.rights,
                    content_type=args.kind,approved=args.approve_ingest,
                    expected_revision=args.revision)
            elif args.action=='ingest-batch':
                from .contracts import KnowledgePolicy
                from .path_guard import read_source
                from .batch import BatchItem
                if not args.approve_ingest:
                    raise KnowledgeError('bulk import requires explicit approval')
                raw=read_source(args.root,args.manifest,policy=KnowledgePolicy(max_document_bytes=65536))
                def unique(pairs):
                    data={}
                    for k,v in pairs:
                        if k in data:raise KnowledgeError('duplicate manifest field')
                        data[k]=v
                    return data
                manifest=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
                if type(manifest)is not dict or set(manifest)!={'schema','documents'} or manifest['schema']!='skeleton.ai.knowledge-batch.v1' or type(manifest['documents'])is not list:
                    raise KnowledgeError('invalid document import manifest')
                entries=[]
                for row in manifest['documents']:
                    if len(entries)>=16:
                        raise KnowledgeError('batch manifest exceeds approved finite limit')
                    if type(row)is not dict or set(row)!={'source','document_id','title','rights','content_type','expected_revision'}:
                        raise KnowledgeError('invalid batch member')
                    entries.append(BatchItem(**row))
                result={'documents':plane.ingest_many(source_root=args.root,items=entries,
                   approved=True,maximum=16)}
            elif args.action=='check-index':result=plane.check_index()
            elif args.action=='rebuild-index':
                result=plane.rebuild_index(approved=args.approve_rebuild)
            elif args.action=='search':
                result={'hits':plane.search(args.question,limit=args.limit,
                                           include_text=args.include_passages)}
            elif args.action=='list':
                result={'documents':plane.list(limit=args.limit,
                                          include_inactive=args.include_inactive)}
            elif args.action=='forget':
                result={'forgotten':plane.forget(args.id,expected_revision=args.revision,
                                                approved=args.approve_forget)}
            else:result=plane.doctor(maximum=args.maximum)
        print(json.dumps({'status':'ok','result':result},sort_keys=True,ensure_ascii=False))
        return 0
    except Exception as exc:
        # Never print paths, question texts, private source passages or DB SQL.
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
