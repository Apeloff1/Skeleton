"""Derived semantic postings use the selected Dragon authority and lineage.

A new destination collection UUID invalidates old coverage even if a
session's source snapshot and grant did not change. Derived rows are rebuilt
using the existing licensed/local encoder pipeline, not copied from stale
legacy caches. No new content or consent authority is granted.
"""
from __future__ import annotations

import hashlib

from pymongo.errors import CollectionInvalid,OperationFailure

NAMES={"current":"dragon_current_full_vector_postings","archive":"dragon_full_vector_postings"}


async def _identity(target,name):
    response=await target.command({"listCollections":1,"filter":{"name":name},"nameOnly":False,"maxTimeMS":3000})
    rows=response.get("cursor",{}).get("firstBatch",[])
    if not rows:return None
    if len(rows)!=1 or rows[0].get("type")!="collection" or rows[0].get("options"):
        raise ValueError("unsupported derived posting topology")
    uuid=rows[0].get("info",{}).get("uuid")
    if uuid is None or len(bytes(uuid))!=16:raise ValueError("derived posting UUID missing")
    return bytes(uuid).hex()


async def prepare(target,receipt_sha):
    """Create only regenerable stores, after authority receipt validation."""
    if not isinstance(receipt_sha,str) or len(receipt_sha)!=64:raise ValueError("receipt identity")
    epochs={}
    for kind,name in NAMES.items():
        identity=await _identity(target,name)
        if identity is None:
            try:await target.create_collection(name)
            except CollectionInvalid:pass
            except OperationFailure as exc:
                if exc.code!=48:raise
            identity=await _identity(target,name)
        if identity is None:raise ValueError("derived posting creation unconfirmed")
        epochs[kind]=hashlib.sha256(("dragon-posting-v1:"+receipt_sha+":"+kind+":"+identity).encode()).hexdigest()
    return epochs


def collection(app,kind):
    if kind not in NAMES:raise ValueError("posting kind")
    # Access the authoritative sessions property first; a held cutover may
    # never read/write a legacy or guessed destination postings collection.
    _=app.sessions
    target=getattr(app,"_derived_database",None)
    if getattr(app,"_cutover_requested",False):
        if target is None or not getattr(app,"_cutover_active",False):
            raise ValueError("derived authority held")
    else:target=app.database
    return target[NAMES[kind]]


def epoch(app,kind):
    return getattr(app,"_derived_epochs",{}).get(kind)


def due_predicate(app,kind,field,now):
    value=[{field:{"$exists":False}},{field:{"$lte":now}}]
    bound=epoch(app,kind)
    if bound:value.append({field+"_storage_epoch":{"$ne":bound}})
    return value


def claim_filter(app,kind,field,item):
    bound=epoch(app,kind)
    if not bound:return {}
    key=field+"_storage_epoch"
    return {key:item.get(key,{"$exists":False})}


def claim_update(app,kind,field,state,lease,item):
    update={"$set":{field:lease}}
    bound=epoch(app,kind)
    if bound:
        key=field+"_storage_epoch"
        update["$set"][key]=bound
        if item.get(key)!=bound:update["$unset"]={state:""}
    return update


def generation(app,kind,legacy):
    bound=epoch(app,kind)
    if not bound:return legacy
    return hashlib.sha256(("dragon-posting-generation-v1:"+bound+":"+legacy).encode()).hexdigest()


def state_filter(app,kind,field):
    bound=epoch(app,kind)
    return {field+"_storage_epoch":bound} if bound else {}
