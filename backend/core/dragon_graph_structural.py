"""Durable independent structural graph admission for canonical release jobs.

The root serializes bounded reservation/publication, not physical node/edge
work. Each lane commits canonical rows and an exact replay receipt under a
shared root policy lock. A pending plan fences coordinated graph access until
all lane receipts and rows are verified and the root settlement commits.
No caller-supplied locator, external fetch, or new source grant enters here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import time
from urllib.parse import urlsplit

from core import dragon_graph_authority as a
from core.dragon_owner_shards import _open,_private,ShardHeld
from core.dragon_hoarder_bulk import owner_key
from core.dragon_game_corpus import CatalogueHeld

VERSION=1
MAX_JOBS=32
MAX_BOOTSTRAP_ROWS=128
MAX_RECORDS=512
MAX_PLAN_BYTES=4*1024**2
WORKERS=4
ROOT="""CREATE TABLE dragon_graph_structural(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL,epoch TEXT NOT NULL,
 sequence INTEGER NOT NULL CHECK(sequence>=0),state TEXT NOT NULL CHECK(state IN ('idle','pending')),
 plan TEXT NOT NULL,sha256 TEXT NOT NULL
)"""
RECEIPT="""CREATE TABLE structural_receipt(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),sequence INTEGER NOT NULL,
 plan_sha TEXT NOT NULL,lane_sha TEXT NOT NULL
)"""
PROTECTED=("lead_owner","lead_node_directory","lead_lane_counts","lead_dataset_candidates",
           "lead_dynamic_targets","lead_expand_jobs","lead_review_events")


def enabled(db):
    if not a.active(db):return False
    if not a._table(db,"dragon_graph_structural"):return False
    marker=db.execute("SELECT version,epoch,state FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
    if not marker or marker[0]!=VERSION or marker[2] not in ("idle","pending"):
        raise a.GraphHeld("structural journal marker differs")
    layout=json.loads(db.execute("SELECT layout FROM main.dragon_graph_authority WHERE singleton=1").fetchone()[0])
    if marker[1]!=layout.get("epoch"):raise a.GraphHeld("structural journal epoch differs")
    return True


def configured(root):
    path=Path(root).absolute()
    if not path.exists():return False
    db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5,isolation_level=None)
    try:return enabled(db)
    finally:db.close()


def guard(db):
    if a._table(db,"dragon_graph_structural"):
        if not enabled(db):raise a.GraphHeld("structural topology missing")
        if db.execute("SELECT state FROM main.dragon_graph_structural WHERE singleton=1").fetchone()[0]=="pending":
            raise a.GraphHeld("structural batch awaiting replay and settlement")


def _triggers(db):
    for table in PROTECTED:
        for event in ("INSERT","UPDATE","DELETE"):
            name="structural_hold_"+table+"_"+event.lower()
            db.execute("CREATE TRIGGER "+name+" BEFORE "+event+" ON "+table+
                       " WHEN EXISTS(SELECT 1 FROM dragon_graph_structural WHERE singleton=1 AND state='pending') "
                       "BEGIN SELECT RAISE(ABORT,'structural batch pending'); END")


def publish(db,epoch):
    db.execute(ROOT)
    db.execute("INSERT INTO main.dragon_graph_structural VALUES(1,?,?,0,'idle','','')",(VERSION,epoch))
    _triggers(db)


def install(root,*,offline_acknowledged=False):
    if offline_acknowledged is not True:raise a.GraphHeld("stop all graph writers")
    root=Path(root)
    with a._probe_connection(root) as db:
        if enabled(db):return {"installed":True,"replayed":True}
        db.execute("BEGIN IMMEDIATE")
        try:
            layout=a._layout(db,root)
            for i in range(a.LANES):
                alias=a._alias(i)
                db.execute(RECEIPT.replace("CREATE TABLE structural_receipt","CREATE TABLE "+alias+".structural_receipt",1))
            publish(db,layout["epoch"])
            a._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    return {"installed":True,"replayed":False,"lanes":a.LANES}


def _serialize(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)


def _sha(obj):
    return hashlib.sha256(_serialize(obj).encode()).hexdigest()


def _pending(db):
    if not enabled(db):raise a.GraphHeld("independent structural writers not installed")
    row=db.execute("SELECT sequence,state,plan,sha256 FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
    if row["state"]=="idle":return None
    raw=row["plan"]
    if not isinstance(raw,str) or not 1<=len(raw.encode())<=MAX_PLAN_BYTES or hashlib.sha256(raw.encode()).hexdigest()!=row["sha256"]:
        raise a.GraphHeld("structural journal witness differs")
    plan=json.loads(raw)
    if (not isinstance(plan,dict) or plan.get("sequence")!=row["sequence"] or plan.get("mode") not in {"catalogue","expansion","bootstrap"}
            or not isinstance(plan.get("lanes"),dict) or len(plan["lanes"])>a.LANES or not isinstance(plan.get("jobs"),list)
            or not 1<=len(plan["jobs"])<=MAX_JOBS):
        raise a.GraphHeld("structural journal shape differs")
    return plan,row["sha256"]


def _record(db,state,owner,identifier,table,columns,index):
    k=(owner,identifier)
    if k not in state:
        row=db.execute("SELECT "+",".join(columns)+" FROM "+a._alias(index)+"."+table+" WHERE owner=? AND id=?",
                       k).fetchone()
        value=list(row) if row else None
        state[k]=[value,deepcopy(value)]
    return state[k]


def _reserve_row(db,work,owner,row,parent,relation,witness,now):
    from core.dragon_lead_graph import (lead_id,digest,SOURCE_CLASSES,ZERO,DATASET_KINDS,
        _lane_counts,MAX_NODES,MAX_EDGES,NODES_PER_LANE,EDGES_PER_LANE)
    url,title,kind,subject=row
    identifier=lead_id(url);index=a.lane(identifier)
    if parent!=ZERO and not db.execute("SELECT 1 FROM main.lead_node_directory WHERE owner=? AND id=?",(owner,parent)).fetchone():
        raise ValueError("parent missing")
    caps=db.execute("SELECT nodes,edges,enabled FROM main.lead_owner WHERE owner=?",(owner,)).fetchone()
    if not caps or not caps["enabled"]:raise CatalogueHeld("owner disabled")
    counts=_lane_counts(db,owner,index)
    total=work["owner_deltas"].setdefault(owner,[0,0])
    local=work["deltas"].setdefault((owner,index),[0,0])
    node=_record(db,work["nodes"],owner,identifier,"nodes",a.NODE_COLUMNS,index)
    if node[1] is None:
        if caps["nodes"]+total[0]>=MAX_NODES or counts["nodes"]+local[0]>=NODES_PER_LANE:raise CatalogueHeld("node quota")
        node[1]=[owner,identifier,url,urlsplit(url).hostname,title,kind,SOURCE_CLASSES[kind].family,now,now,now,0,"candidate"]
        total[0]+=1;local[0]+=1
    elif node[1][2]!=url:raise CatalogueHeld("node identity conflict")
    eid=digest([parent,identifier,relation,subject,kind,title,witness,None])
    edge=_record(db,work["edges"],owner,eid,"edges",a.EDGE_COLUMNS,index)
    expected=[owner,eid,parent,identifier,relation,subject,kind,title,witness,None]
    if edge[1] is None:
        if caps["edges"]+total[1]>=MAX_EDGES or counts["edges"]+local[1]>=EDGES_PER_LANE:raise CatalogueHeld("edge quota")
        edge[1]=expected+[now,now]
        total[1]+=1;local[1]+=1;node[1][10]+=1
    elif edge[1][:10]!=expected:raise CatalogueHeld("edge identity conflict")
    else:edge[1][11]=max(edge[1][11],now)
    node[1][8]=max(node[1][8],now)
    if kind in DATASET_KINDS:work["candidates"].add((owner,identifier))
    return identifier


def reserve(root,mode):
    from core.dragon_lead_graph import (_schema_row,_locator,source_url,clean,digest,APPID,
                                       ZERO,project,_quota_disk,bootstrap_inventory)
    if mode not in {"catalogue","expansion","bootstrap"}:raise ValueError("structural mode")
    root=Path(root);_quota_disk(root)
    with a._probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            previous=_pending(db)
            if previous:
                db.execute("COMMIT");return previous
            seq=db.execute("SELECT sequence FROM main.dragon_graph_structural WHERE singleton=1").fetchone()[0]+1
            now=int(time.time())
            bootstrap=None
            if mode=="bootstrap":
                revision,inventory=bootstrap_inventory()
                record=db.execute("""SELECT * FROM lead_owner WHERE enabled=1 AND due<=?
                    AND (bootstrap_revision IS NULL OR bootstrap_revision<>? OR bootstrapped=0)
                    ORDER BY due,owner LIMIT 1""",(now,revision)).fetchone()
                if record is None:
                    db.execute("COMMIT");return None
                jobs=[]
            elif mode=="catalogue":
                jobs=db.execute("""SELECT j.owner,j.id,j.payload,j.batch,o.scope_json FROM lead_release_outbox q
                  JOIN release_jobs j ON j.owner=q.owner AND j.id=q.id
                  JOIN lead_owner o ON o.owner=q.owner
                  WHERE q.state='queued' AND j.state='done' AND o.enabled=1 ORDER BY q.created_at,q.owner,q.id LIMIT ?""",(MAX_JOBS,)).fetchall()
            else:
                # Grant-bearing jobs stay in the original atomic snapshot path.
                jobs=db.execute("""SELECT j.* FROM lead_expand_jobs j JOIN lead_owner o ON o.owner=j.owner
                  WHERE j.state='queued' AND j.snapshot IS NULL AND o.enabled=1
                  ORDER BY j.created_at,j.owner,j.id LIMIT 16""").fetchall()
            work={"nodes":{},"edges":{},"owner_deltas":{},"deltas":{},"candidates":set(),"expansions":[]}
            planned=[]
            if mode=="bootstrap":
                owner=record["owner"]
                if owner_key(json.loads(record["scope_json"]))!=owner:raise a.GraphHeld("bootstrap owner witness differs")
                offset=record["bootstrap_cursor"] if record["bootstrap_revision"]==revision else 0
                if type(offset) is not int or not 0<=offset<=len(inventory):raise a.GraphHeld("bootstrap cursor differs")
                selected=inventory[offset:offset+MAX_BOOTSTRAP_ROWS]
                for url,title,kind,subject,relation,source_revision,source_id in selected:
                    _reserve_row(db,work,owner,_schema_row(url,title[:256],kind,subject),ZERO,relation,
                                 digest([source_revision,source_id]),now)
                cursor=offset+len(selected)
                bootstrap={"owner":owner,"revision":revision,"cursor":cursor,"complete":cursor>=len(inventory),
                           "processed":len(selected),"inventory_rows":len(inventory)}
                planned.append({"owner":owner,"id":revision,"witness":_sha(dict(record)),"state":"done"})
            for raw in jobs:
                job=dict(raw);owner=job["owner"];trial=deepcopy(work)
                try:
                    if mode=="catalogue":
                        if owner_key(json.loads(job["scope_json"]))!=owner:raise ValueError("scope witness")
                        item=json.loads(job["payload"]);witness=digest([job["batch"],job["id"],item])
                        url=source_url(item["source"]);title=clean(item["title"],256)
                        child=_reserve_row(db,trial,owner,_schema_row(url,title,item["kind"],(item["namespace"]+":"+item["external_id"])[:256]),
                                           ZERO,"catalogue_observation",witness,now)
                        if item["namespace"]=="steam" and APPID.fullmatch(item["external_id"]) and _locator(url)==_locator("https://store.steampowered.com/app/"+item["external_id"]+"/"):
                            job_id=digest(["steam-app",child,item["external_id"],title])
                            trial["expansions"].append([owner,job_id,child,item["external_id"],title,witness,"queued",now,None])
                    else:
                        if not APPID.fullmatch(job["appid"]):raise ValueError("appid")
                        for row in project({"appid":job["appid"],"title":job["title"]},"steam"):
                            _reserve_row(db,trial,owner,row,job["parent"],"feed_discovery",job["witness"],now)
                    if len(trial["nodes"])+len(trial["edges"])>MAX_RECORDS:
                        if planned:break
                        raise CatalogueHeld("job exceeds structural batch bound")
                    work=trial;state="done"
                except (ValueError,KeyError,TypeError,CatalogueHeld):
                    state="held"
                planned.append({"owner":owner,"id":job["id"],"witness":_sha(job),"state":state})
            if not planned:
                db.execute("COMMIT");return None
            lanes={}
            for kind in ("nodes","edges"):
                for pair in work[kind].values():
                    index=a.lane(pair[1][1] if kind=="nodes" else pair[1][3])
                    lanes.setdefault(str(index),{"nodes":[],"edges":[]})[kind].append(pair)
            plan={"sequence":seq,"mode":mode,"now":now,"jobs":planned,"lanes":lanes,"bootstrap":bootstrap,
                  "deltas":[[owner,index,*delta] for (owner,index),delta in sorted(work["deltas"].items())],
                  "candidates":[list(x) for x in sorted(work["candidates"])],"expansions":work["expansions"]}
            raw=_serialize(plan);witness=hashlib.sha256(raw.encode()).hexdigest()
            if len(raw.encode())>MAX_PLAN_BYTES:raise a.GraphHeld("structural plan byte bound")
            db.execute("UPDATE main.dragon_graph_structural SET sequence=?,state='pending',plan=?,sha256=? WHERE singleton=1",
                       (seq,raw,witness))
            db.execute("COMMIT")
            return plan,witness
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def _verify_rows(db,part,prefix=""):
    for kind,columns in (("nodes",a.NODE_COLUMNS),("edges",a.EDGE_COLUMNS)):
        for before,after in part[kind]:
            actual=db.execute("SELECT "+",".join(columns)+" FROM "+prefix+kind+" WHERE owner=? AND id=?",tuple(after[:2])).fetchone()
            if actual is None or list(actual)!=after:raise a.GraphHeld("structural post-state differs")
            if kind=="nodes" and before is None:
                fts=db.execute("SELECT owner,id,title,url,kind,family FROM "+prefix+"graph_search WHERE owner=? AND id=?",tuple(after[:2])).fetchall()
                if [list(r) for r in fts]!=[[after[0],after[1],after[4],after[2],after[5],after[6]]]:
                    raise a.GraphHeld("structural FTS witness differs")


def _apply_rows(db,part,index):
    for kind,columns in (("nodes",a.NODE_COLUMNS),("edges",a.EDGE_COLUMNS)):
        for before,after in part[kind]:
            if a.lane(after[1] if kind=="nodes" else after[3])!=index:raise a.GraphHeld("structural lane mismatch")
            actual=db.execute("SELECT "+",".join(columns)+" FROM "+kind+" WHERE owner=? AND id=?",tuple(after[:2])).fetchone()
            if (list(actual) if actual else None)!=before:raise a.GraphHeld("structural pre-state differs")
            if before is None:
                db.execute("INSERT INTO "+kind+" VALUES("+",".join("?" for _ in columns)+")",after)
                if kind=="nodes":
                    db.execute("INSERT INTO graph_search VALUES(?,?,?,?,?,?)",(after[0],after[1],after[4],after[2],after[5],after[6]))
            elif kind=="nodes":
                db.execute("UPDATE nodes SET last_seen=?,observations=? WHERE owner=? AND id=?",(after[8],after[10],*after[:2]))
            else:
                db.execute("UPDATE edges SET last_seen=? WHERE owner=? AND id=?",(after[11],*after[:2]))


@contextmanager
def _write_lane(root,layout,index):
    path,identity=_private(Path(layout["paths"][index]))
    root_identity=_private(root)[1]
    if identity==root_identity:raise a.GraphHeld("lane aliases root")
    if shutil.disk_usage(path.parent).free<512*1024**2+4*MAX_PLAN_BYTES:
        raise a.GraphHeld("structural lane disk reserve")
    with _open(path) as db:
        if db.execute("PRAGMA journal_mode").fetchone()[0].lower()!="delete":raise a.GraphHeld("structural lane journal differs")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=EXTRA")
        db.execute("BEGIN IMMEDIATE")
        try:
            marker=db.execute("SELECT epoch,lane FROM graph_identity WHERE singleton=1").fetchone()
            if marker is None or tuple(marker)!=(layout["epoch"],index):raise a.GraphHeld("structural lane identity differs")
            yield db
            if _private(path)[1]!=identity or _private(root)[1]!=root_identity:raise a.GraphHeld("storage replaced")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def apply_lane(root,sequence,plan_sha,index):
    root=Path(root)
    with _open(root) as policy:
        policy.execute("BEGIN")
        try:
            item=_pending(policy)
            if item is None or item[0]["sequence"]!=sequence or item[1]!=plan_sha:
                raise a.GraphHeld("structural reservation superseded")
            if policy.execute("PRAGMA journal_mode").fetchone()[0].lower()!="delete":
                raise a.GraphHeld("structural policy journal differs")
            plan=item[0];part=plan["lanes"].get(str(index))
            if part is None:raise a.GraphHeld("unreserved lane")
            layout=a._layout(policy,root)
            witness=_sha(part)
            with _write_lane(root,layout,index) as db:
                receipt=db.execute("SELECT sequence,plan_sha,lane_sha FROM structural_receipt WHERE singleton=1").fetchone()
                if receipt and receipt[0]>=sequence:
                    if tuple(receipt)!=(sequence,plan_sha,witness):raise a.GraphHeld("structural receipt differs")
                    _verify_rows(db,part);replayed=True
                else:
                    _apply_rows(db,part,index)
                    _verify_rows(db,part)
                    db.execute("""INSERT INTO structural_receipt VALUES(1,?,?,?)
                       ON CONFLICT(singleton) DO UPDATE SET sequence=excluded.sequence,plan_sha=excluded.plan_sha,lane_sha=excluded.lane_sha""",
                               (sequence,plan_sha,witness))
                    replayed=False
            policy.execute("COMMIT")
            return {"lane":index,"replayed":replayed,"nodes":len(part["nodes"]),"edges":len(part["edges"])}
        except BaseException:
            if policy.in_transaction:policy.execute("ROLLBACK")
            raise


def _job_row(db,mode,owner,identifier):
    if mode=="bootstrap":
        row=db.execute("SELECT * FROM main.lead_owner WHERE owner=?",(owner,)).fetchone()
    elif mode=="catalogue":
        row=db.execute("""SELECT j.owner,j.id,j.payload,j.batch,o.scope_json FROM lead_release_outbox q
           JOIN release_jobs j ON j.owner=q.owner AND j.id=q.id JOIN lead_owner o ON o.owner=q.owner
           WHERE q.owner=? AND q.id=? AND q.state='queued' AND j.state='done'""",(owner,identifier)).fetchone()
    else:
        row=db.execute("SELECT * FROM lead_expand_jobs WHERE owner=? AND id=? AND state='queued' AND snapshot IS NULL",(owner,identifier)).fetchone()
    return dict(row) if row else None


def settle(root,sequence,plan_sha):
    root=Path(root)
    with a._probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            pending=_pending(db)
            if pending is None:
                row=db.execute("SELECT sequence,sha256 FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
                if tuple(row)!=(sequence,plan_sha):raise a.GraphHeld("settlement superseded")
                db.execute("COMMIT");return {"processed":0,"held":0,"replayed":True,"network_executed":False}
            plan,witness=pending
            if (plan["sequence"],witness)!=(sequence,plan_sha):raise a.GraphHeld("settlement reservation differs")
            for index,part in plan["lanes"].items():
                alias=a._alias(int(index))
                receipt=db.execute("SELECT sequence,plan_sha,lane_sha FROM "+alias+".structural_receipt WHERE singleton=1").fetchone()
                if not receipt or tuple(receipt)!=(sequence,plan_sha,_sha(part)):raise a.GraphHeld("lane commit missing")
                _verify_rows(db,part,alias+".")
            for job in plan["jobs"]:
                actual=_job_row(db,plan["mode"],job["owner"],job["id"])
                if actual is None or _sha(actual)!=job["witness"]:raise a.GraphHeld("root job custody differs")
            # Guard triggers unlock only inside this transaction. Other readers
            # see either the pending fence or all settled root metadata.
            db.execute("UPDATE main.dragon_graph_structural SET state='idle',plan='' WHERE singleton=1")
            for part in plan["lanes"].values():
                for before,after in part["nodes"]:
                    if before is None:
                        db.execute("INSERT INTO main.lead_node_directory VALUES(?,?,?,'','','','',0,0,0,0,'candidate')",after[:3])
            for owner,index,nodes,edges in plan["deltas"]:
                if db.execute("UPDATE main.lead_lane_counts SET nodes=nodes+?,edges=edges+? WHERE owner=? AND lane=?",(nodes,edges,owner,index)).rowcount!=1:
                    raise a.GraphHeld("lane reservation disappeared")
                if db.execute("UPDATE main.lead_owner SET nodes=nodes+?,edges=edges+? WHERE owner=?",(nodes,edges,owner)).rowcount!=1:
                    raise a.GraphHeld("owner reservation disappeared")
            for owner,identifier in plan["candidates"]:
                db.execute("""INSERT INTO lead_dataset_candidates VALUES(?,?,?,?)
                    ON CONFLICT(owner,lead) DO UPDATE SET last_seen=MAX(last_seen,excluded.last_seen)""",
                           (owner,identifier,plan["now"],plan["now"]))
            for expansion in plan["expansions"]:
                db.execute("INSERT OR IGNORE INTO lead_expand_jobs VALUES(?,?,?,?,?,?,?,?,?)",expansion)
            if plan["mode"]=="bootstrap":
                cursor=plan["bootstrap"]
                if db.execute("""UPDATE lead_owner SET bootstrap_revision=?,bootstrap_cursor=?,bootstrapped=?,due=?
                    WHERE owner=?""",(cursor["revision"],cursor["cursor"],int(cursor["complete"]),plan["now"]+1,cursor["owner"])).rowcount!=1:
                    raise a.GraphHeld("bootstrap cursor settlement differs")
            else:
                table="lead_release_outbox" if plan["mode"]=="catalogue" else "lead_expand_jobs"
                for job in plan["jobs"]:
                    if db.execute("UPDATE "+table+" SET state=? WHERE owner=? AND id=? AND state='queued'",
                                  (job["state"],job["owner"],job["id"])).rowcount!=1:raise a.GraphHeld("job settlement differs")
            a._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    bootstrap=plan["bootstrap"]
    return {"processed":bootstrap["processed"] if bootstrap else sum(j["state"]=="done" for j in plan["jobs"]),
            **({"bootstrap_complete":bootstrap["complete"]} if bootstrap else {}),
            "held":sum(j["state"]=="held" for j in plan["jobs"]),"mode":plan["mode"],
            "sequence":sequence,"physical_lanes":len(plan["lanes"]),"network_executed":False}


def _run(root,item):
    if item is None:return {"processed":0,"held":0,"network_executed":False}
    plan,witness=item;seq=plan["sequence"]
    with ThreadPoolExecutor(max_workers=WORKERS,thread_name_prefix="dragon-structural") as pool:
        receipts=list(pool.map(lambda key:apply_lane(root,seq,witness,int(key)),plan["lanes"]))
    result=settle(root,seq,witness)
    return {**result,"lane_receipts":receipts,"independent_structural_writers":True}


def pulse(root,mode="catalogue"):
    """Reserve once, apply independently, and publish only verified settlement."""
    try:return _run(root,reserve(root,mode))
    except (a.GraphHeld,ShardHeld,sqlite3.Error,OSError) as exc:
        raise CatalogueHeld("structural batch held; retry durable plan") from exc


def recover(root):
    """Resume a committed reservation only; never create new work."""
    try:
        with _open(Path(root)) as db:item=_pending(db)
        return _run(root,item)
    except (a.GraphHeld,ShardHeld,sqlite3.Error,OSError) as exc:
        raise CatalogueHeld("structural recovery held") from exc


def status(root):
    with _open(Path(root)) as db:
        if not enabled(db):return {"configured":False}
        row=db.execute("SELECT sequence,state,sha256 FROM main.dragon_graph_structural WHERE singleton=1").fetchone()
        return {"configured":True,"sequence":row[0],"state":row[1],"plan_sha":row[2],
                "physical_writers":a.LANES,"network_authorized":False}
