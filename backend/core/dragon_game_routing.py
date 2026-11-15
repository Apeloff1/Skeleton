"""Cross-store game routing projection: exact receipt, never source authority.

A capture mapping does not imply it may be read or archived. Catalogue and
canonical Mongo session are joined by exact owner, session and canonical seed.
The projection permits indexed game-wide historical queries instead of a
recent-100-session routing cap.
"""
from __future__ import annotations

from core.dragon_game_corpus import GameCorpus,_id,digest
from core.dragon_hoarder_bulk import owner_key
from skeleton.ai.webcrawler.core import canonicalize_url

SCHEMA="dragon.game-route.v1"


def marker(scope,row,binding):
    if owner_key(scope)!=binding["owner"] or row["_id"]!=binding["session_id"]:
        raise ValueError("game route scope")
    if row["status"] in {"deleted","cancelled"}:
        raise ValueError("game route unavailable")
    seeds=row["request"]["seed_urls"]
    if (not isinstance(seeds,list) or len(seeds)!=1
            or canonicalize_url(seeds[0])!=canonicalize_url(binding["url"])):
        raise ValueError("game route seed differs")
    return {"schema":SCHEMA,"game_id":_id(binding["game_id"]),"source_id":_id(binding["source_id"]),
            "observation_digest":_id(binding["observation_digest"]),
            "binding_digest":digest([owner_key(scope),row["_id"],binding["game_id"],binding["source_id"],
                                    binding["observation_digest"],canonicalize_url(binding["url"])])}


def binding_for(path,scope,session):
    store=GameCorpus(path)
    owner=owner_key(scope)
    with store._db() as db:
        row=db.execute("""SELECT b.owner,b.session AS session_id,b.game AS game_id,b.source AS source_id,
            b.observation_digest,s.url FROM capture_bindings b JOIN sources s
            ON b.owner=s.owner AND b.game=s.game AND b.source=s.id
            WHERE b.owner=? AND b.session=?""",(owner,session)).fetchone()
    return dict(row) if row else None


async def publish_route(app,scope,session):
    from core.dragon_corpus_runtime import _bounded,_path
    from core.dragon_crawler import _now
    row=await app.sessions.find_one({**scope,"_id":session,"status":{"$nin":["deleted","cancelled"]}},
        {"_id":1,"version":1,"status":1,"request.seed_urls":1,"game_route":1},max_time_ms=2000)
    if not row:return False
    binding=await _bounded(lambda:binding_for(_path(scope=scope),scope,session))
    if not binding:return False
    value=marker(scope,row,binding)
    if row.get("game_route")==value:return True
    if row.get("game_route") is not None:raise ValueError("game route conflict")
    # This projection only affects candidate routing. No source grant/consent
    # changes and no version bump; current and historical exact pins remain.
    result=await app.sessions.update_one({**scope,"_id":session,"version":row["version"],
        "status":{"$nin":["deleted","cancelled"]},"game_route":{"$exists":False}},
        {"$set":{"game_route":value,"deep_full_due":_now().timestamp(),"current_vector_due":_now().timestamp()},
         "$unset":{"deep_full_state":"","current_vector_state":""}})
    return bool(result.modified_count)


async def verify_game_candidates(scope,game,session_ids):
    """Bounded independent SQLite join for selected evidence, never recent-only."""
    from core.dragon_corpus_runtime import _bounded,_path
    if not isinstance(session_ids,list) or len(session_ids)>100:
        raise ValueError("game candidate bound")
    game=_id(game)
    def work():
        result=[]
        with GameCorpus(_path(scope=scope))._db() as db:
            for session in set(session_ids):
                found=db.execute("SELECT 1 FROM capture_bindings WHERE owner=? AND game=? AND session=?",
                                 (owner_key(scope),game,session)).fetchone()
                if found:result.append(session)
        return set(result)
    return await _bounded(work)


async def backfill_routes(app):
    """Incremental scan, with finite retries across scheduler restarts."""
    from core.dragon_crawler import _now
    from core.dragon_corpus_runtime import _path
    import os
    if not os.getenv("SKL_DRAGON_GAME_CORPUS_DB_PATH","").strip():
        return {"configured":False}
    _path()
    await app.ensure_indexes()
    now=_now().timestamp()
    query={"status":{"$nin":["deleted","cancelled"]},"game_route":{"$exists":False},
           "$or":[{"game_route_retry":{"$exists":False}},{"game_route_retry":{"$lte":now}}]}
    rows=await app.sessions.find(query,{"_id":1,"version":1,"tenant_id":1,"owner_id":1}
        ).sort([("game_route_retry",1),("_id",1)]).limit(16).max_time_ms(2000).to_list(16)
    totals={"configured":True,"scanned":len(rows),"bound":0,"held":0}
    for item in rows:
        scope={k:item[k] for k in ("tenant_id","owner_id")}
        try:
            if await publish_route(app,scope,item["_id"]):
                totals["bound"]+=1;continue
        except (ValueError,LookupError,TypeError,KeyError,RuntimeError,TimeoutError,OSError):
            pass
        totals["held"]+=1
        await app.sessions.update_one({**scope,"_id":item["_id"],"version":item["version"],"game_route":{"$exists":False}},
            {"$set":{"game_route_retry":now+86400}})
    return totals
