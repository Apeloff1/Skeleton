"""Local user-supplied audiovisual custody, explicitly distinct from web grants.

No remote downloader, executable HTML, DRM bypass, transcoder or implicit
training rights. Chunked immutable storage; active owner retention permits
playback, not source truth. The source locator is descriptive provenance.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from core.dragon_game_corpus import GameCorpus,_id,digest
from core.dragon_hoarder_bulk import owner_key,StorageHeld
from core.dragon_hoarder_manifests import BLOCK,MAX_DOCUMENT
from core.dragon_hoarder_copy import _archive
from core.dragon_corpus_runtime import _path

MIME={"video/mp4","video/webm","audio/mpeg","audio/ogg","audio/wav","image/png","image/jpeg","image/webp"}
MAX_GRANT=30*86400
MAX_MEDIA_PER_SOURCE=10000
SCHEMA="""
CREATE TABLE IF NOT EXISTS media_objects(
 owner TEXT NOT NULL,id TEXT NOT NULL,game TEXT NOT NULL,source TEXT NOT NULL,
 observation_digest TEXT NOT NULL,scope_json TEXT NOT NULL,operation TEXT NOT NULL,
 mime TEXT NOT NULL,total_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,
 manifest TEXT,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('building','sealed','revoked','erased')),
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS media_source ON media_objects(owner,game,source,id);
CREATE INDEX IF NOT EXISTS media_expiry ON media_objects(state,expires_at,owner,id);
"""


def _signature(mime,head):
    if mime=="video/mp4":return len(head)>=12 and head[4:8]==b"ftyp"
    if mime=="video/webm":return head.startswith(b"\x1a\x45\xdf\xa3")
    if mime=="audio/mpeg":return head.startswith(b"ID3") or len(head)>2 and head[0]==255 and head[1]&224==224
    if mime=="audio/ogg":return head.startswith(b"OggS")
    if mime=="audio/wav":return len(head)>=12 and head[:4]==b"RIFF" and head[8:12]==b"WAVE"
    if mime=="image/png":return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime=="image/jpeg":return head.startswith(b"\xff\xd8\xff")
    if mime=="image/webp":return len(head)>=12 and head[:4]==b"RIFF" and head[8:12]==b"WEBP"
    return False


class MediaArchive:
    def __init__(self,path=None,store=None):
        self.corpus=GameCorpus(path or _path())
        self.store=store or _archive()

    def _db(self):
        return self.corpus._db()

    @staticmethod
    def _logical(mid):
        return "dragon-local-media:"+mid

    def _row(self,db,scope,mid,states=("building","sealed"),*,live=True):
        row=db.execute("SELECT * FROM media_objects WHERE owner=? AND id=?",(owner_key(scope),_id(mid))).fetchone()
        if row is None or row["state"] not in states or live and row["expires_at"]<=int(time.time()):
            raise LookupError("media unavailable")
        if json.loads(row["scope_json"])!=scope:
            raise StorageHeld("media scope witness")
        return row

    @staticmethod
    def _public(row):
        return {"media_id":row["id"],"game_id":row["game"],"source_id":row["source"],
                "mime":row["mime"],"total_bytes":row["total_bytes"],"sha256":row["sha256"],
                "state":row["state"],"created_at":row["created_at"],"expires_at":row["expires_at"],
                "local_user_supplied":True,"source_verified":False,"training_allowed":False}

    def begin(self,scope,*,game,source,observation_digest,operation,mime,total_bytes,sha256,
              rights_acknowledged,grant_seconds):
        if rights_acknowledged is not True or mime not in MIME or type(total_bytes) is not int or not 1<=total_bytes<=MAX_DOCUMENT:
            raise ValueError("media bounds or rights")
        if type(grant_seconds) is not int or not 300<=grant_seconds<=MAX_GRANT:
            raise ValueError("media grant duration")
        if not isinstance(operation,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",operation):
            raise ValueError("operation")
        game,source,observation_digest,sha256=map(_id,(game,source,observation_digest,sha256))
        self.corpus.capture_plan(scope,game,source,observation_digest)
        owner=owner_key(scope)
        mid=digest([owner,game,source,operation])
        now=int(time.time())
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            try:
                old=db.execute("SELECT * FROM media_objects WHERE owner=? AND id=?",(owner,mid)).fetchone()
                if old:
                    if (old["observation_digest"],old["mime"],old["total_bytes"],old["sha256"])!=(observation_digest,mime,total_bytes,sha256):
                        raise StorageHeld("media operation collision")
                    if old["state"] not in {"building","sealed"} or old["expires_at"]<=now:
                        raise StorageHeld("media intent expired or revoked")
                else:
                    count=db.execute("SELECT COUNT(*) FROM media_objects WHERE owner=? AND game=? AND source=?",(owner,game,source)).fetchone()[0]
                    if count>=MAX_MEDIA_PER_SOURCE:raise StorageHeld("media source quota")
                    db.execute("""INSERT INTO media_objects VALUES(?,?,?,?,?,?,?,?,?,?,NULL,?,?,'building')""",
                        (owner,mid,game,source,observation_digest,json.dumps(scope,sort_keys=True),operation,mime,total_bytes,sha256,now,now+grant_seconds))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        # Persist intent before cross-store write. Revocation creates an exact
        # manifest tombstone even if no payload was ever published.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._row(db,scope,mid)
                receipt=self.store.begin(scope,logical_key=self._logical(mid),operation=operation,
                    expected_hash=sha256,expected_bytes=total_bytes)
                if receipt["state"]=="aborted":
                    raise StorageHeld("manifest withdrawn")
                db.execute("UPDATE media_objects SET manifest=? WHERE owner=? AND id=?",
                    (receipt["manifest"],owner,mid))
                db.execute("COMMIT")
                return {**self._public(row),"chunk_bytes":BLOCK}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def append(self,scope,mid,ordinal,raw):
        if type(ordinal) is not int or not 0<=ordinal<512 or not isinstance(raw,bytes) or not 1<=len(raw)<=BLOCK:
            raise ValueError("media block bounds")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._row(db,scope,mid,("building",))
                if not row["manifest"]:raise StorageHeld("resume media intent")
                if ordinal==0 and not _signature(row["mime"],raw[:64]):raise ValueError("media signature")
                receipt=self.store.append(scope,row["manifest"],ordinal,raw)
                db.execute("COMMIT")
                return {"media_id":mid,"ordinal":ordinal,"sha256":receipt["digest"],"stored":True}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def seal(self,scope,mid):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._row(db,scope,mid)
                if not row["manifest"]:raise StorageHeld("resume media intent")
                witness=self.store.seal(scope,row["manifest"])
                if witness["sha256"]!=row["sha256"] or witness["bytes"]!=row["total_bytes"]:
                    raise StorageHeld("media hash mismatch")
                # Recheck magic on verified bytes; file magic is not full codec
                # qualification. Playback uses an isolated native/browser decoder.
                if not _signature(row["mime"],self.store.read_chunk(scope,row["manifest"],0)[:64]):
                    raise StorageHeld("media signature")
                if row["expires_at"]<=time.time():raise StorageHeld("media grant expired")
                db.execute("UPDATE media_objects SET state='sealed' WHERE owner=? AND id=?",(row["owner"],mid))
                db.execute("COMMIT")
                return {**self._public(row),"state":"sealed","codec_verified":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def list(self,scope,game,source,*,after=None,limit=32):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("page")
        with self._db() as db:
            db.executescript(SCHEMA)
            rows=db.execute("""SELECT * FROM media_objects WHERE owner=? AND game=? AND source=?
                AND state IN ('building','sealed') AND expires_at>? AND id>? ORDER BY id LIMIT ?""",
                (owner_key(scope),_id(game),_id(source),int(time.time()),_id(after) if after else "",limit+1)).fetchall()
        return {"media":[self._public(x) for x in rows[:limit]],"next_cursor":rows[limit-1]["id"] if len(rows)>limit else None}

    def metadata(self,scope,mid):
        with self._db() as db:
            db.executescript(SCHEMA)
            return self._public(self._row(db,scope,mid,("sealed",)))

    def part(self,scope,mid,ordinal):
        with self._db() as db:
            row=self._row(db,scope,mid,("sealed",))
            raw=self.store.read_chunk(scope,row["manifest"],ordinal)
            # Read again under owner scope after cross-store I/O.
            self._row(db,scope,mid,("sealed",))
            return raw

    def revoke(self,scope,mid):
        with self._db() as db:
            db.executescript(SCHEMA)
            row=db.execute("UPDATE media_objects SET state='revoked',expires_at=0 WHERE owner=? AND id=? AND state IN ('building','sealed')",
                           (owner_key(scope),_id(mid)))
        return {"revoked":row.rowcount==1,"secure_erasure":False}

    def cleanup(self,limit=4):
        with self._db() as db:
            db.executescript(SCHEMA)
            rows=db.execute("""SELECT * FROM media_objects WHERE state IN ('building','sealed','revoked')
                AND (expires_at<=? OR state='revoked') ORDER BY expires_at,owner,id LIMIT ?""",
                (int(time.time()),limit)).fetchall()
        count=0
        for row in rows:
            scope=json.loads(row["scope_json"])
            if owner_key(scope)!=row["owner"]:continue
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    current=self._row(db,scope,row["id"],("building","sealed","revoked"),live=False)
                    if current["state"]!="revoked" and current["expires_at"]>time.time():
                        db.execute("ROLLBACK");continue
                    manifest=self.store.abort_intent(scope,logical_key=self._logical(row["id"]),operation=row["operation"],
                        expected_hash=row["sha256"],expected_bytes=row["total_bytes"])
                    result=self.store.collect_manifest(scope,manifest,limit=32)
                    if not result["remaining"]:
                        db.execute("UPDATE media_objects SET state='erased' WHERE owner=? AND id=?",(row["owner"],row["id"]))
                        count+=1
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:db.execute("ROLLBACK")
                    raise
        return {"removed":count,"logical_erasure_only":True}


def byte_range(header,total):
    if header is None:return 0,total-1,False
    match=re.fullmatch(r"bytes=(\d*)-(\d*)",header)
    if not match or not any(match.groups()):raise ValueError("single byte range required")
    a,b=match.groups()
    if not a:
        if len(b)>12 or int(b)<=0:raise ValueError("invalid suffix")
        start=max(0,total-int(b));end=total-1
    else:
        if len(a)>12 or len(b)>12:raise ValueError("range bounds")
        start=int(a);end=min(total-1,int(b)) if b else total-1
    if not 0<=start<=end<total:raise ValueError("unsatisfiable range")
    return start,end,True
