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
MAX_AUTO_SLICES = 64
MAX_AUTO_SECONDS = 3600
TERMINAL_STATES = {"completed", "budget_exhausted", "cancelled", "deleted"}


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
        # Handles only: Mongo owns intent, reservations, leases and snapshots.
        self._workers: dict[str, tuple[threading.Event, asyncio.Future]] = {}

    async def ensure_indexes(self):
        if not self._indexes_ready:
            await self.sessions.create_index(
                [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("_id", DESCENDING)]
            )
            await self.sessions.create_index([("status", ASCENDING), ("lease_until", ASCENDING)])
            await self.sessions.create_index(
                [("automation.enabled", ASCENDING), ("automation.next_run_at", ASCENDING)]
            )
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
        from core.scheduler import scheduler_status

        observed = scheduler_status()
        scheduled = bool(
            observed["running"] and any(job["id"] == "crawler_recovery" for job in observed["jobs"])
        )
        return {
            "schema_version": "skeleton.dragon.crawler_readiness.v1",
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
                "finite_autonomous_crawl": available and scheduled,
                "durable_resume": available,
                "source_export": available,
                "automatic_review": False,
                "model_training": False,
                "trusted_device_idle": False,
            },
            "scheduler": {"running": bool(observed["running"]), "crawler_job_registered": scheduled},
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
                "autonomous_slices": MAX_AUTO_SLICES,
                "autonomous_seconds": MAX_AUTO_SECONDS,
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

    def _worker_state(self, row: dict) -> dict:
        handle = self._workers.get(row.get("worker_token"))
        local = handle is not None
        active = (
            not handle[1].done()
            if local
            else bool(
                row.get("worker_token") and row.get("lease_until") and _utc(row["lease_until"]) > _now()
            )
        )
        unconfirmed = not local and (
            bool(row.get("worker_token")) or row.get("last_worker_exit_confirmed") is False
        )
        return {
            "active": active,
            "quiescent": not active and not unconfirmed,
            "local": local,
            "lease_until": _utc(row["lease_until"]).isoformat() if row.get("lease_until") else None,
            "confirmation": (
                "local_executor"
                if local
                else (
                    "remote_lease_active"
                    if active
                    else (
                        "lease_fenced_physical_unconfirmed"
                        if unconfirmed
                        else "durable_completion" if row.get("worker_epoch", 0) else "no_worker_claim"
                    )
                )
            ),
            "recovery_eligible": not active,
        }

    async def _drain(self, row: dict) -> dict:
        handle = self._workers.get(row.get("worker_token"))
        if handle is not None:
            handle[0].set()
            # wait() never cancels the physical executor on timeout/detach.
            await asyncio.wait({handle[1]}, timeout=15)
            if handle[1].done():
                return {
                    "active": False,
                    "quiescent": True,
                    "local": True,
                    "lease_until": None,
                    "confirmation": "local_executor_joined",
                    "recovery_eligible": True,
                }
        return self._worker_state(row)

    def _projection(self, row: dict) -> dict:
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
            autonomous_slices_total=int(row.get("automation_slices_total", 0)),
            review_state="unreviewed",
            source_classification="untrusted_external_material",
            automatic_review=False,
            counters=status.get("usage", {}),
            limits=row["request"],
        )
        worker = self._worker_state(row)
        grant = row.get("automation")
        status["worker"] = worker
        status["automation"] = (
            {
                key: (_utc(value).isoformat() if isinstance(value, datetime) else value)
                for key, value in grant.items()
                if key not in {"principal_email", "scope", "consent_id", "request_digest"}
            }
            if grant
            else {"enabled": False, "state": "not_authorized", "slices_started": 0}
        )
        current = status["consent_current"]
        status["capabilities"] = {
            "can_run": current
            and row["status"] in {"queued", "interrupted"}
            and not worker["active"]
            and not (grant and grant.get("enabled")),
            "can_pause": row["status"] in {"queued", "running", "interrupted"},
            "can_resume": current and row["status"] in {"paused", "interrupted"} and not worker["active"],
            "can_cancel": row["status"] not in TERMINAL_STATES,
            "can_erase": True,
            "can_automate": current and row["status"] not in TERMINAL_STATES and not worker["active"],
        }
        return status

    async def _reconcile(self, scope: dict[str, str], row: dict) -> dict:
        lease = row.get("lease_until")
        worker = self._worker_state(row)
        if row["status"] == "running" and (lease is None or _utc(lease) <= _now()) and not worker["active"]:
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
                    "lease_until": lease,
                },
                {
                    "$set": {
                        "status": restored,
                        "operations": operations,
                        "updated_at": _now(),
                        "last_worker_exit_confirmed": bool(
                            worker["quiescent"]
                            and (worker["local"] or row.get("last_worker_exit_confirmed") is True)
                        ),
                        "error": (
                            {
                                "code": "crawler_worker_expired",
                                "message": "The previous worker lease expired; recovery uses its last committed snapshot without claiming physical exit.",
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

    def _prior(self, row: dict, operation: str, digest: str, *, safety: bool = False) -> dict | None:
        previous = row.get("operations", {}).get(operation)
        if previous is None and row.get("safety_control", {}).get("operation") == operation:
            previous = row["safety_control"]
        if previous is not None and previous["request_digest"] != digest:
            raise CrawlerError(
                "crawler_idempotency_conflict", "Operation key is bound to a different command.", 409
            )
        if previous is None and len(row.get("operations", {})) >= MAX_OPERATIONS and not safety:
            raise CrawlerError(
                "crawler_command_limit",
                "Session command history reached its bound; create another bounded session.",
                429,
            )
        return previous

    async def _grant_principal(self, scope: dict[str, str], grant: dict) -> None:
        user = await self.database["gameforge_users"].find_one(
            {"email": grant.get("principal_email"), "disabled": {"$ne": True}},
            {"email": 1, "tenant_id": 1, "role": 1, "disabled": 1},
        )
        if user is None or user.get("role") not in {"editor", "admin"} or authenticated_scope(user) != scope:
            raise CrawlerError(
                "crawler_grant_revoked",
                "The authorizing account no longer has current capture permission.",
                403,
            )

    async def automation(
        self, scope: dict[str, str], identifier: str, body: dict, *, principal: dict
    ) -> dict:
        if authenticated_scope(principal) != scope or (
            body.get("enabled") is True and principal.get("role") not in {"editor", "admin"}
        ):
            raise CrawlerError("crawler_grant_denied", "Current editor authority is required.", 403)
        if type(body.get("enabled")) is not bool:
            raise CrawlerError("crawler_grant_invalid", "Choose an explicit finite execution intent.")
        slices, seconds = body.get("max_slices", 16), body.get("max_seconds", 900)
        if (
            type(slices) is not int
            or not 1 <= slices <= MAX_AUTO_SLICES
            or type(seconds) is not int
            or not 15 <= seconds <= MAX_AUTO_SECONDS
        ):
            raise CrawlerError("crawler_grant_bounds", "Autonomous execution exceeds its finite bounds.")
        row = await self._reconcile(scope, await self._owned(scope, identifier))
        operation, digest = _operation(body["idempotency_key"]), _digest(body)
        if self._prior(row, operation, digest, safety=body["enabled"] is False):
            return self._projection(row)
        if row["version"] != body["expected_version"]:
            raise CrawlerError(
                "crawler_conflict", "Reload the crawler before changing its execution grant.", 409
            )
        if row["status"] in TERMINAL_STATES:
            raise CrawlerError("crawler_terminal", "This capture has already stopped permanently.", 409)
        if body["enabled"] and self._worker_state(row)["active"]:
            raise CrawlerError(
                "crawler_busy", "Drain the current worker before authorizing another run.", 409
            )
        now = _now()
        expiry = min(_utc(row["consent_expires_at"]), now + timedelta(seconds=seconds))
        if body["enabled"] and _utc(row["consent_expires_at"]) <= now + timedelta(seconds=15):
            raise CrawlerError(
                "crawler_consent_expired", "The original capture consent is too close to expiry.", 403
            )
        epoch = int(row.get("automation", {}).get("epoch", 0)) + 1
        grant = {
            "schema_version": "skeleton.dragon.crawler_execution_grant.v1",
            "enabled": body["enabled"],
            "state": "authorized" if body["enabled"] else "disabled",
            "epoch": epoch,
            "scope": dict(scope),
            "principal_email": principal["email"].strip().lower(),
            "consent_id": row["consent"]["consent_id"],
            "request_digest": row["request_digest"],
            "authorized_at": now,
            "expires_at": expiry,
            "max_slices": slices,
            "slices_started": 0,
            "next_run_at": now,
            "stop_reason": None if body["enabled"] else "operator_disabled",
        }
        if body["enabled"]:
            await self._grant_principal(scope, grant)
        _, run_type = _core()
        runtime = run_type.from_snapshot(_plain(row["snapshot"]))
        if body["enabled"]:
            if runtime.status()["state"] == "running":
                runtime.pause()
            if runtime.status()["state"] == "paused":
                runtime.resume()
            state = "queued"
        else:
            runtime.pause()
            state = "paused"
        snapshot = runtime.snapshot()
        receipt = await self._admit(
            scope,
            identifier,
            {
                "snapshot": snapshot,
                "grant": {
                    **grant,
                    "authorized_at": now.isoformat(),
                    "expires_at": expiry.isoformat(),
                    "next_run_at": now.isoformat(),
                },
            },
        )
        changed = await self.sessions.update_one(
            {"_id": identifier, **scope, "version": row["version"]},
            {
                "$set": {
                    "automation": grant,
                    "snapshot": snapshot,
                    "status": state,
                    "storage_receipt": receipt,
                    "updated_at": now,
                    (
                        "safety_control"
                        if len(row.get("operations", {})) >= MAX_OPERATIONS
                        else "operations." + operation
                    ): {
                        "operation": operation,
                        "request_digest": digest,
                        "action": "automation",
                        "state": "completed",
                    },
                },
                "$inc": {"version": 1},
            },
        )
        if not changed.modified_count:
            raise CrawlerError("crawler_conflict", "Crawler changed before authorization was committed.", 409)
        if not body["enabled"]:
            await self._drain(row)
        return await self.get(scope, identifier)

    async def control(self, scope: dict[str, str], identifier: str, body: dict) -> dict:
        row = await self._reconcile(scope, await self._owned(scope, identifier))
        operation, digest = _operation(body["idempotency_key"]), _digest(body)
        action = body["action"]
        if self._prior(row, operation, digest, safety=action in {"pause", "cancel"}):
            return self._projection(row)
        if row["version"] != body["expected_version"]:
            raise CrawlerError("crawler_conflict", "Reload the crawler session before changing it.", 409)
        if action == "resume" and self._worker_state(row)["active"]:
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
                    (
                        "safety_control"
                        if len(row.get("operations", {})) >= MAX_OPERATIONS
                        else "operations." + operation
                    ): {
                        "operation": operation,
                        "request_digest": digest,
                        "action": action,
                        "state": "completed",
                    },
                    **(
                        {
                            "automation.enabled": False,
                            "automation.state": "disabled",
                            "automation.stop_reason": "operator_" + action,
                        }
                        if row.get("automation") and action != "resume"
                        else {}
                    ),
                },
                "$inc": {"version": 1},
            },
        )
        if not changed.modified_count:
            raise CrawlerError("crawler_conflict", "Crawler changed while applying the command.", 409)
        if action != "resume":
            await self._drain(row)
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
                        {
                            "$or": [
                                {"$eq": [{"$ifNull": ["$worker_automation_epoch", None]}, None]},
                                {
                                    "$and": [
                                        {"$eq": ["$automation.enabled", True]},
                                        {"$eq": ["$automation.epoch", "$worker_automation_epoch"]},
                                        {
                                            "$gt": [
                                                "$automation.expires_at",
                                                {"$add": ["$$NOW", 15000]} if network_margin else "$$NOW",
                                            ]
                                        },
                                    ]
                                },
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
        if row.get("worker_automation_epoch") is not None:
            grant = row.get("automation", {})
            margin = timedelta(seconds=15 if network_margin else 0)
            if (
                grant.get("enabled") is not True
                or grant.get("epoch") != row["worker_automation_epoch"]
                or grant.get("scope") != scope
                or grant.get("request_digest") != row["request_digest"]
                or grant.get("consent_id") != row["consent"]["consent_id"]
                or not isinstance(grant.get("expires_at"), datetime)
                or _utc(grant["expires_at"]) <= _now() + margin
            ):
                raise CrawlerError(
                    "crawler_grant_expired", "Autonomous capture authority is no longer current.", 403
                )
            await self._grant_principal(scope, grant)
        return row

    async def run(
        self, scope: dict[str, str], identifier: str, body: dict, *, automation_epoch: int | None = None
    ) -> dict:
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
        grant = row.get("automation", {})
        if automation_epoch is None and grant.get("enabled"):
            raise CrawlerError(
                "crawler_automation_active", "Pause autonomous execution before running a manual slice.", 409
            )
        if automation_epoch is not None:
            if (
                grant.get("enabled") is not True
                or grant.get("epoch") != automation_epoch
                or grant.get("scope") != scope
                or grant.get("request_digest") != row["request_digest"]
                or grant.get("consent_id") != row["consent"]["consent_id"]
                or grant.get("slices_started", MAX_AUTO_SLICES) >= grant.get("max_slices", 0)
                or not isinstance(grant.get("expires_at"), datetime)
                or _utc(grant["expires_at"]) <= _now() + timedelta(seconds=15)
            ):
                raise CrawlerError("crawler_grant_expired", "The finite autonomous grant has stopped.", 403)
            await self._grant_principal(scope, grant)
        quota_id, token = _digest(scope), str(uuid4())
        local_credit = await self.limits.find_one({"_id": quota_id, **scope}, {"worker_token": 1})
        local_handle = self._workers.get((local_credit or {}).get("worker_token"))
        if local_handle is not None and not local_handle[1].done():
            raise CrawlerError(
                "crawler_capacity", "The previous local account worker must physically drain.", 429
            )
        if sum(not handle[1].done() for handle in self._workers.values()) >= MAX_CONCURRENT_SLICES:
            raise CrawlerError("crawler_capacity", "Local physical crawler capacity is occupied.", 429)
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
                existing_slot = await self.limits.find_one({"_id": slot}, {"worker_token": 1})
                existing_handle = self._workers.get((existing_slot or {}).get("worker_token"))
                if existing_handle is not None and not existing_handle[1].done():
                    continue
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
        claim = {"_id": identifier, **scope, "version": row["version"], "status": row["status"]}
        if automation_epoch is not None:
            claim.update(
                {
                    "automation.enabled": True,
                    "automation.epoch": automation_epoch,
                    "automation.slices_started": grant["slices_started"],
                    "$expr": {"$gt": ["$automation.expires_at", {"$add": ["$$NOW", 15000]}]},
                }
            )
        changed = await self.sessions.update_one(
            claim,
            {
                "$set": {
                    "status": "running",
                    "worker_token": token,
                    "worker_epoch": epoch,
                    "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                    "updated_at": now,
                    "operations."
                    + operation: {"request_digest": digest, "action": "run", "state": "running"},
                    **(
                        {"worker_automation_epoch": automation_epoch, "automation.state": "running"}
                        if automation_epoch is not None
                        else {}
                    ),
                },
                "$inc": {
                    "version": 1,
                    **(
                        {"automation.slices_started": 1, "automation_slices_total": 1}
                        if automation_epoch is not None
                        else {}
                    ),
                },
                "$unset": {
                    "error": "",
                    **({"worker_automation_epoch": ""} if automation_epoch is None else {}),
                },
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
            await self._live(scope, identifier, token, epoch)
            result = await self.sessions.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "worker_token": token,
                    "worker_epoch": epoch,
                    "status": "running",
                    **(
                        {"automation.enabled": True, "automation.epoch": automation_epoch}
                        if automation_epoch is not None
                        else {}
                    ),
                    "$expr": {
                        "$and": [
                            {"$gt": ["$lease_until", "$$NOW"]},
                            {"$gt": ["$consent_expires_at", "$$NOW"]},
                            *(
                                [{"$gt": ["$automation.expires_at", "$$NOW"]}]
                                if automation_epoch is not None
                                else []
                            ),
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
        self._workers[token] = (cancelled, worker)
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
            current = await self._live(scope, identifier, token, epoch)
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
            automation_update = {}
            if automation_epoch is not None:
                latest_grant = current["automation"]
                stopped = (
                    state in TERMINAL_STATES or latest_grant["slices_started"] >= latest_grant["max_slices"]
                )
                reason = state if state in TERMINAL_STATES else ("slice_budget" if stopped else None)
                if _utc(latest_grant["expires_at"]) <= _now() + timedelta(seconds=15):
                    stopped, reason = True, "authorization_expired"
                ready_at = summary.get("next_ready_at")
                due = _now() + timedelta(seconds=1)
                if isinstance(ready_at, (int, float)):
                    due = max(
                        due,
                        datetime.fromtimestamp(
                            min(ready_at, _utc(latest_grant["expires_at"]).timestamp()), tz=timezone.utc
                        ),
                    )
                automation_update = {
                    "automation.enabled": not stopped,
                    "automation.state": "stopped" if stopped else "waiting",
                    "automation.stop_reason": reason,
                    "automation.next_run_at": due,
                }
            result = await self.sessions.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "version": current["version"],
                    "status": "running",
                    "worker_token": token,
                    "worker_epoch": epoch,
                    **(
                        {"automation.enabled": True, "automation.epoch": automation_epoch}
                        if automation_epoch is not None
                        else {}
                    ),
                    "$expr": {
                        "$and": [
                            {"$gt": ["$lease_until", "$$NOW"]},
                            {"$gt": ["$consent_expires_at", "$$NOW"]},
                            *(
                                [{"$gt": ["$automation.expires_at", "$$NOW"]}]
                                if automation_epoch is not None
                                else []
                            ),
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
                        "last_worker_exit_confirmed": True,
                        **automation_update,
                    },
                    "$inc": {"version": 1},
                    "$unset": {"worker_token": "", "lease_until": "", "worker_automation_epoch": ""},
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
            owned_worker = {"_id": identifier, **scope, "worker_token": token, "worker_epoch": epoch}
            settled = await self.sessions.update_one(
                {**owned_worker, "status": "running"},
                {
                    "$set": {
                        "status": "interrupted",
                        "updated_at": _now(),
                        "operations." + operation: operation_receipt,
                        "last_worker_exit_confirmed": True,
                        "error": {
                            "code": code,
                            "message": "The slice stopped; only accepted checkpoints remain.",
                        },
                    },
                    "$inc": {"version": 1},
                    "$unset": {"worker_token": "", "lease_until": "", "worker_automation_epoch": ""},
                },
            )
            if not settled.matched_count:
                # A safety control may have won while this real worker drained.
                # Preserve its status and grant while settling the old receipt.
                await self.sessions.update_one(
                    {**owned_worker, "status": {"$nin": ["running", "deleted"]}},
                    {
                        "$set": {
                            "updated_at": _now(),
                            "operations." + operation: operation_receipt,
                            "last_worker_exit_confirmed": True,
                        },
                        "$inc": {"version": 1},
                        "$unset": {"worker_token": "", "lease_until": "", "worker_automation_epoch": ""},
                    },
                )
                # Erasure keeps only its tombstone and physical-exit metadata;
                # never recreate an operations journal after source deletion.
                await self.sessions.update_one(
                    {**owned_worker, "status": "deleted"},
                    {
                        "$set": {"last_worker_exit_confirmed": True},
                        "$unset": {"worker_token": "", "lease_until": "", "worker_automation_epoch": ""},
                    },
                )
        finally:
            if worker.done():
                self._workers.pop(token, None)
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
            # Tombstone publication may have succeeded before quota release
            # lost its response. Exact replay must finish that idempotent step.
            await self.limits.update_one(
                {"_id": _digest(scope), **scope}, {"$pull": {"session_ids": identifier}}
            )
            return {
                "ok": True,
                "session_id": identifier,
                "status": "deleted",
                "version": int(row["version"]),
                "worker": await self._drain(row),
            }
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
                    "automation": "",
                    "worker_automation_epoch": "",
                    "safety_control": "",
                },
            },
        )
        if not result.modified_count:
            raise CrawlerError("crawler_conflict", "Crawler changed before source erasure.", 409)
        # A live worker's physical lease is deliberately retained until its
        # actual thread drains; status='deleted' fences its final publication.
        await self.limits.update_one({"_id": _digest(scope), **scope}, {"$pull": {"session_ids": identifier}})
        return {
            "ok": True,
            "session_id": identifier,
            "status": "deleted",
            "version": int(row["version"]) + 1,
            "worker": await self._drain(row),
        }

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
    def _source_use(row: dict) -> None:
        if row["status"] in {"cancelled", "deleted"} or _utc(row["consent_expires_at"]) <= _now():
            raise CrawlerError(
                "crawler_context_revoked",
                "Current capture/use consent is required for source retrieval.",
                403,
            )

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
        self,
        scope: dict[str, str],
        identifier: str,
        *,
        cursor: str | None = None,
        limit: int = 16,
        after_sequence: int | None = None,
    ) -> dict:
        row = await self._owned(scope, identifier)
        self._source_use(row)
        _, run_type = _core()
        runtime = run_type.from_snapshot(_plain(row["snapshot"]))
        sources = runtime.sources()
        snapshot = runtime.snapshot()
        if after_sequence is not None and (
            type(after_sequence) is not int or not 0 <= after_sequence <= snapshot["sequence"]
        ):
            raise CrawlerError(
                "crawler_cursor_invalid", "The source cursor is outside the current capture history.", 409
            )
        events = snapshot["events"]
        truncated = bool(after_sequence is not None and events and after_sequence < events[0]["sequence"] - 1)
        captures = {event["source_id"]: event["sequence"] for event in events if event.get("source_id")}
        if after_sequence is not None and not truncated:
            sources = [source for source in sources if captures.get(source["source_id"], 0) > after_sequence]
        ordered = sorted(sources, key=lambda item: item["source_id"])
        if cursor:
            ordered = [source for source in ordered if source["source_id"] > cursor]
        page = ordered[:limit]
        self._source_use(await self._owned(scope, identifier))
        return {
            "ok": True,
            "sources": [
                {
                    **self._source_projection(source, text=False),
                    "capture_sequence": captures.get(source["source_id"]),
                }
                for source in page
            ],
            "next_cursor": page[-1]["source_id"] if len(ordered) > limit else None,
            "sequence": snapshot["sequence"],
            "version": int(row["version"]),
            "history_truncated": truncated,
            "session_id": identifier,
        }

    async def source(self, scope: dict[str, str], identifier: str, source_id: str) -> dict:
        return (await self.source_evidence(scope, identifier, source_id))["source"]

    async def source_evidence(self, scope: dict[str, str], identifier: str, source_id: str) -> dict:
        row = await self._owned(scope, identifier)
        self._source_use(row)
        _, run_type = _core()
        try:
            source = run_type.from_snapshot(_plain(row["snapshot"])).source_read(source_id)
        except ValueError:
            raise CrawlerError("crawler_source_not_found", "Captured source not found.", 404) from None
        reference = {
            "schema_version": "skeleton.dragon.crawler_reference.v1",
            "session_id": identifier,
            "source_id": source_id,
            "source_digest": _digest(source),
            "request_digest": row["request_digest"],
            "consent_id": row["consent"]["consent_id"],
        }
        await self.assert_context(scope, [reference])
        return {
            "source": self._source_projection(source),
            "reference": reference,
            "valid_until": _utc(row["consent_expires_at"]).isoformat(),
        }

    async def source_chunk(
        self,
        scope: dict[str, str],
        identifier: str,
        source_id: str,
        *,
        offset: int = 0,
        max_chars: int = 8000,
        expected_content_digest: str | None = None,
    ) -> dict:
        if type(offset) is not int or offset < 0 or type(max_chars) is not int or not 1 <= max_chars <= 16000:
            raise CrawlerError("crawler_chunk_bounds", "Source text offsets exceed their finite bounds.")
        evidence = await self.source_evidence(scope, identifier, source_id)
        source = evidence["source"]
        text = source["text"]
        if expected_content_digest is not None and expected_content_digest != source["preserved_text_hash"]:
            raise CrawlerError("crawler_source_changed", "The source content identity differs.", 409)
        if offset > len(text):
            raise CrawlerError("crawler_chunk_bounds", "Source text offset exceeds preserved content.")
        chunk = text[offset : offset + max_chars]
        row = await self._owned(scope, identifier)
        await self.assert_context(scope, [evidence["reference"]])
        return {
            "ok": True,
            "session_id": identifier,
            "source_id": source_id,
            "version": int(row["version"]),
            "offset": offset,
            "end": offset + len(chunk),
            "total_chars": len(text),
            "text": chunk,
            "next_offset": offset + len(chunk) if offset + len(chunk) < len(text) else None,
            "content_digest": source["preserved_text_hash"],
            "chunk_digest": hashlib.sha256(chunk.encode()).hexdigest(),
            "offset_unit": "unicode_code_points",
            "source_classification": "untrusted_external_material",
            "source_url": source["canonical_url"],
            "title": source["title"],
            "captured_at": source["fetched_at"],
        }

    async def search(self, scope: dict[str, str], identifier: str, query: str, *, limit: int = 8) -> dict:
        row = await self._owned(scope, identifier)
        if row["status"] == "cancelled" or _utc(row["consent_expires_at"]) <= _now():
            raise CrawlerError(
                "crawler_context_revoked", "Current capture/use consent is required for retrieval.", 403
            )
        _, run_type = _core()
        runtime = run_type.from_snapshot(_plain(row["snapshot"]))
        evidence = runtime.search(query, limit=limit)
        references = []
        for source_id in dict.fromkeys(hit["source_id"] for hit in evidence["hits"]):
            references.append(
                {
                    "schema_version": "skeleton.dragon.crawler_reference.v1",
                    "session_id": identifier,
                    "source_id": source_id,
                    "source_digest": _digest(runtime.source_read(source_id)),
                    "request_digest": row["request_digest"],
                    "consent_id": row["consent"]["consent_id"],
                }
            )
        await self.assert_context(scope, references)
        return {**evidence, "session_id": identifier, "version": int(row["version"])}

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

    async def _defer_recovery(self, row: dict) -> bool:
        """Rotate a bounded busy/skipped page without changing execution authority."""
        result = await self.sessions.update_one(
            {
                "_id": row["_id"],
                "tenant_id": row["tenant_id"],
                "owner_id": row["owner_id"],
                "version": row["version"],
                "automation.enabled": True,
                "automation.epoch": row["automation"]["epoch"],
                "automation.next_run_at": row["automation"]["next_run_at"],
            },
            {"$set": {"automation.next_run_at": _now() + timedelta(seconds=10)}},
        )
        # Retry scheduling metadata is not a new grant, lease or source revision.
        return bool(result.modified_count)

    async def recover(self, *, limit: int = 16) -> dict:
        """Consume only persisted finite grants in the existing scheduler."""
        if type(limit) is not int or not 1 <= limit <= 16:
            raise ValueError("Crawler recovery scans at most16 records")
        await self.ensure_indexes()
        rows = (
            await self.sessions.find({"automation.enabled": True, "automation.next_run_at": {"$lte": _now()}})
            .sort("automation.next_run_at", ASCENDING)
            .limit(limit)
            .max_time_ms(2000)
            .to_list(length=limit)
        )
        selected, deferred, owners = [], [], set()
        for row in rows:
            owner = (row["tenant_id"], row["owner_id"])
            if owner not in owners and len(selected) < MAX_CONCURRENT_SLICES:
                owners.add(owner)
                selected.append(row)
            else:
                deferred.append(row)
        # Otherwise a page filled by one account remains the oldest page on
        # every sweep, starving due sessions belonging to all other accounts.
        rotations = await asyncio.gather(
            *(self._defer_recovery(row) for row in deferred), return_exceptions=True
        )

        async def pulse(item):
            scope = {key: item[key] for key in ("tenant_id", "owner_id")}
            identifier, epoch = item["_id"], item["automation"]["epoch"]
            try:
                row = await self._reconcile(scope, await self._owned(scope, identifier))
                grant = row.get("automation", {})
                if not grant.get("enabled") or grant.get("epoch") != epoch:
                    return "superseded"
                reason = None
                if row["status"] in TERMINAL_STATES or row["status"] == "paused":
                    reason = row["status"]
                elif _utc(grant["expires_at"]) <= _now() + timedelta(seconds=15):
                    reason = "authorization_expired"
                elif grant["slices_started"] >= grant["max_slices"]:
                    reason = "slice_budget"
                elif len(row.get("operations", {})) >= MAX_OPERATIONS:
                    reason = "command_budget"
                if reason:
                    await self.sessions.update_one(
                        {"_id": identifier, **scope, "automation.epoch": epoch},
                        {
                            "$set": {
                                "automation.enabled": False,
                                "automation.state": "stopped",
                                "automation.stop_reason": reason,
                            },
                            "$inc": {"version": 1},
                        },
                    )
                    return "stopped"
                if self._worker_state(row)["active"]:
                    await self._defer_recovery(row)
                    return "waiting"
                await self._grant_principal(scope, grant)
                _, run_type = _core()
                ready = run_type.from_snapshot(_plain(row["snapshot"])).status()["next_ready_at"]
                if ready is not None and ready > _now().timestamp():
                    await self.sessions.update_one(
                        {"_id": identifier, **scope, "version": row["version"], "automation.epoch": epoch},
                        {
                            "$set": {
                                "automation.next_run_at": datetime.fromtimestamp(
                                    min(ready, _utc(grant["expires_at"]).timestamp()), tz=timezone.utc
                                ),
                                "automation.state": "waiting",
                            },
                            "$inc": {"version": 1},
                        },
                    )
                    return "waiting"
                body = {
                    "expected_version": int(row["version"]),
                    "idempotency_key": f"autonomous:{epoch}:{grant['slices_started'] + 1}",
                    "max_steps": 4,
                }
                result = await self.run(scope, identifier, body, automation_epoch=epoch)
                return "executed" if result.get("ok") else "interrupted"
            except CrawlerError as exc:
                retry = exc.status in {409, 429, 503} and exc.code not in {
                    "crawler_integrity",
                    "crawler_grant_revoked",
                }
                await self.sessions.update_one(
                    {"_id": identifier, **scope, "automation.epoch": epoch, "automation.enabled": True},
                    {
                        "$set": {
                            "automation.next_run_at": _now() + timedelta(seconds=10),
                            "automation.enabled": retry,
                            "automation.state": "waiting" if retry else "blocked",
                            "automation.stop_reason": exc.code,
                        },
                        "$inc": {"version": 1},
                    },
                )
                return "waiting" if retry else "blocked"
            except (ValueError, TypeError, KeyError):
                # Old/invalid runtime or grant evidence never gets silently upgraded.
                await self.sessions.update_one(
                    {"_id": identifier, **scope, "automation.epoch": epoch},
                    {
                        "$set": {
                            "automation.enabled": False,
                            "automation.state": "blocked",
                            "automation.stop_reason": "crawler_integrity",
                        },
                        "$inc": {"version": 1},
                    },
                )
                return "blocked"

        outcomes = await asyncio.gather(*(pulse(row) for row in selected), return_exceptions=True)
        result = {
            "scanned": len(rows),
            "selected": len(selected),
            "deferred": sum(value is True for value in rotations),
            "executed": 0,
            "waiting": 0,
            "stopped": 0,
            "blocked": 0,
            "interrupted": 0,
            "superseded": 0,
            "failures": 0,
        }
        for value in outcomes:
            result[value if isinstance(value, str) and value in result else "failures"] += 1
        return result


crawler_application = DragonCrawlerApplication()


async def recover_crawler_runs(*, limit: int = 16) -> dict:
    return await crawler_application.recover(limit=limit)


async def read_crawler_context(user: dict, query: str, max_docs: int = 4, max_chars: int = 16000) -> dict:
    return await crawler_application.context(authenticated_scope(user), query, max_docs, max_chars)


async def assert_crawler_context(user: dict, references: list[dict]) -> None:
    await crawler_application.assert_context(authenticated_scope(user), references)
