"""Deep archive: partitioned reservations, live-grant routing and exact reparse."""
from __future__ import annotations

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError,PyMongoError
from core.dragon_vault import _bounded_discovery_cpu
from core.dragon_checkpoint_replica import CheckpointReplicaError
from skeleton.ai.webcrawler.dragon_treasury_vault import TERMINAL,identity
from skeleton.ai.webcrawler import dragon_archive_scale as a


class DragonDeepArchiveMixin:
    def _deep_query(self,scope,identifier):
        return {**scope,"_id":identifier,"status":{"$in":sorted(TERMINAL)},
                "treasury_vault.state":"vaulted","treasury_vault.active_slot_released":True}

    async def archive_to_deep(self,scope,identifier,body,*,principal):
        from core.dragon_crawler import CrawlerError,authenticated_scope,_operation,_digest,_now,_plain
        if authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}:
            raise CrawlerError("crawler_deep_denied","Owner editor authority required.",403)
        if (not identity(identifier) or set(body)!={"expected_version","idempotency_key","retention_acknowledged"}
                or type(body["expected_version"]) is not int or body["expected_version"]<1
                or body["retention_acknowledged"] is not True):
            raise CrawlerError("crawler_deep_invalid","Explicit custody acknowledgement required.")
        op=_operation(body["idempotency_key"])
        command=_digest({"action":"deep_archive",**body})
        query=self._deep_query(scope,identifier)
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if not row:
            raise CrawlerError("crawler_deep_held","Retire this expedition before deep archival.",409)
        prior=row.get("deep_archive")
        try:
            if prior is not None:
                mark=a.validate_marker(_plain(prior),scope,identifier)
                if mark["operation"]==op and mark["request_digest"]!=command:
                    raise CrawlerError("crawler_idempotency_conflict","Archive key names another command.",409)
                if mark["operation"]!=op and row["version"]!=body["expected_version"]:
                    raise CrawlerError("crawler_conflict","Reload deep custody state.",409)
            else:
                if row["version"]!=body["expected_version"]:
                    raise CrawlerError("crawler_conflict","Reload expedition.",409)
                snapshot=await _bounded_discovery_cpu(self._vault_primary,scope,row)
                if row["treasury_vault"]["snapshot_digest"]!=snapshot["snapshot_digest"]:
                    raise ValueError("witness mismatch")
                mark=a.marker(scope,identifier,op,command,snapshot["snapshot_digest"],_now().timestamp())
                receipt=await self._admit(scope,identifier,{"deep_archive":mark})
                changed=await self.sessions.update_one({**query,"version":row["version"],
                    "deep_archive":{"$exists":False},"worker_token":None,"lease_until":None,
                    "$expr":{"$lte":["$consent_expires_at","$$NOW"]}},
                    {"$set":{"deep_archive":mark,"storage_receipt":receipt},"$inc":{"version":1}})
                if not changed.modified_count:
                    raise CrawlerError("crawler_conflict","Archive intent changed.",409)
        except (ValueError,TypeError,KeyError,CheckpointReplicaError) as exc:
            raise CrawlerError("crawler_deep_held","Original custody did not qualify.",409) from exc
        outcome=await self._finish_deep_archive(scope,identifier)
        final=await self.sessions.find_one(query,{"version":1,"deep_archive":1},max_time_ms=2000)
        if not final:
            raise CrawlerError("crawler_not_found","Retained record unavailable.",404)
        return {"ok":True,"schema":"skeleton.dragon.deep-command.v1","session_id":identifier,
                "version":final["version"],"archive":a.public_marker(a.validate_marker(final["deep_archive"],scope,identifier)),
                "outcome":outcome,"network_executed":False,"source_permission_extended":False}

    async def _release_deep_slot(self,scope,identifier):
        shard,key=a.partition(scope,identifier)
        await self.limits.update_one({"_id":key,**scope,"kind":"dragon_deep_archive","partition":shard},
                                    {"$pull":{"deep_ids":identifier}})

    async def _finish_deep_archive(self,scope,identifier):
        from core.dragon_crawler import _digest,_now,_plain
        query=self._deep_query(scope,identifier)
        row=await self.sessions.find_one(query,max_time_ms=2000)
        if not row:
            return "superseded"
        mark=a.validate_marker(_plain(row["deep_archive"]),scope,identifier)
        if mark["released"]:
            return "archived"
        if row.get("checkpoint_identity",{}).get("snapshot_digest")!=mark["snapshot_digest"]:
            return "held"
        fence={**query,"version":row["version"],"deep_archive.operation":mark["operation"],
               "deep_archive.state":mark["state"],"deep_archive.released":False}
        quota={"_id":mark["quota_id"],**scope,"kind":"dragon_deep_archive","partition":mark["partition"]}
        if mark["state"]=="pending":
            snapshot=await _bounded_discovery_cpu(self._vault_primary,scope,row)
            if snapshot["snapshot_digest"]!=mark["snapshot_digest"]:
                return "held"
            try:
                await self.limits.update_one(quota,{"$setOnInsert":{"deep_ids":[]}},upsert=True)
            except DuplicateKeyError:
                pass
            reserved=await self.limits.update_one({**quota,"$or":[{"deep_ids":identifier},
                {f"deep_ids.{a.SLOTS-1}":{"$exists":False}}]},{"$addToSet":{"deep_ids":identifier}})
            if not reserved.matched_count:
                await self.sessions.update_one(fence,{"$set":{"deep_archive.retry_at":_now().timestamp()+3600}})
                return "capacity_held"
            published=await self.sessions.update_one(fence,{"$set":{"deep_archive.state":"archived",
                "deep_archive.retry_at":_now().timestamp(),"deep_index_due":_now().timestamp()},"$inc":{"version":1}})
            if not published.modified_count:
                from skeleton.ai.webcrawler.dragon_vault_quota import tombstone
                deleted=await self.sessions.find_one({**scope,"_id":identifier,"status":"deleted"},max_time_ms=2000)
                if tombstone(deleted):
                    await self._release_deep_slot(scope,identifier)
                return "superseded"
            fence={**fence,"version":row["version"]+1,"deep_archive.state":"archived"}
        if await self.limits.find_one({**quota,"deep_ids":identifier},{"_id":1},max_time_ms=2000) is None:
            return "held"
        released=await self.limits.update_one({"_id":_digest(scope),**scope},{"$pull":{"vault_ids":identifier}})
        if not released.matched_count:
            return "held"
        result=await self.sessions.update_one(fence,{"$set":{"deep_archive.released":True}})
        return "archived" if result.modified_count else "superseded"

    async def recover_deep_archive(self,*,limit=2):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=4:
            raise ValueError("recovery bound")
        await self.ensure_indexes()
        rows=await self.sessions.find({"status":{"$in":sorted(TERMINAL)},
            "deep_archive.state":{"$in":["pending","archived"]},"deep_archive.released":False,
            "deep_archive.retry_at":{"$lte":_now().timestamp()}},
            {"_id":1,"tenant_id":1,"owner_id":1}).sort([("deep_archive.retry_at",ASCENDING),("_id",ASCENDING)]
            ).limit(8).max_time_ms(2000).to_list(8)
        totals={"scanned":len(rows),"archived":0,"held":0,"capacity_held":0,"superseded":0,"failed":0}
        owners=set()
        for row in rows:
            scope={k:row[k] for k in ("tenant_id","owner_id")}
            owner=tuple(scope.values())
            if owner in owners or len(owners)>=limit:
                continue
            owners.add(owner)
            try:
                outcome=await self._finish_deep_archive(scope,row["_id"])
            except (ValueError,KeyError,TypeError,CrawlerError,PyMongoError):
                outcome="failed"
            totals[outcome]+=1
            if outcome in ("held","failed"):
                await self.sessions.update_one({"_id":row["_id"],**scope,
                    "deep_archive.released":False,"deep_archive.retry_at":{"$lte":_now().timestamp()}},
                    {"$set":{"deep_archive.retry_at":_now().timestamp()+3600}})
        return totals

    async def deep_archive_catalog(self,scope,*,cursor=None,limit=32):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=64 or cursor is not None and not identity(cursor):
            raise CrawlerError("crawler_deep_bounds","Invalid archive page.")
        await self.ensure_indexes()
        query={**scope,"status":{"$in":sorted(TERMINAL)},"deep_archive.state":{"$in":["pending","archived"]}}
        if cursor is not None:
            query["_id"]={"$gt":cursor}
        fields={"_id":1,"version":1,"deep_archive":1,"checkpoint_identity.snapshot_digest":1,
                "archive_grant.expires_at":1,"deep_index.expires_at":1,"snapshot.binding.code_digest":1}
        async def page():
            return await self.sessions.find(query,fields).sort("_id",ASCENDING).limit(limit+1).max_time_ms(2000).to_list(limit+1)
        rows=await page()
        results=[]
        now=_now().timestamp()
        from skeleton.ai.webcrawler.operations import implementation_digest
        runtime=implementation_digest()
        for row in rows[:limit]:
            try:
                mark=a.validate_marker(row["deep_archive"],scope,row["_id"])
                if row["checkpoint_identity"]["snapshot_digest"]!=mark["snapshot_digest"]:
                    raise ValueError("witness mismatch")
                expiry=(row.get("archive_grant") or {}).get("expires_at")
                idx=(row.get("deep_index") or {}).get("expires_at")
                results.append({"session_id":row["_id"],"version":row["version"],"archive":a.public_marker(mark),
                    "grant_recorded":a.finite(expiry) and expiry>now,"index_recorded":a.finite(idx) and idx>now,
                    "legacy_runtime":(row.get("snapshot") or {}).get("binding",{}).get("code_digest")!=runtime,
                    "integrity_held":False})
            except (ValueError,TypeError,KeyError,AttributeError):
                results.append({"session_id":row["_id"],"version":row["version"],"archive":None,
                    "grant_recorded":False,"index_recorded":False,"legacy_runtime":None,"integrity_held":True})
        if rows!=await page():
            raise CrawlerError("crawler_deep_changed","Archive catalogue changed.",409)
        return {"ok":True,"schema":"skeleton.dragon.deep-catalog.v1","records":results,
            "next_cursor":rows[limit-1]["_id"] if len(rows)>limit else None,
            "partitions":a.SHARDS,"partition_capacity":a.SLOTS,"reservation_ceiling":a.MAX_EXPEDITIONS,
            "storage_capacity_verified":False}

    def _deep_material(self,scope,row,now):
        from skeleton.ai.webcrawler.dragon_archive_grant import validate_grant
        from skeleton.ai.webcrawler.operations import implementation_digest
        mark=a.validate_marker(row["deep_archive"],scope,row["_id"])
        if mark["state"]!="archived" or not mark["released"]:
            raise ValueError("deep custody not final")
        snapshot=self._vault_primary(scope,row)
        grant=row["archive_grant"]
        validate_grant(grant)
        if snapshot["snapshot_digest"]!=mark["snapshot_digest"] or not grant["issued_at"]<=now<grant["expires_at"]:
            raise ValueError("historical grant unavailable")
        allowed=set(snapshot["sources"])
        if snapshot["binding"]["code_digest"]!=implementation_digest():
            proof=self._legacy_inspection(scope,row,snapshot)
            if proof!=row.get("legacy_archive_receipt"):
                raise ValueError("legacy archive use not qualified")
            allowed=set(proof["verified_source_ids"])
        return snapshot,grant,self._source_policies(row),allowed

    async def build_deep_indexes(self,*,limit=2):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=4:
            raise ValueError("deep indexing bound")
        await self.ensure_indexes()
        now=_now().timestamp()
        query={"status":{"$in":sorted(TERMINAL)},"deep_archive.state":"archived","deep_archive.released":True,
               "archive_grant.expires_at":{"$gt":now},"$or":[{"deep_index_due":{"$exists":False}},
                  {"deep_index_due":{"$lte":now}}]}
        rows=await self.sessions.find(query,{"_id":1,"version":1,"tenant_id":1,"owner_id":1,"deep_index_due":1}
            ).sort([("deep_index_due",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        totals={"scanned":len(rows),"indexed":0,"held":0,"superseded":0}
        for item in rows:
            scope={k:item[k] for k in ("tenant_id","owner_id")}
            from core.dragon_crawler import _now
            claimed=_now().timestamp()+180
            clock={"$divide":[{"$toLong":"$$NOW"},1000]}
            fence={**scope,"_id":item["_id"],"version":item["version"],"status":{"$in":sorted(TERMINAL)},
                "deep_archive.released":True,"deep_index_due":item.get("deep_index_due",{"$exists":False}),
                "$expr":{"$lte":[{"$ifNull":["$deep_index_due",0]},clock]}}
            reserved=await self.sessions.update_one(fence,{"$set":{"deep_index_due":claimed}})
            if not reserved.modified_count:
                totals["superseded"]+=1
                continue
            fence={**fence,"deep_index_due":claimed,"$expr":{"$gt":["$deep_index_due",clock]}}
            row=await self.sessions.find_one(fence,max_time_ms=2000)
            if not row:
                totals["superseded"]+=1
                continue
            try:
                def build():
                    snap,grant,policies,allowed=self._deep_material(scope,row,now)
                    return a.build_index(scope,snap,grant,policies,now,allowed)
                index=await _bounded_discovery_cpu(build)
                await self._admit(scope,row["_id"],{"deep_index":index})
            except (ValueError,TypeError,KeyError,CrawlerError,CheckpointReplicaError):
                await self.sessions.update_one(fence,{"$unset":{"deep_index":""},
                      "$set":{"deep_index_due":_now().timestamp()+3600}})
                totals["held"]+=1
                continue
            fence={**fence,"archive_grant":row["archive_grant"],"$expr":{"$and":[
                  {"$gt":["$deep_index_due",clock]},{"$gt":["$archive_grant.expires_at",clock]}]}}
            changed=await self.sessions.update_one(fence,{"$set":{"deep_index":index,
                "deep_index_due":min(index["expires_at"],_now().timestamp()+86400)}})
            totals["indexed" if changed.modified_count else "superseded"]+=1
        return totals

    async def deep_archive_search(self,scope,*,query,cursor=None,partition_id=None,order="relevance",match="any"):
        """Indexed candidate pages, exact reparse of each admitted row."""
        from core.dragon_crawler import CrawlerError,_now
        try:
            terms,tokens=a.query_terms(scope,query)
            options=a.search_options(partition_id=partition_id,order=order,match=match)
            boundary=a.search_boundary(scope,query,options,cursor)
        except ValueError as exc:
            raise CrawlerError("crawler_deep_query","Invalid archive search or cursor.",422) from exc
        await self.ensure_indexes()
        now=_now().timestamp()
        predicate,sort=a.search_predicate(scope,tokens,now,options,boundary)
        async def page():
            return await self.sessions.find(predicate,{"_id":1,"version":1,"deep_index.digest":1,
                "deep_archive.accepted_at":1,"deep_archive.partition":1}
                ).sort(sort).limit(a.PAGE+1).max_time_ms(3000).to_list(a.PAGE+1)
        rows=await page()
        hits=[]
        held=0
        expiries=[]
        for item in rows[:a.PAGE]:
            row=await self.sessions.find_one({**scope,"_id":item["_id"],"version":item["version"],
                "deep_index.digest":item["deep_index"]["digest"],"status":{"$in":sorted(TERMINAL)}},max_time_ms=2000)
            if not row:
                raise CrawlerError("crawler_deep_changed","Archive index changed.",409)
            try:
                def rank():
                    snap,grant,policies,allowed=self._deep_material(scope,row,now)
                    a.validate_index(row["deep_index"],snap,grant,policies,now)
                    return a.rank_exact(scope,snap,grant,policies,now,terms,allowed,
                        require_all=match=="all")
                matches=await _bounded_discovery_cpu(rank)
            except CrawlerError as exc:
                if exc.code=="crawler_vault_busy":
                    raise
                held+=1
                continue
            except (ValueError,KeyError,TypeError,CheckpointReplicaError):
                held+=1
                continue
            for h in matches:
                expiries.append(h["valid_until"])
                hits.append({**h,"session_id":row["_id"],"version":row["version"],
                             "snapshot_digest":row["deep_archive"]["snapshot_digest"],
                             "archived_at":row["deep_archive"]["accepted_at"],
                             "partition":row["deep_archive"]["partition"]})
        if rows!=await page() or expiries and min(expiries)<=_now().timestamp():
            raise CrawlerError("crawler_deep_changed","Archive authority changed during search.",409)
        # Bounded candidate rank, not global BM25. Preserve duplicate evidence
        # separately from source count; never present duplicates as corroboration.
        if order=="relevance":
            hits.sort(key=lambda h:(-h["matched_terms"],-h["term_frequency"],-h["captured_at"],h["session_id"],h["source_id"]))
        else:
            direction=-1 if order=="archive_newest" else 1
            hits.sort(key=lambda h:(direction*h["archived_at"],h["session_id"],-h["matched_terms"],h["source_id"]))
        unique={}
        for h in hits:
            unique.setdefault(h["preserved_text_hash"],h)
        return {"ok":True,"schema":"skeleton.dragon.deep-search.v1","scanned":min(len(rows),a.PAGE),
            "held":held,"matches":list(unique.values())[:32],"matching_payloads":len(unique),
            "next_cursor":a.search_cursor(scope,query,options,identifier=rows[a.PAGE-1]["_id"],
                accepted_at=rows[a.PAGE-1]["deep_archive"]["accepted_at"]) if len(rows)>a.PAGE else None,
            "search_options":options,
            "as_of_unix":now,"earliest_expiry":min(expiries) if expiries else None,
            "approximate_routing":True,"page_local_ranking":True,"history_only":True,
            "source_text_returned":False,"model_context_permission":False,"wiki_approval":False}


    async def purge_expired_deep_indexes(self,*,limit=16):
        from core.dragon_crawler import _now
        if type(limit) is not int or not 1<=limit<=32:
            raise ValueError("deep index expiry limit")
        await self.ensure_indexes()
        now=_now().timestamp()
        rows=await self.sessions.find({"deep_index.expires_at":{"$lte":now},"status":{"$ne":"deleted"}},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"deep_index.expires_at":1}
        ).sort([("deep_index.expires_at",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        purged=0
        for row in rows:
            expiry=row.get("deep_index",{}).get("expires_at")
            if not a.finite(expiry) or expiry>now:continue
            clock={"$divide":[{"$toLong":"$$NOW"},1000]}
            changed=await self.sessions.update_one({"_id":row["_id"],"tenant_id":row["tenant_id"],
                "owner_id":row["owner_id"],"version":row["version"],"status":{"$ne":"deleted"},
                "deep_index.expires_at":expiry,"$expr":{"$lte":["$deep_index.expires_at",clock]}},
                {"$unset":{"deep_index":""},"$inc":{"version":1}})
            purged+=int(bool(changed.modified_count))
        return {"scanned":len(rows),"purged":purged,"source_records_erased":0}

    async def query_hoag_wiki(self,scope,*,query,mode="historic",cursor=None,partition_id=None,order="relevance",match="any"):
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.distributed.galaxy.librarians import WikiLibrarian
        if mode=="historic":
            if partition_id is None and order=="relevance" and match=="any":
                result=await self.deep_archive_search(scope,query=query,cursor=cursor)
            else:
                result=await self.deep_archive_search(scope,query=query,cursor=cursor,
                    partition_id=partition_id,order=order,match=match)
        elif mode=="current" and cursor is None and partition_id is None and order=="relevance" and match=="any":
            result=await self.context(scope,query,8,32000)
        else:
            raise CrawlerError("crawler_wiki_query","Invalid Wiki source plane or cursor.",422)
        try:
            catalog=WikiLibrarian.crawler_catalog(result,mode=mode,now=_now().timestamp())
        except (ValueError,TypeError,KeyError) as exc:
            raise CrawlerError("crawler_wiki_changed","Crawler citation authority changed.",409) from exc
        return {"ok":True,**catalog}
