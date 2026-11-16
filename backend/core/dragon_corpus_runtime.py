"""Application bridge for game catalogue, discovery and canonical capture.

Metadata workers cannot launch network operations. A distinct authenticated
editor command explicitly binds the latest observation, original capture
rights and a finite existing crawler automation grant (if requested).
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

from core.dragon_game_corpus import GameCorpus,CatalogueHeld,digest
from core.dragon_release_queue import ReleaseQueue
from core.game_learning import GameLearningError

_GATE=asyncio.Semaphore(2)


def _path(*,create=False,scope=None):
    from core import dragon_runtime as runtime
    path=runtime._path("SKL_DRAGON_GAME_CORPUS_DB_PATH",create=create)
    for variable in ("SKL_DRAGON_KNOWLEDGE_DB_PATH","SKL_DRAGON_PRACTICE_DB_PATH"):
        raw=os.getenv(variable,"").strip()
        if raw:
            other=Path(raw).expanduser()
            if other.exists() and path.samefile(other):
                raise GameLearningError("dragon_storage_invalid","Game corpus requires a separate store.",503)
    from core.dragon_owner_shards import guard_root,owner_path,ShardHeld
    try:guard_root(path,"corpus")
    except ShardHeld as exc:raise CatalogueHeld("corpus migration held") from exc
    if scope is not None:
        try:path=owner_path(path,"corpus",scope)
        except ShardHeld as exc:raise CatalogueHeld("corpus shard held") from exc
        for variable in ("SKL_DRAGON_KNOWLEDGE_DB_PATH","SKL_DRAGON_PRACTICE_DB_PATH"):
            raw=os.getenv(variable,"").strip()
            if raw and Path(raw).expanduser().exists() and path.samefile(Path(raw).expanduser()):
                raise CatalogueHeld("corpus shard aliases another store")
    return path


def _maintenance_path(job):
    from core.dragon_owner_shards import next_path,ShardHeld
    try:return next_path(_path(),"corpus",job)
    except ShardHeld as exc:raise CatalogueHeld("corpus maintenance shard held") from exc


async def _bounded(work):
    # Hold the gate until the real thread drains, even if an HTTP caller drops.
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


async def release_call(scope,operation,*args,**kwargs):
    if operation not in {"enqueue","status"}:
        raise ValueError("release operation")
    def work():
        path=_path(scope=scope,create=operation=="enqueue" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
        return getattr(ReleaseQueue(path),operation)(scope,*args,**kwargs)
    return await _bounded(work)


async def pulse_release_imports():
    if not os.getenv("SKL_DRAGON_GAME_CORPUS_DB_PATH","").strip():
        return {"configured":False,"network_executed":False}
    try:
        def pulse():
            path=_maintenance_path("release")
            queue=ReleaseQueue(path).pulse(limit=16)
            try:
                index=GameCorpus(path).backfill_facets(limit=32)
            except (CatalogueHeld,ValueError,TypeError,KeyError,sqlite3.Error):
                index={"failed":True,"reason":"facet_index_held"}
            try:
                sources=GameCorpus(path).backfill_source_locators(limit=32)
            except (CatalogueHeld,ValueError,TypeError,KeyError,sqlite3.Error):
                sources={"failed":True,"reason":"locator_index_held"}
            return {**queue,"facet_backfill":index,"source_locator_backfill":sources}
        return await _bounded(pulse)
    except (GameLearningError,CatalogueHeld,sqlite3.Error,OSError,TimeoutError):
        return {"failed":True,"reason":"release_store_held","network_executed":False}


async def dispatch_capture(scope,principal,*,game,source,observation_digest,operation,
                           capture_rights_acknowledged,consent,autonomous=False):
    from core.dragon_crawler import authenticated_scope,crawler_application,CrawlerError
    if (authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}
            or capture_rights_acknowledged is not True or consent is not True or type(autonomous) is not bool):
        raise CrawlerError("crawler_consent_required","Explicit current editor capture rights required.",403)
    if not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation:
        raise ValueError("invalid operation")
    plan=await _bounded(lambda:GameCorpus(_path(scope=scope)).capture_plan(scope,game,source,observation_digest))
    # No additional host, crawl depth or authorization derives from feed text.
    # The existing application's admission and per-request network checks apply.
    await crawler_application._grant_principal(scope,{"principal_email":principal["email"].strip().lower()})
    binding=digest([game,source,observation_digest,operation,autonomous])
    body={"title":plan["title"][:160],"seeds":[plan["url"]],"topics":[],
          "max_depth":0,"max_requests":4,"max_documents":1,"max_bytes":2*1024*1024,
          "discover_sitemaps":False,"frontier_strategy":"fifo",
          "consent":True,"rights_acknowledged":True,"idempotency_key":"game-capture:"+binding}
    session=await crawler_application.create(scope,body)
    identifier=session["session_id"]
    await _bounded(lambda:GameCorpus(_path(scope=scope)).bind_capture(scope,game=game,source=source,
                            observation_digest=observation_digest,session=identifier))
    from core.dragon_game_routing import publish_route
    await publish_route(crawler_application,scope,identifier)
    if autonomous:
        row=await crawler_application._owned(scope,identifier)
        # Never renew/re-enable on replay, after any intervening operation, or
        # after a user revokes automation. Initial version is the only grant.
        if row["version"]==1 and row["status"]=="queued" and not row.get("automation"):
            await _bounded(lambda:GameCorpus(_path(scope=scope)).capture_plan(scope,game,source,observation_digest))
            await crawler_application.automation(scope,identifier,{"enabled":True,"expected_version":1,
                "max_slices":8,"max_seconds":900,"idempotency_key":"game-auto:"+binding},principal=principal)
            session=await crawler_application.get(scope,identifier)
    return {"session":session,"game_id":game,"source_id":source,"observation_digest":observation_digest,
            "network_executed":False,"canonical_scheduler":bool(autonomous),
            "source_is_reviewed":False,"wiki_approved":False,"archive_rights_extended":False}


async def game_session_ids(scope,game):
    """Bound only a query's routing set, never permission to use these sessions."""
    page=await _bounded(lambda:GameCorpus(_path(scope=scope)).capture_sessions(scope,game,limit=100))
    return [r["session_id"] for r in page["captures"]],page["next_cursor"] is not None


async def game_context(scope,query,max_docs,max_chars,*,game,historical):
    from core.dragon_crawler import crawler_application
    session_ids,truncated=await game_session_ids(scope,game)
    if historical:
        value=await crawler_application.history_context(scope,query,max_docs,max_chars,session_ids=session_ids,game_id=game)
    else:
        value=await crawler_application.context(scope,query,max_docs,max_chars,session_ids=session_ids,game_id=game)
    return {**value,"game_id":game,"legacy_capture_window_truncated":truncated,"indexed_game_routing":True,
            "partial_routing":True}

async def world_discovery_call(scope,operation,*args,**kwargs):
    from core.dragon_world_discovery import WorldDiscovery,DiscoveryHeld
    if operation not in {"configure","revoke","status"}:
        raise ValueError("discovery operation")
    def work():
        path=_path(create=operation=="configure" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
        try:
            return getattr(WorldDiscovery(path),operation)(scope,*args,**kwargs)
        except DiscoveryHeld as exc:
            raise CatalogueHeld("discovery subscription held") from exc
    return await _bounded(work)


async def pulse_world_discovery():
    from core.dragon_world_discovery import WorldDiscovery
    if os.getenv("SKL_DRAGON_WORLD_DISCOVERY")!="1":
        return {"enabled":False,"network_executed":False}
    try:
        return await _bounded(lambda:WorldDiscovery(_path(),owner_route=lambda scope:_path(scope=scope)).pulse())
    except (GameLearningError,CatalogueHeld,sqlite3.Error,OSError,TimeoutError,ValueError,RuntimeError):
        return {"enabled":True,"outcome":"held"}


async def pulse_media_archive():
    from core.dragon_hoarder_copy import configured,_io
    if not configured():
        return {"configured":False}
    from core.dragon_media_archive import MediaArchive
    try:
        return await _io(lambda:MediaArchive(path=_maintenance_path("media")).cleanup())
    except (OSError,TimeoutError,ValueError,RuntimeError,sqlite3.Error,GameLearningError):
        return {"configured":True,"held":True}


async def pulse_game_datasets():
    if not os.getenv("SKL_DRAGON_DATASET_ROOT","").strip():
        return {"configured":False}
    from core.dragon_game_datasets import sweep_dataset_shard
    try:
        return await _bounded(lambda:sweep_dataset_shard(_path()))
    except (GameLearningError,CatalogueHeld,sqlite3.Error,OSError,TimeoutError,ValueError,RuntimeError):
        return {"configured":True,"held":True}


def _pulse_graph_root(path):
    """Run one isolated local owner-root's bounded maintenance batch."""
    from core.dragon_lead_graph import LeadGraph
    from core.dragon_graph_structural import configured,status,recover
    from core.dragon_owner_shards import ShardHeld
    from core.dragon_graph_authority import GraphHeld
    graph=LeadGraph(path);results={}
    try:
        if configured(graph.path) and status(graph.path)["state"]=="pending":
            try:results["structural_recovery"]=recover(graph.path)
            except (CatalogueHeld,ValueError,sqlite3.Error,OSError,GraphHeld,ShardHeld):
                return {"structural_recovery":{"held":True},"network_executed":False}
        for key,operation in (("bootstrap",graph.bootstrap_pulse),("catalogue",graph.catalogue_pulse),
                              ("bundle",graph.bundle_pulse),("expansion",graph.expansion_pulse)):
            try:results[key]=operation()
            except (CatalogueHeld,ValueError,sqlite3.Error,OSError,GraphHeld,ShardHeld):
                results[key]={"held":True,"reason":"lead_maintenance_held","network_executed":False}
        canonical_lanes=graph.authority_mode()
        if not canonical_lanes and os.getenv("SKL_DRAGON_LEAD_INDEX_ROOT","").strip():
            from core.dragon_lead_index_shards import pulse,IndexHeld
            try:results["physical_index"]=pulse(graph)
            except (IndexHeld,ShardHeld,ValueError,sqlite3.Error,OSError):
                results["physical_index"]={"held":True,"network_executed":False}
        if not canonical_lanes and os.getenv("SKL_DRAGON_LEAD_EDGE_ROOT","").strip():
            from core.dragon_lead_edge_shards import pulse,EdgeHeld
            try:results["physical_edges"]=pulse(graph)
            except (EdgeHeld,ShardHeld,ValueError,sqlite3.Error,OSError):
                results["physical_edges"]={"held":True,"network_executed":False}
    except (CatalogueHeld,ValueError,sqlite3.Error,OSError,GraphHeld,ShardHeld):
        results["held"]=True
        results["reason"]="lead_store_unavailable"
    return {**results,"network_executed":False}


def _pulse_graph_roots(base,*,count=2):
    from concurrent.futures import ThreadPoolExecutor
    from core.dragon_owner_shards import next_paths,ShardHeld
    try:ready,held=next_paths(base,"corpus","leads",count=count)
    except ShardHeld as exc:raise CatalogueHeld("corpus maintenance topology held") from exc
    outcomes=[{"lane":i,"held":True,"reason":"owner_root_unavailable","network_executed":False} for i in held]
    def work(item):
        i,path=item
        return {"lane":i,**_pulse_graph_root(path)}
    if ready:
        with ThreadPoolExecutor(max_workers=min(2,len(ready)),thread_name_prefix="dragon-owner-root") as pool:
            outcomes.extend(pool.map(work,ready))
    # Preserve original top-level result for the unsharded application.
    if len(outcomes)==1 and not held:
        return {**outcomes[0],"owner_root_batches":1}
    return {"owner_root_batches":len(ready),"held_roots":len(held),
            "roots":sorted(outcomes,key=lambda row:row["lane"]),"network_executed":False}


async def pulse_lead_graph():
    """Run at most two independent owner-root batches per maintenance pulse."""
    if not os.getenv("SKL_DRAGON_GAME_CORPUS_DB_PATH","").strip():
        return {"configured":False,"network_executed":False}
    try:
        return await _bounded(lambda:_pulse_graph_roots(_path()))
    except (GameLearningError,CatalogueHeld,sqlite3.Error,OSError,TimeoutError):
        return {"held":True,"reason":"lead_store_unavailable","network_executed":False}


async def lead_graph_call(scope,operation,*args,**kwargs):
    from core.dragon_lead_graph import LeadGraph
    if operation not in {"configure","status","page","edges","begin","snapshot","append","seal","revoke","review","review_batch","dataset_candidates","register_target","bundle_status","enable_bundle"}:
        raise ValueError("lead graph operation")
    def work():
        path=_path(scope=scope,create=operation=="configure" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
        return getattr(LeadGraph(path),operation)(scope,*args,**kwargs)
    return await _bounded(work)
