"""Persistent, finite research campaigns over the authorized locator federation.

Campaigns remember proposed target identities, not web bodies, credentials,
or the raw objective. A campaign receipt is advisory and never dispatches.
Current graph grants and review state are rechecked on every presentation.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter

from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.navigation_semantics import digest,semantic_features

MAX_ROUNDS=128
MAX_TOTAL_BUDGET=4096
MAX_LIFETIME=30*86400
MAX_CAMPAIGNS=128
MAX_PAGE=64
MODES={"balanced","coverage","exploration","conservation"}

SCHEMA="""
CREATE TABLE IF NOT EXISTS navigation_campaigns(
 owner TEXT NOT NULL,id TEXT NOT NULL,objective TEXT NOT NULL,
 mode TEXT NOT NULL,learned INTEGER NOT NULL,created INTEGER NOT NULL,
 expires INTEGER NOT NULL,initial_budget INTEGER NOT NULL,remaining INTEGER NOT NULL,
 revision INTEGER NOT NULL,rounds INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','exhausted','closed')),
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_campaign_expiry ON navigation_campaigns(owner,state,expires,id);
CREATE TABLE IF NOT EXISTS navigation_campaign_retired(
 owner TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS navigation_campaign_rounds(
 owner TEXT NOT NULL,campaign TEXT NOT NULL,ordinal INTEGER NOT NULL,
 operation TEXT NOT NULL,command TEXT NOT NULL,plan_digest TEXT NOT NULL,
 spent INTEGER NOT NULL,created INTEGER NOT NULL,pool_truncated INTEGER NOT NULL,
 PRIMARY KEY(owner,campaign,ordinal), UNIQUE(owner,campaign,operation),
 FOREIGN KEY(owner,campaign) REFERENCES navigation_campaigns(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS navigation_campaign_targets(
 owner TEXT NOT NULL,campaign TEXT NOT NULL,target TEXT NOT NULL,round INTEGER NOT NULL,
 position INTEGER NOT NULL,cost INTEGER NOT NULL,
 PRIMARY KEY(owner,campaign,target), UNIQUE(owner,campaign,round,position),
 FOREIGN KEY(owner,campaign,round) REFERENCES navigation_campaign_rounds(owner,campaign,ordinal) ON DELETE CASCADE,
 FOREIGN KEY(owner,target) REFERENCES navigation_nodes(owner,id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS navigation_campaign_target_source ON navigation_campaign_targets(owner,target,campaign);
"""


def _now(value):
    return int(time.time()) if value is None else graph._integer(value,0,10**12)


def _objective(query):
    if not isinstance(query,str) or not query.strip() or len(query)>512:
        raise ValueError("campaign objective bound")
    # Retain only a digest; the caller must resupply the exact objective.
    return digest(["dragon-campaign-objective-v1",query])


def _operation(value):
    if not isinstance(value,str) or not 16<=len(value)<=128 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise ValueError("campaign operation identity")
    return digest(["dragon-campaign-operation-v1",value])


def _row(db,owner,identifier):
    graph._id(identifier)
    row=db.execute("SELECT * FROM navigation_campaigns WHERE owner=? AND id=?",(owner,identifier)).fetchone()
    if row is None:raise ValueError("campaign unavailable")
    return row


def _summary(row,now):
    return {"campaign_id":row["id"],"objective_digest":row["objective"],"mode":row["mode"],
        "learned":bool(row["learned"]),"created_at":row["created"],"expires_at":row["expires"],
        "budget":row["initial_budget"],"remaining":row["remaining"],"revision":row["revision"],
        "rounds":row["rounds"],"state":"expired" if row["expires"]<=now and row["state"]=="active" else row["state"],
        "network_authorized":False,"training_permission":False}


def create(db,owner,*,query,operation,budget,retention_seconds,mode="balanced",learned=False,acknowledged=False,now=None):
    at=_now(now);objective=_objective(query);op=_operation(operation)
    graph._integer(budget,1,MAX_TOTAL_BUDGET);graph._integer(retention_seconds,900,MAX_LIFETIME)
    if acknowledged is not True or type(learned) is not bool or mode not in MODES:
        raise ValueError("explicit finite campaign required")
    identifier=digest([owner,op])
    prior=db.execute("SELECT * FROM navigation_campaigns WHERE owner=? AND id=?",(owner,identifier)).fetchone()
    if prior is not None:
        if (prior["objective"],prior["initial_budget"],prior["expires"]-prior["created"],prior["mode"],bool(prior["learned"]))!=(objective,budget,retention_seconds,mode,learned):
            raise ValueError("campaign creation replay differs")
        return {**_summary(prior,at),"replayed":True}
    if db.execute("SELECT 1 FROM navigation_campaign_retired WHERE owner=? AND id=?",(owner,identifier)).fetchone():
        raise ValueError("campaign operation retired")
    count=db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM navigation_campaigns WHERE owner=? LIMIT ?)",
                     (owner,MAX_CAMPAIGNS)).fetchone()[0]
    if count>=MAX_CAMPAIGNS:raise ValueError("campaign custody cap; purge expired campaigns")
    db.execute("INSERT INTO navigation_campaigns VALUES(?,?,?,?,?,?,?,?,?,?,?,'active')",
               (owner,identifier,objective,mode,int(learned),at,at+retention_seconds,budget,budget,1,0))
    return {**_summary(_row(db,owner,identifier),at),"replayed":False}


def _visible(db,owner,identifier,ordinal,now):
    # Reveal only current, due-permitted targets with at least one active
    # source grant. The immutable round commitment never renews that grant.
    query="""SELECT t.target AS target_id,t.position,t.cost,n.url,n.host
      FROM navigation_campaign_targets t JOIN navigation_nodes n ON n.owner=t.owner AND n.id=t.target
      LEFT JOIN navigation_reviews r ON r.owner=n.owner AND r.target=n.id
      WHERE t.owner=? AND t.campaign=? AND t.round=? AND (r.state IS NULL OR r.state='candidate')
      AND (r.next_review IS NULL OR r.next_review<=?) AND """+graph._active_sql("n")+" ORDER BY t.position"
    return [{**dict(row),"network_authorized":False} for row in db.execute(query,(owner,identifier,ordinal,now,now))]


def _round(db,owner,row,record,now,replayed):
    result={"campaign":_summary(row,now),"round":record["ordinal"],"plan_digest":record["plan_digest"],
        "spent":record["spent"],"created_at":record["created"],"pool_truncated":bool(record["pool_truncated"]),
        "targets":_visible(db,owner,row["id"],record["ordinal"],now) if row["state"]!="closed" and row["expires"]>now else [],
        "replayed":replayed,"network_authorized":False,"training_permission":False}
    return {**result,"receipt":digest(result)}


def _coverage(db,owner,identifier,facets,now,*,fleet_id=None):
    # Bounded recent, source-witnessed acquisition evidence, not previously
    # proposed or rejected targets. This is an estimated knowledge coverage
    # of currently retained locator metadata; content is not inspected.
    # Bound the recent proposal window before evaluating acquisition
    # witnesses. Fleet-wide coverage never sorts all 12,800 rounds or
    # hundreds of thousands of historical target references.
    recent="""WITH own_recent AS (
       SELECT target,round AS seq,position FROM navigation_campaign_targets
       WHERE owner=? AND campaign=? ORDER BY round DESC,position DESC LIMIT 128
    )"""
    parameters=[owner,identifier]
    if fleet_id is not None:
        recent+=""", recent_jobs AS (
          SELECT campaign,round,updated FROM navigation_fleet_jobs
          WHERE owner=? AND fleet=? AND state='complete'
          ORDER BY updated DESC,operation DESC LIMIT 128
        ), recent_targets AS (
          SELECT t.target,j.updated AS seq,t.position
          FROM recent_jobs j JOIN navigation_campaign_targets t
          ON t.owner=? AND t.campaign=j.campaign AND t.round=j.round
          UNION ALL SELECT target,seq,position FROM own_recent
        )"""
        parameters.extend([owner,fleet_id,owner])
        target_cte="recent_targets"
    else:
        target_cte="own_recent"
    rows=db.execute(recent+f""" SELECT n.url,MAX(t.seq) AS last_round,MAX(t.position) AS last_position
      FROM {target_cte} t JOIN navigation_nodes n ON n.owner=? AND n.id=t.target
      WHERE EXISTS(SELECT 1 FROM navigation_outcomes o JOIN navigation_grants g
        ON g.owner=o.owner AND g.grant_id=o.grant_id WHERE o.owner=n.owner AND o.target=t.target
        AND o.phase='captured' AND g.state='active' AND g.expires>?)
      GROUP BY n.id,n.url ORDER BY last_round DESC,last_position DESC,n.id LIMIT 129""",
      (*parameters,owner,now)).fetchall()
    values=[0.]*len(facets)
    for row in rows[:128]:
        for i,facet in enumerate(facets):
            score=semantic_features(facet["query"],row["url"])
            values[i]=max(values[i],min(1.,.50*score["exact"]+.35*score["concept"]+.15*score["trigram"]))
    return values,len(rows)>128


def advance(db,owner,*,campaign_id,query,operation,expected_revision,budget=16,now=None,_fleet_claim=None):
    from core.dragon_navigation_intelligence import plan,objective_facets
    at=_now(now);objective=_objective(query);op=_operation(operation)
    graph._integer(expected_revision,1,MAX_ROUNDS+1);graph._integer(budget,1,48)
    command=digest([objective,expected_revision,budget])
    # Read snapshot then optimistic publication. Inference runs without
    # SQLite's writer lock. Any concurrent database change holds publication.
    before=db.execute("PRAGMA data_version").fetchone()[0]
    db.execute("BEGIN")
    try:
        row=_row(db,owner,campaign_id)
        if row["objective"]!=objective:raise ValueError("campaign objective differs")
        prior=db.execute("SELECT * FROM navigation_campaign_rounds WHERE owner=? AND campaign=? AND operation=?",
                         (owner,campaign_id,op)).fetchone()
        if prior is not None:
            if prior["command"]!=command:raise ValueError("campaign round replay differs")
            value=_round(db,owner,row,prior,at,True)
            db.execute("COMMIT")
            return value
        if row["state"]!="active" or row["expires"]<=at or row["revision"]!=expected_revision or row["rounds"]>=MAX_ROUNDS:
            raise ValueError("campaign revision, budget or lifetime held")
        membership=db.execute("SELECT fleet FROM navigation_fleet_members WHERE owner=? AND campaign=?",
                              (owner,campaign_id)).fetchone()
        if membership is not None and (_fleet_claim is None or _fleet_claim[0]!=membership["fleet"]):
            raise ValueError("fleet member requires leased orchestration")
        fleet_id=membership["fleet"] if membership is not None else None
        limit=min(row["remaining"],budget)
        if limit<1:raise ValueError("campaign budget exhausted")
        expiry=db.execute("SELECT MIN(expires) FROM navigation_grants WHERE owner=? AND state='active' AND expires>?",
                          (owner,at)).fetchone()[0]
        coverage,truncated=_coverage(db,owner,campaign_id,objective_facets(query),at,fleet_id=fleet_id)
        result=plan(db,owner,query=query,now=at,budget=limit,mode=row["mode"],
                    learned=bool(row["learned"]),campaign_id=campaign_id,initial_coverage=coverage,
                    exploration_round=row["rounds"],fleet_id=fleet_id)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise
    db.execute("BEGIN IMMEDIATE")
    try:
        at2=_now(now)
        if db.execute("PRAGMA data_version").fetchone()[0]!=before or row["expires"]<=at2 or expiry is not None and expiry<=at2:
            raise ValueError("campaign catalogue changed during deliberation")
        if _fleet_claim is not None:
            fleet_id,operation_digest,token=_fleet_claim
            witness=db.execute("""SELECT 1 FROM navigation_fleet_jobs j JOIN navigation_fleets f
                ON f.owner=j.owner AND f.id=j.fleet WHERE j.owner=? AND j.fleet=? AND j.operation=?
                AND j.token=? AND j.campaign=? AND j.state=\'leased\' AND j.lease_until>?
                AND f.state=\'active\' AND f.expires>?""",
                (owner,fleet_id,operation_digest,token,campaign_id,at2,at2)).fetchone()
            if witness is None:raise ValueError("fleet lease changed before campaign publication")
        latest=_row(db,owner,campaign_id)
        if latest["revision"]!=expected_revision or latest["state"]!="active":
            raise ValueError("campaign revision changed")
        spent=limit-result["remaining"];ordinal=row["rounds"]+1
        if not 0<=spent<=limit or sum(t["estimated_work_units"] for t in result["targets"])!=spent:
            raise ValueError("campaign planner budget differs")
        if len(result["targets"])>24 or len({t["target_id"] for t in result["targets"]})!=len(result["targets"]):
            raise ValueError("campaign planner target bounds")
        db.execute("INSERT INTO navigation_campaign_rounds VALUES(?,?,?,?,?,?,?,?,?)",
                   (owner,campaign_id,ordinal,op,command,result["receipt"],spent,at2,int(truncated or result["pool_truncated"])))
        for i,t in enumerate(result["targets"]):
            target=graph._id(t["target_id"])
            current=db.execute("SELECT 1 FROM navigation_nodes n LEFT JOIN navigation_reviews r ON r.owner=n.owner AND r.target=n.id "
                "WHERE n.owner=? AND n.id=? AND (r.state IS NULL OR r.state='candidate') "
                "AND (r.next_review IS NULL OR r.next_review<=?) AND "+graph._active_sql("n"),(owner,target,at2,at2)).fetchone()
            if current is None:raise ValueError("campaign target authority changed")
            db.execute("INSERT INTO navigation_campaign_targets VALUES(?,?,?,?,?,?)",(owner,campaign_id,target,ordinal,i,t["estimated_work_units"]))
        remaining=row["remaining"]-spent
        state="exhausted" if remaining==0 or ordinal>=MAX_ROUNDS else "active"
        db.execute("UPDATE navigation_campaigns SET remaining=?,revision=revision+1,rounds=?,state=? WHERE owner=? AND id=?",
                   (remaining,ordinal,state,owner,campaign_id))
        record=db.execute("SELECT * FROM navigation_campaign_rounds WHERE owner=? AND campaign=? AND ordinal=?",(owner,campaign_id,ordinal)).fetchone()
        response=_round(db,owner,_row(db,owner,campaign_id),record,at2,False)
        db.execute("COMMIT")
        return response
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise


def inspect(db,owner,*,campaign_id,after=0,limit=16,now=None):
    at=_now(now);graph._integer(after,0,MAX_ROUNDS);graph._integer(limit,1,MAX_PAGE)
    row=_row(db,owner,campaign_id)
    records=db.execute("SELECT * FROM navigation_campaign_rounds WHERE owner=? AND campaign=? AND ordinal>? ORDER BY ordinal LIMIT ?",
                       (owner,campaign_id,after,limit+1)).fetchall()
    # History receipts are metadata only; do not expand all targets here.
    return {"campaign":_summary(row,at),"rounds":[{"ordinal":r["ordinal"],"spent":r["spent"],
        "plan_digest":r["plan_digest"],"created_at":r["created"],"pool_truncated":bool(r["pool_truncated"])}
        for r in records[:limit]],"next_cursor":records[limit-1]["ordinal"] if len(records)>limit else None,
        "network_authorized":False,"training_permission":False}


def close(db,owner,*,campaign_id,expected_revision,now=None):
    at=_now(now);graph._integer(expected_revision,1,MAX_ROUNDS+2)
    row=_row(db,owner,campaign_id)
    if row["state"]=="closed":return {**_summary(row,at),"replayed":True}
    if row["revision"]!=expected_revision:raise ValueError("campaign revision changed")
    db.execute("UPDATE navigation_campaigns SET state='closed',revision=revision+1 WHERE owner=? AND id=?",(owner,campaign_id))
    # Keep only bounded digest receipts until expiry; release selection IDs.
    db.execute("DELETE FROM navigation_campaign_targets WHERE owner=? AND campaign=?",(owner,campaign_id))
    return {**_summary(_row(db,owner,campaign_id),at),"replayed":False}


def purge(db,owner,*,limit=16,now=None):
    at=_now(now);graph._integer(limit,1,32)
    # Keep outstanding fleet recovery commitments until the lease is
    # reconciled. Otherwise a committed debit could be lost by expiry.
    rows=db.execute("""SELECT c.id FROM navigation_campaigns c WHERE c.owner=? AND c.expires<=?
        AND NOT EXISTS(SELECT 1 FROM navigation_fleet_jobs j WHERE j.owner=c.owner AND j.campaign=c.id
                       AND j.state='leased')
        ORDER BY c.expires,c.id LIMIT ?""",(owner,at,limit)).fetchall()
    for row in rows:
        db.execute("INSERT OR IGNORE INTO navigation_campaign_retired VALUES(?,?)",(owner,row["id"]))
        db.execute("DELETE FROM navigation_campaigns WHERE owner=? AND id=?",(owner,row["id"]))
    return {"purged":len(rows),"more_possible":len(rows)==limit,"network_authorized":False}
