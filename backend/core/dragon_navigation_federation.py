"""Durable cross-session locator federation in the existing owner-sharded corpus.

The crawler's finite snapshot is execution custody, not a global research
catalogue. This catalogue stores only explicitly approved public locator
metadata. Separate finite retention authority is required; nothing here
retains page bodies, renews capture consent or authorizes a new crawl.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
import shutil
import time
from urllib.parse import urlsplit

from core.dragon_game_corpus import GameCorpus, source_url
from core.dragon_hoarder_bulk import owner_key
from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.frontier_circuit import navigation_hazard
from skeleton.ai.webcrawler.navigation_semantics import words, concepts, CONCEPTS, semantic_features

RESERVE = 512 * 1024 * 1024
MAX_RETENTION = 3650 * 86400
HEX = re.compile(r"[a-f0-9]{64}\Z")
SCHEMA = """
CREATE TABLE IF NOT EXISTS navigation_grants(
 owner TEXT NOT NULL, grant_id TEXT NOT NULL, source_session TEXT NOT NULL,
 checkpoint TEXT NOT NULL, rights_digest TEXT NOT NULL, expires INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','revoked')),
 accepted INTEGER NOT NULL, omitted INTEGER NOT NULL,
 PRIMARY KEY(owner,grant_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_grants_session ON navigation_grants(owner,source_session,grant_id);
CREATE INDEX IF NOT EXISTS navigation_grants_expiry ON navigation_grants(owner,state,expires,grant_id);
CREATE TABLE IF NOT EXISTS navigation_nodes(
 owner TEXT NOT NULL, id TEXT NOT NULL, url TEXT NOT NULL, host TEXT NOT NULL,
 search_terms TEXT NOT NULL, PRIMARY KEY(owner,id), UNIQUE(owner,url)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_nodes_host ON navigation_nodes(owner,host,id);
CREATE TABLE IF NOT EXISTS navigation_witnesses(
 owner TEXT NOT NULL, grant_id TEXT NOT NULL, target TEXT NOT NULL,
 ordinal INTEGER NOT NULL, occurrence_count INTEGER NOT NULL, relation TEXT NOT NULL,
 PRIMARY KEY(owner,grant_id,target),
 FOREIGN KEY(owner,grant_id) REFERENCES navigation_grants(owner,grant_id),
 FOREIGN KEY(owner,target) REFERENCES navigation_nodes(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_witnesses_target ON navigation_witnesses(owner,target,grant_id);
CREATE VIRTUAL TABLE IF NOT EXISTS navigation_fts USING fts5(
 owner,id UNINDEXED,search_terms,tokenize='unicode61 remove_diacritics 2');
"""


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                  separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _hash(v):
    if not isinstance(v, str) or not HEX.fullmatch(v):
        raise ValueError("invalid navigation federation identity")
    return v


def _text(v, maximum):
    if not isinstance(v,str) or v != v.strip() or not 1 <= len(v) <= maximum or any(ord(c)<32 for c in v):
        raise ValueError("invalid navigation federation reference")
    return v


def _terms(query):
    tokens = set(words(query))
    for index in concepts(tokens):
        tokens.update(CONCEPTS[index])
    return tuple(sorted(tokens))[:128]


class NavigationFederation:
    """No aggregate row ceiling: physical owner-sharded corpus and disk govern.

    Each admission is a finite checkpoint, one ACID write and idempotent
    grant. Search uses keyset pagination, an indexed lexical/concept candidate
    lane and bounded work. Expired or revoked witnesses are never returned.
    """

    def __init__(self, path):
        self.corpus = GameCorpus(path)

    @contextmanager
    def _db(self, *, write=False):
        if write and shutil.disk_usage(self.corpus.path.parent).free < RESERVE:
            raise OSError("navigation federation storage reserve held")
        with self.corpus._db() as db:
            db.executescript(SCHEMA + graph.SCHEMA)
            deadline = time.monotonic() + 15
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            try:
                yield db
            finally:
                db.set_progress_handler(None, 0)

    def publish(self, scope, *, session_id, snapshot, rights_reference, retention_seconds,
                acknowledged, now=None):
        if acknowledged is not True:
            raise ValueError("separate public locator retention consent required")
        if type(retention_seconds) is not int or not 900 <= retention_seconds <= MAX_RETENTION:
            raise ValueError("navigation retention interval")
        owner = owner_key(scope)
        session_id = _text(session_id,128)
        rights = digest(_text(rights_reference,256))
        now = int(time.time()) if now is None else now
        checkpoint = _hash(snapshot["snapshot_digest"])
        from skeleton.ai.webcrawler.operations import _digest as checkpoint_digest
        if checkpoint_digest({k:v for k,v in snapshot.items() if k != "snapshot_digest"}) != checkpoint:
            raise ValueError("navigation checkpoint integrity")
        binding = snapshot["binding"]
        if (binding["scope"] != scope or binding["consent"]["expires_at"] <= now
                or binding["consent"]["source_rights_acknowledged"] is not True
                or snapshot["state"] not in {"completed","budget_exhausted"}):
            raise ValueError("terminal current owner checkpoint required")
        from skeleton.ai.webcrawler.operations import CrawlRun
        ledger = CrawlRun.from_snapshot(snapshot).snapshot()["discovery_backlog"]
        rows, omitted = [], 0
        for observed in ledger["records"].values():
            try:
                url = source_url(observed["url"])
                if url != observed["url"] or navigation_hazard(url) is not None:
                    raise ValueError("non-public locator")
                rows.append((hashlib.sha256(url.encode()).hexdigest(),url,observed))
            except (ValueError,UnicodeError):
                omitted += 1
        grant = digest([owner,session_id,checkpoint,rights,retention_seconds])
        with self._db(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                prior = db.execute("SELECT * FROM navigation_grants WHERE owner=? AND grant_id=?",
                                   (owner,grant)).fetchone()
                if prior is not None:
                    if prior["state"] != "active" or prior["expires"] <= now:
                        raise ValueError("navigation retention grant no longer active")
                    db.execute("COMMIT")
                    return self._receipt(prior, replayed=True)
                db.execute("INSERT INTO navigation_grants VALUES(?,?,?,?,?,?,'active',?,?)",
                           (owner,grant,session_id,checkpoint,rights,now+retention_seconds,len(rows),omitted))
                for identifier,url,row in rows:
                    host = urlsplit(url).hostname
                    terms = " ".join(sorted(set(words(host)) | set(words(urlsplit(url).path))))
                    inserted = db.execute("INSERT OR IGNORE INTO navigation_nodes VALUES(?,?,?,?,?)",
                                          (owner,identifier,url,host,terms))
                    if inserted.rowcount:
                        db.execute("INSERT INTO navigation_fts(owner,id,search_terms) VALUES(?,?,?)",
                                   (owner,identifier,terms))
                    else:
                        existing = db.execute("SELECT url FROM navigation_nodes WHERE owner=? AND id=?",
                                              (owner,identifier)).fetchone()
                        if existing is None or existing["url"] != url:
                            raise ValueError("navigation locator collision")
                    db.execute("INSERT INTO navigation_witnesses VALUES(?,?,?,?,?,?)",
                               (owner,grant,identifier,row["ordinal"],row["observations"],row["kind"]))
                for identifier,url,_ in rows:
                    graph.index_node(db,owner,identifier,url)
                graph.publish_edges(db,owner,grant,rows)
                graph.publish_outcomes(db,owner,grant,rows,snapshot)
                stored = db.execute("SELECT * FROM navigation_grants WHERE owner=? AND grant_id=?",
                                    (owner,grant)).fetchone()
                db.execute("COMMIT")
                return self._receipt(stored,replayed=False)
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _receipt(row, *, replayed):
        return {"grant_id":row["grant_id"],"checkpoint":row["checkpoint"],
                "accepted":row["accepted"],"omitted_nonpublic":row["omitted"],
                "retention_expires_at":row["expires"],"replayed":replayed,
                "network_authorized":False,"metadata_only":True}

    def search(self, scope, *, query="", host=None, after=None, limit=32, now=None):
        owner = owner_key(scope)
        now = int(time.time()) if now is None else now
        if not isinstance(query,str) or len(query)>512 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError("navigation search bound")
        if host is not None:
            host=_text(host,253).lower()
            if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",host):
                raise ValueError("navigation host")
        terms = _terms(query)
        fingerprint = digest([owner,query,host])
        lower = ""
        if after is not None:
            if not isinstance(after,str) or len(after)!=129 or not after.startswith(fingerprint+":"):
                raise ValueError("navigation cursor filter")
            lower=_hash(after[65:])
        clauses=["n.owner=?","n.id>?", "EXISTS (SELECT 1 FROM navigation_witnesses w "
                 "JOIN navigation_grants g ON g.owner=w.owner AND g.grant_id=w.grant_id "
                 "WHERE w.owner=n.owner AND w.target=n.id AND g.state='active' AND g.expires>?)"]
        args=[owner,lower,now]
        sql="SELECT n.id,n.url,n.host FROM navigation_nodes n"
        if host:
            clauses.append("n.host=?");args.append(host)
        if terms:
            sql+=" JOIN navigation_fts f ON f.owner=n.owner AND f.id=n.id"
            clauses.append("navigation_fts MATCH ?")
            args.append('owner:"'+owner+'" AND ('+' OR '.join('"'+t+'"' for t in terms)+')')
        sql+=" WHERE "+" AND ".join(clauses)+" ORDER BY n.id LIMIT ?"
        args.append(limit+1)
        with self._db() as db:
            db.execute("BEGIN")
            try:
                rows=db.execute(sql,args).fetchall()
                result=[]
                for row in rows[:limit]:
                    witness=db.execute("""SELECT g.grant_id,g.source_session,g.checkpoint,g.expires,
                           w.relation,w.occurrence_count FROM navigation_witnesses w
                           JOIN navigation_grants g ON g.owner=w.owner AND g.grant_id=w.grant_id
                           WHERE w.owner=? AND w.target=? AND g.state='active' AND g.expires>?
                           ORDER BY g.grant_id LIMIT 1""",(owner,row["id"],now)).fetchone()
                    if witness is None:
                        raise ValueError("navigation witness missing")
                    result.append({**dict(row),"witness":dict(witness),
                                   "semantic":semantic_features(query,row["url"])["score"],
                                   "network_authorized":False,"reviewed":False})
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"targets":result, "next_cursor":fingerprint+":"+rows[limit-1]["id"] if len(rows)>limit else None,
                "candidate_metadata_only":True,"network_authorized":False,
                "global_completeness_claimed":False}

    def topology(self,scope,*,target,direction="children",after=None,limit=32,now=None):
        with self._db() as db:
            return graph.neighbors(db,owner_key(scope),target,direction=direction,after=after,
                limit=limit,now=int(time.time()) if now is None else now)

    def shortlist(self,scope,*,query,host=None,limit=48,due_only=False,now=None):
        with self._db() as db:
            db.execute("BEGIN")
            return graph.retrieve(db,owner_key(scope),query=query,host=host,limit=limit,due_only=due_only,
                now=int(time.time()) if now is None else now)

    def portfolio(self,scope,*,query,limit=12,now=None):
        with self._db() as db:
            db.execute("BEGIN")
            return graph.portfolio(db,owner_key(scope),query=query,limit=limit,
                now=int(time.time()) if now is None else now)

    def research_plan(self,scope,*,query,budget=16,mode="balanced",previous=None,learned=False,now=None):
        from core.dragon_navigation_intelligence import plan
        with self._db() as db:
            db.execute("BEGIN")
            return plan(db,owner_key(scope),query=query,budget=budget,mode=mode,previous=previous,learned=learned,
                        now=int(time.time()) if now is None else now)

    def trail(self,scope,*,root,query,depth=3,beam=24,now=None):
        with self._db() as db:
            db.execute("BEGIN")
            return graph.trail(db,owner_key(scope),root=root,query=query,depth=depth,beam=beam,
                now=int(time.time()) if now is None else now)

    def reindex(self,scope,*,after=None,limit=100):
        with self._db(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                receipt=graph.reindex(db,owner_key(scope),after=after,limit=limit)
                db.execute("COMMIT")
                return receipt
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def review(self,scope,*,target,state,reason,expected_revision,next_review,now=None):
        with self._db(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                receipt=graph.review(db,owner_key(scope),target,state=state,reason=reason,
                    expected_revision=expected_revision,next_review=next_review,
                    now=int(time.time()) if now is None else now)
                db.execute("COMMIT")
                return receipt
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def revoke(self,scope,grant):
        owner=owner_key(scope);grant=_hash(grant)
        with self._db() as db:
            changed=db.execute("UPDATE navigation_grants SET state='revoked',expires=0 "
                               "WHERE owner=? AND grant_id=?",(owner,grant))
        return {"revoked":changed.rowcount==1,"network_authorized":False}

    def purge(self,scope,*,limit=256,now=None):
        """Bounded physical erasure of expired/revoked payloads; keep tombstones."""
        if type(limit) is not int or not 1<=limit<=1024:
            raise ValueError("navigation purge bound")
        owner=owner_key(scope);now=int(time.time()) if now is None else now
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows=db.execute("""SELECT w.grant_id,w.target FROM navigation_witnesses w
                    JOIN navigation_grants g ON g.owner=w.owner AND g.grant_id=w.grant_id
                    WHERE w.owner=? AND (g.state='revoked' OR g.expires<=?)
                    ORDER BY w.grant_id,w.target LIMIT ?""",(owner,now,limit)).fetchall()
                for row in rows:
                    db.execute("DELETE FROM navigation_witnesses WHERE owner=? AND grant_id=? AND target=?",
                               (owner,row["grant_id"],row["target"]))
                    if not db.execute("SELECT 1 FROM navigation_witnesses WHERE owner=? AND target=? LIMIT 1",
                                      (owner,row["target"])).fetchone():
                        db.execute("DELETE FROM navigation_fts WHERE owner=? AND id=?",(owner,row["target"]))
                        db.execute("DELETE FROM navigation_nodes WHERE owner=? AND id=?",(owner,row["target"]))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"removed_witnesses":len(rows),"more_possible":len(rows)==limit,
                "network_authorized":False}


async def application_call(application,scope,operation,**kwargs):
    """Use the existing corpus owner-shard selector and bounded thread gate."""
    from core.dragon_corpus_runtime import _bounded, _path
    from core.dragon_crawler import CrawlerError, _plain, _utc, _now
    from core.dragon_game_corpus import CatalogueHeld
    import sqlite3
    if operation not in {"publish","search","revoke","purge","topology","shortlist","portfolio","trail","reindex","review","research_plan"}:
        raise ValueError("navigation federation operation")
    if operation=="publish":
        session_id=kwargs["session_id"]
        row=await application._owned(scope,session_id)
        application._source_use(row)
        if row["status"] not in {"completed","budget_exhausted"}:
            raise CrawlerError("crawler_navigation_held","Complete or exhaust the crawl before retaining locator metadata.",409)
        snapshot=_plain(application._custody_snapshot(row))
        if (kwargs.pop("expected_snapshot_digest")!=snapshot["snapshot_digest"]
                or _utc(row["consent_expires_at"])<=_now()):
            raise CrawlerError("crawler_navigation_stale","Refresh the current authorized checkpoint.",409)
        kwargs["snapshot"]=snapshot
    def work():
        return getattr(NavigationFederation(_path(scope=scope)),operation)(scope,**kwargs)
    try:
        return await _bounded(work)
    except (OSError,sqlite3.Error,CatalogueHeld,TimeoutError) as exc:
        raise CrawlerError("crawler_navigation_storage_held","The configured navigation catalogue is unavailable.",503) from exc


async def batch_publish(application,scope,*,sessions,rights_reference,retention_seconds,acknowledged):
    """Bounded, retry-safe batch of independently authorized checkpoints.

    Each publication has its own transaction and grant identity. A request
    never silently renews expired authority or grants other owners access.
    Partial outcomes are explicit; replay the same batch to recover receipts.
    """
    from core.dragon_crawler import CrawlerError
    if acknowledged is not True or not isinstance(sessions,list) or not 1<=len(sessions)<=16:
        raise ValueError("explicit bounded locator retention batch required")
    _text(rights_reference,256)
    if type(retention_seconds) is not int or not 900<=retention_seconds<=MAX_RETENTION:
        raise ValueError("navigation retention interval")
    identifiers=set()
    for item in sessions:
        if not isinstance(item,dict) or set(item)!={"session_id","expected_snapshot_digest"}:
            raise ValueError("navigation batch checkpoint schema")
        identifier=_text(item["session_id"],128)
        _hash(item["expected_snapshot_digest"])
        if identifier in identifiers:raise ValueError("duplicate batch session")
        identifiers.add(identifier)
    result=[]
    for item in sessions:
        try:
            receipt=await application_call(application,scope,"publish",**item,
                rights_reference=rights_reference,retention_seconds=retention_seconds,
                acknowledged=True)
        except CrawlerError as exc:
            result.append({"session_id":item["session_id"],"state":"held","code":exc.code})
        except (ValueError,TypeError,KeyError,LookupError):
            result.append({"session_id":item["session_id"],"state":"held","code":"navigation_checkpoint_held"})
        else:
            result.append({"session_id":item["session_id"],"state":"published","receipt":receipt})
    return {"outcomes":result,"published":sum(x["state"]=="published" for x in result),
        "held":sum(x["state"]=="held" for x in result),"atomic_batch":False,
        "network_authorized":False}
