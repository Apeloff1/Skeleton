"""Owner-scoped cold-custody methods for the canonical crawler application.

There is no copy of text, second source authority, new fetch, or automatic
historical grant. A durable marker precedes quota admission. A crash may hold
both quotas, never release the active slot before retirement is committed.
"""
from __future__ import annotations

from pymongo import ASCENDING,DESCENDING
from pymongo.errors import PyMongoError
from skeleton.ai.webcrawler.dragon_treasury_vault import (
    MAX_VAULT_SESSIONS,TERMINAL,identity,make_marker,validate_marker,
    public_marker,reserve_filter,release_active_filter,
)
from core.dragon_checkpoint_replica import verify_primary,CheckpointReplicaError


class DragonVaultMixin:
    def _vault_primary(self,scope,row):
        from core.dragon_crawler import _now,_utc,_plain,_digest,_core
        if row["status"] not in TERMINAL or row.get("worker_token") is not None or row.get("lease_until") is not None:
            raise ValueError("vault requires quiescent terminal checkpoint")
        now=_now().timestamp()
        if _utc(row["consent_expires_at"]).timestamp()>now:
            raise ValueError("capture consent must expire before retirement")
        watch=row.get("treasury_watch")
        if watch is not None and (not isinstance(watch,dict) or (
                watch.get("enabled") is True and watch.get("expires_at",now+1)>now)):
            raise ValueError("active or invalid watch blocks retirement")
        snapshot=_plain(row["snapshot"])
        verify_primary(snapshot,_plain(row["checkpoint_identity"]))
        binding=snapshot["binding"]
        if (snapshot["state"]!=row["status"] or binding["scope"]!=scope
                or binding["consent"]!=_plain(row["consent"])
                or binding["request_digest"]!=row["request_digest"]
                or _digest(_plain(row["request"]))!=row["request_digest"]
                or abs(_utc(row["consent_expires_at"]).timestamp()-binding["consent"]["expires_at"])>=.002):
            raise ValueError("vault checkpoint scope mismatch")
        _,run_type=_core()
        try:
            run_type.from_snapshot(snapshot)
        except (ValueError,TypeError,KeyError):
            self._legacy_inspection(scope,row,snapshot)
        return snapshot

    async def retire_treasury_session(self,scope,identifier,body,*,principal):
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_plain,_now
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_vault_denied","Owner editor authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or body["retention_acknowledged"] is not True):
            raise CrawlerError("crawler_vault_invalid","Explicit custody and retention acknowledgement required.")
        operation=_operation(body["idempotency_key"])
        digest=_digest({"action":"retire_treasury_session",**body})
        row=await self.sessions.find_one({"_id":identifier,**scope,"status":{"$ne":"deleted"}},max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Crawler session not found.",404)
        existing=row.get("treasury_vault")
        if existing is not None:
            try:
                marker=validate_marker(_plain(existing))
            except (ValueError,TypeError,KeyError) as exc:
                raise CrawlerError("crawler_vault_integrity","Stored retirement receipt is invalid.",503) from exc
            if marker["operation"]==operation:
                if marker["request_digest"]!=digest:
                    raise CrawlerError("crawler_idempotency_conflict","Retirement key names another command.",409)
            elif row["version"]!=body["expected_version"]:
                raise CrawlerError("crawler_conflict","Reload the retirement state.",409)
        else:
            if row["version"]!=body["expected_version"]:
                raise CrawlerError("crawler_conflict","Reload before retiring this expedition.",409)
            try:
                snapshot=self._vault_primary(scope,row)
                marker=make_marker(operation=operation,request_digest=digest,
                    snapshot_digest=snapshot["snapshot_digest"],now=_now().timestamp())
            except (ValueError,TypeError,KeyError,CheckpointReplicaError) as exc:
                raise CrawlerError("crawler_vault_held","Retirement requires witnessed terminal capture, expired consent and no active watch or worker.",409) from exc
            receipt=await self._admit(scope,identifier,{"treasury_vault":marker})
            changed=await self.sessions.update_one({"_id":identifier,**scope,"version":row["version"],
                "status":{"$in":sorted(TERMINAL)},"treasury_vault":{"$exists":False},
                "worker_token":None,"lease_until":None,
                "$expr":{"$lte":["$consent_expires_at","$$NOW"]}},
                {"$set":{"treasury_vault":marker,"storage_receipt":receipt},"$inc":{"version":1}})
            if not changed.modified_count:
                raise CrawlerError("crawler_conflict","Expedition changed before retirement intent.",409)
        outcome=await self._finish_treasury_retirement(scope,identifier)
        latest=await self.sessions.find_one({"_id":identifier,**scope,"status":{"$ne":"deleted"}},
            {"_id":1,"version":1,"treasury_vault":1},max_time_ms=2000)
        if latest is None:
            raise CrawlerError("crawler_not_found","Crawler session not found.",404)
        return {"ok":True,"schema":"skeleton.dragon.vault-command.v1","session_id":identifier,
                "version":int(latest["version"]),"vault":public_marker(_plain(latest["treasury_vault"])),
                "outcome":outcome,"network_executed":False}

    async def _finish_treasury_retirement(self,scope,identifier):
        from core.dragon_crawler import CrawlerError,_plain,_now,_digest
        row=await self.sessions.find_one({"_id":identifier,**scope,"status":{"$ne":"deleted"}},max_time_ms=2000)
        if row is None:
            return "superseded"
        marker=validate_marker(_plain(row["treasury_vault"]))
        if marker["active_slot_released"]:
            return "vaulted"
        fence={"_id":identifier,**scope,"version":row["version"],"status":{"$in":sorted(TERMINAL)},
               "treasury_vault.operation":marker["operation"],"treasury_vault.state":marker["state"],
               "treasury_vault.active_slot_released":False}
        if marker["state"]=="pending":
            try:
                snapshot=self._vault_primary(scope,row)
                if snapshot["snapshot_digest"]!=marker["snapshot_digest"]:
                    raise ValueError("retired checkpoint changed")
            except (ValueError,TypeError,KeyError,CheckpointReplicaError,CrawlerError):
                await self.sessions.update_one(fence,{"$set":{"treasury_vault.retry_at":_now().timestamp()+3600}})
                return "held"
            reserved=await self.limits.update_one(reserve_filter(scope,_digest(scope),identifier),
                {"$addToSet":{"vault_ids":identifier}})
            if not reserved.matched_count:
                await self.sessions.update_one(fence,{"$set":{"treasury_vault.retry_at":_now().timestamp()+300}})
                return "capacity_or_quota_held"
            published=await self.sessions.update_one(fence,
                {"$set":{"treasury_vault.state":"vaulted","treasury_vault.retry_at":_now().timestamp()},
                 "$inc":{"version":1}})
            if not published.modified_count:
                # Never refund a reservation on an uncertain branch: another
                # pulse may already have published it. Deletion removes both.
                return "superseded"
            fence["version"]=row["version"]+1
            fence["treasury_vault.state"]="vaulted"
        released=await self.limits.update_one(release_active_filter(scope,_digest(scope),identifier),
            {"$pull":{"session_ids":identifier}})
        if not released.matched_count:
            await self.sessions.update_one(fence,{"$set":{"treasury_vault.retry_at":_now().timestamp()+3600}})
            return "quota_held"
        changed=await self.sessions.update_one(fence,{"$set":{"treasury_vault.active_slot_released":True}})
        return "vaulted" if changed.modified_count else "superseded"

    async def recover_treasury_retirements(self,*,limit=4):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=4:
            raise ValueError("vault recovery limit exceeded")
        await self.ensure_indexes()
        rows=await self.sessions.find({"status":{"$in":sorted(TERMINAL)},
            "treasury_vault.state":{"$in":["pending","vaulted"]},
            "treasury_vault.active_slot_released":False,
            "treasury_vault.retry_at":{"$lte":_now().timestamp()}},
            {"_id":1,"tenant_id":1,"owner_id":1}).sort(
            [("treasury_vault.retry_at",ASCENDING),("_id",ASCENDING)]).limit(16).max_time_ms(2000).to_list(16)
        totals={"scanned":len(rows),"selected":0,"vaulted":0,"held":0,
                "capacity_or_quota_held":0,"quota_held":0,"superseded":0,"failed":0}
        owners=set()
        for row in rows:
            scope={k:row[k] for k in ("tenant_id","owner_id")}
            owner=tuple(scope.values())
            if owner in owners or totals["selected"]>=limit:
                continue
            owners.add(owner)
            totals["selected"]+=1
            try:
                result=await self._finish_treasury_retirement(scope,row["_id"])
            except (ValueError,KeyError,TypeError,CrawlerError,PyMongoError):
                result="failed"
            totals[result]+=1
        return totals

    async def treasury_vault_catalog(self,scope,*,cursor=None,limit=16):
        from core.dragon_crawler import CrawlerError,_now,_plain
        from skeleton.ai.webcrawler.dragon_archive_grant import validate_grant
        from skeleton.ai.webcrawler.operations import implementation_digest
        if type(limit) is not int or not 1<=limit<=32 or cursor is not None and not identity(cursor):
            raise CrawlerError("crawler_vault_bounds","Invalid vault catalogue page.")
        await self.ensure_indexes()
        query={**scope,"status":{"$in":sorted(TERMINAL)},
               "treasury_vault.state":{"$in":["pending","vaulted"]}}
        if cursor:
            query["_id"]={"$lt":cursor}
        projection={"_id":1,"version":1,"treasury_vault":1,"archive_grant":1,
                    "snapshot.binding.code_digest":1,"checkpoint_identity.snapshot_digest":1}
        async def page():
            return await self.sessions.find(query,projection).sort("_id",DESCENDING).limit(limit+1).max_time_ms(2000).to_list(limit+1)
        rows=await page()
        now=_now().timestamp()
        runtime_digest=implementation_digest()
        result=[]
        for row in rows[:limit]:
            try:
                marker=validate_marker(_plain(row["treasury_vault"]))
                witness=row["checkpoint_identity"]["snapshot_digest"]
                if marker["snapshot_digest"]!=witness:
                    raise ValueError("vault witness no longer matches")
                grant=row.get("archive_grant")
                expiry=None
                if grant is not None:
                    validate_grant(grant)
                    if grant["snapshot_digest"]==witness and grant["issued_at"]<=now<grant["expires_at"]:
                        expiry=grant["expires_at"]
                result.append({"session_id":row["_id"],"version":int(row["version"]),
                    "vault":public_marker(marker),"archive_expires_at":expiry,
                    "legacy_runtime":row["snapshot"]["binding"]["code_digest"]!=runtime_digest,
                    "integrity_held":False})
            except (ValueError,TypeError,KeyError,RecursionError):
                result.append({"session_id":row["_id"],"version":int(row["version"]),
                    "vault":None,"archive_expires_at":None,"legacy_runtime":None,"integrity_held":True})
        final=await page()
        if [(x["_id"],x["version"],x.get("treasury_vault")) for x in rows]!=[
                (x["_id"],x["version"],x.get("treasury_vault")) for x in final]:
            raise CrawlerError("crawler_vault_changed","Vault catalogue changed; reload.",409)
        return {"ok":True,"schema":"skeleton.dragon.vault-catalog.v1","sessions":result,
                "next_cursor":rows[limit-1]["_id"] if len(rows)>limit else None,
                "capacity":MAX_VAULT_SESSIONS,"as_of_unix":now,"archive_use_verified":False,
                "network_executed":False}
