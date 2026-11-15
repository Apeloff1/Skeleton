"""Owner-scoped cold-custody methods for the canonical crawler application.

There is no copy of text, second source authority, new fetch, or automatic
historical grant. A durable marker precedes quota admission. A crash may hold
both quotas, never release the active slot before retirement is committed.
"""
from __future__ import annotations

import asyncio
import threading

from pymongo import ASCENDING,DESCENDING
from pymongo.errors import PyMongoError
from skeleton.ai.webcrawler.dragon_treasury_vault import (
    MAX_VAULT_SESSIONS,TERMINAL,identity,make_marker,validate_marker,
    public_marker,reserve_filter,release_active_filter,
)
from core.dragon_checkpoint_replica import (
    verify_primary,decode_exact_replica,reconstruct_exact_replica,validate_identity,CheckpointReplicaError,
)


# Separate process-wide CPU admission. Keep the permit until the real thread
# finishes, even if the requesting HTTP coroutine has been cancelled.
_DISCOVERY_CPU=threading.BoundedSemaphore(2)


async def _bounded_discovery_cpu(operation,*args):
    from core.dragon_crawler import CrawlerError
    gate=_DISCOVERY_CPU
    if not gate.acquire(blocking=False):
        raise CrawlerError("crawler_vault_busy","Historical chamber parsing is at local capacity. Retry after the active scan completes.",429)
    try:
        future=asyncio.get_running_loop().run_in_executor(None,operation,*args)
    except BaseException:
        gate.release()
        raise

    def finished(result):
        gate.release()
        # Observe any late exception even if the client detached.
        if not result.cancelled():
            result.exception()

    future.add_done_callback(finished)
    return await asyncio.shield(future)


class DragonVaultMixin:
    def _vault_primary(self,scope,row):
        from core.dragon_crawler import _now,_utc,_plain,_digest,_core
        if (row["status"] not in TERMINAL or row.get("worker_token") is not None
                or row.get("lease_until") is not None or row.get("last_worker_exit_confirmed") is False):
            raise ValueError("vault requires quiescent terminal checkpoint")
        now=_now().timestamp()
        if _utc(row["consent_expires_at"]).timestamp()>now:
            raise ValueError("capture consent must expire before retirement")
        watch=row.get("treasury_watch")
        if watch is not None and (not isinstance(watch,dict) or (
                watch.get("enabled") is True and watch.get("expires_at",now+1)>now)):
            raise ValueError("active or invalid watch blocks retirement")
        snapshot=_plain(self._custody_snapshot(row))
        verify_primary(snapshot,_plain(row["checkpoint_identity"]))
        binding=snapshot["binding"]
        if (snapshot["state"]!=row["status"] or binding["scope"]!=scope
                or binding["consent"]!=_plain(row["consent"])
                or binding["request_digest"]!=row["request_digest"]
                or _digest(_plain(row["request"]))!=row["request_digest"]
                or abs(_utc(row["consent_expires_at"]).timestamp()-binding["consent"]["expires_at"])>=.002):
            raise ValueError("vault checkpoint scope mismatch")
        if snapshot.get("pending_dispatch") is not None or set(self._source_policies(row))-set(snapshot["sources"]):
            raise ValueError("terminal source or pending-dispatch custody mismatch")
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
                "worker_token":None,"lease_until":None,"last_worker_exit_confirmed":{"$ne":False},
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
               "treasury_vault.state":{"$in":["pending","vaulted"]},"deep_archive.released":{"$ne":True}}
        if cursor:
            query["_id"]={"$lt":cursor}
        projection={"_id":1,"version":1,"treasury_vault":1,"archive_grant":1,
                    "snapshot.binding.code_digest":1,"checkpoint_identity.snapshot_digest":1,
                    "treasury_vault_scrub":1,"treasury_vault_care":1}
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
                # The primary may be missing or corrupt. A surviving exact
                # marker/witness must keep the repair controls reachable.
                from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity
                snapshot=row.get("snapshot")
                binding=snapshot.get("binding") if isinstance(snapshot,dict) else None
                code=binding.get("code_digest") if isinstance(binding,dict) else None
                legacy=code!=runtime_digest if hash_identity(code) else None
                audit=self._public_vault_scrub(row,now,witness)
                result.append({"session_id":row["_id"],"version":int(row["version"]),
                    "vault":public_marker(marker),"archive_expires_at":expiry,
                    "legacy_runtime":legacy,"integrity_held":False,"last_scrub":audit,
                    "care":self._public_care(row,now,witness)})
            except (ValueError,TypeError,KeyError,RecursionError):
                result.append({"session_id":row["_id"],"version":int(row["version"]),
                    "vault":None,"archive_expires_at":None,"legacy_runtime":None,"integrity_held":True,
                    "last_scrub":None,"care":None})
        final=await page()
        if any(item["archive_expires_at"] is not None and item["archive_expires_at"]<=_now().timestamp()
               for item in result):
            raise CrawlerError("crawler_vault_changed","Historical grant expired during catalogue read.",409)
        if rows!=final or any(item.get("care") and item["care"]["active"]
                and item["care"]["expires_at"]<=_now().timestamp() for item in result):
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
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_vault_discovery import (
            PAGE,query_terms,catalogue_signature,digest_scope,page_offset,order_matches,
        )
        try:
            terms=query_terms(query)
        except (ValueError,UnicodeError) as exc:
            raise CrawlerError("crawler_vault_query","Enter a bounded lexical query.") from exc
        await self.ensure_indexes()
        catalogue={**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted","deep_archive.released":{"$ne":True}}
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
                status,summary,expiry=await _bounded_discovery_cpu(self._discover_vault_row,scope,row,terms,now)
            except CrawlerError as exc:
                if exc.code=="crawler_vault_busy":
                    # Transient local capacity must not masquerade as a
                    # source-integrity hold or advance the scan cursor.
                    raise
                status,summary,expiry="held",None,None
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError):
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


    def _prepare_vault_restore(self,scope,row):
        """Validate identical current witness bytes, never execute old runtime."""
        from core.dragon_crawler import _plain
        marker=validate_marker(_plain(row["treasury_vault"]))
        if marker["state"]!="vaulted" or row.get("last_worker_exit_confirmed") is False:
            raise ValueError("cold custody or physical quiescence not established")
        witness=_plain(row["checkpoint_identity"])
        if witness["snapshot_digest"]!=marker["snapshot_digest"]:
            raise ValueError("retirement marker and original witness disagree")
        # A valid primary needs no write. Do not overwrite healthy bytes
        # just because the duplicate is missing, corrupt or unavailable.
        from core.dragon_crawler import CrawlerError
        try:
            self._vault_primary(scope,row)
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError,CrawlerError):
            candidate=decode_exact_replica(row.get("checkpoint_replica"),witness)
            self._vault_primary(scope,{**row,"snapshot":candidate})
            if candidate.get("pending_dispatch") is not None:
                raise ValueError("pending network dispatch cannot be archived as quiescent")
            return candidate
        return None

    async def restore_treasury_vault(self,scope,identifier,body,*,principal):
        """Explicit repair of only a retired, witnessed original primary.

        Expired source-use permission is not restored or extended. A
        missing witness, absent replica, changed row, old ancestor or
        uncertain physical worker is held. No snapshot leaves this method.
        """
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_plain,_now
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_vault_denied","Owner editor authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or body["retention_acknowledged"] is not True):
            raise CrawlerError("crawler_vault_invalid","Explicit custody acknowledgement required.")
        operation=_operation(body["idempotency_key"])
        digest=_digest({"action":"restore_treasury_vault",**body})
        query={"_id":identifier,**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Retired expedition not found.",404)
        unavailable=CrawlerError("crawler_vault_restore_held","Exact original custody cannot be restored safely.",409)
        previous=row.get("treasury_vault_restore")
        if previous is not None:
            from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity
            if (not isinstance(previous,dict)
                    or set(previous)!={"operation","request_digest","snapshot_digest","published_version","repaired_at"}
                    or not all(hash_identity(previous.get(key)) for key in ("operation","request_digest","snapshot_digest"))
                    or type(previous.get("published_version")) is not int
                    or not 1<=previous["published_version"]<=row["version"]
                    or not isinstance(previous["repaired_at"],str)
                    or not 1<=len(previous["repaired_at"])<=64):
                raise unavailable
        replay=isinstance(previous,dict) and previous.get("operation")==operation
        if replay and previous.get("request_digest")!=digest:
            raise CrawlerError("crawler_idempotency_conflict","Restore key names a different command.",409)
        if not replay and row["version"]!=body["expected_version"]:
            raise CrawlerError("crawler_conflict","Reload before repairing the retained record.",409)
        try:
            marker=validate_marker(_plain(row["treasury_vault"]))
            witness=_plain(row["checkpoint_identity"])
            candidate=await _bounded_discovery_cpu(self._prepare_vault_restore,scope,row)
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError) as exc:
            raise unavailable from exc
        except CrawlerError as exc:
            if exc.code=="crawler_vault_busy":
                raise
            raise unavailable from exc
        fence={**query,"version":row["version"],"checkpoint_identity":row["checkpoint_identity"],
               "treasury_vault.operation":marker["operation"],"treasury_vault.snapshot_digest":marker["snapshot_digest"],
               "worker_token":None,"lease_until":None,"last_worker_exit_confirmed":{"$ne":False},
               "consent_expires_at":row["consent_expires_at"],
               "$expr":{"$lte":["$consent_expires_at","$$NOW"]}}
        if replay:
            if (candidate is not None or previous.get("snapshot_digest")!=marker["snapshot_digest"]
                    or previous.get("published_version")>row["version"]):
                raise unavailable
            outcome="restored"
        elif candidate is None:
            outcome="already_intact"
        else:
            # Publish only the original exact primary, not an updated/rebound
            # checkpoint, new replica, policy, authority or grant. Derived
            # postings are invalidated and must pass normal maintenance.
            repair={"operation":operation,"request_digest":digest,
                    "snapshot_digest":witness["snapshot_digest"],"published_version":row["version"]+1,
                    "repaired_at":_now().isoformat()}
            receipt=await self._admit(scope,identifier,{"snapshot":candidate,"treasury_vault_restore":repair})
            result=await self.sessions.update_one(fence,{"$set":{"snapshot":candidate,
                 "treasury_vault_restore":repair,"storage_receipt":receipt,"treasury_repair_due":_now().timestamp()},
                 "$unset":{"treasury_index":"","treasury_archive_route":""},"$inc":{"version":1}})
            if not result.modified_count:
                raise CrawlerError("crawler_conflict","Retained record changed before repair publication.",409)
            fence={**fence,"version":row["version"]+1}
            outcome="restored"
        current=await self.sessions.find_one(fence,max_time_ms=2000)
        if current is None:
            raise CrawlerError("crawler_conflict","Retained record changed before repair confirmation.",409)
        try:
            if await _bounded_discovery_cpu(self._prepare_vault_restore,scope,current) is not None:
                raise ValueError("restored primary did not qualify")
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError) as exc:
            raise unavailable from exc
        return {"ok":True,"schema":"skeleton.dragon.vault-restore.v1","session_id":identifier,
                "version":current["version"],"outcome":outcome,"snapshot_digest":marker["snapshot_digest"],
                "ancestor_rollback":False,"capture_consent_extended":False,"historical_grant_extended":False,
                "network_executed":False,"model_context_permission":False}


    def _inspect_vault_redundancy(self,scope,row):
        from core.dragon_crawler import _plain
        from core.dragon_crawler import CrawlerError
        marker=validate_marker(_plain(row["treasury_vault"]))
        witness=validate_identity(_plain(row["checkpoint_identity"]))
        if marker["state"]!="vaulted" or witness["snapshot_digest"]!=marker["snapshot_digest"]:
            raise ValueError("vault witness mismatch")
        primary="held"
        replica="unavailable"
        try:
            self._vault_primary(scope,row)
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError,CrawlerError):
            pass
        else:
            primary="exact"
        if witness.get("replica_available") is True:
            try:
                candidate=decode_exact_replica(row.get("checkpoint_replica"),witness)
                self._vault_primary(scope,{**row,"snapshot":candidate})
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError,CrawlerError):
                replica="held"
            else:
                replica="exact"
        return primary,replica,marker["snapshot_digest"]

    async def treasury_vault_redundancy(self,scope,identifier):
        """Verify actual current copies, rather than trusting the availability flag."""
        from core.dragon_crawler import CrawlerError,_now
        if not identity(identifier):
            raise CrawlerError("crawler_identifier_invalid","Invalid retired expedition identifier.")
        query={"_id":identifier,**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Retired expedition not found.",404)
        try:
            primary,replica,digest=await _bounded_discovery_cpu(self._inspect_vault_redundancy,scope,row)
        except CrawlerError as exc:
            if exc.code=="crawler_vault_busy":
                raise
            primary,replica,digest="held","held",None
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError):
            primary,replica,digest="held","held",None
        final=await self.sessions.find_one({**query,"version":row["version"]},
                {"_id":1,"version":1,"checkpoint_identity":1,"treasury_vault":1},max_time_ms=2000)
        if (final is None or final.get("checkpoint_identity")!=row.get("checkpoint_identity")
                or final.get("treasury_vault")!=row.get("treasury_vault")):
            raise CrawlerError("crawler_conflict","Retained record changed during verification.",409)
        state=("redundant" if primary==replica=="exact" else
               "primary_only" if primary=="exact" else
               "repairable_primary" if replica=="exact" else "held")
        return {"ok":True,"schema":"skeleton.dragon.vault-redundancy.v1","session_id":identifier,
                "version":row["version"],"as_of_unix":_now().timestamp(),"state":state,
                "primary":primary,"replica":replica,"snapshot_digest":digest,
                "independent_backup":False,"read_only":True,"source_text_returned":False,
                "historical_grant_extended":False,"network_executed":False}


    def _prepare_vault_replica(self,scope,row):
        from core.dragon_crawler import _plain
        marker=validate_marker(_plain(row["treasury_vault"]))
        witness=validate_identity(_plain(row["checkpoint_identity"]))
        if marker["state"]!="vaulted" or marker["snapshot_digest"]!=witness["snapshot_digest"]:
            raise ValueError("retired witness mismatch")
        snapshot=self._vault_primary(scope,row)
        if not witness["replica_available"]:
            raise CheckpointReplicaError("no originally admitted replica")
        try:
            decode_exact_replica(row.get("checkpoint_replica"),witness)
        except CheckpointReplicaError:
            return reconstruct_exact_replica(snapshot,witness)
        return None

    async def repair_treasury_vault_replica(self,scope,identifier,body,*,principal):
        """Owner-explicit duplicate repair, with no primary or witness rewrite."""
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_plain,_now
        from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_vault_denied","Owner editor authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or body["retention_acknowledged"] is not True):
            raise CrawlerError("crawler_vault_invalid","Explicit custody acknowledgement required.")
        operation=_operation(body["idempotency_key"])
        digest=_digest({"action":"repair_treasury_vault_replica",**body})
        query={"_id":identifier,**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Retired expedition not found.",404)
        held=CrawlerError("crawler_vault_replica_held","Original primary or replica admission cannot be verified.",409)
        prior=row.get("treasury_vault_replica_repair")
        if prior is not None and (not isinstance(prior,dict)
                or set(prior)!={"operation","request_digest","snapshot_digest","published_version","repaired_at"}
                or not all(hash_identity(prior.get(k)) for k in ("operation","request_digest","snapshot_digest"))
                or type(prior.get("published_version")) is not int or not 1<=prior["published_version"]<=row["version"]
                or not isinstance(prior["repaired_at"],str) or not 1<=len(prior["repaired_at"])<=64):
            raise held
        replay=prior is not None and prior["operation"]==operation
        if replay and prior["request_digest"]!=digest:
            raise CrawlerError("crawler_idempotency_conflict","Repair key names a different command.",409)
        if not replay and row["version"]!=body["expected_version"]:
            raise CrawlerError("crawler_conflict","Reload before repairing the retained duplicate.",409)
        try:
            marker=validate_marker(_plain(row["treasury_vault"]))
            witness=validate_identity(_plain(row["checkpoint_identity"]))
            replacement=await _bounded_discovery_cpu(self._prepare_vault_replica,scope,row)
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError) as exc:
            raise held from exc
        except CrawlerError as exc:
            if exc.code=="crawler_vault_busy":
                raise
            raise held from exc
        fence={**query,"version":row["version"],"checkpoint_identity":row["checkpoint_identity"],
               "treasury_vault.operation":marker["operation"],"treasury_vault.snapshot_digest":marker["snapshot_digest"],
               "worker_token":None,"lease_until":None,"last_worker_exit_confirmed":{"$ne":False},
               "consent_expires_at":row["consent_expires_at"],
               "$expr":{"$lte":["$consent_expires_at","$$NOW"]}}
        if replay:
            if replacement is not None or prior["snapshot_digest"]!=marker["snapshot_digest"]:
                raise held
            outcome="repaired"
        elif replacement is None:
            outcome="already_intact"
        else:
            repair={"operation":operation,"request_digest":digest,"snapshot_digest":witness["snapshot_digest"],
                    "published_version":row["version"]+1,"repaired_at":_now().isoformat()}
            payload={"checkpoint_replica":replacement,"treasury_vault_replica_repair":repair}
            receipt=await self._admit(scope,identifier,payload)
            changed=await self.sessions.update_one(fence,{"$set":{**payload,"storage_receipt":receipt,
                "treasury_vault_scrub_due":_now().timestamp()},"$inc":{"version":1}})
            if not changed.modified_count:
                raise CrawlerError("crawler_conflict","Retained record changed before duplicate publication.",409)
            fence={**fence,"version":row["version"]+1}
            outcome="repaired"
        current=await self.sessions.find_one(fence,max_time_ms=2000)
        if current is None:
            raise CrawlerError("crawler_conflict","Retained record changed before duplicate confirmation.",409)
        try:
            if await _bounded_discovery_cpu(self._prepare_vault_replica,scope,current) is not None:
                raise held
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError) as exc:
            raise held from exc
        return {"ok":True,"schema":"skeleton.dragon.vault-replica-repair.v1","session_id":identifier,
                "version":current["version"],"outcome":outcome,"snapshot_digest":marker["snapshot_digest"],
                "primary_rewritten":False,"witness_rewritten":False,"historical_grant_extended":False,
                "network_executed":False,"independent_backup":False}


    @staticmethod
    def _public_vault_scrub(row,now,witness):
        """A past inspection is not live verification or permission."""
        import math
        value=row.get("treasury_vault_scrub")
        if (not isinstance(value,dict) or set(value)!={"schema","version","snapshot_digest","checked_at","state","primary","replica"}
                or value["schema"]!="skeleton.dragon.vault-scrub.v1"
                or value["version"]!=row["version"] or value["snapshot_digest"]!=witness
                or type(value["checked_at"]) not in (float,int) or not math.isfinite(value["checked_at"])
                or not 0<=value["checked_at"]<=now
                or value["primary"] not in ("exact","held") or value["replica"] not in ("exact","held","unavailable")):
            return None
        state=("redundant" if value["primary"]==value["replica"]=="exact" else
               "primary_only" if value["primary"]=="exact" else
               "repairable_primary" if value["replica"]=="exact" else "held")
        if value["state"]!=state:
            return None
        return {"checked_at":value["checked_at"],"state":state,"primary":value["primary"],
                "replica":value["replica"],"live_verified":False}

    async def scrub_treasury_vault(self,*,limit=2):
        """Bounded integrity patrol. Never rewrite retained bytes or authorize use.

        Fair per-owner selection and a 180s server-clock publication lease
        prevent duplicate maintenance from claiming fresh evidence after
        a lost lease. Explicit owners, not the patrol, authorize repairs.
        """
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity
        if type(limit) is not int or not 1<=limit<=2:
            raise ValueError("vault patrol limit exceeded")
        await self.ensure_indexes()
        now=_now().timestamp()
        eligible={"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted",
                  "$or":[{"treasury_vault_scrub_due":{"$exists":False}},
                         {"treasury_vault_scrub_due":{"$lte":now}}]}
        metadata={"_id":1,"tenant_id":1,"owner_id":1,"version":1,"treasury_vault_scrub_due":1}
        rows=await self.sessions.find(eligible,metadata).sort(
            [("treasury_vault_scrub_due",ASCENDING),("_id",ASCENDING)]).limit(8).max_time_ms(2000).to_list(8)
        totals={"scanned":len(rows),"selected":0,"redundant":0,"primary_only":0,
                "repairable_primary":0,"held":0,"superseded":0,"busy":0,"failed":0,
                "auto_primary_repaired":0,"auto_replica_repaired":0}
        owners=set()
        for item in rows:
            scope={k:item[k] for k in ("tenant_id","owner_id")}
            owner=tuple(scope.values())
            if owner in owners or totals["selected"]>=limit:
                continue
            owners.add(owner)
            totals["selected"]+=1
            marked=_now().timestamp()
            claim_until=marked+180
            fence={"_id":item["_id"],**scope,"version":item["version"],
                   "status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted",
                   "treasury_vault_scrub_due":item.get("treasury_vault_scrub_due",{"$exists":False})}
            clock={"$divide":[{"$toLong":"$$NOW"},1000]}
            fence["$expr"]={"$lte":[{"$ifNull":["$treasury_vault_scrub_due",0]},clock]}
            claim=await self.sessions.update_one(fence,{"$set":{"treasury_vault_scrub_due":claim_until}})
            if not claim.modified_count:
                totals["superseded"]+=1
                continue
            clock={"$divide":[{"$toLong":"$$NOW"},1000]}
            fence={**fence,"treasury_vault_scrub_due":claim_until,
                   "$expr":{"$gt":["$treasury_vault_scrub_due",clock]}}
            row=await self.sessions.find_one(fence,max_time_ms=2000)
            if row is None:
                totals["superseded"]+=1
                continue
            try:
                primary,replica,digest=await _bounded_discovery_cpu(self._inspect_vault_redundancy,scope,row)
            except CrawlerError as exc:
                if exc.code=="crawler_vault_busy":
                    totals["busy"]+=1
                    continue
                primary,replica,digest="held","held",None
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError):
                primary,replica,digest="held","held",None
            checked=_now().timestamp()
            if checked>=claim_until:
                totals["superseded"]+=1
                continue
            state=("redundant" if primary==replica=="exact" else
                   "primary_only" if primary=="exact" else
                   "repairable_primary" if replica=="exact" else "held")
            # A malformed witness gets a bounded hold, not a fabricated
            # digest or a persistent qualified inspection.
            witness=row.get("checkpoint_identity")
            fence={**fence,"checkpoint_identity":witness if "checkpoint_identity" in row else {"$exists":False},
                   "treasury_vault":row["treasury_vault"]}
            due=checked+(24*3600 if state=="redundant" else 6*3600)
            if hash_identity(digest) and state in {"repairable_primary","primary_only"}:
                try:
                    automatic=await self._apply_vault_care(scope,row,fence,state,replica,digest,claim_until)
                except CrawlerError as exc:
                    totals["busy" if exc.code=="crawler_vault_busy" else "failed"]+=1
                    continue
                if automatic is not None:
                    totals[automatic]+=1
                    continue
            if not hash_identity(digest):
                changed=await self.sessions.update_one(fence,{"$set":{"treasury_vault_scrub_due":due},
                    "$unset":{"treasury_vault_scrub":""}})
            else:
                audit={"schema":"skeleton.dragon.vault-scrub.v1","version":row["version"],
                       "snapshot_digest":digest,"checked_at":checked,"state":state,"primary":primary,"replica":replica}
                try:
                    # Persist only the admitted tiny observation; no source
                    # copy, authority, grant or previous write receipt changes.
                    await self._admit(scope,row["_id"],{"treasury_vault_scrub":audit})
                except CrawlerError:
                    totals["failed"]+=1
                    continue
                changed=await self.sessions.update_one(fence,{"$set":{"treasury_vault_scrub":audit,
                    "treasury_vault_scrub_due":due}})
            if changed.modified_count:
                totals[state]+=1
            else:
                totals["superseded"]+=1
        return totals


    @staticmethod
    def _public_care(row,now,witness):
        from skeleton.ai.webcrawler.dragon_vault_care import public_care
        if row.get("treasury_vault_care") is None:
            return None
        try:
            return public_care(row["treasury_vault_care"],now=now,version=row["version"],witness=witness)
        except (ValueError,TypeError,KeyError):
            return None

    async def configure_vault_care(self,scope,identifier,body,*,principal):
        """Explicit owner grant. Viewer withdrawal needs no source inspection."""
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_plain,_now
        from skeleton.ai.webcrawler.dragon_vault_care import issue_care,validate_care,public_care
        if authenticated_scope(principal)!=scope or body.get("enabled") is True and principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_vault_denied","Current owner authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","enabled","days","repairs","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or type(body["enabled"]) is not bool or type(body["retention_acknowledged"]) is not bool
                or type(body["days"]) is not int or not 1<=body["days"]<=7
                or type(body["repairs"]) is not int or not 1<=body["repairs"]<=3
                or body["enabled"] and not body["retention_acknowledged"]):
            raise CrawlerError("crawler_vault_care_invalid","Explicit bounded maintenance consent required.")
        operation=_operation(body["idempotency_key"])
        request_digest=_digest({"action":"configure_vault_care",**body})
        query={"_id":identifier,**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Retired expedition not found.",404)
        prior=row.get("treasury_vault_care")
        try:
            marker=validate_marker(_plain(row["treasury_vault"]))
            witness=marker["snapshot_digest"]
        except (ValueError,KeyError,TypeError) as exc:
            raise CrawlerError("crawler_vault_care_held","Retirement witness unavailable.",409) from exc
        previous=None
        try:
            previous=validate_care(_plain(prior)) if prior is not None else None
        except (ValueError,KeyError,TypeError,CrawlerError):
            if body["enabled"]:
                raise CrawlerError("crawler_vault_care_held","Maintenance consent integrity held; withdraw first.",409)
        if previous is not None and previous["operation"]==operation:
            if previous["request_digest"]!=request_digest:
                raise CrawlerError("crawler_idempotency_conflict","Care key names a different command.",409)
            return {"ok":True,"schema":"skeleton.dragon.vault-care-command.v1","session_id":identifier,
                    "version":row["version"],"care":public_care(previous,now=_now().timestamp(),
                    version=row["version"],witness=witness),"network_executed":False}
        if row["version"]!=body["expected_version"]:
            raise CrawlerError("crawler_conflict","Reload before changing maintenance consent.",409)
        if body["enabled"]:
            try:
                primary,replica,digest=await _bounded_discovery_cpu(self._inspect_vault_redundancy,scope,row)
                if digest!=witness or "exact" not in (primary,replica):
                    raise ValueError("no surviving exact copy")
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError) as exc:
                raise CrawlerError("crawler_vault_care_held","At least one exact original copy must qualify.",409) from exc
        now=_now().timestamp()
        grant=issue_care(operation=operation,request_digest=request_digest,snapshot_digest=witness,
                        principal_email=principal["email"].strip().lower(),now=now,
                        days=body["days"],budget=body["repairs"],enabled=body["enabled"])
        fence={**query,"version":row["version"],"treasury_vault":row["treasury_vault"],
               "treasury_vault_care":prior if "treasury_vault_care" in row else {"$exists":False}}
        fields={"treasury_vault_care":grant,"treasury_vault_scrub_due":now}
        from skeleton.ai.webcrawler.dragon_vault_care_history import append_history
        history=row.get("treasury_vault_care_history")
        try:
            fields["treasury_vault_care_history"]=append_history(_plain(history) if history is not None else None,
                witness=witness,version=row["version"]+1,at=now,kind="grant" if body["enabled"] else "withdraw",
                operation=operation,budget=grant["budget"],used=0,prefix_unknown=prior is not None)
            fence["treasury_vault_care_history"]=history if "treasury_vault_care_history" in row else {"$exists":False}
        except (ValueError,TypeError,KeyError,CrawlerError) as exc:
            if body["enabled"]:
                raise CrawlerError("crawler_vault_history_held","Custody history integrity held; no new maintenance authority.",409) from exc
            # Withdrawal always wins over damaged bookkeeping.
        if body["enabled"]:
            fence.update({"checkpoint_identity":row["checkpoint_identity"],"worker_token":None,
                "lease_until":None,"last_worker_exit_confirmed":{"$ne":False},
                "$expr":{"$lte":["$consent_expires_at","$$NOW"]}})
            await self._grant_principal(scope,grant)
            fields["storage_receipt"]=await self._admit(scope,identifier,{"treasury_vault_care":grant,
                "treasury_vault_care_history":fields["treasury_vault_care_history"]})
            await self._grant_principal(scope,grant)
        # Withdrawal must remain available during storage-attester outages.
        # The small disabled receipt replaces the prior bounded grant.
        changed=await self.sessions.update_one(fence,{"$set":fields,"$inc":{"version":1}})
        if not changed.modified_count:
            raise CrawlerError("crawler_conflict","Maintenance consent changed before publication.",409)
        return {"ok":True,"schema":"skeleton.dragon.vault-care-command.v1","session_id":identifier,
                "version":row["version"]+1,"care":public_care(grant,now=now,version=row["version"]+1,
                witness=witness),"network_executed":False}

    async def _apply_vault_care(self,scope,row,fence,state,replica,digest,claim_until):
        """Consume grant and repair in one row CAS; never impersonate owner."""
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_vault_care import consume_care
        grant=row.get("treasury_vault_care")
        public=self._public_care(row,_now().timestamp(),digest)
        if not public or not public["active"]:
            return None
        if state=="repairable_primary":
            side,field,prepare="primary","snapshot",self._prepare_vault_restore
        elif state=="primary_only" and replica=="held":
            side,field,prepare="replica","checkpoint_replica",self._prepare_vault_replica
        else:
            return None
        try:
            await self._grant_principal(scope,grant)
        except CrawlerError as exc:
            if exc.code=="crawler_grant_revoked":
                return None
            raise
        try:
            replacement=await _bounded_discovery_cpu(prepare,scope,row)
            if replacement is None:
                return None
            now=_now().timestamp()
            if now>=claim_until:
                return "superseded"
            consumed=consume_care(grant,now=now,version=row["version"],witness=digest,side=side)
        except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError):
            return None
        from core.dragon_crawler import _plain
        from skeleton.ai.webcrawler.dragon_vault_care_history import append_history
        history=row.get("treasury_vault_care_history")
        try:
            appended=append_history(_plain(history) if history is not None else None,
                witness=digest,version=row["version"]+1,at=now,kind="auto_"+side,operation=grant["operation"],
                budget=consumed["budget"],used=consumed["used"],prefix_unknown=True)
        except (ValueError,TypeError,KeyError,CrawlerError):
            return None
        payload={field:replacement,"treasury_vault_care":consumed,"treasury_vault_care_history":appended}
        receipt=await self._admit(scope,row["_id"],payload)
        try:
            await self._grant_principal(scope,grant)
        except CrawlerError as exc:
            if exc.code=="crawler_grant_revoked":
                return None
            raise
        clock={"$divide":[{"$toLong":"$$NOW"},1000]}
        fenced={**fence,"treasury_vault_care":grant,
                "treasury_vault_care_history":history if "treasury_vault_care_history" in row else {"$exists":False},
                "worker_token":None,"lease_until":None,
                "last_worker_exit_confirmed":{"$ne":False},
                "$expr":{"$and":[{"$gt":["$treasury_vault_scrub_due",clock]},
                    {"$gt":["$treasury_vault_care.expires_at",clock]},
                    {"$lte":["$treasury_vault_care.issued_at",clock]},
                    {"$lte":["$consent_expires_at","$$NOW"]}]}}
        update={"$set":{**payload,"storage_receipt":receipt,"treasury_vault_scrub_due":now+300},
                "$unset":{"treasury_vault_scrub":""},"$inc":{"version":1}}
        if side=="primary":
            update["$unset"]["treasury_index"]=""
            update["$unset"]["treasury_archive_route"]=""
            update["$set"]["treasury_repair_due"]=now
        changed=await self.sessions.update_one(fenced,update)
        return "auto_"+side+"_repaired" if changed.modified_count else "superseded"


    async def treasury_vault_health(self,scope):
        """Exact owner-bounded metadata census, not a live byte verification.

        Retirements can temporarily occupy both quotas. At most 1,056 distinct
        records are possible across the 1,024 cold and 32 active reservations.
        Invalid records remain visible as holds rather than disappearing.
        """
        from core.dragon_crawler import CrawlerError,_now,_plain
        from skeleton.ai.webcrawler.dragon_treasury_vault import finite,hash_identity
        from skeleton.ai.webcrawler.dragon_vault_quota import MAX_RESERVED
        await self.ensure_indexes()
        query={**scope,"status":{"$in":sorted(TERMINAL)},
               "treasury_vault.state":{"$in":["pending","vaulted"]},"deep_archive.released":{"$ne":True}}
        fields={"_id":1,"version":1,"treasury_vault":1,"checkpoint_identity.snapshot_digest":1,
                "treasury_vault_scrub":1,"treasury_vault_care":1,"treasury_vault_scrub_due":1,
                "treasury_vault_care_history":1}
        async def census():
            return await self.sessions.find(query,fields).sort("_id",ASCENDING).limit(
                MAX_RESERVED+1).max_time_ms(2000).to_list(MAX_RESERVED+1)
        rows=await census()
        if len(rows)>MAX_RESERVED or len({row["_id"] for row in rows})!=len(rows):
            raise CrawlerError("crawler_vault_health_held","Retained catalogue exceeds the custody census bound.",503)
        now=_now().timestamp()
        counts={"pending":0,"vaulted":0,"marker_held":0,"uninspected":0,"stale":0,"redundant":0,
                "primary_only":0,"repairable_primary":0,"held":0,"care_active":0,"care_inactive":0,
                "care_absent":0,"care_held":0,"remaining_repairs":0,"due":0}
        transitions=[]
        for row in rows:
            try:
                marker=validate_marker(_plain(row["treasury_vault"]))
                witness=row["checkpoint_identity"]["snapshot_digest"]
                if not hash_identity(witness) or witness!=marker["snapshot_digest"] or type(row["version"]) is not int:
                    raise ValueError("marker identity mismatch")
            except (ValueError,TypeError,KeyError,RecursionError,CrawlerError):
                counts["marker_held"]+=1
                continue
            if marker["state"]=="pending":
                counts["pending"]+=1
                continue
            counts["vaulted"]+=1
            audit=self._public_vault_scrub(row,now,witness)
            if audit is None:
                counts["uninspected"]+=1
            else:
                # Use the observation's own service horizon, not its mutable
                # scheduler marker. A retry lease must never make old data fresh.
                expiry=audit["checked_at"]+(24*3600 if audit["state"]=="redundant" else 6*3600)
                if expiry<=now:
                    counts["stale"]+=1
                else:
                    counts[audit["state"]]+=1
                    transitions.append(expiry)
            due=row.get("treasury_vault_scrub_due",0)
            if not finite(due) or due<=now:
                counts["due"]+=1
            else:
                transitions.append(due)
            grant=row.get("treasury_vault_care")
            care=self._public_care(row,now,witness)
            if row.get("treasury_vault_care_history") is not None:
                from skeleton.ai.webcrawler.dragon_vault_care_history import validate_history
                try:
                    validate_history(_plain(row["treasury_vault_care_history"]),witness=witness,version=row["version"])
                except (ValueError,TypeError,KeyError,CrawlerError):
                    care=None
            if grant is None:
                counts["care_absent"]+=1
            elif care is None:
                counts["care_held"]+=1
            elif care["active"]:
                counts["care_active"]+=1
                counts["remaining_repairs"]+=care["remaining"]
                transitions.append(care["expires_at"])
            else:
                counts["care_inactive"]+=1
                if care["enabled"] and care["remaining"] and care["issued_at"]>now:
                    transitions.append(care["issued_at"])
        if rows!=await census() or transitions and min(transitions)<=_now().timestamp():
            raise CrawlerError("crawler_vault_changed","Custody census changed during inspection; refresh.",409)
        return {"ok":True,"schema":"skeleton.dragon.vault-health.v1","as_of_unix":now,
                "valid_until":min([now+60,*transitions]),"records":len(rows),**counts,
                "live_verified":False,"source_text_returned":False,"independent_backup":False}


    async def treasury_vault_care_history(self,scope,identifier):
        from core.dragon_crawler import CrawlerError,_plain,_now
        from skeleton.ai.webcrawler.dragon_vault_care_history import public_history
        if not identity(identifier):
            raise CrawlerError("crawler_identifier_invalid","Invalid retired expedition identifier.")
        query={"_id":identifier,**scope,"status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted"}
        projection={"_id":1,"version":1,"treasury_vault":1,"treasury_vault_care_history":1}
        row=await self.sessions.find_one(query,projection,max_time_ms=2000)
        if row is None:
            raise CrawlerError("crawler_not_found","Retired expedition not found.",404)
        try:
            marker=validate_marker(_plain(row["treasury_vault"]))
            history=public_history(_plain(row.get("treasury_vault_care_history")),
                witness=marker["snapshot_digest"],version=row["version"])
        except (ValueError,TypeError,KeyError,CrawlerError):
            history={"state":"held","prefix_unknown":True,"omitted":0,"events":[]}
        final=await self.sessions.find_one({**query,"version":row["version"]},projection,max_time_ms=2000)
        if final!=row:
            raise CrawlerError("crawler_conflict","Custody history changed; refresh.",409)
        return {"ok":True,"schema":"skeleton.dragon.vault-care-history.v1","session_id":identifier,
                "version":row["version"],"as_of_unix":_now().timestamp(),**history,
                "read_only":True,"independent_audit":False,"source_text_returned":False,"network_executed":False}


    def _verify_indexed_archive_candidate(self,scope,row,query,now):
        from core.dragon_crawler import _plain
        from skeleton.ai.webcrawler.dragon_archive_routing import validate_routing,pointer
        from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
        from skeleton.ai.webcrawler.dragon_vault_discovery import query_terms
        from skeleton.ai.webcrawler.dragon_companion import _lexemes
        from skeleton.ai.webcrawler.operations import implementation_digest
        snapshot=self._vault_primary(scope,row)
        grant=_plain(row["archive_grant"])
        if not validate_routing(_plain(row["treasury_archive_route"]),scope,
                                _plain(row["treasury_index"]),grant,now=now):
            return []
        if grant["snapshot_digest"]!=snapshot["snapshot_digest"]:
            return []
        policies=self._source_policies(row)
        ids=set(snapshot["sources"])
        if snapshot["binding"]["code_digest"]!=implementation_digest():
            proof=self._legacy_inspection(scope,row,snapshot)
            if row.get("legacy_archive_receipt")!=proof:
                return []
            ids=set(proof["verified_source_ids"])
        terms=set(query_terms(query))
        matches=[]
        for sid in sorted(ids):
            source=snapshot["sources"][sid]
            expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
                policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
            if expiry is None:continue
            hits=len(terms.intersection(_lexemes(source["text"])))
            if hits:
                matches.append(pointer(row["_id"],sid,row["version"],hits,expiry=expiry))
        return matches

    async def search_indexed_archive(self,scope,*,query):
        """Indexed historical pointer lookup; never a model context grant."""
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_archive_routing import query_keys,candidate_pipeline,MAX_CANDIDATES,MAX_RECHECK,MAX_RESULTS
        try:
            keys=query_keys(scope,query)
        except (ValueError,UnicodeError) as exc:
            raise CrawlerError("crawler_archive_query","Enter a bounded lexical archive query.") from exc
        await self.ensure_indexes()
        stamp=_now().timestamp()
        pipeline=candidate_pipeline(scope,keys,stamp)
        rows=await self.sessions.aggregate(pipeline,maxTimeMS=2500).to_list(MAX_CANDIDATES+1)
        matches=[]
        held=0
        qualified_rows=[]
        for candidate in rows[:MAX_RECHECK]:
            row=await self.sessions.find_one({**scope,"_id":candidate["_id"],"version":candidate["version"],
                "status":{"$in":sorted(TERMINAL)},"treasury_vault.state":"vaulted",
                "treasury_archive_route.digest":candidate["digest"]},max_time_ms=2000)
            if row is None:
                raise CrawlerError("crawler_vault_changed","Indexed archive changed; refresh.",409)
            try:
                hits=await _bounded_discovery_cpu(self._verify_indexed_archive_candidate,scope,row,query,stamp)
            except CrawlerError as exc:
                if exc.code=="crawler_vault_busy":raise
                hits=None
            except (ValueError,TypeError,KeyError,RecursionError,CheckpointReplicaError):
                hits=None
            if hits is None:
                held+=1
                continue
            matches.extend(hits)
            qualified_rows.append(candidate)
        # Recheck exact candidate versions and authority, not cached text.
        final=await self.sessions.aggregate(pipeline,maxTimeMS=2500).to_list(MAX_CANDIDATES+1)
        now=_now().timestamp()
        if rows!=final or any(hit["valid_until"]<=now for hit in matches):
            raise CrawlerError("crawler_vault_changed","Indexed archive changed during retrieval.",409)
        matches.sort(key=lambda hit:(-hit["score"],hit["session_id"],hit["source_id"]))
        # Citation handles are transient, not promoted into knowledge.
        return {"ok":True,"schema":"skeleton.dragon.archive-index-search.v1","as_of_unix":stamp,
                "candidate_chambers":min(len(rows),MAX_CANDIDATES),"candidate_limit_reached":len(rows)>MAX_RECHECK,
                "rechecked_chambers":min(len(rows),MAX_RECHECK),"held_chambers":held,
                "results":matches[:MAX_RESULTS],"result_limit_reached":len(matches)>MAX_RESULTS,
                "ranking":"indexed_term_overlap_then_exact_coverage","complete_corpus":False,
                "stored_prose":0,"model_context_authorized":False,"network_executed":False}
