"""Authenticated crawler operations in the existing CORE_DB authority.

The canonical crawler owns transport, extraction and runtime snapshots. This
adapter owns the account-scoped durable command and worker fences. A captured
page is unreviewed external material, never a promoted Dragon lesson.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.databases import core_db
from core.engine_client import EngineClient, EngineClientError

log = logging.getLogger(__name__)
MAX_SNAPSHOT = 4 * 1024 * 1024
MAX_SESSIONS = 32
MAX_OPERATIONS = 128
LEASE_SECONDS = 120
MAX_CONCURRENT_SLICES = 4


class CrawlerError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _encoded(value: object, maximum: int = MAX_SNAPSHOT) -> bytes:
    try:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise CrawlerError("crawler_integrity", "Crawler evidence is not finite JSON.", 503) from exc
    if len(raw) > maximum:
        raise CrawlerError("crawler_size_limit", "Crawler evidence exceeds its storage bound.", 413)
    return raw


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _plain(value: object) -> Any:
    # Mongo Int64 is a lossless integer representation, but the numerical and
    # crawl validators accept plain JSON types. No string/default coercion.
    return json.loads(_encoded(value))


def _operation(key: str) -> str:
    if not isinstance(key, str) or not key or key != key.strip() or len(key) > 128:
        raise CrawlerError("crawler_idempotency", "A normalized idempotency key is required.")
    return hashlib.sha256(key.encode()).hexdigest()


def authenticated_scope(user: dict | None) -> dict[str, str]:
    if not isinstance(user, dict) or user.get("disabled") or user.get("dev_mode"):
        raise CrawlerError("crawler_sign_in_required", "Sign in to use scoped crawler data.", 401)
    email, tenant = user.get("email"), user.get("tenant_id") or user.get("email")
    if (
        not isinstance(email, str)
        or not 3 <= len(email.strip()) <= 200
        or not isinstance(tenant, str)
        or not 1 <= len(tenant.strip()) <= 128
        or user.get("role") not in {"viewer", "editor", "admin"}
    ):
        raise CrawlerError("crawler_account_unavailable", "Authenticated account scope is unavailable.", 403)
    return {
        "tenant_id": tenant.strip(),
        "owner_id": hashlib.sha256((tenant.strip() + "\x00" + email.strip().lower()).encode()).hexdigest(),
    }


def _core():
    from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

    return CrawlRequest, CrawlRun


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, CrawlerError):
        return exc.code
    if isinstance(exc, PermissionError):
        return "crawler_authority_denied"
    if isinstance(exc, (ValueError, TypeError)):
        return "crawler_request_rejected"
    return "crawler_slice_interrupted"


class DragonCrawlerApplication:
    def __init__(self, database=core_db):
        self.database = database
        self.sessions = database["dragon_crawler_sessions"]
        self.limits = database["dragon_crawler_commands"]
        try:
            self.engine = EngineClient.from_env()
        except EngineClientError:
            self.engine = None
        self._indexes_ready = False

    async def ensure_indexes(self):
        if not self._indexes_ready:
            await self.sessions.create_index(
                [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("_id", DESCENDING)]
            )
            await self.sessions.create_index([("status", ASCENDING), ("lease_until", ASCENDING)])
            self._indexes_ready = True

    async def readiness(self) -> dict[str, Any]:
        available, code, message = False, "crawler_storage_unavailable", "Crawler storage is unavailable."
        try:
            _core()
            await asyncio.wait_for(self.database.command("ping", maxTimeMS=2000), timeout=2)
            await self.ensure_indexes()
            if self.engine is None:
                code, message = (
                    "crawler_admission_unconfigured",
                    "Configure the canonical engine storage admission endpoint.",
                )
            else:
                try:
                    # This is a read-only canonical boundary probe. A model
                    # can be unavailable while crawler storage remains usable.
                    await asyncio.wait_for(self.engine.provider_status(), timeout=2)
                except (EngineClientError, TimeoutError):
                    code = "crawler_admission_unreachable"
                    message = "The canonical engine boundary is not reachable; crawler writes remain blocked."
                    return self._readiness_payload(False, code, message)
                available, code, message = (
                    True,
                    "ready",
                    "Scoped crawler persistence is available; each run still checks source and network policy.",
                )
        except ImportError:
            code, message = (
                "crawler_runtime_unavailable",
                "Install the canonical crawler runtime with the application.",
            )
        except (PyMongoError, TimeoutError):
            pass
        return self._readiness_payload(available, code, message)

    def _readiness_payload(self, available: bool, code: str, message: str) -> dict:
        return {
            "ok": True,
            "configured": self.engine is not None,
            "available": available,
            "code": code,
            "message": message,
            "action": (
                None
                if available
                else "Run first-install diagnostics and configure CORE_DB and canonical engine storage admission."
            ),
            "storage_authority": "CORE_DB Mongo",
            "network_reachability_verified": False,
            "capabilities": {
                "manual_crawl": available,
                "durable_resume": available,
                "source_export": available,
                "automatic_review": False,
                "model_training": False,
                "trusted_device_idle": False,
            },
            "limits": {
                "seed_urls": 16,
                "sessions": MAX_SESSIONS,
                "max_requests": 128,
                "max_documents": 64,
                "max_bytes": 32 * 1024 * 1024,
                "max_depth": 3,
                "slice_steps": 4,
                "slice_seconds": 40,
                "snapshot_bytes": MAX_SNAPSHOT,
                "source_page": 32,
                "session_page": 32,
                "concurrent_slices": MAX_CONCURRENT_SLICES,
            },
        }

    async def _admit(self, scope: dict[str, str], identifier: str, payload: dict) -> dict:
        if self.engine is None:
            raise CrawlerError(
                "crawler_admission_unconfigured", "Canonical storage admission is not configured.", 503
            )
        raw = _encoded(payload)
        try:
            receipt = await self.engine.admit_storage_write(
                tenant_id=scope["tenant_id"],
                capability="dragon-crawler-persistence",
                resource_id=identifier,
                write_id=identifier + ":" + hashlib.sha256(raw).hexdigest(),
                storage_bytes=len(raw),
            )
        except Exception as exc:
            raise CrawlerError(
                "crawler_admission_unavailable",
                "Canonical storage admission rejected the crawler write.",
                503,
            ) from exc
        if (
            not isinstance(receipt, Mapping)
            or type(receipt.get("storage_bytes")) is not int
            or receipt["storage_bytes"] < len(raw)
        ):
            raise CrawlerError(
                "crawler_admission_invalid", "Storage admission did not cover the crawler snapshot.", 503
            )
        _encoded(dict(receipt), 64 * 1024)
        return dict(receipt)

    async def _owned(self, scope: dict[str, str], identifier: str) -> dict:
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128:
            raise CrawlerError("crawler_identifier_invalid", "Crawler session identifier is invalid.")
        row = await self.sessions.find_one({"_id": identifier, **scope})
        if row is None or row.get("status") == "deleted":
            raise CrawlerError("crawler_not_found", "Crawler session not found.", 404)
        if _digest(_plain(row["request"])) != row["request_digest"]:
            raise CrawlerError("crawler_integrity", "Crawler request integrity check failed.", 503)
        _, run_type = _core()
        run = run_type.from_snapshot(_plain(row["snapshot"]))
        snapshot = run.snapshot()
        binding = snapshot.get("binding", {})
        if (
            binding.get("scope") != scope
            or binding.get("request_digest") != row["request_digest"]
            or binding.get("consent") != _plain(row["consent"])
        ):
            raise CrawlerError(
                "crawler_integrity", "Crawler snapshot owner does not match its durable scope.", 503
            )
        return row

    @staticmethod
    def _projection(row: dict) -> dict:
        _, run_type = _core()
        runtime = run_type.from_snapshot(_plain(row["snapshot"]))
        status = dict(runtime.status())
        # Operational state is authoritative in Mongo while a pure snapshot
        # is paused at its last accepted checkpoint.
        status.update(
            session_id=row["_id"],
            title=row["title"],
            status=row["status"],
            version=int(row["version"]),
            created_at=_utc(row["created_at"]).isoformat(),
            updated_at=_utc(row["updated_at"]).isoformat(),
            seeds=row["request"]["seed_urls"],
            consent_expires_at=_utc(row["consent_expires_at"]).isoformat(),
            error=row.get("error"),
            last_event=row.get("last_event"),
            review_state="unreviewed",
            source_classification="untrusted_external_material",
            automatic_review=False,
            counters=status.get("usage", {}),
            limits=row["request"],
        )
        return status

    async def _reconcile(self, scope: dict[str, str], row: dict) -> dict:
        if row["status"] == "running" and row.get("lease_until") and _utc(row["lease_until"]) <= _now():
            _, run_type = _core()
            checkpoint_state = run_type.from_snapshot(_plain(row["snapshot"])).status()["state"]
            restored = (
                checkpoint_state
                if checkpoint_state in {"completed", "budget_exhausted", "cancelled"}
                else "interrupted"
            )
            operations = _plain(row.get("operations", {}))
            for receipt in operations.values():
                if receipt.get("state") == "running":
                    receipt.update(
                        state="interrupted" if restored == "interrupted" else "completed",
                        recovered_from_checkpoint=True,
                    )
            await self.sessions.update_one(
                {
                    "_id": row["_id"],
                    **scope,
                    "status": "running",
                    "worker_token": row.get("worker_token"),
                    "lease_until": row["lease_until"],
                },
                {
                    "$set": {
                        "status": restored,
                        "operations": operations,
                        "updated_at": _now(),
                        "error": (
                            {
                                "code": "crawler_worker_expired",
                                "message": "The previous worker stopped; resume from its last committed snapshot.",
                            }
                            if restored == "interrupted"
                            else None
                        ),
                    },
                    "$inc": {"version": 1},
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
            row = await self._owned(scope, row["_id"])
        return row

    async def get(self, scope: dict[str, str], identifier: str) -> dict:
        return self._projection(await self._reconcile(scope, await self._owned(scope, identifier)))

    async def list(self, scope: dict[str, str], *, cursor: str | None = None, limit: int = 16) -> dict:
        query = {**scope, "status": {"$ne": "deleted"}}
        if cursor:
            query["_id"] = {"$lt": cursor}
        rows = (
            await self.sessions.find(query, {"_id": 1})
            .sort("_id", DESCENDING)
            .limit(limit + 1)
            .to_list(limit + 1)
        )
        items = []
        for row in rows[:limit]:
            items.append(await self.get(scope, row["_id"]))
        return {
            "ok": True,
            "sessions": items,
            "next_cursor": rows[limit - 1]["_id"] if len(rows) > limit else None,
        }

    async def create(self, scope: dict[str, str], body: dict) -> dict:
        if body.get("consent") is not True or body.get("rights_acknowledged") is not True:
            raise CrawlerError(
                "crawler_consent_required",
                "Explicit capture and source-rights acknowledgement are required.",
                403,
            )
        await self.ensure_indexes()
        op = _operation(body["idempotency_key"])
        identifier = str(uuid5(NAMESPACE_URL, "dragon-crawler:" + _digest(scope) + ":" + op))
        request_digest = _digest(body)
        prior = await self.sessions.find_one({"_id": identifier, **scope})
        if prior:
            if prior["creation_digest"] != request_digest:
                raise CrawlerError(
                    "crawler_idempotency_conflict", "This operation key already names a different crawl.", 409
                )
            return await self.get(scope, identifier)
        request_type, run_type = _core()
        from urllib.parse import urlsplit

        from skeleton.ai.webcrawler.core import canonicalize_url

        seeds = tuple(canonicalize_url(url) for url in body["seeds"])
        hosts = tuple(sorted({urlsplit(url).hostname for url in seeds}))
        request = request_type(
            seed_urls=seeds,
            allowed_hosts=hosts,
            query=" ".join(body.get("topics", [])),
            max_depth=body.get("max_depth", 1),
            max_requests=body.get("max_requests", 24),
            max_documents=body.get("max_documents", 16),
            max_response_bytes=524288,
            max_total_bytes=body.get("max_bytes", 8 * 1024 * 1024),
            min_host_delay_seconds=1.0,
        )
        now = _now()
        expiry = now + timedelta(hours=24)
        consent = {
            "consent_id": _digest([scope, identifier, request_digest]),
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": expiry.timestamp(),
        }
        runtime = run_type.create(request, scope=scope, consent=consent, now=now.timestamp())
        snapshot = runtime.snapshot()
        row = {
            "_id": identifier,
            **scope,
            "title": body.get("title") or seeds[0][:160],
            "creation_digest": request_digest,
            "request": request.as_dict(),
            "request_digest": _digest(request.as_dict()),
            "snapshot": snapshot,
            "status": "queued",
            "version": 1,
            "worker_epoch": 0,
            "created_at": now,
            "updated_at": now,
            "consent_expires_at": expiry,
            "consent": consent,
            "operations": {},
        }
        row["storage_receipt"] = await self._admit(
            scope, identifier, {"request": row["request"], "snapshot": snapshot}
        )
        quota_id = _digest(scope)
        await self.limits.update_one(
            {"_id": quota_id}, {"$setOnInsert": {**scope, "session_ids": []}}, upsert=True
        )
        reserved = await self.limits.update_one(
            {
                "_id": quota_id,
                **scope,
                "$or": [{"session_ids": identifier}, {"session_ids.31": {"$exists": False}}],
            },
            {"$addToSet": {"session_ids": identifier}},
        )
        if not reserved.matched_count:
            raise CrawlerError(
                "crawler_session_limit", "This account has reached its bounded crawl-session allowance.", 429
            )
        try:
            await self.sessions.insert_one(row)
        except DuplicateKeyError:
            prior = await self.sessions.find_one({"_id": identifier, **scope})
            if prior is None or prior["creation_digest"] != request_digest:
                raise CrawlerError(
                    "crawler_idempotency_conflict", "Concurrent crawler creation conflicted.", 409
                ) from None
        return await self.get(scope, identifier)

    def _prior(self, row: dict, operation: str, digest: str) -> dict | None:
        previous = row.get("operations", {}).get(operation)
        if previous is not None and previous["request_digest"] != digest:
            raise CrawlerError(
                "crawler_idempotency_conflict", "Operation key is bound to a different command.", 409
            )
        if previous is None and len(row.get("operations", {})) >= MAX_OPERATIONS:
            raise CrawlerError(
                "crawler_command_limit",
                "Session command history reached its bound; create another bounded session.",
                429,
            )
        return previous

    async def control(self, scope: dict[str, str], identifier: str, body: dict) -> dict:
        row = await self._reconcile(scope, await self._owned(scope, identifier))
        operation, digest = _operation(body["idempotency_key"]), _digest(body)
        if self._prior(row, operation, digest):
            return self._projection(row)
        if row["version"] != body["expected_version"]:
            raise CrawlerError("crawler_conflict", "Reload the crawler session before changing it.", 409)
        action = body["action"]
        if action == "resume" and row["status"] == "running":
            raise CrawlerError("crawler_busy", "The current worker must drain before resuming.", 409)
        _, run_type = _core()
        runtime = run_type.from_snapshot(_plain(row["snapshot"]))
        if (
            action == "resume"
            and row["status"] == "interrupted"
            and runtime.status()["state"] in {"ready", "running"}
        ):
            # Recovery preserves pending dispatch reservations and fences the
            # old worker before going through canonical control transitions.
            runtime.pause()
        getattr(runtime, action)()
        snapshot = runtime.snapshot()
        state = "queued" if action == "resume" else ("paused" if action == "pause" else "cancelled")
        receipt = await self._admit(scope, identifier, snapshot)
        changed = await self.sessions.update_one(
            {"_id": identifier, **scope, "version": row["version"]},
            {
                "$set": {
                    "snapshot": snapshot,
                    "status": state,
                    "updated_at": _now(),
                    "storage_receipt": receipt,
                    "operations."
                    + operation: {"request_digest": digest, "action": action, "state": "completed"},
                },
                "$inc": {"version": 1},
            },
        )
        if not changed.modified_count:
            raise CrawlerError("crawler_conflict", "Crawler changed while applying the command.", 409)
        return await self.get(scope, identifier)

    async def _live(
        self, scope: dict[str, str], identifier: str, token: str, epoch: int, *, network_margin: bool = False
    ) -> dict:
        row = await self.sessions.find_one(
            {
                "_id": identifier,
                **scope,
                "status": "running",
                "worker_token": token,
                "worker_epoch": epoch,
                "$expr": {
                    "$and": [
                        {"$gt": ["$lease_until", {"$add": ["$$NOW", 15000]} if network_margin else "$$NOW"]},
                        {
                            "$gt": [
                                "$consent_expires_at",
                                {"$add": ["$$NOW", 15000]} if network_margin else "$$NOW",
                            ]
                        },
                    ]
                },
            }
        )
        if row is None:
            raise CrawlerError(
                "crawler_worker_fenced", "Crawler worker lost its live session authority.", 409
            )
        return row

    async def run(self, scope: dict[str, str], identifier: str, body: dict) -> dict:
        row = await self._reconcile(scope, await self._owned(scope, identifier))
        operation, digest = _operation(body["idempotency_key"]), _digest(body)
        previous = self._prior(row, operation, digest)
        if previous:
            return {"ok": True, "session": self._projection(row), "run": previous}
        if row["version"] != body["expected_version"]:
            raise CrawlerError("crawler_conflict", "Reload the current crawler revision before running.", 409)
        if row["status"] not in {"queued", "interrupted"}:
            raise CrawlerError(
                "crawler_not_runnable", "Resume a paused crawl before running another bounded slice.", 409
            )
        if _utc(row["consent_expires_at"]) <= _now():
            raise CrawlerError(
                "crawler_consent_expired", "Capture consent expired; create a newly authorized crawl.", 403
            )
        quota_id, token = _digest(scope), str(uuid4())
        now, epoch = _now(), int(row["worker_epoch"]) + 1
        credit = await self.limits.find_one_and_update(
            {
                "_id": quota_id,
                **scope,
                "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lt": now}}],
            },
            {
                "$set": {
                    "worker_token": token,
                    "active_session_id": identifier,
                    "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if credit is None:
            raise CrawlerError(
                "crawler_capacity", "This account already has an active bounded crawler slice.", 429
            )
        global_credit = None
        try:
            for index in range(MAX_CONCURRENT_SLICES):
                slot = "crawler-slice:" + str(index)
                await self.limits.update_one(
                    {"_id": slot},
                    {
                        "$setOnInsert": {
                            "kind": "physical_slice_capacity",
                            "lease_until": datetime(1970, 1, 1, tzinfo=timezone.utc),
                        }
                    },
                    upsert=True,
                )
                global_credit = await self.limits.find_one_and_update(
                    {
                        "_id": slot,
                        "$or": [
                            {"lease_until": {"$exists": False}},
                            {"$expr": {"$lte": ["$lease_until", "$$NOW"]}},
                        ],
                    },
                    {
                        "$set": {
                            "worker_token": token,
                            "active_session_id": identifier,
                            "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if global_credit is not None:
                    break
            if global_credit is None:
                raise CrawlerError(
                    "crawler_capacity",
                    "The bounded crawler worker capacity is occupied; retry after a slice drains.",
                    429,
                )
        except BaseException:
            await self.limits.update_many(
                {"worker_token": token},
                {"$unset": {"worker_token": "", "active_session_id": "", "lease_until": ""}},
            )
            raise
        changed = await self.sessions.update_one(
            {"_id": identifier, **scope, "version": row["version"], "status": row["status"]},
            {
                "$set": {
                    "status": "running",
                    "worker_token": token,
                    "worker_epoch": epoch,
                    "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                    "updated_at": now,
                    "operations."
                    + operation: {"request_digest": digest, "action": "run", "state": "running"},
                },
                "$inc": {"version": 1},
                "$unset": {"error": ""},
            },
        )
        if not changed.modified_count:
            await self.limits.update_many(
                {"worker_token": token},
                {"$unset": {"worker_token": "", "active_session_id": "", "lease_until": ""}},
            )
            raise CrawlerError("crawler_conflict", "Crawler changed before the worker was claimed.", 409)
        loop, cancelled = asyncio.get_running_loop(), threading.Event()

        def bridge(coroutine):
            # A publication must finish before the pure worker can roll back or
            # release its physical lease. Cancelling a Future does not prove a
            # Mongo write stopped, so await its actual bounded-driver result.
            return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

        async def commit(snapshot: dict, event: dict):
            raw = _plain(snapshot)
            await self._live(scope, identifier, token, epoch)
            receipt = await self._admit(scope, identifier, raw)
            result = await self.sessions.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "worker_token": token,
                    "worker_epoch": epoch,
                    "status": "running",
                    "$expr": {
                        "$and": [
                            {"$gt": ["$lease_until", "$$NOW"]},
                            {"$gt": ["$consent_expires_at", "$$NOW"]},
                        ]
                    },
                },
                {
                    "$set": {
                        "snapshot": raw,
                        "storage_receipt": receipt,
                        "updated_at": _now(),
                        "last_event": _plain(event),
                    },
                    "$inc": {"version": 1},
                },
            )
            if not result.modified_count:
                raise CrawlerError(
                    "crawler_worker_fenced", "Crawler completion was fenced by a newer command.", 409
                )

        def work():
            _, run_type = _core()
            runtime = run_type.from_snapshot(_plain(row["snapshot"]))
            summary = runtime.run_slice(
                max_steps=body.get("max_steps", 4),
                max_seconds=40,
                # The canonical transport's full deadline is ten seconds.
                # Refuse new IO with less than fifteen seconds of lease left,
                # including a thread delayed in the application executor.
                authorize=lambda: bridge(self._live(scope, identifier, token, epoch, network_margin=True)),
                cancelled=cancelled.is_set,
                on_checkpoint=lambda snapshot, event: bridge(commit(snapshot, event)),
            )
            return runtime.snapshot(), _plain(summary)

        # Keep the executor Future rather than wrapping it in a child Task:
        # shutdown cancels all Tasks, including a shielded to_thread Task.
        # The Future remains joinable while the actual HTTP thread drains.
        worker = loop.run_in_executor(None, work)
        failure: BaseException | None = None
        interrupted = False
        try:
            while True:
                try:
                    snapshot, summary = await asyncio.shield(worker)
                    break
                except asyncio.CancelledError:
                    # Detaching HTTP does not release an active network worker.
                    cancelled.set()
                    interrupted = True
            current = await self._live(scope, identifier, token, epoch)
            snapshot = _plain(snapshot)
            receipt = await self._admit(scope, identifier, snapshot)
            _, run_type = _core()
            state = str(run_type.from_snapshot(snapshot).status()["state"])
            state = "queued" if state in {"ready", "created", "queued", "running"} else state
            if interrupted and state == "queued":
                state = "interrupted"
            operation_receipt = {
                "request_digest": digest,
                "action": "run",
                "state": "completed",
                # The current queue and recent events live once in the full
                # snapshot. Repeating them in every command receipt would
                # eventually exceed a bounded Mongo document.
                "summary": {
                    key: summary[key]
                    for key in (
                        "run_id",
                        "state",
                        "sequence",
                        "usage",
                        "frontier_count",
                        "source_count",
                        "stop_reason",
                        "slice_steps",
                    )
                    if key in summary
                },
                "result_digest": _digest(summary),
                "event_digests": [event["event_digest"] for event in summary.get("slice_events", [])],
            }
            result = await self.sessions.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "version": current["version"],
                    "status": "running",
                    "worker_token": token,
                    "worker_epoch": epoch,
                    "$expr": {
                        "$and": [
                            {"$gt": ["$lease_until", "$$NOW"]},
                            {"$gt": ["$consent_expires_at", "$$NOW"]},
                        ]
                    },
                },
                {
                    "$set": {
                        "status": state,
                        "snapshot": snapshot,
                        "storage_receipt": receipt,
                        "updated_at": _now(),
                        "operations." + operation: operation_receipt,
                    },
                    "$inc": {"version": 1},
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
            if not result.modified_count:
                raise CrawlerError("crawler_worker_fenced", "Crawler final status was superseded.", 409)
        except BaseException as exc:
            failure = exc
            cancelled.set()
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    cancelled.set()
                except BaseException:
                    break
            if worker.done() and not worker.cancelled():
                # Retrieve an exception even when another control command won.
                worker.exception()
            code = _safe_error(exc)
            operation_receipt = {
                "request_digest": digest,
                "action": "run",
                "state": "interrupted",
                "error_code": code,
            }
            await self.sessions.update_one(
                {"_id": identifier, **scope, "worker_token": token, "worker_epoch": epoch},
                {
                    "$set": {"updated_at": _now(), "operations." + operation: operation_receipt},
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
            await self.sessions.update_one(
                {"_id": identifier, **scope, "status": "running", "worker_epoch": epoch},
                {
                    "$set": {
                        "status": "interrupted",
                        "error": {
                            "code": code,
                            "message": "The slice stopped; only accepted checkpoints remain.",
                        },
                    },
                    "$inc": {"version": 1},
                },
            )
        finally:
            await self.limits.update_many(
                {"worker_token": token},
                {"$unset": {"worker_token": "", "active_session_id": "", "lease_until": ""}},
            )
        if isinstance(failure, asyncio.CancelledError):
            raise failure
        current = await self.get(scope, identifier)
        return {"ok": failure is None, "session": current, "run": operation_receipt}

    async def delete(self, scope: dict[str, str], identifier: str, body: dict) -> dict:
        # Erasure remains available to the exact owner even after a runtime
        # upgrade makes an old source snapshot inadmissible to execution.
        row = await self.sessions.find_one({"_id": identifier, **scope})
        if row is None:
            raise CrawlerError("crawler_not_found", "Crawler session not found.", 404)
        operation, digest = _operation(body["idempotency_key"]), _digest(body)
        previous = row.get("deletion")
        if previous and previous.get("operation") == operation and previous.get("request_digest") == digest:
            return {"ok": True, "session_id": identifier, "status": "deleted", "version": int(row["version"])}
        if row["version"] != body["expected_version"]:
            raise CrawlerError(
                "crawler_conflict", "Reload the current session version before deleting it.", 409
            )
        result = await self.sessions.update_one(
            {"_id": identifier, **scope, "version": row["version"]},
            {
                "$set": {
                    "status": "deleted",
                    "title": "Deleted crawl",
                    "updated_at": _now(),
                    "deletion": {"operation": operation, "request_digest": digest},
                },
                "$inc": {"version": 1},
                "$unset": {
                    "snapshot": "",
                    "request": "",
                    "consent": "",
                    "operations": "",
                    "last_event": "",
                    "storage_receipt": "",
                },
            },
        )
        if not result.modified_count:
            raise CrawlerError("crawler_conflict", "Crawler changed before source erasure.", 409)
        # A live worker's physical lease is deliberately retained until its
        # actual thread drains; status='deleted' fences its final publication.
        await self.limits.update_one({"_id": _digest(scope), **scope}, {"$pull": {"session_ids": identifier}})
        return {"ok": True, "session_id": identifier, "status": "deleted", "version": int(row["version"]) + 1}

    async def events(
        self, scope: dict[str, str], identifier: str, *, after_sequence: int = 0, limit: int = 32
    ) -> dict:
        row = await self._owned(scope, identifier)
        _, run_type = _core()
        events = run_type.from_snapshot(_plain(row["snapshot"])).snapshot()["events"]
        available = [event for event in events if event["sequence"] > after_sequence]
        page = available[:limit]
        return {
            "ok": True,
            "session_id": identifier,
            "events": page,
            "next_cursor": page[-1]["sequence"] if page else after_sequence,
            "has_more": len(available) > limit,
            "history_truncated": bool(events and after_sequence < events[0]["sequence"] - 1),
        }

    @staticmethod
    def _source_projection(source: dict, *, text: bool = True) -> dict:
        result = dict(source)
        result.update(
            url=source["canonical_url"],
            content_digest=source["preserved_text_hash"],
            fetched_at=datetime.fromtimestamp(source["fetched_at"], tz=timezone.utc).isoformat(),
            fetched_at_unix=source["fetched_at"],
            source_classification="untrusted_external_material",
        )
        if not text:
            result.pop("text", None)
        return result

    async def sources(
        self, scope: dict[str, str], identifier: str, *, cursor: str | None = None, limit: int = 16
    ) -> dict:
        row = await self._owned(scope, identifier)
        _, run_type = _core()
        sources = run_type.from_snapshot(_plain(row["snapshot"])).sources()
        ordered = sorted(sources, key=lambda item: item["source_id"])
        if cursor:
            ordered = [source for source in ordered if source["source_id"] > cursor]
        page = ordered[:limit]
        return {
            "ok": True,
            "sources": [self._source_projection(source, text=False) for source in page],
            "next_cursor": page[-1]["source_id"] if len(ordered) > limit else None,
        }

    async def source(self, scope: dict[str, str], identifier: str, source_id: str) -> dict:
        row = await self._owned(scope, identifier)
        _, run_type = _core()
        try:
            source = run_type.from_snapshot(_plain(row["snapshot"])).source_read(source_id)
        except ValueError:
            raise CrawlerError("crawler_source_not_found", "Captured source not found.", 404)
        return self._source_projection(source)

    async def context(self, scope: dict[str, str], query: str, max_docs: int, max_chars: int) -> dict:
        import re

        if (
            not isinstance(query, str)
            or len(query) > 2000
            or type(max_docs) is not int
            or not 1 <= max_docs <= 8
            or type(max_chars) is not int
            or not 1 <= max_chars <= 32000
        ):
            raise CrawlerError(
                "crawler_context_bounds", "Crawler context exceeds its query or document bound."
            )
        terms = tuple(dict.fromkeys(re.findall(r"\w{2,}", query.lower())))[:24]
        if not terms:
            return {"documents": [], "references": []}
        rows = (
            self.sessions.find(
                {**scope, "status": {"$nin": ["deleted", "cancelled"]}, "consent_expires_at": {"$gt": _now()}}
            )
            .sort("updated_at", DESCENDING)
            .limit(MAX_SESSIONS)
        )
        candidates = []
        _, run_type = _core()
        search_query = " ".join(terms)[:512]
        async for row in rows:
            await self._owned(scope, row["_id"])
            runtime = run_type.from_snapshot(_plain(row["snapshot"]))
            for hit in runtime.search(search_query, limit=8)["hits"]:
                # Re-capturing one page in multiple sessions is not several
                # independent sources, and must not create duplicate context
                # segment IDs for the same source/passage.
                if any(item[3]["content_hash"] == hit["content_hash"] for item in candidates):
                    continue
                source = runtime.source_read(hit["source_id"])
                if (
                    source["text"][hit["start"] : hit["end"]] != hit["text"]
                    or hashlib.sha256(hit["text"].encode()).hexdigest() != hit["passage_hash"]
                ):
                    raise CrawlerError(
                        "crawler_passage_integrity",
                        "Selected evidence is not the exact captured source passage.",
                        503,
                    )
                candidates.append((hit["lexical_score"], source["fetched_at"], row, source, hit))
                candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
                # Retain only the selected bounded source records, rather
                # than every account snapshot while scanning history.
                del candidates[max_docs:]
        candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
        documents, references, remaining = [], [], max_chars
        for _, _, row, source, hit in candidates[:max_docs]:
            if not remaining:
                break
            text = hit["text"][:remaining]
            remaining -= len(text)
            reference = {
                "schema_version": "skeleton.dragon.crawler_reference.v1",
                "session_id": row["_id"],
                "source_id": source["source_id"],
                "source_digest": _digest(source),
                "request_digest": row["request_digest"],
                "consent_id": row["consent"]["consent_id"],
            }
            documents.append(
                {
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "text": text,
                    "content_digest": hashlib.sha256(text.encode()).hexdigest(),
                    "source_ref": "dragon-crawl://" + row["_id"] + "/" + source["source_id"],
                    "source_url": source["canonical_url"],
                    "captured_at": source["fetched_at"],
                    "review_state": "unreviewed",
                    "source_classification": "untrusted_external_material",
                    "authority": "external_evidence_only",
                    "source_content_hash": source["content_hash"],
                    "preserved_text_hash": source["preserved_text_hash"],
                    "passage_start": hit["start"],
                    "passage_end": hit["start"] + len(text),
                    "instruction_risks": [
                        risk for risk in hit["instruction_risks"] if risk["start"] < len(text)
                    ],
                }
            )
            references.append(reference)
        await self.assert_context(scope, references)
        return {"documents": documents, "references": references}

    async def assert_context(self, scope: dict[str, str], references: list[dict]) -> None:
        if not isinstance(references, list) or len(references) > 8:
            raise CrawlerError("crawler_reference_bounds", "Crawler source references exceed their bound.")
        _, run_type = _core()
        for reference in references:
            if (
                not isinstance(reference, dict)
                or set(reference)
                != {
                    "schema_version",
                    "session_id",
                    "source_id",
                    "source_digest",
                    "request_digest",
                    "consent_id",
                }
                or reference["schema_version"] != "skeleton.dragon.crawler_reference.v1"
                or any(
                    not isinstance(value, str) or not 1 <= len(value) <= 256 for value in reference.values()
                )
            ):
                raise CrawlerError("crawler_reference_invalid", "Crawler source reference is invalid.", 403)
            row = await self._owned(scope, reference["session_id"])
            if (
                row["status"] in {"cancelled", "deleted"}
                or _utc(row["consent_expires_at"]) <= _now()
                or row["request_digest"] != reference["request_digest"]
                or row["consent"]["consent_id"] != reference["consent_id"]
            ):
                raise CrawlerError(
                    "crawler_context_revoked", "Captured source consent or identity changed.", 403
                )
            try:
                source = run_type.from_snapshot(_plain(row["snapshot"])).source_read(reference["source_id"])
            except ValueError:
                raise CrawlerError(
                    "crawler_context_revoked", "The exact captured source is no longer available.", 403
                ) from None
            if _digest(source) != reference["source_digest"]:
                raise CrawlerError("crawler_context_changed", "The captured source evidence changed.", 403)


crawler_application = DragonCrawlerApplication()


async def read_crawler_context(user: dict, query: str, max_docs: int = 4, max_chars: int = 16000) -> dict:
    return await crawler_application.context(authenticated_scope(user), query, max_docs, max_chars)


async def assert_crawler_context(user: dict, references: list[dict]) -> None:
    await crawler_application.assert_context(authenticated_scope(user), references)
