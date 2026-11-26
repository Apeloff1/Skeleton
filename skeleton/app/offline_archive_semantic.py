"""Semantic navigation for the existing bounded-RAM offline file library.

The canonical SQLite document store still owns bytes and FTS projection.
ANN only points to exact spans. Neither source files nor archive text are
executed; no remote acquisition or separate source authority is introduced.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path

from skeleton.retrieval.disk_semantic_ann import DiskANN,DiskANNPolicy,build_generation
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticSpan
from skeleton.retrieval.learned_embeddings import _digest
from .offline_disk_index import verify_chunks
from .offline_library import OfflineDocumentLibrary,OfflineLibraryError
from .offline_resources import probe_local_resources,LocalResourcePressure


@dataclass(frozen=True,slots=True)
class ArchiveSemanticPolicy:
    leaf_chars:int=320
    halo_chars:int=160
    batch_size:int=32
    max_source_bytes:int=1024**4
    max_query_sources:int=32
    max_query_scan_bytes:int=256*1024**2
    min_free_ram_bytes:int=64*1024**2

    def __post_init__(self):
        for v,lo,hi in ((self.leaf_chars,64,1024),(self.halo_chars,0,1024),(self.batch_size,1,128),
            (self.max_source_bytes,1,1024**4),(self.max_query_sources,1,128),
            (self.max_query_scan_bytes,1024,1024**4),(self.min_free_ram_bytes,1024**2,16*1024**3)):
            if type(v) is not int or not lo<=v<=hi:raise ValueError("invalid archive semantic policy")

    @property
    def digest(self):
        from dataclasses import asdict
        return _digest(asdict(self))


class ArchiveSemanticSearch:
    """Stream archive-derived vectors and resolve them on demand.

    One read transaction pins the catalog across each build/query. Explicit
    generation activation is required, and stale inventory refuses queries.
    Verification may scan the entire selected document, but bounded Python
    buffers never hold the whole disk-spilled body.
    """
    def __init__(self,library,ranker,policy=ArchiveSemanticPolicy()):
        if not isinstance(library,OfflineDocumentLibrary) or not isinstance(ranker,ContextualRanker) or not isinstance(policy,ArchiveSemanticPolicy):
            raise TypeError("canonical file library and pinned learned ranker required")
        if policy.leaf_chars+2*policy.halo_chars>ranker.policy.context_chars:
            raise ValueError("archive leaf/halo exceeds local encoder context")
        self.library,self.ranker,self.policy=library,ranker,policy
        self.space=_digest(["skeleton.archive-semantic.v1",ranker.identity,policy.digest])
        self.index=None

    @contextmanager
    def _snapshot(self):
        with self.library._lock:
            db=self.library._db
            if db.in_transaction:raise OfflineLibraryError("archive semantic snapshot already active")
            db.execute("BEGIN")
            try:yield db
            finally:db.execute("ROLLBACK")

    def _inventory(self,db):
        return db.execute("""SELECT id,root,relative_path,sha256,size_bytes,
            LENGTH(body) FROM offline_documents ORDER BY id""")

    def _watermark(self,db):
        h=sha256(("archive-semantic-v1:"+self.space).encode())
        for row in self._inventory(db):
            raw=json.dumps(list(row),ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
            h.update(len(raw).to_bytes(8,"big"));h.update(raw)
        return h.hexdigest()

    def watermark(self):
        with self._snapshot() as db:return self._watermark(db)

    def _admit(self,storage,*,write=False):
        snapshot=probe_local_resources(storage)
        if snapshot.available_ram_bytes<self.policy.min_free_ram_bytes or snapshot.memory_pressure_ratio>.9:
            raise LocalResourcePressure("archive semantic work paused for measured memory pressure")
        if write and snapshot.free_disk_bytes<=max(16*1024**2,snapshot.total_disk_bytes//100):
            raise LocalResourcePressure("archive semantic disk reserve is unavailable")
        return snapshot

    @staticmethod
    def _source_id(docid):
        if type(docid) is not int or docid<1:raise OfflineLibraryError("invalid archive source identity")
        return f"archive:{docid}"

    def _pieces(self,db,row,interrupt):
        docid,root,relative,pin,size,chars=row
        if type(size) is not int or not 1<=size<=self.policy.max_source_bytes:
            raise OfflineLibraryError("archive source outside explicit semantic operation bounds")
        h=sha256();observed=0
        if chars:
            # Existing resident path still has its canonical FTS projection.
            # Check it without returning a second complete body to Python.
            if db.execute("""SELECT 1 FROM offline_documents d
                JOIN offline_document_fts f ON d.id=f.rowid
                WHERE d.id=? AND d.body=f.body""",(docid,)).fetchone()!=(1,):
                raise OfflineLibraryError("archive resident projection mismatch")
            if db.execute("SELECT 1 FROM offline_document_chunks WHERE document_id=? LIMIT 1",(docid,)).fetchone():
                raise OfflineLibraryError("archive source has conflicting storage representations")
            for start in range(1,chars+1,16384):
                if interrupt:interrupt()
                (piece,)=db.execute("SELECT substr(body,?,16384) FROM offline_documents WHERE id=?",(start,docid)).fetchone()
                if not isinstance(piece,str) or not piece:raise OfflineLibraryError("archive resident span missing")
                raw=piece.encode();h.update(raw);observed+=len(raw)
                yield piece
        else:
            if not verify_chunks(db,docid,pin,size):
                raise OfflineLibraryError("archive disk chunks failed source custody")
            for (body,) in db.execute("SELECT body FROM offline_document_chunks WHERE document_id=? ORDER BY ordinal",(docid,)):
                if interrupt:interrupt()
                raw=body.encode();h.update(raw);observed+=len(raw)
                # A persistently stored chunk can be larger than model input.
                for offset in range(0,len(body),16384):yield body[offset:offset+16384]
        if observed!=size or h.hexdigest()!=pin:
            raise OfflineLibraryError("archive source changed or failed digest verification")

    def _leaves(self,db,row,interrupt):
        size=self.policy.leaf_chars
        halo=self.policy.halo_chars
        past=""
        pending=""
        ordinal=0
        offset=0
        def emit(leaf,following):
            nonlocal past,ordinal,offset
            context=past+leaf+following[:halo]
            if leaf.strip():
                span=SemanticSpan(self._source_id(row[0]),row[3],ordinal,offset,offset+len(leaf),
                                  leaf,context,len(past),len(past)+len(leaf))
            else:span=None
            past=(past+leaf)[-halo:] if halo else ""
            offset+=len(leaf);ordinal+=1
            return span
        for chunk in self._pieces(db,row,interrupt):
            pending+=chunk
            while len(pending)>=size+halo:
                leaf,pending=pending[:size],pending[size:]
                span=emit(leaf,pending)
                if span is not None:yield span
        while pending:
            leaf,pending=pending[:size],pending[size:]
            span=emit(leaf,pending)
            if span is not None:yield span

    def build(self,root,name,ann_policy,*,previous=None,interrupt=None):
        if not isinstance(ann_policy,DiskANNPolicy):raise TypeError("explicit ANN policy required")
        root=Path(root)
        self._admit(root,write=True)
        if previous is not None and (not isinstance(previous,DiskANN) or previous.space!=self.space):
            raise ValueError("previous archive index feature identity differs")
        counts={"reused":0,"encoded":0,"encode_calls":0,"documents":0}
        def features(batch):
            existing=previous.fetch_dense(batch) if previous else {}
            todo=[s for s in batch if s.identity not in existing]
            fresh,calls=self.ranker._features(todo,None,interrupt) if todo else ({},0)
            counts["reused"]+=len(existing);counts["encoded"]+=len(todo);counts["encode_calls"]+=calls
            for span in batch:yield span,existing.get(span.identity) or fresh[span.identity]
        with self._snapshot() as db:
            pin=self._watermark(db)
            def rows():
                batch=[]
                for row in self._inventory(db):
                    counts["documents"]+=1
                    for span in self._leaves(db,row,interrupt):
                        batch.append(span)
                        if len(batch)>=self.policy.batch_size:
                            self._admit(root,write=True)
                            yield from features(batch);batch.clear()
                if batch:yield from features(batch)
            receipt=build_generation(root,name,rows(),space=self.space,source_snapshot=pin,
                dimension=self.ranker.encoder.policy.dimension,policy=ann_policy,interrupt=interrupt)
        if self.watermark()!=pin:
            raise OfflineLibraryError("archive inventory changed during ANN build; generation is historical")
        return {**receipt,**counts,"source_snapshot":pin,"feature_space":self.space}

    def attach(self,path,manifest_sha256):
        index=DiskANN(path,manifest_sha256,expected_space=self.space,expected_snapshot=self.watermark())
        if index.dimension!=self.ranker.encoder.policy.dimension:raise ValueError("archive vector geometry drift")
        self.index=index

    def search(self,query,*,limit=6,allowed_source_ids=None,interrupt=None):
        if not isinstance(query,str) or not query.strip() or len(query.encode())>4096 or type(limit) is not int or not 1<=limit<=20:
            raise ValueError("bounded archive semantic query required")
        if self.index is None:raise OfflineLibraryError("explicit current archive semantic index required")
        self._admit(self.library.path)
        index=self.index
        with self._snapshot() as db:
            if self._watermark(db)!=index.snapshot:raise OfflineLibraryError("archive semantic generation stale")
            query_vector=self.ranker.encoder.query(query,segments=16)
            candidates,ann_proof=index.search(query,query_vector.dense,allowed_source_ids=allowed_source_ids,
                limit=min(index.policy.global_candidate_limit,self.ranker.policy.candidate_pool))
            groups={}
            for c in candidates:groups.setdefault(c.source_id,[]).append(c)
            if len(groups)>self.policy.max_query_sources:
                raise OfflineLibraryError("archive candidate source count exceeds verification budget")
            spans=[];metadata={};checked=0
            for source_id,group in groups.items():
                if interrupt:interrupt()
                if not source_id.startswith("archive:") or not source_id[8:].isdigit():raise OfflineLibraryError("invalid archive candidate pointer")
                docid=int(source_id[8:])
                if self._source_id(docid)!=source_id:raise OfflineLibraryError("noncanonical archive candidate source")
                row=db.execute("SELECT id,root,relative_path,sha256,size_bytes,LENGTH(body) FROM offline_documents WHERE id=?",(docid,)).fetchone()
                if row is None:raise OfflineLibraryError("archive candidate source revoked")
                checked+=row[4]
                if checked>self.policy.max_query_scan_bytes:
                    raise OfflineLibraryError("archive candidate verification byte budget exhausted")
                wanted={x.ordinal:x for x in group}
                metadata[source_id]=(row[1],row[2])
                # Complete streaming verification before using any candidate.
                for span in self._leaves(db,row,interrupt):
                    c=wanted.pop(span.ordinal,None)
                    if c is not None:
                        if (span.identity,span.revision,span.start,span.end)!=(c.span_sha256,c.source_revision,c.start,c.end):
                            raise OfflineLibraryError("archive ANN span identity mismatch")
                        spans.append(span)
                if wanted:raise OfflineLibraryError("archive candidate exact span absent")
            ranked,proof=self.ranker.search(query,spans,limit=min(limit,self.ranker.policy.candidate_pool),interrupt=interrupt)
            result=[]
            for span,score in ranked:
                left,right=self.ranker.evidence_excerpt(query,span,max_chars=220)
                root,relative=metadata[span.source_id]
                result.append({"source":root,"relative_path":relative,"document_sha256":span.revision,
                    "source_id":span.source_id,"ordinal":span.ordinal,"char_start":span.start+left,
                    "char_end":span.start+right,"excerpt":span.text[left:right],"score":score})
        if self.watermark()!=index.snapshot:raise OfflineLibraryError("archive inventory changed before delivery")
        return tuple(result),{"schema":"skeleton.archive-semantic-search.v1","source_snapshot":index.snapshot,
            "verified_source_bytes":checked,"ann":ann_proof,"rerank":proof,"semantic_entailment_verified":False}
