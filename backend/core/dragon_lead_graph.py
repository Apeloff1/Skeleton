"""Durable owner-scoped, ever-growing research lead graph.

Candidate identity is not a reviewed source. Every expansion keeps its parent
and exact metadata witness. Discovery never delegates network authority to an
unreviewed child. No corpus text, binary payload or user account data is stored.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import re
import shutil
import sqlite3
import time
from urllib.parse import urlsplit

from core.dragon_game_corpus import GameCorpus,CatalogueHeld,clean,digest,source_url,_id
from core.dragon_game_taxonomy import SOURCE_CLASSES
from core.dragon_hoarder_bulk import owner_key
from core.dragon_dataset_library import target,_library
from core.dragon_mod_seed_catalogue import STEAM_ROUTES,APPID,_canonical_locator
from core.dragon_lead_index_shards import SOURCE_SCHEMA as INDEX_SCHEMA
from core.dragon_lead_edge_shards import SOURCE_SCHEMA as EDGE_SCHEMA

LEAD_LANES=10
NODES_PER_LANE=20_000_000
EDGES_PER_LANE=100_000_000
MAX_NODES=LEAD_LANES*NODES_PER_LANE
MAX_EDGES=LEAD_LANES*EDGES_PER_LANE
MAX_SNAPSHOTS=100_000
MAX_DYNAMIC_TARGETS=100_000
MAX_SNAPSHOT_ROWS=100_000_000
MAX_PAGE_ROWS=128
MAX_PAGE_BYTES=1024*1024
MAX_GRANT=30*86400
MAX_SEED_BATCH=256
BUNDLE_PAGES_PER_PULSE=4
MAX_BOOTSTRAP_OWNERS=100_000
MIN_RESERVE=512*1024*1024
ZERO="0"*64
PROJECTION_VERSION="dragon.lead-projection.v1"
SCHEMA="""
CREATE TABLE IF NOT EXISTS lead_owner(
 owner TEXT PRIMARY KEY, scope_json TEXT NOT NULL, enabled INTEGER NOT NULL,
 bootstrap_revision TEXT, bootstrap_cursor INTEGER NOT NULL DEFAULT 0,
 bootstrapped INTEGER NOT NULL DEFAULT 0,due INTEGER NOT NULL,
 nodes INTEGER NOT NULL DEFAULT 0,edges INTEGER NOT NULL DEFAULT 0,
 snapshots INTEGER NOT NULL DEFAULT 0,
 CHECK(nodes>=0 AND edges>=0 AND snapshots>=0)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_owner_due ON lead_owner(enabled,due,owner);
CREATE TABLE IF NOT EXISTS lead_lane_counts(
 owner TEXT NOT NULL,lane INTEGER NOT NULL CHECK(lane BETWEEN 0 AND 9),
 nodes INTEGER NOT NULL CHECK(nodes>=0),edges INTEGER NOT NULL CHECK(edges>=0),
 PRIMARY KEY(owner,lane)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_nodes(
 owner TEXT NOT NULL,id TEXT NOT NULL,url TEXT NOT NULL,host TEXT NOT NULL,
 title TEXT NOT NULL,kind TEXT NOT NULL,family TEXT NOT NULL,
 first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,next_review INTEGER NOT NULL,
 observations INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('candidate','held','retired')),
 PRIMARY KEY(owner,id),UNIQUE(owner,url)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_nodes_due ON lead_nodes(owner,state,next_review,id);
CREATE INDEX IF NOT EXISTS lead_nodes_family ON lead_nodes(owner,family,id);
CREATE INDEX IF NOT EXISTS lead_nodes_host ON lead_nodes(owner,host,id);
CREATE TABLE IF NOT EXISTS lead_edges(
 owner TEXT NOT NULL,id TEXT NOT NULL,parent TEXT NOT NULL,child TEXT NOT NULL,
 relation TEXT NOT NULL,subject TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,
 witness TEXT NOT NULL,snapshot TEXT,first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,
 PRIMARY KEY(owner,id),
 FOREIGN KEY(owner,child) REFERENCES lead_nodes(owner,id),
 CHECK(length(witness)=64)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_edges_parent ON lead_edges(owner,parent,id);
CREATE INDEX IF NOT EXISTS lead_edges_child ON lead_edges(owner,child,id);
CREATE INDEX IF NOT EXISTS lead_edges_subject ON lead_edges(owner,subject,id);
CREATE VIRTUAL TABLE IF NOT EXISTS lead_fts USING fts5(owner,id UNINDEXED,title,url,kind,family,
 tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS lead_dataset_candidates(
 owner TEXT NOT NULL,lead TEXT NOT NULL,first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,
 PRIMARY KEY(owner,lead),FOREIGN KEY(owner,lead) REFERENCES lead_nodes(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_dynamic_targets(
 owner TEXT NOT NULL,id TEXT NOT NULL,lead TEXT NOT NULL,projection TEXT NOT NULL,
 revision TEXT NOT NULL,rights_ref TEXT NOT NULL,enabled INTEGER NOT NULL,
 reviewed_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
 PRIMARY KEY(owner,id),UNIQUE(owner,lead),FOREIGN KEY(owner,lead) REFERENCES lead_nodes(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_snapshots(
 owner TEXT NOT NULL,id TEXT NOT NULL,root TEXT NOT NULL,target_id TEXT NOT NULL,
 registry_revision TEXT NOT NULL,projection TEXT NOT NULL,source_sha TEXT NOT NULL,rights_ref TEXT NOT NULL,
 expected_rows INTEGER NOT NULL,rows INTEGER NOT NULL DEFAULT 0,
 next_page INTEGER NOT NULL DEFAULT 0,chain TEXT NOT NULL,state TEXT NOT NULL,
 expires_at INTEGER NOT NULL,created_at INTEGER NOT NULL,sealed_at INTEGER,
 PRIMARY KEY(owner,id),
 CHECK(state IN ('open','sealed','revoked'))
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_snapshot_target ON lead_snapshots(owner,target_id,created_at,id);
CREATE TABLE IF NOT EXISTS lead_snapshot_pages(
 owner TEXT NOT NULL,snapshot TEXT NOT NULL,ordinal INTEGER NOT NULL,digest TEXT NOT NULL,
 row_count INTEGER NOT NULL,chain TEXT NOT NULL,
 PRIMARY KEY(owner,snapshot,ordinal),
 FOREIGN KEY(owner,snapshot) REFERENCES lead_snapshots(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lead_expand_jobs(
 owner TEXT NOT NULL,id TEXT NOT NULL,parent TEXT NOT NULL,appid TEXT NOT NULL,title TEXT NOT NULL,
 witness TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('queued','done','held')),created_at INTEGER NOT NULL,snapshot TEXT,
 PRIMARY KEY(owner,id),FOREIGN KEY(owner,parent) REFERENCES lead_nodes(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_expand_ready ON lead_expand_jobs(state,created_at,owner,id);
CREATE TABLE IF NOT EXISTS lead_review_events(
 owner TEXT NOT NULL,id TEXT NOT NULL,lead TEXT NOT NULL,decision TEXT NOT NULL,
 reason TEXT NOT NULL,created_at INTEGER NOT NULL,
 PRIMARY KEY(owner,id),FOREIGN KEY(owner,lead) REFERENCES lead_nodes(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS lead_review_history ON lead_review_events(owner,lead,created_at,id);
"""+INDEX_SCHEMA+EDGE_SCHEMA
STATES={"candidate","held","retired"}
DATASET_KINDS={"dataset_manifest","dataset_checksum_manifest","public_jsonl_dataset","public_csv_dataset","public_parquet_dataset","public_sqlite_dataset","public_data_export","static_data_export","static_data_schema","dataset_version_history","public_metadata_bulk_export","research_dataset_catalogue","public_data_endpoint"}
RELATIONS={"seed","dataset_target","dataset_projection","feed_discovery","catalogue_observation"}

def _quota_disk(path):
    if shutil.disk_usage(path.parent).free<MIN_RESERVE:
        raise CatalogueHeld("lead graph disk reserve")

def _locator(url):
    return _canonical_locator(source_url(url))

def lead_id(url):
    return digest(["dragon.lead.v1",_locator(url)])

def lead_lane(identifier):
    key=_id(identifier)
    return int(key[:4],16)*LEAD_LANES//65536


def lane_bounds(lane):
    if type(lane) is not int or not 0<=lane<LEAD_LANES:raise ValueError("lead lane")
    low=(lane*65536+LEAD_LANES-1)//LEAD_LANES
    high=((lane+1)*65536+LEAD_LANES-1)//LEAD_LANES
    return format(low,"04x"),format(high,"04x") if high<65536 else "g"


def _lane_counts(db,owner,lane):
    row=db.execute("SELECT nodes,edges FROM lead_lane_counts WHERE owner=? AND lane=?",(owner,lane)).fetchone()
    if row is not None:return row
    # Lazy indexed migration of existing owner rows; one lane at a time.
    # Runs inside the caller's transaction; previous binaries must be stopped.
    low,high=lane_bounds(lane)
    nodes=db.execute("SELECT COUNT(*) FROM lead_nodes WHERE owner=? AND id>=? AND id<?",
        (owner,low,high)).fetchone()[0]
    edges=db.execute("SELECT COUNT(*) FROM lead_edges WHERE owner=? AND child>=? AND child<?",
        (owner,low,high)).fetchone()[0]
    db.execute("INSERT INTO lead_lane_counts VALUES(?,?,?,?)",(owner,lane,nodes,edges))
    return {"nodes":nodes,"edges":edges}


def _int(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError("lead integer bound")
    return value

def _tokens(q):
    if q is None:return []
    terms=re.findall(r"[^\W_]+",clean(q,256).casefold())[:12]
    if not terms:raise ValueError("lead search terms")
    return terms

def _schema_row(url,title,kind,subject):
    url=_locator(url);title=clean(title,256);subject=clean(subject,256)
    if kind not in SOURCE_CLASSES:raise ValueError("lead source class")
    return url,title,kind,subject

def _seed_inventory():
    from core.dragon_source_directory import _load as legacy
    from core.dragon_mod_seed_catalogue import _load as expanded
    lv,_,lr,_=legacy();mv,mr,*_=expanded();dv,dr=_library()
    return lv,mv,dv,lr,mr,dr

@lru_cache(maxsize=1)
def bootstrap_inventory():
    lv,mv,dv,lr,mr,dr=_seed_inventory()
    # One node for a locator; distinct source provenance stays as edges.
    inventory=[]
    for item in lr.values():
        inventory.append((item["url"],item["label"],item["kind"],"directory:"+item["group"],"seed",lv,item["lead_id"]))
    for item in mr.values():
        subject="steam:"+item["appid"] if item["appid"] else "seed:"+item["group"]
        inventory.append((item["url"],item["title"]+" · "+item["label"],item["kind"],subject,"seed",mv,item["seed_id"]))
    for item in dr.values():
        inventory.append((item["url"],item["id"],"dataset_manifest","dataset:"+item["id"],"dataset_target",dv,item["id"]))
    inventory.sort(key=lambda r:(r[4],r[6]))
    return digest([lv,mv,dv]),tuple(inventory)

def _pairs(values):
    out={}
    for k,v in values:
        if k in out:raise ValueError("duplicate projection field")
        out[k]=v
    return out

def parse_page(raw,projection):
    """Accept a bounded normalized page; do not accept arbitrary raw exports."""
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_PAGE_BYTES:raise ValueError("lead page bytes")
    lines=raw.splitlines()
    if not 1<=len(lines)<=MAX_PAGE_ROWS:raise ValueError("lead page rows")
    rows=[]
    for line in lines:
        if not line.strip() or len(line)>8192:raise ValueError("lead row bytes")
        item=json.loads(line,object_pairs_hook=_pairs)
        if not isinstance(item,dict):raise ValueError("lead row fields")
        if projection in {"steam","steam_seed"}:
            if set(item)!={"appid","title"}:raise ValueError("Steam projection schema")
            appid=item["appid"]
            if type(appid) is int:appid=str(appid)
            if not isinstance(appid,str) or not APPID.fullmatch(appid):raise ValueError("Steam AppID")
            rows.append({"appid":appid,"title":clean(item["title"],256)})
        elif projection=="modrinth":
            if set(item)!={"id","slug","title","project_type"}:raise ValueError("mod project projection schema")
            if not isinstance(item["id"],str) or not re.fullmatch(r"[A-Za-z0-9]{6,32}",item["id"]):raise ValueError("mod project identity")
            if not isinstance(item["slug"],str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}",item["slug"]):raise ValueError("mod project slug")
            if item["project_type"] not in {"mod","modpack","resourcepack","shader","plugin","datapack","project"}:
                raise ValueError("mod project type")
            rows.append({**item,"title":clean(item["title"],256)})
        elif projection=="locator":
            if set(item)!={"url","title","kind","subject"}:raise ValueError("source projection schema")
            url,title,kind,subject=_schema_row(item["url"],item["title"],item["kind"],item["subject"])
            rows.append({"url":url,"title":title,"kind":kind,"subject":subject})
        else:raise ValueError("projection adapter")
    return rows

def project(item,projection):
    if projection=="steam_seed":
        yield _schema_row("https://store.steampowered.com/app/"+item["appid"]+"/",item["title"],"storefront","steam:"+item["appid"])
    elif projection=="steam":
        # Exactly existing provider route families; no fabricated AppIDs.
        for provider,kind,label,route,_ in STEAM_ROUTES:
            yield _schema_row(route.format(id=item["appid"]),(item["title"]+" · "+label)[:256],kind,"steam:"+item["appid"])
    elif projection=="modrinth":
        kind={"mod":"mod_project_readme","modpack":"mod_pack_manifest","resourcepack":"mod_texture_pack",
              "shader":"mod_shader_pack","plugin":"mod_plugin_manifest","datapack":"mod_project_readme",
              "project":"mod_project_readme"}[item["project_type"]]
        base="https://modrinth.com/"+item["project_type"]+"/"+item["slug"] if item["project_type"]!="project" else "https://modrinth.com/project/"+item["id"]
        for url,k,label in ((base,kind,"project"),(base+"/versions","mod_project_releases","versions")):
            yield _schema_row(url,(item["title"]+" · "+label)[:256],k,"modrinth:"+item["id"])
    else:
        yield _schema_row(item["url"],item["title"],item["kind"],item["subject"])

class LeadGraph:
    def __init__(self,path):
        self.corpus=GameCorpus(path);self.path=self.corpus.path

    @contextmanager
    def _db(self):
        with self.corpus._db() as db:
            db.executescript(SCHEMA)
            yield db

    def configure(self,scope,*,enabled,acknowledged):
        if type(enabled) is not bool or acknowledged is not True:raise ValueError("metadata-only acknowledgement")
        owner=owner_key(scope);now=int(time.time())
        if enabled:_quota_disk(self.path)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                exists=db.execute("SELECT 1 FROM lead_owner WHERE owner=?",(owner,)).fetchone()
                if not exists and db.execute("SELECT COUNT(*) FROM lead_owner").fetchone()[0]>=MAX_BOOTSTRAP_OWNERS:
                    raise CatalogueHeld("lead owner quota")
                db.execute("""INSERT INTO lead_owner(owner,scope_json,enabled,due) VALUES(?,?,?,?)
                    ON CONFLICT(owner) DO UPDATE SET enabled=excluded.enabled,due=excluded.due""",
                    (owner,json.dumps(scope,sort_keys=True),int(enabled),now))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return self.status(scope)

    def _enabled(self,db,owner):
        row=db.execute("SELECT * FROM lead_owner WHERE owner=?",(owner,)).fetchone()
        if row is None or not row["enabled"]:raise CatalogueHeld("lead expansion disabled")
        return row

    def _add(self,db,owner,row,*,parent,relation,witness,now,snapshot=None):
        url,title,kind,subject=row
        if relation not in RELATIONS:raise ValueError("lead relation")
        witness=_id(witness);identifier=lead_id(url)
        if parent!=ZERO:
            _id(parent)
            if not db.execute("SELECT 1 FROM lead_nodes WHERE owner=? AND id=?",(owner,parent)).fetchone():
                raise ValueError("lead parent not owned")
        caps=self._enabled(db,owner)
        node=db.execute("SELECT id FROM lead_nodes WHERE owner=? AND id=?",(owner,identifier)).fetchone()
        spec=SOURCE_CLASSES[kind]
        lane=lead_lane(identifier)
        lane_counts=_lane_counts(db,owner,lane)
        if node is None:
            if caps["nodes"]>=MAX_NODES or lane_counts["nodes"]>=NODES_PER_LANE:raise CatalogueHeld("lead node quota")
            db.execute("""INSERT INTO lead_nodes(owner,id,url,host,title,kind,family,first_seen,last_seen,next_review,observations,state)
                VALUES(?,?,?,?,?,?,?,?,?,?,0,'candidate')""",
                (owner,identifier,url,urlsplit(url).hostname,title,kind,spec.family,now,now,now))
            db.execute("INSERT INTO lead_fts(owner,id,title,url,kind,family) VALUES(?,?,?,?,?,?)",
                (owner,identifier,title,url,kind,spec.family))
            db.execute("UPDATE lead_owner SET nodes=nodes+1 WHERE owner=?",(owner,))
            db.execute("UPDATE lead_lane_counts SET nodes=nodes+1 WHERE owner=? AND lane=?",(owner,lane))
        eid=digest([parent,identifier,relation,subject,kind,title,witness,snapshot])
        edge=db.execute("SELECT 1 FROM lead_edges WHERE owner=? AND id=?",(owner,eid)).fetchone()
        if edge is None:
            if caps["edges"]>=MAX_EDGES or lane_counts["edges"]>=EDGES_PER_LANE:raise CatalogueHeld("lead evidence quota")
            db.execute("INSERT INTO lead_edges VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (owner,eid,parent,identifier,relation,subject,kind,title,witness,snapshot,now,now))
            db.execute("UPDATE lead_owner SET edges=edges+1 WHERE owner=?",(owner,))
            db.execute("UPDATE lead_lane_counts SET edges=edges+1 WHERE owner=? AND lane=?",(owner,lane))
            db.execute("UPDATE lead_nodes SET observations=observations+1,last_seen=MAX(last_seen,?) WHERE owner=? AND id=?",
                (now,owner,identifier))
        else:
            db.execute("UPDATE lead_edges SET last_seen=MAX(last_seen,?) WHERE owner=? AND id=?",(now,owner,eid))
            db.execute("UPDATE lead_nodes SET last_seen=MAX(last_seen,?) WHERE owner=? AND id=?",(now,owner,identifier))
        if kind in DATASET_KINDS:
            db.execute("""INSERT INTO lead_dataset_candidates VALUES(?,?,?,?)
                ON CONFLICT(owner,lead) DO UPDATE SET last_seen=MAX(last_seen,excluded.last_seen)""",
                (owner,identifier,now,now))
        return identifier

    def status(self,scope):
        owner=owner_key(scope);revision,seed=bootstrap_inventory()
        with self._db() as db:
            record=db.execute("""SELECT enabled,bootstrap_revision,bootstrap_cursor,bootstrapped,nodes,edges,snapshots,due
                FROM lead_owner WHERE owner=?""",(owner,)).fetchone()
        result=dict(record) if record else {"enabled":0,"bootstrap_revision":None,"bootstrap_cursor":0,"bootstrapped":0,"nodes":0,"edges":0,"snapshots":0,"due":0}
        return {**result,"bootstrap_target_rows":len(seed),"available_seed_revision":revision,
                "growth_floor":147020,"growth_floor_met":result["nodes"]>=147020,
                "architecture_node_cap":MAX_NODES,"architecture_evidence_cap":MAX_EDGES,
                "logical_quota_lanes":LEAD_LANES,"physical_graph_sharding":False,
                "network_authorized":False,"physical_capacity_verified":False}

    def bootstrap_pulse(self):
        revision,inventory=bootstrap_inventory();now=int(time.time())
        _quota_disk(self.path)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("""SELECT * FROM lead_owner WHERE enabled=1 AND due<=?
                    AND (bootstrap_revision IS NULL OR bootstrap_revision<>? OR bootstrapped=0)
                    ORDER BY due,owner LIMIT 1""",(now,revision)).fetchone()
                if row is None:
                    db.execute("COMMIT");return {"processed":0,"network_executed":False}
                owner=row["owner"]
                if owner_key(json.loads(row["scope_json"]))!=owner:raise ValueError("lead owner witness")
                offset=row["bootstrap_cursor"] if row["bootstrap_revision"]==revision else 0
                selected=inventory[offset:offset+MAX_SEED_BATCH]
                for url,title,kind,subject,relation,source_revision,source_id in selected:
                    # Some source labels are long across two fields.
                    self._add(db,owner,_schema_row(url,title[:256],kind,subject),
                        parent=ZERO,relation=relation,witness=digest([source_revision,source_id]),now=now)
                cursor=offset+len(selected)
                db.execute("""UPDATE lead_owner SET bootstrap_revision=?,bootstrap_cursor=?,bootstrapped=?,due=?
                    WHERE owner=?""",(revision,cursor,int(cursor>=len(inventory)),now+1,owner))
                db.execute("COMMIT")
                return {"processed":len(selected),"bootstrap_complete":cursor>=len(inventory),"network_executed":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def begin(self,scope,*,target_id,projection,source_sha,expected_rows,rights_ref,grant_seconds,acknowledged):
        owner=owner_key(scope);now=int(time.time())
        dynamic=None
        if isinstance(target_id,str) and target_id.startswith("dynamic-"):
            with self._db() as db:
                dynamic=db.execute("""SELECT t.*,n.url,n.title FROM lead_dynamic_targets t
                    JOIN lead_nodes n ON n.owner=t.owner AND n.id=t.lead
                    WHERE t.owner=? AND t.id=? AND t.enabled=1 AND t.expires_at>?""",
                    (owner,target_id,now)).fetchone()
            if not dynamic:raise LookupError("dynamic dataset target not authorized for metadata import")
            if projection!=dynamic["projection"] or rights_ref!=dynamic["rights_ref"]:
                raise ValueError("dynamic target projection or rights changed")
            registry_revision=dynamic["revision"]
            item={"id":target_id,"url":dynamic["url"],"access":"policy_review",
                  "adapter":"steam_csv" if projection=="steam" else "modrinth_json" if projection=="modrinth" else "directory"}
            grant_seconds=min(_int(grant_seconds,900,MAX_GRANT),dynamic["expires_at"]-now)
        else:
            item=target(target_id);registry_revision,_=_library()
        if acknowledged is not True:raise ValueError("public dataset metadata rights acknowledgement")
        if item["access"] in {"credential_required","noncommercial_only","landing_only"}:
            raise ValueError("target requires separate source review or explicit export target")
        if projection not in {"steam","steam_seed","modrinth","locator"}:raise ValueError("dataset projection")
        if projection=="steam_seed":
            from core.dragon_bundled_steam_leads import summary as bundle_summary,TARGET
            bundle=bundle_summary()
            if target_id!=TARGET or source_sha!=bundle["bundle_revision"] or expected_rows!=bundle["title_identity_candidates"]:
                raise ValueError("bundle target witness")
        if projection in {"steam","steam_seed"} and item["adapter"] not in {"steam_csv","steam_json"}:raise ValueError("Steam dataset target")
        if projection=="modrinth" and item["adapter"]!="modrinth_json":raise ValueError("mod dataset target")
        source_sha=_id(source_sha);expected_rows=_int(expected_rows,1,MAX_SNAPSHOT_ROWS)
        rights_ref=clean(rights_ref,128);grant_seconds=_int(grant_seconds,900,MAX_GRANT)
        owner=owner_key(scope);now=int(time.time())
        sid=digest([target_id,registry_revision,projection,PROJECTION_VERSION,source_sha,expected_rows,rights_ref])
        _quota_disk(self.path)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                caps=self._enabled(db,owner)
                if dynamic and not db.execute("""SELECT 1 FROM lead_dynamic_targets WHERE owner=? AND id=? AND revision=? AND enabled=1 AND expires_at>?""",
                    (owner,target_id,registry_revision,now+grant_seconds-1)).fetchone():raise CatalogueHeld("dynamic target superseded")
                prior=db.execute("SELECT * FROM lead_snapshots WHERE owner=? AND id=?",(owner,sid)).fetchone()
                if prior:
                    if prior["state"]=="revoked":raise CatalogueHeld("dataset snapshot revoked")
                    db.execute("COMMIT");return self.snapshot(scope,sid)
                if caps["snapshots"]>=MAX_SNAPSHOTS:raise CatalogueHeld("lead snapshot quota")
                root=self._add(db,owner,_schema_row(item["url"],item["id"],"dataset_manifest","dataset:"+target_id),
                    parent=ZERO,relation="dataset_target",witness=digest([registry_revision,target_id]),now=now)
                db.execute("""INSERT INTO lead_snapshots(owner,id,root,target_id,registry_revision,projection,
                    source_sha,rights_ref,expected_rows,chain,state,expires_at,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,'open',?,?)""",
                    (owner,sid,root,target_id,registry_revision,projection,source_sha,rights_ref,expected_rows,ZERO,now+grant_seconds,now))
                db.execute("UPDATE lead_owner SET snapshots=snapshots+1 WHERE owner=?",(owner,))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return self.snapshot(scope,sid)

    def snapshot(self,scope,sid):
        owner=owner_key(scope);sid=_id(sid)
        with self._db() as db:
            row=db.execute("""SELECT id,root,target_id,registry_revision,projection,source_sha,expected_rows,rows,
                next_page,chain,state,expires_at,created_at,sealed_at FROM lead_snapshots WHERE owner=? AND id=?""",(owner,sid)).fetchone()
        if row is None:raise LookupError("lead snapshot missing")
        return {**dict(row),"snapshot_id":sid,"candidate_only":True,"network_authorized":False,"source_verified":False}

    def append(self,scope,sid,*,ordinal,raw,sha256,previous_chain):
        owner=owner_key(scope);sid=_id(sid);ordinal=_int(ordinal,0,MAX_SNAPSHOT_ROWS)
        sha256=_id(sha256);previous_chain=_id(previous_chain)
        if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_PAGE_BYTES or hashlib.sha256(raw).hexdigest()!=sha256:
            raise ValueError("lead page digest")
        _quota_disk(self.path);now=int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                snap=db.execute("SELECT * FROM lead_snapshots WHERE owner=? AND id=?",(owner,sid)).fetchone()
                if snap is None:raise LookupError("lead snapshot missing")
                if snap["state"]=="revoked" or snap["expires_at"]<=now:raise CatalogueHeld("lead snapshot grant expired or revoked")
                prior=db.execute("SELECT * FROM lead_snapshot_pages WHERE owner=? AND snapshot=? AND ordinal=?",(owner,sid,ordinal)).fetchone()
                if prior:
                    expected=digest([previous_chain,ordinal,sha256,prior["row_count"]])
                    if prior["digest"]!=sha256 or prior["chain"]!=expected:raise CatalogueHeld("lead snapshot replay differs")
                    db.execute("COMMIT")
                    return {"ordinal":ordinal,"rows":prior["row_count"],"chain":prior["chain"],"replayed":True,"network_authorized":False}
                if snap["state"]!="open" or snap["next_page"]!=ordinal or snap["chain"]!=previous_chain:
                    raise CatalogueHeld("lead snapshot ordering")
                bundle_witness=None
                if snap["projection"]=="steam_seed":
                    from core.dragon_bundled_steam_leads import normalized_page,summary as bundle_summary
                    expected,bundle_witness=normalized_page(ordinal)
                    if snap["source_sha"]!=bundle_summary()["bundle_revision"] or expected!=raw:
                        raise CatalogueHeld("bundled dataset page differs from pinned source")
                items=parse_page(raw,snap["projection"])
                if snap["rows"]+len(items)>snap["expected_rows"]:raise CatalogueHeld("lead snapshot row budget")
                chain=digest([previous_chain,ordinal,sha256,len(items)])
                for ix,item in enumerate(items):
                    witness=digest([sid,ordinal,sha256,bundle_witness,ix,item])
                    for row in project(item,snap["projection"]):
                        child=self._add(db,owner,row,parent=snap["root"],relation="dataset_projection",witness=witness,now=now,snapshot=sid)
                        if snap["projection"]=="steam_seed":
                            job=digest(["bundle-steam-app",child,item["appid"],sid])
                            db.execute("INSERT OR IGNORE INTO lead_expand_jobs VALUES(?,?,?,?,?,?,'queued',?,?)",
                                (owner,job,child,item["appid"],item["title"],witness,now,sid))
                db.execute("INSERT INTO lead_snapshot_pages VALUES(?,?,?,?,?,?)",(owner,sid,ordinal,sha256,len(items),chain))
                db.execute("UPDATE lead_snapshots SET rows=rows+?,next_page=next_page+1,chain=? WHERE owner=? AND id=?",
                    (len(items),chain,owner,sid))
                db.execute("COMMIT")
                return {"ordinal":ordinal,"rows":len(items),"chain":chain,"replayed":False,"network_authorized":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def seal(self,scope,sid,chain):
        owner=owner_key(scope);sid=_id(sid);chain=_id(chain);now=int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                row=db.execute("SELECT * FROM lead_snapshots WHERE owner=? AND id=?",(owner,sid)).fetchone()
                if row is None:raise LookupError("lead snapshot missing")
                if row["state"]=="revoked" or row["expires_at"]<=now or row["rows"]!=row["expected_rows"] or row["chain"]!=chain:
                    raise CatalogueHeld("lead snapshot seal incomplete")
                if row["state"]=="open":
                    db.execute("UPDATE lead_snapshots SET state='sealed',sealed_at=? WHERE owner=? AND id=?",(now,owner,sid))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return self.snapshot(scope,sid)

    def revoke(self,scope,sid):
        # Locator-only leads are retained as historical candidate metadata.
        # Revocation stops future imports, and evidence browsing reports status.
        owner=owner_key(scope);sid=_id(sid)
        with self._db() as db:
            result=db.execute("UPDATE lead_snapshots SET state='revoked',expires_at=0 WHERE owner=? AND id=?",(owner,sid))
        return {"revoked":result.rowcount==1,"candidate_locators_retained":True,"network_authorized":False}

    def dataset_candidates(self,scope,*,after=None,limit=32):
        owner=owner_key(scope);_int(limit,1,100)
        with self._db() as db:
            rows=db.execute("""SELECT n.id,n.url,n.title,n.kind,c.first_seen,c.last_seen,
                t.id AS target_id,t.projection,t.enabled,t.expires_at FROM lead_dataset_candidates c
                JOIN lead_nodes n ON n.owner=c.owner AND n.id=c.lead
                LEFT JOIN lead_dynamic_targets t ON t.owner=c.owner AND t.lead=c.lead
                WHERE c.owner=? AND c.lead>? ORDER BY c.lead LIMIT ?""",
                (owner,_id(after) if after else "",limit+1)).fetchall()
        return {"candidates":[{**dict(r),"network_authorized":False,"source_verified":False} for r in rows[:limit]],
            "next_cursor":rows[limit-1]["id"] if len(rows)>limit else None,
            "network_authorized":False}

    def register_target(self,scope,lead,*,projection,rights_ref,grant_seconds,enabled,acknowledged):
        """An owner can add a newly found dataset to the live library.
        Registration is a finite permission to import locator-only metadata,
        never an authorization to fetch the URL or promote its contents.
        """
        if acknowledged is not True or type(enabled) is not bool:raise ValueError("explicit metadata acknowledgement")
        if projection not in {"steam","modrinth","locator"}:raise ValueError("dataset projection")
        owner=owner_key(scope);lead=_id(lead);rights_ref=clean(rights_ref,128)
        grant_seconds=_int(grant_seconds,900,MAX_GRANT);now=int(time.time())
        identifier="dynamic-"+digest([lead,"dataset"])[:56]
        revision=digest([identifier,projection,rights_ref,now,enabled])
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                row=db.execute("""SELECT n.url,n.state FROM lead_dataset_candidates c JOIN lead_nodes n
                    ON n.owner=c.owner AND n.id=c.lead WHERE c.owner=? AND c.lead=?""",(owner,lead)).fetchone()
                if row is None:raise LookupError("dataset candidate missing")
                if enabled and row["state"]!="candidate":raise CatalogueHeld("dataset lead not active")
                previous=db.execute("SELECT lead,revision FROM lead_dynamic_targets WHERE owner=? AND id=?",(owner,identifier)).fetchone()
                if previous and previous["lead"]!=lead:raise CatalogueHeld("dataset target collision")
                if not previous and db.execute("SELECT COUNT(*) FROM lead_dynamic_targets WHERE owner=?",(owner,)).fetchone()[0]>=MAX_DYNAMIC_TARGETS:
                    raise CatalogueHeld("dynamic target quota")
                db.execute("""INSERT INTO lead_dynamic_targets VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(owner,id) DO UPDATE SET projection=excluded.projection,revision=excluded.revision,
                    rights_ref=excluded.rights_ref,enabled=excluded.enabled,reviewed_at=excluded.reviewed_at,expires_at=excluded.expires_at""",
                    (owner,identifier,lead,projection,revision,rights_ref,int(enabled),now,now+grant_seconds if enabled else 0))
                # A changed or withdrawn grant never perpetuates open imports.
                db.execute("""UPDATE lead_snapshots SET state='revoked',expires_at=0 WHERE owner=?
                    AND target_id=? AND state='open' AND registry_revision<>?""",(owner,identifier,revision))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"target_id":identifier,"lead_id":lead,"revision":revision,"enabled":enabled,
                "expires_at":now+grant_seconds if enabled else 0,"network_authorized":False,"source_verified":False}

    def feed_page(self,scope,*,url,raw,adapter,options,subscription_id):
        """Mirror already-approved feed proposals into graph, no extra fetch."""
        from core.dragon_release_discovery import parse_manifest,parse_steam_catalogue,parse_release_feed
        owner=owner_key(scope);now=int(time.time());_id(subscription_id)
        try:
            with self._db() as db:
                row=db.execute("SELECT enabled FROM lead_owner WHERE owner=?",(owner,)).fetchone()
                if row is None or not row["enabled"]:return {"enabled":False}
        except sqlite3.Error:
            raise
        if adapter=="manifest":proposals=parse_manifest(raw)
        elif adapter=="steam":proposals=parse_steam_catalogue(raw)
        elif adapter=="rss_atom":proposals=parse_release_feed(raw,**options)
        else:raise ValueError("lead feed adapter")
        _quota_disk(self.path)
        # A normalized feed page can be larger than a snapshot projection page,
        # but existing parsers enforce their own byte and proposal limits.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                root=self._add(db,owner,_schema_row(url,"Authorized feed metadata","release_feed","subscription:"+subscription_id),
                    parent=ZERO,relation="dataset_target",witness=digest([subscription_id,url]),now=now)
                fingerprint=hashlib.sha256(raw).hexdigest()
                for item in proposals:
                    witness=digest([subscription_id,fingerprint,item.event_key])
                    child=self._add(db,owner,_schema_row(item.source,item.title,item.kind,(item.namespace+":"+item.external_id)[:256]),
                        parent=root,relation="feed_discovery",witness=witness,now=now)
                    if adapter=="steam" and item.namespace=="steam" and APPID.fullmatch(item.external_id):
                        job=digest(["steam-app",child,item.external_id,item.title])
                        db.execute("INSERT OR IGNORE INTO lead_expand_jobs VALUES(?,?,?,?,?,?,'queued',?,NULL)",
                            (owner,job,child,item.external_id,item.title,witness,now))
                db.execute("COMMIT");return {"enabled":True,"proposals":len(proposals),"network_authorized":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def bundle_status(self,scope):
        from core.dragon_bundled_steam_leads import summary as bundle_summary,TARGET
        summary=bundle_summary();owner=owner_key(scope)
        with self._db() as db:
            row=db.execute("""SELECT id,rows,expected_rows,next_page,state,expires_at FROM lead_snapshots
                WHERE owner=? AND target_id=? AND projection='steam_seed' AND source_sha=?
                ORDER BY created_at DESC,id LIMIT 1""",(owner,TARGET,summary["bundle_revision"])).fetchone()
        return {**summary,"snapshot":dict(row) if row else None,
                "snapshot_identity_candidates_ingested":row["rows"] if row else 0,
                "growth_floor_met":self.status(scope)["growth_floor_met"]}

    def enable_bundle(self,scope,*,rights_ref,grant_seconds,acknowledged):
        from core.dragon_bundled_steam_leads import summary as bundle_summary,TARGET
        info=bundle_summary();grant_seconds=_int(grant_seconds,900,MAX_GRANT)
        if acknowledged is not True:raise ValueError("separate bundle rights acknowledgement required")
        result=self.begin(scope,target_id=TARGET,projection="steam_seed",source_sha=info["bundle_revision"],
            expected_rows=info["title_identity_candidates"],rights_ref=rights_ref,grant_seconds=grant_seconds,acknowledged=True)
        # Renewal is explicit; reusing the same reviewed source identity
        # extends the finite grant without discarding the committed cursor.
        owner=owner_key(scope);now=int(time.time())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                db.execute("""UPDATE lead_snapshots SET expires_at=? WHERE owner=? AND id=?
                    AND state IN ('open','sealed') AND source_sha=?""",
                    (now+grant_seconds,owner,result["id"],info["bundle_revision"]))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return self.bundle_status(scope)

    def bundle_pulse(self):
        """Replay-safe bundled source admission (512 identity rows per pulse)."""
        from core.dragon_bundled_steam_leads import summary as bundle_summary,normalized_page,TARGET
        info=bundle_summary();now=int(time.time());_quota_disk(self.path)
        with self._db() as db:
            row=db.execute("""SELECT s.id,o.scope_json,s.owner FROM lead_snapshots s JOIN lead_owner o
                ON o.owner=s.owner WHERE o.enabled=1 AND s.target_id=? AND s.projection='steam_seed'
                AND s.source_sha=? AND s.state='open' AND s.expires_at>? ORDER BY s.next_page,s.owner,s.id LIMIT 1""",
                (TARGET,info["bundle_revision"],now)).fetchone()
        if row is None:return {"processed":0,"network_executed":False}
        scope=json.loads(row["scope_json"])
        if owner_key(scope)!=row["owner"]:raise ValueError("bundle owner witness")
        processed=0
        for _ in range(BUNDLE_PAGES_PER_PULSE):
            snap=self.snapshot(scope,row["id"])
            if snap["state"]!="open":break
            if snap["rows"]==snap["expected_rows"]:
                self.seal(scope,snap["id"],snap["chain"])
                break
            raw,witness=normalized_page(snap["next_page"])
            receipt=self.append(scope,snap["id"],ordinal=snap["next_page"],raw=raw,
                sha256=hashlib.sha256(raw).hexdigest(),previous_chain=snap["chain"])
            if not receipt["replayed"]:processed+=receipt["rows"]
        return {"processed":processed,"network_executed":False}

    def catalogue_pulse(self):
        """Consume the transactional canonical-release outbox exactly once."""
        from core.dragon_release_queue import ReleaseQueue
        now=int(time.time());_quota_disk(self.path)
        with ReleaseQueue(self.path)._db() as db:pass
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            counts={"processed":0,"held":0,"network_executed":False}
            try:
                jobs=db.execute("""SELECT j.owner,j.id,j.payload,j.batch,o.scope_json FROM lead_release_outbox q
                    JOIN release_jobs j ON j.owner=q.owner AND j.id=q.id
                    JOIN lead_owner o ON o.owner=q.owner
                    WHERE q.state='queued' AND o.enabled=1 ORDER BY q.created_at,q.owner,q.id LIMIT 64""").fetchall()
                for job in jobs:
                    db.execute("SAVEPOINT lead_catalogue_row")
                    try:
                        if owner_key(json.loads(job["scope_json"]))!=job["owner"]:raise ValueError("catalogue scope")
                        item=json.loads(job["payload"])
                        witness=digest([job["batch"],job["id"],item])
                        url=source_url(item["source"]);title=clean(item["title"],256)
                        child=self._add(db,job["owner"],_schema_row(url,title,item["kind"],
                            (item["namespace"]+":"+item["external_id"])[:256]),
                            parent=ZERO,relation="catalogue_observation",witness=witness,now=now)
                        if (item["namespace"]=="steam" and APPID.fullmatch(item["external_id"])
                            and _locator(url)==_locator("https://store.steampowered.com/app/"+item["external_id"]+"/")):
                            job_id=digest(["steam-app",child,item["external_id"],title])
                            db.execute("INSERT OR IGNORE INTO lead_expand_jobs VALUES(?,?,?,?,?,?,'queued',?,NULL)",
                                (job["owner"],job_id,child,item["external_id"],title,witness,now))
                        db.execute("UPDATE lead_release_outbox SET state='done' WHERE owner=? AND id=?",
                            (job["owner"],job["id"]))
                        db.execute("RELEASE lead_catalogue_row")
                        counts["processed"]+=1
                    except (ValueError,TypeError,KeyError,CatalogueHeld):
                        db.execute("ROLLBACK TO lead_catalogue_row")
                        db.execute("RELEASE lead_catalogue_row")
                        db.execute("UPDATE lead_release_outbox SET state='held' WHERE owner=? AND id=?",
                            (job["owner"],job["id"]))
                        counts["held"]+=1
                db.execute("COMMIT")
                return counts
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def expansion_pulse(self):
        """Expand feed-supplied AppIDs without guessing identifiers or fetching."""
        now=int(time.time());_quota_disk(self.path)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                jobs=db.execute("""SELECT j.* FROM lead_expand_jobs j JOIN lead_owner o ON o.owner=j.owner
                    WHERE j.state='queued' AND o.enabled=1 AND (j.snapshot IS NULL OR EXISTS(
                    SELECT 1 FROM lead_snapshots s WHERE s.owner=j.owner AND s.id=j.snapshot AND s.state IN ('open','sealed') AND s.expires_at>?))
                    ORDER BY j.created_at,j.owner,j.id LIMIT 16""",(now,)).fetchall()
                processed=0;held=0
                for job in jobs:
                    db.execute("SAVEPOINT lead_expansion_row")
                    try:
                        if not APPID.fullmatch(job["appid"]):raise ValueError("expansion identity")
                        for row in project({"appid":job["appid"],"title":job["title"]},"steam"):
                            self._add(db,job["owner"],row,parent=job["parent"],relation="dataset_projection" if job["snapshot"] else "feed_discovery",
                                witness=job["witness"],now=now,snapshot=job["snapshot"])
                        state="done";processed+=1
                    except (ValueError,TypeError,KeyError,CatalogueHeld):
                        db.execute("ROLLBACK TO lead_expansion_row")
                        state="held";held+=1
                    db.execute("RELEASE lead_expansion_row")
                    db.execute("UPDATE lead_expand_jobs SET state=? WHERE owner=? AND id=?",
                        (state,job["owner"],job["id"]))
                db.execute("COMMIT")
                return {"processed":processed,"held":held,"network_executed":False}
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def page(self,scope,*,q=None,family=None,host=None,state="candidate",after=None,limit=32,due_only=False):
        owner=owner_key(scope);_int(limit,1,100)
        if state not in STATES or type(due_only) is not bool:raise ValueError("lead filter")
        if family is not None and family not in {s.family for s in SOURCE_CLASSES.values()}:raise ValueError("lead family")
        if host is not None:
            host=clean(host,253).lower()
            if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",host):raise ValueError("lead host")
        terms=_tokens(q);fingerprint=digest([owner,terms,family,host,state,due_only]);lower=""
        if after is not None:
            if not isinstance(after,str) or len(after)!=129 or not after.startswith(fingerprint+":"):
                raise ValueError("lead cursor filter")
            lower=_id(after[65:])
        clauses=["n.owner=?","n.state=?","n.id>?"];values=[owner,state,lower]
        if family:clauses.append("n.family=?");values.append(family)
        if host:clauses.append("n.host=?");values.append(host)
        cutoff=int(time.time()) if due_only else None
        if due_only:clauses.append("n.next_review<=?");values.append(cutoff)
        sql="SELECT n.* FROM lead_nodes n"
        if terms:
            sql+=" JOIN lead_fts f ON f.owner=n.owner AND f.id=n.id"
            clauses.append("lead_fts MATCH ?")
            values.append('owner:"'+owner+'" AND '+' AND '.join('"'+term+'"' for term in terms))
        sql+=" WHERE "+" AND ".join(clauses)+" ORDER BY n.id LIMIT ?";values.append(limit+1)
        physical=False
        with self._db() as db:
            import os
            if terms and os.getenv("SKL_DRAGON_LEAD_INDEX_ROOT","").strip():
                from core.dragon_lead_index_shards import lookup,IndexHeld
                from core.dragon_owner_shards import ShardHeld
                db.execute("BEGIN")
                try:
                    rows=lookup(db,owner,terms,state=state,family=family,host=host,lower=lower,cutoff=cutoff,limit=limit)
                    db.execute("COMMIT");physical=True
                except (IndexHeld,ShardHeld,sqlite3.Error,OSError,ValueError):
                    if db.in_transaction:db.execute("ROLLBACK")
            if not physical:
                deadline=time.monotonic()+3
                db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
                rows=db.execute(sql,values).fetchall()
        return {"leads":[{**dict(r),"verified":False,"network_authorized":False} for r in rows[:limit]],
            "physical_search_shards_used":physical,
            "next_cursor":fingerprint+":"+rows[limit-1]["id"] if len(rows)>limit else None,
            "candidate_only":True,"network_authorized":False}

    def edges(self,scope,lead,*,direction="children",after=None,limit=32):
        owner=owner_key(scope);lead=_id(lead);_int(limit,1,100)
        if direction not in {"children","parents"}:raise ValueError("lead edge direction")
        field="parent" if direction=="children" else "child"
        lower=_id(after) if after else ""
        physical=False
        with self._db() as db:
            import os
            if os.getenv("SKL_DRAGON_LEAD_EDGE_ROOT","").strip():
                from core.dragon_lead_edge_shards import lookup,EdgeHeld
                from core.dragon_owner_shards import ShardHeld
                db.execute("BEGIN")
                try:
                    if not db.execute("SELECT 1 FROM lead_nodes WHERE owner=? AND id=?",(owner,lead)).fetchone():raise LookupError("lead missing")
                    rows=lookup(db,owner,lead,field=field,lower=lower,limit=limit)
                    db.execute("COMMIT");physical=True
                except (EdgeHeld,ShardHeld,sqlite3.Error,OSError,ValueError):
                    if db.in_transaction:db.execute("ROLLBACK")
            if not physical:
                if not db.execute("SELECT 1 FROM lead_nodes WHERE owner=? AND id=?",(owner,lead)).fetchone():raise LookupError("lead missing")
                rows=db.execute("SELECT e.*,s.state AS snapshot_state,s.expires_at AS snapshot_expires_at FROM lead_edges e LEFT JOIN lead_snapshots s ON s.owner=e.owner AND s.id=e.snapshot WHERE e.owner=? AND e."+field+"=? AND e.id>? ORDER BY e.id LIMIT ?",
                    (owner,lead,lower,limit+1)).fetchall()
        return {"edges":[dict(r) for r in rows[:limit]],"next_cursor":rows[limit-1]["id"] if len(rows)>limit else None,
                "physical_edge_shards_used":physical,
                "candidate_only":True,"network_authorized":False}

    def review(self,scope,lead,*,decision,reason,operation,interval_seconds=604800):
        owner=owner_key(scope);lead=_id(lead);reason=clean(reason,512);operation=clean(operation,128)
        if decision not in {"candidate","held","retired"}:raise ValueError("lead disposition")
        interval_seconds=_int(interval_seconds,900,90*86400);now=int(time.time())
        identity=digest([lead,operation]);witness=digest([decision,reason,interval_seconds])
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._enabled(db,owner)
                prior=db.execute("SELECT decision,reason FROM lead_review_events WHERE owner=? AND id=?",(owner,identity)).fetchone()
                if prior:
                    if prior["decision"]!=decision or prior["reason"]!=witness:raise CatalogueHeld("lead review replay differs")
                else:
                    updated=db.execute("UPDATE lead_nodes SET state=?,next_review=? WHERE owner=? AND id=?",
                        (decision,now+interval_seconds,owner,lead))
                    if updated.rowcount!=1:raise LookupError("lead missing")
                    db.execute("INSERT INTO lead_review_events VALUES(?,?,?,?,?,?)",(owner,identity,lead,decision,witness,now))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"lead_id":lead,"decision":decision,"verified":False,"network_authorized":False}
