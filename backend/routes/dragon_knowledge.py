"""Typed knowledge/review operations mounted on the existing Academy router."""

from __future__ import annotations

from typing import Literal
import os

from fastapi import Depends, HTTPException, Query, Response, Request as HttpRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from core import dragon_runtime as runtime
from core.dragon_crawler import authenticated_scope
from core.game_learning import GameLearningError
from routes.gameforge_auth import get_current_user


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateRequest(Request):
    session_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    start: int = Field(ge=0, le=1_000_000, strict=True)
    end: int = Field(ge=1, le=1_000_000, strict=True)
    statement: str = Field(min_length=1, max_length=2048)
    mechanic: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(Request):
    expected_version: int = Field(ge=1, le=3, strict=True)
    decision: Literal["approve_design_reference", "reject"]
    rationale: str = Field(min_length=1, max_length=2048)
    rights_reference: str | None = Field(default=None, min_length=1, max_length=128)
    rights_acknowledged: StrictBool = False
    idempotency_key: str = Field(min_length=1, max_length=128)


class ResumeReviewRequest(Request):
    review_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class PracticeRequest(Request):
    expected_version: int = Field(ge=1, le=3, strict=True)
    seed: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)
    max_steps: int = Field(default=128, ge=16, le=512, strict=True)
    practice_consent: StrictBool
    idempotency_key: str = Field(min_length=1, max_length=128)


class GameObservationRequest(Request):
    namespace: str = Field(min_length=1, max_length=128)
    external_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    stage: Literal["announced", "early_access", "released", "updated", "delisted", "unknown"]
    source: str = Field(min_length=1, max_length=2048)
    kind: str = Field(min_length=1, max_length=32)
    language: str = Field(default="und", min_length=2, max_length=32)
    event_key: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=128)
    released_on: str | None = Field(default=None, min_length=10, max_length=10)


class ReleaseImportRequest(Request):
    adapter: Literal["manifest","steam","rss_atom"]
    payload: str = Field(min_length=1,max_length=2*1024*1024)
    operation: str = Field(min_length=1,max_length=128)
    provider: str | None = Field(default=None,max_length=32)
    external_id: str | None = Field(default=None,max_length=128)
    title: str | None = Field(default=None,max_length=256)


class GameCaptureRequest(Request):
    game: str = Field(min_length=64,max_length=64,pattern=r"^[0-9a-f]{64}$")
    source: str = Field(min_length=64,max_length=64,pattern=r"^[0-9a-f]{64}$")
    observation_digest: str = Field(min_length=64,max_length=64,pattern=r"^[0-9a-f]{64}$")
    operation: str = Field(min_length=1,max_length=128)
    capture_rights_acknowledged: StrictBool
    consent: StrictBool
    autonomous: StrictBool = False


class HoarderCopyRequest(Request):
    expected_version: int = Field(ge=1,strict=True)
    idempotency_key: str = Field(min_length=1,max_length=128)
    retention_acknowledged: StrictBool


class SourceViewPin(Request):
    session: str = Field(min_length=36,max_length=36)
    capture_source: str = Field(pattern=r"^[a-f0-9]{64}$")
    offset: int = Field(ge=0,le=24000,strict=True)
    length: int = Field(ge=1,le=4000,strict=True)
    session_version: int = Field(ge=1,strict=True)
    snapshot_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    preserved_text_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    history_only: StrictBool


class SourceComparisonRequest(Request):
    left: SourceViewPin
    right: SourceViewPin


class DiscoverySubscriptionRequest(Request):
    url: str = Field(min_length=1,max_length=2048)
    adapter: Literal["manifest","steam","rss_atom","sitemap","classified_sitemap","eve_sde"]
    provider: str | None = Field(default=None,max_length=32)
    external_id: str | None = Field(default=None,max_length=128)
    title: str | None = Field(default=None,max_length=256)
    interval_seconds: int = Field(default=3600,ge=900,le=604800,strict=True)
    grant_seconds: int = Field(default=86400,ge=900,le=2592000,strict=True)
    rights_acknowledged: StrictBool


class MediaBeginRequest(Request):
    game: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: str = Field(min_length=1,max_length=128)
    mime: Literal["video/mp4","video/webm","audio/mpeg","audio/ogg","audio/wav","image/png","image/jpeg","image/webp"]
    total_bytes: int = Field(ge=1,le=1073741824,strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_acknowledged: StrictBool
    grant_seconds: int = Field(ge=300,le=2592000,strict=True)


class ColdPrimaryRequest(Request):
    expected_version: int = Field(ge=1,strict=True)
    idempotency_key: str = Field(min_length=1,max_length=128)
    acknowledged: StrictBool


class ColdRestoreRequest(Request):
    expected_version: int = Field(ge=1,strict=True)


class DatasetBeginRequest(Request):
    dataset: str = Field(min_length=1,max_length=128)
    source: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: str = Field(min_length=1,max_length=128)
    expected_rows: int = Field(ge=1,le=100000000,strict=True)
    expected_chain: str = Field(pattern=r"^[0-9a-f]{64}$")
    grant_seconds: int = Field(ge=300,le=2592000,strict=True)
    rights_acknowledged: StrictBool


class SourceDirectoryImportRequest(Request):
    operation: str = Field(min_length=1,max_length=128)
    group: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    lead_ids: list[str] = Field(min_length=1,max_length=64)
    game: str | None = Field(default=None,pattern=r"^[0-9a-f]{64}$")
    use_preset: StrictBool = False
    acknowledged: StrictBool


class ModSeedApplicationsRequest(Request):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: str = Field(min_length=1,max_length=128)
    appids: list[str] = Field(min_length=1,max_length=128)
    mod_only: StrictBool = False
    acknowledged: StrictBool


class ModSeedSpecialistsRequest(Request):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: str = Field(min_length=1,max_length=128)
    game: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_ids: list[str] = Field(min_length=1,max_length=256)
    acknowledged: StrictBool


class LeadGraphConfiguration(Request):
    enabled: StrictBool
    acknowledged: StrictBool


class LeadBundleGrant(Request):
    rights_ref: str = Field(min_length=1,max_length=128)
    grant_seconds: int = Field(default=86400,ge=900,le=2592000,strict=True)
    acknowledged: StrictBool


class LeadDatasetBegin(Request):
    target_id: str = Field(min_length=1,max_length=64)
    projection: Literal["steam","modrinth","locator"]
    source_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_rows: int = Field(ge=1,le=100000000,strict=True)
    rights_ref: str = Field(min_length=1,max_length=128)
    grant_seconds: int = Field(ge=900,le=2592000,strict=True)
    acknowledged: StrictBool


class LeadDatasetSeal(Request):
    chain: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeadReview(Request):
    decision: Literal["candidate","held","retired"]
    reason: str = Field(min_length=1,max_length=512)
    operation: str = Field(min_length=1,max_length=128)
    interval_seconds: int = Field(default=604800,ge=900,le=7776000,strict=True)


class LeadTargetRegistration(Request):
    projection: Literal["steam","modrinth","locator"]
    rights_ref: str = Field(min_length=1,max_length=128)
    grant_seconds: int = Field(ge=900,le=2592000,strict=True)
    enabled: StrictBool
    acknowledged: StrictBool


def register_knowledge_routes(router):
    def scope(user):
        try:
            return authenticated_scope(user)
        except Exception as exc:
            raise HTTPException(
                getattr(exc, "status", 403),
                detail={
                    "code": getattr(exc, "code", "dragon_scope_invalid"),
                    "message": "Sign in to use Dragon knowledge.",
                },
            ) from exc

    def editor(user):
        value = scope(user)
        if user.get("role") not in {"editor", "admin"}:
            raise HTTPException(
                403,
                detail={
                    "code": "dragon_review_role_required",
                    "message": "Editor or administrator review is required.",
                },
            )
        return value

    async def call(operation):
        try:
            return await operation
        except GameLearningError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
        except (runtime.KnowledgeError, runtime.sqlite3.Error, LookupError) as exc:
            safe = runtime._error(exc)
            raise HTTPException(safe.status, detail={"code": safe.code, "message": safe.message}) from exc

    @router.get("/runtime/readiness")
    async def readiness(user: dict = Depends(get_current_user)):
        scope(user)
        return await call(runtime.runtime_readiness())

    @router.post("/knowledge/candidates")
    async def create(body: CandidateRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.create_candidate(scope(user), body.model_dump()))

    @router.get("/knowledge/candidates")
    async def candidates(
        state: Literal["pending_review", "approved", "rejected"] | None = None,
        cursor: str | None = Query(None, max_length=64),
        limit: int = Query(20, ge=1, le=20),
        user: dict = Depends(get_current_user),
    ):
        return await call(runtime.list_candidates(scope(user), state=state, cursor=cursor, limit=limit))

    @router.get("/knowledge/candidates/{candidate_id}")
    async def candidate(candidate_id: str, user: dict = Depends(get_current_user)):
        return await call(runtime.get_candidate(scope(user), candidate_id))

    @router.post("/knowledge/candidates/{candidate_id}/review")
    async def review(candidate_id: str, body: ReviewRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.review_candidate(editor(user), candidate_id, body.model_dump()))

    @router.get("/knowledge/hoag-archive")
    async def hoag_archive(q:str=Query(min_length=1,max_length=300),limit:int=Query(8,ge=1,le=8),
        cursor:str|None=Query(default=None,max_length=193),user:dict=Depends(get_current_user),
        game_catalogue:bool=Query(False)):
        from core.dragon_crawler import CrawlerError
        try:
            owner = scope(user)
            result = await call(runtime.search_hoag_archive(owner,q,limit,cursor))
            if game_catalogue:
                try:
                    hints = await corpus_call(owner, "search", q, limit=limit)
                except HTTPException as exc:
                    if exc.status_code != 503:
                        raise
                    result = {**result, "game_catalogue_state": "unavailable", "game_catalogue": None}
                else:
                    result = {**result, "game_catalogue_state": "available", "game_catalogue": hints,
                              "game_catalogue_is_evidence": False}
            return result
        except CrawlerError as exc:
            raise HTTPException(exc.status,detail={"code":exc.code,"message":exc.message}) from exc


    @router.get("/knowledge/search")
    async def search(
        q: str = Query(min_length=1, max_length=300),
        limit: int = Query(8, ge=1, le=8),
        user: dict = Depends(get_current_user),
    ):
        return await call(runtime.search_reviewed_references(scope(user), q, limit))

    @router.post("/knowledge/candidates/{candidate_id}/practice")
    async def practice(candidate_id: str, body: PracticeRequest, user: dict = Depends(get_current_user)):
        return await call(runtime.practice_candidate(scope(user), candidate_id, body.model_dump()))

    @router.get("/knowledge/candidates/{candidate_id}/practice")
    async def practices(
        candidate_id: str, limit: int = Query(20, ge=1, le=20), user: dict = Depends(get_current_user)
    ):
        return await call(runtime.practice_history(scope(user), candidate_id, limit))

    @router.get("/knowledge/candidates/{candidate_id}/practice/{practice_id}")
    async def practice_receipt(candidate_id: str, practice_id: str, user: dict = Depends(get_current_user)):
        return await call(runtime.inspect_reference_practice(scope(user), candidate_id, practice_id))

    @router.post("/knowledge/candidates/{candidate_id}/review/resume")
    async def resume_review(
        candidate_id: str, body: ResumeReviewRequest, user: dict = Depends(get_current_user)
    ):
        return await call(runtime.resume_review(editor(user), candidate_id, body.review_id))


    async def corpus_call(owner, operation, *args, **kwargs):
        from core.dragon_game_corpus import GameCorpus, CatalogueHeld

        def work():
            from core.dragon_corpus_runtime import _path
            path=_path(scope=owner,create=operation=="observe" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1")
            return getattr(GameCorpus(path), operation)(owner, *args, **kwargs)

        try:
            from core.dragon_corpus_runtime import _bounded
            return await _bounded(work)
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, detail={"code": "dragon_game_catalogue_invalid"}) from exc
        except CatalogueHeld as exc:
            raise HTTPException(409, detail={"code": "dragon_game_catalogue_held"}) from exc
        except GameLearningError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
        except (OSError, TimeoutError, runtime.sqlite3.Error) as exc:
            raise HTTPException(503, detail={"code": "dragon_game_catalogue_unavailable"}) from exc

    @router.post("/knowledge/game-corpus/observations")
    async def observe_game(body: GameObservationRequest, user: dict = Depends(get_current_user)):
        return await corpus_call(editor(user), "observe", **body.model_dump())

    @router.get("/knowledge/game-corpus/search")
    async def search_games(q: str = Query(min_length=1, max_length=256),
                           limit: int = Query(32, ge=1, le=100),
                           user: dict = Depends(get_current_user)):
        return await corpus_call(scope(user), "search", q, limit=limit)

    @router.get("/knowledge/game-corpus/due")
    async def due_sources(limit: int = Query(32, ge=1, le=100),
                          user: dict = Depends(get_current_user)):
        return await corpus_call(editor(user), "due", limit=limit)

    @router.get("/knowledge/game-corpus/{game_id}/sources")
    async def game_sources(game_id: str, after: str | None = Query(None, max_length=64),
                           limit: int = Query(64, ge=1, le=100),
                           kind: str | None = Query(None,max_length=32),
                           family: str | None = Query(None,max_length=32),
                           language: str | None = Query(None,max_length=32),
                           user: dict = Depends(get_current_user)):
        return await corpus_call(scope(user), "sources", game_id, after=after, limit=limit,kind=kind,family=family,language=language)

    @router.get("/knowledge/game-corpus/{game_id}/history")
    async def game_history(game_id: str, stamp: int | None = Query(None, ge=0),
                           source: str | None = Query(None, max_length=64),
                           event: str | None = Query(None, max_length=128),
                           limit: int = Query(32, ge=1, le=100),
                           user: dict = Depends(get_current_user)):
        cursor = (stamp, source, event)
        if any(x is not None for x in cursor) and any(x is None for x in cursor):
            raise HTTPException(422, detail={"code": "dragon_game_history_cursor_invalid"})
        return await corpus_call(scope(user), "history", game_id, limit=limit,
                                 before=cursor if stamp is not None else None)


    async def corpus_runtime_call(operation):
        from core.dragon_game_corpus import CatalogueHeld
        from core.dragon_crawler import CrawlerError
        try:
            return await operation
        except (CrawlerError, GameLearningError) as exc:
            raise HTTPException(exc.status,detail={"code":exc.code,"message":exc.message}) from exc
        except CatalogueHeld as exc:
            raise HTTPException(409,detail={"code":"dragon_game_catalogue_held"}) from exc
        except LookupError as exc:
            raise HTTPException(404,detail={"code":"dragon_release_import_missing"}) from exc
        except (ValueError,TypeError,OverflowError) as exc:
            raise HTTPException(422,detail={"code":"dragon_release_invalid"}) from exc
        except (OSError,TimeoutError,runtime.sqlite3.Error) as exc:
            raise HTTPException(503,detail={"code":"dragon_release_unavailable"}) from exc

    @router.post("/knowledge/game-corpus/release-imports")
    async def release_import(body: ReleaseImportRequest,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import release_call
        owner=editor(user)
        data=body.model_dump(exclude={"payload"})
        return await corpus_runtime_call(release_call(owner,"enqueue",raw=body.payload.encode("utf-8"),**data))

    @router.get("/knowledge/game-corpus/release-imports/{batch}")
    async def release_status(batch:str,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import release_call
        return await corpus_runtime_call(release_call(scope(user),"status",batch))

    @router.post("/knowledge/game-corpus/capture")
    async def game_capture(body: GameCaptureRequest,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import dispatch_capture
        owner=editor(user)
        return await corpus_runtime_call(dispatch_capture(owner,user,**body.model_dump()))


    @router.get("/knowledge/game-corpus/taxonomy")
    async def game_taxonomy(user:dict=Depends(get_current_user)):
        from core.dragon_game_taxonomy import public_taxonomy
        scope(user)
        return public_taxonomy()

    @router.get("/knowledge/game-corpus/timeline")
    async def game_timeline(stage:str|None=Query(None,max_length=32),
                            kind:str|None=Query(None,max_length=32),
                            language:str|None=Query(None,max_length=32),
                            current_only:bool=Query(False),
                            stamp:int|None=Query(None,ge=0),
                            game:str|None=Query(None,max_length=64),
                            source:str|None=Query(None,max_length=64),
                            event:str|None=Query(None,max_length=128),
                            limit:int=Query(32,ge=1,le=100),
                            user:dict=Depends(get_current_user)):
        cursor=(stamp,game,source,event)
        if any(x is not None for x in cursor) and any(x is None for x in cursor):
            raise HTTPException(422,detail={"code":"dragon_game_timeline_cursor_invalid"})
        return await corpus_call(scope(user),"release_timeline",stage=stage,kind=kind,
                                 language=language,current_only=current_only,limit=limit,
                                 before=cursor if stamp is not None else None)


    @router.post("/knowledge/hoarder-copy/{session_id}")
    async def hoarder_copy(session_id:str,body:HoarderCopyRequest,user:dict=Depends(get_current_user)):
        owner=editor(user)
        return await corpus_runtime_call(runtime.crawler_application.stage_bulk_copy(
            owner,session_id,body.model_dump(),principal=user))


    @router.get("/knowledge/game-corpus/{game_id}/sources/{source_id}/captures")
    async def source_captures(game_id:str,source_id:str,stamp:int|None=Query(None,ge=0),
                              session:str|None=Query(None,max_length=36),limit:int=Query(32,ge=1,le=100),
                              user:dict=Depends(get_current_user)):
        from core.dragon_source_library import source_capture_page
        if (stamp is None)!=(session is None):
            raise HTTPException(422,detail={"code":"dragon_source_cursor_invalid"})
        return await corpus_runtime_call(source_capture_page(scope(user),game_id,source_id,
                    before=(stamp,session) if stamp is not None else None,limit=limit))

    @router.get("/knowledge/game-corpus/{game_id}/sources/{source_id}/captures/{session}/documents")
    async def source_documents(game_id:str,source_id:str,session:str,response:Response,after:str|None=Query(None,max_length=64),
                               limit:int=Query(8,ge=1,le=8),user:dict=Depends(get_current_user)):
        from core.dragon_source_library import capture_documents
        response.headers['Cache-Control']='no-store'
        return await corpus_runtime_call(capture_documents(scope(user),game_id,source_id,session,after=after,limit=limit))

    @router.post("/knowledge/game-corpus/{game_id}/sources/{source_id}/view")
    async def source_view(game_id:str,source_id:str,body:SourceViewPin,response:Response,user:dict=Depends(get_current_user)):
        from core.dragon_source_library import read_document
        response.headers['Cache-Control']='no-store'
        return await corpus_runtime_call(read_document(scope(user),game_id,source_id,**body.model_dump()))

    @router.post("/knowledge/game-corpus/{game_id}/sources/{source_id}/compare")
    async def source_compare(game_id:str,source_id:str,body:SourceComparisonRequest,response:Response,user:dict=Depends(get_current_user)):
        from core.dragon_source_library import compare_documents
        response.headers['Cache-Control']='no-store'
        return await corpus_runtime_call(compare_documents(scope(user),game_id,source_id,
                    body.left.model_dump(),body.right.model_dump()))

    @router.get("/knowledge/game-corpus/source-search")
    async def source_search(q:str=Query(min_length=1,max_length=256),
                            kind:str|None=Query(None,max_length=32),
                            family:str|None=Query(None,max_length=32),
                            language:str|None=Query(None,max_length=32),
                            limit:int=Query(32,ge=1,le=100),
                            user:dict=Depends(get_current_user)):
        return await corpus_call(scope(user),"search_source_library",q,kind=kind,family=family,
                                 language=language,limit=limit)


    @router.post("/knowledge/game-corpus/discovery/subscriptions")
    async def discovery_subscribe(body:DiscoverySubscriptionRequest,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import world_discovery_call
        return await corpus_runtime_call(world_discovery_call(editor(user),"configure",**body.model_dump()))

    @router.get("/knowledge/game-corpus/discovery/subscriptions")
    async def discovery_subscriptions(after:str|None=Query(None,max_length=64),limit:int=Query(32,ge=1,le=100),
                                      user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import world_discovery_call
        return await corpus_runtime_call(world_discovery_call(editor(user),"status",after=after,limit=limit))

    @router.delete("/knowledge/game-corpus/discovery/subscriptions/{subscription_id}")
    async def discovery_revoke(subscription_id:str,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import world_discovery_call
        return await corpus_runtime_call(world_discovery_call(editor(user),"revoke",subscription_id))


    async def media_call(owner,op,*args,**kwargs):
        from core.dragon_media_archive import MediaArchive
        from core.dragon_corpus_runtime import _path as corpus_path
        from core.dragon_hoarder_copy import _io
        from core.dragon_hoarder_bulk import StorageHeld
        from core.dragon_game_corpus import CatalogueHeld
        if op not in {"begin","append","seal","list","metadata","part","revoke"}:
            raise HTTPException(422,detail={"code":"dragon_media_operation"})
        try:
            return await _io(lambda:getattr(MediaArchive(path=corpus_path(scope=owner)),op)(owner,*args,**kwargs))
        except (StorageHeld,CatalogueHeld) as exc:
            raise HTTPException(409,detail={"code":"dragon_media_storage_held"}) from exc
        except LookupError as exc:
            raise HTTPException(404,detail={"code":"dragon_media_unavailable"}) from exc
        except (ValueError,TypeError,KeyError) as exc:
            raise HTTPException(422,detail={"code":"dragon_media_invalid"}) from exc
        except (OSError,TimeoutError,runtime.sqlite3.Error,GameLearningError) as exc:
            raise HTTPException(503,detail={"code":"dragon_media_unconfigured"}) from exc

    @router.post("/knowledge/media")
    async def media_begin(body:MediaBeginRequest,user:dict=Depends(get_current_user)):
        return await media_call(editor(user),"begin",**body.model_dump())

    @router.put("/knowledge/media/{media_id}/chunks/{ordinal}")
    async def media_append(media_id:str,ordinal:int,request:HttpRequest,user:dict=Depends(get_current_user)):
        from core.dragon_hoarder_manifests import BLOCK
        owner=editor(user)
        if request.headers.get("content-type","").lower()!="application/octet-stream":
            raise HTTPException(415,detail={"code":"dragon_media_binary_required"})
        raw=bytearray()
        async for piece in request.stream():
            if len(raw)+len(piece)>BLOCK:
                raise HTTPException(413,detail={"code":"dragon_media_chunk_bound"})
            raw.extend(piece)
        return await media_call(owner,"append",media_id,ordinal,bytes(raw))

    @router.post("/knowledge/media/{media_id}/seal")
    async def media_seal(media_id:str,user:dict=Depends(get_current_user)):
        return await media_call(editor(user),"seal",media_id)

    @router.get("/knowledge/game-corpus/{game_id}/sources/{source_id}/media")
    async def media_list(game_id:str,source_id:str,after:str|None=Query(None,max_length=64),
                         user:dict=Depends(get_current_user)):
        return await media_call(scope(user),"list",game_id,source_id,after=after)

    @router.delete("/knowledge/media/{media_id}")
    async def media_revoke(media_id:str,user:dict=Depends(get_current_user)):
        return await media_call(editor(user),"revoke",media_id)

    @router.get("/knowledge/media/{media_id}/content")
    async def media_content(media_id:str,request:HttpRequest,user:dict=Depends(get_current_user)):
        from core.dragon_media_archive import byte_range
        from core.dragon_hoarder_manifests import BLOCK
        owner=scope(user)
        meta=await media_call(owner,"metadata",media_id)
        total=meta["total_bytes"]
        try:
            start,end,partial=byte_range(request.headers.get("range"),total)
        except ValueError as exc:
            raise HTTPException(416,headers={"Content-Range":f"bytes */{total}"},
                                detail={"code":"dragon_media_range_invalid"}) from exc
        # First block must qualify before response headers are committed.
        first=start//BLOCK
        first_data=await media_call(owner,"part",media_id,first)
        async def stream():
            for ordinal in range(first,end//BLOCK+1):
                if await request.is_disconnected():return
                raw=first_data if ordinal==first else await media_call(owner,"part",media_id,ordinal)
                lo=max(0,start-ordinal*BLOCK)
                hi=min(len(raw),end-ordinal*BLOCK+1)
                yield raw[lo:hi]
        headers={"Accept-Ranges":"bytes","Content-Length":str(end-start+1),
            "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff",
            "Content-Security-Policy":"default-src 'none'; sandbox",
            "Content-Disposition":"inline","Referrer-Policy":"no-referrer"}
        if partial:headers["Content-Range"]=f"bytes {start}-{end}/{total}"
        return StreamingResponse(stream(),status_code=206 if partial else 200,
                                 media_type=meta["mime"],headers=headers)


    @router.post("/knowledge/hoarder-primary/{session_id}/relocate")
    async def relocate_primary(session_id:str,body:ColdPrimaryRequest,user:dict=Depends(get_current_user)):
        from core.dragon_crawler import crawler_application
        from core.dragon_hoarder_bulk import StorageHeld
        try:
            return await corpus_runtime_call(crawler_application.relocate_cold_primary(
                editor(user),session_id,body.model_dump(),principal=user))
        except StorageHeld as exc:
            raise HTTPException(409,detail={"code":"dragon_cold_qualification_held"}) from exc

    @router.post("/knowledge/hoarder-primary/{session_id}/restore")
    async def restore_primary(session_id:str,body:ColdRestoreRequest,user:dict=Depends(get_current_user)):
        from core.dragon_crawler import crawler_application
        from core.dragon_hoarder_bulk import StorageHeld
        try:
            return await corpus_runtime_call(crawler_application.restore_cold_primary(
                editor(user),session_id,expected_version=body.expected_version))
        except StorageHeld as exc:
            raise HTTPException(409,detail={"code":"dragon_cold_restore_held"}) from exc


    async def dataset_call(owner,game,operation,*args,**kwargs):
        from core.dragon_game_datasets import DatasetShard
        from core.dragon_corpus_runtime import _bounded
        if operation not in {"begin","append","seal","query","edges","versions","revoke"}:
            raise HTTPException(422,detail={"code":"dragon_dataset_invalid"})
        return await corpus_runtime_call(_bounded(lambda:getattr(DatasetShard(owner,game,
            create=operation=="begin" and os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1"),operation)(*args,**kwargs)))

    @router.post("/knowledge/game-corpus/{game_id}/datasets")
    async def dataset_begin(game_id:str,body:DatasetBeginRequest,user:dict=Depends(get_current_user)):
        return await dataset_call(editor(user),game_id,"begin",**body.model_dump())

    @router.put("/knowledge/game-corpus/{game_id}/datasets/{version}/pages/{ordinal}")
    async def dataset_append(game_id:str,version:str,ordinal:int,request:HttpRequest,user:dict=Depends(get_current_user)):
        from core.dragon_game_datasets import MAX_PAGE
        owner=editor(user)
        if request.headers.get("content-type","").lower() not in {"application/x-ndjson","application/jsonl"}:
            raise HTTPException(415,detail={"code":"dragon_dataset_jsonl_required"})
        content=bytearray()
        async for piece in request.stream():
            if len(content)+len(piece)>MAX_PAGE:raise HTTPException(413,detail={"code":"dragon_dataset_page_bound"})
            content.extend(piece)
        return await dataset_call(owner,game_id,"append",version,ordinal,bytes(content))

    @router.post("/knowledge/game-corpus/{game_id}/datasets/{version}/seal")
    async def dataset_seal(game_id:str,version:str,user:dict=Depends(get_current_user)):
        return await dataset_call(editor(user),game_id,"seal",version)

    @router.get("/knowledge/game-corpus/{game_id}/datasets")
    async def dataset_versions(game_id:str,response:Response,after:str|None=Query(None,max_length=64),
                                user:dict=Depends(get_current_user)):
        response.headers["Cache-Control"]="no-store"
        return await dataset_call(scope(user),game_id,"versions",after=after)

    @router.get("/knowledge/game-corpus/{game_id}/datasets/{version}/records")
    async def dataset_records(game_id:str,version:str,response:Response,q:str|None=Query(None,max_length=256),
                              after:str|None=Query(None,max_length=128),limit:int=Query(16,ge=1,le=32),
                              user:dict=Depends(get_current_user)):
        response.headers["Cache-Control"]="no-store"
        return await dataset_call(scope(user),game_id,"query",version,q=q,after=after,limit=limit)

    @router.get("/knowledge/game-corpus/{game_id}/datasets/{version}/relations/{record}")
    async def dataset_relations(game_id:str,version:str,record:str,response:Response,reverse:bool=Query(False),
                                user:dict=Depends(get_current_user)):
        response.headers["Cache-Control"]="no-store"
        return await dataset_call(scope(user),game_id,"edges",version,record,reverse=reverse)

    @router.delete("/knowledge/game-corpus/{game_id}/datasets/{version}")
    async def dataset_revoke(game_id:str,version:str,user:dict=Depends(get_current_user)):
        return await dataset_call(editor(user),game_id,"revoke",version)


    @router.get("/knowledge/media/{media_id}/metadata")
    async def media_metadata(media_id:str,response:Response,user:dict=Depends(get_current_user)):
        response.headers["Cache-Control"]="private, no-store"
        return await media_call(scope(user),"metadata",media_id)

    @router.get("/knowledge/game-corpus/design-profiles")
    async def design_profiles(user:dict=Depends(get_current_user)):
        from core.dragon_ecosystem_profiles import public_profiles
        scope(user)
        return public_profiles()

    @router.post("/knowledge/game-corpus/design-profiles/{profile}")
    async def import_design_profile(profile:str,operation:str=Query(min_length=1,max_length=128),
                                    user:dict=Depends(get_current_user)):
        from core.dragon_ecosystem_profiles import manifest
        from core.dragon_corpus_runtime import release_call
        owner=editor(user)
        try:
            payload=manifest(profile)
        except ValueError as exc:
            raise HTTPException(422,detail={"code":"dragon_profile_unknown"}) from exc
        return await corpus_runtime_call(release_call(owner,"enqueue",raw=payload,
                    adapter="manifest",operation=operation))


    @router.get("/knowledge/game-corpus/source-directory")
    async def source_directory_summary(user:dict=Depends(get_current_user)):
        from core.dragon_source_directory import summary
        from core.dragon_corpus_runtime import _bounded
        scope(user)
        return await corpus_runtime_call(_bounded(summary))

    @router.get("/knowledge/game-corpus/source-directory/leads")
    async def source_directory_leads(group:str|None=Query(None,max_length=64),
            domain:str|None=Query(None,max_length=64),family:str|None=Query(None,max_length=32),
            kind:str|None=Query(None,max_length=32),q:str|None=Query(None,max_length=256),
            after:str|None=Query(None,max_length=129),limit:int=Query(32,ge=1,le=100),
            user:dict=Depends(get_current_user)):
        from core.dragon_source_directory import page
        from core.dragon_corpus_runtime import _bounded
        scope(user)
        return await corpus_runtime_call(_bounded(lambda:page(group=group,domain=domain,
            family=family,kind=kind,q=q,after=after,limit=limit)))

    @router.post("/knowledge/game-corpus/source-directory/import")
    async def source_directory_import(body:SourceDirectoryImportRequest,user:dict=Depends(get_current_user)):
        from core.dragon_source_directory import enqueue
        from core.dragon_corpus_runtime import _bounded,_path
        owner=editor(user)
        return await corpus_runtime_call(_bounded(lambda:enqueue(
            _path(scope=owner,create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1"),owner,**body.model_dump())))


    @router.get("/knowledge/game-corpus/mod-seeds")
    async def mod_seed_summary(user:dict=Depends(get_current_user)):
        from core.dragon_mod_seed_catalogue import summary
        from core.dragon_corpus_runtime import _bounded
        scope(user)
        return await corpus_runtime_call(_bounded(summary))

    @router.get("/knowledge/game-corpus/mod-seeds/locators")
    async def mod_seed_locators(response:Response,lane:str|None=Query(None,max_length=32),
            group:str|None=Query(None,max_length=64),provider:str|None=Query(None,max_length=32),
            family:str|None=Query(None,max_length=32),kind:str|None=Query(None,max_length=32),
            appid:str|None=Query(None,max_length=12),q:str|None=Query(None,max_length=256),
            mod_only:bool=False,after:str|None=Query(None,max_length=129),limit:int=Query(32,ge=1,le=100),
            user:dict=Depends(get_current_user)):
        from core.dragon_mod_seed_catalogue import page
        from core.dragon_corpus_runtime import _bounded
        scope(user);response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(_bounded(lambda:page(lane=lane,group=group,provider=provider,
            family=family,kind=kind,appid=appid,q=q,mod_only=mod_only,after=after,limit=limit)))

    @router.get("/knowledge/game-corpus/mod-seeds/applications")
    async def mod_seed_applications(response:Response,group:str|None=Query(None,max_length=64),
            q:str|None=Query(None,max_length=256),after:str|None=Query(None,max_length=129),
            limit:int=Query(32,ge=1,le=100),user:dict=Depends(get_current_user)):
        from core.dragon_mod_seed_catalogue import applications
        from core.dragon_corpus_runtime import _bounded
        scope(user);response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(_bounded(lambda:applications(group=group,q=q,after=after,limit=limit)))

    @router.post("/knowledge/game-corpus/mod-seeds/import-applications")
    async def mod_seed_import_apps(body:ModSeedApplicationsRequest,user:dict=Depends(get_current_user)):
        from core.dragon_mod_seed_catalogue import import_applications
        from core.dragon_corpus_runtime import _bounded,_path
        owner=editor(user)
        return await corpus_runtime_call(_bounded(lambda:import_applications(
            _path(scope=owner,create=os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP")=="1"),owner,**body.model_dump())))

    @router.post("/knowledge/game-corpus/mod-seeds/attach")
    async def mod_seed_attach(body:ModSeedSpecialistsRequest,user:dict=Depends(get_current_user)):
        from core.dragon_mod_seed_catalogue import attach_specialists
        from core.dragon_corpus_runtime import _bounded,_path
        owner=editor(user)
        return await corpus_runtime_call(_bounded(lambda:attach_specialists(
            _path(scope=owner,create=False),owner,**body.model_dump())))


    @router.get("/knowledge/game-corpus/dataset-library")
    async def dataset_library(response:Response,domain:str|None=Query(None,max_length=32),
            access:str|None=Query(None,max_length=32),q:str|None=Query(None,max_length=256),
            after:str|None=Query(None,max_length=129),limit:int=Query(32,ge=1,le=100),
            user:dict=Depends(get_current_user)):
        from core.dragon_dataset_library import library
        from core.dragon_corpus_runtime import _bounded
        scope(user);response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(_bounded(lambda:library(domain=domain,access=access,q=q,after=after,limit=limit)))

    @router.get("/knowledge/game-corpus/lead-graph")
    async def lead_graph_status(response:Response,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"status"))

    @router.post("/knowledge/game-corpus/lead-graph/configure")
    async def lead_graph_configure(body:LeadGraphConfiguration,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"configure",**body.model_dump()))

    @router.get("/knowledge/game-corpus/lead-graph/leads")
    async def lead_graph_page(response:Response,q:str|None=Query(None,max_length=256),
            family:str|None=Query(None,max_length=32),host:str|None=Query(None,max_length=253),
            state:Literal["candidate","held","retired"]="candidate",due_only:bool=False,
            after:str|None=Query(None,max_length=129),limit:int=Query(32,ge=1,le=100),
            user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"page",q=q,family=family,host=host,
            state=state,due_only=due_only,after=after,limit=limit))

    @router.get("/knowledge/game-corpus/lead-graph/leads/{lead}/edges")
    async def lead_graph_edges(lead:str,response:Response,direction:Literal["parents","children"]="children",
            after:str|None=Query(None,max_length=64),limit:int=Query(32,ge=1,le=100),
            user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"edges",lead,direction=direction,after=after,limit=limit))

    @router.post("/knowledge/game-corpus/lead-graph/leads/{lead}/review")
    async def lead_graph_review(lead:str,body:LeadReview,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"review",lead,**body.model_dump()))

    @router.get("/knowledge/game-corpus/lead-graph/dataset-candidates")
    async def lead_dataset_candidates(response:Response,after:str|None=Query(None,max_length=64),
            limit:int=Query(32,ge=1,le=100),user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"dataset_candidates",after=after,limit=limit))

    @router.post("/knowledge/game-corpus/lead-graph/dataset-candidates/{lead}")
    async def lead_dataset_register(lead:str,body:LeadTargetRegistration,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"register_target",lead,**body.model_dump()))

    @router.post("/knowledge/game-corpus/lead-graph/snapshots")
    async def lead_dataset_begin(body:LeadDatasetBegin,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"begin",**body.model_dump()))

    @router.get("/knowledge/game-corpus/lead-graph/snapshots/{snapshot}")
    async def lead_dataset_status(snapshot:str,response:Response,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"snapshot",snapshot))

    @router.put("/knowledge/game-corpus/lead-graph/snapshots/{snapshot}/pages/{ordinal}")
    async def lead_dataset_append(snapshot:str,ordinal:int,request:HttpRequest,
            sha256:str=Query(pattern=r"^[0-9a-f]{64}$"),previous_chain:str=Query(pattern=r"^[0-9a-f]{64}$"),
            user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        from core.dragon_lead_graph import MAX_PAGE_BYTES
        owner=editor(user)
        if request.headers.get("content-type","").split(";")[0].strip().lower() not in {"application/x-ndjson","application/octet-stream"}:
            raise HTTPException(415,detail={"code":"dragon_lead_page_content_type"})
        # Bound the streaming body before allocating the next chunk.
        raw=bytearray()
        async for block in request.stream():
            if len(block)>MAX_PAGE_BYTES-len(raw):
                raise HTTPException(413,detail={"code":"dragon_lead_page_bound"})
            raw.extend(block)
        return await corpus_runtime_call(lead_graph_call(owner,"append",snapshot,ordinal=ordinal,
            raw=bytes(raw),sha256=sha256,previous_chain=previous_chain))

    @router.post("/knowledge/game-corpus/lead-graph/snapshots/{snapshot}/seal")
    async def lead_dataset_seal(snapshot:str,body:LeadDatasetSeal,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"seal",snapshot,body.chain))

    @router.delete("/knowledge/game-corpus/lead-graph/snapshots/{snapshot}")
    async def lead_dataset_revoke(snapshot:str,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"revoke",snapshot))


    @router.get("/knowledge/game-corpus/lead-graph/bundle")
    async def lead_bundle_status(response:Response,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        response.headers["Cache-Control"]="private, no-store"
        return await corpus_runtime_call(lead_graph_call(scope(user),"bundle_status"))

    @router.post("/knowledge/game-corpus/lead-graph/bundle/enable")
    async def lead_bundle_enable(body:LeadBundleGrant,user:dict=Depends(get_current_user)):
        from core.dragon_corpus_runtime import lead_graph_call
        return await corpus_runtime_call(lead_graph_call(editor(user),"enable_bundle",**body.model_dump()))
