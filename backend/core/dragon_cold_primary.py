"""Explicit dual-manifest cold-primary migration for final terminal archives.

Before Mongo payload removal, verify independent copies of the exact checkpoint.
The Mongo row remains the authoritative version/consent/policy/tombstone ledger.
Reads rehydrate exact data, never change source authority. Restore is atomic and
cleanup is retryable. Disabled by default; not a general Mongo migration.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from core.dragon_checkpoint_replica import verify_primary,CheckpointReplicaError,checkpoint_fields
from core.dragon_hoarder_bulk import StorageHeld,owner_key
from core.dragon_hoarder_copy import _archive,_io
from core.dragon_hoarder_manifests import BLOCK
from core.dragon_hoarder_qualification import open_backup,independent,require_probe
from skeleton.ai.webcrawler.dragon_treasury_vault import identity,hash_identity
from skeleton.ai.webcrawler.dragon_archive_scale import digest

SCHEMA="dragon.cold-primary.v1"
MAX_BYTES=4*1024*1024


def _logical(session):
    if not identity(session):raise ValueError("session identity")
    return "dragon-cold-primary:"+session


def _mid(scope,session,operation):
    return hashlib.sha256(json.dumps([owner_key(scope),_logical(session),operation],separators=(",",":")).encode()).hexdigest()


def _marker(scope,session,mark):
    keys={"schema","operation","manifest","sha256","bytes","snapshot_digest","state","grant_digest","policy_digest",
          "expires_at","qualification_digest"}
    if (not isinstance(mark,dict) or set(mark)!=keys or mark["schema"]!=SCHEMA
        or not all(hash_identity(mark[k]) for k in ("operation","manifest","sha256","snapshot_digest","grant_digest","policy_digest","qualification_digest"))
        or mark["manifest"]!=_mid(scope,session,mark["operation"]) or type(mark["bytes"]) is not int or not 1<=mark["bytes"]<=MAX_BYTES
        or type(mark["expires_at"]) not in (int,float) or not 0<mark["expires_at"]<1e12
        or mark["state"] not in {"staging","relocated","restored"}):
        raise StorageHeld("cold-primary marker differs")
    return mark


def _stores():
    primary=_archive()
    backup=open_backup()
    independent(primary,backup)
    return primary,backup


def _stage_one(store,scope,session,mark,raw):
    mid=store.begin(scope,logical_key=_logical(session),operation=mark["operation"],
                    expected_hash=mark["sha256"],expected_bytes=mark["bytes"])
    if mid["manifest"]!=mark["manifest"] or mid["state"]=="aborted":
        raise StorageHeld("cold intent unavailable")
    if mid["state"]=="building":
        for ordinal,start in enumerate(range(0,len(raw),BLOCK)):
            store.append(scope,mark["manifest"],ordinal,raw[start:start+BLOCK])
    sealed=store.seal(scope,mark["manifest"])
    if sealed["sha256"]!=mark["sha256"] or sealed["bytes"]!=len(raw):
        raise StorageHeld("cold manifest receipt differs")
    if _read_one(store,scope,mark)!=raw:
        raise StorageHeld("cold readback differs")


def _read_one(store,scope,mark):
    if hasattr(store,"read_document"):
        raw=store.read_document(scope,mark["manifest"],maximum_bytes=MAX_BYTES)
    else:
        raw=b"".join(store.read_chunk(scope,mark["manifest"],i) for i in range((mark["bytes"]+BLOCK-1)//BLOCK))
    if len(raw)!=mark["bytes"] or hashlib.sha256(raw).hexdigest()!=mark["sha256"]:
        raise StorageHeld("cold payload witness differs")
    return raw


def _stage_both(scope,session,mark,raw):
    primary,backup=_stores()
    evidence=require_probe(primary,backup)
    if evidence["receipt_sha256"]!=mark["qualification_digest"]:
        raise StorageHeld("qualification witness changed during migration")
    for archive in (primary,backup):
        _stage_one(archive,scope,session,mark,raw)
    return evidence


def _compact_both(scope,mark,raw):
    """Migrate the backup first; retain exact recoverability on each plane.

    Both stores must contain the original independently verified bytes.
    A crash between planes leaves mixed layouts, both readable; retry
    exact marker/byte identities. Never rebuild a missing replica here.
    """
    primary,backup=_stores()
    evidence=require_probe(primary,backup)
    if evidence["receipt_sha256"]!=mark["qualification_digest"]:
        raise StorageHeld("independent qualification witness changed")
    if any(_read_one(store,scope,mark)!=raw for store in (primary,backup)):
        raise StorageHeld("dual-custody payload differs")
    secondary=backup.migrate_content_defined(scope,mark["manifest"],raw)
    if _read_one(backup,scope,mark)!=raw:
        raise StorageHeld("backup migration readback failed")
    first=primary.migrate_content_defined(scope,mark["manifest"],raw)
    if any(_read_one(store,scope,mark)!=raw for store in (primary,backup)):
        raise StorageHeld("dual-custody final readback differs")
    return {"primary":first,"backup":secondary,"independent_readback_verified":True,
            "qualification_digest":evidence["receipt_sha256"],"cross_store_atomic":False,
            "canonical_primary_replaced":False,"source_authorized":False}


def custody_snapshot(row):
    """Return exact Mongo or cold bytes. An offloaded row cannot fall through
    to checkpoint repair or a stale replica. Readback is bounded to 4 MiB.
    """
    if isinstance(row.get("snapshot"),dict):return row["snapshot"]
    if not row.get("cold_primary"):
        raise CheckpointReplicaError("primary checkpoint unavailable")
    from core.dragon_crawler import CrawlerError
    scope={k:row[k] for k in ("tenant_id","owner_id")}
    try:
        mark=_marker(scope,row["_id"],row["cold_primary"])
        if mark["state"]!="relocated" or row["status"] not in {"completed","budget_exhausted"}:
            raise StorageHeld("cold primary not published")
        # Attempt primary and then isolated backup. Read authority stays in
        # Mongo; internal custody restoration can occur after grant expiry.
        raw=None
        for opener in (_archive,open_backup):
            try:
                raw=_read_one(opener(),scope,mark)
                snap=json.loads(raw)
                verify_primary(snap,row["checkpoint_identity"])
                if snap["snapshot_digest"]!=mark["snapshot_digest"] or snap["binding"]["scope"]!=scope:
                    raise StorageHeld("external snapshot binding differs")
                return snap
            except (OSError,sqlite3.Error,ValueError,KeyError,TypeError,StorageHeld,CheckpointReplicaError):
                continue
        raise StorageHeld("both external copies unavailable")
    except (StorageHeld,OSError,sqlite3.Error,ValueError,KeyError,TypeError,CheckpointReplicaError) as exc:
        raise CrawlerError("crawler_cold_primary_held","Exact relocated archive is unavailable.",503) from exc


def _erase_both(scope,session,mark):
    for archive in _stores():
        mid=archive.abort_intent(scope,logical_key=_logical(session),operation=mark["operation"],
            expected_hash=mark["sha256"],expected_bytes=mark["bytes"])
        if mid!=mark["manifest"]:raise StorageHeld("cleanup witness")
        if archive.collect_manifest(scope,mid,limit=32)["remaining"]:return False
    return True


class DragonColdPrimaryMixin:
    def _custody_snapshot(self,row):
        return custody_snapshot(row)

    async def relocate_cold_primary(self,scope,identifier,body,*,principal):
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_now,_encoded,_plain
        if os.getenv("SKL_DRAGON_ENABLE_COLD_PRIMARY")!="1":
            raise CrawlerError("crawler_cold_disabled","Cold-primary relocation is disabled.",503)
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"} or body.get("acknowledged") is not True:
            raise CrawlerError("crawler_cold_denied","Explicit owner editor migration permission required.",403)
        if not identity(identifier) or set(body)!={"expected_version","idempotency_key","acknowledged"} or type(body["expected_version"]) is not int:
            raise ValueError("migration request")
        op=_operation(body["idempotency_key"])
        row=await self.sessions.find_one({**scope,"_id":identifier,"status":{"$in":["completed","budget_exhausted"]},
            "deep_archive.released":True},max_time_ms=2000)
        if not row:raise CrawlerError("crawler_cold_held","Final archive custody is required.",409)
        previous=row.get("cold_primary")
        if previous:
            mark=_marker(scope,identifier,previous)
            if mark["operation"]!=op:raise CrawlerError("crawler_cold_conflict","Another cold operation exists.",409)
            if mark["state"]=="relocated":
                return {"session_id":identifier,"state":"relocated","version":row["version"],"sha256":mark["sha256"],"replayed":True}
            if mark["state"]!="staging":raise CrawlerError("crawler_cold_conflict","Restore cleanup pending.",409)
        else:
            if row["version"]!=body["expected_version"] or row.get("last_cold_cleanup")==op:
                raise CrawlerError("crawler_cold_conflict","Reload or choose a new operation.",409)
            # Every source must qualify for retained storage. The snapshot is
            # still authoritative in Mongo through all staging failure paths.
            raw_payload,payload,binding=await _io(lambda:self._copy_material(scope,row,_now().timestamp()))
            del raw_payload
            raw=_encoded(payload["snapshot"],MAX_BYTES)
            evidence=await _io(lambda:require_probe(*_stores()))
            mark=_marker(scope,identifier,{"schema":SCHEMA,"operation":op,"manifest":_mid(scope,identifier,op),
                "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"snapshot_digest":binding["snapshot_digest"],
                "grant_digest":binding["grant_digest"],"policy_digest":binding["policy_digest"],
                "expires_at":binding["expires_at"],"qualification_digest":evidence["receipt_sha256"],"state":"staging"})
            await self._admit(scope,identifier,{"cold_primary":mark,"snapshot":payload["snapshot"]})
            result=await self.sessions.update_one({**scope,"_id":identifier,"version":row["version"],"cold_primary":{"$exists":False}},
                {"$set":{"cold_primary":mark,"cold_primary_invalidated":False},"$inc":{"version":1}})
            if not result.modified_count:raise CrawlerError("crawler_cold_conflict","Migration intent raced.",409)
        await self._finish_cold(scope,identifier)
        latest=await self.sessions.find_one({**scope,"_id":identifier,"cold_primary.operation":op},
            {"cold_primary":1,"version":1},max_time_ms=2000)
        if not latest:raise CrawlerError("crawler_cold_conflict","Migration intent withdrawn.",409)
        return {"session_id":identifier,"state":latest["cold_primary"]["state"],"version":latest["version"],
                "sha256":mark["sha256"],"replayed":False,"primary_replaced":latest["cold_primary"]["state"]=="relocated"}

    async def _finish_cold(self,scope,identifier):
        from core.dragon_crawler import _now,_encoded
        if os.getenv("SKL_DRAGON_ENABLE_COLD_PRIMARY")!="1":return "held"
        now=_now().timestamp()
        predicate={**scope,"_id":identifier,"status":{"$in":["completed","budget_exhausted"]},
            "deep_archive.released":True,"cold_primary.state":"staging","cold_primary_invalidated":False,
            "cold_primary.expires_at":{"$gt":now}}
        row=await self.sessions.find_one(predicate,max_time_ms=2000)
        if not row:return "held"
        mark=_marker(scope,identifier,row["cold_primary"])
        def stage():
            _,payload,binding=self._copy_material(scope,row,_now().timestamp())
            raw=_encoded(payload["snapshot"],MAX_BYTES)
            if hashlib.sha256(raw).hexdigest()!=mark["sha256"] or len(raw)!=mark["bytes"] or any(
                binding[k]!=mark[k] for k in ("snapshot_digest","grant_digest","policy_digest","expires_at")):
                raise StorageHeld("source grant or payload changed")
            return _stage_both(scope,identifier,mark,raw)
        await _io(stage)
        # Mongo retains the canonical checkpoint identity and source policy,
        # but the primary payload and embedded compressed replica leave Mongo.
        fence={**predicate,"version":row["version"],"cold_primary":mark,
               "archive_grant":row["archive_grant"],"checkpoint_identity":row["checkpoint_identity"],
               "$expr":{"$gt":["$cold_primary.expires_at",{"$divide":[{"$toLong":"$$NOW"},1000]}]}}
        changed=await self.sessions.update_one(fence,{"$set":{"cold_primary.state":"relocated"},
            "$unset":{"snapshot":"","checkpoint_replica":""},"$inc":{"version":1}})
        return "relocated" if changed.modified_count else "superseded"

    async def compact_cold_primary(self,scope,identifier,body,*,principal):
        """Explicit migration of both currently retained relocated copies."""
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_now,_encoded
        if os.getenv("SKL_DRAGON_ENABLE_COLD_PRIMARY")!="1":
            raise CrawlerError("crawler_cold_disabled","Cold-primary relocation is disabled.",503)
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"} or body.get("acknowledged") is not True:
            raise CrawlerError("crawler_cold_denied","Explicit owner editor migration permission required.",403)
        if not identity(identifier) or set(body)!={"expected_version","idempotency_key","acknowledged"} or type(body["expected_version"]) is not int or body["expected_version"]<1:
            raise ValueError("compaction request")
        _operation(body["idempotency_key"])
        predicate={**scope,"_id":identifier,"status":{"$in":["completed","budget_exhausted"]},
            "deep_archive.released":True,"cold_primary.state":"relocated","cold_primary_invalidated":False,
            "cold_primary.expires_at":{"$gt":_now().timestamp()},"version":body["expected_version"]}
        row=await self.sessions.find_one(predicate,max_time_ms=2000)
        if not row:raise CrawlerError("crawler_cold_conflict","Reload the current relocated archive.",409)
        mark=_marker(scope,identifier,row["cold_primary"])
        fence={**predicate,"cold_primary":mark,"archive_grant":row["archive_grant"],
            "checkpoint_identity":row["checkpoint_identity"],
            "source_use_policies":row.get("source_use_policies",{"$exists":False})}
        def material():
            _,payload,binding=self._copy_material(scope,row,_now().timestamp())
            raw=_encoded(payload["snapshot"],MAX_BYTES)
            if (len(raw)!=mark["bytes"] or hashlib.sha256(raw).hexdigest()!=mark["sha256"]
                    or any(binding[k]!=mark[k] for k in ("snapshot_digest","grant_digest","policy_digest","expires_at"))):
                raise StorageHeld("cold source authority or bytes changed")
            return raw
        try:
            raw=await _io(material)
            if not await self.sessions.find_one(fence,{"_id":1},max_time_ms=2000):
                raise StorageHeld("cold migration authority changed")
            result=await _io(lambda:_compact_both(scope,mark,raw) if _now().timestamp()<mark["expires_at"]
                else (_ for _ in ()).throw(StorageHeld("cold migration grant expired")))
            if _now().timestamp()>=mark["expires_at"] or not await self.sessions.find_one(fence,{"_id":1},max_time_ms=2000):
                raise StorageHeld("cold migration authority changed during conversion")
        except (CrawlerError,StorageHeld,CheckpointReplicaError,ValueError,KeyError,TypeError,sqlite3.Error,OSError,TimeoutError) as exc:
            raise CrawlerError("crawler_cold_compaction_held","Dual migration held; current mixed layouts remain readable or require custody repair.",409) from exc
        return {"session_id":identifier,"version":row["version"],"migration":result,
                "network_executed":False,"source_authorized":False}

    async def restore_cold_primary(self,scope,identifier,*,expected_version):
        """Restore before erasing copies. No grant renewal or source exposure."""
        from core.dragon_crawler import CrawlerError,_now
        row=await self.sessions.find_one({**scope,"_id":identifier,"cold_primary.state":{"$in":["relocated","staging"]},
            "status":{"$in":["completed","budget_exhausted"]}},max_time_ms=2000)
        if not row or row["version"]!=expected_version:
            raise CrawlerError("crawler_cold_conflict","Reload cold archive version.",409)
        mark=_marker(scope,identifier,row["cold_primary"])
        snapshot=await _io(lambda:custody_snapshot(row))
        # The original identity explicitly binds the same exact snapshot. A
        # normal checkpoint reconstruction may regenerate only the replica.
        fields=checkpoint_fields(snapshot)
        verify_primary(snapshot,fields["checkpoint_identity"])
        await self._admit(scope,identifier,fields)
        changed=await self.sessions.update_one({**scope,"_id":identifier,"version":expected_version,"cold_primary":mark},
            {"$set":{**fields,"cold_primary.state":"restored","cold_primary_invalidated":True},"$inc":{"version":1}})
        if not changed.modified_count:raise CrawlerError("crawler_cold_conflict","Restore raced.",409)
        return {"session_id":identifier,"state":"restored","version":expected_version+1,"source_use_extended":False}

    async def reconcile_cold_primaries(self):
        from core.dragon_crawler import CrawlerError,_now
        now=_now().timestamp()
        if not getattr(self,"_cold_index_ready",False):
            await self.sessions.create_index([("cold_primary.state",1),("cold_primary.expires_at",1)])
            self._cold_index_ready=True
        rows=await self.sessions.find({"cold_primary":{"$exists":True},"$or":[
            {"status":"deleted"},{"cold_primary_invalidated":True},{"cold_primary.expires_at":{"$lte":now}},
            {"cold_primary.state":"staging"}]},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"status":1,"cold_primary":1,"cold_primary_invalidated":1,"deletion":1}
            ).sort([("cold_primary.expires_at",1),("_id",1)]).limit(4).max_time_ms(2000).to_list(4)
        result={"scanned":len(rows),"relocated":0,"restored":0,"cleaned":0,"held":0}
        for row in rows:
            scope={k:row[k] for k in ("tenant_id","owner_id")}
            try:
                mark=_marker(scope,row["_id"],row["cold_primary"])
                withdrawn=row.get("cold_primary_invalidated") or mark["expires_at"]<=now or row["status"]=="deleted"
                if not withdrawn and mark["state"]=="staging":
                    if await self._finish_cold(scope,row["_id"])=="relocated":result["relocated"]+=1
                    else:result["held"]+=1
                    continue
                if row["status"]!="deleted" and mark["state"]!="restored":
                    await self.restore_cold_primary(scope,row["_id"],expected_version=row["version"])
                    result["restored"]+=1
                    continue
                if row["status"]=="deleted" and not isinstance(row.get("deletion"),dict):
                    raise StorageHeld("deletion tombstone unavailable")
                if await _io(lambda:_erase_both(scope,row["_id"],mark)):
                    changed=await self.sessions.update_one({**scope,"_id":row["_id"],"version":row["version"],"cold_primary":mark},
                        {"$unset":{"cold_primary":"","cold_primary_invalidated":""},"$set":{"last_cold_cleanup":mark["operation"]}})
                    result["cleaned"]+=changed.modified_count
                else:result["held"]+=1
            except (CrawlerError,StorageHeld,ValueError,KeyError,TypeError,sqlite3.Error,OSError,TimeoutError):
                result["held"]+=1
        return result
