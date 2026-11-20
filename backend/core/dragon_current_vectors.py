"""Full current-capture semantic coverage, independent of historical grants.

Derived embeddings are never treated as evidence. Only exact current source
spans with canonical freshness, policy and consent pins can reach Jeeves.
"""
from __future__ import annotations

import base64
from datetime import datetime,timezone
import hashlib
import logging
from dataclasses import asdict

from pymongo import ASCENDING
from core import dragon_dense_index as dense,dragon_local_embeddings as local
from core.dragon_dense_runtime import _cpu
from skeleton.ai.webcrawler.dragon_archive_scale import digest

BATCH=8
MAX_BATCHES=48
log=logging.getLogger(__name__)


def current_windows(app,row,snapshot):
    windows=[]
    for sid,source in sorted(snapshot["sources"].items()):
        fresh=app._capture_freshness(row,source)
        if not fresh["usable"]:continue
        text=source["text"]
        if len(text)>24000:raise ValueError("retained text bound")
        expiry=datetime.fromisoformat(fresh["valid_until"]).timestamp()
        for start in range(0,len(text),512):
            end=min(len(text),start+768)
            if text[start:end].strip():
                windows.append([sid,start,end,expiry,source["preserved_text_hash"],app._capture_policy(row,source)["version"]])
            if end==len(text):break
    if len(windows)>64*47:raise ValueError("source windows bound")
    return windows


def build_current_batch(scope,snapshot,windows,encoder):
    projection=dense.planes(encoder.identity,encoder.dimensions)
    records=[];union=set()
    texts=[snapshot["sources"][w[0]]["text"][w[1]:w[2]] for w in windows]
    vectors=encoder.encode(texts)
    if len(vectors)!=len(windows):raise ValueError("model response bound")
    for (sid,start,end,expiry,content_hash,policy),text,vector in zip(windows,texts,vectors):
        raw=dense.quantize(vector)
        if len(raw)!=encoder.dimensions:raise ValueError("vector dimensions")
        keys=dense.tokens(scope,encoder.identity,dense.codes(raw,projection))
        union.update(keys)
        records.append({"source_id":sid,"start":start,"end":end,"expiry":expiry,"content_hash":content_hash,
            "policy":policy,"vector":base64.b64encode(raw).decode("ascii"),"tokens":keys,
            "passage_hash":hashlib.sha256(text.encode()).hexdigest()})
    value={"schema":"dragon.current-vector-batch.v1","model":encoder.identity,"records":records,"tokens":sorted(union)}
    return {**value,"digest":digest(value)}


class DragonCurrentVectorMixin:
    def _current_vectors(self):
        return self.database["dragon_current_full_vector_postings"]

    async def ensure_current_vector_indexes(self):
        if getattr(self,"_current_vector_ready",False):return
        col=self._current_vectors()
        await col.create_index([("tenant_id",ASCENDING),("owner_id",ASCENDING),
            ("model",ASCENDING),("batch.tokens",ASCENDING),("expires",ASCENDING)])
        await col.create_index([("tenant_id",1),("owner_id",1),("game_id",1),("model",1),("batch.tokens",1),("expires",1)])
        await col.create_index([("tenant_id",1),("owner_id",1),("session",1),("generation",1),("ordinal",1)],unique=True)
        await col.create_index("expires",expireAfterSeconds=0)
        await self.sessions.create_index([("current_vector_due",1),("consent_expires_at",1)])
        self._current_vector_ready=True

    async def build_current_vector_batch(self):
        from core.dragon_crawler import _now,_plain,CrawlerError
        if not local.configured():return {"enabled":False}
        try:encoder=await _cpu(local.encoder)
        except Exception:return {"enabled":True,"held":True}
        await self.ensure_current_vector_indexes()
        now=_now()
        eligible={"status":{"$in":["completed","budget_exhausted","paused","ready"]},
            "treasury_vault":None,"consent_expires_at":{"$gt":now},
            "$or":[{"current_vector_due":{"$exists":False}},{"current_vector_due":{"$lte":now.timestamp()}}]}
        rows=await self.sessions.find(eligible,{"_id":1,"tenant_id":1,"owner_id":1,"version":1,"current_vector_due":1}
            ).sort([("current_vector_due",1),("_id",1)]).limit(1).max_time_ms(2000).to_list(1)
        if not rows:return {"enabled":True,"idle":True}
        item=rows[0];scope={k:item[k] for k in ("tenant_id","owner_id")}
        lease=now.timestamp()+180
        fence={**scope,"_id":item["_id"],"version":item["version"],
               "consent_expires_at":{"$gt":now},"current_vector_due":item.get("current_vector_due",{"$exists":False})}
        if not (await self.sessions.update_one(fence,{"$set":{"current_vector_due":lease}})).modified_count:
            return {"superseded":True}
        fence["current_vector_due"]=lease
        try:
            row=await self._owned(scope,item["_id"])
            if row["version"]!=item["version"]:return {"superseded":True}
            self._source_use(row)
            snap=_plain(row["snapshot"])
            windows=await _cpu(lambda:current_windows(self,row,snap))
            gen=digest([scope,item["_id"],row["version"],snap["snapshot_digest"],encoder.identity,windows])
            old=row.get("current_vector_state") or {}
            cursor=old.get("covered",0) if old.get("generation")==gen else 0
            if type(cursor) is not int or not 0<=cursor<=len(windows):raise ValueError("coverage cursor")
            end=min(cursor+BATCH,len(windows))
            if end>cursor:
                batch=await _cpu(lambda:build_current_batch(scope,snap,windows[cursor:end],encoder))
                expiry=min(x[3] for x in windows[cursor:end])
                posting={**scope,"session":row["_id"],"generation":gen,"model":encoder.identity,
                    "game_id":(row.get("game_route") or {}).get("game_id"),
                    "ordinal":cursor,"batch":batch,"expires":datetime.fromtimestamp(expiry,timezone.utc)}
                await self._admit(scope,row["_id"],{"current_semantic_batch":{**posting,"expires":expiry}})
                await self._current_vectors().replace_one({**scope,"session":row["_id"],"generation":gen,
                    "ordinal":cursor},posting,upsert=True)
            complete=end==len(windows)
            if complete:
                expected=list(range(0,len(windows),BATCH))
                actual=await self._current_vectors().find({**scope,"session":row["_id"],"generation":gen},
                    {"ordinal":1}).sort("ordinal",1).limit(len(expected)+1).max_time_ms(2000).to_list(len(expected)+1)
                if [x["ordinal"] for x in actual]!=expected:
                    await self.sessions.update_one(fence,{"$unset":{"current_vector_state":""},"$set":{"current_vector_due":now.timestamp()+30}})
                    return {"held":True,"reason":"coverage_gap"}
            expiry=min((x[3] for x in windows),default=now.timestamp()+600)
            state={"generation":gen,"model":encoder.identity,"covered":end,"total":len(windows),"complete":complete,
                   "snapshot_digest":snap["snapshot_digest"],"version":row["version"],"expires_at":expiry}
            changed=await self.sessions.update_one(fence,{"$set":{"current_vector_state":state,
                "current_vector_due":min(expiry,now.timestamp()+600) if complete else _now().timestamp()}})
            return {"enabled":True,"covered":end,"total":len(windows),"complete":complete,"published":bool(changed.modified_count)}
        except (CrawlerError,ValueError,KeyError,TypeError,RuntimeError,TimeoutError,OSError):
            return {"enabled":True,"held":True}

    async def current_semantic_candidates(self,scope,query,session_ids=None,game_id=None):
        from core.dragon_crawler import _now,_plain,CrawlerError
        from skeleton.ai.webcrawler.dragon_mission_quality import scan_untrusted_instructions
        if not local.configured():return []
        await self.ensure_current_vector_indexes()
        q=await _cpu(lambda:dense.query(scope,query[:512],local.encoder()))
        predicate={**scope,"model":q["model_identity"],"batch.tokens":{"$in":q["tokens"]},"expires":{"$gt":_now()}}
        if game_id is not None:
            predicate["$or"]=[{"game_id":game_id},{"session":{"$in":session_ids or []}}]
        elif session_ids is not None:predicate["session"]={"$in":session_ids}
        postings=await self._current_vectors().find(predicate).sort([("session",1),("ordinal",1)]).limit(
            MAX_BATCHES).max_time_ms(2000).to_list(MAX_BATCHES)
        hits=[]
        for posting in postings:
            row=await self.sessions.find_one({**scope,"_id":posting["session"],"current_vector_state.generation":posting["generation"],
                "current_vector_state.complete":True,"consent_expires_at":{"$gt":_now()}},max_time_ms=2000)
            if not row or row["current_vector_state"]["version"]!=row["version"]:continue
            try:
                row=await self._owned(scope,row["_id"])
                state=row["current_vector_state"]
                if state["version"]!=row["version"] or state["generation"]!=posting["generation"]:continue
                self._source_use(row)
                snap=_plain(row["snapshot"]);batch=posting["batch"]
                if state["snapshot_digest"]!=snap["snapshot_digest"] or batch["model"]!=q["model_identity"] or batch["digest"]!=digest({k:v for k,v in batch.items() if k!="digest"}):
                    continue
                if len(batch["records"])>BATCH:continue
                for record in batch["records"]:
                    if not set(q["tokens"]).intersection(record["tokens"]):continue
                    source=snap["sources"].get(record["source_id"])
                    if not source:continue
                    fresh=self._capture_freshness(row,source)
                    if not fresh["usable"] or source["preserved_text_hash"]!=record["content_hash"] or self._capture_policy(row,source)["version"]!=record["policy"]:continue
                    if datetime.fromisoformat(fresh["valid_until"]).timestamp()!=record["expiry"]:continue
                    start,end=record["start"],record["end"]
                    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(source["text"]) or end-start>768:continue
                    span=source["text"][start:end];h=hashlib.sha256(span.encode()).hexdigest()
                    if h!=record["passage_hash"]:continue
                    raw=base64.b64decode(record["vector"],validate=True)
                    if len(raw)!=len(q["vector"]):continue
                    score=dense._cosine(q["vector"],raw)
                    if score<dense.MIN_COSINE:continue
                    reference=self._source_reference(row,source)
                    hits.append({"source_id":source["source_id"],"canonical_url":source["canonical_url"],"title":source["title"],
                        "content_hash":source["content_hash"],"preserved_text_hash":source["preserved_text_hash"],
                        "passage_hash":h,"start":start,"end":end,"text":span,
                        "lexical_score":min(1,.85*score),"semantic_score":score,"review_state":"unreviewed",
                        "authority":"external_evidence_only","reference":reference,"valid_until":fresh["valid_until"],
                        "capture_timestamp":source["fetched_at"],
                        "instruction_risks":[asdict(x) for x in scan_untrusted_instructions(span,limit=16)]})
            except (CrawlerError,KeyError,ValueError,TypeError,RuntimeError):continue
        return sorted(hits,key=lambda x:(-x["semantic_score"],x["source_id"],x["start"]))[:32]

    async def purge_current_vector_batches(self):
        if not local.configured() and not getattr(self,"_current_vector_ready",False):return {"enabled":False}
        await self.ensure_current_vector_indexes()
        col=self._current_vectors()
        after=getattr(self,"_current_purge_after",None)
        rows=await col.find({"_id":{"$gt":after}} if after is not None else {},
            {"tenant_id":1,"owner_id":1,"session":1,"generation":1}).sort("_id",1).limit(32).max_time_ms(2000).to_list(32)
        if not rows:
            self._current_purge_after=None;return {"removed":0}
        removed=0
        from core.dragon_crawler import _now
        for p in rows:
            row=await self.sessions.find_one({"tenant_id":p["tenant_id"],"owner_id":p["owner_id"],"_id":p["session"],
                "status":{"$nin":["cancelled","deleted"]},"consent_expires_at":{"$gt":_now()},
                "$or":[{"current_vector_state.generation":p["generation"],"$expr":{"$eq":["$version","$current_vector_state.version"]}},
                       {"current_vector_due":{"$gt":_now().timestamp(),"$lte":_now().timestamp()+180}}]}, {"_id":1},max_time_ms=2000)
            if row is None:removed+=(await col.delete_one({"_id":p["_id"],"generation":p["generation"]})).deleted_count
        self._current_purge_after=rows[-1]["_id"]
        return {"scanned":len(rows),"removed":removed}
