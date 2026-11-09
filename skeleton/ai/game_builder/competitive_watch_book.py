"""Durable competitor watch journal: change detection, cadence, priority delivery.

Append-only canonical hash chain; rollback of a source/rights decision never
erases what was previously believed. A periodical crawler/operator may invoke
this journal repeatedly using *new* approved Wiki snapshots. The library
itself does NOT secretly scrape games, run services, access websites, or start
a scheduler on the operator's machine.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import sqlite3
import json

from .contracts import canonical_digest,canonical_json
from .competitive_title_radar import (
    PlannedOriginalTitle,ThreatAssessment,ThreatRadarError,_date,_id,
)
from .competitive_delivery_gate import CompetitiveDeliveryReport
from .game_project_workspace import GameWorkspace

SCHEMA="skeleton.game_builder.competition_watch.v1"


@dataclass(frozen=True,slots=True)
class WatchDelta:
    original_id: str
    as_of: str
    parent_digest: str|None
    event_digest: str
    new_enemies: tuple[str,...]
    still_enemies: tuple[str,...]
    removed_enemies: tuple[str,...]
    watch_ids: tuple[str,...]
    pending_delivery_axes: tuple[str,...]
    next_review_at: str
    recorded_reports: int

    def payload(self):
        return dict(schema=SCHEMA,original_id=self.original_id,
                    as_of=self.as_of,parent_digest=self.parent_digest,
                    event_digest=self.event_digest,
                    new_enemies=list(self.new_enemies),
                    still_enemies=list(self.still_enemies),
                    removed_enemies=list(self.removed_enemies),
                    watch_ids=list(self.watch_ids),
                    pending_delivery_axes=list(self.pending_delivery_axes),
                    next_review_at=self.next_review_at,
                    recorded_reports=self.recorded_reports,
                    actual_background_monitor_running=False,
                    host_scheduler_not_claimed=True,
                    requires_updated_reviewed_wiki_research=True)


class CompetitionWatchBook:
    """Local workbench-scoped WAL; integrity-checked before every state read."""

    def __init__(self,workspace_root: str|Path):
        ws=GameWorkspace(workspace_root)
        folder=ws.root/"competitive_intelligence"
        if folder.is_symlink():
            raise ThreatRadarError("competitive watch directory cannot be a symlink")
        folder.mkdir(exist_ok=True)
        path=folder/"watch.sqlite3"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ThreatRadarError("competitive watch DB cannot be a symlink")
        self.db=sqlite3.connect(str(path),timeout=15,isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS competitive_watch_events(
            original_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            as_of TEXT NOT NULL,
            parent_digest TEXT,
            event_json TEXT NOT NULL,
            digest TEXT NOT NULL,
            PRIMARY KEY(original_id,revision))""")

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def _history(self,original_id):
        _id(original_id)
        raw=self.db.execute(
            "SELECT revision,as_of,parent_digest,event_json,digest "
            "FROM competitive_watch_events WHERE original_id=? ORDER BY revision",
            (original_id,)).fetchall()
        previous=None
        entries=[]
        previous_time=None
        for number,(rev,stamp,parent,encoded,digest) in enumerate(raw):
            try:
                data=json.loads(encoded,object_pairs_hook=self._unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(
                                    ThreatRadarError("invalid nonfinite watch value")))
            except (TypeError,ValueError) as exc:
                raise ThreatRadarError("corrupt unparseable competitive history") from exc
            if (rev!=number or parent!=previous
                    or data.get("schema")!=SCHEMA
                    or data.get("original_id")!=original_id
                    or data.get("revision")!=number
                    or data.get("parent_digest")!=previous
                    or data.get("as_of")!=stamp
                    or canonical_json(data)!=encoded
                    or canonical_digest(data)!=digest):
                raise ThreatRadarError("competitive watch history digest or parent mismatch")
            parsed=_date(stamp)
            if previous_time is not None and parsed<=previous_time:
                raise ThreatRadarError("competitive event timestamp rolled back")
            assessments=data.get("assessments")
            reports=data.get("delivery_reports")
            if (not isinstance(assessments,list) or not isinstance(reports,list)
                    or len(assessments)>128 or len(reports)>128):
                raise ThreatRadarError("competitive watch history contains malformed evidence")
            if any(not isinstance(x,dict) or x.get("original_id")!=original_id
                   for x in assessments):
                raise ThreatRadarError("watch contains unrelated original title")
            if (len({x.get("rival_id") for x in assessments})!=len(assessments)
                    or len({x.get("rival_id") for x in reports})!=len(reports)):
                raise ThreatRadarError("duplicate competitor identities in watch")
            expected={x["rival_id"]:x for x in assessments}
            for r in reports:
                if (not isinstance(r,dict)
                        or r.get("original_id")!=original_id
                        or r.get("watch_digest")!=
                           canonical_digest(expected.get(r.get("rival_id"),{}))):
                    raise ThreatRadarError("competitive delivery not bound to same watch snapshot")
            previous=digest
            previous_time=parsed
            entries.append((data,digest))
        return tuple(entries)

    @staticmethod
    def _unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:
                raise ThreatRadarError("duplicate key in competitive history")
            d[k]=v
        return d

    def history(self,original_id: str,*,authorized: bool):
        if not authorized:
            raise PermissionError("historical competitor watch access requires authorization")
        return self._history(original_id)

    def record(self,planned: PlannedOriginalTitle,
               assessments: tuple[ThreatAssessment,...],
               reports: tuple[CompetitiveDeliveryReport,...]=(), *,
               as_of: str,authorized: bool)->WatchDelta:
        if not authorized:
            raise PermissionError("competitor history updates require operator approval")
        if (not isinstance(planned,PlannedOriginalTitle)
                or type(assessments) is not tuple or not 1<=len(assessments)<=128
                or type(reports) is not tuple or len(reports)>128
                or any(not isinstance(a,ThreatAssessment) for a in assessments)
                or any(not isinstance(r,CompetitiveDeliveryReport) for r in reports)):
            raise ThreatRadarError("full typed radar snapshot and qualified reports required")
        timestamp=_date(as_of)
        assessments=tuple(sorted(assessments,key=lambda x:x.rival_id))
        reports=tuple(sorted(reports,key=lambda x:x.rival_id))
        ids={x.rival_id for x in assessments}
        if (len(ids)!=len(assessments) or len({x.rival_id for x in reports})!=len(reports)
                or any(x.original_id!=planned.title_id or x.as_of!=as_of
                       for x in assessments)
                or any(r.original_id!=planned.title_id or r.rival_id not in ids
                       or r.as_of!=as_of or r.baseline_design_digest!=planned.design_digest
                       or r.watch_digest!=canonical_digest(next(
                           x.payload() for x in assessments if x.rival_id==r.rival_id))
                       for r in reports)):
            raise ThreatRadarError("radar and delivery proofs are not for the same frozen title/snapshot")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            history=self._history(planned.title_id)
            last=history[-1][0] if history else None
            if last is not None:
                if _date(last["as_of"])>=timestamp:
                    raise ThreatRadarError("watch revision must advance time")
                if last["planned_design_digest"]!=planned.design_digest:
                    raise ThreatRadarError("original title redesign needs a new explicit watch baseline")
                previous_ids={x["rival_id"] for x in last["assessments"]}
                if previous_ids!=ids:
                    raise ThreatRadarError("full competitor scope may not silently change or disappear")
            previous_digest=history[-1][1] if history else None
            data=dict(
                schema=SCHEMA,original_id=planned.title_id,
                planned_design_digest=planned.design_digest,
                revision=len(history),parent_digest=previous_digest,
                as_of=as_of,
                assessments=[x.payload() for x in assessments],
                delivery_reports=[x.payload() for x in reports],
                monitoring_source="authorized_offline_Wiki_review",
                no_automatic_host_execution=True)
            serialized=canonical_json(data)
            digest=canonical_digest(data)
            if len(serialized)>800000:
                raise ThreatRadarError("watch state exceeds bounded journal storage")
            self.db.execute(
                "INSERT INTO competitive_watch_events("
                "original_id,revision,as_of,parent_digest,event_json,digest)"
                " VALUES(?,?,?,?,?,?)",
                (planned.title_id,len(history),as_of,previous_digest,
                 serialized,digest))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        old={x["rival_id"] for x in last["assessments"]
             if x["status"]=="enemy"} if last else set()
        new={x.rival_id for x in assessments if x.status=="enemy"}
        due=min(x.next_review_hours for x in assessments)
        next_time=(timestamp+timedelta(hours=due)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pending=tuple(sorted(set(
            d.axis for r in reports for d in r.demands)))
        return WatchDelta(
            planned.title_id,as_of,previous_digest,digest,
            tuple(sorted(new-old)),tuple(sorted(new&old)),
            tuple(sorted(old-new)),tuple(sorted(
                x.rival_id for x in assessments if x.status=="watch")),
            pending,next_time,len(reports))


__all__=["CompetitionWatchBook","WatchDelta"]
