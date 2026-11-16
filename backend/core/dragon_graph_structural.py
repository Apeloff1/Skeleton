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
MAX_IMPORT_RECORDS=8192
MAX_IMPORT_PLAN_BYTES=32*1024**2
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
FEED_RECEIPTS="""CREATE TABLE IF NOT EXISTS dragon_parallel_feed_receipts(
 owner TEXT NOT NULL,batch TEXT NOT NULL,request_sha TEXT NOT NULL,proposals INTEGER NOT NULL,
 PRIMARY KEY(owner,batch),FOREIGN KEY(owner,batch) REFERENCES release_imports(owner,id)
) WITHOUT ROWID"""
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
    if not isinstance(raw,str) or not 1<=len(raw.encode())<=MAX_IMPORT_PLAN_BYTES or hashlib.sha256(raw.encode()).hexdigest()!=row["sha256"]:
        raise a.GraphHeld("structural journal witness differs")
    plan=json.loads(raw)
    if (not isinstance(plan,dict) or plan.get("sequence")!=row["sequence"] or plan.get("mode") not in {"catalogue","expansion","bootstrap","snapshot","feed"}
            or not isinstance(plan.get("lanes"),dict) or len(plan["lanes"])>a.LANES or not isinstance(plan.get("jobs"),list)
            or not 1<=len(plan["jobs"])<=MAX_JOBS):
        raise a.GraphHeld("structural journal shape differs")
    large=plan["mode"] in ("snapshot","feed")
    if len(raw.encode())>(MAX_IMPORT_PLAN_BYTES if large else MAX_PLAN_BYTES):
        raise a.GraphHeld("structural journal mode byte bound")
    records=0
    for key,part in plan["lanes"].items():
        if key not in {str(i) for i in range(a.LANES)} or not isinstance(part,dict) or set(part)!={"nodes","edges"}:
            raise a.GraphHeld("structural lane shape differs")
        for table,columns in (("nodes",a.NODE_COLUMNS),("edges",a.EDGE_COLUMNS)):
            pairs=part[table]
            if not isinstance(pairs,list):raise a.GraphHeld("structural row group differs")
            records+=len(pairs)
            for pair in pairs:
                if not isinstance(pair,list) or len(pair)!=2 or not isinstance(pair[1],list) or len(pair[1])!=len(columns):
                    raise a.GraphHeld("structural row shape differs")
                if pair[0] is not None and (not isinstance(pair[0],list) or len(pair[0])!=len(columns) or pair[0][:2]!=pair[1][:2]):
                    raise a.GraphHeld("structural before-state shape differs")
                if any(not isinstance(v,str) or not a.HEX.fullmatch(v) for v in pair[1][:2]):
                    raise a.GraphHeld("structural row identity differs")
                if a.lane(pair[1][1] if table=="nodes" else pair[1][3])!=int(key):
                    raise a.GraphHeld("structural row route differs")
    if records>(MAX_IMPORT_RECORDS if large else MAX_RECORDS):raise a.GraphHeld("structural journal record bound")
    grants=plan.get("grants",[])
    if not isinstance(grants,list) or len(grants)>MAX_JOBS:
        raise a.GraphHeld("structural grant count differs")
    for grant in grants:
        if (not isinstance(grant,dict) or set(grant)!={"owner","snapshot","sha256","expires_at"}
                or any(not isinstance(grant[k],str) or not a.HEX.fullmatch(grant[k]) for k in ("owner","snapshot","sha256"))
                or type(grant["expires_at"]) is not int):
            raise a.GraphHeld("structural grant shape differs")
    if large and not isinstance(plan.get("publication"),dict):raise a.GraphHeld("structural publication missing")
    return plan,row["sha256"]


def _record(db,state,owner,identifier,table,columns,index):
    k=(owner,identifier)
    if k not in state:
        row=db.execute("SELECT "+",".join(columns)+" FROM "+a._alias(index)+"."+table+" WHERE owner=? AND id=?",
                       k).fetchone()
        value=list(row) if row else None
        state[k]=[value,deepcopy(value)]
    return state[k]


def _reserve_row(db,work,owner,row,parent,relation,witness,now,snapshot=None):
    from core.dragon_lead_graph import (lead_id,digest,SOURCE_CLASSES,ZERO,DATASET_KINDS,
        _lane_counts,MAX_NODES,MAX_EDGES,NODES_PER_LANE,EDGES_PER_LANE)
    url,title,kind,subject=row
    identifier=lead_id(url);index=a.lane(identifier)
    if parent!=ZERO and (owner,parent) not in work["nodes"] and not db.execute("SELECT 1 FROM main.lead_node_directory WHERE owner=? AND id=?",(owner,parent)).fetchone():
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
    eid=digest([parent,identifier,relation,subject,kind,title,witness,snapshot])
    edge=_record(db,work["edges"],owner,eid,"edges",a.EDGE_COLUMNS,index)
    expected=[owner,eid,parent,identifier,relation,subject,kind,title,witness,snapshot]
    if edge[1] is None:
        if caps["edges"]+total[1]>=MAX_EDGES or counts["edges"]+local[1]>=EDGES_PER_LANE:raise CatalogueHeld("edge quota")
        edge[1]=expected+[now,now]
        total[1]+=1;local[1]+=1;node[1][10]+=1
    elif edge[1][:10]!=expected:raise CatalogueHeld("edge identity conflict")
    else:edge[1][11]=max(edge[1][11],now)
    node[1][8]=max(node[1][8],now)
    if kind in DATASET_KINDS:work["candidates"].add((owner,identifier))
    return identifier


def _work():
    return {"nodes":{},"edges":{},"owner_deltas":{},"deltas":{},"candidates":set(),"expansions":[]}


def _publish(db,seq,mode,now,planned,work,*,bootstrap=None,publication=None,grants=None,large=False):
    if len(work["nodes"])+len(work["edges"])>(MAX_IMPORT_RECORDS if large else MAX_RECORDS):
        raise CatalogueHeld("structural record bound")
    lanes={}
    for kind in ("nodes","edges"):
        for pair in work[kind].values():
            index=a.lane(pair[1][1] if kind=="nodes" else pair[1][3])
            lanes.setdefault(str(index),{"nodes":[],"edges":[]})[kind].append(pair)
    plan={"sequence":seq,"mode":mode,"now":now,"jobs":planned,"lanes":lanes,"bootstrap":bootstrap,
          "publication":publication,"grants":grants or [],
          "deltas":[[owner,index,*delta] for (owner,index),delta in sorted(work["deltas"].items())],
          "candidates":[list(x) for x in sorted(work["candidates"])],"expansions":work["expansions"]}
    raw=_serialize(plan);witness=hashlib.sha256(raw.encode()).hexdigest()
    if len(raw.encode())>(MAX_IMPORT_PLAN_BYTES if large else MAX_PLAN_BYTES):
        raise a.GraphHeld("structural plan byte bound")
    db.execute("UPDATE main.dragon_graph_structural SET sequence=?,state='pending',plan=?,sha256=? WHERE singleton=1",
               (seq,raw,witness))
    return plan,witness


def _grant(db,owner,sid,now,*,append=False):
    row=db.execute("SELECT * FROM main.lead_snapshots WHERE owner=? AND id=?",(owner,sid)).fetchone()
    if row is None:raise LookupError("lead snapshot missing")
    if row["state"] not in (("open",) if append else ("open","sealed")) or row["expires_at"]<=now:
        raise CatalogueHeld("lead snapshot grant expired or revoked")
    return dict(row)


def _grant_witness(row):
    return {"owner":row["owner"],"snapshot":row["id"],"sha256":_sha(row),"expires_at":row["expires_at"]}


def _live_grants(db,plan):
    now=int(time.time())
    for grant in plan.get("grants",[]):
        row=db.execute("SELECT * FROM main.lead_snapshots WHERE owner=? AND id=?",(grant["owner"],grant["snapshot"])).fetchone()
        if row is None or row["state"]=="revoked" or row["expires_at"]<=now or _sha(dict(row))!=grant["sha256"]:
            return False
    return True


def _owner_enabled(db,owner):
    row=db.execute("SELECT enabled FROM main.lead_owner WHERE owner=?",(owner,)).fetchone()
    return bool(row and row[0])


def _request_pending(db,mode,request_sha):
    pending=_pending(db)
    if pending and (pending[0]["mode"]!=mode or (pending[0].get("publication") or {}).get("request_sha")!=request_sha):
        raise CatalogueHeld("another structural reservation requires recovery")
    return pending


def reserve_snapshot(root,scope,sid,*,ordinal,raw,sha256,previous_chain):
    from core.dragon_lead_graph import (_id,_int,MAX_SNAPSHOT_ROWS,MAX_PAGE_BYTES,parse_page,project,digest,_quota_disk)
    owner=owner_key(scope);sid=_id(sid);ordinal=_int(ordinal,0,MAX_SNAPSHOT_ROWS)
    sha256=_id(sha256);previous_chain=_id(previous_chain)
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_PAGE_BYTES or hashlib.sha256(raw).hexdigest()!=sha256:
        raise ValueError("lead page digest")
    root=Path(root);_quota_disk(root)
    request_sha=_sha([owner,sid,ordinal,sha256,previous_chain])
    with a._probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            pending=_request_pending(db,"snapshot",request_sha)
            if pending:
                db.execute("COMMIT");return pending,None
            now=int(time.time())
            if not _owner_enabled(db,owner):raise CatalogueHeld("lead expansion disabled")
            snap=_grant(db,owner,sid,now)
            prior=db.execute("SELECT * FROM lead_snapshot_pages WHERE owner=? AND snapshot=? AND ordinal=?",(owner,sid,ordinal)).fetchone()
            if prior:
                if prior["digest"]!=sha256 or prior["chain"]!=digest([previous_chain,ordinal,sha256,prior["row_count"]]):
                    raise CatalogueHeld("lead snapshot replay differs")
                db.execute("COMMIT")
                return None,{"ordinal":ordinal,"rows":prior["row_count"],"chain":prior["chain"],"replayed":True,"network_authorized":False}
            if snap["state"]!="open" or snap["next_page"]!=ordinal or snap["chain"]!=previous_chain:
                raise CatalogueHeld("lead snapshot ordering")
            bundle_witness=None
            if snap["projection"]=="steam_seed":
                from core.dragon_bundled_steam_leads import normalized_page,summary
                expected,bundle_witness=normalized_page(ordinal)
                if snap["source_sha"]!=summary()["bundle_revision"] or expected!=raw:
                    raise CatalogueHeld("bundled dataset page differs from pinned source")
            items=parse_page(raw,snap["projection"])
            if snap["rows"]+len(items)>snap["expected_rows"]:raise CatalogueHeld("lead snapshot row budget")
            chain=digest([previous_chain,ordinal,sha256,len(items)])
            work=_work()
            for ix,item in enumerate(items):
                witness=digest([sid,ordinal,sha256,bundle_witness,ix,item])
                for row in project(item,snap["projection"]):
                    child=_reserve_row(db,work,owner,row,snap["root"],"dataset_projection",witness,now,sid)
                    if snap["projection"]=="steam_seed":
                        job=digest(["bundle-steam-app",child,item["appid"],sid])
                        work["expansions"].append([owner,job,child,item["appid"],item["title"],witness,"queued",now,sid])
            publication={"owner":owner,"snapshot":sid,"ordinal":ordinal,"digest":sha256,"chain":chain,
                         "previous_chain":previous_chain,"rows":len(items),"request_sha":request_sha}
            seq=db.execute("SELECT sequence FROM main.dragon_graph_structural WHERE singleton=1").fetchone()[0]+1
            planned=[{"owner":owner,"id":sid,"witness":_sha(snap),"state":"done"}]
            result=_publish(db,seq,"snapshot",now,planned,work,publication=publication,grants=[_grant_witness(snap)],large=True)
            db.execute("COMMIT");return result,None
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


def reserve_feed(root,scope,*,url,raw,adapter,options,subscription_id,batch_id):
    from core.dragon_lead_graph import (_id,_schema_row,digest,APPID,ZERO,_quota_disk)
    from core.dragon_release_discovery import parse_manifest,parse_steam_catalogue,parse_release_feed
    owner=owner_key(scope);subscription_id=_id(subscription_id);batch_id=_id(batch_id)
    if not isinstance(options,dict) or set(options)-{"provider","external_id","title"}:
        raise ValueError("feed options")
    if adapter=="manifest" and not options:proposals=parse_manifest(raw)
    elif adapter=="steam" and not options:proposals=parse_steam_catalogue(raw)
    elif adapter=="rss_atom":proposals=parse_release_feed(raw,**options)
    else:raise ValueError("lead feed adapter")
    fingerprint=hashlib.sha256(raw).hexdigest()
    input_digest=digest([adapter,fingerprint,options.get("provider"),options.get("external_id"),options.get("title")])
    request_sha=_sha([owner,subscription_id,batch_id,url,input_digest])
    root=Path(root);_quota_disk(root)
    with a._probe_connection(root) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            pending=_request_pending(db,"feed",request_sha)
            if pending:
                db.execute("COMMIT");return pending,None
            if not _owner_enabled(db,owner):
                db.execute("COMMIT");return None,{"enabled":False}
            source=db.execute("SELECT * FROM release_imports WHERE owner=? AND id=?",(owner,batch_id)).fetchone()
            if source is None or source["input_digest"]!=input_digest or source["total"]!=len({p.event_key for p in proposals}):
                raise CatalogueHeld("feed release batch witness differs")
            db.execute(FEED_RECEIPTS)
            prior=db.execute("SELECT request_sha,proposals FROM dragon_parallel_feed_receipts WHERE owner=? AND batch=?",(owner,batch_id)).fetchone()
            if prior:
                if prior["request_sha"]!=request_sha or prior["proposals"]!=len(proposals):raise CatalogueHeld("feed replay differs")
                db.execute("COMMIT")
                return None,{"enabled":True,"proposals":len(proposals),"replayed":True,"network_authorized":False}
            now=int(time.time());work=_work()
            parent=_reserve_row(db,work,owner,_schema_row(url,"Authorized feed metadata","release_feed","subscription:"+subscription_id),
                                ZERO,"dataset_target",digest([subscription_id,url]),now)
            for item in proposals:
                witness=digest([subscription_id,fingerprint,item.event_key])
                child=_reserve_row(db,work,owner,_schema_row(item.source,item.title,item.kind,(item.namespace+":"+item.external_id)[:256]),
                                   parent,"feed_discovery",witness,now)
                if adapter=="steam" and item.namespace=="steam" and APPID.fullmatch(item.external_id):
                    job=digest(["steam-app",child,item.external_id,item.title])
                    work["expansions"].append([owner,job,child,item.external_id,item.title,witness,"queued",now,None])
            publication={"owner":owner,"batch":batch_id,"proposals":len(proposals),"request_sha":request_sha}
            seq=db.execute("SELECT sequence FROM main.dragon_graph_structural WHERE singleton=1").fetchone()[0]+1
            planned=[{"owner":owner,"id":batch_id,"witness":_sha(dict(source)),"state":"done"}]
            result=_publish(db,seq,"feed",now,planned,work,publication=publication,large=True)
            db.execute("COMMIT");return result,None
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise


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
                if previous[0]["mode"]!=mode:raise CatalogueHeld("different structural operation pending; recover first")
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
                jobs=db.execute("""SELECT j.* FROM lead_expand_jobs j JOIN lead_owner o ON o.owner=j.owner
                  WHERE j.state='queued' AND o.enabled=1 AND (j.snapshot IS NULL OR EXISTS(
                      SELECT 1 FROM lead_snapshots s WHERE s.owner=j.owner AND s.id=j.snapshot
                      AND s.state IN ('open','sealed') AND s.expires_at>?))
                  ORDER BY j.created_at,j.owner,j.id LIMIT 16""",(now,)).fetchall()
            work=_work()
            grants={}
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
                        snap=None
                        if job["snapshot"] is not None:
                            snap=_grant(db,owner,job["snapshot"],now)
                            if snap["root"]!=job["parent"] and not db.execute(
                                "SELECT 1 FROM lead_edges WHERE owner=? AND child=? AND snapshot=? LIMIT 1",
                                (owner,job["parent"],job["snapshot"])).fetchone():
                                raise CatalogueHeld("expansion snapshot parent differs")
                        for row in project({"appid":job["appid"],"title":job["title"]},"steam"):
                            _reserve_row(db,trial,owner,row,job["parent"],"dataset_projection" if snap else "feed_discovery",job["witness"],now,job["snapshot"])
                    if len(trial["nodes"])+len(trial["edges"])>MAX_RECORDS:
                        if planned:break
                        raise CatalogueHeld("job exceeds structural batch bound")
                    work=trial;state="done"
                    if mode=="expansion" and snap:grants[(owner,snap["id"])]=_grant_witness(snap)
                except (ValueError,KeyError,TypeError,CatalogueHeld):
                    state="held"
                planned.append({"owner":owner,"id":job["id"],"witness":_sha(job),"state":state})
            if not planned:
                db.execute("COMMIT");return None
            result=_publish(db,seq,mode,now,planned,work,bootstrap=bootstrap,grants=list(grants.values()))
            db.execute("COMMIT");return result
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
    if shutil.disk_usage(path.parent).free<512*1024**2+4*MAX_IMPORT_PLAN_BYTES:
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
            if not _live_grants(policy,plan):
                policy.execute("COMMIT")
                return {"lane":index,"skipped":True,"reason":"grant_changed"}
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
    if mode=="snapshot":
        row=db.execute("SELECT * FROM main.lead_snapshots WHERE owner=? AND id=?",(owner,identifier)).fetchone()
    elif mode=="feed":
        row=db.execute("SELECT * FROM main.release_imports WHERE owner=? AND id=?",(owner,identifier)).fetchone()
    elif mode=="bootstrap":
        row=db.execute("SELECT * FROM main.lead_owner WHERE owner=?",(owner,)).fetchone()
    elif mode=="catalogue":
        row=db.execute("""SELECT j.owner,j.id,j.payload,j.batch,o.scope_json FROM lead_release_outbox q
           JOIN release_jobs j ON j.owner=q.owner AND j.id=q.id JOIN lead_owner o ON o.owner=q.owner
           WHERE q.owner=? AND q.id=? AND q.state='queued' AND j.state='done'""",(owner,identifier)).fetchone()
    else:
        row=db.execute("SELECT * FROM lead_expand_jobs WHERE owner=? AND id=? AND state='queued'",(owner,identifier)).fetchone()
    return dict(row) if row else None


def _rollback_grant(db,plan,witness):
    """Exact compensation in one attached rollback-journal transaction.

    No committed root directory/counter/page changes exist yet. Restore only
    rows created/changed by this reservation; never erase historical evidence.
    """
    sequence=plan["sequence"]
    for index,part in plan["lanes"].items():
        alias=a._alias(int(index));prefix=alias+"."
        receipt=db.execute("SELECT sequence,plan_sha,lane_sha FROM "+prefix+"structural_receipt WHERE singleton=1").fetchone()
        if receipt and receipt[0]>=sequence:
            if tuple(receipt)!=(sequence,witness,_sha(part)):raise a.GraphHeld("grant rollback receipt differs")
            _verify_rows(db,part,prefix)
            for kind,columns in (("edges",a.EDGE_COLUMNS),("nodes",a.NODE_COLUMNS)):
                for before,after in reversed(part[kind]):
                    if before is None:
                        if kind=="nodes":
                            db.execute("DELETE FROM "+prefix+"graph_search WHERE owner=? AND id=?",after[:2])
                        if db.execute("DELETE FROM "+prefix+kind+" WHERE owner=? AND id=?",after[:2]).rowcount!=1:
                            raise a.GraphHeld("grant rollback created row missing")
                    else:
                        if db.execute("UPDATE "+prefix+kind+" SET "+",".join(k+"=?" for k in columns[2:])+" WHERE owner=? AND id=?",
                                      [*before[2:],*before[:2]]).rowcount!=1:
                            raise a.GraphHeld("grant rollback prior row missing")
            db.execute("DELETE FROM "+prefix+"structural_receipt WHERE singleton=1")
        for kind,columns in (("nodes",a.NODE_COLUMNS),("edges",a.EDGE_COLUMNS)):
            for before,after in part[kind]:
                row=db.execute("SELECT "+",".join(columns)+" FROM "+prefix+kind+" WHERE owner=? AND id=?",after[:2]).fetchone()
                if (list(row) if row else None)!=before:raise a.GraphHeld("grant rollback pre-state differs")
    db.execute("UPDATE main.dragon_graph_structural SET state='idle',plan='',sha256='' WHERE singleton=1")
    a._fence(db)


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
            if not _live_grants(db,plan):
                _rollback_grant(db,plan,witness)
                db.execute("COMMIT")
                return {"processed":0,"held":len(plan["jobs"]),"aborted":True,"reason":"snapshot_grant_changed","network_executed":False}
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
            if plan["mode"]=="snapshot":
                page=plan["publication"]
                db.execute("INSERT INTO lead_snapshot_pages VALUES(?,?,?,?,?,?)",
                           (page["owner"],page["snapshot"],page["ordinal"],page["digest"],page["rows"],page["chain"]))
                if db.execute("""UPDATE lead_snapshots SET rows=rows+?,next_page=next_page+1,chain=?
                      WHERE owner=? AND id=? AND state='open' AND next_page=? AND chain=? AND expires_at>?""",
                    (page["rows"],page["chain"],page["owner"],page["snapshot"],page["ordinal"],page["previous_chain"],int(time.time()))).rowcount!=1:
                    raise a.GraphHeld("snapshot publication grant differs")
            elif plan["mode"]=="feed":
                page=plan["publication"]
                db.execute("INSERT INTO dragon_parallel_feed_receipts VALUES(?,?,?,?)",
                           (page["owner"],page["batch"],page["request_sha"],page["proposals"]))
            elif plan["mode"]=="bootstrap":
                cursor=plan["bootstrap"]
                if db.execute("""UPDATE lead_owner SET bootstrap_revision=?,bootstrap_cursor=?,bootstrapped=?,due=?
                    WHERE owner=?""",(cursor["revision"],cursor["cursor"],int(cursor["complete"]),plan["now"]+1,cursor["owner"])).rowcount!=1:
                    raise a.GraphHeld("bootstrap cursor settlement differs")
            else:
                table="lead_release_outbox" if plan["mode"]=="catalogue" else "lead_expand_jobs"
                for job in plan["jobs"]:
                    if db.execute("UPDATE "+table+" SET state=? WHERE owner=? AND id=? AND state='queued'",
                                  (job["state"],job["owner"],job["id"])).rowcount!=1:raise a.GraphHeld("job settlement differs")
            if plan["mode"]=="expansion" and not _live_grants(db,plan):
                raise a.GraphHeld("snapshot grant expired during expansion settlement")
            a._fence(db)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
    bootstrap=plan["bootstrap"]
    return {"processed":bootstrap["processed"] if bootstrap else sum(j["state"]=="done" for j in plan["jobs"]),
            **({"bootstrap_complete":bootstrap["complete"]} if bootstrap else {}),
            **({"ordinal":plan["publication"]["ordinal"],"rows":plan["publication"]["rows"],
                "chain":plan["publication"]["chain"],"replayed":False,"network_authorized":False} if plan["mode"]=="snapshot" else {}),
            **({"enabled":True,"proposals":plan["publication"]["proposals"],
                "replayed":False,"network_authorized":False} if plan["mode"]=="feed" else {}),
            "held":sum(j["state"]=="held" for j in plan["jobs"]),"mode":plan["mode"],
            "sequence":sequence,"physical_lanes":len(plan["lanes"]),"network_executed":False}


def _run(root,item):
    if item is None:return {"processed":0,"held":0,"network_executed":False}
    plan,witness=item;seq=plan["sequence"]
    with _open(Path(root)) as db:
        db.execute("BEGIN")
        live=_live_grants(db,plan)
        db.execute("COMMIT")
    if not live:return settle(root,seq,witness)
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


def append(root,scope,sid,**kwargs):
    try:
        item,receipt=reserve_snapshot(root,scope,sid,**kwargs)
        if receipt is not None:return receipt
        result=_run(root,item)
        if result.get("aborted"):raise CatalogueHeld("snapshot grant changed before publication")
        if result.get("replayed"):
            # Another worker may have settled the same page after this call
            # reserved it. Read the canonical page receipt, not a guessed result.
            _,receipt=reserve_snapshot(root,scope,sid,**kwargs)
            if receipt is None:raise CatalogueHeld("snapshot settlement replay unavailable")
            return receipt
        return result
    except (a.GraphHeld,ShardHeld,sqlite3.Error,OSError) as exc:
        raise CatalogueHeld("snapshot structural admission held") from exc


def feed(root,scope,**kwargs):
    try:
        item,receipt=reserve_feed(root,scope,**kwargs)
        if receipt is not None:return receipt
        result=_run(root,item)
        if result.get("replayed"):
            _,receipt=reserve_feed(root,scope,**kwargs)
            if receipt is None:raise CatalogueHeld("feed settlement replay unavailable")
            return receipt
        return result
    except (a.GraphHeld,ShardHeld,sqlite3.Error,OSError) as exc:
        raise CatalogueHeld("feed structural admission held") from exc
