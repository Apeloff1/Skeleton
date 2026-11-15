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
        if row.get("status") not in TERMINAL:
            return "held"
        # Even after publication, a lost or replaced witness must not
        # cause a second mutation that frees active capacity.
        witness=row.get("checkpoint_identity")
        if marker["state"]=="vaulted" and (
                not isinstance(witness,dict) or witness.get("snapshot_digest")!=marker["snapshot_digest"]):
            await self.sessions.update_one({"_id":identifier,**scope,"version":row["version"],
                "treasury_vault.operation":marker["operation"],"treasury_vault.active_slot_released":False},
                {"$set":{"treasury_vault.retry_at":_now().timestamp()+3600}})
            return "held"
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
            fence={**fence,"version":row["version"]+1,"treasury_vault.state":"vaulted"}
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
        if any(item["archive_expires_at"] is not None and item["archive_expires_at"]<=_now().timestamp()
               for item in result):
            raise CrawlerError("crawler_vault_changed","Historical grant expired during catalogue read.",409)
        if [(x["_id"],x["version"],x.get("treasury_vault")) for x in rows]!=[
                (x["_id"],x["version"],x.get("treasury_vault")) for x in final]:
            raise CrawlerError("crawler_vault_changed","Vault catalogue changed; reload.",409)
        return {"ok":True,"schema":"skeleton.dragon.vault-catalog.v1","sessions":result,
                "next_cursor":rows[limit-1]["_id"] if len(rows)>limit else None,
                "capacity":MAX_VAULT_SESSIONS,"as_of_unix":now,"archive_use_verified":False,
                "network_executed":False}


    async def _quota_rows(self,scope,document):
        from skeleton.ai.webcrawler.dragon_vault_quota import quota_lists,MAX_RESERVED
        active,vault=quota_lists(document)
        identifiers=sorted(set(active)|set(vault))
        if not identifiers:
            return []
        return await self.sessions.find({**scope,"_id":{"$in":identifiers}},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"status":1,"deletion":1,
             "treasury_vault":1,"checkpoint_identity.snapshot_digest":1}
        ).sort("_id",ASCENDING).limit(MAX_RESERVED+1).max_time_ms(2000).to_list(MAX_RESERVED+1)

    async def treasury_quota_status(self,scope):
        """Read-only reservation health; no source text or identifier exposure."""
        from core.dragon_crawler import CrawlerError,_digest,_now
        from skeleton.ai.webcrawler.dragon_vault_quota import classify_quota,quota_lists
        query={"_id":_digest(scope),**scope}
        projection={"_id":1,"session_ids":1,"vault_ids":1}
        document=await self.limits.find_one(query,projection,max_time_ms=2000)
        try:
            rows=await self._quota_rows(scope,document)
            counts,_=classify_quota(document,rows,scope)
            final=await self.limits.find_one(query,projection,max_time_ms=2000)
            confirmed=await self._quota_rows(scope,final)
            if final!=document or rows!=confirmed:
                raise CrawlerError("crawler_quota_changed","Quota changed during inspection; refresh.",409)
            quota_lists(final)
        except (ValueError,TypeError,KeyError) as exc:
            raise CrawlerError("crawler_quota_integrity","Quota reservation metadata requires review.",503) from exc
        return {"ok":True,"schema":"skeleton.dragon.vault-quota.v1","as_of_unix":_now().timestamp(),
                **counts,"missing_auto_reclaimed":False,"source_records_erased":False,"read_only":True}

    async def reconcile_treasury_quotas(self,*,limit=2):
        """Conservatively reclaim only proven permanent tombstones.

        Owner quota documents are scanned round-robin by a bounded due marker.
        Missing rows are never reclaimed: creation can have reserved a slot
        before inserting the record. Exact-array CAS defeats concurrent moves.
        """
        from core.dragon_crawler import CrawlerError,_digest,_now
        from skeleton.ai.webcrawler.dragon_vault_quota import classify_quota,quota_fence
        if type(limit) is not int or not 1<=limit<=2:
            raise ValueError("quota repair limit exceeded")
        await self.ensure_indexes()
        now=_now().timestamp()
        documents=await self.limits.find({
            "tenant_id":{"$type":"string"},"owner_id":{"$type":"string"},"session_ids":{"$exists":True},
            "$or":[{"treasury_quota_due":{"$exists":False}},{"treasury_quota_due":{"$lte":now}}]},
            {"_id":1,"tenant_id":1,"owner_id":1,"session_ids":1,"vault_ids":1,"treasury_quota_due":1}
        ).sort([("treasury_quota_due",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        totals={"scanned":len(documents),"audited":0,"reclaimed":0,"missing_held":0,
                "integrity_held":0,"superseded":0,"failed":0}
        for document in documents:
            scope={k:document[k] for k in ("tenant_id","owner_id")}
            if document["_id"]!=_digest(scope):
                totals["failed"]+=1
                continue
            try:
                rows=await self._quota_rows(scope,document)
                counts,removed=classify_quota(document,rows,scope)
                fence=quota_fence(document,scope)
                fence["treasury_quota_due"]=document.get("treasury_quota_due",{"$exists":False})
                update={"$set":{"treasury_quota_due":_now().timestamp()+3600}}
                if removed:
                    update["$pull"]={"session_ids":{"$in":removed},"vault_ids":{"$in":removed}}
                changed=await self.limits.update_one(fence,update)
                if not changed.modified_count:
                    totals["superseded"]+=1
                    continue
                totals["audited"]+=1
                totals["reclaimed"]+=len(removed)
                totals["missing_held"]+=counts["missing"]
                totals["integrity_held"]+=counts["integrity_held"]
            except (ValueError,TypeError,KeyError,CrawlerError,PyMongoError):
                totals["failed"]+=1
                # Quarantine the scheduler cursor without editing malformed
                # reservations. Never allow one broken owner to monopolize it.
                await self.limits.update_one({"_id":document["_id"],**scope,
                    "treasury_quota_due":document.get("treasury_quota_due",{"$exists":False})},
                    {"$set":{"treasury_quota_due":_now().timestamp()+3600}})
        return totals


    def _discover_vault_row(self,scope,row,terms,now):
        """Qualify original bytes before any lexical operation."""
        from core.dragon_crawler import _plain
        from skeleton.ai.webcrawler.dragon_archive_grant import validate_grant,archive_expiry
        from skeleton.ai.webcrawler.dragon_vault_discovery import summarize_sources
        from skeleton.ai.webcrawler.operations import implementation_digest
        marker=validate_marker(_plain(row["treasury_vault"]))
        if marker["state"]!="vaulted":
            raise ValueError("chamber not retired")
        grant=row.get("archive_grant")
        if grant is None:
            return "no_grant",None,None
        grant=_plain(grant)
        validate_grant(grant)
        if not grant["issued_at"]<=now<grant["expires_at"]:
            return "no_grant",None,None
        snapshot=self._vault_primary(scope,row)
        if snapshot["snapshot_digest"]!=marker["snapshot_digest"] or grant["snapshot_digest"]!=marker["snapshot_digest"]:
            raise ValueError("chamber grant/witness mismatch")
        policies=self._source_policies(row)
        if set(policies)-set(snapshot["sources"]):
            raise ValueError("chamber orphan policy")
        permitted_ids=set(snapshot["sources"])
        if snapshot["binding"]["code_digest"]!=implementation_digest():
            proof=self._legacy_inspection(scope,row,snapshot)
            if row.get("legacy_archive_receipt")!=proof:
                raise ValueError("older chamber lacks historical-use admission")
            permitted_ids=set(proof["verified_source_ids"])
        permitted=[]
        for sid in sorted(permitted_ids):
            source=snapshot["sources"][sid]
            if archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                    policy=policies.get(sid,{"enabled":True,"version":0}),now=now) is not None:
                permitted.append(source)
        if not permitted:
            return "no_grant",None,None
        summary=summarize_sources(permitted,terms)
        return "qualified",{"session_id":row["_id"],"version":row["version"],
                          "valid_until":grant["expires_at"],**summary},grant["expires_at"]

    async def discover_treasury_vault(self,scope,*,query,cursor=None):
        """Scan up to eight original cold-custody records per page.

        Cursor binds the complete bounded metadata catalogue and grant-active
        states, but each page rechecks current archive authority independently.
        Results are page-local candidate advice, not an exhaustive global rank.
        """
        import asyncio
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_vault_discovery import (
            PAGE,query_terms,catalogue_signature,digest_scope,page_offset,order_matches,
        )
        try:
            terms=query_terms(query)
        except (ValueError,UnicodeError) as exc:
            raise CrawlerError("crawler_vault_query","Enter a bounded lexical query.") from exc
        await self.ensure_indexes()
        catalogue={**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        projection={"_id":1,"version":1,"archive_grant.issued_at":1,"archive_grant.expires_at":1}
        async def metadata():
            return await self.sessions.find(catalogue,projection).sort("_id",DESCENDING).limit(
                MAX_VAULT_SESSIONS+1).max_time_ms(2000).to_list(MAX_VAULT_SESSIONS+1)
        now=_now().timestamp()
        rows=await metadata()
        try:
            signature=catalogue_signature(rows,now=now)
            bound=digest_scope(scope,signature,terms)
            offset=page_offset(cursor,bound,len(rows))
        except (ValueError,TypeError,KeyError) as exc:
            raise CrawlerError("crawler_vault_search_changed","Chamber catalogue or search cursor changed. Restart from the first page.",409) from exc
        matches=[]
        counts={"qualified":0,"no_grant":0,"held":0,"eligible_sources":0,"scanned_bytes":0}
        expiries=[]
        for item in rows[offset:offset+PAGE]:
            row=await self.sessions.find_one({**catalogue,"_id":item["_id"],"version":item["version"]},
                  max_time_ms=2000)
            if row is None:
                raise CrawlerError("crawler_vault_search_changed","Chamber changed during discovery.",409)
            try:
                status,summary,expiry=await asyncio.to_thread(self._discover_vault_row,scope,row,terms,now)
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError,CrawlerError):
                status,summary,expiry="held",None,None
            counts[status]+=1
            if summary is not None:
                counts["eligible_sources"]+=summary["eligible_sources"]
                counts["scanned_bytes"]+=summary["scanned_bytes"]
                if summary["matched_sources"]:
                    matches.append(summary)
            if expiry is not None:
                expiries.append(expiry)
        final=await metadata()
        final_time=_now().timestamp()
        try:
            if catalogue_signature(final,now=final_time)!=signature or (expiries and min(expiries)<=final_time):
                raise ValueError("chamber authority changed")
        except (ValueError,TypeError,KeyError) as exc:
            raise CrawlerError("crawler_vault_search_changed","Chamber catalogue or historical authority changed during scan.",409) from exc
        scanned=min(PAGE,len(rows)-offset)
        next_offset=offset+scanned
        return {"ok":True,"schema":"skeleton.dragon.vault-discovery.v1","scope_digest":bound,
                "as_of_unix":now,"earliest_expiry":min(expiries) if expiries else None,
                "catalogue_size":len(rows),"page_offset":offset,"scanned_sessions":scanned,
                "query_terms":len(terms),**counts,"matches":order_matches(matches),
                "next_cursor":bound+":"+str(next_offset) if next_offset<len(rows) else None,
                "page_local_ranking":True,"source_text_returned":False,"network_executed":False,
                "model_context_permission":False}
