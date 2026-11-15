"""Explicit, source-bound staging into physical Hoarder storage.

Mongo snapshot stays authoritative. External copy is not an evidence reader,
current source, backup certificate, or replacement primary. Persistent intent,
exact manifest tombstones and bounded cleanup fence cross-store crashes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading

from pymongo import ASCENDING
from core.dragon_hoarder_bulk import BulkArchive,Volume,StorageHeld,owner_key,MAX_VOLUMES
from core.dragon_storage_topology import topology_config
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK
from core.dragon_checkpoint_replica import CheckpointReplicaError
from core.dragon_vault import _bounded_discovery_cpu
from skeleton.ai.webcrawler import dragon_archive_scale as a
from skeleton.ai.webcrawler.dragon_treasury_vault import TERMINAL,identity,hash_identity,finite

SCHEMA="skeleton.dragon.bulk-copy.v1"
_MAX_BYTES=4*1024*1024
_GATE=asyncio.Semaphore(1)
_INIT_LOCK=threading.Lock()
_store=None
_config=None


def configured():
    return bool((os.getenv("SKL_DRAGON_HOARDER_VOLUMES_JSON","").strip() or
                 os.getenv("SKL_DRAGON_HOARDER_VOLUMES_JSON_FILE","").strip()) and
                os.getenv("SKL_DRAGON_HOARDER_MANIFEST_DB_PATH","").strip())


def _archive():
    global _store,_config
    raw=topology_config("SKL_DRAGON_HOARDER_VOLUMES_JSON")
    path=Path(os.environ.get("SKL_DRAGON_HOARDER_MANIFEST_DB_PATH",""))
    if not raw or not path.is_absolute():
        raise StorageHeld("bulk storage not configured")
    config=(raw,str(path))
    with _INIT_LOCK:
        if _store is not None:
            if _config!=config:
                raise StorageHeld("bulk configuration changed")
            return _store
        specs=json.loads(raw)
        if not isinstance(specs,list) or not 1<=len(specs)<=MAX_VOLUMES:
            raise ValueError("volume configuration")
        volumes=[]
        bootstrap=os.getenv("SKL_DRAGON_HOARDER_BOOTSTRAP")=="1"
        for spec in specs:
            if not isinstance(spec,dict) or not {"name","root","payload_budget"}<=set(spec) or set(spec)-{"name","root","payload_budget","free_reserve"}:
                raise ValueError("volume configuration")
            volume=Volume(**{**spec,"root":Path(spec["root"])})
            if not bootstrap and not (volume.root/"hoarder-payload-v1.sqlite3").is_file():
                raise StorageHeld("payload volume unavailable; explicit initialization required")
            volumes.append(volume)
        if not bootstrap and not path.is_file():
            raise StorageHeld("manifest ledger unavailable")
        _store=ManifestArchive(path,BulkArchive(tuple(volumes)))
        _config=config
        return _store


async def _io(work):
    await asyncio.wait_for(_GATE.acquire(),timeout=2)
    try:
        task=asyncio.create_task(asyncio.to_thread(work))
    except BaseException:
        _GATE.release()
        raise
    def drained(done):
        _GATE.release()
        if not done.cancelled():
            done.exception()
    task.add_done_callback(drained)
    return await asyncio.shield(task)


def _logical(identifier):
    if not identity(identifier):
        raise ValueError("session identity")
    return "dragon-deep:"+identifier


def _manifest_id(scope,identifier,operation):
    return hashlib.sha256(json.dumps([owner_key(scope),_logical(identifier),operation],
                        separators=(",",":")).encode()).hexdigest()


def validate_marker(scope,identifier,mark):
    required={"schema","operation","command_digest","snapshot_digest","grant_digest","policy_digest",
              "expected_hash","expected_bytes","expires_at","retry_at","manifest","state"}
    if (not isinstance(mark,dict) or set(mark)!=required or mark["schema"]!=SCHEMA
            or not all(hash_identity(mark[k]) for k in ("operation","command_digest","snapshot_digest",
                "grant_digest","policy_digest","expected_hash","manifest"))
            or mark["manifest"]!=_manifest_id(scope,identifier,mark["operation"])
            or type(mark["expected_bytes"]) is not int or not 1<=mark["expected_bytes"]<=_MAX_BYTES
            or not finite(mark["expires_at"]) or not finite(mark["retry_at"])
            or mark["state"] not in {"pending","sealed"}):
        raise ValueError("invalid bulk staging marker")
    return mark


def _public(mark,*,state=None):
    return {"manifest":mark["manifest"],"snapshot_digest":mark["snapshot_digest"],
            "state":state or mark["state"],"bytes":mark["expected_bytes"],"expires_at":mark["expires_at"],
            "canonical_primary_replaced":False,"independent_backup_verified":False,"source_use_authorized":False}


def _write(scope,identifier,mark,raw):
    if hashlib.sha256(raw).hexdigest()!=mark["expected_hash"] or len(raw)!=mark["expected_bytes"]:
        raise StorageHeld("copy payload changed")
    store=_archive()
    begun=store.begin(scope,logical_key=_logical(identifier),operation=mark["operation"],
                      expected_hash=mark["expected_hash"],expected_bytes=mark["expected_bytes"])
    if begun["manifest"]!=mark["manifest"] or begun["state"]=="aborted":
        raise StorageHeld("copy intent withdrawn")
    if begun["state"]=="building":
        for ordinal,start in enumerate(range(0,len(raw),BLOCK)):
            store.append(scope,mark["manifest"],ordinal,raw[start:start+BLOCK])
    sealed=store.seal(scope,mark["manifest"])
    if sealed["sha256"]!=mark["expected_hash"] or sealed["bytes"]!=mark["expected_bytes"]:
        raise StorageHeld("sealed copy witness differs")
    return sealed


def _erase(scope,identifier,mark):
    store=_archive()
    mid=store.abort_intent(scope,logical_key=_logical(identifier),operation=mark["operation"],
                           expected_hash=mark["expected_hash"],expected_bytes=mark["expected_bytes"])
    if mid!=mark["manifest"]:
        raise StorageHeld("cleanup manifest differs")
    return store.collect_manifest(scope,mid,limit=32)


class DragonHoarderCopyMixin:
    def _copy_material(self,scope,row,now):
        from core.dragon_crawler import _encoded,_plain
        from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
        snap,grant,policies,allowed=self._deep_material(scope,row,now)
        if not snap["sources"] or set(snap["sources"])!=set(allowed):
            raise ValueError("every copied source must independently qualify")
        expiries=[]
        for sid,source in snap["sources"].items():
            expiry=archive_expiry(grant,snapshot_digest=snap["snapshot_digest"],source=source,
                policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
            if expiry is None:
                raise ValueError("source does not authorize archive staging")
            expiries.append(expiry)
        payload={"schema":"skeleton.dragon.exact-cold-copy.v1","snapshot":snap,
                 "checkpoint_identity":_plain(row["checkpoint_identity"])}
        raw=_encoded(payload,_MAX_BYTES)
        return raw,payload,{"snapshot_digest":snap["snapshot_digest"],"grant_digest":a.digest(grant),
                            "policy_digest":a.digest(policies),"expires_at":min(expiries),
                            "expected_hash":hashlib.sha256(raw).hexdigest(),"expected_bytes":len(raw)}

    async def stage_bulk_copy(self,scope,identifier,body,*,principal):
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_now
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_bulk_denied","Current editor authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or body["retention_acknowledged"] is not True):
            raise CrawlerError("crawler_bulk_invalid","Explicit physical copy rights required.",422)
        if not configured():
            raise CrawlerError("crawler_bulk_unconfigured","Provision private Hoarder volumes first.",503)
        await self.ensure_indexes()
        op=_operation(body["idempotency_key"])
        command=_digest({"action":"bulk_copy",**body})
        q={**self._deep_query(scope,identifier),"deep_archive.released":True}
        row=await self.sessions.find_one(q,max_time_ms=2000)
        if not row:
            raise CrawlerError("crawler_bulk_held","Final deep custody required.",409)
        previous=row.get("bulk_copy")
        if previous is not None:
            try:
                marker=validate_marker(scope,identifier,previous)
            except (ValueError,TypeError,KeyError) as exc:
                raise CrawlerError("crawler_bulk_held","Bulk marker requires operator review.",409) from exc
            if marker["operation"]!=op or marker["command_digest"]!=command or row.get("bulk_copy_invalidated"):
                raise CrawlerError("crawler_bulk_conflict","Another copy intent exists or awaits cleanup.",409)
        else:
            if row["version"]!=body["expected_version"] or row.get("last_bulk_cleanup")==op:
                raise CrawlerError("crawler_bulk_conflict","Reload custody and use a new operation.",409)
            now=_now().timestamp()
            try:
                raw,payload,binding=await _bounded_discovery_cpu(self._copy_material,scope,row,now)
                marker=validate_marker(scope,identifier,{"schema":SCHEMA,"operation":op,"command_digest":command,
                    **binding,"manifest":_manifest_id(scope,identifier,op),"state":"pending","retry_at":now})
            except (ValueError,TypeError,KeyError,CheckpointReplicaError) as exc:
                raise CrawlerError("crawler_bulk_held","Exact source retention did not qualify.",409) from exc
            # Admission is bound to the actual copied payload, not just its marker.
            await self._admit(scope,identifier,{"bulk_copy":marker,"payload":payload})
            changed=await self.sessions.update_one({**q,"version":row["version"],"bulk_copy":{"$exists":False}},
                {"$set":{"bulk_copy":marker,"bulk_copy_invalidated":False},"$inc":{"version":1}})
            if not changed.modified_count:
                raise CrawlerError("crawler_bulk_conflict","Copy intent changed.",409)
        outcome=await self._finish_bulk_copy(scope,identifier)
        latest=await self.sessions.find_one({**q,"bulk_copy.operation":op},{"bulk_copy":1,"version":1},max_time_ms=2000)
        if not latest:
            raise CrawlerError("crawler_bulk_conflict","Copy intent withdrawn.",409)
        return {"ok":outcome=="sealed","session_id":identifier,"version":latest["version"],
                "bulk_copy":_public(validate_marker(scope,identifier,latest["bulk_copy"])),
                "outcome":outcome,"network_executed":False}

    async def _finish_bulk_copy(self,scope,identifier):
        from core.dragon_crawler import _now,CrawlerError
        q={**self._deep_query(scope,identifier),"deep_archive.released":True,
           "bulk_copy_invalidated":False}
        row=await self.sessions.find_one(q,max_time_ms=2000)
        if not row or not row.get("bulk_copy"):
            return "held"
        mark=validate_marker(scope,identifier,row["bulk_copy"])
        now=_now().timestamp()
        if mark["expires_at"]<=now:
            return "held"
        fence={**q,"version":row["version"],"bulk_copy":mark}
        try:
            raw,_,binding=await _bounded_discovery_cpu(self._copy_material,scope,row,now)
            if any(mark[k]!=value for k,value in binding.items()):
                return "held"
            await _io(lambda:_write(scope,identifier,mark,raw))
        except (ValueError,TypeError,KeyError,CheckpointReplicaError,StorageHeld,sqlite3.Error,OSError,TimeoutError,CrawlerError):
            await self.sessions.update_one(fence,{"$set":{"bulk_copy.retry_at":_now().timestamp()+300}})
            return "held"
        result=await self.sessions.update_one({**fence,"$expr":{"$gt":["$bulk_copy.expires_at",
                {"$divide":[{"$toLong":"$$NOW"},1000]}]}},
                {"$set":{"bulk_copy.state":"sealed"}})
        if result.modified_count:
            return "sealed"
        latest=await self.sessions.find_one({**q,"bulk_copy.operation":mark["operation"],
            "bulk_copy.state":"sealed","bulk_copy.expires_at":{"$gt":_now().timestamp()}},{"_id":1},max_time_ms=2000)
        return "sealed" if latest else "held"

    async def recover_bulk_copies(self,*,limit=2):
        from core.dragon_crawler import _now,CrawlerError
        from pymongo.errors import PyMongoError
        if not configured():
            return {"configured":False,"network_executed":False}
        if type(limit) is not int or not 1<=limit<=4:
            raise ValueError("copy maintenance bound")
        await self.ensure_indexes()
        now=_now().timestamp()
        candidates=await self.sessions.find({"bulk_copy.state":"pending","bulk_copy_invalidated":False,
            "bulk_copy.expires_at":{"$gt":now},"bulk_copy.retry_at":{"$lte":now},
            "status":{"$in":sorted(TERMINAL)}},{"_id":1,"tenant_id":1,"owner_id":1}
            ).sort([("bulk_copy.retry_at",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        results={"sealed":0,"held":0,"failed":0}
        for item in candidates:
            scope={k:item[k] for k in ("tenant_id","owner_id")}
            try:
                result=await self._finish_bulk_copy(scope,item["_id"])
                results[result]+=1
                if result=="held":
                    await self.sessions.update_one({**scope,"_id":item["_id"],"bulk_copy.state":"pending",
                        "bulk_copy.retry_at":{"$lte":now}},{"$set":{"bulk_copy.retry_at":_now().timestamp()+300}})
            except (ValueError,TypeError,KeyError,CrawlerError,PyMongoError):
                results["failed"]+=1
        return {**results,"network_executed":False}

    async def cleanup_bulk_copies(self,*,limit=2):
        from core.dragon_crawler import _now
        from skeleton.ai.webcrawler.dragon_vault_quota import tombstone
        if not configured():
            return {"configured":False,"cleanup_verified":False}
        if type(limit) is not int or not 1<=limit<=4:
            raise ValueError("cleanup bound")
        await self.ensure_indexes()
        now=_now().timestamp()
        rows=await self.sessions.find({"bulk_copy":{"$exists":True},"$or":[
            {"bulk_copy_invalidated":True},{"bulk_copy.expires_at":{"$lte":now}},{"status":"deleted"}]},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"status":1,"deletion":1,
             "checkpoint_identity":1,"treasury_vault":1,"bulk_copy":1,"bulk_copy_invalidated":1}
            ).sort([("bulk_copy.expires_at",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        cleaned=held=0
        for row in rows:
            scope={k:row[k] for k in ("tenant_id","owner_id")}
            try:
                if row["status"]=="deleted" and not tombstone(row):
                    raise ValueError("deletion witness incomplete")
                mark=validate_marker(scope,row["_id"],row["bulk_copy"])
                outcome=await _io(lambda:_erase(scope,row["_id"],mark))
                if outcome["remaining"]:
                    held+=1
                    continue
                result=await self.sessions.update_one({**scope,"_id":row["_id"],"version":row["version"],
                    "bulk_copy":mark},{"$set":{"last_bulk_cleanup":mark["operation"]},
                    "$unset":{"bulk_copy":"","bulk_copy_invalidated":""}})
                cleaned+=result.modified_count
            except (ValueError,TypeError,KeyError,StorageHeld,sqlite3.Error,OSError,TimeoutError):
                held+=1
        return {"scanned":len(rows),"cleaned":cleaned,"held":held,"physical_secure_erasure":False}
