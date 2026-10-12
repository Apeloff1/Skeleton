"""Durable, fail-closed operations for Dragon's article hatchling.

The signed nest and live global scheduler still control resource admission.
This store adds cross-process source/host fencing, durable per-host cooldown,
crash quarantine, audit history, and independent-review handoff. It never
executes I/O, restarts unknown workers, or grants source/model permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from urllib.parse import urlsplit

from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_technical_source_captures import DragonSourceCaptures
from .reviewed_knowledge import _integer

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_EVENTS = 128
_MAX_OWNER_QUEUE = 4096


def _epoch(utc: str) -> int:
    if not isinstance(utc, str) or not utc.endswith("Z"):
        raise ValueError("canonical UTC ticket required")
    try:
        dt = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("canonical UTC ticket required") from exc
    return int(dt.timestamp())


def _ticket_digest(ticket: HatchlingWorkerTicket) -> str:
    return canonical_digest({
        "owner": ticket.owner, "lane": ticket.lane,
        "source_id": ticket.source_id, "url": ticket.source_url,
        "task_id": ticket.task_id, "assignment": ticket.assignment_digest,
        "issued_at": ticket.issued_at, "expires_at": ticket.expires_at,
    })


@dataclass(frozen=True, slots=True)
class DurableSourceLease:
    owner: str
    source_id: str
    host: str
    ticket_digest: str
    expires_at: int
    audit_digest: str
    acquisition_authorized: bool = False
    model_training_authorized: bool = False


class DragonSourceOperations:
    """Owner-bound, append-only scheduling with host-level durable fencing."""

    def __init__(self, captures: DragonSourceCaptures):
        if not isinstance(captures, DragonSourceCaptures):
            raise TypeError("canonical Dragon capture store required")
        self.captures = captures
        self.db = captures.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_ops_events_v1(
          owner TEXT NOT NULL, source TEXT NOT NULL, seq INTEGER NOT NULL,
          body TEXT NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(owner,source,seq))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_ops_heads_v1(
          owner TEXT NOT NULL, source TEXT NOT NULL, host TEXT NOT NULL,
          state TEXT NOT NULL, ready_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL, ticket_digest TEXT,
          seq INTEGER NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(owner,source))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_host_cooldown_v1(
          host TEXT PRIMARY KEY, next_at INTEGER NOT NULL)""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_source_ops_hosts_v1
          ON dragon_source_ops_heads_v1(host,state,expires_at)""")

    def _history(self, owner: str, source: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT seq,body,digest FROM dragon_source_ops_events_v1 "
            "WHERE owner=? AND source=? ORDER BY seq LIMIT ?",
            (owner,source,_MAX_EVENTS+1)).fetchall()
        if len(rows)>_MAX_EVENTS:
            raise ValueError("source operation journal exhausted")
        history=[];parent=None
        allowed={
            None:{"scheduled"},
            "scheduled":{"leased"},
            "retry_wait":{"leased"},
            "leased":{"completed","retry_wait","quarantined","policy_hold"},
            "quarantined":{"acknowledged_stop"},
            "policy_hold":set(),
            "acknowledged_stop":{"scheduled"},
            "completed":set(),
        }
        for i,(seq,raw,digest) in enumerate(rows):
            if not isinstance(raw,str) or len(raw.encode())>4096:
                raise ValueError("oversized source operation event")
            e=json.loads(raw)
            if (not isinstance(e,dict) or seq!=i
                or e.get("seq")!=i or e.get("owner")!=owner
                or e.get("source_id")!=source
                or e.get("parent_digest")!=parent
                or canonical_digest(e)!=digest
                or e.get("state") not in allowed[history[-1]["state"] if history else None]
                or e.get("network_authorized") is not False
                or e.get("training_authorized") is not False
                or type(e.get("at")) is not int
                or (history and e["at"] < history[-1]["at"])):
                raise ValueError("source operation journal integrity invalid")
            if e["state"] in ("leased","retry_wait","quarantined") and (
                type(e.get("ready_at")) is not int
                or type(e.get("expires_at")) is not int
            ):
                raise ValueError("invalid durable lease scheduling")
            history.append({**e,"digest":digest})
            parent=digest
        head=self.db.execute(
            "SELECT host,state,ready_at,expires_at,ticket_digest,seq,digest "
            "FROM dragon_source_ops_heads_v1 WHERE owner=? AND source=?",
            (owner,source)).fetchone()
        if not history:
            if head is not None:
                raise ValueError("source operations head without history")
            return []
        last=history[-1]
        if (head is None or head!=(last["host"],last["state"],
            last.get("ready_at",0),last.get("expires_at",0),
            last.get("ticket_digest"),last["seq"],last["digest"])):
            raise ValueError("source operation head mismatch")
        return history

    def _append(self, owner: str, source: str, host: str, state: str,
                *, now: int, ready_at: int=0, expires_at: int=0,
                ticket_digest: str | None=None, details: dict | None=None) -> dict:
        history=self._history(owner,source)
        if len(history)>=_MAX_EVENTS:
            raise ValueError("source operation event retention limit")
        prior=history[-1]["digest"] if history else None
        body={
            "schema":"skeleton.dragon.source_ops.v1",
            "owner":owner,"source_id":source,"host":host,
            "state":state,"seq":len(history),"parent_digest":prior,
            "at":now,"ready_at":ready_at,"expires_at":expires_at,
            "ticket_digest":ticket_digest,"details":details or {},
            "network_authorized":False,"training_authorized":False,
        }
        # Validate the transition BEFORE writing. Transaction state protects
        # cross-process concurrent admissions and host cooldown.
        valid={
            None:{"scheduled"},"scheduled":{"leased"},
            "retry_wait":{"leased"},"leased":{"completed","retry_wait","quarantined","policy_hold"},
            "quarantined":{"acknowledged_stop"},"policy_hold":set(),
            "acknowledged_stop":{"scheduled"},"completed":set(),
        }
        before=history[-1]["state"] if history else None
        if state not in valid[before]:
            raise ValueError("illegal or replayed source operation transition")
        if history and now<history[-1]["at"]:
            raise ValueError("nonmonotonic source operation clock")
        if history and history[-1]["host"]!=host:
            raise ValueError("source hostname changed after scheduling")
        digest=canonical_digest(body)
        self.db.execute("INSERT INTO dragon_source_ops_events_v1 VALUES(?,?,?,?,?)",
                        (owner,source,len(history),canonical_json(body),digest))
        self.db.execute(
            """INSERT INTO dragon_source_ops_heads_v1 VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(owner,source) DO UPDATE SET
               host=excluded.host,state=excluded.state,ready_at=excluded.ready_at,
               expires_at=excluded.expires_at,ticket_digest=excluded.ticket_digest,
               seq=excluded.seq,digest=excluded.digest""",
            (owner,source,host,state,ready_at,expires_at,ticket_digest,len(history),digest))
        return {**body,"digest":digest}

    def schedule(self, owner: str, source_id: str, *, now: int,
                 ready_at: int, authorized: bool, trusted_worker: bool) -> dict:
        _auth(owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted source scheduling required")
        _integer(now,"schedule clock",0,4_102_444_800)
        _integer(ready_at,"scheduled date",now,4_102_444_800)
        source,_=self.captures._source(owner,source_id)
        host=urlsplit(source["url"]).hostname
        if not host:
            raise ValueError("registered HTTPS host required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.captures._policy(owner,source_id,source["url"],observed_at=now)
            row=self.db.execute(
                "SELECT stage,state FROM dragon_almanac_jobs WHERE owner=? AND source=?",
                (owner,source_id)).fetchone()
            if row!=(1,"pending"):
                raise PermissionError("only ready canonical fetch-stage sources may be scheduled")
            if self.db.execute(
                "SELECT COUNT(*) FROM dragon_source_ops_heads_v1 WHERE owner=?",
                (owner,)).fetchone()[0]>=_MAX_OWNER_QUEUE:
                raise ValueError("owner schedule budget exceeded")
            old=self._history(owner,source_id)
            if old:
                if old[-1]["state"]=="scheduled" and old[-1]["ready_at"]==ready_at:
                    self.db.execute("COMMIT")
                    return {"source_id":source_id,"status":"already_scheduled",
                            "event_digest":old[-1]["digest"]}
                if old[-1]["state"]!="acknowledged_stop":
                    raise ValueError("source is already queued, active, or completed")
            event=self._append(owner,source_id,host,"scheduled",
                               now=now,ready_at=ready_at)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"source_id":source_id,"status":"scheduled",
                "event_digest":event["digest"],"network_requests":0,
                "training_authorized":False}

    def attach(self, ticket: HatchlingWorkerTicket,
               admission: DragonNestWorkerAdmission, *, now: int,
               authorized: bool, trusted_worker: bool,
               host_delay_seconds: int=5) -> DurableSourceLease:
        if not isinstance(ticket,HatchlingWorkerTicket) or ticket.lane!="article":
            raise TypeError("article hatchling resource ticket required")
        _auth(ticket.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted lease binding required")
        _integer(now,"lease time",0,4_102_444_800)
        _integer(host_delay_seconds,"host spacing",1,300)
        if (not isinstance(admission,DragonNestWorkerAdmission)
            or admission.feed.almanacs is not self.captures.a
            or admission.session.tenant!=ticket.owner
            or ticket.task_id not in admission.active
            or admission.active[ticket.task_id][0]!=ticket):
            raise PermissionError("live exact global-resource grant required")
        issued,expires=_epoch(ticket.issued_at),_epoch(ticket.expires_at)
        if not issued<=now<expires:
            raise ValueError("stale worker resource ticket")
        source,_=self.captures._source(ticket.owner,ticket.source_id)
        if source["url"]!=ticket.source_url:
            raise PermissionError("worker URL differs from reviewed canonical source")
        host=__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(source["url"]).hostname
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.captures._policy(ticket.owner,ticket.source_id,
                                  ticket.source_url,observed_at=now)
            state=self._history(ticket.owner,ticket.source_id)
            if not state or state[-1]["state"] not in ("scheduled","retry_wait"):
                raise PermissionError("source has no runnable durable proposal")
            if state[-1]["ready_at"]>now:
                raise PermissionError("scheduled source delay not elapsed")
            check=self.db.execute(
                "SELECT next_at FROM dragon_source_host_cooldown_v1 WHERE host=?",
                (host,)).fetchone()
            if check and check[0]>now:
                raise PermissionError("durable host crawl spacing active")
            if self.db.execute(
                """SELECT 1 FROM dragon_source_ops_heads_v1 WHERE host=?
                   AND state IN ('leased','quarantined') LIMIT 1""",
                (host,)).fetchone():
                raise PermissionError("host already has an unresolved live or crashed worker")
            if self.db.execute(
                """SELECT 1 FROM dragon_source_ops_heads_v1
                   WHERE owner=? AND state='leased' LIMIT 1""",
                (ticket.owner,)).fetchone():
                raise PermissionError("owner already has a source lease")
            td=_ticket_digest(ticket)
            event=self._append(ticket.owner,ticket.source_id,host,"leased",
                               now=now,ready_at=now,expires_at=expires,
                               ticket_digest=td,
                               details={"lane":"article","ticket_task_id":ticket.task_id})
            self.db.execute(
                """INSERT INTO dragon_source_host_cooldown_v1(host,next_at)
                   VALUES(?,?) ON CONFLICT(host) DO UPDATE SET next_at=excluded.next_at""",
                (host,now+host_delay_seconds))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return DurableSourceLease(ticket.owner,ticket.source_id,host,td,expires,
                                  event["digest"])

    def authorize_chunk(self, ticket: HatchlingWorkerTicket,
                        admission: DragonNestWorkerAdmission, *,
                        sample, at: str, idle_since: str, now_seconds: float,
                        authorized: bool, trusted_worker: bool,
                        consented: bool,article_consent: bool,
                        video_consent: bool,updates_consent: bool) -> bool:
        if not isinstance(ticket,HatchlingWorkerTicket):
            raise TypeError("worker ticket required")
        _auth(ticket.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted fenced chunk inspection required")
        now=_epoch(at)
        chain=self._history(ticket.owner,ticket.source_id)
        if (not chain or chain[-1]["state"]!="leased"
            or chain[-1]["ticket_digest"]!=_ticket_digest(ticket)
            or now>=chain[-1]["expires_at"]):
            return False
        if not admission.authorize_chunk(
            ticket,sample=sample,at=at,idle_since=idle_since,
            now_seconds=now_seconds,authorized=True,trusted_worker=True,
            consented=consented,article_consent=article_consent,
            video_consent=video_consent,updates_consent=updates_consent):
            return False
        try:
            self.captures._policy(ticket.owner,ticket.source_id,
                                  ticket.source_url,observed_at=now)
        except (ValueError,PermissionError):
            return False
        return True

    def release(self,ticket: HatchlingWorkerTicket,
                admission: DragonNestWorkerAdmission, *,
                now: int,capture_digest: str | None,
                authorized: bool,trusted_worker: bool,
                deferred_seconds: int | None = None,
                deferred_reason: str | None = None,
                policy_hold: bool = False) -> dict:
        """Call only AFTER synchronous worker exit + global-resource stop ack.

        Long robots crawl-delay is retained in SQLite, not slept through on a
        short-lived resource grant. A delay exceeding 7 days is quarantined as
        a manual policy hold; it is never retried automatically.
        """
        if not isinstance(ticket,HatchlingWorkerTicket):
            raise TypeError("typed article ticket required")
        _auth(ticket.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted stop acknowledgement required")
        _integer(now,"worker release time",0,4_102_444_800)
        if type(policy_hold) is not bool:
            raise ValueError("explicit policy-hold flag required")
        if policy_hold:
            if deferred_seconds is not None or deferred_reason!="robots_delay_exceeds_limit" or capture_digest is not None:
                raise ValueError("unbounded robots delay requires manual hold")
        if deferred_seconds is not None:
            _integer(deferred_seconds,"real robots delay",6,604800)
            if deferred_reason!="robots_crawl_delay" or capture_digest is not None:
                raise ValueError("only uncaptured, observed robots delay can defer")
        elif deferred_reason is not None and not policy_hold:
            raise ValueError("deferral reason without measured delay")
        if (not isinstance(admission,DragonNestWorkerAdmission)
            or admission.feed.almanacs is not self.captures.a
            or admission.session.tenant!=ticket.owner
            or ticket.task_id in admission.active):
            raise PermissionError("actual resource stop must precede journal release")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            chain=self._history(ticket.owner,ticket.source_id)
            if (not chain or chain[-1]["state"]!="leased"
                or chain[-1]["ticket_digest"]!=_ticket_digest(ticket)):
                raise ValueError("durable lease missing, replaced or already released")
            host=chain[-1]["host"]
            if capture_digest is not None:
                if not isinstance(capture_digest,str) or not _HASH.fullmatch(capture_digest):
                    raise ValueError("captured source digest required")
                evidence=self.captures._history(ticket.owner,ticket.source_id)
                if (not evidence or evidence[-1]["digest"]!=capture_digest
                    or evidence[-1]["observed_at"]<chain[-1]["at"]
                    or evidence[-1]["source_url"]!=ticket.source_url):
                    raise ValueError("successful outcome needs matching captured content")
                evt=self._append(
                    ticket.owner,ticket.source_id,host,"completed",now=now,
                    details={"capture_digest":capture_digest,
                             "review_status":"independent_review_pending"})
            elif policy_hold:
                evt=self._append(
                    ticket.owner,ticket.source_id,host,"policy_hold",now=now,
                    details={"reason":"robots_delay_exceeds_limit",
                             "stop_acknowledged":True,
                             "manual_rights_review_required":True})
            else:
                attempts=sum(e["state"]=="leased" for e in chain)
                delay=(deferred_seconds if deferred_seconds is not None
                       else min(3600,30*(2**min(attempts-1,6))))
                if now+delay>4_102_444_800:
                    raise ValueError("delay passes supported epoch ceiling")
                evt=self._append(
                    ticket.owner,ticket.source_id,host,"retry_wait",
                    now=now,ready_at=now+delay,
                    details={"retry_number":attempts,
                             "stop_acknowledged":True,
                             "retry_cause":deferred_reason or "bounded_worker_retry",
                             "robots_delay_seconds":deferred_seconds})
            if deferred_seconds is not None or policy_hold:
                cooldown=self.db.execute(
                    "SELECT next_at FROM dragon_source_host_cooldown_v1 "
                    "WHERE host=?",(host,)).fetchone()
                next_ready=max((4_102_444_800 if policy_hold else now+deferred_seconds),
                               cooldown[0] if cooldown else 0)
                self.db.execute(
                    """INSERT INTO dragon_source_host_cooldown_v1(host,next_at)
                       VALUES(?,?) ON CONFLICT(host)
                       DO UPDATE SET next_at=max(next_at,excluded.next_at)""",
                    (host,next_ready))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"state":evt["state"],"event_digest":evt["digest"],
                "next_ready_at":evt["ready_at"],
                "review_required":evt["state"]=="completed",
                "manual_policy_review_required":evt["state"]=="policy_hold",
                "network_authorized":False,"training_authorized":False}

    def quarantine_expired(self, owner: str, *, now: int,
                           authorized: bool,trusted_supervisor: bool) -> dict:
        """Fence expired workers; NEVER release resources on a timeout alone."""
        _auth(owner,authorized)
        if trusted_supervisor is not True:
            raise PermissionError("supervisor authentication required")
        _integer(now,"recovery time",0,4_102_444_800)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self.db.execute(
                """SELECT source,host FROM dragon_source_ops_heads_v1
                   WHERE owner=? AND state='leased' AND expires_at<=?
                   ORDER BY source LIMIT 101""",(owner,now)).fetchall()
            if len(rows)>100:
                raise ValueError("recovery pass too large")
            quarantined=[]
            for source,host in rows:
                event=self._append(owner,source,host,"quarantined",now=now,
                    ready_at=now,expires_at=now,
                    ticket_digest=self._history(owner,source)[-1]["ticket_digest"],
                    details={"stop_verified":False,
                             "global_resource_release_claimed":False})
                quarantined.append({"source_id":source,"event_digest":event["digest"]})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"quarantined":quarantined,"resources_released":0,
                "network_requests":0}

    def confirm_recovered(self,owner:str,source_id:str,*,now:int,
                          external_stop_receipt:str,authorized:bool,
                          trusted_supervisor:bool,worker_stopped:bool,
                          resources_reconciled:bool) -> dict:
        """Requires independent supervisor proof of real process/grant cleanup."""
        _auth(owner,authorized)
        _integer(now,"stop verified time",0,4_102_444_800)
        if (trusted_supervisor is not True or worker_stopped is not True
            or resources_reconciled is not True):
            raise PermissionError("independent process-stop and grant reconciliation required")
        if (not isinstance(external_stop_receipt,str)
            or not _HASH.fullmatch(external_stop_receipt)):
            raise ValueError("bounded external supervisor receipt required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old=self._history(owner,source_id)
            if not old or old[-1]["state"]!="quarantined":
                raise ValueError("source has no quarantined lease")
            event=self._append(owner,source_id,old[-1]["host"],
                               "acknowledged_stop",now=now,
                               details={"supervisor_stop_receipt":external_stop_receipt})
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"status":"ready_for_new_policy_review","digest":event["digest"],
                "resource_release_verified_externally":True,
                "training_authorized":False}

    def inspect(self,owner:str,source_id:str,*,authorized:bool)->dict:
        _auth(owner,authorized)
        self.captures._source(owner,source_id)
        chain=self._history(owner,source_id)
        if not chain:
            return {"owner":owner,"source_id":source_id,"state":"not_scheduled"}
        final=chain[-1]
        return {
            "owner":owner,"source_id":source_id,
            "state":final["state"],"host":final["host"],
            "next_ready_at":final["ready_at"],
            "lease_expires_at":final["expires_at"],
            "event_count":len(chain),"head_digest":final["digest"],
            "independent_review_pending":final["state"]=="completed",
            "network_authorized":False,"training_authorized":False,
        }

    def review_queue(self,owner:str,*,authorized:bool,limit:int=50)->dict:
        _auth(owner,authorized)
        _integer(limit,"review queue limit",1,100)
        rows=self.db.execute(
            """SELECT source FROM dragon_source_ops_heads_v1
               WHERE owner=? AND state='completed'
               ORDER BY source LIMIT ?""",(owner,limit+1)).fetchall()
        if len(rows)>limit:
            raise ValueError("review queue page requires smaller permitted scope")
        items=[]
        for (source,) in rows:
            last=self._history(owner,source)[-1]
            captured=last["details"]["capture_digest"]
            packet=self.captures.review_packet(owner,source,authorized=True)
            if packet is None or packet["capture_digest"]!=captured:
                raise ValueError("review queue capture custody invalid")
            items.append({
                "source_id":source,"capture_digest":captured,
                "change":packet["change"],
                "observed_at":packet["observed_at"],
                "review_required":packet["source_review_needed"],
                "independent_review_approved":False,
            })
        return {"owner":owner,"items":items,"network_requests":0,
                "model_training_authorized":False}


    def ready_candidates(self, owner: str, *, now: int, authorized: bool,
                         limit: int=32) -> tuple[str, ...]:
        """Read-only, fenced admission inventory, not an execution grant.

        Waited retries become eligible only once their backoff AND per-host
        cooldown have elapsed. Stale active leases require supervisor
        quarantine; they are NEVER automatically released here.
        """
        _auth(owner,authorized)
        _integer(now,"source scheduling clock",0,4_102_444_800)
        _integer(limit,"source inventory limit",1,64)
        entries=self.db.execute(
            """SELECT source FROM dragon_source_ops_heads_v1
               WHERE owner=? AND state IN ('scheduled','retry_wait')
               AND ready_at<=? ORDER BY ready_at,source LIMIT ?""",
            (owner,now,_MAX_OWNER_QUEUE+1)
        ).fetchall()
        if len(entries)>_MAX_OWNER_QUEUE:
            raise ValueError("too many queued sources; operator intervention required")
        # Never admit one more worker for an owner with a crashed, still
        # unaccounted, or live worker. No process manager proves otherwise.
        if self.db.execute(
            """SELECT 1 FROM dragon_source_ops_heads_v1
               WHERE owner=? AND state IN ('leased','quarantined') LIMIT 1""",
            (owner,)
        ).fetchone():
            return ()
        candidates=[]
        for (sid,) in entries:
            event=self._history(owner,sid)[-1]
            host=event["host"]
            if event["ready_at"]>now:
                continue
            cooldown=self.db.execute(
                "SELECT next_at FROM dragon_source_host_cooldown_v1 WHERE host=?",
                (host,)
            ).fetchone()
            if cooldown and cooldown[0]>now:
                continue
            if self.db.execute(
                """SELECT 1 FROM dragon_source_ops_heads_v1
                   WHERE host=? AND state IN ('leased','quarantined') LIMIT 1""",
                (host,)
            ).fetchone():
                continue
            registered,_=self.captures._source(owner,sid)
            self.captures._policy(owner,sid,registered["url"],observed_at=now)
            row=self.db.execute(
                """SELECT stage,state FROM dragon_almanac_jobs
                   WHERE owner=? AND source=?""",(owner,sid)
            ).fetchone()
            if row!=(1,"pending"):
                continue
            candidates.append(sid)
            if len(candidates)>=limit:
                break
        return tuple(candidates)
