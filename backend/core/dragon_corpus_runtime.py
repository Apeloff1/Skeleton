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


def _path(*,create=False):
    from core import dragon_runtime as runtime
    path=runtime._path("SKL_DRAGON_GAME_CORPUS_DB_PATH",create=create)
    for variable in ("SKL_DRAGON_KNOWLEDGE_DB_PATH","SKL_DRAGON_PRACTICE_DB_PATH"):
        raw=os.getenv(variable,"").strip()
        if raw:
            other=Path(raw).expanduser()
            if other.exists() and path.samefile(other):
                raise GameLearningError("dragon_storage_invalid","Game corpus requires a separate store.",503)
    return path


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
        path=_path(create=operation=="enqueue" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
        return getattr(ReleaseQueue(path),operation)(scope,*args,**kwargs)
    return await _bounded(work)


async def pulse_release_imports():
    if not os.getenv("SKL_DRAGON_GAME_CORPUS_DB_PATH","").strip():
        return {"configured":False,"network_executed":False}
    try:
        def pulse():
            path=_path()
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
    except (GameLearningError,sqlite3.Error,OSError,TimeoutError):
        return {"failed":True,"reason":"release_store_held","network_executed":False}


async def dispatch_capture(scope,principal,*,game,source,observation_digest,operation,
                           capture_rights_acknowledged,consent,autonomous=False):
    from core.dragon_crawler import authenticated_scope,crawler_application,CrawlerError
    if (authenticated_scope(principal)!=scope or principal.get("role") not in {"editor","admin"}
            or capture_rights_acknowledged is not True or consent is not True or type(autonomous) is not bool):
        raise CrawlerError("crawler_consent_required","Explicit current editor capture rights required.",403)
    if not isinstance(operation,str) or not 1<=len(operation)<=128 or operation.strip()!=operation:
        raise ValueError("invalid operation")
    plan=await _bounded(lambda:GameCorpus(_path()).capture_plan(scope,game,source,observation_digest))
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
    await _bounded(lambda:GameCorpus(_path()).bind_capture(scope,game=game,source=source,
                            observation_digest=observation_digest,session=identifier))
    if autonomous:
        row=await crawler_application._owned(scope,identifier)
        # Never renew/re-enable on replay, after any intervening operation, or
        # after a user revokes automation. Initial version is the only grant.
        if row["version"]==1 and row["status"]=="queued" and not row.get("automation"):
            await _bounded(lambda:GameCorpus(_path()).capture_plan(scope,game,source,observation_digest))
            await crawler_application.automation(scope,identifier,{"enabled":True,"expected_version":1,
                "max_slices":8,"max_seconds":900,"idempotency_key":"game-auto:"+binding},principal=principal)
            session=await crawler_application.get(scope,identifier)
    return {"session":session,"game_id":game,"source_id":source,"observation_digest":observation_digest,
            "network_executed":False,"canonical_scheduler":bool(autonomous),
            "source_is_reviewed":False,"wiki_approved":False,"archive_rights_extended":False}


async def game_session_ids(scope,game):
    """Bound only a query's routing set, never permission to use these sessions."""
    page=await _bounded(lambda:GameCorpus(_path()).capture_sessions(scope,game,limit=100))
    return [r["session_id"] for r in page["captures"]],page["next_cursor"] is not None


async def game_context(scope,query,max_docs,max_chars,*,game,historical):
    from core.dragon_crawler import crawler_application
    session_ids,truncated=await game_session_ids(scope,game)
    if not session_ids:
        return {"documents":[],"references":[],"game_catalogue_only":True,"partial_routing":False}
    if historical:
        value=await crawler_application.history_context(scope,query,max_docs,max_chars,session_ids=session_ids)
    else:
        value=await crawler_application.context(scope,query,max_docs,max_chars,session_ids=session_ids)
    return {**value,"game_id":game,"game_capture_window_truncated":truncated,
            "partial_routing":True}
