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

KINDS = {
    "official_wiki": 86400, "community_wiki": 86400, "storefront": 21600,
    "release_feed": 3600, "patch_notes": 3600, "developer_blog": 21600,
    "manual": 604800, "mod_catalogue": 86400, "technical_reference": 604800,
    "accessibility": 604800, "preservation": 604800, "esports": 21600,
    "community_guide": 86400, "engine_docs": 604800, "localization": 86400,
}
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
CREATE TABLE IF NOT EXISTS sources(
 owner TEXT NOT NULL, game TEXT NOT NULL, id TEXT NOT NULL,
 url TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL,
 last_observed INTEGER NOT NULL, next_review INTEGER NOT NULL,
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
 ON observations(owner,game,recorded_at DESC,source,event_key);
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
                    db.execute("INSERT INTO game_search(owner,game_id,title) VALUES(?,?,?)",(owner,gid,title))
                else:
                    # Keep first-seen title/stage as identity hints, NOT a consensus
                    # current version; conflicting source observations remain separate.
                    db.execute("UPDATE games SET updated_at=? WHERE owner=? AND id=?",(now,owner,gid))
                old_source = db.execute("SELECT 1 FROM sources WHERE owner=? AND game=? AND id=?",
                                        (owner,gid,sid)).fetchone()
                if not old_source:
                    count = db.execute("SELECT COUNT(*) FROM sources WHERE owner=? AND game=?",(owner,gid)).fetchone()[0]
                    if count >= MAX_SOURCES:
                        raise CatalogueHeld("per-game source quota reached")
                next_review = now + KINDS[kind]
                if stage in {"announced","early_access","updated"}:
                    next_review = now + min(21600,KINDS[kind])
                db.execute("""INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(owner,game,id) DO UPDATE SET last_observed=excluded.last_observed,
                    next_review=excluded.next_review""",(owner,gid,sid,url,kind,language,now,next_review))
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?)",
                           (owner,gid,sid,event_key,fingerprint,json.dumps(payload,ensure_ascii=False,sort_keys=True),now))
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
            rows = db.execute("""SELECT g.id AS game_id,g.namespace,g.external_id,g.title AS first_title,
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
            rows = db.execute("""SELECT id AS source_id,url,kind,language,last_observed,next_review
                FROM sources WHERE owner=? AND game=? AND id>? ORDER BY id LIMIT ?""",
                (owner,game,after,limit+1)).fetchall()
        return {"sources":[dict(row) for row in rows[:limit]],
                "next_cursor":rows[limit-1]["source_id"] if len(rows)>limit else None,
                "crawl_authorized":False,"source_use_authorized":False}
