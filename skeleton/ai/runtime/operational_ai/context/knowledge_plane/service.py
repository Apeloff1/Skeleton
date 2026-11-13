"""High-level private knowledge API sharing one existing spine SQLite owner."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import KnowledgePolicy,KnowledgeError
from .path_guard import read_source
from . import schema, ingest, search, catalog, events
from .provider import KnowledgeEvidenceProvider
from ...orchestration.execution_spine.contracts import Identity


class KnowledgePlane:
    def __init__(self,db,identity:Identity,*,policy:KnowledgePolicy|None=None,
                 initialize:bool=True):
        if not isinstance(identity,Identity):raise KnowledgeError('knowledge identity required')
        self.db=db
        self.identity=identity
        self.policy=policy if policy is not None else KnowledgePolicy()
        if not isinstance(self.policy,KnowledgePolicy):
            raise KnowledgeError('typed knowledge admission limits required')
        schema.install(db) if initialize else schema.verify(db)

    def admit_file(self,*,root,relative_path:str,doc_id:str,title:str,
                   rights:str,content_type:str,approved:bool,expected_revision:int):
        if approved is not True:
            raise KnowledgeError('source ingestion explicitly approved by the operator only')
        # Source read is completed before BEGIN IMMEDIATE to avoid holding
        # write-lock on an untrusted or slow filesystem.
        raw=read_source(root,relative_path,policy=self.policy)
        with self.db.transaction() as conn:
            record,replayed=ingest.ingest(conn,self.identity,raw,doc_id=doc_id,
                title=title,rights=rights,kind=content_type,approved=True,
                expected_revision=expected_revision,policy=self.policy)
        return record.to_dict() | {'replayed':replayed}

    def admit_bytes_for_tests(self,raw:bytes,*,doc_id:str,title:str,
                              rights:str='operator-authored',content_type:str='text/plain',
                              expected_revision:int=0,approved:bool=False):
        """Explicit bytes path for trusted application callers and small fixtures."""
        with self.db.transaction() as conn:
            record,replayed=ingest.ingest(conn,self.identity,raw,doc_id=doc_id,
                title=title,rights=rights,kind=content_type,
                approved=approved,expected_revision=expected_revision,policy=self.policy)
        return record.to_dict() | {'replayed':replayed}

    def forget(self,doc_id:str,*,expected_revision:int,approved:bool=False)->bool:
        with self.db.transaction() as conn:
            return ingest.forget(conn,self.identity,doc_id=doc_id,
                        expected_revision=expected_revision,approved=approved)

    def search(self,question:str,*,limit:int|None=None,include_text:bool=False)->tuple[dict,...]:
        with self.db.snapshot() as conn:
            rows=search.search(conn,self.identity,question,limit=limit or self.policy.max_hits,
                               policy=self.policy)
        return tuple(row.to_dict(include_text=include_text) for row in rows)

    def list(self,*,limit:int=128,include_inactive:bool=False):
        with self.db.snapshot() as conn:
            return tuple(record.to_dict() for record in catalog.list_documents(
                conn,self.identity.key(),limit=limit,include_inactive=include_inactive))

    def evidence_provider(self)->KnowledgeEvidenceProvider:
        return KnowledgeEvidenceProvider(self.db,self.identity,self.policy)

    def doctor(self,*,maximum:int=65536):
        from .doctor import inspect
        return inspect(self.db,self.identity,maximum=maximum)

    def ingest_many(self,*,source_root,items,approved:bool=False,maximum:int=16):
        from .batch import ingest_batch
        return ingest_batch(self,source_root=source_root,items=items,approved=approved,maximum=maximum)

    def check_index(self):
        from .index import verify_index
        with self.db.transaction() as conn:return verify_index(conn)

    def rebuild_index(self,*,approved:bool=False,maximum:int=65536):
        from .index import rebuild
        return rebuild(self,approved=approved,maximum=maximum)
