"""Bounded read-only health and recovery visibility for the Dragon crawler.

No network I/O, scheduler mutation, recovery release or model authority.
Every reported source is checked against its append-only operations history
and its canonical freshness/policy/capture metadata before inclusion.
"""
from __future__ import annotations

from collections import Counter
from .dragon_almanacs import _auth
from .dragon_source_refresh_planner import DragonSourceRefreshPlanner
from .dragon_technical_source_operations import DragonSourceOperations
from .reviewed_knowledge import _integer


class DragonSourceHealth:
    def __init__(self, operations:DragonSourceOperations):
        if not isinstance(operations,DragonSourceOperations):
            raise TypeError("canonical durable operations store required")
        self.operations=operations
        self.db=operations.db
        self.freshness=DragonSourceRefreshPlanner(operations)

    def snapshot(self,owner:str,*,now:int,authorized:bool,
                 limit:int=100,after_source:str|None=None)->dict:
        """Stable cursor paging; checks underlying custody, never grants work."""
        _auth(owner,authorized)
        _integer(now,"health clock",0,4_102_444_800)
        _integer(limit,"health page size",1,100)
        if after_source is not None and (
            type(after_source) is not str
            or len(after_source)>160 or not after_source.startswith("source-")
        ):
            raise ValueError("canonical continuation source required")
        rows=self.db.execute(
            "SELECT source FROM dragon_source_ops_heads_v1 "
            "WHERE owner=? AND source>? ORDER BY source LIMIT ?",
            (owner,after_source or "",limit+1)
        ).fetchall()
        has_more=len(rows)>limit
        ids=[r[0] for r in rows[:limit]]
        states=Counter()
        alarms=[]
        entries=[]
        for sid in ids:
            state=self.operations._history(owner,sid)[-1]
            doc=self.freshness.assess(owner,sid,now=now,authorized=True)
            states[state["state"]]+=1
            warnings=[]
            if state["state"]=="leased" and state["expires_at"]<=now:
                warnings.append("expired_lease_needs_quarantine")
            if state["state"]=="quarantined":
                warnings.append("external_stop_and_grant_reconciliation_required")
            if state["state"]=="policy_hold":
                warnings.append("manual_robots_or_rights_review_required")
            if state["state"]=="policy_recheck":
                warnings.append("awaiting_independent_policy_receipt")
            if doc["reason"]=="policy_expired_requires_recheck":
                warnings.append("source_policy_expired")
            if doc["reason"]=="reviewed_source_revisit_due":
                warnings.append("editorial_revisit_due_not_remote_change")
            if doc["reason"]=="acquisition_pending_independent_review":
                warnings.append("captured_text_pending_review")
            if warnings:
                alarms.append({
                    "source_id":sid,
                    "needs_supervisor":state["state"] in
                        {"leased","quarantined","policy_hold"},
                    "warnings":warnings,
                })
            entries.append({
                "source_id":sid,"state":state["state"],
                "last_event_digest":state["digest"],
                "event_count":state["seq"]+1,
                "last_event_at":state["at"],
                "retry_after":state["ready_at"] if
                    state["state"] in {"retry_wait","scheduled"} else None,
                "lease_expires_at":state["expires_at"] if
                    state["state"] in {"leased","quarantined"} else None,
                "policy_expires_at":doc["policy_expires_at"],
                "captured_revision":doc["latest_capture_digest"],
                "review_reason":doc["reason"],
                "warnings":warnings,
            })
        return {
            "schema":"skeleton.dragon.source_health.v1",
            "owner":owner,"observed_at":now,
            "page_size":len(entries),"has_more":has_more,
            "next_after_source":ids[-1] if has_more and ids else None,
            "state_counts_this_page":dict(sorted(states.items())),
            "alerts_this_page":alarms,"entries":entries,
            "fleet_totals_complete":not has_more and after_source is None,
            "source_health_does_not_prove_external_process_stopped":True,
            "network_requests":0,"workers_started":0,
            "resources_released":0,"training_authorized":False,
        }
