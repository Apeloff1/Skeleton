"""Optional local dense retrieval lane, with separate bounded worker admission."""
from __future__ import annotations

import asyncio
import logging
from pymongo import ASCENDING
from core import dragon_dense_index as dense
from core import dragon_local_embeddings as local
from core.dragon_checkpoint_replica import CheckpointReplicaError
from skeleton.ai.webcrawler.dragon_treasury_vault import TERMINAL

log=logging.getLogger(__name__)
_gate=asyncio.Semaphore(1)

async def _cpu(fn):
    await asyncio.wait_for(_gate.acquire(),timeout=0.5)
    try:
        task=asyncio.create_task(asyncio.to_thread(fn))
    except BaseException:
        _gate.release()
        raise
    def finished(future):
        _gate.release()
        if not future.cancelled():
            future.exception()
    task.add_done_callback(finished)
    return await asyncio.shield(task)


class DragonDenseArchiveMixin:
    async def build_deep_dense_indexes(self,*,limit=1):
        from core.dragon_crawler import CrawlerError,_now
        if type(limit) is not int or not 1<=limit<=2:
            raise ValueError("dense indexing bound")
        totals={"scanned":0,"indexed":0,"held":0,"superseded":0,"enabled":local.configured()}
        if not totals["enabled"]:
            return totals
        try:
            encoder=await _cpu(local.encoder)
        except Exception:
            totals["held"]+=1
            return totals
        await self.ensure_indexes()
        now=_now().timestamp()
        query={"status":{"$in":sorted(TERMINAL)},"deep_archive.released":True,
               "archive_grant.expires_at":{"$gt":now},"deep_index.expires_at":{"$gt":now},
               "$or":[{"deep_dense_due":{"$exists":False}},{"deep_dense_due":{"$lte":now}}]}
        rows=await self.sessions.find(query,{"_id":1,"version":1,"tenant_id":1,"owner_id":1,"deep_dense_due":1}
            ).sort([("deep_dense_due",ASCENDING),("_id",ASCENDING)]).limit(limit).max_time_ms(2000).to_list(limit)
        totals["scanned"]=len(rows)
        for item in rows:
            scope={k:item[k] for k in ("tenant_id","owner_id")}
            clock={"$divide":[{"$toLong":"$$NOW"},1000]}
            claim=_now().timestamp()+300
            fence={**scope,"_id":item["_id"],"version":item["version"],"deep_archive.released":True,
                   "deep_dense_due":item.get("deep_dense_due",{"$exists":False}),
                   "$expr":{"$lte":[{"$ifNull":["$deep_dense_due",0]},clock]}}
            changed=await self.sessions.update_one(fence,{"$set":{"deep_dense_due":claim}})
            if not changed.modified_count:
                totals["superseded"]+=1
                continue
            fence={**fence,"deep_dense_due":claim,"$expr":{"$gt":["$deep_dense_due",clock]}}
            row=await self.sessions.find_one(fence,max_time_ms=2000)
            if row is None:
                totals["superseded"]+=1
                continue
            try:
                def build():
                    snap,grant,policies,allowed=self._deep_material(scope,row,_now().timestamp())
                    return dense.build(scope,snap,grant,policies,_now().timestamp(),allowed,encoder)
                index=await _cpu(build)
                await self._admit(scope,row["_id"],{"deep_dense_route":index})
            except (CrawlerError,CheckpointReplicaError,ValueError,TypeError,KeyError,RuntimeError,OSError,TimeoutError):
                totals["held"]+=1
                continue
            except Exception:
                log.warning("Optional dense index unavailable")
                totals["held"]+=1
                continue
            fence={**fence,"archive_grant":row["archive_grant"],"deep_index.digest":row["deep_index"]["digest"],
                   "$expr":{"$and":[{"$gt":["$deep_dense_due",clock]},
                                     {"$gt":["$archive_grant.expires_at",clock]}]}}
            changed=await self.sessions.update_one(fence,{"$set":{"deep_dense_route":index,
                "deep_dense_due":min(index["expires_at"],_now().timestamp()+86400)}})
            totals["indexed" if changed.modified_count else "superseded"]+=1
        return totals

    async def dense_archive_candidates(self,scope,query,*,session_ids=None,game_id=None):
        from core.dragon_crawler import CrawlerError,_now
        if not local.configured():
            return []
        q=await _cpu(lambda:dense.query(scope,query,local.encoder()))
        now=_now().timestamp()
        predicate={**scope,"status":{"$in":sorted(TERMINAL)},"deep_archive.released":True,
                   "deep_dense_route.model_identity":q["model_identity"],
                   "deep_dense_route.expires_at":{"$gt":now},"deep_dense_route.tokens":{"$in":q["tokens"]}}
        if game_id is not None:
            predicate["$or"]=[{"game_route.game_id":game_id},{"_id":{"$in":session_ids or []}}]
        elif session_ids is not None:
            predicate["_id"]={"$in":session_ids}
        rows=await self.sessions.find(predicate).sort("_id",ASCENDING).limit(16).max_time_ms(2000).to_list(16)
        def rerank():
            hits=[]
            for row in rows:
                try:
                    snap,grant,policies,allowed=self._deep_material(scope,row,_now().timestamp())
                    for hit in dense.rank(scope,snap,grant,policies,_now().timestamp(),allowed,row["deep_dense_route"],q):
                        hits.append({**hit,"session_id":row["_id"],"version":row["version"],
                                     "snapshot_digest":snap["snapshot_digest"],"_dense":True})
                except (CrawlerError,CheckpointReplicaError,ValueError,KeyError,TypeError):
                    continue
            return sorted(hits,key=lambda h:(-h["score"],h["session_id"],h["source_id"],h["start"]))[:32]
        return await _cpu(rerank)
