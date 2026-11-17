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

    async def purge_expired_deep_indexes(self,*,limit=8):
        """Drop only derived routing fields, never preserved source bytes."""
        from core.dragon_crawler import _now
        if type(limit) is not int or not 1<=limit<=32:
            raise ValueError("purge bound")
        await self.ensure_indexes()
        now=_now().timestamp()
        rows=await self.sessions.find({"deep_index.expires_at":{"$lte":now}},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"deep_index.digest":1,"deep_index.expires_at":1}
            ).sort("deep_index.expires_at",ASCENDING).limit(limit).max_time_ms(2000).to_list(limit)
        purged=0
        for row in rows:
            index=row["deep_index"]
            result=await self.sessions.update_one({"_id":row["_id"],"tenant_id":row["tenant_id"],"owner_id":row["owner_id"],
                "version":row["version"],"deep_index.digest":index["digest"],"deep_index.expires_at":index["expires_at"],
                "$expr":{"$lte":["$deep_index.expires_at",{"$divide":[{"$toLong":"$$NOW"},1000]}]}},
                {"$unset":{"deep_index":"","deep_hybrid_route":"","deep_passage_route":"","deep_dense_route":"","deep_dense_due":"","deep_full_state":"","deep_full_due":"","deep_index_due":""}})
            purged+=result.modified_count
        return {"scanned":len(rows),"purged":purged}

    async def recover_deep_erasure(self,*,limit=8):
        """Finish partition cleanup after a crash following durable deletion."""
        from skeleton.ai.webcrawler.dragon_vault_quota import tombstone
        if type(limit) is not int or not 1<=limit<=32:
            raise ValueError("cleanup bound")
        await self.ensure_indexes()
        rows=await self.sessions.find({"status":"deleted","deep_slot_cleanup":True},
            {"_id":1,"tenant_id":1,"owner_id":1,"version":1,"status":1,"deletion":1,"deep_slot_cleanup":1}
            ).sort("_id",ASCENDING).limit(limit).max_time_ms(2000).to_list(limit)
        cleaned=held=0
        for row in rows:
            if not tombstone(row):
                held+=1
                continue
            scope={k:row[k] for k in ("tenant_id","owner_id")}
            await self._release_deep_slot(scope,row["_id"])
            result=await self.sessions.update_one({**scope,"_id":row["_id"],"version":row["version"],
                "status":"deleted","deletion":row["deletion"],"deep_slot_cleanup":True},
                {"$unset":{"deep_slot_cleanup":""}})
            cleaned+=result.modified_count
        return {"scanned":len(rows),"cleaned":cleaned,"held":held}

    async def deep_archive_catalog(self,scope,*,cursor=None,limit=32):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=64 or cursor is not None and not identity(cursor):
            raise CrawlerError("crawler_deep_bounds","Invalid archive page.")
        await self.ensure_indexes()
        query={**scope,"status":{"$in":sorted(TERMINAL)},"deep_archive.state":{"$in":["pending","archived"]}}
        if cursor is not None:
            query["_id"]={"$gt":cursor}
        fields={"_id":1,"version":1,"deep_archive":1,"checkpoint_identity.snapshot_digest":1,
                "archive_grant.expires_at":1,"deep_index.expires_at":1}
        async def page():
            return await self.sessions.find(query,fields).sort("_id",ASCENDING).limit(limit+1).max_time_ms(2000).to_list(limit+1)
        rows=await page()
        results=[]
        now=_now().timestamp()
        for row in rows[:limit]:
            try:
                mark=a.validate_marker(row["deep_archive"],scope,row["_id"])
                if row["checkpoint_identity"]["snapshot_digest"]!=mark["snapshot_digest"]:
                    raise ValueError("witness mismatch")
                expiry=(row.get("archive_grant") or {}).get("expires_at")
                idx=(row.get("deep_index") or {}).get("expires_at")
                results.append({"session_id":row["_id"],"version":row["version"],"archive":a.public_marker(mark),
                    "grant_recorded":a.finite(expiry) and expiry>now,"index_recorded":a.finite(idx) and idx>now,
                    "integrity_held":False})
            except (ValueError,TypeError,KeyError,AttributeError):
                results.append({"session_id":row["_id"],"version":row["version"],"archive":None,
                    "grant_recorded":False,"index_recorded":False,"integrity_held":True})
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

    async def archive_intelligence(self,scope,*,session_id,compare_session=None):
        """Read-only revision/compaction analysis of currently granted history."""
        from core.dragon_crawler import CrawlerError,_now
        from core.dragon_archive_intelligence import eligible_material,archive_report,compare_text
        if not identity(session_id) or (compare_session is not None and
                (not identity(compare_session) or compare_session==session_id)):
            raise CrawlerError("crawler_archive_analysis_input","Invalid archive comparison.",422)
        await self.ensure_indexes()
        now=_now().timestamp()
        ids=[session_id]+([compare_session] if compare_session is not None else [])
        rows=[]
        for identifier in ids:
            predicate={**scope,"_id":identifier,"deep_archive.released":True,
                       "status":{"$in":sorted(TERMINAL)}}
            row=await self.sessions.find_one(predicate,max_time_ms=2000)
            if row is None:
                raise CrawlerError("crawler_archive_analysis_held","Archive unavailable.",403)
            rows.append((predicate,row))
        def analyze():
            material=[];reports=[]
            for _,row in rows:
                snapshot,grant,policies,allowed=self._deep_material(scope,row,now)
                eligible=eligible_material(snapshot,grant,policies,allowed,now)
                if not eligible:
                    raise ValueError("no currently granted material")
                material.append(eligible)
                reports.append(archive_report(eligible,snapshot_digest=snapshot["snapshot_digest"],grant=grant))
            changes=[]
            if len(material)==2:
                # Compare only exact canonical URL families; a fuzzy content
                # match never invents lineage or makes different URLs equivalent.
                def latest(items):
                    result={}
                    for sid,source,expiry in items:
                        url=source["canonical_url"];old=result.get(url)
                        if old is None or (source["fetched_at"],sid)>(old[1]["fetched_at"],old[0]):
                            result[url]=(sid,source,expiry)
                    return result
                old,new=map(latest,material)
                for url in sorted(old.keys() & new.keys()):
                    left,right=old[url],new[url]
                    comparison=compare_text(left[1]["text"],right[1]["text"])
                    changes.append({"old_source_id":left[0],"new_source_id":right[0],
                        "old_captured_at":left[1]["fetched_at"],"new_captured_at":right[1]["fetched_at"],
                        "chronology_forward":left[1]["fetched_at"]<=right[1]["fetched_at"],
                        "valid_until":min(left[2],right[2]),**comparison})
                differences={"matched_locator_families":len(changes),
                    "left_only":len(old.keys()-new.keys()),"right_only":len(new.keys()-old.keys()),
                    "comparisons":changes}
            else:
                differences=None
            return reports,differences
        try:
            reports,differences=await _bounded_discovery_cpu(analyze)
        except (ValueError,TypeError,KeyError,CheckpointReplicaError) as exc:
            raise CrawlerError("crawler_archive_analysis_held","Archive material is no longer qualified.",403) from exc
        # Revalidate the exact observed Mongo version and policy/grant witness
        # after CPU work, before returning any derived source metadata.
        for (predicate,row),report in zip(rows,reports):
            witness=await self.sessions.find_one({**predicate,"version":row["version"],
                "archive_grant":row["archive_grant"],"deep_archive":row["deep_archive"],
                "source_use_policies":row.get("source_use_policies",{"$exists":False})},
                {"_id":1},max_time_ms=2000)
            if witness is None or min(g["valid_until"] for g in report["groups"])<=_now().timestamp():
                raise CrawlerError("crawler_archive_analysis_changed","Archive authority changed during analysis.",409)
        result={"schema":"skeleton.dragon.archive-intelligence.v1","sessions":ids,"reports":reports,
                "revision_comparison":differences,"history_only":True,"source_text_returned":False,
                "physical_storage_modified":False,"network_authorized":False,"training_permission":False}
        return {**result,"receipt":a.digest(result)}

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
                    from core.dragon_hybrid_rank import build_route
                    from core.dragon_passage_index import build_passage_route
                    return (a.build_index(scope,snap,grant,policies,now,allowed),
                            build_route(scope,snap,grant,policies,now,allowed),
                            build_passage_route(scope,snap,grant,policies,now,allowed))
                index,hybrid,passages=await _bounded_discovery_cpu(build)
                await self._admit(scope,row["_id"],{"deep_index":index,"deep_hybrid_route":hybrid,
                    "deep_passage_route":passages})
            except CrawlerError:
                await self.sessions.update_one(fence,{"$set":{"deep_index_due":_now().timestamp()+300}})
                totals["held"]+=1
                continue
            except (ValueError,TypeError,KeyError,CheckpointReplicaError):
                await self.sessions.update_one(fence,{"$unset":{"deep_index":"","deep_hybrid_route":"","deep_passage_route":"","deep_dense_route":"","deep_dense_due":"","deep_full_state":"","deep_full_due":""},
                      "$set":{"deep_index_due":_now().timestamp()+3600}})
                totals["held"]+=1
                continue
            fence={**fence,"archive_grant":row["archive_grant"],"$expr":{"$and":[
                  {"$gt":["$deep_index_due",clock]},{"$gt":["$archive_grant.expires_at",clock]}]}}
            changed=await self.sessions.update_one(fence,{"$set":{"deep_index":index,"deep_hybrid_route":hybrid,"deep_passage_route":passages,
                "deep_index_due":min(index["expires_at"],_now().timestamp()+86400)}})
            totals["indexed" if changed.modified_count else "superseded"]+=1
        return totals

    async def deep_archive_search(self,scope,*,query,cursor=None,session_ids=None,game_id=None,_work=None):
        """Indexed candidate pages, exact reparse of each admitted row."""
        from core.dragon_crawler import CrawlerError,_now
        try:
            terms,tokens=a.query_terms(scope,query)
            from core.dragon_hybrid_rank import route_terms
            rare_tokens=route_terms(scope,query)
            from core.dragon_passage_index import query_keys
            passage_tokens=query_keys(scope,query)
            if session_ids is not None and (not isinstance(session_ids,list) or len(session_ids)>100 or not all(identity(x) for x in session_ids)):
                raise ValueError("session routing bound")
            if game_id is not None:
                from core.dragon_game_corpus import _id
                _id(game_id)
            cursor_query=query if session_ids is None and game_id is None else query+":"+a.digest([game_id,sorted(set(session_ids or []))])
            after=a.decode_cursor(scope,cursor_query,cursor)
        except ValueError as exc:
            raise CrawlerError("crawler_deep_query","Invalid archive search or cursor.",422) from exc
        from core.dragon_archive_intelligence import ArchiveWork,rank_exact
        work=_work if _work is not None else ArchiveWork()
        await self.ensure_indexes()
        now=_now().timestamp()
        predicate={**scope,"status":{"$in":sorted(TERMINAL)},"deep_archive.released":True,
            "deep_index.expires_at":{"$gt":now},"$or":[{"deep_index.tokens":{"$in":tokens}},
            {"deep_hybrid_route.tokens":{"$in":rare_tokens},"deep_hybrid_route.expires_at":{"$gt":now}},
            {"deep_passage_route.tokens":{"$in":passage_tokens},"deep_passage_route.expires_at":{"$gt":now}}]}
        if game_id is not None:
            predicate["$and"]=[{"$or":[{"game_route.game_id":game_id},{"_id":{"$in":session_ids or []}}]}]
        elif session_ids is not None:
            predicate["_id"]={"$in":session_ids}
        if after:
            predicate.setdefault("_id",{})["$gt"]=after
        async def page():
            return await self.sessions.find(predicate,{"_id":1,"version":1,"deep_index.digest":1,"deep_hybrid_route.digest":1,"deep_passage_route.digest":1}
                ).sort("_id",ASCENDING).limit(a.PAGE+1).max_time_ms(3000).to_list(a.PAGE+1)
        rows=await page()
        permitted=None
        if game_id is not None:
            from core.dragon_game_routing import verify_game_candidates
            permitted=await verify_game_candidates(scope,game_id,[x["_id"] for x in rows])
        hits=[]
        held=0
        expiries=[]
        for item in rows[:a.PAGE]:
            if permitted is not None and item["_id"] not in permitted:
                held+=1
                continue
            row=await self.sessions.find_one({**scope,"_id":item["_id"],"version":item["version"],
                "deep_index.digest":item["deep_index"]["digest"],"status":{"$in":sorted(TERMINAL)}},max_time_ms=2000)
            if not row:
                raise CrawlerError("crawler_deep_changed","Archive index changed.",409)
            try:
                def rank():
                    from core.dragon_hybrid_rank import Candidate,rank as hybrid_rank
                    snap,grant,policies,allowed=self._deep_material(scope,row,now)
                    a.validate_index(row["deep_index"],snap,grant,policies,now)
                    if "deep_hybrid_route" in row:
                        from core.dragon_hybrid_rank import validate_route
                        validate_route(row["deep_hybrid_route"],snap,grant,policies,now)
                    exact=rank_exact(snap,grant,policies,now,terms,allowed,work)
                    ranks=hybrid_rank(query,[Candidate(h["source_id"],snap["sources"][h["source_id"]]["title"],
                        snap["sources"][h["source_id"]]["text"]) for h in exact],work=work)
                    scored={h["key"]:h for h in ranks}
                    passage_scores={}
                    if row.get("deep_passage_route") is not None:
                        from core.dragon_passage_index import rank_passage_offsets
                        for hit in rank_passage_offsets(scope,query,snap,grant,policies,now,row["deep_passage_route"],allowed,work=work):
                            passage_scores.setdefault(hit["source_id"],hit["score"])
                    return [{**h,"hybrid_score":scored.get(h["source_id"],{}).get("score",0.0)
                            +.25*passage_scores.get(h["source_id"],0.0)} for h in exact]
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
                             "snapshot_digest":row["deep_archive"]["snapshot_digest"]})
        if rows!=await page() or expiries and min(expiries)<=_now().timestamp():
            raise CrawlerError("crawler_deep_changed","Archive authority changed during search.",409)
        # Bounded candidate rank, not global BM25. Preserve duplicate evidence
        # separately from source count; never present duplicates as corroboration.
        hits.sort(key=lambda h:(-h.get("hybrid_score",0),-h["matched_terms"],-h["term_frequency"],-h["captured_at"],h["session_id"],h["source_id"]))
        unique={}
        for h in hits:
            unique.setdefault(h["preserved_text_hash"],h)
        return {"ok":True,"schema":"skeleton.dragon.deep-search.v1","scanned":min(len(rows),a.PAGE),
            "held":held,"matches":list(unique.values())[:32],"matching_payloads":len(unique),
            "next_cursor":a.cursor(scope,cursor_query,rows[a.PAGE-1]["_id"]) if len(rows)>a.PAGE else None,
            "as_of_unix":now,"earliest_expiry":min(expiries) if expiries else None,
            "approximate_routing":True,"page_local_ranking":True,"ranking":"candidate_local_bm25_subword_passage_v2","history_only":True,
            "source_text_returned":False,"model_context_permission":False,"wiki_approval":False}


    def _historical_document(self,scope,row,source_id,terms,max_chars,now,dense_hit=None):
        """Exact historical Unicode passage, with no authority from the index."""
        import hashlib
        from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
        from skeleton.ai.webcrawler.dragon_companion import _lexemes
        snap,grant,policies,allowed=self._deep_material(scope,row,now)
        if source_id not in allowed:
            raise ValueError("source unavailable")
        source=snap["sources"][source_id]
        policy=policies.get(source_id,{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snap["snapshot_digest"],source=source,policy=policy,now=now)
        if expiry is None:
            raise ValueError("historical permission unavailable")
        text=source["text"]
        if not text:
            raise ValueError("empty source")
        if dense_hit is not None:
            start,end=dense_hit["start"],dense_hit["end"]
            if (type(start) is not int or type(end) is not int or not 0<=start<end<=len(text)
                    or end-start>768 or hashlib.sha256(text[start:end].encode()).hexdigest()!=dense_hit["passage_digest"]):
                raise ValueError("dense passage changed")
            span=text[start:min(end,start+max_chars)]
        else:
            width=min(max_chars,4000,len(text))
            wanted=set(terms)
            stride=max(1,width//2,(max(0,len(text)-width)+126)//127)
            starts=list(range(0,max(1,len(text)-width+1),stride))
            if starts[-1]!=len(text)-width:
                starts.append(len(text)-width)
            start=max(starts,key=lambda x:(len(wanted.intersection(_lexemes(text[x:x+width]))),-x))
            span=text[start:start+width]
            if wanted and not wanted.intersection(_lexemes(span)):
                raise ValueError("query matched metadata, not text")
        content=hashlib.sha256(span.encode("utf-8")).hexdigest()
        ref={"schema_version":"skeleton.dragon.historical-chat-reference.v1",
             "session_id":row["_id"],"source_id":source_id,"snapshot_digest":snap["snapshot_digest"],
             "source_digest":a.digest(source),"grant_digest":a.digest(grant),"policy_version":policy["version"],
             "start":start,"end":start+len(span),"passage_digest":content,"valid_until":expiry}
        doc={"source_id":source_id,"text":span,"content_digest":content,
            "source_ref":"dragon-archive://"+row["_id"]+"/"+source_id,
            "source_url":source["canonical_url"],"title":source["title"],
            "captured_at":source["fetched_at"],"valid_until":expiry,
            "history_only":True,"review_state":"unreviewed","source_classification":"untrusted_external_material",
            "authority":"historical_external_evidence_only","training_permission":False}
        return doc,ref

    async def history_context(self,scope,query,max_docs,max_chars,*,session_ids=None,game_id=None):
        """Explicit local-chat history retrieval; no promotion or current facts."""
        from core.dragon_crawler import CrawlerError,_now
        if type(max_docs) is not int or not 1<=max_docs<=4 or type(max_chars) is not int or not 1<=max_chars<=16000:
            raise CrawlerError("crawler_deep_context_bounds","Invalid historical context budget.",422)
        terms,_=a.query_terms(scope,query)
        options={} if session_ids is None else {"session_ids":session_ids}
        if game_id is not None:options["game_id"]=game_id
        from core.dragon_archive_intelligence import ArchiveWork
        work=ArchiveWork()
        page=await self.deep_archive_search(scope,query=query,_work=work,**options)
        from core.dragon_hybrid_rank import fuse_ranked
        pages=[page]
        for _ in range(2):
            cursor=pages[-1].get("next_cursor")
            if not cursor:
                break
            pages.append(await self.deep_archive_search(scope,query=query,cursor=cursor,_work=work,**options))
        by_key={}
        lanes=[]
        for result in pages:
            lane=[]
            for hit in result["matches"]:
                key=hit["session_id"]+":"+hit["source_id"]
                by_key[key]=hit
                lane.append(key)
            lanes.append(lane)
        from core.dragon_local_embeddings import configured
        dense_status="disabled"
        if configured():
            try:
                vector_hits=await self.dense_archive_candidates(scope,query,**options)
                try:
                    full_hits=await self.full_vector_candidates(scope,query,**options)
                    vector_hits=sorted(full_hits+vector_hits,key=lambda h:(-h["score"],h["session_id"],h["source_id"],h["start"]))[:64]
                except Exception:
                    # Preserve the already qualified sampled/lexical lanes.
                    pass
                dense_status="available"
                lane=[]
                for hit in vector_hits:
                    key=hit["session_id"]+":"+hit["source_id"]
                    by_key.setdefault(key,hit)
                    if key not in lane:
                        lane.append(key)
                if lane:
                    lanes.append(lane)
            except Exception:
                # A missing or failed operator model never blocks exact lexical retrieval.
                dense_status="held"
        ordered=fuse_ranked(lanes,limit=32)
        selected=[]
        seen_payloads=set()
        for key in ordered:
            hit=by_key[key]
            payload=hit.get("preserved_text_hash",key)
            if payload not in seen_payloads:
                selected.append(hit)
                seen_payloads.add(payload)
        permitted=None
        if game_id is not None:
            from core.dragon_game_routing import verify_game_candidates
            permitted=await verify_game_candidates(scope,game_id,[h["session_id"] for h in selected])
        docs=[]
        refs=[]
        remaining=max_chars
        for hit in selected:
            if permitted is not None and hit["session_id"] not in permitted:continue
            if len(docs)>=max_docs or remaining<=0:
                break
            row=await self.sessions.find_one({**scope,"_id":hit["session_id"],"version":hit["version"],
                "deep_archive.released":True,"status":{"$in":sorted(TERMINAL)}},max_time_ms=2000)
            if row is None:
                raise CrawlerError("crawler_deep_changed","Selected historical evidence changed.",409)
            try:
                doc,ref=await _bounded_discovery_cpu(self._historical_document,scope,row,
                    hit["source_id"],terms,min(remaining,4000),_now().timestamp(),hit if hit.get("_dense") else None)
            except (ValueError,TypeError,KeyError,CheckpointReplicaError):
                continue
            if ref["snapshot_digest"]!=hit["snapshot_digest"]:
                raise CrawlerError("crawler_deep_changed","Historical witness changed.",409)
            docs.append(doc)
            refs.append(ref)
            remaining-=len(doc["text"])
        await self.assert_history_context(scope,refs)
        return {"documents":docs,"references":refs,"history_only":True,"partial_routing":True,"dense_status":dense_status}

    def _check_history_pin(self,scope,row,pin,now):
        import hashlib
        from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
        snap,grant,policies,allowed=self._deep_material(scope,row,now)
        if pin["source_id"] not in allowed:
            raise ValueError("historical source unavailable")
        source=snap["sources"][pin["source_id"]]
        policy=policies.get(pin["source_id"],{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snap["snapshot_digest"],source=source,policy=policy,now=now)
        if (expiry is None or expiry!=pin["valid_until"] or snap["snapshot_digest"]!=pin["snapshot_digest"]
                or a.digest(source)!=pin["source_digest"] or a.digest(grant)!=pin["grant_digest"]
                or policy["version"]!=pin["policy_version"] or pin["end"]>len(source["text"])
                or hashlib.sha256(source["text"][pin["start"]:pin["end"]].encode()).hexdigest()!=pin["passage_digest"]):
            raise ValueError("historical evidence identity changed")

    async def assert_history_context(self,scope,references):
        """Separate chat-only verifier; never a current reviewed Wiki pin."""
        from core.dragon_crawler import CrawlerError,_now
        from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity,finite
        if not isinstance(references,list) or len(references)>4:
            raise CrawlerError("crawler_deep_reference","Historical references exceed bound.",403)
        for pin in references:
            if (not isinstance(pin,dict) or set(pin)!={"schema_version","session_id","source_id","snapshot_digest",
                    "source_digest","grant_digest","policy_version","start","end","passage_digest","valid_until"}
                    or pin["schema_version"]!="skeleton.dragon.historical-chat-reference.v1"
                    or not identity(pin["session_id"])
                    or not all(hash_identity(pin[k]) for k in ("source_id","snapshot_digest","source_digest","grant_digest","passage_digest"))
                    or type(pin["policy_version"]) is not int or not 0<=pin["policy_version"]<=2**31-1
                    or type(pin["start"]) is not int or type(pin["end"]) is not int
                    or not 0<=pin["start"]<pin["end"]<=24000 or pin["end"]-pin["start"]>4000
                    or not finite(pin["valid_until"]) or pin["valid_until"]<=_now().timestamp()):
                raise CrawlerError("crawler_deep_reference","Historical reference invalid or expired.",403)
            query={**scope,"_id":pin["session_id"],"deep_archive.released":True,"status":{"$in":sorted(TERMINAL)}}
            row=await self.sessions.find_one(query,max_time_ms=2000)
            if row is None:
                raise CrawlerError("crawler_deep_reference","Historical evidence unavailable.",403)
            try:
                await _bounded_discovery_cpu(self._check_history_pin,scope,row,pin,_now().timestamp())
            except (ValueError,TypeError,KeyError,CheckpointReplicaError) as exc:
                raise CrawlerError("crawler_deep_reference","Historical evidence changed or withdrawn.",403) from exc
            final=await self.sessions.find_one({**query,"version":row["version"]},{"_id":1},max_time_ms=2000)
            if final is None or pin["valid_until"]<=_now().timestamp():
                raise CrawlerError("crawler_deep_reference","Historical evidence changed during verification.",403)
