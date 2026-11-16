"""Local disk-sharded approximate semantic index with bounded parallel fanout.

Derived navigation only: candidate pointers are never citations or authority.
Each immutable generation is published via a create-only directory rename.
The trusted owner must keep the directory private and stable during reads.
No network services, pickle, implicit source imports or model downloads.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing
from dataclasses import asdict,dataclass
import hashlib
from collections import Counter
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time

from .learned_embeddings import SpanEmbedding,_digest,_pin
from .semantic_long_context import SemanticSpan,terms


@dataclass(frozen=True,slots=True)
class DiskANNPolicy:
    shards:int=8
    bands:int=8
    bits:int=12
    probes:int=4
    bucket_limit:int=128
    shard_candidate_limit:int=512
    global_candidate_limit:int=128
    workers:int=4
    max_rows:int=10_000_000
    max_index_bytes:int=64*1024**3
    max_anchor_terms:int=16
    query_timeout_seconds:int=30
    worker_mode:str="thread"

    def __post_init__(self):
        for v,lo,hi in ((self.shards,1,64),(self.bands,2,16),(self.bits,4,20),
                        (self.probes,1,21),(self.bucket_limit,8,4096),
                        (self.shard_candidate_limit,16,8192),(self.global_candidate_limit,1,1024),
                        (self.workers,1,16),(self.max_rows,1,100_000_000),
                        (self.max_index_bytes,1024**2,1024**4),(self.max_anchor_terms,1,32),
                        (self.query_timeout_seconds,1,300)):
            if type(v) is not int or not lo<=v<=hi:
                raise ValueError("invalid local disk ANN policy")
        if self.worker_mode not in {"thread","process"}:
            raise ValueError("explicit local ANN executor mode required")
        if self.bands*self.probes*self.bucket_limit+2*self.max_anchor_terms*self.bucket_limit>262144 or self.shards*self.shard_candidate_limit>262144:
            raise ValueError("aggregate ANN candidate workspace outside bounds")
        if self.probes>self.bits+1 or self.shard_candidate_limit<self.bucket_limit:
            raise ValueError("invalid ANN multi-probe/candidate geometry")

    @property
    def digest(self):return _digest(asdict(self))


def _unit(v,dimension):
    import numpy as np
    a=np.asarray(v,dtype=np.float32)
    if a.shape!=(dimension,) or not np.isfinite(a).all() or abs(float(np.linalg.norm(a))-1)>0.002:
        raise ValueError("ANN requires finite unit vector with exact dimensions")
    return a


def _planes(space,dimension,policy):
    import numpy as np
    # Reproducible seed and explicit NumPy implementation version bound in
    # manifest. Persist a projection digest so a changed RNG fails closed.
    seed=int(hashlib.sha256((space+":"+policy.digest).encode()).hexdigest()[:16],16)
    rng=np.random.Generator(np.random.PCG64(seed))
    p=rng.standard_normal((policy.bands,policy.bits,dimension),dtype=np.float32)
    return p,hashlib.sha256(p.astype("<f4",copy=False).tobytes()).hexdigest()


def _codes(vector,planes,policy):
    import numpy as np
    projections=planes@vector
    out=[]
    for band,row in enumerate(projections):
        code=sum(int(v>=0)<<i for i,v in enumerate(row))
        # Multiprobe adjacent Hamming buckets by ascending displacement
        # margin, not an exhaustive scan of all signatures.
        bits=sorted(range(policy.bits),key=lambda i:(abs(float(row[i])),i))
        out.append((band,code,tuple(code^(1<<i) for i in bits[:policy.probes-1])))
    return out


def _private_root(root):
    root=Path(os.path.abspath(root))
    if root.resolve(strict=True)!=root or not root.is_dir():
        raise PermissionError("ANN root must be an existing non-symlinked directory")
    observed=root.stat()
    if os.name=="posix" and (observed.st_uid!=os.geteuid() or observed.st_mode&0o077):
        raise PermissionError("ANN root must be owner-private")
    return root


def _hash_file(path,limit):
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size>limit:
        raise ValueError("ANN artifact outside file bounds")
    ident=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    h=hashlib.sha256()
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as stream:
        if ident(os.fstat(stream.fileno()))!=ident(before):
            raise OSError("ANN artifact replaced")
        for block in iter(lambda:stream.read(1024**2),b""):h.update(block)
        if ident(os.fstat(stream.fileno()))!=ident(before) or ident(path.lstat())!=ident(before):
            raise OSError("ANN artifact changed")
    return h.hexdigest(),before.st_size,ident(before)


def _sync_dir(root):
    if os.name=="posix":
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


def _anchors(text,limit):
    return tuple(sorted({x for x in terms(text) if len(x)<=128 and
        (any(c.isdigit() for c in x) or any(c in "-_.:" for c in x))}))[:limit]


def _sparse(text):
    # Full normalized terms, not only identifiers. Bounded per-leaf storage;
    # digests are derived features, not a privacy boundary.
    words=Counter(x for x in terms(text) if 1<=len(x)<=128)
    return [(hashlib.sha256(term.encode()).hexdigest(),min(count,255))
            for term,count in sorted(words.items(),key=lambda x:(-x[1],x[0]))[:256]]


def _init(db):
    db.executescript("""
      PRAGMA journal_mode=DELETE;
      PRAGMA synchronous=FULL;
      PRAGMA temp_store=FILE;
      CREATE TABLE leaves(id INTEGER PRIMARY KEY, span TEXT NOT NULL UNIQUE,
        source TEXT NOT NULL, revision TEXT NOT NULL, ordinal INTEGER NOT NULL,
        start INTEGER NOT NULL,end INTEGER NOT NULL,vector BLOB NOT NULL,
        UNIQUE(source,revision,ordinal));
      CREATE TABLE buckets(band INTEGER NOT NULL,code INTEGER NOT NULL,
        id INTEGER NOT NULL REFERENCES leaves(id),PRIMARY KEY(band,code,id)) WITHOUT ROWID;
      CREATE TABLE sparse(term TEXT NOT NULL,id INTEGER NOT NULL REFERENCES leaves(id),
        tf INTEGER NOT NULL,PRIMARY KEY(term,id)) WITHOUT ROWID;
      CREATE TABLE anchors(term TEXT NOT NULL,id INTEGER NOT NULL REFERENCES leaves(id),
        PRIMARY KEY(term,id)) WITHOUT ROWID;
    """)


def build_generation(root,name,rows,*,space,source_snapshot,dimension,
                     policy:DiskANNPolicy=DiskANNPolicy(),interrupt=None):
    """Stream individual verified spans/features into physically distinct shards.

    The caller, not the index, is responsible for constructing the source
    snapshot digest from its authority. All writes occur in staging and an
    exact manifest is returned only after every shard is closed and hashed.
    """
    import numpy as np
    if not isinstance(policy,DiskANNPolicy) or not _pin(space) or not _pin(source_snapshot):
        raise ValueError("pinned semantic space and source snapshot required")
    if type(dimension) is not int or not 2<=dimension<=4096:
        raise ValueError("invalid ANN vector dimension")
    if not isinstance(name,str) or not 1<=len(name)<=64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise ValueError("invalid generation name")
    root=_private_root(root)
    target=root/name
    if target.exists() or target.is_symlink():
        raise FileExistsError("new semantic ANN generation required")
    stage=Path(tempfile.mkdtemp(prefix=".ann-build-",dir=root))
    dbs=[]
    try:
        planes,plane_hash=_planes(space,dimension,policy)
        for i in range(policy.shards):
            path=stage/f"shard-{i:03d}.sqlite"
            db=sqlite3.connect(path,isolation_level=None)
            dbs.append(db)
            _init(db)
            db.execute("BEGIN")
        counts=[0]*policy.shards
        processed=0
        logical=0
        for span,feature in rows:
            if interrupt:interrupt()
            if not isinstance(span,SemanticSpan) or not isinstance(feature,SpanEmbedding):
                raise TypeError("verified semantic span and learned feature required")
            processed+=1
            if processed>policy.max_rows:
                raise MemoryError("ANN row ceiling exceeded")
            vector=_unit(feature.dense,dimension)
            blob=vector.astype("<f4",copy=False).tobytes()
            anchors=_anchors(span.text,policy.max_anchor_terms)
            sparse=_sparse(span.text)
            logical+=len(blob)+len(span.source_id.encode())+512+policy.bands*48+sum(len(x.encode())+48 for x in anchors)+len(sparse)*144
            if logical>policy.max_index_bytes:
                raise MemoryError("ANN logical disk reservation exceeded")
            shard=int(span.identity[:16],16)%policy.shards
            db=dbs[shard]
            row=db.execute("INSERT INTO leaves(span,source,revision,ordinal,start,end,vector) VALUES(?,?,?,?,?,?,?)",
                (span.identity,span.source_id,span.revision,span.ordinal,span.start,span.end,blob))
            rid=row.lastrowid
            db.executemany("INSERT INTO buckets VALUES(?,?,?)",[(band,code,rid) for band,code,_ in _codes(vector,planes,policy)])
            db.executemany("INSERT INTO anchors VALUES(?,?)",[(a,rid) for a in anchors])
            db.executemany("INSERT INTO sparse VALUES(?,?,?)",[(term,rid,tf) for term,tf in sparse])
            counts[shard]+=1
            if processed%1024==0:
                if sum(p.stat().st_size for p in stage.iterdir() if p.is_file())>policy.max_index_bytes:
                    raise MemoryError("ANN physical staging budget exceeded")
                for db in dbs:
                    db.execute("COMMIT")
                    db.execute("BEGIN")
        if not processed:raise ValueError("empty ANN source generation")
        for db in dbs:
            db.execute("COMMIT")
            db.close()
        dbs.clear()
        artifacts=[]
        for i,count in enumerate(counts):
            path=stage/f"shard-{i:03d}.sqlite"
            with path.open("rb") as handle:os.fsync(handle.fileno())
            pin,size,_=_hash_file(path,policy.max_index_bytes)
            artifacts.append({"name":path.name,"sha256":pin,"bytes":size,"rows":count})
        if sum(x["bytes"] for x in artifacts)>policy.max_index_bytes:
            raise MemoryError("ANN physical generation exceeds disk budget")
        manifest={"schema":"skeleton.local.disk-ann.v2","space":space,"source_snapshot":source_snapshot,
                  "dimension":dimension,"projection_sha256":plane_hash,"numpy_version":np.__version__,
                  "policy":asdict(policy),"rows":processed,"artifacts":artifacts}
        raw=json.dumps(manifest,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        with (stage/"manifest.json").open("xb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        _sync_dir(stage)
        # No overwrite of any valid competing generation. A concurrent
        # published target contains files and POSIX rename rejects it.
        if target.exists() or target.is_symlink():raise FileExistsError("generation name occupied")
        os.rename(stage,target)
        _sync_dir(root)
        return {"path":str(target),"manifest_sha256":hashlib.sha256(raw).hexdigest(),
                "rows":processed,"shards":policy.shards,"bytes":sum(x["bytes"] for x in artifacts)}
    finally:
        for db in dbs:db.close()
        if stage.exists():shutil.rmtree(stage)


@dataclass(frozen=True,slots=True)
class ANNCandidate:
    span_sha256:str
    source_id:str
    source_revision:str
    ordinal:int
    start:int
    end:int
    cosine:float
    anchor_matches:int
    lexical_matches:int=0


class DiskANN:
    """Read-only immutable per-shard search. Full artifact hashes on admission."""
    def __init__(self,root,manifest_sha256,*,expected_space,expected_snapshot):
        import numpy as np
        if not all(_pin(x) for x in (manifest_sha256,expected_space,expected_snapshot)):
            raise ValueError("exact ANN configuration pins required")
        self.root=_private_root(root)
        file=self.root/"manifest.json"
        pin,size,_=_hash_file(file,256*1024)
        raw=file.read_bytes()
        if pin!=manifest_sha256 or hashlib.sha256(raw).hexdigest()!=pin or len(raw)!=size:
            raise ValueError("ANN manifest digest mismatch")
        m=json.loads(raw)
        if m.get("schema") not in {"skeleton.local.disk-ann.v1","skeleton.local.disk-ann.v2"} or m.get("space")!=expected_space or m.get("source_snapshot")!=expected_snapshot or m.get("numpy_version")!=np.__version__:
            raise ValueError("ANN source/feature/runtime identity mismatch")
        self.schema=m["schema"]
        self.policy=DiskANNPolicy(**m["policy"])
        self.dimension=m["dimension"]
        if type(self.dimension) is not int or not 2<=self.dimension<=4096:
            raise ValueError("invalid ANN manifest geometry")
        self._planes,projection=_planes(expected_space,self.dimension,self.policy)
        if projection!=m["projection_sha256"]:
            raise ValueError("ANN projection drift")
        files=m["artifacts"]
        if not isinstance(files,list) or len(files)!=self.policy.shards or type(m["rows"]) is not int or not 1<=m["rows"]<=self.policy.max_rows:
            raise ValueError("invalid ANN shard manifest")
        self._files=[]
        for i,row in enumerate(files):
            if set(row)!={"name","sha256","bytes","rows"} or row["name"]!=f"shard-{i:03d}.sqlite" or not _pin(row["sha256"]) or type(row["bytes"]) is not int or type(row["rows"]) is not int or row["rows"]<0:
                raise ValueError("invalid ANN ordered artifact record")
            path=self.root/row["name"]
            observed,actual,identity=_hash_file(path,self.policy.max_index_bytes)
            if observed!=row["sha256"] or actual!=row["bytes"]:
                raise ValueError("ANN shard byte custody mismatch")
            self._files.append((path,identity,row["rows"]))
        if sum(x["rows"] for x in files)!=m["rows"] or sum(x["bytes"] for x in files)>self.policy.max_index_bytes:
            raise ValueError("ANN manifest aggregate mismatch")
        self.space,self.snapshot,self.manifest_sha256=expected_space,expected_snapshot,manifest_sha256
        self.rows=m["rows"]

    def _assert_identity(self,entry):
        path,expected,_=entry
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=expected:
            raise OSError("ANN shard changed after admission")

    def fetch_dense(self,spans):
        """Reuse exact previously encoded leaves, never stale source revisions.

        The previous immutable generation is independently pinned on open.
        Missing rows are returned as misses rather than guessed embeddings.
        """
        import numpy as np
        if not isinstance(spans,(list,tuple)) or len(spans)>256 or any(not isinstance(s,SemanticSpan) for s in spans):
            raise ValueError("bounded exact semantic reuse batch required")
        grouped={}
        for span in spans:
            grouped.setdefault(int(span.identity[:16],16)%self.policy.shards,[]).append(span)
        found={}
        for shard,group in grouped.items():
            entry=self._files[shard]
            self._assert_identity(entry)
            db=sqlite3.connect(entry[0].as_uri()+"?mode=ro&immutable=1",uri=True,timeout=1)
            try:
                db.execute("PRAGMA query_only=ON")
                db.execute("PRAGMA trusted_schema=OFF")
                for span in group:
                    row=db.execute("SELECT source,revision,ordinal,start,end,vector FROM leaves WHERE span=?",(span.identity,)).fetchone()
                    if row is None:continue
                    if tuple(row[:5])!=(span.source_id,span.revision,span.ordinal,span.start,span.end) or len(row[5])!=4*self.dimension:
                        raise ValueError("prior semantic vector provenance mismatch")
                    dense=_unit(np.frombuffer(row[5],dtype="<f4"),self.dimension)
                    # Derived dense-only record; never used as a late-interaction vector.
                    found[span.identity]=SpanEmbedding(tuple(map(float,dense)),())
                self._assert_identity(entry)
            finally:db.close()
        return found

    def _search(self,entry,q,codes,anchors,sparse_terms,deadline,allowed):
        import numpy as np
        path,_,_=entry
        self._assert_identity(entry)
        db=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True,timeout=1)
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
            p=self.policy
            candidates={}
            exhausted=False
            filters=" AND l.source IN ("+",".join("?" for _ in allowed)+")" if allowed else ""
            def collect(sql,args,channel=0):
                nonlocal exhausted
                for index,(rid,) in enumerate(db.execute(sql+filters+" ORDER BY l.id LIMIT ?",(*args,*allowed,p.bucket_limit+1))):
                    if index>=p.bucket_limit:
                        exhausted=True;break
                    previous=candidates.setdefault(rid,[0,0,0])
                    previous[channel]+=1
            for term in anchors:
                if time.monotonic()>=deadline:raise TimeoutError("ANN shard deadline exceeded")
                collect("SELECT l.id FROM anchors a JOIN leaves l ON l.id=a.id WHERE a.term=?",(term,),True)
            if self.schema=="skeleton.local.disk-ann.v2":
                # Exact sparse postings form a complementary candidate channel.
                # Query terms capped, identifier channel retains priority.
                for term in sparse_terms:
                    if time.monotonic()>=deadline:raise TimeoutError("ANN sparse deadline exceeded")
                    collect("SELECT l.id FROM sparse s JOIN leaves l ON l.id=s.id WHERE s.term=?",(term,),2)
            for band,code,neighbors in codes:
                for signature in (code,*neighbors):
                    if time.monotonic()>=deadline:raise TimeoutError("ANN shard deadline exceeded")
                    collect("SELECT l.id FROM buckets b JOIN leaves l ON l.id=b.id WHERE b.band=? AND b.code=?",(band,signature))
            ordered=sorted(candidates,key=lambda rid:(-candidates[rid][1],-(candidates[rid][0]+2*candidates[rid][2]),rid))
            if len(ordered)>p.shard_candidate_limit:exhausted=True
            results=[]
            for rid in ordered[:p.shard_candidate_limit]:
                if time.monotonic()>=deadline:raise TimeoutError("ANN shard rerank deadline exceeded")
                row=db.execute("SELECT span,source,revision,ordinal,start,end,vector FROM leaves WHERE id=?",(rid,)).fetchone()
                if row is None or not _pin(row[0]) or not _pin(row[2]) or len(row[6])!=4*self.dimension:
                    raise ValueError("ANN candidate row is invalid")
                if allowed and row[1] not in allowed:
                    raise PermissionError("ANN allowed-source filter drift")
                vector=_unit(np.frombuffer(row[6],dtype="<f4"),self.dimension)
                score=float(np.clip(vector@q,-1,1))
                results.append(ANNCandidate(*row[:6],score,candidates[rid][1],candidates[rid][2]))
            self._assert_identity(entry)
            results.sort(key=lambda row:(-row.anchor_matches,-(row.cosine+min(row.lexical_matches,8)*.035),row.span_sha256))
            return results[:p.global_candidate_limit],exhausted,len(candidates)
        finally:db.close()

    def search(self,query,vector,*,allowed_source_ids=None,limit=None,worker_limit=None):
        """Bounded concurrent read-only fanout; no partial success on shard loss."""
        if not isinstance(query,str) or not query.strip() or len(query.encode())>16384:
            raise ValueError("invalid ANN query")
        allowed=() if allowed_source_ids is None else tuple(allowed_source_ids)
        if allowed_source_ids is not None and (not 1<=len(allowed)<=256 or len(set(allowed))!=len(allowed) or any(not isinstance(x,str) or not 1<=len(x)<=256 for x in allowed)):
            raise ValueError("explicit allowed-source selection outside bounds")
        p=self.policy
        limit=p.global_candidate_limit if limit is None else limit
        if type(limit) is not int or not 1<=limit<=p.global_candidate_limit:
            raise ValueError("ANN global result budget exceeded")
        q=_unit(vector,self.dimension)
        codes=_codes(q,self._planes,p)
        anchors=_anchors(query,p.max_anchor_terms)
        sparse_terms=tuple(x[0] for x in _sparse(query)[:min(16,p.max_anchor_terms)])
        deadline=time.monotonic()+p.query_timeout_seconds
        merged=[]
        count=0
        truncated=False
        if worker_limit is not None and (type(worker_limit) is not int or not 1<=worker_limit<=p.workers):
            raise ValueError("invalid measured worker concurrency bound")
        workers=min(p.workers,p.shards,worker_limit if worker_limit is not None else p.workers)
        pool=(ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context("spawn"))
              if p.worker_mode=="process" else ThreadPoolExecutor(max_workers=workers))
        # The process executor serializes only trusted internally constructed
        # value objects, never an imported pickle or external worker payload.
        with pool as executor:
            futures=[executor.submit(self._search,entry,q,codes,anchors,sparse_terms,deadline,allowed) for entry in self._files]
            for f in futures:
                rows,cut,observed=f.result(timeout=max(0.001,deadline-time.monotonic()))
                merged.extend(rows);truncated|=cut;count+=observed
        if len({row.span_sha256 for row in merged})!=len(merged):
            raise ValueError("duplicate candidate across ANN shards")
        ranked=sorted(merged,key=lambda x:(-x.anchor_matches,-(x.cosine+min(x.lexical_matches,8)*.035),x.span_sha256))[:limit]
        receipt={"schema":"skeleton.local.disk-ann-query.v1","manifest_sha256":self.manifest_sha256,
                 "space_sha256":self.space,"source_snapshot_sha256":self.snapshot,
                 "shards_searched":len(self._files),"workers_admitted":workers,"worker_mode":p.worker_mode,"indexed_rows":self.rows,"candidate_pointers":count,
                 "bucket_or_shard_truncation":bool(truncated),"sparse_candidate_channel":self.schema=="skeleton.local.disk-ann.v2","approximate":True,
                 "selected":[r.span_sha256 for r in ranked],"citation_authorized":False}
        receipt["receipt_sha256"]=_digest(receipt)
        return tuple(ranked),receipt
