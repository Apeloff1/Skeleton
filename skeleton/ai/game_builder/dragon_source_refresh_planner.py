"""Read-only refresh and permission-expiry diagnosis for Dragon sources.

Editorial review cadence is not evidence that content changed. Recrawl and
model promotions require separate, authorized workers/reviewers.
"""
from __future__ import annotations

import json

from .dragon_almanacs import _auth
from .dragon_technical_source_operations import DragonSourceOperations
from .reviewed_knowledge import _integer


class DragonSourceRefreshPlanner:
    def __init__(self, operations: DragonSourceOperations):
        if not isinstance(operations, DragonSourceOperations):
            raise TypeError("trusted source operations required")
        self.ops=operations
        self.captures=operations.captures
        self.db=operations.db

    def assess(self, owner: str, source_id: str, *,
               now: int, authorized: bool) -> dict:
        _auth(owner,authorized)
        _integer(now,"source freshness clock",0,4_102_444_800)
        source, seed=self.captures._source(owner,source_id)
        operations=self.ops._history(owner,source_id)
        captures=self.captures._history(owner,source_id)
        row=self.db.execute(
            "SELECT stage,state FROM dragon_almanac_jobs "
            "WHERE owner=? AND source=?",(owner,source_id)).fetchone()
        policy=self.db.execute(
            "SELECT body,digest FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=0",(owner,source_id)).fetchone()
        policy_expiry=None
        if policy:
            from .contracts import canonical_digest
            payload=json.loads(policy[0])
            if canonical_digest(payload)!=policy[1]:
                raise ValueError("source policy receipt integrity failed")
            policy_expiry=payload["evidence"]["expires_at"]
        state=operations[-1]["state"] if operations else "unregistered_in_operations"
        last_at=captures[-1]["observed_at"] if captures else None
        review_interval_days=seed["suggested_review_days"]
        due=(last_at+review_interval_days*86400) if last_at is not None else None
        if state in {"leased","quarantined"}:
            reason="active_or_unreconciled_worker"
        elif state=="policy_hold":
            reason="manual_site_policy_hold"
        elif state=="policy_recheck":
            reason="awaiting_independent_policy_review"
        elif state=="completed" and row==(1,"pending"):
            reason="acquisition_pending_independent_review"
        elif state=="completed" and row==(5,"reviewed"):
            reason=("reviewed_source_revisit_due" if due is not None and now>=due
                    else "reviewed_source_cadence_not_due")
        elif policy_expiry is not None and now>=policy_expiry:
            reason="policy_expired_requires_recheck"
        elif state=="retry_wait" and operations[-1]["ready_at"]>now:
            reason="robots_or_retry_cooldown"
        else:
            reason="no_refresh_transition_required"
        return {
            "schema":"skeleton.dragon.source_freshness.v1",
            "owner":owner,"source_id":source_id,
            "url":source["url"],"family":seed["family"],
            "operations_state":state,"almanac_stage":row[0] if row else None,
            "almanac_state":row[1] if row else None,
            "policy_expires_at":policy_expiry,
            "latest_capture_digest":captures[-1]["digest"] if captures else None,
            "latest_capture_at":last_at,
            "suggested_review_days":review_interval_days,
            "editorial_next_review_at":due,
            "observed_remote_change":False,
            "reason":reason,
            "operator_revalidation_required":reason in {
                "policy_expired_requires_recheck","reviewed_source_revisit_due",
                "manual_site_policy_hold",
            },
            "network_requests":0,"rights_granted":False,
            "training_authorized":False,
        }


    def scan(self, owner: str, *, now: int, authorized: bool,
             limit: int=100) -> dict:
        """Bounded, owner-wide refresh inventory; no network, jobs, or grants."""
        _auth(owner,authorized)
        _integer(now,"refresh census clock",0,4_102_444_800)
        _integer(limit,"refresh scan limit",1,100)
        rows=self.db.execute(
            "SELECT source FROM dragon_source_ops_heads_v1 "
            "WHERE owner=? ORDER BY source LIMIT ?",(owner,limit+1)
        ).fetchall()
        if len(rows)>limit:
            raise ValueError("refresh scan exceeds bounded page; narrow owner batch")
        items=[self.assess(owner,sid,now=now,authorized=True) for (sid,) in rows]
        def priority(x):
            return (0 if x["reason"]=="policy_expired_requires_recheck"
                    else 1 if x["reason"]=="reviewed_source_revisit_due"
                    else 2 if x["reason"]=="manual_site_policy_hold"
                    else 3, x["source_id"])
        items.sort(key=priority)
        return {
            "schema":"skeleton.dragon.source_refresh_census.v1",
            "owner":owner,"tracked_sources":len(items),
            "operator_revalidation_due":sum(
                bool(x["operator_revalidation_required"]) for x in items),
            "policy_expired":sum(
                x["reason"]=="policy_expired_requires_recheck" for x in items),
            "manual_holds":sum(
                x["reason"]=="manual_site_policy_hold" for x in items),
            "items":items,"network_requests":0,
            "queue_modified":False,"training_authorized":False,
        }
