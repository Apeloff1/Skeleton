"""Durable, bounded release-import queue with restart-safe metadata ingestion.

Only catalogue observations are processed. This queue never grants capture or
network permission, schedules model training, or makes Wiki facts. Canonical
crawl dispatch is a separate, explicit operation.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from core.dragon_game_corpus import GameCorpus, CatalogueHeld, digest
from core.dragon_hoarder_bulk import owner_key
from core.dragon_release_discovery import parse_manifest,parse_steam_catalogue,parse_release_feed

MAX_PENDING=2_000_000
MAX_ROWS_PER_IMPORT=4000
MAX_ATTEMPTS=5
LEASE_SECONDS=90
SCHEMA="""
CREATE TABLE IF NOT EXISTS release_queue_counts(owner TEXT PRIMARY KEY,total INTEGER NOT NULL CHECK(total>=0)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS release_imports(
 owner TEXT NOT NULL, id TEXT NOT NULL, input_digest TEXT NOT NULL,
 created_at INTEGER NOT NULL, total INTEGER NOT NULL,
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS release_jobs(
 owner TEXT NOT NULL, id TEXT NOT NULL, batch TEXT NOT NULL,
 scope_json TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','leased','done','held')),
 due INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 claim TEXT, lease_until INTEGER NOT NULL DEFAULT 0, reason TEXT,
 PRIMARY KEY(owner,id), FOREIGN KEY(owner,batch) REFERENCES release_imports(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS release_jobs_ready ON release_jobs(state,due,owner,id);
CREATE INDEX IF NOT EXISTS release_jobs_lease ON release_jobs(state,lease_until,owner,id);
CREATE INDEX IF NOT EXISTS release_jobs_batch ON release_jobs(owner,batch,state,id);
"""


class ReleaseQueue:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.corpus=GameCorpus(path)

    @contextmanager
    def _db(self):
        with self.corpus._db() as db:
            db.executescript(SCHEMA)
            yield db

    def enqueue(self,scope,*,raw,adapter,operation,provider=None,external_id=None,title=None):
        owner=owner_key(scope)
        if not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation:
            raise ValueError("operation key")
        if adapter=="manifest":
            if any(x is not None for x in (provider,external_id,title)):
                raise ValueError("unexpected manifest options")
            proposals=parse_manifest(raw)
        elif adapter=="steam":
            if any(x is not None for x in (provider,external_id,title)):
                raise ValueError("unexpected Steam options")
            proposals=parse_steam_catalogue(raw)
        elif adapter=="rss_atom":
            proposals=parse_release_feed(raw,provider=provider,external_id=external_id,title=title)
        else:
            raise ValueError("unknown adapter")
        if not 1<=len(proposals)<=MAX_ROWS_PER_IMPORT:
            raise ValueError("empty or excessive import")
        batch=digest([owner,operation])
        input_digest=digest([adapter,hashlib.sha256(raw).hexdigest(),provider,external_id,title])
        items={p.event_key:p.observation() for p in proposals}
        now=int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                prior=db.execute("SELECT input_digest,total FROM release_imports WHERE owner=? AND id=?",
                                 (owner,batch)).fetchone()
                if prior:
                    if prior["input_digest"]!=input_digest:
                        raise CatalogueHeld("import operation conflict")
                    db.execute("COMMIT")
                    return {"batch_id":batch,"total":prior["total"],"replayed":True,"network_executed":False}
                # Bound total retained jobs, not just pending rows. Compact
                # completed jobs only after an explicit retention design.
                counted=db.execute("SELECT total FROM release_queue_counts WHERE owner=?",(owner,)).fetchone()
                if counted is None:
                    count=db.execute("SELECT COUNT(*) FROM release_jobs WHERE owner=?",(owner,)).fetchone()[0]
                    db.execute("INSERT INTO release_queue_counts VALUES(?,?)",(owner,count))
                else:count=counted["total"]
                if count+len(items)>MAX_PENDING:
                    raise CatalogueHeld("release queue storage cap")
                db.execute("INSERT INTO release_imports VALUES(?,?,?,?,?)",(owner,batch,input_digest,now,len(items)))
                db.executemany("""INSERT INTO release_jobs(owner,id,batch,scope_json,payload,state,due)
                    VALUES(?,?,?,?,?,'queued',?)""",
                    [(owner,digest([batch,k]),batch,json.dumps(scope,sort_keys=True),
                      json.dumps(p,ensure_ascii=False,sort_keys=True),now) for k,p in items.items()])
                db.execute("UPDATE release_queue_counts SET total=total+? WHERE owner=?",(len(items),owner))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction: db.execute("ROLLBACK")
                raise
        return {"batch_id":batch,"total":len(items),"replayed":False,"network_executed":False}

    def status(self,scope,batch):
        from core.dragon_game_corpus import _id
        owner=owner_key(scope)
        batch=_id(batch)
        with self._db() as db:
            meta=db.execute("SELECT total,created_at FROM release_imports WHERE owner=? AND id=?",(owner,batch)).fetchone()
            if not meta:
                raise LookupError("import missing")
            rows=db.execute("SELECT state,COUNT(*) AS n FROM release_jobs WHERE owner=? AND batch=? GROUP BY state",
                            (owner,batch)).fetchall()
        counts={s:0 for s in ("queued","leased","done","held")}
        counts.update({row["state"]:row["n"] for row in rows})
        return {"batch_id":batch,"total":meta["total"],"created_at":meta["created_at"],
                "counts":counts,"network_executed":False,"wiki_approved":False}

    def _claim(self):
        now=int(time.time())
        claim=uuid4().hex
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                # Recover a bounded set of expired jobs. A crash after observing
                # but before acknowledgement replays the same event identity.
                expired=db.execute("""SELECT owner,id,attempts FROM release_jobs
                    WHERE state='leased' AND lease_until<=? ORDER BY lease_until,owner,id LIMIT 32""",(now,)).fetchall()
                for x in expired:
                    state="held" if x["attempts"]>=MAX_ATTEMPTS else "queued"
                    db.execute("""UPDATE release_jobs SET state=?,due=?,claim=NULL,lease_until=0,reason='lease_expired'
                        WHERE owner=? AND id=? AND state='leased' AND lease_until<=?""",(state,now,x["owner"],x["id"],now))
                row=db.execute("""SELECT owner,id,scope_json,payload,attempts FROM release_jobs
                    WHERE state='queued' AND due<=? AND attempts<? ORDER BY due,owner,id LIMIT 1""",(now,MAX_ATTEMPTS)).fetchone()
                if row:
                    db.execute("""UPDATE release_jobs SET state='leased',claim=?,lease_until=?,attempts=attempts+1
                        WHERE owner=? AND id=? AND state='queued'""",(claim,now+LEASE_SECONDS,row["owner"],row["id"]))
                db.execute("COMMIT")
                return ({**dict(row),"claim":claim,"attempts":row["attempts"]+1} if row else None)
            except BaseException:
                if db.in_transaction: db.execute("ROLLBACK")
                raise

    def _settle(self,row,reason=None,*,permanent=False):
        now=int(time.time())
        state="done" if reason is None else "held" if permanent or row["attempts"]>=MAX_ATTEMPTS else "queued"
        due=now+min(3600,30*(2**row["attempts"])) if state=="queued" else now
        with self._db() as db:
            change=db.execute("""UPDATE release_jobs SET state=?,due=?,claim=NULL,lease_until=0,reason=?
                WHERE owner=? AND id=? AND state='leased' AND claim=? AND lease_until>?""",
                (state,due,reason,row["owner"],row["id"],row["claim"],now))
        return state if change.rowcount else "superseded"

    def pulse(self,*,limit=8):
        if type(limit) is not int or not 1<=limit<=32:
            raise ValueError("pulse bounds")
        counts={s:0 for s in ("done","queued","held","superseded")}
        for _ in range(limit):
            row=self._claim()
            if row is None:
                break
            try:
                scope=json.loads(row["scope_json"])
                if owner_key(scope)!=row["owner"]:
                    raise ValueError("scope binding")
                payload=json.loads(row["payload"])
                self.corpus.observe(scope,**payload)
            except (ValueError,TypeError,KeyError,CatalogueHeld):
                state=self._settle(row,"catalogue_rejected",permanent=True)
            except (sqlite3.Error,OSError):
                state=self._settle(row,"storage_unavailable")
            else:
                state=self._settle(row)
            counts[state]+=1
        return {**counts,"network_executed":False}
