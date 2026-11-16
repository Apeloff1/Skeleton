"""Signed cutover and read-only actual startup seams, without production data."""
import asyncio
from dataclasses import replace
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from bson import ObjectId
from bson.int64 import Int64
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from skeleton.app.canonical_writer_cutover import (
    CanonicalWriterCutover, VerifiedWriterCutover, CutoverInventory, WriterCutoverDenied,
    qualify_writer_cutover, inspect_writer_inventory,
)
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

TENANT, ACTOR = "tenant","actor"
KEY = MongoCanonicalSourceEpoch._key(TENANT, ACTOR)
HOSTS = ("primary:27017",)
PRINCIPALS = (("admin","fixture"),("ROLE_BOUNDARY",""),("canonical","readWrite"))

class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False
    def sort(self,*args): return self
    def limit(self,*args): return self
    def max_time_ms(self,*args): return self
    async def close(self): self.closed = True
    async def __aiter__(self):
        for item in self.rows:
            yield dict(item)

class Collection:
    def __init__(self,name,db,rows):
        self.name,self.database,self.rows = name,db,rows
    def with_options(self,**kwargs):
        assert kwargs["read_concern"].level == "majority"
        return self
    def find(self,*args): return Cursor(self.rows)
    def aggregate(self,*args,**kwargs):
        assert kwargs["allowDiskUse"] is False
        return Cursor(self.rows)

class Database:
    name = "canonical"
    def __init__(self):
        self.client = object()
        self.hello = dict(setName="rs0", isWritablePrimary=True, me=HOSTS[0],
            primary=HOSTS[0], hosts=list(HOSTS), electionId=ObjectId(), setVersion=2,
            topologyVersion={"processId":ObjectId(),"counter":Int64(1)})
        self.auth = {"authInfo":{"authenticatedUsers":[{"db":"admin","user":"fixture"}],
                               "authenticatedUserRoles":[{"db":"canonical","role":"readWrite"}]}}
    async def command(self, name):
        return self.hello if name == "hello" else self.auth

def signed(inventory=None,**updates):
    inventory = inventory or CutoverInventory(((KEY,2),),(KEY,))
    now = int(time.time())
    data = dict(authority_id="operator",deployment_id="fixture",source_head="a"*40,
       database_name="canonical", replica_set="rs0", voting_hosts=HOSTS,
       principal_inventory=PRINCIPALS, issued_at=now-1,expires_at=now+300,
       epoch_count=len(inventory.epochs),source_scope_count=len(inventory.source_scopes),
       inventory_sha256=inventory.digest,backup_sha256="b"*64,quiescence_sha256="c"*64,
       external_writer_retirement_sha256="d"*64,storage_provenance_sha256="e"*64)
    data.update(updates)
    plan=CanonicalWriterCutover(**data)
    key=Ed25519PrivateKey.generate()
    return VerifiedWriterCutover(plan,key.sign(plan.canonical_bytes()),"operator","fixture","a"*40,
                                 key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))

def fixture():
    db=Database()
    epoch=object.__new__(MongoCanonicalSourceEpoch)
    epoch._database=db
    epoch._collection=Collection("canonical_source_epochs",db,[
        {"_id":KEY,"tenant_id":TENANT,"actor_id":ACTOR,"phase":"stable","epoch":Int64(2),"writer_token":None}])
    epoch._reader=Collection("canonical_source_epochs",db,[])
    epoch.read_epoch=AsyncMock(return_value=2)
    threads=Collection("conversation_threads",db,[{"_id":{"tenant":TENANT,"actor":ACTOR}}])
    records=Collection("canonical_memory_records",db,[])
    return db,epoch,threads,records

def test_signed_plan_binds_source_and_scope_and_expiry():
    approval=signed()
    raw=json.dumps(approval.plan.document()).encode()
    parsed=CanonicalWriterCutover.parse(raw)
    assert parsed==approval.plan
    with pytest.raises(WriterCutoverDenied):
        replace(approval,source_head="f"*40)
    with pytest.raises(WriterCutoverDenied):
        replace(approval,plan=replace(parsed,epoch_count=2))
    with pytest.raises(WriterCutoverDenied):
        CanonicalWriterCutover.parse(raw[:-1]+b',"authority_id":"operator"}')
    with pytest.raises(WriterCutoverDenied):
        signed(issued_at=int(time.time())-500,expires_at=int(time.time())-1)

def test_read_only_inventory_and_signed_live_gate():
    _,epoch,threads,records=fixture()
    async def run():
        observed=await inspect_writer_inventory(epoch=epoch,threads=threads,records=records)
        assert observed["guarded_local_ai_ready"] is False and observed["writes_performed"] is False
        approval=signed()
        result=await qualify_writer_cutover(approval,epoch=epoch,threads=threads,records=records)
        assert result.digest==observed["inventory_sha256"] and result.matches(approval.plan)
        assert epoch.read_epoch.await_count==2
    asyncio.run(run())

@pytest.mark.parametrize("change",["missing","odd","actor","role","generation","foreign_db","oversize","second_scan"])
def test_cutover_denies_ambiguous_or_unapproved_source(change):
    db,epoch,threads,records=fixture()
    if change=="missing":
        epoch._collection.rows=[]
    elif change=="odd":
        epoch._collection.rows[0]["epoch"]=3
    elif change=="actor":
        records.rows=[{"_id":{"tenant":TENANT,"actor":"uncovered"}}]
    elif change=="role":
        db.auth["authInfo"]["authenticatedUserRoles"][0]["role"]="root"
    elif change=="generation":
        epoch.read_epoch.return_value=4
    elif change=="foreign_db":
        threads.database=Database()
    elif change=="oversize":
        epoch._collection.rows*=2
    elif change=="second_scan":
        async def changed(**kwargs):
            epoch._collection.rows[0]["epoch"]=4
            return 2
        epoch.read_epoch.side_effect=changed
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,threads=threads,records=records))

def test_launch_context_cannot_use_unverified_approval():
    from core.canonical_writer_startup import configure_cutover
    app=SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(WriterCutoverDenied):
        configure_cutover(app,object())
    configure_cutover(app,signed())
    with pytest.raises(WriterCutoverDenied):
        configure_cutover(app,signed())

def test_backend_lifespan_admission_never_swallows_cutover_error(monkeypatch):
    from core import canonical_writer_startup as startup
    app=SimpleNamespace(state=SimpleNamespace())
    startup.configure_cutover(app,signed())
    db,epoch,threads,records=fixture()
    conversation=SimpleNamespace(threads=threads,canonical_source_epoch=None)
    memory=SimpleNamespace(records=records,canonical_source_epoch=None)
    writer=SimpleNamespace(repository=memory)
    monkeypatch.setattr(startup,"_owners",lambda:(db,conversation,memory,writer))
    monkeypatch.setattr(startup,"MongoCanonicalSourceEpoch",lambda db:epoch)
    async def deny(*args,**kwargs):
        raise WriterCutoverDenied("fixture denied")
    monkeypatch.setattr(startup,"qualify_writer_cutover",deny)
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(startup.install_before_lifespan(app))
    assert conversation.canonical_source_epoch is None and memory.canonical_source_epoch is None
    assert not getattr(app.state,"_writer_cutover_installed",False)
