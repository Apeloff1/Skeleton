"""Game corpus catalogue and release/source watch planning.

All assertions are unverified catalogue metadata. A registered source is NOT
authorized to crawl, quote, archive, train, or promote into Wiki. Network work
must go through the existing crawler mandate and source-policy machinery.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from core.dragon_hoarder_bulk import owner_key

from core.dragon_game_taxonomy import KINDS, cadence, priority, public_taxonomy
STAGES = {"announced", "early_access", "released", "updated", "delisted", "unknown"}
KEY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,127}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
MAX_SOURCES = 512
MAX_GAMES = 2_000_000
MAX_REVISIONS = 50_000_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS counters(
 owner TEXT PRIMARY KEY, games INTEGER NOT NULL DEFAULT 0,
 revisions INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS games(
 owner TEXT NOT NULL, id TEXT NOT NULL, namespace TEXT NOT NULL,
 external_id TEXT NOT NULL, title TEXT NOT NULL, stage TEXT NOT NULL,
 updated_at INTEGER NOT NULL, PRIMARY KEY(owner,id),
 UNIQUE(owner,namespace,external_id)
) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS game_search USING fts5(
 owner, game_id UNINDEXED, title, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS aliases(
 owner TEXT NOT NULL, game TEXT NOT NULL, title TEXT NOT NULL,
 PRIMARY KEY(owner,game,title), FOREIGN KEY(owner,game) REFERENCES games(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sources(
 owner TEXT NOT NULL, game TEXT NOT NULL, id TEXT NOT NULL,
 url TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL,
 last_observed INTEGER NOT NULL, next_review INTEGER NOT NULL,
 latest_event TEXT NOT NULL,
 PRIMARY KEY(owner,game,id),
 FOREIGN KEY(owner,game) REFERENCES games(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS source_due ON sources(owner,next_review,game,id);
CREATE TABLE IF NOT EXISTS observations(
 owner TEXT NOT NULL, game TEXT NOT NULL, source TEXT NOT NULL,
 event_key TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL,
 recorded_at INTEGER NOT NULL, PRIMARY KEY(owner,game,source,event_key),
 FOREIGN KEY(owner,game,source) REFERENCES sources(owner,game,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS observation_history
 ON observations(owner,game,recorded_at DESC,source DESC,event_key DESC);
CREATE TABLE IF NOT EXISTS release_facets(
 owner TEXT NOT NULL, game TEXT NOT NULL, source TEXT NOT NULL, event_key TEXT NOT NULL,
 stage TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL, released_on TEXT,
 observed_at INTEGER NOT NULL, version TEXT, priority INTEGER NOT NULL,
 PRIMARY KEY(owner,game,source,event_key),
 FOREIGN KEY(owner,game,source,event_key) REFERENCES observations(owner,game,source,event_key)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS release_event_time ON release_facets(owner,observed_at DESC,game DESC,source DESC,event_key DESC);
CREATE INDEX IF NOT EXISTS release_event_stage ON release_facets(owner,stage,observed_at DESC,game DESC,source DESC,event_key DESC);
CREATE INDEX IF NOT EXISTS release_event_date ON release_facets(owner,released_on,game,source,event_key);
CREATE INDEX IF NOT EXISTS release_event_kind ON release_facets(owner,kind,observed_at DESC,game DESC,source DESC,event_key DESC);
CREATE INDEX IF NOT EXISTS release_event_language ON release_facets(owner,language,observed_at DESC,game DESC,source DESC,event_key DESC);
CREATE TABLE IF NOT EXISTS corpus_migration(
 name TEXT PRIMARY KEY, cursor TEXT, complete INTEGER NOT NULL CHECK(complete IN (0,1))
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS game_source_kind ON sources(owner,kind,game,id);
CREATE INDEX IF NOT EXISTS game_source_language ON sources(owner,language,game,id);
"""


class CatalogueHeld(RuntimeError):
    pass


def clean(value, max_len):
    if not isinstance(value, str):
        raise ValueError("invalid text")
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > max_len or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("invalid text")
    return value


def key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise ValueError("invalid external key")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def source_url(value):
    value = clean(value, 2048)
    if any(c.isspace() for c in value) or "\\" in value:
        raise ValueError("invalid source URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("HTTPS source identifier required")
    if parsed.port not in (None, 443) or parsed.query or parsed.fragment:
        # Avoid persisting URL tokens or signed queries in the candidate catalogue.
        raise ValueError("plain HTTPS source identifier required")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
        raise ValueError("DNS source identifier required")
    return urlunsplit(("https", host, parsed.path or "/", "", ""))


def game_id(namespace, external_id):
    return digest([key(namespace), key(external_id)])


def _id(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError("invalid catalogue identity")
    return value


def _limit(limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("page bounds")
    return limit


class GameCorpus:
    """Durable owner-scoped observations, FTS catalogue and bounded review queue."""

    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(SCHEMA)
            yield db
        finally:
            db.close()

    def observe(self, scope, *, namespace, external_id, title, stage, source, kind,
                language, event_key, version, released_on):
        owner = owner_key(scope)
        gid = game_id(namespace, external_id)
        url = source_url(source)
        title = clean(title, 256)
        if stage not in STAGES or kind not in KINDS:
            raise ValueError("unsupported lifecycle or source kind")
        language = clean(language, 32).lower()
        if not re.fullmatch(r"[a-z]{2,8}(?:-[a-z0-9]{1,8}){0,3}|und", language):
            raise ValueError("invalid language tag")
        event_key = key(event_key)
        version = clean(version, 128) if version is not None else None
        if released_on is not None:
            import datetime
            if not isinstance(released_on, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", released_on):
                raise ValueError("invalid release date")
            datetime.date.fromisoformat(released_on)
        sid = digest([url, kind, language])
        payload = {"namespace":namespace,"external_id":external_id,"title":title,
                   "stage":stage,"source":url,"kind":kind,"language":language,
                   "version":version,"released_on":released_on}
        fingerprint = digest(payload)
        now = int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                before = db.execute("SELECT digest FROM observations WHERE owner=? AND game=? AND source=? AND event_key=?",
                                    (owner,gid,sid,event_key)).fetchone()
                if before:
                    if before[0] != fingerprint:
                        raise CatalogueHeld("event identity already binds different metadata")
                    db.execute("COMMIT")
                    return self._receipt(gid,sid,fingerprint,True)
                db.execute("INSERT OR IGNORE INTO counters(owner) VALUES(?)",(owner,))
                counts = db.execute("SELECT games,revisions FROM counters WHERE owner=?",(owner,)).fetchone()
                existing = db.execute("SELECT 1 FROM games WHERE owner=? AND id=?",(owner,gid)).fetchone()
                if counts["revisions"] >= MAX_REVISIONS or not existing and counts["games"] >= MAX_GAMES:
                    raise CatalogueHeld("catalogue quota reached")
                if not existing:
                    db.execute("INSERT INTO games VALUES(?,?,?,?,?,?,?)",
                               (owner,gid,namespace,external_id,title,stage,now))
                    db.execute("UPDATE counters SET games=games+1 WHERE owner=?",(owner,))
                else:
                    # Keep first-seen title/stage as identity hints, NOT a consensus
                    # current version; conflicting source observations remain separate.
                    db.execute("UPDATE games SET updated_at=? WHERE owner=? AND id=?",(now,owner,gid))
                alias = db.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)",(owner,gid,title))
                if alias.rowcount:
                    db.execute("INSERT INTO game_search(owner,game_id,title) VALUES(?,?,?)",(owner,gid,title))
                old_source = db.execute("SELECT 1 FROM sources WHERE owner=? AND game=? AND id=?",
                                        (owner,gid,sid)).fetchone()
                if not old_source:
                    count = db.execute("SELECT COUNT(*) FROM sources WHERE owner=? AND game=?",(owner,gid)).fetchone()[0]
                    if count >= MAX_SOURCES:
                        raise CatalogueHeld("per-game source quota reached")
                next_review = now + cadence(kind,stage)
                db.execute("""INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(owner,game,id) DO UPDATE SET last_observed=excluded.last_observed,
                    next_review=excluded.next_review,latest_event=excluded.latest_event""",(owner,gid,sid,url,kind,language,now,next_review,event_key))
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?)",
                           (owner,gid,sid,event_key,fingerprint,json.dumps(payload,ensure_ascii=False,sort_keys=True),now))
                self._index_observation(db,owner,gid,sid,event_key,payload,now)
                db.execute("UPDATE counters SET revisions=revisions+1 WHERE owner=?",(owner,))
                db.execute("COMMIT")
                return self._receipt(gid,sid,fingerprint,False)
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _receipt(game,source,fingerprint,replayed):
        return {"game_id":game,"source_id":source,"observation_digest":fingerprint,
                "replayed":replayed,"verified":False,"crawl_authorized":False,
                "wiki_approved":False,"training_allowed":False}

    def search(self, scope, query, *, limit=32):
        owner = owner_key(scope)
        limit = _limit(limit)
        words = re.findall(r"[^\W_]+",clean(query,256),flags=re.UNICODE)[:12]
        if not words:
            raise ValueError("search requires title terms")
        fts = 'owner : "' + owner + '" AND title : (' + " AND ".join('"'+word+'"' for word in words) + ")"
        with self._db() as db:
            rows = db.execute("""SELECT DISTINCT g.id AS game_id,g.namespace,g.external_id,g.title AS first_title,
                g.stage AS first_stage,g.updated_at FROM game_search f JOIN games g
                ON g.owner=f.owner AND g.id=f.game_id
                WHERE game_search MATCH ? AND g.owner=?
                ORDER BY g.updated_at DESC,g.id LIMIT ?""",(fts,owner,limit)).fetchall()
        return {"games":[dict(row) for row in rows],"catalogue_only":True,"verified":False}

    def history(self, scope, game, *, limit=32, before=None):
        owner = owner_key(scope)
        game = _id(game)
        limit = _limit(limit)
        args = [owner,game]
        predicate = ""
        if before is not None:
            if not isinstance(before,(tuple,list)) or len(before)!=3 or type(before[0]) is not int:
                raise ValueError("invalid history cursor")
            stamp,source,event = before
            predicate = " AND (recorded_at,source,event_key)<(?,?,?)"
            args += [stamp,_id(source),key(event)]
        args.append(limit+1)
        with self._db() as db:
            rows = db.execute("""SELECT source,event_key,digest,payload,recorded_at FROM observations
                WHERE owner=? AND game=?""" + predicate +
                " ORDER BY recorded_at DESC,source DESC,event_key DESC LIMIT ?",args).fetchall()
        result = [{**dict(row),"payload":json.loads(row["payload"]),"verified":False} for row in rows[:limit]]
        cursor = [rows[limit-1][k] for k in ("recorded_at","source","event_key")] if len(rows)>limit else None
        return {"observations":result,"next_cursor":cursor,"history_only":True}

    def due(self, scope, *, limit=32):
        owner = owner_key(scope)
        with self._db() as db:
            rows = db.execute("""SELECT game AS game_id,id AS source_id,url,kind,language,next_review
                FROM sources WHERE owner=? AND next_review<=?
                ORDER BY next_review,game,id LIMIT ?""",(owner,int(time.time()),_limit(limit))).fetchall()
        return {"review_candidates":[dict(row) for row in rows],
                "network_executed":False,"crawl_authorized":False}

    def sources(self, scope, game, *, after=None, limit=64):
        owner = owner_key(scope)
        game = _id(game)
        limit = _limit(limit)
        after = _id(after) if after is not None else ""
        with self._db() as db:
            rows = db.execute("""SELECT s.id AS source_id,s.url,s.kind,s.language,s.last_observed,s.next_review,
                o.payload AS latest_observation,o.digest AS observation_digest
                FROM sources s JOIN observations o ON o.owner=s.owner AND o.game=s.game
                AND o.source=s.id AND o.event_key=s.latest_event
                WHERE s.owner=? AND s.game=? AND s.id>? ORDER BY s.id LIMIT ?""",
                (owner,game,after,limit+1)).fetchall()
        return {"sources":[{**dict(row),"latest_observation":json.loads(row["latest_observation"]),
                            "verified":False} for row in rows[:limit]],
                "next_cursor":rows[limit-1]["source_id"] if len(rows)>limit else None,
                "crawl_authorized":False,"source_use_authorized":False}


    def capture_plan(self,scope,game,source,observation_digest):
        """Resolve exactly one current catalogue entry, not a URL supplied to dispatch."""
        owner=owner_key(scope)
        game,source,observation_digest=map(_id,(game,source,observation_digest))
        with self._db() as db:
            row=db.execute("""SELECT s.url,s.kind,s.language,o.digest,o.payload
                FROM sources s JOIN observations o ON o.owner=s.owner AND o.game=s.game
                AND o.source=s.id AND o.event_key=s.latest_event
                WHERE s.owner=? AND s.game=? AND s.id=?""",(owner,game,source)).fetchone()
        if not row or row["digest"]!=observation_digest:
            raise CatalogueHeld("source candidate changed or unavailable")
        payload=json.loads(row["payload"])
        if digest(payload)!=observation_digest or source_url(row["url"])!=payload["source"]:
            raise CatalogueHeld("source observation witness changed")
        return {"game_id":game,"source_id":source,"observation_digest":observation_digest,
                "url":row["url"],"kind":row["kind"],"language":row["language"],
                "title":payload["title"],"crawl_authorized":False,"wiki_approved":False}


    @staticmethod
    def _index_observation(db,owner,gid,sid,event,payload,now):
        db.execute("""INSERT OR IGNORE INTO release_facets
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(owner,gid,sid,event,payload["stage"],payload["kind"],
            payload["language"],payload["released_on"],now,payload["version"],
            priority(payload["kind"],payload["stage"])))

    def release_timeline(self,scope,*,stage=None,kind=None,language=None,current_only=False,
                         limit=32,before=None):
        """Owner-scoped release and patch timeline; latest observation is not truth."""
        owner=owner_key(scope)
        limit=_limit(limit)
        if type(current_only) is not bool:
            raise ValueError("current flag")
        clauses=["f.owner=?"]
        args=[owner]
        if stage is not None:
            if stage not in STAGES: raise ValueError("stage")
            clauses.append("f.stage=?");args.append(stage)
        if kind is not None:
            if kind not in KINDS: raise ValueError("source kind")
            clauses.append("f.kind=?");args.append(kind)
        if language is not None:
            language=clean(language,32).lower()
            clauses.append("f.language=?");args.append(language)
        if current_only:
            clauses.append("s.latest_event=f.event_key")
        if before is not None:
            if not isinstance(before,(tuple,list)) or len(before)!=4 or type(before[0]) is not int:
                raise ValueError("timeline cursor")
            clauses.append("(f.observed_at,f.game,f.source,f.event_key)<(?,?,?,?)")
            args.extend([before[0],_id(before[1]),_id(before[2]),key(before[3])])
        args.append(limit+1)
        with self._db() as db:
            rows=db.execute("""SELECT f.game AS game_id,f.source AS source_id,f.event_key,
                f.stage,f.kind,f.language,f.released_on,f.observed_at,f.version,f.priority,
                g.title AS first_title,o.digest AS observation_digest,
                s.latest_event=f.event_key AS latest_for_source
                FROM release_facets f JOIN sources s ON s.owner=f.owner AND s.game=f.game AND s.id=f.source
                JOIN games g ON g.owner=f.owner AND g.id=f.game
                JOIN observations o ON o.owner=f.owner AND o.game=f.game AND o.source=f.source AND o.event_key=f.event_key
                WHERE """+" AND ".join(clauses)+
                " ORDER BY f.observed_at DESC,f.game DESC,f.source DESC,f.event_key DESC LIMIT ?",args).fetchall()
        result=[{**dict(row),"latest_for_source":bool(row["latest_for_source"]),"verified":False} for row in rows[:limit]]
        cursor=[rows[limit-1][k] for k in ("observed_at","game_id","source_id","event_key")] if len(rows)>limit else None
        return {"events":result,"next_cursor":cursor,"catalogue_only":True,"verified":False,
                "current_means_latest_observed":True,"index_may_be_partial":True}

    def backfill_facets(self,*,limit=32):
        """Bounded keyset migration, no repeated whole-corpus missing-row scan.

        New writes publish facets atomically; migration only repairs older rows.
        A corrupt existing row holds the cursor instead of silently skipping it.
        """
        limit=_limit(limit)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT OR IGNORE INTO corpus_migration VALUES('release-facets-v1',NULL,0)")
                state=db.execute("SELECT cursor,complete FROM corpus_migration WHERE name='release-facets-v1'").fetchone()
                if state["complete"]:
                    db.execute("COMMIT")
                    return {"indexed":0,"visited":0,"complete":True,"network_executed":False}
                where=""
                args=[]
                if state["cursor"] is not None:
                    cursor=json.loads(state["cursor"])
                    if not isinstance(cursor,list) or len(cursor)!=4 or not all(isinstance(x,str) for x in cursor):
                        raise CatalogueHeld("facet migration cursor invalid")
                    where=" WHERE (o.owner,o.game,o.source,o.event_key)>(?,?,?,?)"
                    args.extend(cursor)
                args.append(limit)
                rows=db.execute("""SELECT o.owner,o.game,o.source,o.event_key,o.payload,o.digest,o.recorded_at
                    FROM observations o"""+where+" ORDER BY o.owner,o.game,o.source,o.event_key LIMIT ?",args).fetchall()
                indexed=0
                for row in rows:
                    existing=db.execute("SELECT 1 FROM release_facets WHERE owner=? AND game=? AND source=? AND event_key=?",
                                        (row["owner"],row["game"],row["source"],row["event_key"])).fetchone()
                    if existing: continue
                    payload=json.loads(row["payload"])
                    if digest(payload)!=row["digest"]:
                        raise CatalogueHeld("historical observation witness mismatch")
                    self._index_observation(db,row["owner"],row["game"],row["source"],row["event_key"],payload,row["recorded_at"])
                    indexed+=1
                cursor=json.dumps([rows[-1][k] for k in ("owner","game","source","event_key")]) if rows else state["cursor"]
                complete=len(rows)<limit
                db.execute("UPDATE corpus_migration SET cursor=?,complete=? WHERE name='release-facets-v1'",(cursor,int(complete)))
                db.execute("COMMIT")
                return {"indexed":indexed,"visited":len(rows),"complete":complete,"network_executed":False}
            except BaseException:
                if db.in_transaction: db.execute("ROLLBACK")
                raise
