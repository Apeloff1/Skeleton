"""Evidence-based, read-only recrawl priorities for the Dragon hatchlings.

Consumes the existing reviewed source-version and idle-attempt ledgers and
delegates bounded recrawl intervals to the canonical mission scheduler. This
does not authorize HTTP/video access, discover unapproved URLs, mint XP,
train models, or treat guessed volatility as calibrated likelihood.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import json

from .dragon_family import DragonFamily, SourceReceipt, _epoch, _tokens, _utc
from .dragon_mission_scheduler import RecrawlSource, plan_adaptive_recrawls


@dataclass(frozen=True)
class DragonRecrawlPolicy:
    minimum_interval_seconds: float = 3600.
    maximum_interval_seconds: float = 7 * 86400.
    max_source_scan: int = 2000

    def validate(self) -> None:
        for value in (self.minimum_interval_seconds,self.maximum_interval_seconds):
            if type(value) not in (int,float) or not isfinite(value) or value<3600:
                raise ValueError("invalid recrawl interval")
        if self.minimum_interval_seconds>self.maximum_interval_seconds:
            raise ValueError("recrawl interval floor exceeds maximum")
        if type(self.max_source_scan) is not int or not 1<=self.max_source_scan<=10000:
            raise ValueError("invalid recrawl source scan limit")


class DragonFamilyRecrawlPlanner:
    """Owner-locked, no-side-effect source revisit advice.

    Caller retains source-topic admission, native idle signal, consent,
    host rate budget, human rights review and per-source lease ownership.
    The posterior-like volatility index here is an *uncalibrated heuristic*.
    """

    def __init__(self, family: DragonFamily, *,
                 policy: DragonRecrawlPolicy = DragonRecrawlPolicy()):
        if not isinstance(family,DragonFamily) or family.owner_scope is None:
            raise PermissionError("reviewed owner-locked family required")
        if family.approval is None:
            raise PermissionError("canonical source reviewer required")
        policy.validate()
        self.family=family
        self.db=family.db
        self.policy=policy

    def plan(self, owner: str, *, authorized: bool, at: float,
             task_topics: tuple[str,...],
             adjacent_topics: tuple[str,...] = ()) -> dict[str,object]:
        self.family._assert_owner(owner)
        if not authorized:
            raise PermissionError("authenticated recrawl plan required")
        at=_epoch(at)
        direct=set(_tokens(task_topics))
        adjacent=set(_tokens(adjacent_topics))
        if not direct:
            raise ValueError("recrawl planning requires a real task")
        # Only source revisions admitted to canonical Dragon readings may
        # enter the recrawl planner; registered-but-unreviewed URLs cannot.
        rows=self.db.execute("""WITH latest AS (
           SELECT owner,source_id,content_digest,review_digest,observed_at,
             ROW_NUMBER() OVER (PARTITION BY owner,source_id
               ORDER BY observed_at DESC,rowid DESC) AS ordinal
           FROM dragon_family_readings WHERE owner=?
         ), revision_count AS (
           SELECT owner,source_id,COUNT(DISTINCT content_digest) AS n
           FROM dragon_family_readings WHERE owner=? GROUP BY owner,source_id
         )
         SELECT s.source_id,s.url,s.media,s.topics_json,
                l.content_digest,l.review_digest,l.observed_at,rc.n
         FROM dragon_family_sources s JOIN latest l
           ON l.owner=s.owner AND l.source_id=s.source_id AND l.ordinal=1
         JOIN revision_count rc
           ON rc.owner=s.owner AND rc.source_id=s.source_id
         WHERE s.owner=? ORDER BY s.source_id LIMIT ?""",
         (owner,owner,owner,self.policy.max_source_scan)).fetchall()
        # The host creates the lease table when installed. A read-only
        # projection must remain safe even before host installation.
        leases_exist=bool(self.db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='dragon_family_idle_leases'""").fetchone())
        entries=[]
        details={}
        for sid,url,media,topics_json,digest,review,observed,versions in rows:
            tags=set(json.loads(topics_json))
            relevance=1. if tags & direct else .65 if tags & adjacent else 0.
            if relevance==0 or observed>at:
                continue
            if self.family.approval(SourceReceipt(sid,digest,review,observed)) is not True:
                # A source whose review was withdrawn is not eligible for
                # priority scoring, even when its old digest is still stored.
                continue
            if leases_exist:
                completed,attempts,blocked,unchanged=self.db.execute("""
                    SELECT COALESCE(MAX(last_completed),0),
                           COALESCE(SUM(attempts),0),
                           MAX(last_outcome='policy_blocked'),
                           MAX(last_outcome='unchanged')
                    FROM dragon_family_idle_leases
                    WHERE owner=? AND source_id=?""",(owner,sid)).fetchone()
                if blocked:
                    continue
            else:
                completed,attempts,unchanged=0,0,0
            last_fetched=max(float(observed),float(completed or 0))
            if last_fetched>at:
                continue
            # Derived only from accepted revisions and recorded attempts.
            # This is a conservative ordering score, not model probability.
            volatility=min(1.,max(0.,float(max(0,versions-1)) /
                                    float(max(2,attempts+2))))
            item=RecrawlSource(sid,url,last_fetched,float(observed),
                volatility,relevance,1 if unchanged else 0)
            entries.append(item)
            details[sid]=(media,int(versions),int(attempts),round(volatility,6))
        planned=plan_adaptive_recrawls(tuple(entries),now=at,
            minimum_interval=self.policy.minimum_interval_seconds,
            maximum_interval=self.policy.maximum_interval_seconds,
            max_sources=self.policy.max_source_scan)
        items=[dict(source_id=p.source_id,media=details[p.source_id][0],
            reviewed_revisions=details[p.source_id][1],
            past_attempts=details[p.source_id][2],
            volatility_index=details[p.source_id][3],
            due=p.due,urgency=p.urgency,
            next_due_at=_utc(p.next_due),
            revisit_interval_seconds=p.revisit_interval)
            for p in planned]
        return dict(schema="skeleton.ai.dragon.recrawl_plan.v1",
            at=_utc(at),reviewed_sources=len(items),
            due_sources=sum(1 for row in items if row["due"]),
            uncalibrated_volatility=True,no_network_authority=True,
            items=items)
