"""Durable, capability-limited autonomous local read-only tool orchestration.

One explicit grant binds a finite action inventory and budget. The controller
selects ready actions based on verified predecessor results. It never parses
source text as instructions, expands its authority, invokes a shell, performs
network I/O, mutates knowledge or resumes an uncertain operation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import time

from skeleton.app.jeeves_constraints import rational
from skeleton.app.offline_grounding import normalized_document_scope,_citation

SCHEMA="skeleton.jeeves.tool-campaign.v1"
MAX_ACTIONS=12
MAX_EXECUTION=8
MAX_CAMPAIGNS=16
MAX_RECORD_BYTES=256*1024
_ID=re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PIN=re.compile(r"[0-9a-f]{64}\Z")


class ToolCampaignError(ValueError):
    pass


class ToolCampaignConflict(ToolCampaignError):
    pass


def stable(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False)


def digest(value):
    return sha256(stable(value).encode()).hexdigest()


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ToolCampaignError("invalid action or campaign identifier")
    return value


def _integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise ToolCampaignError("invalid tool budget")
    return value


def normalize_plan(value):
    if type(value) is not dict or set(value) not in ({"actions","maximum_calls","maximum_seconds"},{"actions","maximum_calls","maximum_seconds","selector"}):
        raise ToolCampaignError("explicit closed tool plan required")
    budget=_integer(value["maximum_calls"],1,MAX_EXECUTION)
    seconds=_integer(value["maximum_seconds"],1,45)
    actions=value["actions"]
    if type(actions) is not list or not 1<=len(actions)<=MAX_ACTIONS:
        raise ToolCampaignError("bounded action inventory required")
    rows=[]
    known={}
    for action in actions:
        if type(action) is not dict or set(action)!={"id","kind","arguments","depends_on","condition"}:
            raise ToolCampaignError("invalid closed action shape")
        node=_id(action["id"])
        if node in known:
            raise ToolCampaignError("duplicate action id")
        deps=action["depends_on"]
        if type(deps) is not list or len(deps)>MAX_ACTIONS:
            raise ToolCampaignError("invalid tool dependencies")
        deps=[_id(x) for x in deps]
        if len(set(deps))!=len(deps) or any(x not in known for x in deps):
            raise ToolCampaignError("dependencies must be distinct and precede action")
        condition=action["condition"]
        if type(condition) is not dict or set(condition)!={"kind","action"}:
            raise ToolCampaignError("invalid tool condition")
        if condition["kind"]=="always":
            if condition["action"] is not None:
                raise ToolCampaignError("unconditional action cannot reference a result")
        elif (condition["kind"] not in ("has_hits","no_hits") or condition["action"] not in deps
                or known[condition["action"]]["kind"]!="search"):
            raise ToolCampaignError("conditional action requires an approved search dependency")
        kind,args=action["kind"],action["arguments"]
        if type(args) is not dict:
            raise ToolCampaignError("invalid tool arguments")
        if kind=="search" and set(args)=={"query","document_ids","limit"}:
            query=args["query"]
            if type(query) is not str or not query.strip() or len(query.encode())>1024 or "\x00" in query:
                raise ToolCampaignError("invalid bounded tool query")
            scope=normalized_document_scope(args["document_ids"])
            if scope is None:
                raise ToolCampaignError("explicit local source scope required")
            clean={"query":query.strip(),"document_ids":list(scope),"limit":_integer(args["limit"],1,3)}
        elif kind=="calculate" and set(args)=={"expression"}:
            rational(args["expression"])
            clean={"expression":args["expression"]}
        elif kind=="document_identity" and set(args)=={"document_id","sha256"}:
            scope=normalized_document_scope([args["document_id"]])
            if type(args["sha256"]) is not str or not _PIN.fullmatch(args["sha256"]):
                raise ToolCampaignError("document identity pin required")
            clean={"document_id":scope[0],"sha256":args["sha256"]}
        else:
            raise ToolCampaignError("tool is outside closed read-only registry")
        row={"id":node,"kind":kind,"arguments":clean,"depends_on":deps,"condition":dict(condition)}
        rows.append(row);known[node]=row
    result={"actions":rows,"maximum_calls":budget,"maximum_seconds":seconds}
    if "selector" in value:
        from skeleton.app.jeeves_model_tool_selector import validate_selector
        result["selector"]=validate_selector(value["selector"],known)
    return result


class LocalToolCampaign:
    def __init__(self,store,library,model_digest,tokenizer_digest):
        self.store=store;self.library=library
        self.model_digest=model_digest;self.tokenizer_digest=tokenizer_digest
        with store._transaction():
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_tool_campaigns (
                session_id TEXT NOT NULL REFERENCES offline_sessions(session_id) ON DELETE CASCADE,
                campaign_id TEXT NOT NULL,
                row_json TEXT NOT NULL,
                row_sha256 TEXT NOT NULL,
                PRIMARY KEY(session_id,campaign_id)
            )""")

    def _session(self,sid):
        return self.store.load(sid,self.model_digest,self.tokenizer_digest)

    def _load(self,sid,cid):
        found=self.store._db.execute(
            "SELECT row_json,row_sha256 FROM offline_tool_campaigns WHERE session_id=? AND campaign_id=?",
            (sid,cid)).fetchone()
        if found is None:
            raise ToolCampaignError("unknown local tool campaign")
        raw,pin=found
        if type(raw) is not str or len(raw.encode())>MAX_RECORD_BYTES or sha256(raw.encode()).hexdigest()!=pin:
            raise ToolCampaignConflict("tool campaign integrity mismatch")
        row=json.loads(raw)
        if (stable(row)!=raw or row["schema"]!=SCHEMA or row["session_id"]!=sid or row["campaign_id"]!=cid
                or row["model_digest"]!=self.model_digest or row["tokenizer_digest"]!=self.tokenizer_digest
                or digest(row["plan"])!=row["plan_sha256"]):
            raise ToolCampaignConflict("tool campaign identity mismatch")
        return row

    def _write(self,row,create=False):
        raw=stable(row)
        if len(raw.encode())>MAX_RECORD_BYTES:
            raise ToolCampaignError("tool campaign record exceeds ceiling")
        pin=sha256(raw.encode()).hexdigest()
        key=(row["session_id"],row["campaign_id"])
        if create:
            self.store._db.execute("INSERT INTO offline_tool_campaigns VALUES (?,?,?,?)",(*key,raw,pin))
        else:
            result=self.store._db.execute(
                "UPDATE offline_tool_campaigns SET row_json=?,row_sha256=? WHERE session_id=? AND campaign_id=?",
                (raw,pin,*key))
            if result.rowcount!=1:
                raise ToolCampaignConflict("durable tool claim disappeared")

    def inspect(self,sid,cid):
        cid=_id(cid)
        with self.store.read_snapshot():
            current=self._session(sid)
            row=self._load(sid,cid)
            return {**row,"session_snapshot_stale":current.revision!=row["session_revision"],
                    "automatic_restart":False}

    def _source_pins(self,plan):
        ids=set()
        for action in plan["actions"]:
            args=action["arguments"]
            if action["kind"]=="search":
                ids.update(args["document_ids"])
            elif action["kind"]=="document_identity":
                ids.add(args["document_id"])
        if len(ids)>8:
            raise ToolCampaignError("combined campaign source scope exceeds eight documents")
        if not ids:
            return {}
        docs,_=self.library._verified_snapshot(tuple(sorted(ids)))
        pins={row[0]:row[2] for row in docs}
        for action in plan["actions"]:
            if action["kind"]=="document_identity":
                args=action["arguments"]
                if pins[args["document_id"]]!=args["sha256"]:
                    raise ToolCampaignConflict("approved document identity changed")
        return pins

    def begin(self,sid,cid,revision,plan):
        cid=_id(cid);_integer(revision,0,2**63-1)
        plan=normalize_plan(plan)
        pin=digest(plan)
        with self.store._transaction():
            session=self._session(sid)
            exists=self.store._db.execute(
                "SELECT 1 FROM offline_tool_campaigns WHERE session_id=? AND campaign_id=?",(sid,cid)).fetchone()
            if exists:
                old=self._load(sid,cid)
                if old["plan_sha256"]!=pin or old["session_revision"]!=revision:
                    raise ToolCampaignConflict("tool campaign identifier reused")
                return old,False
            if session.revision!=revision:
                raise ToolCampaignConflict("conversation revision changed")
            count=self.store._db.execute(
                "SELECT COUNT(*) FROM offline_tool_campaigns WHERE session_id=?",(sid,)).fetchone()[0]
            if count>=MAX_CAMPAIGNS:
                raise ToolCampaignError("tool campaign capacity reached")
            source_pins=self._source_pins(plan)
            row={"schema":SCHEMA,"session_id":sid,"campaign_id":cid,"session_revision":revision,
                 "model_digest":self.model_digest,"tokenizer_digest":self.tokenizer_digest,
                 "plan":plan,"plan_sha256":pin,"source_pins":source_pins,
                 "status":"running","calls":0,"results":{},"active_action":None,
                 "stop_reason":None,"network_called":False,"knowledge_modified":False,
                 "transcript_committed":False,"model_generated_tool_arguments":False,
                 "model_directed_selection":"selector" in plan,"selector_receipts":[]}
            self._write(row,True)
            return row,True

    def _mutate(self,sid,cid,operation):
        with self.store._transaction():
            row=self._load(sid,cid)
            if row["status"]!="running":
                raise ToolCampaignConflict("tool campaign is no longer running")
            operation(row)
            self._write(row)
            return row

    def _recheck(self,sid,row):
        if self._session(sid).revision!=row["session_revision"]:
            raise ToolCampaignConflict("conversation changed during tool execution")
        if self._source_pins(row["plan"])!=row["source_pins"]:
            raise ToolCampaignConflict("approved local sources changed during execution")

    def _execute(self,action,row):
        kind,args=action["kind"],action["arguments"]
        if kind=="calculate":
            value=rational(args["expression"])
            return {"numerator":str(value.numerator),"denominator":str(value.denominator),
                    "exact_arithmetic":True}
        if kind=="document_identity":
            return {"document_id":args["document_id"],"sha256":row["source_pins"][args["document_id"]],
                    "identity_verified":True}
        hits=self.library.search(args["query"],limit=args["limit"],document_ids=args["document_ids"],
                                 evidence_excerpt=True)
        citations=[]
        for hit in hits:
            proof=_citation(hit)
            if proof["document_id"] not in args["document_ids"] or row["source_pins"].get(proof["document_id"])!=proof["document_sha256"]:
                raise ToolCampaignConflict("search escaped granted source scope")
            citations.append(proof)
        return {"hit_count":len(citations),"citations":citations,
                "semantic_truth_verified":False,"source_content_is_instruction":False}

    def run(self,sid,cid,revision,plan,*,selector=None):
        plan=normalize_plan(plan)
        if ("selector" in plan)!=(selector is not None):
            raise ToolCampaignError("model selector authority mismatch")
        if selector is not None and not callable(selector):
            raise ToolCampaignError("invalid local model selector")
        row,created=self.begin(sid,cid,revision,plan)
        if not created:
            return {**self.inspect(sid,cid),"replayed":True}
        deadline=time.monotonic()+row["plan"]["maximum_seconds"]
        reason="all_actions_resolved"
        try:
            while True:
                if time.monotonic()>=deadline:
                    reason="cooperative_deadline_before_next_action";break
                self._recheck(sid,row)
                pending=[a for a in row["plan"]["actions"] if a["id"] not in row["results"]]
                if not pending:
                    break
                ready=[]
                skipped=[]
                for action in pending:
                    dependencies=[row["results"].get(d) for d in action["depends_on"]]
                    if not all(r is not None for r in dependencies):
                        continue
                    eligible=all(r["status"]=="succeeded" for r in dependencies)
                    condition=action["condition"]
                    if eligible and condition["kind"]!="always":
                        prior=row["results"][condition["action"]]["result"]["hit_count"]
                        eligible=(prior>0)==(condition["kind"]=="has_hits")
                    if eligible:
                        ready.append(action)
                    else:
                        skipped.append(action["id"])
                if skipped:
                    def skip(current):
                        for node in skipped:
                            current["results"][node]={"status":"skipped","reason":"dependency_or_condition"}
                    row=self._mutate(sid,cid,skip)
                    continue
                if not ready:
                    raise ToolCampaignConflict("no ready action in approved dependency graph")
                if row["calls"]>=row["plan"]["maximum_calls"]:
                    reason="tool_call_budget";break
                decision=None
                if selector is None:
                    action=ready[0]
                else:
                    if len(row.get("selector_receipts",[]))>=plan["selector"]["maximum_decisions"]:
                        reason="model_decision_budget";break
                    decision=selector(ready,row,deadline)
                    self._recheck(sid,row)
                    if (type(decision) is not dict or decision.get("plan_sha256")!=row["plan_sha256"]
                            or decision.get("ready_actions")!=[a["id"] for a in ready]
                            or decision.get("model_digest")!=self.model_digest
                            or decision.get("tokenizer_digest")!=self.tokenizer_digest
                            or decision.get("authority_expanded") is not False
                            or decision.get("new_arguments_generated") is not False
                            or decision.get("model_graph_executed") is not True
                            or decision.get("receipt_sha256")!=digest({k:v for k,v in decision.items() if k!="receipt_sha256"})):
                        raise ToolCampaignConflict("unbound model selection receipt")
                    selected=decision["selected_action"]
                    if selected is None:
                        def stop_selection(current):
                            self._recheck(sid,current)
                            current.setdefault("selector_receipts",[]).append(decision)
                        row=self._mutate(sid,cid,stop_selection)
                        reason="model_selected_stop";break
                    options={a["id"]:a for a in ready}
                    if selected not in options:
                        raise ToolCampaignConflict("selection escaped approved ready actions")
                    action=options[selected]
                node=action["id"]
                def claim(current):
                    self._recheck(sid,current)
                    if current["active_action"] is not None:
                        raise ToolCampaignConflict("unresolved tool claim")
                    current["active_action"]=node
                    current["calls"]+=1
                    if decision is not None:
                        current.setdefault("selector_receipts",[]).append(decision)
                row=self._mutate(sid,cid,claim)
                result=self._execute(action,row)
                self._recheck(sid,row)
                def settle(current):
                    self._recheck(sid,current)
                    if current["active_action"]!=node:
                        raise ToolCampaignConflict("tool claim withdrawn")
                    current["results"][node]={"status":"succeeded","result":result,
                        "receipt_sha256":digest({"action":action,"result":result,"plan_sha256":row["plan_sha256"]})}
                    current["active_action"]=None
                row=self._mutate(sid,cid,settle)
        except Exception:
            reason="execution_or_source_unconfirmed"
        def finish(current):
            current["status"]="complete" if reason=="all_actions_resolved" else "stopped"
            current["stop_reason"]=reason
        self._mutate(sid,cid,finish)
        return {**self.inspect(sid,cid),"replayed":False}

    def abandon(self,sid,cid,expected_plan_sha256):
        if type(expected_plan_sha256) is not str or not _PIN.fullmatch(expected_plan_sha256):
            raise ToolCampaignError("exact reviewed plan digest required")
        def stop(row):
            if row["plan_sha256"]!=expected_plan_sha256:
                raise ToolCampaignConflict("tool plan changed")
            row["status"]="abandoned_unconfirmed"
            row["stop_reason"]="operator_abandoned_not_process_cancellation"
        self._mutate(sid,cid,stop)
        return self.inspect(sid,cid)
