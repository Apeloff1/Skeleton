"""Opt-in learned word-vector retrieval without network or executable assets.

The encoder consumes an explicitly installed, SHA-pinned JSONL word-vector
artifact (for example, an operator-converted fastText/GloVe inventory). It
performs actual dense vector pooling and cosine ranking. This is a limited
static embedding encoder, not a transformer sentence encoder or language model.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import time
import unicodedata
from typing import Any, BinaryIO

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.jeeves_approved_memory import (
    ApprovedMemory, MemoryRejected, MemoryConflict, KINDS,
    _stable, _digest, _text,
)

ASSET_SCHEMA = "skeleton.jeeves.word-vector-asset.v1"
INDEX_SCHEMA = "skeleton.jeeves.memory-vector-index.v1"
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ROW_BYTES = 64 * 1024
MAX_VOCAB = 250_000
MAX_DIM = 512
MIN_DIM = 4
MAX_WORDS = 128
MAX_INDEX_PAGE = 128
MAX_SEARCH_CANDIDATES = 4096
MAX_RESULTS = 20
LSH_BANDS = 6
LSH_BITS = 8
LSH_VERSION = "skeleton.jeeves.dense-lsh.v1"
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset("a an and are as at be by can do for from have how i in is it me my of on or so that the this to was we what when where which who will with you your".split())


def _reject_constant(value: str):
    raise MemoryRejected("nonfinite encoder asset value")


def _pairs(rows):
    output = {}
    for key,value in rows:
        if key in output:
            raise MemoryRejected("duplicate JSON asset field")
        output[key] = value
    return output


def _decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8",errors="strict"), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError,ValueError,RecursionError):
        raise MemoryRejected("invalid encoder asset JSON") from None


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC",text).casefold()


def _sha(value: Any) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise MemoryRejected("invalid encoder identity")
    return value


def _vector(values: Any, dimensions: int) -> tuple[float,...]:
    if not isinstance(values,(list,tuple)) or len(values)!=dimensions:
        raise MemoryRejected("invalid word vector dimension")
    if any(type(v) not in (int,float) or abs(v)>1e12 or not math.isfinite(v) for v in values):
        raise MemoryRejected("nonfinite or excessive vector component")
    length=math.sqrt(math.fsum(float(v)*float(v) for v in values))
    if not math.isfinite(length) or length<1e-20:
        raise MemoryRejected("empty word vector")
    return tuple(float(v)/length for v in values)


def _pack(values: tuple[float,...]) -> bytes:
    return struct.pack("<"+"f"*len(values),*values)


def _unpack(raw: Any, dimensions: int) -> tuple[float,...]:
    if type(raw) is not bytes or len(raw)!=4*dimensions:
        raise MemoryRejected("invalid stored dense vector")
    values=struct.unpack("<"+"f"*dimensions,raw)
    length=math.sqrt(math.fsum(v*v for v in values))
    if not math.isfinite(length) or abs(length-1.0)>1e-4:
        raise MemoryRejected("stored vector not finite and normalized")
    return values


def _blob_digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _stable_token(word: Any) -> str:
    if (type(word) is not str or not word or len(word.encode("utf-8"))>128
            or _normalize(word)!=word or not _TOKEN.fullmatch(word)):
        raise MemoryRejected("asset token must be one canonical Unicode word")
    return word


def _read_line(handle: BinaryIO, digest, consumed: int) -> tuple[bytes,int]:
    raw=handle.readline(MAX_ROW_BYTES+1)
    if len(raw)>MAX_ROW_BYTES or consumed+len(raw)>MAX_FILE_BYTES:
        raise MemoryRejected("encoder asset exceeds bounded row or byte budget")
    digest.update(raw)
    return raw,consumed+len(raw)


@lru_cache(maxsize=16)
def _planes(dimensions: int) -> tuple[tuple[int,...],...]:
    """Deterministic ubiquitous signed random projections; no mutable RNG.

    Hash expansion is versioned, independent of Python random implementations.
    Sign projections are independent of the underlying word vector asset.
    """
    planes=[]
    for plane in range(LSH_BANDS*LSH_BITS):
        bits=[]
        block=0
        while len(bits)<dimensions:
            raw=sha256(f"{LSH_VERSION}:{dimensions}:{plane}:{block}".encode("ascii")).digest()
            for byte in raw:
                bits.extend(1 if byte&(1<<bit) else -1 for bit in range(8))
            block+=1
        planes.append(tuple(bits[:dimensions]))
    return tuple(planes)


def _signatures(values: tuple[float,...]) -> tuple[int,...]:
    planes=_planes(len(values))
    signatures=[]
    for band in range(LSH_BANDS):
        value=0
        for bit in range(LSH_BITS):
            projection=math.fsum(a*b for a,b in zip(values,planes[band*LSH_BITS+bit]))
            if projection>=0:
                value|=1<<bit
        signatures.append(value)
    return tuple(signatures)


def _probes(values: tuple[float,...]) -> tuple[tuple[int,int,int],...]:
    """Exact bucket priority 4, one-bit neighbors priority 1."""
    result=[]
    for band,signature in enumerate(_signatures(values)):
        result.append((band,signature,4))
        result.extend((band,signature^(1<<bit),1) for bit in range(LSH_BITS))
    return tuple(result)


class MemoryVectorIndex:
    """Word vectors and derived note vectors in the canonical local DB.

    A bank is immutable by digest; replacing it requires explicit import.
    Cached notes are joined to their exact active memory revision and digest.
    No scan is represented as exhaustive if it reached the candidate cap.
    """

    def __init__(self,memory: ApprovedMemory):
        self.memory=memory
        self.store=memory.store
        with self.store._transaction():
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_encoder_bank (
                model_digest TEXT NOT NULL, tokenizer_digest TEXT NOT NULL,
                asset_sha256 TEXT NOT NULL, model_name TEXT NOT NULL,
                dimensions INTEGER NOT NULL, vocabulary INTEGER NOT NULL,
                PRIMARY KEY(model_digest,tokenizer_digest)
            )""")
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_encoder_words (
                model_digest TEXT NOT NULL, tokenizer_digest TEXT NOT NULL,
                token TEXT NOT NULL, vector BLOB NOT NULL, vector_sha256 TEXT NOT NULL,
                PRIMARY KEY(model_digest,tokenizer_digest,token),
                FOREIGN KEY(model_digest,tokenizer_digest)
                REFERENCES jeeves_encoder_bank(model_digest,tokenizer_digest)
                ON DELETE CASCADE
            ) WITHOUT ROWID""")
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_memory_vectors (
                memory_id TEXT PRIMARY KEY REFERENCES jeeves_approved_memory(memory_id)
                ON DELETE CASCADE,
                asset_sha256 TEXT NOT NULL, memory_revision INTEGER NOT NULL,
                memory_sha256 TEXT NOT NULL, vector BLOB, vector_sha256 TEXT,
                token_count INTEGER NOT NULL, covered_count INTEGER NOT NULL
            )""")
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_memory_vector_buckets (
                memory_id TEXT NOT NULL REFERENCES jeeves_memory_vectors(memory_id)
                    ON DELETE CASCADE,
                asset_sha256 TEXT NOT NULL,
                band INTEGER NOT NULL CHECK(band>=0 AND band<6),
                signature INTEGER NOT NULL CHECK(signature>=0 AND signature<256),
                PRIMARY KEY(memory_id,band)
            ) WITHOUT ROWID""")
            self.store._db.execute("""CREATE INDEX IF NOT EXISTS jeeves_memory_vector_bucket_lookup
                ON jeeves_memory_vector_buckets(asset_sha256,band,signature,memory_id)""")

    def _bank(self) -> dict|None:
        row=self.store._db.execute(
            "SELECT asset_sha256,model_name,dimensions,vocabulary FROM jeeves_encoder_bank "
            "WHERE model_digest=? AND tokenizer_digest=?",self.memory.scope
        ).fetchone()
        if row is None:
            return None
        asset,name,dim,vocab=row
        if (type(dim) is not int or type(vocab) is not int
                or not MIN_DIM<=dim<=MAX_DIM or not 1<=vocab<=MAX_VOCAB
                or type(name) is not str or not name or len(name.encode("utf-8"))>200):
            raise MemoryRejected("stored encoder metadata invalid")
        return {"asset_sha256":_sha(asset),"model_name":name,
                "dimensions":dim,"vocabulary":vocab}

    def status(self) -> dict:
        with self.store.read_snapshot():
            bank=self._bank()
            scope=self.memory.scope
            active=self.store._db.execute(
                "SELECT count(*) FROM jeeves_approved_memory WHERE model_digest=? AND "
                "tokenizer_digest=? AND (expires_at IS NULL OR expires_at>?)",
                (*scope,int(time.time())),
            ).fetchone()[0]
            indexed=0; covered=0
            if bank:
                indexed,covered=self.store._db.execute(
                    "SELECT count(*),COALESCE(sum(v.vector IS NOT NULL),0) "
                    "FROM jeeves_memory_vectors v JOIN jeeves_approved_memory m "
                    "ON m.memory_id=v.memory_id WHERE m.model_digest=? AND m.tokenizer_digest=? "
                    "AND (m.expires_at IS NULL OR m.expires_at>?) "
                    "AND v.asset_sha256=? AND v.memory_revision=m.revision "
                    "AND v.memory_sha256=m.content_sha256 "
                    "AND (v.vector IS NULL OR (SELECT count(*) FROM jeeves_memory_vector_buckets b "
                    "WHERE b.memory_id=v.memory_id AND b.asset_sha256=v.asset_sha256)=?)",
                    (*scope,int(time.time()),bank["asset_sha256"],LSH_BANDS),
                ).fetchone()
            return {"schema":INDEX_SCHEMA,"bank":bank,"active_memories":active,
                    "indexed_active_memories":indexed,"covered_active_memories":covered,
                    "index_complete_snapshot":bank is not None and indexed==active,
                    "model_digest":scope[0],"tokenizer_digest":scope[1],
                    "encoder_kind":"static-learned-word-vector-mean-pooling",
                    "candidate_index":LSH_VERSION,
                    "remote_calls":False,"semantic_quality_certified":False}

    def install(self,path: Path,expected_sha256: str,*,approved: bool,
                expected_prior: str|None=None) -> dict:
        """Explicit CLI-only installation. Never receives paths from HTTP.

        Verify actual raw bytes, exact row count and unchanged regular file.
        All metadata/vectors switch atomically. A failed import keeps the prior
        bank and all previous derived vectors.
        """
        expected_sha256=_sha(expected_sha256)
        if approved is not True:
            raise MemoryRejected("explicit encoder install approval required")
        if expected_prior is not None:
            _sha(expected_prior)
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=MAX_FILE_BYTES:
            raise MemoryRejected("encoder asset must be a bounded regular file")
        fd=os.open(path,os.O_RDONLY| get_flag("O_NOFOLLOW") |get_flag("O_NONBLOCK")|get_flag("O_BINARY"))
        with os.fdopen(fd,"rb") as handle:
            opened=os.fstat(handle.fileno())
            source_identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if not stat.S_ISREG(opened.st_mode) or source_identity(opened)!=source_identity(before):
                raise MemoryRejected("encoder asset path changed")
            digest=sha256()
            line,consumed=_read_line(handle,digest,0)
            header=_decode_json(line)
            if (type(header) is not dict or set(header)!={"schema","model_name","dimensions","vocabulary"}
                    or header["schema"]!=ASSET_SCHEMA):
                raise MemoryRejected("invalid encoder header")
            dimensions,vocabulary=header["dimensions"],header["vocabulary"]
            name=_text(header["model_name"],200).strip()
            if (type(dimensions) is not int or not MIN_DIM<=dimensions<=MAX_DIM
                    or type(vocabulary) is not int or not 1<=vocabulary<=MAX_VOCAB):
                raise MemoryRejected("encoder dimensions or vocabulary exceed local budget")
            scope=self.memory.scope
            try:
                with self.store._transaction():
                    prior=self._bank()
                    if (prior["asset_sha256"] if prior else None)!=expected_prior:
                        raise MemoryConflict("encoder bank changed; inspect current identity")
                    self.store._db.execute(
                        "DELETE FROM jeeves_memory_vectors WHERE memory_id IN "
                        "(SELECT memory_id FROM jeeves_approved_memory WHERE "
                        "model_digest=? AND tokenizer_digest=?)",scope)
                    self.store._db.execute(
                        "DELETE FROM jeeves_encoder_bank WHERE model_digest=? AND tokenizer_digest=?",scope)
                    self.store._db.execute("INSERT INTO jeeves_encoder_bank VALUES(?,?,?,?,?,?)",
                        (*scope,expected_sha256,name,dimensions,vocabulary))
                    batch=[]
                    previous=""
                    for _ in range(vocabulary):
                        row,consumed=_read_line(handle,digest,consumed)
                        if not row:
                            raise MemoryRejected("truncated encoder vocabulary")
                        decoded=_decode_json(row)
                        if type(decoded) is not list or len(decoded)!=2:
                            raise MemoryRejected("invalid encoder row")
                        token=_stable_token(decoded[0])
                        if token<=previous:
                            raise MemoryRejected("encoder tokens must be unique and sorted")
                        previous=token
                        blob=_pack(_vector(decoded[1],dimensions))
                        batch.append((*scope,token,blob,_blob_digest(blob)))
                        if len(batch)>=256:
                            self.store._db.executemany(
                                "INSERT INTO jeeves_encoder_words VALUES(?,?,?,?,?)",batch)
                            batch.clear()
                    if batch:
                        self.store._db.executemany("INSERT INTO jeeves_encoder_words VALUES(?,?,?,?,?)",batch)
                    extra,consumed=_read_line(handle,digest,consumed)
                    after=os.fstat(handle.fileno()); final=path.lstat()
                    if (extra or consumed!=before.st_size or source_identity(after)!=source_identity(before)
                            or source_identity(final)!=source_identity(before) or digest.hexdigest()!=expected_sha256):
                        raise MemoryRejected("encoder asset digest, size or path custody mismatch")
            except sqlite3.IntegrityError:
                raise MemoryRejected("encoder inventory rejected atomically") from None
        return self.status()

    def uninstall(self,expected_sha256: str,*,approved: bool) -> dict:
        if approved is not True:
            raise MemoryRejected("explicit encoder removal approval required")
        _sha(expected_sha256)
        with self.store._transaction():
            bank=self._bank()
            if bank is None or bank["asset_sha256"]!=expected_sha256:
                raise MemoryConflict("encoder bank changed")
            scope=self.memory.scope
            self.store._db.execute(
                "DELETE FROM jeeves_memory_vectors WHERE memory_id IN (SELECT memory_id "
                "FROM jeeves_approved_memory WHERE model_digest=? AND tokenizer_digest=?)",scope)
            self.store._db.execute("DELETE FROM jeeves_encoder_bank WHERE model_digest=? AND tokenizer_digest=?",scope)
        return self.status()

    def _encode(self,text: str,bank: dict) -> tuple[bytes|None,int,int]:
        terms=Counter(w for w in _TOKEN.findall(_normalize(text))[:MAX_WORDS]
                      if w not in _STOP and len(w)>1 and len(w.encode("utf-8"))<=128)
        if not terms:
            return None,0,0
        dims=bank["dimensions"]
        qmarks=",".join("?" for _ in terms)
        rows=self.store._db.execute(
            "SELECT token,vector,vector_sha256 FROM jeeves_encoder_words WHERE model_digest=? "
            "AND tokenizer_digest=? AND token IN ("+qmarks+")",(*self.memory.scope,*terms),
        ).fetchall()
        if not rows:
            return None,sum(terms.values()),0
        accumulator=[0.0]*dims
        covered=0
        for word,raw,digest in sorted(rows,key=lambda r:r[0]):
            if _blob_digest(raw)!=digest:
                raise MemoryRejected("word vector integrity mismatch")
            vector=_unpack(raw,dims)
            count=terms[word]
            weight=1.0+math.log(count)
            covered+=count
            for i,value in enumerate(vector):
                accumulator[i]+=weight*value
        length=math.sqrt(math.fsum(x*x for x in accumulator))
        if length<1e-20:
            return None,sum(terms.values()),covered
        return _pack(tuple(x/length for x in accumulator)),sum(terms.values()),covered

    def refresh(self,*,cursor: str|None=None,limit: int=64,approved: bool,
                expected_asset: str) -> dict:
        """Process one keyset page, atomically pin every record and encoder."""
        if approved is not True or type(limit) is not int or not 1<=limit<=MAX_INDEX_PAGE:
            raise MemoryRejected("explicit bounded vector index refresh required")
        _sha(expected_asset)
        if cursor is not None and (type(cursor) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",cursor)):
            raise MemoryRejected("invalid vector-index cursor")
        with self.store._transaction():
            bank=self._bank()
            if bank is None or bank["asset_sha256"]!=expected_asset:
                raise MemoryConflict("encoder bank changed")
            now=int(time.time())
            rows=self.store._db.execute(
                "SELECT memory_id FROM jeeves_approved_memory m WHERE model_digest=? "
                "AND tokenizer_digest=? AND memory_id>? AND (expires_at IS NULL OR expires_at>?) "
                "ORDER BY memory_id LIMIT ?",(*self.memory.scope,cursor or "",now,limit+1)
            ).fetchall()
            embedded=0
            for (mid,) in rows[:limit]:
                record=self.memory._find(mid,now=now)
                raw,tokens,covered=self._encode(record["label"]+" "+record["text"]+" "+" ".join(record["tags"]),bank)
                self.store._db.execute(
                    "INSERT INTO jeeves_memory_vectors VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(memory_id) DO UPDATE SET asset_sha256=excluded.asset_sha256,"
                    "memory_revision=excluded.memory_revision,memory_sha256=excluded.memory_sha256,"
                    "vector=excluded.vector,vector_sha256=excluded.vector_sha256,"
                    "token_count=excluded.token_count,covered_count=excluded.covered_count",
                    (mid,expected_asset,record["revision"],record["sha256"],raw,
                     _blob_digest(raw) if raw is not None else None,tokens,covered),
                )
                self.store._db.execute(
                    "DELETE FROM jeeves_memory_vector_buckets WHERE memory_id=?",(mid,))
                if raw is not None:
                    self.store._db.executemany(
                        "INSERT INTO jeeves_memory_vector_buckets VALUES(?,?,?,?)",
                        [(mid,expected_asset,band,signature) for band,signature in
                         enumerate(_signatures(_unpack(raw,bank["dimensions"])))],
                    )
                embedded+=raw is not None
            return {"asset_sha256":expected_asset,"processed":min(len(rows),limit),
                    "embedded":embedded,"next_cursor":rows[limit-1][0] if len(rows)>limit else None,
                    "snapshot_time":now,"index_complete_not_certified":True}

    def search(self,query: str,*,limit: int=8,kinds: list[str]|None=None) -> dict:
        query=_text(query,1024)
        if type(limit) is not int or not 1<=limit<=MAX_RESULTS:
            raise MemoryRejected("invalid dense retrieval limit")
        if kinds is not None and (type(kinds) is not list or not kinds or
                any(type(k) is not str or k not in KINDS for k in kinds) or
                len(set(kinds))!=len(kinds)):
            raise MemoryRejected("invalid dense memory category filter")
        now=int(time.time())
        with self.store.read_snapshot():
            bank=self._bank()
            if bank is None:
                return {"records":[],"enabled":False,"candidate_limit_reached":False,
                        "semantic_quality_certified":False}
            raw,words,covered=self._encode(query,bank)
            if raw is None:
                return {"records":[],"enabled":True,"asset_sha256":bank["asset_sha256"],
                        "word_count":words,"covered_words":covered,
                        "candidate_limit_reached":False,"semantic_quality_certified":False}
            query_vec=_unpack(raw,bank["dimensions"])
            where="" if kinds is None else " AND m.kind IN ("+",".join("?" for _ in kinds)+")"
            base_where=(
                "m.model_digest=? AND m.tokenizer_digest=? "
                "AND (m.expires_at IS NULL OR m.expires_at>?) AND v.asset_sha256=? "
                "AND v.memory_revision=m.revision AND v.memory_sha256=m.content_sha256 "
                "AND v.vector IS NOT NULL"+where+
                " AND (SELECT count(*) FROM jeeves_memory_vector_buckets z "
                "WHERE z.memory_id=v.memory_id AND z.asset_sha256=v.asset_sha256)=?"
            )
            params=(*self.memory.scope,now,bank["asset_sha256"],*(kinds or []),LSH_BANDS)
            eligible=self.store._db.execute(
                "SELECT count(*) FROM jeeves_memory_vectors v JOIN jeeves_approved_memory m "
                "ON m.memory_id=v.memory_id WHERE "+base_where,params,
            ).fetchone()[0]
            exact=eligible<=MAX_SEARCH_CANDIDATES
            if exact:
                rows=self.store._db.execute(
                    "SELECT v.memory_id,v.vector,v.vector_sha256,v.token_count,v.covered_count "
                    "FROM jeeves_memory_vectors v JOIN jeeves_approved_memory m ON m.memory_id=v.memory_id "
                    "WHERE "+base_where+" ORDER BY v.memory_id LIMIT ?",
                    (*params,MAX_SEARCH_CANDIDATES+1),
                ).fetchall()
            else:
                probes=_probes(query_vec)
                marks=",".join("(?,?,?)" for _ in probes)
                # A multiprobe LSH candidate stage scales beyond arbitrary
                # first-ID scanning; true cosine is still used on all finalists.
                rows=self.store._db.execute(
                    "WITH probes(band,signature,weight) AS (VALUES "+marks+"), "
                    "candidates AS (SELECT v.memory_id,SUM(p.weight) AS priority "
                    "FROM probes p JOIN jeeves_memory_vector_buckets b "
                    "ON b.band=p.band AND b.signature=p.signature "
                    "JOIN jeeves_memory_vectors v ON v.memory_id=b.memory_id "
                    "JOIN jeeves_approved_memory m ON m.memory_id=v.memory_id "
                    "WHERE b.asset_sha256=v.asset_sha256 AND "+base_where+
                    " GROUP BY v.memory_id ORDER BY priority DESC,v.memory_id LIMIT ?) "
                    "SELECT v.memory_id,v.vector,v.vector_sha256,v.token_count,v.covered_count "
                    "FROM candidates c JOIN jeeves_memory_vectors v ON v.memory_id=c.memory_id "
                    "ORDER BY c.priority DESC,v.memory_id",
                    (*(x for probe in probes for x in probe),*params,MAX_SEARCH_CANDIDATES+1),
                ).fetchall()
            scored=[]
            for mid,blob,digest,tokens,count in rows[:MAX_SEARCH_CANDIDATES]:
                if (_blob_digest(blob)!=digest or type(tokens) is not int or type(count) is not int
                        or not 0<count<=tokens<=MAX_WORDS):
                    raise MemoryRejected("cached vector custody mismatch")
                values=_unpack(blob,bank["dimensions"])
                bucket_rows=self.store._db.execute(
                    "SELECT band,signature FROM jeeves_memory_vector_buckets WHERE memory_id=? "
                    "AND asset_sha256=? ORDER BY band",(mid,bank["asset_sha256"]),
                ).fetchall()
                if bucket_rows!=list(enumerate(_signatures(values))):
                    raise MemoryRejected("derived vector bucket integrity mismatch")
                cosine=math.fsum(a*b for a,b in zip(query_vec,values))
                if cosine>=0.30:
                    scored.append((cosine,mid,count,tokens))
            scored.sort(key=lambda row:(-row[0],row[1]))
            records=[]
            for cosine,mid,count,tokens in scored[:limit]:
                record=self.memory._find(mid,now=now)
                # Verify selected winners against exact currently pinned note
                # and word values, not merely a mutable cached vector digest.
                expected,t,c=self._encode(record["label"]+" "+record["text"]+" "+" ".join(record["tags"]),bank)
                cached=self.store._db.execute(
                    "SELECT vector FROM jeeves_memory_vectors WHERE memory_id=?",(mid,)
                ).fetchone()
                if cached is None or expected!=cached[0] or t!=tokens or c!=count:
                    raise MemoryRejected("derived note vector differs from current encoder and source")
                records.append(record|{"cosine":round(cosine,7),"encoder_word_coverage":count/tokens})
            status=self.status()
            return {"records":records,"enabled":True,"asset_sha256":bank["asset_sha256"],
                    "word_count":words,"covered_words":covered,
                    "candidate_limit_reached":not exact or len(rows)>MAX_SEARCH_CANDIDATES,
                    "eligible_vectors":eligible,"scanned_vectors":min(len(rows),MAX_SEARCH_CANDIDATES),
                    "exhaustive_vector_scan":exact,"candidate_method":"exact-cosine" if exact else "multiprobe-lsh-then-cosine",
                    "indexed_active_memories":status["indexed_active_memories"],
                    "active_memories":status["active_memories"],
                    "index_complete_snapshot":status["index_complete_snapshot"],
                    "semantic_quality_certified":False}


def get_flag(name: str) -> int:
    return getattr(os,name,0)
