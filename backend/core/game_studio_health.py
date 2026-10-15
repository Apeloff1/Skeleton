"""Observed studio readiness through existing application and engine owners.

This is a read-only projection: it never installs tools, admits content, invents
model availability or exposes operator paths/credentials. Configuration presence
and an actual current probe are distinct fields.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import datetime, timezone

from core.game_learning import workspace

_probes = {}


async def _bounded_probe(identifier, function, pending):
    """Join one derived probe without allowing refreshes to multiply workers."""
    prior = _probes.get(identifier)
    if prior and prior.get("finished_at") is not None and time.monotonic() - prior["finished_at"] < 30:
        return prior["result"]
    if prior is None or prior.get("finished_at") is not None:
        prior = {"task": asyncio.create_task(asyncio.to_thread(function))}
        _probes[identifier] = prior

        def completed(task):
            try:
                result = task.result()
            except (Exception, asyncio.CancelledError):
                result = pending
            if isinstance(result, dict):
                result = {
                    **result,
                    "observed": result is not pending,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
            prior.update(result=result, finished_at=time.monotonic())

        prior["task"].add_done_callback(completed)
    try:
        await asyncio.wait_for(asyncio.shield(prior["task"]), timeout=4)
    except (Exception, asyncio.CancelledError):
        if asyncio.current_task().cancelling():
            raise
        return pending
    return prior.get("result", pending)


async def _native_probe():
    from skeleton.jeeves.game_emulator_catalog import canonical_targets

    return await _bounded_probe(
        "native",
        _native,
        {
            "approved": 0,
            "mapped_targets": 0,
            "total_targets": len(canonical_targets()),
            "observed": False,
            "error": "native_probe_pending",
        },
    )


async def _toolchain_probe():
    return await _bounded_probe(
        "toolchains",
        _toolchains,
        [
            {
                "id": "compiler_probe",
                "status": "unavailable",
                "message": "Compiler prerequisites are still being inspected. Refresh joins the same bounded diagnostic work.",
            }
        ],
    )


async def _storage():
    from core.conversations import conversation_authority

    connected = False
    try:
        await asyncio.wait_for(workspace.database.command("ping"), timeout=2)
        connected = True
    except Exception:
        pass
    return {
        "connected": connected,
        "admitter_configured": conversation_authority.storage_admitter is not None,
    }


async def _model():
    from core.engine_client import EngineClient, EngineClientError

    try:
        client = EngineClient.from_env()
    except (EngineClientError, ValueError):
        return {
            "configured": True,
            "reachable": False,
            "available": None,
            "error": "engine_configuration_invalid",
        }
    if client is None:
        return {"configured": False, "reachable": None, "available": None}
    try:
        observed = await asyncio.wait_for(client.provider_status(), timeout=3)
        return {
            "configured": True,
            "reachable": True,
            "available": observed["available"],
            "provider": observed["active"],
        }
    except Exception:
        return {
            "configured": True,
            "reachable": False,
            "available": None,
            "error": "engine_status_unavailable",
        }


def _native():
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, canonical_targets

    try:
        registry = GameEmulatorRegistry.from_environment()
        rows = registry.catalog()
        approved = {row["core"]["core_id"] for row in rows if row["available"]}
        return {
            "approved": len(approved),
            "mapped_targets": sum(row["available"] for row in rows),
            "total_targets": len(rows),
            "registry_digest": registry.registry_digest,
        }
    except Exception:
        return {
            "approved": 0,
            "mapped_targets": 0,
            "total_targets": len(canonical_targets()),
            "error": "emulator_registry_unavailable",
        }


def _toolchains():
    from skeleton.jeeves.game_console_build import ConsoleBuildError, console_build_catalog

    try:
        rows = console_build_catalog()
    except (ConsoleBuildError, OSError, ValueError):
        return [
            {
                "id": "operator_configuration",
                "status": "blocked",
                "message": "The trusted compiler/SDK configuration is invalid or unavailable; configure the existing operator roots before building.",
            }
        ]
    grouped = {}
    for row in rows:
        key = row["toolchain"]
        bucket = grouped.setdefault(key, [])
        bucket.append(row)
    result = []
    for identifier, group in sorted(grouped.items()):
        ready = sum(row["state"] == "build_available_unexecuted" for row in group)
        states = Counter(row["state"] for row in group)
        result.append(
            {
                "id": identifier,
                "status": "ready" if ready else "blocked",
                "message": f"{ready} of {len(group)} registered target profiles have observed build prerequisites; compilation is a separate operation.",
                "ready_targets": ready,
                "total_targets": len(group),
                "states": dict(states),
            }
        )
    return result[:64]


async def _workers(scope, connected):
    from core.scheduler import scheduler_status
    from core.game_play import resource_profiles

    resources = resource_profiles()["profiles"][0]
    capacity, active_jobs, active_plays = resources["combined_instance_capacity"], None, None
    if connected:
        active_jobs, active_plays = await asyncio.gather(
            workspace.jobs.count_documents({**scope, "status": {"$in": ["queued", "running"]}}),
            workspace.database["game_learning_plays"].count_documents(
                {**scope, "status": {"$in": ["queued", "starting", "running", "paused", "stopping"]}}
            ),
        )
    scheduler = scheduler_status()
    return {
        "capacity": capacity,
        "active_jobs": active_jobs,
        "active_plays": active_plays,
        "recovery_scheduler_running": bool(
            scheduler["running"] and any(row["id"] == "studio_campaign_recovery" for row in scheduler["jobs"])
        ),
        "configured_job_slots": 2,
        "global_actor_safety_ceiling": 8,
        "max_training_workers": resources["max_training_workers"],
        "max_live_plays": resources["max_live_plays"],
        "effective_cpu_count": resources["effective_cpu_count"],
        "shared_single_capacity": resources["shared_single_capacity"],
        "counts_scope": "authenticated_owner",
    }


def _rows(rows, identity, fields):
    return [{identity: row[identity], **{key: row[key] for key in fields if key in row}} for row in rows]


async def _project_scope(scope, project_id):
    project = await workspace._project(project_id, scope)
    # Issued membership is necessary; prepared orphan records are not activities.
    jobs, plays, goals, campaigns = await asyncio.gather(
        workspace.jobs.find(
            {
                **scope,
                "project_id": project_id,
                "job_id": {"$in": project["job_ids"]},
                "status": {"$in": ["queued", "running", "interrupted"]},
            }
        )
        .sort("updated_at", -1)
        .limit(16)
        .to_list(16),
        workspace.database["game_learning_plays"]
        .find(
            {
                **scope,
                "project_id": project_id,
                "play_id": {"$in": project.get("play_ids", [])},
                "status": {"$in": ["queued", "starting", "running", "paused", "stopping", "interrupted"]},
            }
        )
        .sort("updated_at", -1)
        .limit(16)
        .to_list(16),
        workspace.revisions.find(
            {
                **scope,
                "project_id": project_id,
                "kind": "studio_agent_goal",
                "status": {"$nin": ["completed", "cancelled", "expired", "planned"]},
            }
        )
        .sort("updated_at", -1)
        .limit(16)
        .to_list(16),
        workspace.database["game_learning_campaigns"]
        .find({**scope, "project_id": project_id, "status": {"$nin": ["completed", "cancelled"]}})
        .sort("updated_at", -1)
        .limit(16)
        .to_list(16),
    )
    return {
        "project_id": project_id,
        "version": project["version"],
        "active_jobs": _rows(jobs, "job_id", ("kind", "status", "progress", "worker_epoch")),
        "active_plays": _rows(plays, "play_id", ("status", "steps", "controller", "control_version")),
        "goals": _rows(
            goals,
            "goal_id",
            ("status", "version", "cursor", "max_steps", "pending_job_id", "pending_play_id"),
        ),
        "campaigns": _rows(
            campaigns, "campaign_id", ("status", "version", "cursor", "round_limit", "active_job_id")
        ),
    }


async def readiness(scope, project_id=None):
    scope = workspace._scope(scope["tenant_id"], scope["owner_id"])
    storage, model, native, toolchains = await asyncio.gather(
        _storage(), _model(), _native_probe(), _toolchain_probe()
    )
    checks = [
        {
            "id": "core_storage",
            "label": "Studio database",
            "status": "ready" if storage["connected"] else "blocked",
            "message": (
                "Existing CORE_DB responded to a current probe."
                if storage["connected"]
                else "The existing studio database did not respond."
            ),
            "setup": "Configure MONGO_URL and DB_NAME on the existing backend.",
        },
        {
            "id": "storage_admission",
            "label": "Governed studio writes",
            "status": "ready" if storage["admitter_configured"] and model["reachable"] else "blocked",
            "message": (
                "Canonical engine storage admission is configured and its status endpoint responded; individual writes still require admission."
                if storage["admitter_configured"] and model["reachable"]
                else "Studio writes require the existing canonical engine admission service."
            ),
            "setup": "Set SKELETON_INTERNAL_URL and the same SKL_ENGINE_SERVICE_TOKEN/principal before backend startup.",
        },
        {
            "id": "model",
            "label": "Jeeves model execution",
            "status": "ready" if model.get("available") else "blocked",
            "message": (
                "The canonical engine reports an available provider; a particular goal remains a separate admitted execution."
                if model.get("available")
                else "The canonical model service is unconfigured, unavailable or not currently observed."
            ),
            "setup": "Configure an approved provider on the canonical engine, or select one valid digest-pinned local artifact/deployment.",
        },
        {
            "id": "native_emulators",
            "label": "Native cartridge execution",
            "status": "ready" if native["mapped_targets"] else "unavailable",
            "message": (
                f"{native['mapped_targets']} of {native['total_targets']} hardware targets have observed approved core mappings; title compatibility is checked during actual execution."
                if native.get("observed", True)
                else "Native core availability is still being inspected; no count has been established."
            ),
            "setup": "Install and explicitly approve legitimate cores/firmware using the existing operator installer.",
        },
        {
            "id": "native_builds",
            "label": "Console toolchains",
            "status": "ready" if any(row["status"] == "ready" for row in toolchains) else "unavailable",
            "message": "Readiness comes from current fixed compiler/SDK/sandbox prerequisites, not source catalogue membership.",
            "setup": "Configure trusted console SDK roots and the mandatory sandbox using the existing operator toolchain installer.",
        },
    ]
    worker = await _workers(scope, storage["connected"])
    checks.append(
        {
            "id": "campaign_recovery",
            "label": "Authorized campaign recovery",
            "status": "ready" if worker["recovery_scheduler_running"] else "unavailable",
            "message": (
                "The existing scheduler has a bounded campaign recovery job."
                if worker["recovery_scheduler_running"]
                else "Automatic recovery is not currently running in this backend process; explicit campaign controls remain separate."
            ),
        }
    )
    ready = sum(row["status"] == "ready" for row in checks)
    result = {
        "schema_version": "skeleton.game.studio_readiness.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready == len(checks) else "partial" if ready else "blocked",
        "checks": checks,
        "storage": storage,
        "model": model,
        "native_cores": native,
        "toolchains": toolchains,
        "worker": worker,
    }
    if project_id is not None:
        result["project_scope"] = await _project_scope(scope, project_id)
    return result
