"""Owner-fenced research fleet orchestration over finite advisory campaigns.

Ten campaigns can be coordinated as one finite portfolio (1,280 rounds and
40,960 advisory units at the current campaign ceilings). Persistent leases
cover the proposal operation, not transport. No query text is stored, no
unapproved campaign is created, and the fleet cannot authorize acquisition.
"""
from __future__ import annotations

import time
from collections import Counter
from uuid import uuid4

from core import dragon_research_campaign as campaign
from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.navigation_semantics import digest

MAX_MEMBERS=10
MAX_FLEETS=32
MAX_LEASE=180
MAX_JOBS=1280
MAX_LIFETIME=30*86400
MAX_PAGE=64
MAX_BUDGET=40960

SCHEMA="""
CREATE TABLE IF NOT EXISTS navigation_fleets(
 owner TEXT NOT NULL,id TEXT NOT NULL,command TEXT NOT NULL,
 created INTEGER NOT NULL,expires INTEGER NOT NULL,
 budget INTEGER NOT NULL,remaining INTEGER NOT NULL,revision INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','closed','exhausted')),
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_fleet_expiry ON navigation_fleets(owner,expires,id);
CREATE TABLE IF NOT EXISTS navigation_fleet_retired(
 owner TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS navigation_fleet_members(
 owner TEXT NOT NULL,fleet TEXT NOT NULL,campaign TEXT NOT NULL,
 weight INTEGER NOT NULL CHECK(weight BETWEEN 1 AND 16),
 rounds INTEGER NOT NULL DEFAULT 0,spent INTEGER NOT NULL DEFAULT 0,
 last_served INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,fleet,campaign),
 UNIQUE(owner,campaign),
 FOREIGN KEY(owner,fleet) REFERENCES navigation_fleets(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS navigation_fleet_jobs(
 owner TEXT NOT NULL,fleet TEXT NOT NULL,operation TEXT NOT NULL,command TEXT NOT NULL,
 campaign TEXT NOT NULL,campaign_revision INTEGER NOT NULL,round_budget INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('leased','complete','held')),
 token TEXT NOT NULL,lease_until INTEGER NOT NULL,
 created INTEGER NOT NULL,updated INTEGER NOT NULL,spent INTEGER NOT NULL DEFAULT 0,
 round INTEGER,plan_digest TEXT,code TEXT,
 PRIMARY KEY(owner,fleet,operation),
 FOREIGN KEY(owner,fleet) REFERENCES navigation_fleets(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE UNIQUE INDEX IF NOT EXISTS navigation_fleet_active_job
ON navigation_fleet_jobs(owner,fleet) WHERE state='leased';
CREATE INDEX IF NOT EXISTS navigation_fleet_job_history ON navigation_fleet_jobs(owner,fleet,created,operation);
"""


def _at(now):
    return int(time.time()) if now is None else graph._integer(now,0,10**12)


def _row(db,owner,identifier):
    graph._id(identifier)
    row=db.execute("SELECT * FROM navigation_fleets WHERE owner=? AND id=?",(owner,identifier)).fetchone()
    if row is None:raise ValueError("research fleet unavailable")
    return row


def _members(db,owner,identifier):
    return db.execute("""SELECT m.*,c.objective,c.remaining AS campaign_remaining,
        c.revision AS campaign_revision,c.expires AS campaign_expiry,c.state AS campaign_state
        FROM navigation_fleet_members m LEFT JOIN navigation_campaigns c
        ON c.owner=m.owner AND c.id=m.campaign
        WHERE m.owner=? AND m.fleet=? ORDER BY m.campaign""",(owner,identifier)).fetchall()


def _summary(db,owner,row,now):
    members=_members(db,owner,row["id"])
    return {"fleet_id":row["id"],"revision":row["revision"],"created_at":row["created"],
        "expires_at":row["expires"],"budget":row["budget"],"remaining":row["remaining"],
        "state":"expired" if now>=row["expires"] and row["state"]=="active" else row["state"],
        "members":[{"campaign_id":m["campaign"],"weight":m["weight"],"rounds":m["rounds"],
                    "spent":m["spent"],"campaign_revision":m["campaign_revision"],
                    "campaign_remaining":m["campaign_remaining"],
                    "eligible":m["campaign_state"]=="active" and m["campaign_expiry"]>now
                               and m["campaign_remaining"]>0} for m in members],
        "network_authorized":False,"training_permission":False}


def create(db,owner,*,operation,members,budget,retention_seconds,acknowledged,now=None):
    at=_at(now);op=campaign._operation(operation)
    graph._integer(budget,1,MAX_BUDGET);graph._integer(retention_seconds,900,MAX_LIFETIME)
    if acknowledged is not True or not isinstance(members,list) or not 1<=len(members)<=MAX_MEMBERS:
        raise ValueError("explicit bounded research fleet required")
    parsed={}
    for item in members:
        if not isinstance(item,dict) or set(item)!={"campaign_id","weight"}:
            raise ValueError("fleet member shape")
        identifier=graph._id(item["campaign_id"]);weight=graph._integer(item["weight"],1,16)
        if identifier in parsed:raise ValueError("duplicate fleet member")
        parsed[identifier]=weight
    identity=digest(["dragon-research-fleet-v1",owner,op])
    command=digest([sorted(parsed.items()),budget,retention_seconds])
    prior=db.execute("SELECT * FROM navigation_fleets WHERE owner=? AND id=?",(owner,identity)).fetchone()
    if prior:
        if prior["command"]!=command:raise ValueError("fleet create replay differs")
        return {**_summary(db,owner,prior,at),"replayed":True}
    if db.execute("SELECT 1 FROM navigation_fleet_retired WHERE owner=? AND id=?",(owner,identity)).fetchone():
        raise ValueError("fleet operation retired")
    if db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM navigation_fleets WHERE owner=? LIMIT ?)",
                  (owner,MAX_FLEETS)).fetchone()[0]>=MAX_FLEETS:
        raise ValueError("fleet retention cap")
    total=0
    for identifier in parsed:
        member=campaign._row(db,owner,identifier)
        if member["state"]!="active" or member["expires"]<at+retention_seconds or member["remaining"]<1:
            raise ValueError("fleet member lifecycle held")
        if db.execute("SELECT 1 FROM navigation_fleet_members WHERE owner=? AND campaign=?",
                      (owner,identifier)).fetchone():raise ValueError("campaign already belongs to a fleet")
        total+=member["remaining"]
    if total<budget:raise ValueError("fleet budget exceeds admitted member budgets")
    db.execute("INSERT INTO navigation_fleets VALUES(?,?,?,?,?,?,?,?, 'active')",
               (owner,identity,command,at,at+retention_seconds,budget,budget,1))
    db.executemany("INSERT INTO navigation_fleet_members(owner,fleet,campaign,weight) VALUES(?,?,?,?)",
                   ((owner,identity,identifier,weight) for identifier,weight in sorted(parsed.items())))
    return {**_summary(db,owner,_row(db,owner,identity),at),"replayed":False}


def inspect(db,owner,*,fleet_id,after=None,limit=16,now=None):
    at=_at(now);row=_row(db,owner,fleet_id);graph._integer(limit,1,MAX_PAGE)
    lower="" if after is None else graph._id(after)
    jobs=db.execute("""SELECT operation,campaign,state,spent,round,plan_digest,code,created,updated
        FROM navigation_fleet_jobs WHERE owner=? AND fleet=? AND operation>?
        ORDER BY operation LIMIT ?""",(owner,fleet_id,lower,limit+1)).fetchall()
    return {"fleet":_summary(db,owner,row,at),"jobs":[dict(x) for x in jobs[:limit]],
            "next_cursor":jobs[limit-1]["operation"] if len(jobs)>limit else None,
            "network_authorized":False}


def _job(db,owner,fleet,operation):
    return db.execute("SELECT * FROM navigation_fleet_jobs WHERE owner=? AND fleet=? AND operation=?",
                      (owner,fleet,operation)).fetchone()


def _command(objectives,budget,expected_revision):
    if not isinstance(objectives,list) or not 1<=len(objectives)<=MAX_MEMBERS:
        raise ValueError("exact objective set required")
    values={}
    for item in objectives:
        if not isinstance(item,dict) or set(item)!={"campaign_id","query"}:
            raise ValueError("fleet objective shape")
        key=graph._id(item["campaign_id"])
        if key in values:raise ValueError("duplicate fleet objective")
        campaign._objective(item["query"])
        values[key]=item["query"]
    graph._integer(budget,1,48);graph._integer(expected_revision,1,MAX_JOBS+2)
    return values,digest([sorted((key,campaign._objective(value)) for key,value in values.items()),
                          budget,expected_revision])


def _project(db,owner,fleet,job,now,*,replayed):
    row=_row(db,owner,fleet)
    result={"fleet":_summary(db,owner,row,now),"operation":job["operation"],
            "campaign_id":job["campaign"],"state":job["state"],"allocated":job["round_budget"],
            "spent":job["spent"],"round":job["round"],"plan_digest":job["plan_digest"],
            "code":job["code"],"targets":[],"replayed":replayed,"network_authorized":False}
    if job["state"]=="complete" and row["state"]!="closed" and row["expires"]>now:
        try:
            member=campaign._row(db,owner,job["campaign"])
        except ValueError:
            member=None
        if member is not None and member["state"]!="closed" and member["expires"]>now:
            result["targets"]=campaign._visible(db,owner,member["id"],job["round"],now)
    return {**result,"receipt":digest(result)}


def _claim(db,owner,fleet,operation,command,objectives,budget,expected_revision,now):
    row=_row(db,owner,fleet)
    old=_job(db,owner,fleet,operation)
    if old:
        if old["command"]!=command:raise ValueError("fleet pulse replay differs")
        if old["state"]!="leased":return None,_project(db,owner,fleet,old,now,replayed=True)
        if old["lease_until"]>now:raise ValueError("fleet operation currently leased")
        if row["state"]!="active" or row["expires"]<=now:raise ValueError("fleet expired; use lease reconciliation")
        member=campaign._row(db,owner,old["campaign"])
        if old["campaign"] not in objectives or member["objective"]!=campaign._objective(objectives[old["campaign"]]):
            raise ValueError("fleet objective differs")
        token=uuid4().hex
        db.execute("UPDATE navigation_fleet_jobs SET token=?,lease_until=?,updated=? WHERE owner=? AND fleet=? AND operation=?",
                   (token,min(row["expires"],now+MAX_LEASE),now,owner,fleet,operation))
        return token,None
    if row["state"]!="active" or row["expires"]<=now or row["revision"]!=expected_revision:
        raise ValueError("fleet lifecycle or revision held")
    if db.execute("SELECT 1 FROM navigation_fleet_jobs WHERE owner=? AND fleet=? AND state='leased'",
                  (owner,fleet)).fetchone():
        raise ValueError("recover the outstanding fleet operation first")
    if db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM navigation_fleet_jobs WHERE owner=? AND fleet=? LIMIT ?)",
                  (owner,fleet,MAX_JOBS)).fetchone()[0]>=MAX_JOBS:
        raise ValueError("fleet round cap")
    members=_members(db,owner,fleet)
    if set(objectives)!={m["campaign"] for m in members}:
        raise ValueError("all exact fleet objectives required")
    eligible=[]
    for m in members:
        if m["objective"] is None or m["objective"]!=campaign._objective(objectives[m["campaign"]]):
            raise ValueError("fleet member objective differs")
        if m["campaign_state"]=="active" and m["campaign_expiry"]>now and m["campaign_remaining"]>0:
            eligible.append(m)
    if not eligible or row["remaining"]<=0:
        raise ValueError("no eligible fleet work")
    # Weighted deficit scheduling. Charge actual committed advisory units;
    # use rounds and last-served order to avoid zero-cost starvation.
    selected=min(eligible,key=lambda m:((m["spent"]+m["rounds"])/m["weight"],m["last_served"],m["campaign"]))
    allocation=min(budget,row["remaining"],selected["campaign_remaining"])
    token=uuid4().hex
    db.execute("""INSERT INTO navigation_fleet_jobs(owner,fleet,operation,command,campaign,campaign_revision,
        round_budget,state,token,lease_until,created,updated) VALUES(?,?,?,?,?,?,?,'leased',?,?,?,?)""",
        (owner,fleet,operation,command,selected["campaign"],selected["campaign_revision"],
         allocation,token,min(row["expires"],now+MAX_LEASE),now,now))
    return token,None


def _finish(db,owner,fleet,operation,token,result,now,code=None):
    row=_row(db,owner,fleet);job=_job(db,owner,fleet,operation)
    if job is None or job["state"]!="leased" or job["token"]!=token:
        raise ValueError("fleet lease superseded")
    # A round committed before a worker crash is accounted exactly once
    # even if the fleet expired before receipt publication. No targets
    # are disclosed after expiration. A held attempt consumes no budget.
    spent=0
    if result is not None:
        spent=result["spent"]
        if type(spent) is not int or not 0<=spent<=job["round_budget"] or spent>row["remaining"]:
            raise ValueError("fleet spend witness differs")
        if result["campaign"]["campaign_id"]!=job["campaign"] or result["round"]<1:
            raise ValueError("fleet round identity differs")
        _plan=graph._id(result["plan_digest"])
        db.execute("UPDATE navigation_fleet_members SET rounds=rounds+1,spent=spent+?,last_served=? "
                   "WHERE owner=? AND fleet=? AND campaign=?",(spent,now,owner,fleet,job["campaign"]))
        db.execute("UPDATE navigation_fleet_jobs SET state='complete',updated=?,spent=?,round=?,plan_digest=?,code=NULL "
                   "WHERE owner=? AND fleet=? AND operation=?",(now,spent,result["round"],_plan,owner,fleet,operation))
    else:
        db.execute("UPDATE navigation_fleet_jobs SET state='held',updated=?,code=? WHERE owner=? AND fleet=? AND operation=?",
                   (now,code or "campaign_held",owner,fleet,operation))
    remaining=row["remaining"]-spent
    db.execute("UPDATE navigation_fleets SET remaining=?,revision=revision+1,state=? WHERE owner=? AND id=?",
               (remaining,"exhausted" if remaining==0 else row["state"],owner,fleet))
    return _project(db,owner,fleet,_job(db,owner,fleet,operation),now,replayed=False)


def pulse(db,owner,*,fleet_id,operation,objectives,expected_revision,budget=16,now=None):
    at=_at(now);op=campaign._operation(operation)
    supplied,command=_command(objectives,budget,expected_revision)
    db.execute("BEGIN IMMEDIATE")
    try:
        token,replayed=_claim(db,owner,fleet_id,op,command,supplied,budget,expected_revision,at)
        job=_job(db,owner,fleet_id,op)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise
    if replayed is not None:return replayed
    # Existing exact campaign operation is independently restart-safe.
    # Its deterministic operation ID is never supplied by the client.
    internal=digest(["fleet-round",fleet_id,op])
    result=None;code=None
    try:
        result=campaign.advance(db,owner,campaign_id=job["campaign"],query=supplied[job["campaign"]],
            operation=internal,expected_revision=job["campaign_revision"],budget=job["round_budget"],now=now,
            _fleet_claim=(fleet_id,op,token))
    except ValueError:
        # Distinguish an actual committed round from a held proposal. If
        # campaign.advance raised after an ambiguous commit, leave lease
        # recovery available rather than writing a false held outcome.
        prior=db.execute("SELECT 1 FROM navigation_campaign_rounds WHERE owner=? AND campaign=? AND operation=?",
                         (owner,job["campaign"],campaign._operation(internal))).fetchone()
        if prior is not None:raise
        code="campaign_revision_or_authority_held"
    db.execute("BEGIN IMMEDIATE")
    try:
        value=_finish(db,owner,fleet_id,op,token,result,_at(now),code)
        db.execute("COMMIT")
        return value
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise


def reconcile(db,owner,*,fleet_id,now=None):
    """Fence an expired lease and debit a committed round without raw query."""
    at=_at(now);row=_row(db,owner,fleet_id)
    job=db.execute("SELECT * FROM navigation_fleet_jobs WHERE owner=? AND fleet=? AND state='leased'",
                   (owner,fleet_id)).fetchone()
    if job is None:return {"fleet":_summary(db,owner,row,at),"reconciled":False,"network_authorized":False}
    if job["lease_until"]>at:raise ValueError("fleet operation currently leased")
    # This operation holds the writer transaction. Campaign publication
    # checks the same token inside its own transaction, so a displaced
    # worker cannot publish after this reconciliation.
    internal=digest(["fleet-round",fleet_id,job["operation"]])
    record=db.execute("SELECT * FROM navigation_campaign_rounds WHERE owner=? AND campaign=? AND operation=?",
        (owner,job["campaign"],campaign._operation(internal))).fetchone()
    result=None
    if record:
        member=campaign._row(db,owner,job["campaign"])
        result=campaign._round(db,owner,member,record,at,True)
    value=_finish(db,owner,fleet_id,job["operation"],job["token"],result,at,"lease_expired_without_commit")
    return {"fleet":value["fleet"],"reconciled":True,"operation":value["operation"],
            "state":value["state"],"spent":value["spent"],"network_authorized":False}


def close(db,owner,*,fleet_id,expected_revision,now=None):
    at=_at(now);row=_row(db,owner,fleet_id)
    graph._integer(expected_revision,1,MAX_JOBS+2)
    if row["state"]=="closed":return {**_summary(db,owner,row,at),"replayed":True}
    if row["revision"]!=expected_revision or db.execute(
        "SELECT 1 FROM navigation_fleet_jobs WHERE owner=? AND fleet=? AND state='leased'",(owner,fleet_id)).fetchone():
        raise ValueError("fleet revision or outstanding operation held")
    db.execute("UPDATE navigation_fleets SET state='closed',revision=revision+1 WHERE owner=? AND id=?",(owner,fleet_id))
    db.execute("DELETE FROM navigation_fleet_members WHERE owner=? AND fleet=?",(owner,fleet_id))
    return {**_summary(db,owner,_row(db,owner,fleet_id),at),"replayed":False}


def purge(db,owner,*,limit=16,now=None):
    graph._integer(limit,1,32);at=_at(now)
    rows=db.execute("""SELECT f.id FROM navigation_fleets f WHERE f.owner=? AND f.expires<=?
        AND NOT EXISTS(SELECT 1 FROM navigation_fleet_jobs j WHERE j.owner=f.owner AND j.fleet=f.id AND j.state='leased')
        ORDER BY f.expires,f.id LIMIT ?""",(owner,at,limit)).fetchall()
    for row in rows:
        db.execute("INSERT OR IGNORE INTO navigation_fleet_retired VALUES(?,?)",(owner,row["id"]))
        db.execute("DELETE FROM navigation_fleets WHERE owner=? AND id=?",(owner,row["id"]))
    return {"purged":len(rows),"more_possible":len(rows)==limit,"network_authorized":False}
