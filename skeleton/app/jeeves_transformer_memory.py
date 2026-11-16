"""Revision-bound transformer sentence retrieval for approved local memories.

The approved-memory table remains the sole content authority. This is a
derived, replaceable index. Install/replace/remove is explicit owner CLI;
search never downloads assets, and writes never occur during query execution.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import math
import re
import struct
import threading
import time

from skeleton.app.jeeves_approved_memory import ApprovedMemory,MemoryRejected,MemoryConflict,KINDS
from skeleton.app.jeeves_sentence_encoder import EncoderSpec,SentenceEncoder,EncoderUnavailable,MAX_BATCH
from skeleton.app.jeeves_memory_vectors import _signatures,_probes,LSH_BANDS
from skeleton.app.jeeves_deliberation import digest,stable

SCHEMA="skeleton.jeeves.transformer-memory-index.v1"
MAX_REFRESH=64
MAX_CANDIDATES=4096
MAX_RESULTS=20
MAX_QUERY_BYTES=1024
_SHA=re.compile(r"[0-9a-f]{64}\Z")
_ID=re.compile(r"[A-Za-z0-9_-]{8,100}\Z")


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise MemoryRejected("invalid transformer index identity")
    return value


def _bounded_number(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise MemoryRejected("invalid transformer index limit")
    return value


def _text(value,limit):
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise MemoryRejected("invalid transformer index query")
    try:
        if len(value.encode("utf-8"))>limit:
            raise MemoryRejected("transformer index text exceeds byte budget")
    except UnicodeError:
        raise MemoryRejected("invalid transformer index Unicode") from None
    return value


def _pack(vector,dimension):
    if type(vector) is not tuple or len(vector)!=dimension:
        raise MemoryRejected("unexpected sentence vector dimension")
    if any(type(x) not in (float,int) or not math.isfinite(x) or abs(x)>1.00001 for x in vector):
        raise MemoryRejected("invalid finite sentence vector")
    norm=math.sqrt(math.fsum(x*x for x in vector))
    if abs(norm-1)>1e-5:
        raise MemoryRejected("sentence vector norm mismatch")
    raw=struct.pack("<"+"f"*dimension,*vector)
    return raw


def _unpack(raw,dimension):
    if type(raw) is not bytes or len(raw)!=4*dimension:
        raise MemoryRejected("stored sentence vector size mismatch")
    values=struct.unpack("<"+"f"*dimension,raw)
    norm=math.sqrt(math.fsum(x*x for x in values))
    if not math.isfinite(norm) or abs(norm-1)>1e-4:
        raise MemoryRejected("stored sentence vector norm mismatch")
    return values


def _blob_sha(raw):
    return sha256(raw).hexdigest()


def _pin(row):
    return row["memory_id"],row["revision"],row["sha256"]


def _document(row):
    return _text(row["label"]+"\n"+row["text"]+"\n"+"\n".join(row["tags"]),4096)


class TransformerMemoryIndex:
    """One model/tokenizer chat scope and one optional sentence encoder."""

    def __init__(self,memory: ApprovedMemory,*,encoder_factory=SentenceEncoder):
        if not isinstance(memory,ApprovedMemory):
            raise MemoryRejected("canonical approved memory required")
        self.memory=memory
        self.store=memory.store
        # Injectable only for focused tests; HTTP/CLI always use real encoder.
        self._factory=encoder_factory
        self._lock=threading.RLock()
        self._encoder=None
        with self.store._transaction():
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_transformer_encoder (
                model_digest TEXT NOT NULL,tokenizer_digest TEXT NOT NULL,
                encoder_identity TEXT NOT NULL,spec_json TEXT NOT NULL,spec_sha256 TEXT NOT NULL,
                probe_json TEXT NOT NULL,probe_sha256 TEXT NOT NULL,
                PRIMARY KEY(model_digest,tokenizer_digest)
            )""")
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_transformer_vectors (
                memory_id TEXT PRIMARY KEY REFERENCES jeeves_approved_memory(memory_id) ON DELETE CASCADE,
                encoder_identity TEXT NOT NULL,memory_revision INTEGER NOT NULL,
                memory_sha256 TEXT NOT NULL,document_sha256 TEXT NOT NULL,
                vector BLOB NOT NULL,vector_sha256 TEXT NOT NULL
            )""")
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_transformer_buckets (
                memory_id TEXT NOT NULL REFERENCES jeeves_transformer_vectors(memory_id) ON DELETE CASCADE,
                encoder_identity TEXT NOT NULL,band INTEGER NOT NULL CHECK(band>=0 AND band<6),
                signature INTEGER NOT NULL CHECK(signature>=0 AND signature<256),
                PRIMARY KEY(memory_id,band)
            ) WITHOUT ROWID""")
            self.store._db.execute("""CREATE INDEX IF NOT EXISTS jeeves_transformer_bucket_lookup
                ON jeeves_transformer_buckets(encoder_identity,band,signature,memory_id)""")

    def _bank(self):
        row=self.store._db.execute(
            "SELECT encoder_identity,spec_json,spec_sha256,probe_json,probe_sha256 "
            "FROM jeeves_transformer_encoder WHERE model_digest=? AND tokenizer_digest=?",
            self.memory.scope,
        ).fetchone()
        if row is None:
            return None
        identity,spec_json,spec_sha,probe_json,probe_sha=row
        try:
            if (type(spec_json) is not str or len(spec_json.encode())>8192
                    or type(probe_json) is not str or len(probe_json.encode())>4096
                    or digest(spec_json)!=_sha(spec_sha) or digest(probe_json)!=_sha(probe_sha)):
                raise MemoryRejected("transformer encoder manifest integrity mismatch")
            spec=EncoderSpec.parse(json.loads(spec_json))
            probe=json.loads(probe_json)
            if (spec.identity!=_sha(identity) or stable(spec.as_dict())!=spec_json
                    or type(probe) is not dict or stable(probe)!=probe_json
                    or probe.get("encoder_identity")!=identity
                    or probe.get("dimensions")!=spec.dimensions
                    or probe.get("document_vectors")!=2 or probe.get("query_vectors")!=1
                    or probe.get("query_path_executed") is not True
                    or probe.get("document_path_executed") is not True
                    or probe.get("independent_quality_certified") is not False):
                raise MemoryRejected("stored transformer probe or manifest mismatch")
            return spec,probe
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise MemoryRejected("invalid stored transformer bank") from None

    @contextmanager
    def _loaded(self,spec):
        with self._lock:
            if self._encoder is not None and self._encoder.spec!=spec:
                self._encoder.close()
                self._encoder=None
            if self._encoder is None:
                self._encoder=self._factory(spec)
            self._encoder.assert_stable()
            yield self._encoder

    def close(self):
        with self._lock:
            if self._encoder is not None:
                self._encoder.close()
                self._encoder=None

    def _count_active(self,now):
        return self.store._db.execute(
            "SELECT count(*) FROM jeeves_approved_memory WHERE model_digest=? AND tokenizer_digest=? "
            "AND (expires_at IS NULL OR expires_at>?)",(*self.memory.scope,now),
        ).fetchone()[0]

    def _where(self,identity,kinds,now):
        category="" if kinds is None else " AND m.kind IN ("+",".join("?" for _ in kinds)+")"
        sql=("m.model_digest=? AND m.tokenizer_digest=? "
             "AND (m.expires_at IS NULL OR m.expires_at>?) AND v.encoder_identity=? "
             "AND v.memory_revision=m.revision AND v.memory_sha256=m.content_sha256"+category+
             " AND (SELECT count(*) FROM jeeves_transformer_buckets b "
             "WHERE b.memory_id=v.memory_id AND b.encoder_identity=v.encoder_identity)=?")
        return sql,(*self.memory.scope,now,identity,*(kinds or []),LSH_BANDS)

    def status(self):
        with self.store.read_snapshot():
            bank=self._bank();now=int(time.time())
            active=self._count_active(now);indexed=0
            if bank is not None:
                spec,probe=bank
                where,params=self._where(spec.identity,None,now)
                indexed=self.store._db.execute(
                    "SELECT count(*) FROM jeeves_transformer_vectors v JOIN jeeves_approved_memory m "
                    "ON m.memory_id=v.memory_id WHERE "+where,params,
                ).fetchone()[0]
                public={"encoder_identity":spec.identity,**spec.as_dict(private=False),
                        "prior_install_smoke":probe}
            else:
                public=None
            return {"schema":SCHEMA,"model_digest":self.memory.scope[0],
                    "tokenizer_digest":self.memory.scope[1],"bank":public,
                    "active_memories":active,"indexed_active_memories":indexed,
                    "index_complete_snapshot":bank is not None and indexed==active,
                    "remote_calls":False,"runtime_readiness_rechecked":False,
                    "semantic_quality_certified":False}

    def install(self,spec: EncoderSpec,*,approved: bool,expected_prior: str|None=None):
        if approved is not True or not isinstance(spec,EncoderSpec):
            raise MemoryRejected("explicit validated encoder installation required")
        # Direct dataclass instances must also satisfy the public parser.
        if EncoderSpec.parse(spec.as_dict())!=spec:
            raise MemoryRejected("noncanonical encoder manifest")
        if expected_prior is not None:
            _sha(expected_prior)
        with self._lock:
            with self.store.read_snapshot():
                old=self._bank()
                if (old[0].identity if old else None)!=expected_prior:
                    raise MemoryConflict("transformer encoder changed before install")
            # Genuine encoder inference before write admission; if any
            # dependency or model fails, the old bank/index survives unchanged.
            candidate=self._factory(spec)
            try:
                probe=candidate.qualification()
                spec_json=stable(spec.as_dict());probe_json=stable(probe)
                if (len(probe_json.encode())>4096 or probe.get("encoder_identity")!=spec.identity
                        or probe.get("document_vectors")!=2 or probe.get("query_vectors")!=1
                        or probe.get("query_path_executed") is not True
                        or probe.get("document_path_executed") is not True
                        or probe.get("dimensions")!=spec.dimensions
                        or probe.get("independent_quality_certified") is not False):
                    raise MemoryRejected("encoder qualification shape mismatch")
                candidate.assert_stable()
                with self.store._transaction():
                    old=self._bank()
                    if (old[0].identity if old else None)!=expected_prior:
                        raise MemoryConflict("transformer encoder changed during install")
                    self._clear_index()
                    self.store._db.execute(
                        "INSERT INTO jeeves_transformer_encoder VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(model_digest,tokenizer_digest) DO UPDATE SET "
                        "encoder_identity=excluded.encoder_identity,spec_json=excluded.spec_json,"
                        "spec_sha256=excluded.spec_sha256,probe_json=excluded.probe_json,"
                        "probe_sha256=excluded.probe_sha256",
                        (*self.memory.scope,spec.identity,spec_json,digest(spec_json),probe_json,digest(probe_json)),
                    )
                    self._bank()
            except BaseException:
                candidate.close()
                raise
            if self._encoder is not None:
                self._encoder.close()
            self._encoder=candidate
        return self.status()

    def _clear_index(self):
        self.store._db.execute(
            "DELETE FROM jeeves_transformer_vectors WHERE memory_id IN "
            "(SELECT memory_id FROM jeeves_approved_memory WHERE model_digest=? AND tokenizer_digest=?)",
            self.memory.scope,
        )

    def uninstall(self,identity: str,*,approved: bool):
        _sha(identity)
        if approved is not True:
            raise MemoryRejected("explicit transformer removal required")
        with self._lock:
            with self.store._transaction():
                bank=self._bank()
                if bank is None or bank[0].identity!=identity:
                    raise MemoryConflict("transformer encoder changed")
                self._clear_index()
                self.store._db.execute(
                    "DELETE FROM jeeves_transformer_encoder WHERE model_digest=? AND tokenizer_digest=?",
                    self.memory.scope,
                )
            self.close()
        return self.status()

    def refresh(self,*,expected_encoder: str,approved: bool,cursor: str|None=None,limit: int=16):
        _sha(expected_encoder);_bounded_number(limit,1,MAX_REFRESH)
        if approved is not True or (cursor is not None and (type(cursor) is not str or not _ID.fullmatch(cursor))):
            raise MemoryRejected("invalid explicit transformer refresh request")
        # Establish consistent content pins, release SQLite before model work,
        # then atomically recheck every pin and the bank at publication.
        with self.store.read_snapshot():
            bank=self._bank()
            if bank is None or bank[0].identity!=expected_encoder:
                raise MemoryConflict("transformer encoder changed")
            spec,_=bank;now=int(time.time())
            rows=self.store._db.execute(
                "SELECT memory_id FROM jeeves_approved_memory WHERE model_digest=? AND tokenizer_digest=? "
                "AND memory_id>? AND (expires_at IS NULL OR expires_at>?) ORDER BY memory_id LIMIT ?",
                (*self.memory.scope,cursor or "",now,limit+1),
            ).fetchall()
            source=[self.memory._find(mid,now=now) for (mid,) in rows[:limit]]
        encoded=[]
        if source:
            with self._loaded(spec) as encoder:
                for i in range(0,len(source),MAX_BATCH):
                    page=source[i:i+MAX_BATCH]
                    documents=[_document(r) for r in page]
                    vectors=encoder.encode(documents,query=False)
                    if len(vectors)!=len(page):
                        raise MemoryRejected("incomplete transformer inference batch")
                    for row,text,values in zip(page,documents,vectors):
                        raw=_pack(values,spec.dimensions)
                        encoded.append((_pin(row),digest(text),raw,
                            _blob_sha(raw),_signatures(_unpack(raw,spec.dimensions))))
                encoder.assert_stable()
                with self.store._transaction():
                    current=self._bank()
                    if current is None or current[0]!=spec:
                        raise MemoryConflict("transformer encoder changed before index publication")
                    for pin,doc_sha,raw,vector_sha,buckets in encoded:
                        record=self.memory._find(pin[0],now=int(time.time()))
                        if not record["active"] or _pin(record)!=pin or digest(_document(record))!=doc_sha:
                            raise MemoryConflict("memory changed before vector publication; retry page")
                        self.store._db.execute(
                            "INSERT INTO jeeves_transformer_vectors VALUES(?,?,?,?,?,?,?) "
                            "ON CONFLICT(memory_id) DO UPDATE SET "
                            "encoder_identity=excluded.encoder_identity,memory_revision=excluded.memory_revision,"
                            "memory_sha256=excluded.memory_sha256,document_sha256=excluded.document_sha256,"
                            "vector=excluded.vector,vector_sha256=excluded.vector_sha256",
                            (pin[0],expected_encoder,pin[1],pin[2],doc_sha,raw,vector_sha),
                        )
                        self.store._db.execute(
                            "DELETE FROM jeeves_transformer_buckets WHERE memory_id=?",(pin[0],))
                        self.store._db.executemany(
                            "INSERT INTO jeeves_transformer_buckets VALUES(?,?,?,?)",
                            [(pin[0],expected_encoder,i,signature)
                             for i,signature in enumerate(buckets)],
                        )
        return {"encoder_identity":expected_encoder,"processed":len(encoded),
                "next_cursor":rows[limit-1][0] if len(rows)>limit else None,
                "index_complete_not_certified":True}

    def _candidates(self,vector,spec,kinds,now):
        where,params=self._where(spec.identity,kinds,now)
        join=("FROM jeeves_transformer_vectors v JOIN jeeves_approved_memory m "
              "ON m.memory_id=v.memory_id WHERE ")
        eligible=self.store._db.execute("SELECT count(*) "+join+where,params).fetchone()[0]
        exact=eligible<=MAX_CANDIDATES
        fields="v.memory_id,v.memory_revision,v.memory_sha256,v.document_sha256,v.vector,v.vector_sha256 "
        if exact:
            rows=self.store._db.execute("SELECT "+fields+join+where+
                " ORDER BY v.memory_id LIMIT ?",(*params,MAX_CANDIDATES+1)).fetchall()
        else:
            probes=_probes(vector)
            marks=",".join("(?,?,?)" for _ in probes)
            rows=self.store._db.execute(
                "WITH probes(band,signature,weight) AS (VALUES "+marks+"), "
                "candidates AS (SELECT v.memory_id,SUM(p.weight) AS priority "
                "FROM probes p JOIN jeeves_transformer_buckets b ON b.band=p.band AND "
                "b.signature=p.signature JOIN jeeves_transformer_vectors v ON v.memory_id=b.memory_id "
                "JOIN jeeves_approved_memory m ON m.memory_id=v.memory_id WHERE "
                "b.encoder_identity=v.encoder_identity AND "+where+
                " GROUP BY v.memory_id ORDER BY priority DESC,v.memory_id LIMIT ?) "
                "SELECT "+fields+"FROM candidates c JOIN jeeves_transformer_vectors v "
                "ON v.memory_id=c.memory_id ORDER BY c.priority DESC,v.memory_id",
                (*(value for probe in probes for value in probe),*params,MAX_CANDIDATES+1),
            ).fetchall()
        return rows,eligible,exact

    def search(self,query: str,*,limit: int=8,kinds: list[str]|None=None):
        query=_text(query,MAX_QUERY_BYTES);_bounded_number(limit,1,MAX_RESULTS)
        if kinds is not None and (type(kinds) is not list or not kinds or
                any(type(k) is not str or k not in KINDS for k in kinds) or len(set(kinds))!=len(kinds)):
            raise MemoryRejected("invalid transformer memory kind filter")
        with self.store.read_snapshot():
            bank=self._bank()
            if bank is None:
                return {"schema":SCHEMA,"records":[],"enabled":False,
                        "semantic_quality_certified":False,"remote_calls":False}
            spec,_=bank
        with self._loaded(spec) as encoder:
            encoded=encoder.encode([query],query=True)
            if len(encoded)!=1:
                raise MemoryRejected("transformer query batch mismatch")
            vector=_unpack(_pack(encoded[0],spec.dimensions),spec.dimensions)
            with self.store.read_snapshot():
                current=self._bank()
                if current is None or current[0]!=spec:
                    raise MemoryConflict("transformer encoder changed during search")
                now=int(time.time())
                rows,eligible,exact=self._candidates(vector,spec,kinds,now)
                scored=[]
                for mid,revision,sha,doc_sha,raw,vector_sha in rows[:MAX_CANDIDATES]:
                    if _blob_sha(raw)!=_sha(vector_sha):
                        raise MemoryRejected("transformer vector integrity mismatch")
                    value=_unpack(raw,spec.dimensions)
                    # Validate projected buckets for every scored candidate.
                    observed=self.store._db.execute(
                        "SELECT band,signature FROM jeeves_transformer_buckets "
                        "WHERE memory_id=? AND encoder_identity=? ORDER BY band",(mid,spec.identity),
                    ).fetchall()
                    if observed!=list(enumerate(_signatures(value))):
                        raise MemoryRejected("transformer vector bucket mismatch")
                    cosine=math.fsum(a*b for a,b in zip(value,vector))
                    scored.append((cosine,mid,revision,sha,doc_sha))
                scored.sort(key=lambda row:(-row[0],row[1]))
                results=[]
                for score,mid,revision,sha,doc_sha in scored[:limit]:
                    record=self.memory._find(mid,now=now)
                    if _pin(record)!=(mid,revision,sha) or not record["active"] or digest(_document(record))!=doc_sha:
                        raise MemoryRejected("transformer result source changed")
                    results.append(record|{"cosine":round(max(-1.0,min(1.0,score)),7),
                                           "encoder_identity":spec.identity})
                status=self.status()
            encoder.assert_stable()
        return {"schema":SCHEMA,"records":results,"enabled":True,
                "encoder_identity":spec.identity,"model_digest":self.memory.scope[0],
                "tokenizer_digest":self.memory.scope[1],"query_sha256":digest(query),
                "eligible_vectors":eligible,"scanned_vectors":min(len(rows),MAX_CANDIDATES),
                "exhaustive_vector_scan":exact,"candidate_method":"exact-cosine" if exact else "multiprobe-lsh-then-cosine",
                "candidate_limit_reached":not exact or len(rows)>MAX_CANDIDATES,
                "active_memories":status["active_memories"],"indexed_active_memories":status["indexed_active_memories"],
                "index_complete_snapshot":status["index_complete_snapshot"],
                "remote_calls":False,"semantic_quality_certified":False}
