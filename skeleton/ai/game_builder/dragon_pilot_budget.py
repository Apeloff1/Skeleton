"""Cross-process, fail-closed daily attempt budgets for Dragon source pilots.

Budgets count attempts rather than successful documents: failed HTTP, robots
denials, revoked consent and worker crashes still consume a slot.  A restart
cannot manufacture fresh capacity.  This ledger is separate from crawler
rights, operator consent, work scheduling and model knowledge approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_technical_source_captures import DragonSourceCaptures
from .reviewed_knowledge import _integer

_ATTEMPT=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
_HASH=re.compile(r"[0-9a-f]{64}\Z")


class DragonPilotBudget:
    """Durable attempted-acquisition quotas (defaults 8/owner and 2/host/day)."""

    def __init__(self,captures:DragonSourceCaptures, *,
                 owner_daily_limit:int=8,host_daily_limit:int=2):
        if not isinstance(captures,DragonSourceCaptures):
            raise TypeError("canonical owner-scoped capture store required")
        _integer(owner_daily_limit,"owner daily attempts",1,64)
        _integer(host_daily_limit,"host daily attempts",1,16)
        if host_daily_limit>owner_daily_limit:
            raise ValueError("host quota cannot exceed owner quota")
        self.captures=captures
        self.db=captures.db
        self.owner_daily_limit=owner_daily_limit
        self.host_daily_limit=host_daily_limit
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_pilot_attempts_v1(
            owner TEXT NOT NULL, attempt_id TEXT NOT NULL,
            source_id TEXT NOT NULL, host TEXT NOT NULL,
            day TEXT NOT NULL, at INTEGER NOT NULL,
            grant_digest TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(owner,attempt_id))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_pilot_attempt_daily_v1
            ON dragon_pilot_attempts_v1(owner,day,host)""")

    def _day(self,now:int)->str:
        _integer(now,"quota UTC time",0,4_102_444_800)
        return datetime.fromtimestamp(now,timezone.utc).strftime("%Y-%m-%d")

    def _inventory(self,owner:str,day:str)->list[dict]:
        rows=self.db.execute(
            "SELECT attempt_id,source_id,host,day,at,grant_digest,digest "
            "FROM dragon_pilot_attempts_v1 WHERE owner=? AND day=? "
            "ORDER BY at,attempt_id",(owner,day)).fetchall()
        records=[]
        for attempt,source,host,stored_day,at,grant,digest in rows:
            item={"schema":"skeleton.dragon.pilot_attempt.v1",
                  "owner":owner,"attempt_id":attempt,"source_id":source,
                  "host":host,"day":stored_day,"at":at,
                  "grant_digest":grant,
                  "network_permitted_by_quota":False,
                  "training_authorized":False}
            if (stored_day!=day or self._day(at)!=day
                or not _ATTEMPT.fullmatch(attempt)
                or not _HASH.fullmatch(grant)
                or canonical_digest(item)!=digest):
                raise ValueError("source pilot attempt ledger integrity invalid")
            records.append({**item,"digest":digest})
        return records

    def reserve(self,owner:str,source_id:str,*,grant_digest:str,
                attempt_id:str,now:int,authorized:bool)->dict:
        """One attempt is consumed in an IMMEDIATE transaction before I/O.

        Same-id retries never regain quota, even when every HTTP request
        failed. Operators must use a new id for a genuinely new attempt.
        """
        _auth(owner,authorized)
        day=self._day(now)
        if not isinstance(attempt_id,str) or not _ATTEMPT.fullmatch(attempt_id):
            raise ValueError("bounded canonical attempt ID required")
        if not isinstance(grant_digest,str) or not _HASH.fullmatch(grant_digest):
            raise ValueError("exact signed permission receipt required")
        source,_=self.captures._source(owner,source_id)
        host=urlsplit(source["url"]).hostname
        if not host:
            raise ValueError("canonical destination host required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior=self.db.execute(
                "SELECT 1 FROM dragon_pilot_attempts_v1 "
                "WHERE owner=? AND attempt_id=?",(owner,attempt_id)).fetchone()
            if prior:
                raise PermissionError("pilot attempt ID already consumed")
            rows=self._inventory(owner,day)
            if len(rows)>=self.owner_daily_limit:
                raise PermissionError("owner daily research attempt budget exhausted")
            if sum(row["host"]==host for row in rows)>=self.host_daily_limit:
                raise PermissionError("host daily research attempt budget exhausted")
            payload={
                "schema":"skeleton.dragon.pilot_attempt.v1",
                "owner":owner,"attempt_id":attempt_id,
                "source_id":source_id,"host":host,"day":day,
                "at":now,"grant_digest":grant_digest,
                "network_permitted_by_quota":False,
                "training_authorized":False,
            }
            digest=canonical_digest(payload)
            self.db.execute(
                "INSERT INTO dragon_pilot_attempts_v1 VALUES(?,?,?,?,?,?,?,?)",
                (owner,attempt_id,source_id,host,day,now,grant_digest,digest))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "attempt_digest":digest,"owner":owner,
            "source_id":source_id,"day":day,
            "consumed":True,"model_training_authorized":False,
            "network_authorized_by_budget":False,
        }

    def census(self,owner:str,*,now:int,authorized:bool)->dict:
        _auth(owner,authorized)
        day=self._day(now)
        records=self._inventory(owner,day)
        count_hosts={}
        for row in records:
            count_hosts[row["host"]]=count_hosts.get(row["host"],0)+1
        return {
            "schema":"skeleton.dragon.pilot_attempt_census.v1",
            "owner":owner,"day":day,"attempted":len(records),
            "owner_remaining":max(0,self.owner_daily_limit-len(records)),
            "host_attempts":dict(sorted(count_hosts.items())),
            "host_daily_limit":self.host_daily_limit,
            "no_network_requests":True,"model_training_authorized":False,
        }
