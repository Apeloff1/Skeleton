"""Offline, restartable relocation of the Dragon Mongo authority.

Operate against a stopped application and a dedicated, unused destination
database. Source collections are never written, deleted, or renamed. Copy
raw BSON, preserve _id, indexes and tombstones, then independently rescan both
sides. Unsupported Mongo schemas hold, not silently degrade.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path
from contextlib import closing

from bson import BSON
from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError,PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.dragon_mongo_receipt import _ack,_dir,_new_json,_read_json,_json,DeploymentHeld


COLLECTIONS=("dragon_crawler_sessions","dragon_crawler_commands")
JOURNAL="dragon_relocation_control_v1"
MARKER="dragon-relocation"
RAW=CodecOptions(document_class=RawBSONDocument)
MAX_BATCH=128
MAX_ID=2048
NAME=re.compile(r"[A-Za-z0-9_-]{1,63}\Z")
HEX=re.compile(r"[0-9a-f]{64}\Z")
INDEX_OPTIONS={"name","key","v","unique","sparse","partialFilterExpression","hidden"}


class RelocationHeld(RuntimeError):
    pass


def _digest(value):
    return hashlib.sha256(BSON.encode({"value":value})).hexdigest()


def _name(value):
    if not isinstance(value,str) or not NAME.fullmatch(value) or value in {"admin","local","config"}:
        raise RelocationHeld("invalid dedicated database name")
    return value


def _id(value):
    if not isinstance(value,str) or not value or len(value.encode("utf-8"))>MAX_ID or "\x00" in value:
        raise RelocationHeld("unsupported Dragon document identity")
    return value


def _metadata(db,name):
    values=list(db.list_collections(filter={"name":name}))
    if len(values)!=1:raise RelocationHeld("collection absent or ambiguous")
    row=values[0]
    if row.get("type")!="collection" or row.get("options"):
        raise RelocationHeld("collection has unsupported options; use specialist migration")
    uuid=row.get("info",{}).get("uuid")
    if uuid is None:raise RelocationHeld("collection UUID unavailable")
    indexes=[]
    for idx in db[name].list_indexes():
        if set(idx)-INDEX_OPTIONS:raise RelocationHeld("unsupported index option or TTL")
        keys=list(idx["key"].items())
        if not keys or any(not isinstance(k,str) or type(v) is not int or v not in (1,-1) for k,v in keys):
            raise RelocationHeld("unsupported non-B-tree index")
        opts={k:idx[k] for k in sorted(set(idx)-{"key","v","name"})}
        # Explicit false/default absence is semantically equal on Mongo.
        opts={k:v for k,v in opts.items() if v is not False}
        indexes.append({"name":idx["name"],"keys":[[k,v] for k,v in keys],"options":opts})
    indexes.sort(key=lambda x:x["name"])
    if not any(x["name"]=="_id_" and x["keys"]==[["_id",1]] for x in indexes):
        raise RelocationHeld("source _id index missing")
    return {"uuid":bytes(uuid).hex(),"indexes":indexes,"index_sha":_digest(indexes)}


def _raw(db,name):
    return db.get_collection(name,codec_options=RAW,read_concern=ReadConcern("majority"),
                             write_concern=WriteConcern(w="majority",j=True,wtimeout=15000))


def _scan(col,after=None,limit=0):
    query={} if after is None else {"_id":{"$gt":_id(after)}}
    cursor=col.find(query,batch_size=16).sort("_id",1).collation({"locale":"simple"})
    if limit:cursor=cursor.limit(limit)
    try:
        for doc in cursor:
            _id(doc["_id"]);yield doc
    finally:cursor.close()


def fingerprint(col):
    h=hashlib.sha256();n=size=0;last=None
    for doc in _scan(col):
        identifier=_id(doc["_id"])
        if last is not None and identifier.encode()<=last.encode():
            raise RelocationHeld("document ordering differs")
        raw=doc.raw;h.update(len(raw).to_bytes(8,"big"));h.update(raw)
        last=identifier;n+=1;size+=len(raw)
    return {"documents":n,"bytes":size,"sha256":h.hexdigest()}


def _source_state(source):
    # The explicit stop acknowledgement is still required. A residual
    # worker token or running session is evidence of unresolved custody,
    # even if its time lease has elapsed. Never clear it during copying.
    for name in COLLECTIONS:
        predicate={"worker_token":{"$exists":True,"$ne":None}}
        if name=="dragon_crawler_sessions":
            predicate={"$or":[predicate,{"status":"running"}]}
        if source[name].find_one(predicate,{"_id":1}) is not None:
            raise RelocationHeld("source contains unresolved worker custody")
    state={}
    for name in COLLECTIONS:
        before=_metadata(source,name)
        witness=fingerprint(_raw(source,name))
        after=_metadata(source,name)
        if before!=after:raise RelocationHeld("source collection changed during scan")
        state[name]={"uuid":before["uuid"],"index_sha":before["index_sha"],"data":witness}
    return state


def _fresh_target(target):
    names=set(target.list_collection_names())
    if names=={JOURNAL} and target[JOURNAL].find_one({}) is None:
        _metadata(target,JOURNAL)
        return
    if names:raise RelocationHeld("destination database must be empty on first preparation")
    target.create_collection(JOURNAL)


def _journal(target):
    return target.get_collection(JOURNAL,write_concern=WriteConcern(w="majority",j=True,wtimeout=15000))


def _state(target):
    return _journal(target).find_one({"_id":MARKER})


def _binding(source,target,state):
    if not state or state.get("version")!=1 or state.get("source_db")!=source.name or state.get("target_db")!=target.name:
        raise RelocationHeld("relocation journal binding differs")
    if state.get("phase") not in {"preparing","copying","verified"} or set(state.get("source",{}))!=set(COLLECTIONS):
        raise RelocationHeld("relocation journal shape differs")
    if set(target.list_collection_names())-set((*COLLECTIONS,JOURNAL)):
        raise RelocationHeld("unexpected destination collection")
    for name in COLLECTIONS:
        meta=_metadata(source,name)
        if meta["uuid"]!=state["source"][name]["uuid"] or meta["index_sha"]!=state["source"][name]["index_sha"]:
            raise RelocationHeld("source UUID or index topology changed")


def _create_target(source,target,state):
    control=_journal(target)
    for name in COLLECTIONS:
        existing=name in target.list_collection_names()
        recorded=state.get("target",{}).get(name)
        if recorded:
            meta=_metadata(target,name)
            if meta["uuid"]!=recorded:raise RelocationHeld("destination collection replaced")
            continue
        if not existing:target.create_collection(name)
        else:
            # Crash after create but before UUID publication: only an empty
            # collection in this explicitly dedicated database can resume.
            if target[name].find_one({},{"_id":1}) is not None:
                raise RelocationHeld("unbound destination contains documents")
        meta=_metadata(target,name)
        if meta["uuid"]==state["source"][name]["uuid"]:
            raise RelocationHeld("source and destination collection alias")
        result=control.update_one({"_id":MARKER,"phase":"preparing","target."+name:{"$exists":False}},
                                  {"$set":{"target."+name:meta["uuid"]}})
        if result.matched_count!=1:raise RelocationHeld("destination preparation raced")
    control.update_one({"_id":MARKER,"phase":"preparing"},{"$set":{"phase":"copying"}})
    return _state(target)


def prepare(source,target,*,offline_acknowledged=False):
    _ack(offline_acknowledged)
    _name(source.name);_name(target.name)
    if source.name==target.name:raise RelocationHeld("dedicated destination must use a different database name")
    state=_state(target)
    if state is None:
        source_before=_source_state(source)
        _fresh_target(target)
        state={"_id":MARKER,"version":1,"source_db":source.name,"target_db":target.name,
               "phase":"preparing","source":source_before,"target":{},"progress":{}}
        _journal(target).insert_one(state)
    _binding(source,target,state)
    if state["phase"]=="preparing":state=_create_target(source,target,state)
    _verify_target_binding(target,state)
    return {"phase":state["phase"],"source":state["source"],"target":state["target"],"source_retained":True}


def _verify_target_binding(target,state):
    if set(state.get("target",{}))!=set(COLLECTIONS):raise RelocationHeld("target preparation incomplete")
    for name in COLLECTIONS:
        meta=_metadata(target,name)
        if meta["uuid"]!=state["target"][name] or meta["uuid"]==state["source"][name]["uuid"]:
            raise RelocationHeld("target UUID differs")


def _put_exact(col,doc):
    identifier=_id(doc["_id"])
    try:col.insert_one(doc)
    except DuplicateKeyError:
        existing=col.find_one({"_id":identifier})
        if existing is None or existing.raw!=doc.raw:raise RelocationHeld("destination document conflict")
    existing=col.find_one({"_id":identifier})
    if existing is None or existing.raw!=doc.raw:raise RelocationHeld("destination BSON readback differs")


def copy_pulse(source,target,*,batches=8,offline_acknowledged=False):
    _ack(offline_acknowledged)
    if type(batches) is not int or not 1<=batches<=64:raise ValueError("bounded batch count")
    state=_state(target);_binding(source,target,state);_verify_target_binding(target,state)
    if state["phase"]=="verified":return {"phase":"verified","copied":0,"ready_for_verify":True}
    if state["phase"]!="copying":raise RelocationHeld("prepare destination first")
    control=_journal(target);copied=0;remaining=batches
    for name in COLLECTIONS:
        if not remaining:break
        while remaining:
            state=_state(target);progress=state.get("progress",{}).get(name)
            if progress and progress.get("complete"):break
            after=progress["after"] if progress else None
            count=progress["count"] if progress else 0
            docs=0;last=after
            for doc in _scan(_raw(source,name),after,MAX_BATCH):
                _put_exact(_raw(target,name),doc)
                last=doc["_id"];docs+=1
            next_progress={"after":last,"count":count+docs,"complete":docs<MAX_BATCH}
            field="progress."+name
            expected=progress if progress else {"$exists":False}
            updated=control.update_one({"_id":MARKER,"phase":"copying",field:expected},{"$set":{field:next_progress}})
            if updated.matched_count!=1:raise RelocationHeld("copy checkpoint raced; replay exact batch")
            copied+=docs;remaining-=1
            if next_progress["complete"]:break
    latest=_state(target)
    return {"phase":"copying","copied":copied,"progress":latest["progress"],
            "ready_for_verify":all(latest["progress"].get(n,{}).get("complete") for n in COLLECTIONS)}


def _indexes(source,target,name):
    expected=_metadata(source,name)
    actual=_metadata(target,name)
    by_name={x["name"]:x for x in expected["indexes"]}
    for idx in actual["indexes"]:
        if idx["name"] not in by_name or idx!=by_name[idx["name"]]:
            raise RelocationHeld("unexpected destination index")
    names={x["name"] for x in actual["indexes"]}
    for idx in expected["indexes"]:
        if idx["name"] not in names:
            target[name].create_index([tuple(x) for x in idx["keys"]],name=idx["name"],**idx["options"])
    if _metadata(target,name)["index_sha"]!=expected["index_sha"]:
        raise RelocationHeld("destination index witness differs")


def verify(source,target,*,offline_acknowledged=False):
    _ack(offline_acknowledged);state=_state(target)
    _binding(source,target,state);_verify_target_binding(target,state)
    if state["phase"] not in {"copying","verified"} or any(not state.get("progress",{}).get(n,{}).get("complete") for n in COLLECTIONS):
        raise RelocationHeld("copy is incomplete")
    if _source_state(source)!=state["source"]:raise RelocationHeld("source changed since preparation; no cutover")
    for name in COLLECTIONS:
        _indexes(source,target,name)
        actual=fingerprint(_raw(target,name))
        if actual!=state["source"][name]["data"] or actual["documents"]!=state["progress"][name]["count"]:
            raise RelocationHeld("destination full BSON witness differs")
    if _source_state(source)!=state["source"]:raise RelocationHeld("source changed during final verification")
    receipt={"version":1,"source_db":source.name,"target_db":target.name,
             "source":state["source"],"target":state["target"],"verified":True}
    witness=hashlib.sha256(_json(receipt)).hexdigest()
    result=_journal(target).update_one({"_id":MARKER,"phase":{"$in":["copying","verified"]}},
                                      {"$set":{"phase":"verified","receipt_sha":witness}})
    if result.matched_count!=1:raise RelocationHeld("verification publication raced")
    return {**receipt,"receipt_sha":witness,"source_retained":True,"live_cutover_executed":False}


def _client(variable):
    uri=os.environ.get(variable,"").strip()
    if not uri:raise RelocationHeld("explicit Mongo connection configuration required")
    return MongoClient(uri,serverSelectionTimeoutMS=5000,connectTimeoutMS=5000,socketTimeoutMS=120000,
                       retryReads=True,retryWrites=True,appname="dragon-offline-relocation",
                       w="majority",journal=True)


def _topology(client):
    hello=client.admin.command("hello")
    if hello.get("msg")=="isdbgrid" or not hello.get("isWritablePrimary"):
        raise RelocationHeld("requires an ordinary writable standalone or replica-set primary")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("prepare","copy","verify"))
    p.add_argument("--offline-writers-stopped",action="store_true")
    p.add_argument("--batches",type=int,default=8)
    p.add_argument("--receipt")
    args=p.parse_args()
    import json
    try:
        _ack(args.offline_writers_stopped)
        with closing(_client("MONGO_URL")) as src,closing(_client("SKL_DRAGON_TARGET_MONGO_URL")) as dst:
            _topology(src);_topology(dst)
            source=src[_name(os.environ.get("DB_NAME","galaxy_studio_db"))]
            target=dst[_name(os.environ.get("SKL_DRAGON_TARGET_MONGO_DB",""))]
            if args.command=="prepare":value=prepare(source,target,offline_acknowledged=True)
            elif args.command=="copy":value=copy_pulse(source,target,batches=args.batches,offline_acknowledged=True)
            else:
                value=verify(source,target,offline_acknowledged=True)
                if args.receipt:
                    path=Path(args.receipt);_dir(path.parent)
                    if path.exists():
                        if _read_json(path)!=value:raise RelocationHeld("existing receipt differs")
                    else:_new_json(path,value)
            print(json.dumps(value,sort_keys=True))
    except (PyMongoError,RelocationHeld,DeploymentHeld,ValueError,OSError) as exc:
        # Mongo exceptions may expose connection endpoints or payload values.
        # Only the class is emitted; no source records, URI or credentials.
        p.exit(1,"Dragon relocation held: "+type(exc).__name__+"\n")


if __name__=="__main__":main()
