"""Explicitly approved, bounded campaign-batch orchestration.

The controller executes only pre-authored immutable DAG steps. It reserves a
durable batch ID before dispatch, never auto-resumes after an uncertain
interruption, and cannot authorize tools or inject predecessor outputs.
Existing per-step CAS claims remain the execution authority.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import time

from skeleton.app.jeeves_review_campaign import CampaignConflict, CampaignRejected

SCHEMA="skeleton.jeeves.campaign-batch.v1"
MAX_BATCHES=24
MAX_STEPS=4
MAX_TOKENS=2048
MAX_SECONDS=180
_ID=re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PIN=re.compile(r"[0-9a-f]{64}\Z")


def _stable(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      separators=(",",":"),allow_nan=False)


def _digest(value):
    return sha256(_stable(value).encode("utf-8")).hexdigest()


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise CampaignRejected("invalid batch identifier")
    return value


def _validate(body):
    if type(body) is not dict or set(body)!={"batch_id","plan_sha256","expected_revision",
            "steps","maximum_reserved_tokens","maximum_seconds"}:
        raise CampaignRejected("explicit immutable batch approval required")
    _id(body["batch_id"])
    if type(body["plan_sha256"]) is not str or not _PIN.fullmatch(body["plan_sha256"]):
        raise CampaignRejected("exact approved graph digest required")
    for key,lo,hi in (("expected_revision",0,2**63-1),
                      ("maximum_reserved_tokens",1,MAX_TOKENS),
                      ("maximum_seconds",1,MAX_SECONDS)):
        if type(body[key]) is not int or not lo<=body[key]<=hi:
            raise CampaignRejected("invalid batch budget")
    steps=body["steps"]
    if type(steps) is not list or not 1<=len(steps)<=MAX_STEPS:
        raise CampaignRejected("one to four ordered approved steps required")
    for node in steps:
        _id(node)
    if len(set(steps))!=len(steps):
        raise CampaignRejected("duplicate approved steps")
    return dict(body)


def preview(graph,steps,maximum_reserved_tokens):
    if graph["session_snapshot_stale"] or any(
            r["status"]=="running" for r in graph["statuses"].values()):
        raise CampaignConflict("campaign has stale or unresolved work")
    done={key for key,row in graph["statuses"].items() if row["status"]=="complete"}
    specs={row["id"]:row for row in graph["plan"]["steps"]}
    total=0
    for node in steps:
        if node not in specs or graph["statuses"][node]["status"]!="pending":
            raise CampaignConflict("batch step is not pending")
        spec=specs[node]
        if not set(spec["depends_on"])<=done:
            raise CampaignConflict("batch is not in dependency order")
        total+=spec["reservation"]
        done.add(node)
    if (total>maximum_reserved_tokens or graph["reserved_tokens"]+total>
            graph["plan"]["maximum_reserved_tokens"]):
        raise CampaignConflict("batch reservation exceeds approved budget")
    return total


class CampaignBatchController:
    def __init__(self,campaigns):
        self.campaigns=campaigns
        self.store=campaigns.store
        with self.store._transaction():
            self.store._db.execute("""CREATE TABLE IF NOT EXISTS offline_review_batches (
                session_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                row_json TEXT NOT NULL,
                row_sha256 TEXT NOT NULL,
                PRIMARY KEY(session_id,campaign_id,batch_id),
                FOREIGN KEY(session_id,campaign_id)
                  REFERENCES offline_review_campaigns(session_id,campaign_id) ON DELETE CASCADE
            )""")

    def _load(self,sid,cid,bid):
        row=self.store._db.execute(
            "SELECT row_json,row_sha256 FROM offline_review_batches WHERE session_id=? AND campaign_id=? AND batch_id=?",
            (sid,cid,bid)).fetchone()
        if row is None:
            raise CampaignRejected("unknown approved batch")
        raw,pin=row
        try:
            if len(raw.encode())>32768 or sha256(raw.encode()).hexdigest()!=pin:
                raise CampaignConflict("batch record digest mismatch")
            value=json.loads(raw)
            if (_stable(value)!=raw or value["schema"]!=SCHEMA or value["session_id"]!=sid
                    or value["campaign_id"]!=cid or value["approval"]["batch_id"]!=bid
                    or _digest(value["approval"])!=value["approval_sha256"]):
                raise CampaignConflict("batch record identity mismatch")
        except (KeyError,ValueError,TypeError):
            raise CampaignConflict("batch integrity failure") from None
        return value

    def _write(self,row,*,create=False):
        raw=_stable(row)
        if len(raw.encode())>32768:
            raise CampaignRejected("batch record limit exceeded")
        key=(row["session_id"],row["campaign_id"],row["approval"]["batch_id"])
        pin=sha256(raw.encode()).hexdigest()
        if create:
            self.store._db.execute("INSERT INTO offline_review_batches VALUES (?,?,?,?,?)",(*key,raw,pin))
        else:
            result=self.store._db.execute(
                "UPDATE offline_review_batches SET row_json=?,row_sha256=? WHERE session_id=? AND campaign_id=? AND batch_id=?",
                (raw,pin,*key))
            if result.rowcount!=1:
                raise CampaignConflict("batch claim disappeared")

    def inspect(self,sid,cid,bid):
        cid,bid=_id(cid),_id(bid)
        with self.store.read_snapshot():
            graph=self.campaigns.inspect(sid,cid)
            row=self._load(sid,cid,bid)
            return {"batch":row,"campaign":graph,"replayed":True,
                    "automatic_restart":False,"external_tool_execution":False}

    def begin(self,sid,cid,body):
        cid=_id(cid)
        approval=_validate(body)
        bid=approval["batch_id"]
        identity=_digest(approval)
        with self.store._transaction():
            graph=self.campaigns.inspect(sid,cid)
            seen=self.store._db.execute(
                "SELECT 1 FROM offline_review_batches WHERE session_id=? AND campaign_id=? AND batch_id=?",
                (sid,cid,bid)).fetchone()
            if seen:
                row=self._load(sid,cid,bid)
                if row["approval_sha256"]!=identity:
                    raise CampaignConflict("batch identifier reused with changed authorization")
                return row,False
            if graph["plan_sha256"]!=approval["plan_sha256"] or graph["revision"]!=approval["expected_revision"]:
                raise CampaignConflict("approved batch snapshot changed")
            count=self.store._db.execute(
                "SELECT COUNT(*) FROM offline_review_batches WHERE session_id=? AND campaign_id=?",
                (sid,cid)).fetchone()[0]
            if count>=MAX_BATCHES:
                raise CampaignRejected("campaign batch capacity reached")
            reservation=preview(graph,approval["steps"],approval["maximum_reserved_tokens"])
            row={"schema":SCHEMA,"session_id":sid,"campaign_id":cid,
                 "approval":approval,"approval_sha256":identity,"reserved_upper_bound":reservation,
                 "status":"running","completed":[],"attempted":[],
                 "stop_reason":None,"final_campaign_revision":graph["revision"],
                 "automatic_restart":False,"tool_execution_authorized":False}
            self._write(row,create=True)
            return row,True

    def _replace(self,sid,cid,bid,update):
        with self.store._transaction():
            row=self._load(sid,cid,bid)
            if row["status"]!="running":
                raise CampaignConflict("batch is not running")
            update(row)
            self._write(row)
            return row

    def execute(self,sid,cid,body,*,advance):
        if not callable(advance):
            raise CampaignRejected("canonical step dispatcher required")
        row,created=self.begin(sid,cid,body)
        bid=row["approval"]["batch_id"]
        if not created:
            result=self.inspect(sid,cid,bid)
            # An existing running batch may be live or interrupted. Viewing
            # it never invokes generation or creates another step claim.
            return result
        deadline=time.monotonic()+row["approval"]["maximum_seconds"]
        stop="all_approved_steps_complete"
        revision=row["final_campaign_revision"]
        try:
            for index,node in enumerate(row["approval"]["steps"]):
                if time.monotonic()>=deadline:
                    stop="cooperative_deadline_before_next_step"
                    break
                graph=self.campaigns.inspect(sid,cid)
                if (graph["revision"]!=revision or graph["plan_sha256"]!=row["approval"]["plan_sha256"]
                        or graph["session_snapshot_stale"] or node not in graph["ready_steps"]):
                    stop="campaign_changed_or_dependency_not_ready"
                    break
                operation="batch-"+_digest([row["approval_sha256"],node,index])[:48]
                def mark_started(current):
                    current["attempted"].append({"step_id":node,"operation_id":operation,
                                                 "before_revision":revision})
                self._replace(sid,cid,bid,mark_started)
                result=advance(node,operation,revision,deadline)
                observed=result["statuses"][node]
                revision=result["revision"]
                def mark_settled(current):
                    current["attempted"][-1]["status"]=observed["status"]
                    current["attempted"][-1]["after_revision"]=revision
                    current["final_campaign_revision"]=revision
                    if observed["status"]=="complete":
                        current["completed"].append(node)
                self._replace(sid,cid,bid,mark_settled)
                if observed["status"]!="complete":
                    stop="step_not_complete"
                    break
        except Exception:
            # Existing step state is authoritative. The batch may have
            # stopped after dispatch but before receiving a result.
            stop="step_execution_unconfirmed"
        def finish(current):
            current["stop_reason"]=stop
            current["status"]="complete" if stop=="all_approved_steps_complete" else "stopped"
        self._replace(sid,cid,bid,finish)
        observed=self.inspect(sid,cid,bid)
        observed["replayed"]=False
        return observed

    def abandon(self,sid,cid,bid,approval_sha256):
        cid,bid=_id(cid),_id(bid)
        if type(approval_sha256) is not str or not _PIN.fullmatch(approval_sha256):
            raise CampaignRejected("exact prior batch approval required")
        def stop(row):
            if row["approval_sha256"]!=approval_sha256:
                raise CampaignConflict("batch approval identity changed")
            row["status"]="abandoned_unconfirmed"
            row["stop_reason"]="operator_marked_abandoned_not_cancellation"
        self._replace(sid,cid,bid,stop)
        return self.inspect(sid,cid,bid)
