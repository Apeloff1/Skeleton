"""Restart-safe full historical passage coverage in separately bounded postings.

A generation is queryable only after every expected overlapping window is
published. Partial generations are never presented as complete. Source authority
is revalidated using the existing canonical archive material and final pin.
"""
from __future__ import annotations

from datetime import datetime,timezone
import hashlib
import json
import logging

from pymongo import ASCENDING
from core import dragon_dense_index as dense,dragon_local_embeddings as local
from core.dragon_dense_runtime import _cpu
from core.dragon_checkpoint_replica import CheckpointReplicaError
from skeleton.ai.webcrawler.dragon_archive_scale import digest
from skeleton.ai.webcrawler.dragon_treasury_vault import TERMINAL

log=logging.getLogger(__name__)
BATCH=8
MAX_CANDIDATE_BATCHES=64


def generation(scope,session,snapshot,grant,policies,model,spans):
    return digest({"scope":scope,"session":session,"snapshot":snapshot["snapshot_digest"],
                   "grant":digest(grant),"policy":digest(policies),"model":model,
                   "windows":digest(spans),"schema":"dragon.full-vector-v1"})


class DragonExhaustiveVectorMixin:
    def _full_vectors(self):
        return self.database["dragon_full_vector_postings"]

    async def ensure_full_vector_indexes(self):
        if getattr(self,"_full_vectors_ready",False):return
        collection=self._full_vectors()
        await collection.create_index([("tenant_id",ASCENDING),("owner_id",ASCENDING),
            ("model",ASCENDING),("index.tokens",ASCENDING),("expires",ASCENDING)])
        await collection.create_index([("tenant_id",1),("owner_id",1),("game_id",1),("model",1),("index.tokens",1),("expires",1)])
        await collection.create_index([("tenant_id",ASCENDING),("owner_id",ASCENDING),
            ("session",ASCENDING),("generation",ASCENDING),("ordinal",ASCENDING)],unique=True)
        await collection.create_index("expires",expireAfterSeconds=0)
        await self.sessions.create_index([("deep_full_due",ASCENDING),("archive_grant.expires_at",ASCENDING)])
        self._full_vectors_ready=True

    async def build_full_vector_batch(self):
        from core.dragon_crawler import _now,CrawlerError
        if not local.configured():return {"configured":False}
        try: encoder=await _cpu(local.encoder)
        except Exception:return {"configured":True,"held":True,"reason":"local_encoder_unavailable"}
        await self.ensure_indexes()
        await self.ensure_full_vector_indexes()
        now=_now().timestamp()
        rows=await self.sessions.find({"status":{"$in":sorted(TERMINAL)},"deep_archive.released":True,
            "archive_grant.expires_at":{"$gt":now},"$or":[{"deep_full_due":{"$exists":False}},
                 {"deep_full_due":{"$lte":now}}]},
            {"_id":1,"version":1,"tenant_id":1,"owner_id":1,"deep_full_due":1}
            ).sort([("deep_full_due",ASCENDING),("_id",ASCENDING)]).limit(1).max_time_ms(2000).to_list(1)
        if not rows:return {"configured":True,"idle":True}
        item=rows[0];scope={k:item[k] for k in ("tenant_id","owner_id")}
        # Same version/lease fence as the archive indexer. Worker claims do not
        # count as a change in content authority.
        claim=now+300
        fence={**scope,"_id":item["_id"],"version":item["version"],
               "deep_archive.released":True,"archive_grant.expires_at":{"$gt":now},
               "deep_full_due":item.get("deep_full_due",{"$exists":False})}
        reserved=await self.sessions.update_one(fence,{"$set":{"deep_full_due":claim}})
        if not reserved.modified_count:return {"superseded":True}
        fence={**fence,"deep_full_due":claim}
        row=await self.sessions.find_one(fence,max_time_ms=2000)
        if not row:return {"superseded":True}
        try:
            def plan():
                snap,grant,policies,allowed=self._deep_material(scope,row,_now().timestamp())
                spans=dense.exhaustive_spans(snap,grant,policies,_now().timestamp(),allowed)
                gen=generation(scope,row["_id"],snap,grant,policies,encoder.identity,spans)
                return snap,grant,policies,allowed,spans,gen
            snap,grant,policies,allowed,spans,gen=await _cpu(plan)
            previous=row.get("deep_full_state") or {}
            if previous.get("generation")==gen:
                cursor=previous.get("covered",0)
                if type(cursor) is not int or not 0<=cursor<=len(spans) or (cursor% BATCH and cursor!=len(spans)):
                    raise ValueError("invalid coverage cursor")
            else:cursor=0
            end=min(cursor+BATCH,len(spans))
            if cursor<end:
                index=await _cpu(lambda:dense.build(scope,snap,grant,policies,_now().timestamp(),allowed,
                    encoder,explicit_spans=spans[cursor:end]))
                if len(index["records"])!=end-cursor:raise ValueError("incomplete batch")
                expiry=min(grant["expires_at"],min(s[3] for s in spans[cursor:end]))
                # Derived rows never outlive their grant. Admit the exact batch
                # before publication and use a deterministic unique identity.
                posting={**scope,"session":row["_id"],"generation":gen,"model":encoder.identity,
                         "game_id":(row.get("game_route") or {}).get("game_id"),
                         "ordinal":cursor,"index":index,"expires":datetime.fromtimestamp(expiry,timezone.utc)}
                await self._admit(scope,row["_id"],{"full_vector":{**posting,"expires":expiry}})
                await self._full_vectors().replace_one({**scope,"session":row["_id"],"generation":gen,
                    "ordinal":cursor},posting,upsert=True)
            complete=end==len(spans)
            if complete:
                # Verify every expected batch ordinal is present before making
                # a generation searchable; never infer completeness from cursor.
                expected=list(range(0,len(spans),BATCH))
                actual=await self._full_vectors().find({**scope,"session":row["_id"],"generation":gen},
                    {"ordinal":1}).sort("ordinal",ASCENDING).limit(len(expected)+1).max_time_ms(2000).to_list(len(expected)+1)
                if [r["ordinal"] for r in actual]!=expected:
                    await self.sessions.update_one(fence,{"$unset":{"deep_full_state":""},"$set":{"deep_full_due":now+60}})
                    return {"held":True,"reason":"coverage_gap"}
            state={"generation":gen,"model":encoder.identity,"covered":end,"total":len(spans),
                   "complete":complete,"snapshot_digest":snap["snapshot_digest"],
                   "grant_digest":digest(grant),"policy_digest":digest(policies),"expires_at":grant["expires_at"]}
            result=await self.sessions.update_one({**fence,"archive_grant":row["archive_grant"],
                "$expr":{"$gt":["$archive_grant.expires_at",{"$divide":[{"$toLong":"$$NOW"},1000]}]}},
                {"$set":{"deep_full_state":state,"deep_full_due":grant["expires_at"] if complete else _now().timestamp()}})
            return {"configured":True,"covered":end,"total":len(spans),"complete":complete,
                    "published":bool(result.modified_count),"exhaustive_retained_text":complete}
        except (CrawlerError,CheckpointReplicaError,ValueError,RuntimeError,TypeError,KeyError,OSError,TimeoutError):
            log.warning("Full vector batch held")
            return {"configured":True,"held":True}

    async def full_vector_candidates(self,scope,query,*,session_ids=None,game_id=None):
        from core.dragon_crawler import _now,CrawlerError
        if not local.configured():return []
        await self.ensure_full_vector_indexes()
        q=await _cpu(lambda:dense.query(scope,query,local.encoder()))
        predicate={**scope,"model":q["model_identity"],"index.tokens":{"$in":q["tokens"]},
                   "expires":{"$gt":_now()}}
        if game_id is not None:
            predicate["$or"]=[{"game_id":game_id},{"session":{"$in":session_ids or []}}]
        elif session_ids is not None:predicate["session"]={"$in":session_ids}
        postings=await self._full_vectors().find(predicate).sort(
            [("session",ASCENDING),("ordinal",ASCENDING)]).limit(MAX_CANDIDATE_BATCHES).max_time_ms(2000).to_list(MAX_CANDIDATE_BATCHES)
        hits=[]
        for p in postings:
            now=_now().timestamp()
            row=await self.sessions.find_one({**scope,"_id":p["session"],"deep_full_state.generation":p["generation"],
                "deep_full_state.complete":True,"deep_full_state.expires_at":{"$gt":now},
                "status":{"$in":sorted(TERMINAL)}},max_time_ms=2000)
            if row is None:continue
            try:
                def rerank():
                    snap,grant,policies,allowed=self._deep_material(scope,row,_now().timestamp())
                    state=row["deep_full_state"]
                    if state["snapshot_digest"]!=snap["snapshot_digest"] or state["grant_digest"]!=digest(grant) or state["policy_digest"]!=digest(policies):
                        return []
                    return [{**h,"session_id":row["_id"],"version":row["version"],
                            "snapshot_digest":snap["snapshot_digest"],"_dense":True}
                        for h in dense.rank(scope,snap,grant,policies,_now().timestamp(),allowed,p["index"],q)]
                hits.extend(await _cpu(rerank))
            except (CrawlerError,CheckpointReplicaError,ValueError,RuntimeError,KeyError,TypeError):continue
        return sorted(hits,key=lambda h:(-h["score"],h["session_id"],h["source_id"],h["start"]))[:32]

    async def purge_stale_full_vector_batches(self):
        """Incremental stale-generation purge in addition to grant-expiry TTL."""
        from core.dragon_crawler import _now
        if not local.configured() and not getattr(self,"_full_vectors_ready",False):
            return {"configured":False}
        await self.ensure_full_vector_indexes()
        collection=self._full_vectors()
        after=getattr(self,"_full_purge_after",None)
        predicate={} if after is None else {"_id":{"$gt":after}}
        rows=await collection.find(predicate,{"tenant_id":1,"owner_id":1,"session":1,"generation":1,
            "expires":1}).sort("_id",ASCENDING).limit(32).max_time_ms(2000).to_list(32)
        if not rows:
            self._full_purge_after=None
            return {"scanned":0,"removed":0}
        removed=0
        for p in rows:
            row=await self.sessions.find_one({"tenant_id":p["tenant_id"],"owner_id":p["owner_id"],"_id":p["session"],
                "status":{"$in":sorted(TERMINAL)},"archive_grant.expires_at":{"$gt":_now().timestamp()},
                "$or":[{"deep_full_state.generation":p["generation"]},{"deep_full_due":{"$gt":_now().timestamp(),"$lte":_now().timestamp()+300}}]},
                {"_id":1},max_time_ms=2000)
            if row is None:
                result=await collection.delete_one({"_id":p["_id"],"generation":p["generation"]})
                removed+=result.deleted_count
        self._full_purge_after=rows[-1]["_id"]
        return {"scanned":len(rows),"removed":removed}
