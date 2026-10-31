"""Private project admission over the existing playable Mongo authority.

The request principal is retained across the existing background tasks. Collection
adapters preserve the shared Mongo database and enforce the same scope on every
operation; absent request/job authority never means installation-wide access.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute

from routes import gameforge_auth as auth
from routes.playable_htmlutils import model_review_projection, playable_html_digest


@dataclass(frozen=True)
class _Access:
    principal: dict
    token: str | None
    identity: dict[str, str]
    project_ids: tuple[str, ...] = ()
    sources: tuple[tuple[str, str, str], ...] = ()


_current: ContextVar[_Access | None] = ContextVar("private_playable_access", default=None)
_PROJECT_KEYS = frozenset({"pid", "game_id", "playable_id", "parent_pid", "parent_id", "project_id", "opponent_id", "winner_id", "forged_from"})
_PROJECT_LIST_KEYS = frozenset({"pids", "game_ids", "playable_ids"})
_RESERVED = frozenset({"tenant_id", "owner_id"})
_LIFECYCLE_KEYS = frozenset({"deleted", "revoked", "rights_revoked", "state"})


def _raw_database():
    import os
    from core.databases import client

    return client[os.environ.get("DB_NAME", "test_database")]


def _access() -> _Access:
    access = _current.get()
    if access is None:
        raise HTTPException(401, "Authentication required")
    return access


def project_identity() -> dict[str, str]:
    return dict(_access().identity)


def project_principal() -> dict:
    return dict(_access().principal)


def _editor(user):
    if user.get("role") not in {"editor", "admin"}:
        raise HTTPException(403, "Editor authority required")


def reauthorize_project_principal(*, mutate: bool = False, sources: bool = False) -> dict[str, str]:
    """Recheck the captured canonical token/account without async Mongo handles."""
    access = _access()
    user = auth.get_current_user(access.token)
    identity = auth.require_authenticated_identity(user)
    if identity != access.identity or user.get("disabled"):
        raise HTTPException(403, "Project account authority changed")
    if mutate:
        _editor(user)
    if sources:
        import os
        from core.databases import get_sync_db

        # The legacy playable authority uses this same database selection for
        # async reads. The core factory's different fallback cannot redirect a
        # background recheck to another database on an unconfigured install.
        database = get_sync_db(os.environ.get("DB_NAME", "test_database"))
        for pid in access.project_ids:
            row = database.playables.find_one({"playable_id": pid, **identity})
            if not _available(row, identity) or row.get("playable_id") != pid:
                raise HTTPException(404, "Game not found")
        for collection, key, value in access.sources:
            row = database[collection].find_one({key: value, **identity})
            if not _available(row, identity) or row.get(key) != value:
                raise HTTPException(404, "Project source not found")
    return dict(identity)


def _owned(row, identity) -> bool:
    return isinstance(row, dict) and all(row.get(key) == value for key, value in identity.items())


def _available(row, identity):
    return (_owned(row, identity) and row.get("deleted") is not True
            and row.get("revoked") is not True and row.get("rights_revoked") is not True
            and row.get("state") not in {"deleted", "revoked", "archived", "withdrawn"})


async def assert_project_access(pid: str, *, mutate: bool = False):
    identity = await asyncio.to_thread(reauthorize_project_principal, mutate=mutate)
    if not isinstance(pid, str) or not pid or len(pid) > 200 or pid != pid.strip():
        raise HTTPException(422, "Invalid project identity")
    row = await _raw_database().playables.find_one(
        {"playable_id": pid, **identity},
        {"_id": 0, "playable_id": 1, "owner_id": 1, "tenant_id": 1,
         "deleted": 1, "revoked": 1, "rights_revoked": 1, "state": 1},
    )
    if not _available(row, identity) or row.get("playable_id") != pid:
        raise HTTPException(404, "Game not found")
    access = _access()
    if pid not in access.project_ids:
        _current.set(_Access(access.principal, access.token, access.identity,
                             (*access.project_ids, pid), access.sources))
    return row


async def bind_project_id(pid: str, *, mutate: bool = False):
    return await assert_project_access(pid, mutate=mutate)


async def owned_galaxy_source(build_id: str):
    """Resolve current persisted Galaxy ownership before reading side signals."""
    identity = await reauthorize_project_context()
    row = await _raw_database().galaxy_builds.find_one({"build_id": build_id, **identity})
    if not _available(row, identity) or row.get("build_id") != build_id:
        return None
    await bind_project_source("galaxy_builds", "build_id", build_id)
    return row


async def reauthorize_project_context(*, mutate: bool = False) -> dict[str, str]:
    identity = await asyncio.to_thread(reauthorize_project_principal, mutate=mutate)
    for pid in _access().project_ids:
        await assert_project_access(pid, mutate=mutate)
    for collection, key, value in _access().sources:
        await _assert_source(collection, key, value, identity)
    return identity


async def _assert_source(collection, key, value, identity):
    row = await _raw_database()[collection].find_one({key: value, **identity})
    if not _available(row, identity) or row.get(key) != value:
        raise HTTPException(404, "Project source not found")
    return row


async def bind_project_source(collection: str, key: str, value: str):
    """Pin an existing owned spec/import/asset authority for later job rechecks."""
    if collection not in {"design_specs", "galaxy_builds", "galaxy_build_archive", "galaxy_vault",
                           "worldforge_worlds", "asset_genesis", "photoreal_images"}:
        raise HTTPException(403, "Unsupported project source authority")
    if not isinstance(key, str) or key.startswith("$") or not isinstance(value, str) or not value:
        raise HTTPException(422, "Invalid project source identity")
    identity = await reauthorize_project_context()
    row = await _assert_source(collection, key, value, identity)
    access = _access()
    source = (collection, key, value)
    if source not in access.sources:
        _current.set(_Access(access.principal, access.token, access.identity,
                             access.project_ids, (*access.sources, source)))
    return row


def _project_ids(values) -> set[str]:
    ids = set()
    if isinstance(values, dict):
        for key, value in values.items():
            if key in _PROJECT_KEYS and isinstance(value, str) and value:
                ids.add(value)
            elif key in _PROJECT_LIST_KEYS and isinstance(value, list):
                if any(not isinstance(item, str) or not item for item in value):
                    raise HTTPException(422, "Invalid project identities")
                ids.update(value)
    return ids


async def project_request_access(
    request: Request, response: Response,
    user=Depends(auth.get_current_user), token=Depends(auth.oauth2_scheme),
    *, local_jobs=False,
):
    identity = auth.require_authenticated_identity(user)
    mutate = request.method not in {"GET", "HEAD", "OPTIONS"}
    if mutate:
        _editor(user)
    access_token = _current.set(_Access(dict(user), token, identity))
    try:
        response.headers["Cache-Control"] = "private, no-store"
        ids = _project_ids(dict(request.path_params)) | _project_ids(dict(request.query_params))
        media_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if mutate and (not media_type or media_type == "application/json"
                       or media_type.startswith("application/") and media_type.endswith("+json")):
            try:
                body = await request.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                for key in _RESERVED:
                    if key in body and body[key] != identity[key]:
                        raise HTTPException(403, "Project owner mismatch")
                ids.update(_project_ids(body))
        for pid in ids:
            await assert_project_access(pid, mutate=mutate)
        # Jobs cannot become a second project authority. Resolve only this
        # account's existing job and recheck every source it names.
        job_id = request.path_params.get("job_id")
        if job_id and not local_jobs:
            database = _raw_database()
            row = await database.playable_jobs.find_one({"job_id": job_id, **identity})
            if not _available(row, identity):
                row = await database.groupchat_jobs.find_one({"job_id": job_id, **identity})
            if not _available(row, identity) or row.get("job_id") != job_id:
                raise HTTPException(404, "Job not found")
            ids.update(_project_ids(row))
            for pid in ids:
                await assert_project_access(pid, mutate=mutate)
        _current.set(_Access(dict(user), token, identity, tuple(sorted(ids))))
        yield
    finally:
        _current.reset(access_token)


class _PrivateProjectRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            response = await original(request)
            response.headers["Cache-Control"] = "private, no-store"
            return response
        return handler


def project_router(*args, **kwargs):
    local_jobs = kwargs.pop("local_jobs", False)
    project_aliases = kwargs.pop("project_aliases", ())

    async def admission(request: Request, response: Response,
                        user=Depends(auth.get_current_user), token=Depends(auth.oauth2_scheme)):
        async for value in project_request_access(request, response, user, token, local_jobs=local_jobs):
            for key in project_aliases:
                if request.path_params.get(key):
                    await assert_project_access(request.path_params[key], mutate=request.method not in {"GET", "HEAD", "OPTIONS"})
            yield value

    dependencies = list(kwargs.pop("dependencies", ()))
    dependencies.insert(0, Depends(admission))
    kwargs.setdefault("route_class", _PrivateProjectRoute)
    return APIRouter(*args, dependencies=dependencies, **kwargs)


def _query(query=None) -> dict:
    identity = project_identity()
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise HTTPException(422, "Project query must be an object")
    for key in _RESERVED:
        if key in query and query[key] != identity[key]:
            raise HTTPException(403, "Project owner mismatch")
    return {**query, **identity}


def _live_query(query=None) -> dict:
    return {"$and": [_query(query), {
        "deleted": {"$ne": True}, "revoked": {"$ne": True},
        "rights_revoked": {"$ne": True},
        "state": {"$nin": ["deleted", "revoked", "archived", "withdrawn"]},
    }]}


def _projection(projection):
    if isinstance(projection, dict):
        inclusion = any(value for key, value in projection.items() if key != "_id")
        if inclusion or projection == {"_id": 1}:
            return {**projection, **{key: 1 for key in _RESERVED | _LIFECYCLE_KEYS}}
        # Ownership remains available for the adapter's result check even when
        # the caller hides it from its public projection.
        return {key: value for key, value in projection.items()
                if key not in _RESERVED | _LIFECYCLE_KEYS and (key != "_id" or not value)}
    if isinstance(projection, (list, tuple)):
        return list(set(projection) | _RESERVED | _LIFECYCLE_KEYS)
    return projection


def _document(document) -> dict:
    if not isinstance(document, dict):
        raise HTTPException(422, "Project record must be an object")
    identity = project_identity()
    for key in _RESERVED:
        if key in document and document[key] != identity[key]:
            raise HTTPException(403, "Project owner mismatch")
    return {**document, **identity}


def _update(update) -> dict:
    if not isinstance(update, dict):
        raise HTTPException(422, "Project update must be an object")
    for operation, changes in update.items():
        if not operation.startswith("$") or not isinstance(changes, dict):
            raise HTTPException(422, "Unsupported project update")
        for key, value in changes.items():
            if key.split(".", 1)[0] in _RESERVED:
                if operation not in {"$set", "$setOnInsert"} or key not in _RESERVED or value != project_identity()[key]:
                    raise HTTPException(403, "Project ownership is immutable")
            if operation == "$rename" and isinstance(value, str) and value.split(".", 1)[0] in _RESERVED:
                raise HTTPException(403, "Project ownership is immutable")
    inserted = {**update.get("$setOnInsert", {}), **project_identity()}
    for key in update.get("$set", {}):
        inserted.pop(key, None)
    return {**update, "$setOnInsert": inserted}


async def _authorize_operation(name, values, *, mutate=False, insert=False):
    identity = await reauthorize_project_context(mutate=mutate)
    ids = _project_ids(values)
    if insert and name == "playables":
        ids.discard(values.get("playable_id"))
    for pid in ids:
        await assert_project_access(pid, mutate=mutate)
    return identity


def _review_record(row, name):
    if name not in {"playables", "playable_jobs"} or not isinstance(row, dict):
        return row
    projected = dict(row)
    digest = playable_html_digest(row["html"]) if isinstance(row.get("html"), str) else row.get("html_digest")
    if "evaluation" in row:
        projected["evaluation"] = model_review_projection(row["evaluation"], current_source_digest=digest)
    return projected


def _review_document(document, name):
    if name not in {"playables", "playable_jobs"} or not isinstance(document, dict):
        return document
    projected = dict(document)
    if isinstance(projected.get("html"), str):
        projected["html_digest"] = playable_html_digest(projected["html"])
    return _review_record(projected, name)


def _review_update(update, name):
    if name not in {"playables", "playable_jobs"} or not isinstance(update, dict):
        return update
    projected = {operation: dict(changes) if isinstance(changes, dict) else changes
                 for operation, changes in update.items()}
    for operation in ("$set", "$setOnInsert"):
        changes = projected.get(operation)
        if not isinstance(changes, dict):
            continue
        if isinstance(changes.get("html"), str):
            # One atomic source digest invalidates the prior review on all
            # reads. Keep its historical scores; an unchanged source retains
            # its review, and a fresh same-write review must match these bytes.
            changes["html_digest"] = playable_html_digest(changes["html"])
        if "evaluation" in changes:
            review = changes["evaluation"]
            digest = changes.get("html_digest")
            if digest is None and isinstance(review, dict):
                digest = review.get("source_digest")  # Rechecked against source on every read.
            changes["evaluation"] = model_review_projection(review, current_source_digest=digest)
    return projected


class _ProjectCursor:
    def __init__(self, cursor, name, query, *, aggregate=False):
        self._cursor, self._name, self._query = cursor, name, query
        self._aggregate = aggregate
        self._identity = project_identity()

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    async def to_list(self, *args, **kwargs):
        identity = await _authorize_operation(self._name, self._query)
        if identity != self._identity:
            raise HTTPException(403, "Project cursor authority changed")
        rows = await self._cursor.to_list(*args, **kwargs)
        # Aggregations are scoped before any grouping/projection; ordinary
        # records additionally require intact authority in every result.
        return [_review_record(row, self._name) for row in rows if self._aggregate or _available(row, identity)]

    def __aiter__(self):
        async def iterate():
            identity = await _authorize_operation(self._name, self._query)
            if identity != self._identity:
                raise HTTPException(403, "Project cursor authority changed")
            async for row in self._cursor:
                if self._aggregate or _available(row, identity):
                    yield _review_record(row, self._name)
        return iterate()


class _ProjectCollection:
    def __init__(self, collection, name):
        self._collection, self._name = collection, name

    def find(self, query=None, projection=None, *args, **kwargs):
        return _ProjectCursor(self._collection.find(_query(query), _projection(projection), *args, **kwargs), self._name, query or {})

    async def find_one(self, query=None, projection=None, *args, **kwargs):
        identity = await _authorize_operation(self._name, query or {})
        row = await self._collection.find_one(_query(query), _projection(projection), *args, **kwargs)
        return _review_record(row, self._name) if _available(row, identity) else None

    async def insert_one(self, document, *args, **kwargs):
        await _authorize_operation(self._name, document, mutate=True, insert=True)
        return await self._collection.insert_one(_document(_review_document(document, self._name)), *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        documents = list(documents)
        for document in documents:
            await _authorize_operation(self._name, document, mutate=True, insert=True)
        return await self._collection.insert_many([_document(_review_document(document, self._name)) for document in documents], *args, **kwargs)

    async def update_one(self, query, update, *args, **kwargs):
        await _authorize_operation(self._name, {**query, **update.get("$set", {})}, mutate=True)
        result = await self._collection.update_one(_query(query), _update(_review_update(update, self._name)), *args, **kwargs)
        if not kwargs.get("upsert") and getattr(result, "matched_count", None) == 0:
            raise HTTPException(404, "Project record not found")
        return result

    async def update_many(self, query, update, *args, **kwargs):
        await _authorize_operation(self._name, {**query, **update.get("$set", {})}, mutate=True)
        return await self._collection.update_many(_query(query), _update(_review_update(update, self._name)), *args, **kwargs)

    async def find_one_and_update(self, query, update, *args, **kwargs):
        identity = await _authorize_operation(self._name, {**query, **update.get("$set", {})}, mutate=True)
        if "projection" in kwargs:
            kwargs["projection"] = _projection(kwargs["projection"])
        row = await self._collection.find_one_and_update(_query(query), _update(_review_update(update, self._name)), *args, **kwargs)
        return _review_record(row, self._name) if _available(row, identity) else None

    async def replace_one(self, query, document, *args, **kwargs):
        await _authorize_operation(self._name, document, mutate=True)
        return await self._collection.replace_one(_query(query), _document(_review_document(document, self._name)), *args, **kwargs)

    async def delete_one(self, query, *args, **kwargs):
        await _authorize_operation(self._name, query, mutate=True)
        return await self._collection.delete_one(_query(query), *args, **kwargs)

    async def delete_many(self, query, *args, **kwargs):
        await _authorize_operation(self._name, query, mutate=True)
        return await self._collection.delete_many(_query(query), *args, **kwargs)

    async def count_documents(self, query, *args, **kwargs):
        await _authorize_operation(self._name, query)
        return await self._collection.count_documents(_live_query(query), *args, **kwargs)

    async def distinct(self, key, query=None, *args, **kwargs):
        await _authorize_operation(self._name, query or {})
        return await self._collection.distinct(key, _live_query(query), *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        # These operators can read/write another collection outside this
        # adapter's scoped authority. No legacy project route needs them.
        def unsafe(value):
            if isinstance(value, dict):
                return any(key in {"$lookup", "$unionWith", "$out", "$merge", "$graphLookup"} or unsafe(item)
                           for key, item in value.items())
            return isinstance(value, list) and any(unsafe(item) for item in value)
        if unsafe(pipeline):
            raise HTTPException(403, "Cross-collection project aggregation is unavailable")
        cursor = self._collection.aggregate([{"$match": _live_query()}, *pipeline], *args, **kwargs)
        return _ProjectCursor(cursor, self._name, {}, aggregate=True)

    async def create_index(self, *args, **kwargs):
        await reauthorize_project_context(mutate=True)
        return await self._collection.create_index(*args, **kwargs)


class _ProjectDatabase:
    def __init__(self, database):
        self._database = database

    def __getitem__(self, name):
        return _ProjectCollection(self._database[name], name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def scoped_database(database):
    return database if isinstance(database, _ProjectDatabase) else _ProjectDatabase(database)
