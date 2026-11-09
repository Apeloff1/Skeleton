"""Explicit, fail-closed renewal for Dragon source rights and recrawl policies.

No site is fetched here. Expired/periodically due source policies are retired,
historical stage receipts are archived, and a NEW independent policy-stage
receipt is required before a source is scheduled again. Policy holds caused by
extreme robots delays are deliberately not reset here.
"""
from __future__ import annotations

import json

from .contracts import canonical_digest
from .dragon_almanacs import _auth
from .dragon_almanac_sequence import SequentialAlmanacWorker
from .dragon_technical_source_operations import DragonSourceOperations
from .reviewed_knowledge import _integer

_MAX_EPOCH = 4_102_444_800


class DragonSourcePolicyRenewal:
    def __init__(self, operations: DragonSourceOperations):
        if not isinstance(operations, DragonSourceOperations):
            raise TypeError("canonical durable source operations required")
        self.ops = operations
        self.captures = operations.captures
        self.db = operations.db
        self.worker = SequentialAlmanacWorker(self.captures.a)
        from .dragon_technical_source_analysis import DragonTechnicalGlean
        self.glean = DragonTechnicalGlean(self.captures)

    def _proof(self, owner: str, source_id: str, now: int) -> tuple:
        source, seed = self.captures._source(owner, source_id)
        source_row = self.db.execute(
            "SELECT digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
            (owner, source_id)).fetchone()
        job = self.db.execute(
            "SELECT stage,state,input_digest,token FROM dragon_almanac_jobs "
            "WHERE owner=? AND source=?", (owner, source_id)).fetchone()
        if job is None or job[1] not in {"pending","reviewed"} or job[3] is not None:
            raise PermissionError("live or missing canonical source job cannot renew")
        current = self.ops._history(owner, source_id)
        if not current:
            raise ValueError("source must have a durable operations record")
        stage,state,input_digest,_ = job
        if stage==1 and state=="pending":
            # Old policy may be expired now; historical evidence must
            # nonetheless be complete and match the source snapshot.
            self.worker._verify_prefix(
                owner,source_id,1,input_digest,source["url"],source_row[0],now)
        elif stage==5 and state=="reviewed":
            # The canonical review receipt must be sealed and the corresponding
            # reviewed library document current. This is NOT self-approval.
            handoff=self.glean.handoff(
                owner,source_id,authorized=True)
            if handoff["status"]!="canonical_wiki_review_verified":
                raise PermissionError("reviewed source must have accepted Wiki lineage")
        else:
            raise PermissionError("source in active extraction or analysis cannot renew")
        row=self.db.execute(
            "SELECT body,digest FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=0",
            (owner,source_id)).fetchone()
        if row is None:
            raise PermissionError("source has no original policy receipt")
        old=json.loads(row[0])
        if canonical_digest(old)!=row[1] or old.get("stage")!="policy":
            raise ValueError("old policy receipt tampered")
        return source,seed,job,current,old,row[1],source_row[0]

    def request(self, owner: str, source_id: str, *,
                now: int, expected_operations_digest: str, reason: str,
                authorized: bool, trusted_supervisor: bool) -> dict:
        """Fenced, atomic old-policy retirement; never issues a new permission."""
        _auth(owner,authorized)
        _integer(now,"policy renewal clock",0,_MAX_EPOCH)
        if trusted_supervisor is not True:
            raise PermissionError("verified external supervisor required")
        if reason not in {"expired_policy","scheduled_revisit"}:
            raise ValueError("explicit renewal reason required")
        if (not isinstance(expected_operations_digest,str)
            or len(expected_operations_digest)!=64
            or any(ch not in "0123456789abcdef" for ch in expected_operations_digest)):
            raise ValueError("exact operation head digest required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            source,seed,job,chain,old,old_digest,source_digest = self._proof(owner,source_id,now)
            current=chain[-1]
            if current["digest"]!=expected_operations_digest:
                raise ValueError("policy renewal compare-and-swap failed")
            if current["state"] not in {"scheduled","retry_wait","completed"}:
                raise PermissionError("live, crashed or manually held source cannot renew")
            if self.db.execute(
                "SELECT 1 FROM dragon_source_ops_heads_v1 WHERE host=? "
                "AND state IN ('leased','quarantined','policy_hold') LIMIT 1",
                (current["host"],)).fetchone():
                raise PermissionError("host has unresolved worker or manual policy hold")
            old_expiry=old["evidence"]["expires_at"]
            if reason=="expired_policy":
                if job[0]!=1 or old_expiry>now:
                    raise PermissionError("only expired policy-stage-one sources qualify")
                if current["state"]=="completed":
                    raise PermissionError("completed source requires periodic review")
            else:
                if job[0]!=5 or current["state"]!="completed":
                    raise PermissionError("revisit requires independently reviewed source")
                recent=self.captures._history(owner,source_id)
                if not recent:
                    raise ValueError("cannot revisit source without captured history")
                due=recent[-1]["observed_at"]+seed["suggested_review_days"]*86400
                if now<due:
                    raise PermissionError("source not yet scheduled for review")
            steps=self.db.execute(
                "SELECT body,digest FROM dragon_almanac_steps "
                "WHERE owner=? AND source=? ORDER BY stage",
                (owner,source_id)).fetchall()
            for raw,digest in steps:
                payload=json.loads(raw)
                if canonical_digest(payload)!=digest or payload.get("at",_MAX_EPOCH+1)>now:
                    raise ValueError("unable to archive invalid or future policy lineage")
            event=self.ops._append(
                owner,source_id,current["host"],"policy_recheck",
                now=now,details={
                    "reason":reason,"old_policy_receipt":old_digest,
                    "old_policy_expires_at":old_expiry,
                    "old_source_stage":job[0],
                    "trusted_supervisor_required":True,
                })
            for raw,digest in steps:
                self.db.execute(
                    "INSERT OR IGNORE INTO dragon_almanac_archived_steps "
                    "VALUES(?,?,?,?,?)",(owner,source_id,raw,digest,now))
            self.db.execute(
                "DELETE FROM dragon_almanac_steps WHERE owner=? AND source=?",
                (owner,source_id))
            self.db.execute(
                "UPDATE dragon_almanac_jobs SET stage=0,state='pending',"
                "attempts=0,token=NULL,expires=NULL,input_digest=?,started=? "
                "WHERE owner=? AND source=?",
                (source_digest,now,owner,source_id))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "owner":owner,"source_id":source_id,
            "status":"awaiting_new_independent_policy_review",
            "renewal_digest":event["digest"],
            "previous_policy_digest":old_digest,
            "review_required":True,"network_requests":0,
            "crawler_authorized":False,"training_authorized":False,
        }

    def rearm(self, owner: str, source_id: str, *, now: int,
              expected_renewal_digest: str, authorized: bool,
              trusted_supervisor: bool) -> dict:
        """Admit fresh independent policy stage without resetting host cooldown."""
        _auth(owner,authorized)
        _integer(now,"rearm clock",0,_MAX_EPOCH)
        if trusted_supervisor is not True:
            raise PermissionError("external source-policy supervisor required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current=self.ops._history(owner,source_id)
            if (not current or current[-1]["state"]!="policy_recheck"
                or current[-1]["digest"]!=expected_renewal_digest):
                raise ValueError("stale or missing explicit policy renewal identity")
            registered,_=self.captures._source(owner,source_id)
            row=self.db.execute(
                "SELECT stage,state,input_digest FROM dragon_almanac_jobs "
                "WHERE owner=? AND source=?",(owner,source_id)).fetchone()
            if row is None or row[0]!=1 or row[1]!="pending":
                raise PermissionError("new independent policy-stage receipt required")
            new_policy=self.captures._policy(
                owner,source_id,registered["url"],observed_at=now)
            if new_policy==current[-1]["details"]["old_policy_receipt"]:
                raise ValueError("renewal must have genuinely new policy receipt")
            latest=self.db.execute(
                "SELECT body FROM dragon_almanac_steps WHERE owner=? AND source=? AND stage=0",
                (owner,source_id)).fetchone()
            if latest is None:
                raise ValueError("missing new policy receipt")
            receipt=json.loads(latest[0])
            if receipt.get("at",0)<=current[-1]["at"]:
                raise PermissionError("independent new policy review must be newer")
            host=current[-1]["host"]
            if self.db.execute(
                "SELECT 1 FROM dragon_source_ops_heads_v1 "
                "WHERE host=? AND state IN ('leased','quarantined','policy_hold') LIMIT 1",
                (host,)).fetchone():
                raise PermissionError("host unresolved or manually held")
            host_cooldown=self.db.execute(
                "SELECT next_at FROM dragon_source_host_cooldown_v1 WHERE host=?",
                (host,)).fetchone()
            ready=max(now,host_cooldown[0] if host_cooldown else now)
            event=self.ops._append(
                owner,source_id,host,"scheduled",now=now,ready_at=ready,
                details={"renewed_policy_receipt":new_policy,
                         "renewal_request_digest":expected_renewal_digest,
                         "independent_policy_stage_completed":True})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "source_id":source_id,"status":"scheduled_after_policy_revalidation",
            "operations_digest":event["digest"],"next_ready_at":ready,
            "network_requests":0,"source_rights_granted_by_this_method":False,
            "model_training_authorized":False,
        }


    def pending(self, owner: str, *, authorized: bool,
                limit: int=50) -> dict:
        """Read-only, proof-checked renewal queue. Does not grant site rights."""
        _auth(owner,authorized)
        _integer(limit,"renewal queue limit",1,100)
        rows=self.db.execute(
            "SELECT source FROM dragon_source_ops_heads_v1 "
            "WHERE owner=? AND state='policy_recheck' "
            "ORDER BY source LIMIT ?",(owner,limit+1)
        ).fetchall()
        if len(rows)>limit:
            raise ValueError("bounded renewal queue page required")
        items=[]
        for (sid,) in rows:
            current=self.ops._history(owner,sid)[-1]
            source,_=self.captures._source(owner,sid)
            job=self.db.execute(
                "SELECT stage,state FROM dragon_almanac_jobs WHERE owner=? AND source=?",
                (owner,sid)).fetchone()
            if job not in {(0,"pending"),(1,"pending")}:
                raise ValueError("renewal queue and canonical stage disagree")
            items.append({
                "source_id":sid,"url":source["url"],
                "renewal_digest":current["digest"],
                "renewal_reason":current["details"]["reason"],
                "policy_stage":job[0],
                "policy_review_required":job[0]==0,
                "supervisor_rearm_required":True,
            })
        return {"schema":"skeleton.dragon.policy_renewal_queue.v1",
                "owner":owner,"items":items,
                "network_requests":0,"crawler_authorized":False,
                "training_authorized":False}
