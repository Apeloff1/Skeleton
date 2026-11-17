"""Immutable, disk-backed Dragon source catalogue for large reviewed exports.

This is derived candidate metadata, not new acquisition or retention authority.
Build offline, install an exact manifest and database together, and pin the
manifest in the canonical crawler implementation identity. No network client.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from urllib.parse import urlsplit

from .navigation_semantics import digest, words, concepts
from .source_navigation import (
    Catalogue, FAMILIES, REGISTRY_PATH, SCHEMA, MAX_BYTES, source_record, _root,
)
from .source_catalogue_bulk import _row, _unique_pairs, _publish_new

BASELINE = 3894
TARGET = BASELINE * 100
MAX_SOURCES = 1_048_576
MAX_DATABASE_BYTES = 8 * 1024**3
MAX_EXPORT_BYTES = 512 * 1024**2
MAX_EXPORTS = 128
MAX_LINE_BYTES = 4096
MAX_MANIFEST_BYTES = 128 * 1024
MAX_SEED_SCAN = 8192
MAX_LANE = 128
MAX_TERMS = 48
MAX_REPRESENTATIVES = 128
MAX_PRIOR = 512
INDEX_SCHEMA = "skeleton.dragon.indexed-source-catalogue.v1"
HEX = re.compile(r"[a-f0-9]{64}\Z")
DB_NAME = "dragon_source_catalogue.sqlite3"
DDL = """
CREATE TABLE sources(
    seq INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE, host TEXT NOT NULL, path TEXT NOT NULL,
    match_path TEXT NOT NULL, family TEXT NOT NULL, seed INTEGER NOT NULL,
    raw TEXT NOT NULL, UNIQUE(host,match_path)
);
CREATE TABLE postings(
    token TEXT NOT NULL, tier INTEGER NOT NULL, seq INTEGER NOT NULL,
    PRIMARY KEY(token,tier,seq)
) WITHOUT ROWID;
CREATE TABLE witnesses(
    seq INTEGER NOT NULL, export_number INTEGER NOT NULL, line INTEGER NOT NULL,
    PRIMARY KEY(seq,export_number,line)
) WITHOUT ROWID;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
"""


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _hex(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError("source digest pin")
    return value


def _signature(path):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("index must be a regular standalone file")
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _hash_file(path, maximum):
    before = _signature(path)
    if not 0 < before[2] <= maximum:
        raise ValueError("source index file size bound")
    h = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            h.update(chunk)
    if before != _signature(path):
        raise ValueError("source index changed while hashing")
    return h.hexdigest(), before


def manifest_bytes(path):
    before = _signature(path)
    if not 0 < before[2] <= MAX_MANIFEST_BYTES:
        raise ValueError("source index manifest byte bound")
    with path.open("rb") as file:
        raw = file.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES or before != _signature(path):
        raise ValueError("source index manifest changed")
    return raw


def _ensure_clean(path):
    if any(Path(str(path)+suffix).exists() or Path(str(path)+suffix).is_symlink()
           for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("source generation cannot have SQLite sidecars")


def _match_path(host, path):
    if host == "github.com":
        parts = path.split("/")
        if len(parts) >= 3:
            parts[1:3] = [p.casefold() for p in parts[1:3]]
            return "/".join(parts)
    return path


def _metadata(record):
    host, original_path = _root(record["url"])
    _row(record)
    key = _match_path(host, original_path)
    sid = digest(["dragon-source-root", host, original_path])
    identity = set(words(record["name"]+" "+host+" "+original_path))
    terms = set(words(record["tags"])) | identity
    tokens = {("w:"+term, 0 if term in identity else 1) for term in terms}
    tokens.update(("c:"+str(term), 2) for term in concepts(terms))
    return host, original_path, key, sid, sorted(tokens)


def _publisher_export(spec):
    if not isinstance(spec, dict) or set(spec) != {"path", "sha256", "publisher", "rights_reference"}:
        raise ValueError("publisher export specification")
    _hex(spec["sha256"])
    _root(spec["publisher"])
    reference = spec["rights_reference"]
    if (not isinstance(reference, str) or not reference.strip() or len(reference)>512
            or any(ord(c)<32 or ord(c)==127 for c in reference)):
        raise ValueError("publisher metadata-rights reference")
    if not isinstance(spec["path"], str) or not spec["path"]:
        raise ValueError("publisher export file")
    return Path(spec["path"])


def _insert(db, record, *, seed, export_number, line):
    host, path, key, sid, tokens = _metadata(record)
    raw = _canonical(record)
    old = db.execute(
        "SELECT seq,raw FROM sources WHERE host=? AND match_path=?", (host,key)
    ).fetchone()
    if old is not None:
        if old[1] != raw:
            return "conflict", None
        db.execute("INSERT INTO witnesses VALUES(?,?,?)", (old[0],export_number,line))
        return "duplicate", old[0]
    seq = db.execute(
        "INSERT INTO sources(id,host,path,match_path,family,seed,raw) VALUES(?,?,?,?,?,?,?)",
        (sid,host,path,key,record["family"],seed,raw)
    ).lastrowid
    db.executemany("INSERT INTO postings VALUES(?,?,?)",
                   ((t,tier,seq) for t,tier in tokens))
    db.execute("INSERT INTO witnesses VALUES(?,?,?)", (seq,export_number,line))
    return "added", seq


def _ingest(db, export, number, count, conflicts):
    path = _publisher_export(export)
    before = _signature(path)
    if not 0 < before[2] <= MAX_EXPORT_BYTES:
        raise ValueError("publisher export byte bound")
    h = hashlib.sha256()
    seen_bytes = 0
    counters = Counter()
    with path.open("rb") as file:
        line_no = 0
        while True:
            line = file.readline(MAX_LINE_BYTES+1)
            if not line:
                break
            line_no += 1
            seen_bytes += len(line)
            h.update(line)
            if (len(line)>MAX_LINE_BYTES or seen_bytes>MAX_EXPORT_BYTES
                    or line_no>MAX_SOURCES*2):
                raise ValueError("publisher export line bound")
            if not line.strip():
                continue
            status, _ = _insert(db,_json(line),seed=0,export_number=number,line=line_no)
            counters[status] += 1
            if status == "conflict":
                conflicts += 1
            if status == "added":
                count += 1
                if count > MAX_SOURCES:
                    raise ValueError("indexed source capacity exceeded")
    if h.hexdigest() != export["sha256"] or before != _signature(path):
        raise ValueError("publisher export digest mismatch")
    if not counters:
        raise ValueError("empty publisher export")
    receipt = {"publisher": export["publisher"], "sha256": export["sha256"],
               "rights_reference": export["rights_reference"],
               "bytes": seen_bytes, "rows": sum(counters.values()),
               **{key: counters[key] for key in ("added","duplicate","conflict")}}
    return count, conflicts, receipt


def build_index(base_path, exports, output_dir, *, base_sha256, minimum=TARGET):
    """Build a single immutable generation from explicit reviewed locator rows.

    No inferred titles/URLs, live fetcher or crawl authorization. Conflicting
    metadata stays held, and first accepted data (especially curated roots)
    wins. Export provenance persists as byte digest and exact line witness.
    """
    if type(minimum) is not int or not 1 <= minimum <= MAX_SOURCES:
        raise ValueError("source generation count bound")
    if not isinstance(exports, list) or not 1 <= len(exports) <= MAX_EXPORTS:
        raise ValueError("publisher export count bound")
    _hex(base_sha256)
    base_path = Path(base_path)
    actual, signature = _hash_file(base_path, MAX_BYTES)
    if actual != base_sha256:
        raise ValueError("base catalogue digest mismatch")
    raw = base_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=actual or _signature(base_path)!=signature:
        raise ValueError("base catalogue changed")
    base = Catalogue(raw)
    seed_rows = _json(raw)["sources"]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=False, exist_ok=True)
    db_path = output_dir / DB_NAME
    manifest_path = output_dir / "dragon_source_catalogue.index.json"
    if db_path.exists() or db_path.is_symlink() or manifest_path.exists() or manifest_path.is_symlink():
        raise FileExistsError("generation output exists")
    fd, staging_name = tempfile.mkstemp(prefix=".dragon-index-",dir=output_dir)
    os.close(fd)
    staging = Path(staging_name)
    receipts = []
    count = conflicts = 0
    try:
        db = sqlite3.connect(staging)
        try:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA cache_size=-32768")
            db.execute("PRAGMA max_page_count=2097152")
            db.execute("PRAGMA trusted_schema=OFF")
            db.executescript(DDL)
            with db:
                for line, record in enumerate(seed_rows, 1):
                    status,_ = _insert(db,record,seed=1,export_number=0,line=line)
                    if status != "added":
                        raise ValueError("canonical seed collision")
                    count += 1
                for index, export in enumerate(exports,1):
                    count,conflicts,receipt = _ingest(db,export,index,count,conflicts)
                    receipts.append(receipt)
                if count < minimum:
                    raise ValueError("minimum populated source count not reached")
                db.execute("CREATE INDEX sources_seed ON sources(seed,seq)")
                db.execute("CREATE INDEX sources_family ON sources(family,seq)")
                db.execute("CREATE INDEX sources_origin ON sources(family,host,seed,seq)")
                db.execute("""CREATE TABLE origin_representatives AS
                    SELECT family,host,COALESCE(MIN(CASE WHEN seed=1 THEN seq END),MIN(seq)) AS seq
                    FROM sources GROUP BY family,host""")
                db.execute("CREATE UNIQUE INDEX origin_reps ON origin_representatives(family,seq)")
                db.execute("CREATE TABLE token_counts AS SELECT token,COUNT(*) AS n FROM postings GROUP BY token")
                db.execute("CREATE UNIQUE INDEX token_count_lookup ON token_counts(token)")
                families = dict(db.execute("SELECT family,COUNT(*) FROM sources GROUP BY family"))
                hosts = db.execute("SELECT COUNT(DISTINCT host) FROM sources").fetchone()[0]
                metadata = {"schema":INDEX_SCHEMA,"sources":count,"hosts":hosts,
                            "families":families,"base_sha256":actual,"base_digest":base.digest,
                            "revision":base.revision,"seed_count":len(seed_rows)}
                db.executemany("INSERT INTO meta VALUES(?,?)",
                               ((k,_canonical(v)) for k,v in metadata.items()))
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("source index integrity failure")
        finally:
            db.close()
        _ensure_clean(staging)
        index_hash, sig = _hash_file(staging,MAX_DATABASE_BYTES)
        with staging.open("rb") as f:
            os.fsync(f.fileno())
        manifest = {
            **metadata, "file":DB_NAME,"file_bytes":sig[2],"file_sha256":index_hash,
            "exports":receipts,"conflicts_held":conflicts,"target":TARGET,
            "target_reached":count>=TARGET,"candidate_only":True,
            "network_authorized":False,"rights_verified":False,"access_verified":False,
        }
        # Manifest last. An orphan database cannot be activated without it.
        os.link(staging,db_path)
        staging.unlink()
        _publish_new(manifest_path,(_canonical(manifest)+"\n").encode("ascii"))
        return manifest
    finally:
        staging.unlink(missing_ok=True)


class _Rows:
    def __init__(self, registry):
        self.registry = registry

    def __len__(self):
        return self.registry.count

    def __iter__(self):
        with self.registry.connection() as db:
            for (raw,) in db.execute("SELECT raw FROM sources ORDER BY seq"):
                yield source_record(_json(raw))


class _Ids:
    def __init__(self, registry):
        self.registry = registry

    def __len__(self):
        return self.registry.count

    def get(self, key, default=None):
        if not isinstance(key,str) or not HEX.fullmatch(key):
            return default
        with self.registry.connection() as db:
            row = db.execute("SELECT raw FROM sources WHERE id=?", (key,)).fetchone()
            if row is None:
                return default
            source = source_record(_json(row[0]))
            if source.id != key:
                raise ValueError("source index identity mismatch")
            return source


class IndexedCatalogue:
    """Read-only reviewed generation; integrity pin before first use.

    Candidate shortlisting is bounded and approximate, unlike exact source
    identity and prefix lookup. File/path changes fail closed; deploy on an
    operator-controlled read-only directory, never an untrusted writable mount.
    """
    def __init__(self, manifest_path, raw=None, *, base_path=REGISTRY_PATH):
        self.manifest_path = Path(manifest_path)
        raw = manifest_bytes(self.manifest_path) if raw is None else raw
        if raw != manifest_bytes(self.manifest_path):
            raise ValueError("source generation manifest drift")
        m = _json(raw)
        if (not isinstance(m,dict) or m.get("schema")!=INDEX_SCHEMA
                or m.get("file")!=DB_NAME or m.get("candidate_only") is not True
                or m.get("network_authorized") is not False
                or m.get("rights_verified") is not False or m.get("access_verified") is not False
                or type(m.get("sources")) is not int or not 1<=m["sources"]<=MAX_SOURCES):
            raise ValueError("source generation manifest schema")
        _hex(m.get("file_sha256"))
        _hex(m.get("base_sha256"))
        if _hash_file(Path(base_path),MAX_BYTES)[0] != m["base_sha256"]:
            raise ValueError("source generation base no longer matches packaged catalogue")
        self.path = self.manifest_path.parent / DB_NAME
        _ensure_clean(self.path)
        actual,self.signature = _hash_file(self.path,MAX_DATABASE_BYTES)
        if actual!=m["file_sha256"] or self.signature[2]!=m["file_bytes"]:
            raise ValueError("source generation database hash mismatch")
        self.manifest_signature = _signature(self.manifest_path)
        if raw != manifest_bytes(self.manifest_path) or self.manifest_signature != _signature(self.manifest_path):
            raise ValueError("source generation manifest changed during verification")
        self.digest = hashlib.sha256(raw).hexdigest()
        self.count = m["sources"]
        self.revision = m["revision"]
        self._summary = {"schema":SCHEMA,"revision":self.revision,
                         "catalogue_digest":self.digest,"sources":self.count,
                         "hosts":m["hosts"], "families":m["families"],
                         "candidate_only":True,"network_authorized":False,
                         "indexed_generation":True}
        with self.connection() as db:
            metadata = {k:_json(v) for k,v in db.execute("SELECT key,value FROM meta")}
            for key in ("schema","sources","hosts","families","base_sha256",
                        "base_digest","revision","seed_count"):
                if metadata.get(key)!=m.get(key):
                    raise ValueError("source generation manifest metadata mismatch")
            if db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]!=self.count:
                raise ValueError("source generation count mismatch")
        self.rows = _Rows(self)
        self.by_id = _Ids(self)

    def assert_unchanged(self):
        _ensure_clean(self.path)
        if (_signature(self.path)!=self.signature
                or _signature(self.manifest_path)!=self.manifest_signature):
            raise ValueError("source generation modified; restart with reviewed generation")

    @contextmanager
    def connection(self):
        self.assert_unchanged()
        db = sqlite3.connect(self.path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA cache_size=-16384")
            yield db
            self.assert_unchanged()
        finally:
            db.close()

    def summary(self):
        self.assert_unchanged()
        return {**self._summary,"families":dict(self._summary["families"])}

    def match(self,url):
        try:
            p = urlsplit(url)
            if p.scheme!="https" or not p.hostname or p.username or p.password or p.port not in (None,443):
                return None
        except ValueError:
            return None
        path = _match_path(p.hostname,p.path.rstrip("/") or "/")
        with self.connection() as db:
            while True:
                r = db.execute("SELECT raw,id FROM sources WHERE host=? AND match_path=?",
                               (p.hostname,path)).fetchone()
                if r is not None:
                    source = source_record(_json(r[0]))
                    if source.id!=r[1]:
                        raise ValueError("source index identity drift")
                    return source
                if path=="/":
                    return None
                path = path.rpartition("/")[0] or "/"

    def candidate_rows(self,task,families,prior):
        """Rare-term lanes, deterministic exploration and origin representatives.

        Seed coverage remains bounded, while a massive same-host repository
        collection cannot monopolize all candidate lanes. No global recall or
        relevance-optimality claim. Search only reads indexed metadata.
        """
        allowed = sorted(FAMILIES if families is None else set(families))
        if not allowed:
            return
        wanted = {"w:"+t for t in task.terms}|{"c:"+str(t) for t in task.concepts}
        for tag in task.ecosystems:
            wanted.update("w:"+t for t in words(tag.replace("-"," ")))
        seen=set()
        with self.connection() as db:
            def emit(rows):
                for seq,sid,family,raw in rows:
                    if seq in seen or sid in prior or family not in allowed:
                        continue
                    seen.add(seq)
                    source = source_record(_json(raw))
                    if source.id!=sid:
                        raise ValueError("source index identity drift")
                    yield source
            yield from emit(db.execute("SELECT seq,id,family,raw FROM sources WHERE seed=1 ORDER BY seq LIMIT ?",
                                       (MAX_SEED_SCAN,)))
            frequencies=[]
            for token in wanted:
                row=db.execute("SELECT n FROM token_counts WHERE token=?",(token,)).fetchone()
                if row:
                    frequencies.append((row[0],token))
            pivot=int(digest(sorted(wanted))[:12],16)%self.count+1
            for _,token in sorted(frequencies)[:MAX_TERMS]:
                # Exact identity matches first, then a deterministic rotating
                # slice of the full lane. Bound each read independently.
                for tier in (0,1,2):
                    for where,params in (("",()),(" AND p.seq>=?",(pivot,))):
                        yield from emit(db.execute(
                            "SELECT s.seq,s.id,s.family,s.raw FROM postings p JOIN sources s ON s.seq=p.seq "
                            "WHERE p.token=? AND p.tier=?"+where+" ORDER BY p.seq LIMIT ?",
                            (token,tier,*params,MAX_LANE//6)))
            for family in allowed:
                for extra,params in ((" AND r.seq>=?",(pivot,)),("",())):
                    yield from emit(db.execute(
                        "SELECT s.seq,s.id,s.family,s.raw FROM origin_representatives r "
                        "JOIN sources s ON s.seq=r.seq WHERE r.family=?"+extra+
                        " ORDER BY r.seq LIMIT ?",(family,*params,MAX_REPRESENTATIVES//2)))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base",type=Path,default=REGISTRY_PATH)
    parser.add_argument("--base-sha256",required=True)
    parser.add_argument("--exports",type=Path,required=True,help="reviewed JSON list of publisher export pins")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--minimum",type=int,default=TARGET)
    args=parser.parse_args(argv)
    exports=_json(manifest_bytes(args.exports))
    print(_canonical(build_index(args.base,exports,args.output_dir,
                                base_sha256=args.base_sha256,minimum=args.minimum)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
