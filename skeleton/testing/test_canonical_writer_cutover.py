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
    qualify_writer_cutover, inspect_writer_inventory, _OwnerGraph, _GRAPH_FIELDS, _GRAPH_NAMES,
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
    def find(self,*args,**kwargs): return Cursor(getattr(self,"find_rows",self.rows))
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

def graph_rows():
    root = {"repository_namespace":"memory","memory_id":"mem","tenant_id":TENANT,
            "namespace":"local","subject_id":ACTOR,"version":2}
    snap = {k:v for k,v in root.items() if k!="repository_namespace"}
    common = {k:v for k,v in root.items() if k not in ("subject_id","version")}
    return {
        "threads":[{"_id":"thread","thread_id":"thread","tenant_id":TENANT,
                    "owner_id":ACTOR,"version":2,"message_sequence":1}],
        "messages":[{"_id":"message","message_id":"message","thread_id":"thread",
                     "sequence":1,"_commit_state":"committed"}],
        "records":[root],
        "revisions":[{**common,"version":2,"record":dict(snap)}],
        "projection_outbox":[{**common,"event_id":"event","memory_version":2,
                              "action":"upsert","published_at":None,"record":dict(snap)}],
        "idempotency":[{**common,"idempotency_key":"idem","request_digest":"f"*64,
                        "status":"committed","result":dict(snap)}],
    }


def expected_inventory():
    rows = graph_rows()
    graph = _OwnerGraph("memory")
    for lane in _GRAPH_FIELDS:
        graph.begin(lane)
        for row in rows[lane]:
            graph.feed(row)
    digest, scopes, counts = graph.finish()
    return CutoverInventory(((KEY,2),),scopes,digest,counts)


def signed(inventory=None,**updates):
    inventory = inventory or expected_inventory()
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
    rows = graph_rows()
    collections = {lane:Collection(_GRAPH_NAMES[lane],db,data) for lane,data in rows.items()}
    threads.find_rows = rows["threads"]
    records.find_rows = rows["records"]
    records.rows = [{"_id":{"tenant":TENANT,"actor":ACTOR}}]
    collections.update(threads=threads,records=records)
    return db,epoch,collections

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
    _,epoch,collections=fixture()
    async def run():
        observed=await inspect_writer_inventory(epoch=epoch,collections=collections,repository_namespace="memory")
        assert observed["guarded_local_ai_ready"] is False and observed["writes_performed"] is False
        approval=signed()
        result=await qualify_writer_cutover(approval,epoch=epoch,collections=collections,repository_namespace="memory")
        assert result.digest==observed["inventory_sha256"] and result.matches(approval.plan)
        assert epoch.read_epoch.await_count==2
    asyncio.run(run())

@pytest.mark.parametrize("change",["missing","odd","actor","role","generation","foreign_db","oversize","second_scan"])
def test_cutover_denies_ambiguous_or_unapproved_source(change):
    db,epoch,collections=fixture()
    if change=="missing":
        epoch._collection.rows=[]
    elif change=="odd":
        epoch._collection.rows[0]["epoch"]=3
    elif change=="actor":
        collections["records"].rows=[{"_id":{"tenant":TENANT,"actor":"uncovered"}}]
    elif change=="role":
        db.auth["authInfo"]["authenticatedUserRoles"][0]["role"]="root"
    elif change=="generation":
        epoch.read_epoch.return_value=4
    elif change=="foreign_db":
        collections["threads"].database=Database()
    elif change=="oversize":
        epoch._collection.rows*=2
    elif change=="second_scan":
        async def changed(**kwargs):
            epoch._collection.rows[0]["epoch"]=4
            return 2
        epoch.read_epoch.side_effect=changed
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,collections=collections,repository_namespace="memory"))

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
    db,epoch,collections=fixture()
    conversation=SimpleNamespace(threads=collections["threads"],messages=collections["messages"],canonical_source_epoch=None)
    memory=SimpleNamespace(repository_namespace="memory",canonical_source_epoch=None,
                           **{k:collections[k] for k in ("records","revisions","projection_outbox","idempotency")})
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

@pytest.mark.parametrize("lane,change", [
    ("messages", {"_commit_state":"prepared"}),
    ("messages", {"thread_id":"missing"}),
    ("messages", {"sequence":2}),
    ("threads", {"_id":"alias"}),
    ("records", {"repository_namespace":"other"}),
    ("records", {"subject_id":"another_actor"}),
    ("revisions", {"version":3}),
    ("revisions", {"memory_id":"missing"}),
    ("projection_outbox", {"memory_version":3}),
    ("projection_outbox", {"record":{"subject_id":"other"}}),
    ("idempotency", {"status":"pending"}),
    ("idempotency", {"request_digest":"invalid"}),
    ("idempotency", {"result":{"subject_id":"other"}}),
])
def test_complete_local_graph_rejects_unresolved_or_foreign_metadata(lane,change):
    _,epoch,collections=fixture()
    target=collections[lane]
    rows=getattr(target,"find_rows",target.rows)
    rows[0].update(change)
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,collections=collections,
                                           repository_namespace="memory"))


@pytest.mark.parametrize("lane",tuple(_GRAPH_FIELDS))
def test_signed_graph_denies_duplicate_or_disappeared_rows(lane):
    for duplicate in (True,False):
        _,epoch,collections=fixture()
        target=collections[lane]
        rows=getattr(target,"find_rows",target.rows)
        if duplicate:
            rows.append(dict(rows[0]))
        else:
            rows.clear()
        with pytest.raises(WriterCutoverDenied):
            asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,collections=collections,
                                               repository_namespace="memory"))


def test_valid_but_changed_metadata_invalidates_old_approval():
    _,epoch,collections=fixture()
    collections["projection_outbox"].rows[0]["published_at"]="2026-11-16T06:00:00Z"
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,collections=collections,
                                           repository_namespace="memory"))


def test_receipt_contains_only_counts_and_hashes_not_actor_or_content():
    _,epoch,collections=fixture()
    collections["messages"].rows[0]["content"]="private payload must not enter receipt"
    receipt=asyncio.run(inspect_writer_inventory(epoch=epoch,collections=collections,
                                                  repository_namespace="memory"))
    assert receipt["local_collection_counts"]==dict.fromkeys(_GRAPH_FIELDS,1)
    assert receipt["local_owner_graph_sha256"]==expected_inventory().graph_sha256
    assert "private payload" not in json.dumps(receipt)
    assert receipt["writer_cutover_authorized"] is False


def test_second_graph_scan_detects_write_after_linearizable_observation():
    _,epoch,collections=fixture()
    async def race(**kwargs):
        collections["projection_outbox"].rows[0]["published_at"]="2026-11-16T06:00:00Z"
        return 2
    epoch.read_epoch.side_effect=race
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(qualify_writer_cutover(signed(),epoch=epoch,collections=collections,
                                           repository_namespace="memory"))

def _private_dir(tmp_path):
    import os
    directory = tmp_path / "writer-custody"
    directory.mkdir(mode=0o700)
    os.chmod(directory,0o700)
    return directory


def test_durable_local_approval_cannot_be_replayed_after_shutdown(tmp_path):
    from scripts.start_protected_backend import _reserve_cutover
    directory = _private_dir(tmp_path)
    approval = signed()
    with _reserve_cutover(approval,directory):
        records=list(directory.glob("approval-*.reserved"))
        assert len(records)==1
        assert json.loads(records[0].read_text())["state"]=="reserved_not_qualified"
    with pytest.raises(WriterCutoverDenied):
        with _reserve_cutover(approval,directory):
            pytest.fail("consumed approval replayed")


def test_local_deployment_lock_excludes_distinct_approvals_until_exit(tmp_path):
    from scripts.start_protected_backend import _reserve_cutover
    directory=_private_dir(tmp_path)
    one,two=signed(),signed(backup_sha256="9"*64)
    with _reserve_cutover(one,directory):
        with pytest.raises(WriterCutoverDenied):
            with _reserve_cutover(two,directory):
                pytest.fail("concurrent deployment admitted")
    with _reserve_cutover(two,directory):
        assert len(list(directory.glob("approval-*.reserved")))==2


def test_failed_startup_burns_approval(tmp_path):
    from scripts.start_protected_backend import _reserve_cutover
    directory=_private_dir(tmp_path)
    approval=signed()
    with pytest.raises(ValueError):
        with _reserve_cutover(approval,directory):
            raise ValueError("startup failed")
    with pytest.raises(WriterCutoverDenied):
        with _reserve_cutover(approval,directory):
            pytest.fail("failed startup reused approval")


@pytest.mark.parametrize("kind",["symlink_leaf","symlink_ancestor","public","missing","relative"])
def test_untrusted_local_custody_directories_denied(tmp_path,kind):
    from scripts.start_protected_backend import _reserve_cutover
    from pathlib import Path
    directory=_private_dir(tmp_path)
    if kind=="symlink_leaf":
        alias=tmp_path/"alias"
        alias.symlink_to(directory,target_is_directory=True)
        directory=alias
    elif kind=="symlink_ancestor":
        alias=tmp_path/"alias"
        alias.symlink_to(tmp_path,target_is_directory=True)
        directory=alias/directory.name
    elif kind=="public":
        directory.chmod(0o755)
    elif kind=="missing":
        directory=directory/"missing"
    else:
        directory=Path(directory.name)
    with pytest.raises(WriterCutoverDenied):
        with _reserve_cutover(signed(),directory):
            pytest.fail("untrusted state directory admitted")


def test_symlinked_local_lock_does_not_modify_target(tmp_path):
    import hashlib
    from scripts.start_protected_backend import _reserve_cutover
    directory=_private_dir(tmp_path)
    approval=signed()
    key=hashlib.sha256(b"skeleton.local-cutover-deployment.v1\0"
                       + approval.plan.deployment_id.encode("ascii")).hexdigest()
    victim=tmp_path/"victim"
    victim.write_text("unchanged")
    (directory/("deployment-"+key+".lock")).symlink_to(victim)
    with pytest.raises(WriterCutoverDenied):
        with _reserve_cutover(approval,directory):
            pytest.fail("symlink lock admitted")
    assert victim.read_text()=="unchanged"


class LatchCollection:
    def __init__(self,db):
        self.database,self.name=db,"canonical_writer_deployment_latch"
        self.row=None
        self.uncertain=False
    async def find_one(self,query,**kwargs):
        assert query=={"_id":"canonical-writer-single-deployment-v1"}
        return None if self.row is None else dict(self.row)
    async def insert_one(self,row):
        if self.row is not None:
            raise RuntimeError("duplicate")
        self.row=dict(row)
        if self.uncertain:
            raise RuntimeError("uncertain majority acknowledgement")
        return SimpleNamespace(acknowledged=True,inserted_id=row["_id"])
    async def replace_one(self,predicate,row,**kwargs):
        match=int(self.row==predicate)
        if match:
            self.row=dict(row)
        return SimpleNamespace(acknowledged=True,matched_count=match,modified_count=match)


def latch_fixture():
    db,epoch,_=fixture()
    coll=LatchCollection(db)
    db.get_collection=lambda name,**kwargs:coll
    return epoch,coll


def retirement(epoch,approval,digest,**updates):
    from skeleton.app.canonical_writer_cutover import WriterDeploymentRetirement
    values=dict(authority_id=approval.authority_id,deployment_id=approval.deployment_id,
                source_head=approval.source_head,database_name=epoch._database.name,
                active_latch_sha256=digest,shutdown_evidence_sha256="7"*64,
                issued_at=int(time.time())-1,expires_at=int(time.time())+120)
    values.update(updates)
    plan=WriterDeploymentRetirement(**values)
    key=Ed25519PrivateKey.generate()
    return plan,key.sign(plan.canonical_bytes()),dict(
        epoch=epoch,authority_id=plan.authority_id,deployment_id=plan.deployment_id,
        source_head=plan.source_head,public_key=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))


def test_database_latch_retirement_and_monotonic_approval_highwater():
    from skeleton.app.canonical_writer_cutover import (
        reserve_writer_deployment, inspect_writer_deployment, verify_writer_deployment,
        retire_writer_deployment,
    )
    epoch,coll=latch_fixture()
    now=int(time.time())
    first=signed(issued_at=now-4)
    async def run():
        assert (await inspect_writer_deployment(epoch=epoch))["state"]=="ABSENT"
        reservation=await reserve_writer_deployment(first,epoch=epoch)
        assert reservation["generation"]==1
        await verify_writer_deployment(epoch=epoch,reservation=reservation)
        with pytest.raises(WriterCutoverDenied):
            await reserve_writer_deployment(signed(issued_at=now-3),epoch=epoch)
        p,s,k=retirement(epoch,first,reservation["latch_sha256"],issued_at=now-2)
        retired=await retire_writer_deployment(p,s,**k)
        assert retired["generation"]==2 and retired["state"]=="RETIRED"
        with pytest.raises(WriterCutoverDenied):
            await verify_writer_deployment(epoch=epoch,reservation=reservation)
        with pytest.raises(WriterCutoverDenied):
            await retire_writer_deployment(p,s,**k)
        with pytest.raises(WriterCutoverDenied):
            await reserve_writer_deployment(first,epoch=epoch)
        again=await reserve_writer_deployment(signed(issued_at=now-1),epoch=epoch)
        assert again["generation"]==3
        assert coll.row["state"]=="ACTIVE"
    asyncio.run(run())


def test_uncertain_write_never_grants_startup_or_allows_retry():
    from skeleton.app.canonical_writer_cutover import reserve_writer_deployment,inspect_writer_deployment
    epoch,coll=latch_fixture()
    coll.uncertain=True
    async def run():
        with pytest.raises(WriterCutoverDenied):
            await reserve_writer_deployment(signed(),epoch=epoch)
        assert (await inspect_writer_deployment(epoch=epoch))["state"]=="ACTIVE"
        with pytest.raises(WriterCutoverDenied):
            await reserve_writer_deployment(signed(),epoch=epoch)
    asyncio.run(run())


@pytest.mark.parametrize("change",["wrong_digest","wrong_signature","stale_time","wrong_database"])
def test_retirement_does_not_reset_latch_on_wrong_authority(change):
    from skeleton.app.canonical_writer_cutover import reserve_writer_deployment,retire_writer_deployment
    epoch,coll=latch_fixture()
    first=signed(issued_at=int(time.time())-4)
    async def run():
        active=await reserve_writer_deployment(first,epoch=epoch)
        updates={}
        if change=="wrong_digest":
            updates["active_latch_sha256"]="9"*64
        elif change=="stale_time":
            updates["issued_at"]=first.plan.issued_at
        elif change=="wrong_database":
            updates["database_name"]="different"
        p,s,k=retirement(epoch,first,active["latch_sha256"],**updates)
        if change=="wrong_signature":
            s=b"x"*64
        before=dict(coll.row)
        with pytest.raises(WriterCutoverDenied):
            await retire_writer_deployment(p,s,**k)
        assert coll.row==before
    asyncio.run(run())


def test_malformed_existing_latch_denies_instead_of_overwriting():
    from skeleton.app.canonical_writer_cutover import reserve_writer_deployment
    epoch,coll=latch_fixture()
    coll.row={"_id":"canonical-writer-single-deployment-v1","state":"RETIRED"}
    with pytest.raises(WriterCutoverDenied):
        asyncio.run(reserve_writer_deployment(signed(),epoch=epoch))
    assert coll.row=={"_id":"canonical-writer-single-deployment-v1","state":"RETIRED"}


def test_process_reservation_becomes_sticky_denial_after_retirement():
    from skeleton.app.canonical_writer_cutover import reserve_writer_deployment,retire_writer_deployment
    from skeleton.persistence.mongo_source_epoch import MongoSourceEpochError
    epoch,coll=latch_fixture()
    now=int(time.time())
    first=signed(issued_at=now-4)
    async def run():
        reservation=await reserve_writer_deployment(first,epoch=epoch)
        await epoch.bind_deployment_latch(reservation)
        await epoch._assert_deployment_latch()
        with pytest.raises(MongoSourceEpochError):
            await epoch.bind_deployment_latch(reservation)
        p,s,k=retirement(epoch,first,reservation["latch_sha256"],issued_at=now-2)
        await retire_writer_deployment(p,s,**k)
        with pytest.raises(MongoSourceEpochError):
            await epoch._assert_deployment_latch()
        next_reservation=await reserve_writer_deployment(signed(issued_at=now-1),epoch=epoch)
        assert next_reservation["generation"]==3
        with pytest.raises(MongoSourceEpochError):
            await epoch.bind_deployment_latch(next_reservation)
        with pytest.raises(MongoSourceEpochError):
            await epoch._assert_deployment_latch()
    asyncio.run(run())
