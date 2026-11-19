"""Authenticated append-only campaign saves with atomic optimistic transitions.

Caller-owned private SQLite and a separate key are mandatory for application
use. Records are authenticated, not encrypted. The verified campaign is an
immutable source input. A whole-file rollback or deletion requires an external
trusted head to detect. No automatic retries or migrations are performed.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict,dataclass
from hashlib import sha256
import hmac
import json
import os
import sqlite3
import threading

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle
from skeleton.frontier.payloads import json_snapshot
from skeleton.prood.campaign_world import VirtualCampaign
from skeleton.prood.campaign_play import (
    Action,CampaignState,Transition,MAX_TURNS,genesis,initial_state,transition,verify_state,
)

_HEAD="prood_campaign_head_v1"
_EVENT="prood_campaign_event_v1"
_HEAD_COLUMNS=("scope","slot","campaign","revision","head","state","mac")
_EVENT_COLUMNS=("scope","slot","sequence","request","body","mac")
_MAX_STATE=4096
_MAX_EVENT=8192


class SaveConflict(RuntimeError):
    """Stale optimistic head or conflicting idempotency request."""


class SaveIntegrityError(RuntimeError):
    """Persisted campaign state or event failed authentication/replay."""


class SaveCapacity(RuntimeError):
    """No further durable history can be admitted within policy."""


def _text(value,name):
    if (type(value) is not str or not value or value!=value.strip()
            or len(value.encode("utf-8"))>128 or any(ord(c)<32 or ord(c)==127 for c in value)):
        raise ValueError("invalid "+name)
    return value


def _hex(value):
    if type(value) is not str or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid SHA-256 identity")
    return value


def _encode(value,maximum=_MAX_EVENT):
    result=json.dumps(json_snapshot(value,max_bytes=maximum),sort_keys=True,
                      separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")
    if len(result)>maximum:
        raise ValueError("campaign record exceeds encoded budget")
    return result


def _decode(raw,maximum):
    if type(raw) is not bytes or not 0<len(raw)<=maximum:
        raise ValueError("invalid record bytes")
    result=json.loads(raw)
    if _encode(result,maximum)!=raw:
        raise ValueError("noncanonical campaign record")
    return result


@dataclass(frozen=True,slots=True)
class SaveHead:
    slot:str
    revision:int
    head:str
    state:CampaignState


@dataclass(frozen=True,slots=True)
class SaveReceipt:
    saved:SaveHead
    event:Transition
    replayed:bool


class CampaignSaveStore:
    """One connection and process owner; application supplies access policy."""

    def __init__(self,connection:sqlite3.Connection,*,campaign:VirtualCampaign,scope:str,
                 key:bytes,initialize:bool=True,private_handle:PrivateSQLiteHandle|None=None,
                 max_events:int=MAX_TURNS,max_bytes:int=128<<20,max_slots:int=16):
        if type(campaign) is not VirtualCampaign:
            raise TypeError("canonical campaign required")
        if not isinstance(connection,sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite connection required")
        if type(key) is not bytes or len(key)!=32:
            raise ValueError("independent save custody key required")
        if type(initialize) is not bool:
            raise ValueError("explicit save initialization policy required")
        if type(max_events) is not int or not 1<=max_events<=MAX_TURNS:
            raise ValueError("invalid campaign event ceiling")
        if type(max_bytes) is not int or not 4096<=max_bytes<=256<<20:
            raise ValueError("invalid campaign storage ceiling")
        if type(max_slots) is not int or not 1<=max_slots<=256:
            raise ValueError("invalid campaign slot ceiling")
        if private_handle is not None:
            if type(private_handle) is not PrivateSQLiteHandle or private_handle.connection is not connection:
                raise ValueError("private handle must own exact connection")
            private_handle.assert_current()
        self._db,self._campaign,self._scope,self._key=connection,campaign,_text(scope,"scope"),key
        self._handle=private_handle
        self._pid,self._thread=os.getpid(),threading.get_ident()
        self._closed=False
        self._max_events,self._max_bytes,self._max_slots=max_events,max_bytes,max_slots
        with self._tx(check=False):
            if initialize:
                connection.execute(f"CREATE TABLE IF NOT EXISTS main.{_HEAD} ("
                    "scope TEXT NOT NULL,slot TEXT NOT NULL,campaign TEXT NOT NULL,"
                    "revision INTEGER NOT NULL CHECK(revision>=0),head TEXT NOT NULL,"
                    "state BLOB NOT NULL,mac TEXT NOT NULL,PRIMARY KEY(scope,slot)) WITHOUT ROWID")
                connection.execute(f"CREATE TABLE IF NOT EXISTS main.{_EVENT} ("
                    "scope TEXT NOT NULL,slot TEXT NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>0),"
                    "request TEXT NOT NULL,body BLOB NOT NULL,mac TEXT NOT NULL,"
                    "PRIMARY KEY(scope,slot,sequence),UNIQUE(scope,slot,request)) WITHOUT ROWID")
            self._schema()
            self._capacity()

    def _owner(self):
        if self._closed or self._pid!=os.getpid() or self._thread!=threading.get_ident():
            raise RuntimeError("campaign store owner closed or changed")
        if self._handle is not None:
            self._handle.assert_current()
        if self._db.in_transaction:
            raise RuntimeError("campaign store requires exclusive transaction authority")

    @contextmanager
    def _tx(self,*,check=True):
        self._owner()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if self._handle is not None:
                self._handle.assert_current()
            if check:
                self._schema()
            yield
            if self._handle is not None:
                self._handle.assert_current()
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _schema(self):
        for table,columns,types,pk in (
            (_HEAD,_HEAD_COLUMNS,("TEXT","TEXT","TEXT","INTEGER","TEXT","BLOB","TEXT"),(1,2,0,0,0,0,0)),
            (_EVENT,_EVENT_COLUMNS,("TEXT","TEXT","INTEGER","TEXT","BLOB","TEXT"),(1,2,3,0,0,0)),
        ):
            rows=self._db.execute(f"PRAGMA main.table_xinfo({table})").fetchall()
            if (tuple(row[1] for row in rows)!=columns or
                    tuple(row[2].upper() for row in rows)!=types or
                    tuple(row[3] for row in rows)!=(1,)*len(columns) or
                    tuple(row[5] for row in rows)!=pk or any(row[6]!=0 for row in rows)):
                raise SaveIntegrityError("unexpected campaign save schema")
            if self._db.execute("SELECT 1 FROM main.sqlite_master WHERE type='trigger' AND tbl_name=?",
                                (table,)).fetchone() or self._db.execute(
                    "SELECT 1 FROM temp.sqlite_master WHERE (type='trigger' AND tbl_name=?) OR name=?",
                    (table,table)).fetchone():
                raise SaveIntegrityError("unexpected campaign trigger or temp shadow")
        unique=False
        for row in self._db.execute(f"PRAGMA main.index_list({_EVENT})"):
            if row[2]!=1 or row[4]!=0 or not row[1].isidentifier():
                continue
            columns=tuple(r[2] for r in self._db.execute("SELECT * FROM pragma_index_info(?)",(row[1],)))
            if columns==("scope","slot","request"):
                unique=True
        if not unique:
            raise SaveIntegrityError("campaign request uniqueness missing")

    def _capacity(self,*,events=0,slots=0,extra=0):
        event_count,event_size=self._db.execute(
            f"SELECT COUNT(*),COALESCE(SUM(length(body)+512),0) FROM main.{_EVENT}").fetchone()
        slot_count,slot_size=self._db.execute(
            f"SELECT COUNT(*),COALESCE(SUM(length(state)+512),0) FROM main.{_HEAD}").fetchone()
        if (event_count+events>self._max_events or slot_count+slots>self._max_slots
                or event_size+slot_size+extra>self._max_bytes):
            raise SaveCapacity("campaign save capacity exhausted")

    def _mac(self,domain,identity,raw):
        return hmac.new(self._key,domain+_encode(identity)+sha256(raw).digest(),sha256).hexdigest()

    def _head_mac(self,slot,revision,head,raw):
        return self._mac(b"prood.save.head.v1\0",[self._scope,slot,self._campaign.campaign_id,revision,head],raw)

    def _event_mac(self,slot,seq,request,raw):
        return self._mac(b"prood.save.event.v1\0",[self._scope,slot,self._campaign.campaign_id,seq,request],raw)

    def _request(self,slot,request):
        return hmac.new(self._key,b"prood.save.request.v1\0"+
                        _encode([self._scope,slot,_text(request,"request ID")]),sha256).hexdigest()

    def _state(self,raw):
        state=CampaignState(**_decode(raw,_MAX_STATE))
        verify_state(self._campaign,state)
        return state

    def _head(self,slot):
        if self._db.execute(f"SELECT 1 FROM main.{_HEAD} WHERE scope=? AND slot=? AND "
                            "(length(state)>? OR length(mac)<>64 OR length(head)<>64 OR length(campaign)<>64)",
                            (self._scope,slot,_MAX_STATE)).fetchone():
            raise SaveIntegrityError("oversized or invalid campaign head")
        row=self._db.execute(f"SELECT campaign,revision,head,state,mac FROM main.{_HEAD} WHERE scope=? AND slot=?",
                             (self._scope,slot)).fetchone()
        if row is None:
            if self._db.execute(f"SELECT 1 FROM main.{_EVENT} WHERE scope=? AND slot=? LIMIT 1",
                                (self._scope,slot)).fetchone():
                raise SaveIntegrityError("orphaned campaign history")
            raise KeyError("campaign save unavailable")
        try:
            campaign,rev,head,raw,mac=row
            if campaign!=self._campaign.campaign_id or type(rev) is not int or not 0<=rev<=MAX_TURNS:
                raise ValueError("foreign campaign or revision")
            _hex(head)
            if not hmac.compare_digest(_hex(mac),self._head_mac(slot,rev,head,raw)):
                raise ValueError("head MAC mismatch")
            state=self._state(raw)
            if state.turn!=rev or (rev==0 and (head!=genesis(self._campaign) or state!=initial_state(self._campaign))):
                raise ValueError("head state/revision mismatch")
            return SaveHead(slot,rev,head,state),mac
        except (ValueError,TypeError,UnicodeError,RecursionError) as exc:
            raise SaveIntegrityError("campaign head authentication failed") from exc

    def _event(self,slot,row):
        try:
            seq,request,raw,mac=row
            if type(seq) is not int or not 1<=seq<=MAX_TURNS:
                raise ValueError("invalid event sequence")
            _hex(request)
            if type(raw) is not bytes or len(raw)>_MAX_EVENT:
                raise ValueError("event byte budget exceeded")
            if not hmac.compare_digest(_hex(mac),self._event_mac(slot,seq,request,raw)):
                raise ValueError("event MAC mismatch")
            data=_decode(raw,_MAX_EVENT)
            if type(data) is not dict or set(data)!={"event","state"}:
                raise ValueError("invalid event envelope")
            fields=dict(data["event"])
            fields["action"]=Action(**fields["action"])
            event=Transition(**fields)
            state=CampaignState(**data["state"])
            verify_state(self._campaign,state)
            if event.sequence!=seq or state.turn!=seq:
                raise ValueError("event sequence differs")
            return event,state
        except (ValueError,TypeError,UnicodeError,RecursionError,KeyError) as exc:
            raise SaveIntegrityError("campaign event authentication failed") from exc

    def _read_event(self,slot,*,seq=None,request=None):
        column,value=("sequence",seq) if seq is not None else ("request",request)
        if self._db.execute(f"SELECT 1 FROM main.{_EVENT} WHERE scope=? AND slot=? AND {column}=? "
                            "AND (length(body)>? OR length(request)<>64 OR length(mac)<>64)",
                            (self._scope,slot,value,_MAX_EVENT)).fetchone():
            raise SaveIntegrityError("invalid campaign event length")
        row=self._db.execute(f"SELECT sequence,request,body,mac FROM main.{_EVENT} WHERE scope=? AND slot=? AND {column}=?",
                             (self._scope,slot,value)).fetchone()
        return None if row is None else self._event(slot,row)

    def _tail(self,saved):
        last=self._db.execute(f"SELECT MAX(sequence) FROM main.{_EVENT} WHERE scope=? AND slot=?",
                              (self._scope,saved.slot)).fetchone()[0]
        if (last or 0)!=saved.revision:
            raise SaveIntegrityError("campaign tail differs from head")
        if last:
            row=self._read_event(saved.slot,seq=last)
            if row is None or row[0].event_digest!=saved.head or row[1]!=saved.state:
                raise SaveIntegrityError("campaign tail does not bind head")

    def create(self,slot):
        slot=_text(slot,"slot")
        with self._tx():
            try:
                self._head(slot)
            except KeyError:
                pass
            else:
                raise SaveConflict("campaign slot already exists")
            state,head=initial_state(self._campaign),genesis(self._campaign)
            raw=_encode(asdict(state),_MAX_STATE)
            self._capacity(slots=1,extra=len(raw)+512)
            self._db.execute(f"INSERT INTO main.{_HEAD} VALUES(?,?,?,?,?,?,?)",
                             (self._scope,slot,self._campaign.campaign_id,0,head,raw,self._head_mac(slot,0,head,raw)))
            return SaveHead(slot,0,head,state)

    def audit(self,slot,*,trusted_head=None):
        """Replay the complete bounded history; use on restart before playing."""
        slot=_text(slot,"slot")
        if trusted_head is not None:
            _hex(trusted_head)
        with self._tx():
            self._capacity()
            saved,_=self._head(slot)
            if trusted_head is not None and not hmac.compare_digest(saved.head,trusted_head):
                raise SaveConflict("campaign head differs from independent checkpoint")
            if self._db.execute(f"SELECT 1 FROM main.{_EVENT} WHERE scope=? AND slot=? AND "
                                "(length(body)>? OR length(request)<>64 OR length(mac)<>64) LIMIT 1",
                                (self._scope,slot,_MAX_EVENT)).fetchone():
                raise SaveIntegrityError("oversized campaign event")
            cursor=self._db.execute(f"SELECT sequence,request,body,mac FROM main.{_EVENT} "
                                    "WHERE scope=? AND slot=? ORDER BY sequence",(self._scope,slot))
            state,head=initial_state(self._campaign),genesis(self._campaign)
            for row in cursor:
                if state.turn>=MAX_TURNS:
                    raise SaveIntegrityError("campaign replay budget exhausted")
                event,stored_state=self._event(slot,row)
                try:
                    updated,canonical=transition(self._campaign,state,event.action,previous=head)
                except ValueError as exc:
                    raise SaveIntegrityError("invalid campaign action during replay") from exc
                if canonical!=event or updated!=stored_state:
                    raise SaveIntegrityError("campaign event replay mismatch")
                state,head=updated,event.event_digest
            if saved.state!=state or saved.head!=head:
                raise SaveIntegrityError("campaign replay does not bind saved head")
            return saved

    def step(self,slot,action:Action,*,expected_head:str,request_id:str):
        """Commit transition and head atomically; duplicate request returns original receipt."""
        slot=_text(slot,"slot")
        _hex(expected_head)
        request=self._request(slot,request_id)
        with self._tx():
            saved,old_mac=self._head(slot)
            self._tail(saved)
            prior=self._read_event(slot,request=request)
            if prior is not None:
                event,state=prior
                if event.action!=action or event.previous!=expected_head:
                    raise SaveConflict("campaign request already bound to another action")
                return SaveReceipt(SaveHead(slot,event.sequence,event.event_digest,state),event,True)
            if not hmac.compare_digest(saved.head,expected_head):
                raise SaveConflict("stale campaign head")
            updated,event=transition(self._campaign,saved.state,action,previous=saved.head)
            raw_state=_encode(asdict(updated),_MAX_STATE)
            raw_event=_encode({"event":asdict(event),"state":asdict(updated)})
            self._capacity(events=1,extra=len(raw_event)+len(raw_state)+512)
            self._db.execute(f"INSERT INTO main.{_EVENT} VALUES(?,?,?,?,?,?)",
                (self._scope,slot,event.sequence,request,raw_event,self._event_mac(slot,event.sequence,request,raw_event)))
            mac=self._head_mac(slot,event.sequence,event.event_digest,raw_state)
            changed=self._db.execute(f"UPDATE main.{_HEAD} SET revision=?,head=?,state=?,mac=? WHERE scope=? AND slot=? AND mac=?",
                        (event.sequence,event.event_digest,raw_state,mac,self._scope,slot,old_mac))
            if changed.rowcount!=1:
                raise SaveConflict("campaign head changed during commit")
            return SaveReceipt(SaveHead(slot,event.sequence,event.event_digest,updated),event,False)

    def close(self):
        self._owner()
        self._closed=True
