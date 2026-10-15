"""Authenticated live play over process-isolated canonical Jeeves adapters.

Mongo owns input, consent, snapshots and worker fences. Process queues and frame
rings are execution/delivery projections. No user executable or provider client
is admitted by this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import multiprocessing
import os
import queue
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

from core.game_learning_events import FrameCursorError, frame_hub


def _now():
    return datetime.now(timezone.utc)


def _encoded(value, limit=8 * 1024 * 1024):
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    if len(data) > limit:
        raise ValueError("live play payload exceeds byte limit")
    return data


def _error(code, message, status=409):
    from core.game_learning import GameLearningError

    return GameLearningError(code, message, status)


def resource_profiles():
    cpus = os.cpu_count() or 1
    effective = cpus
    affinity = getattr(os, "sched_getaffinity", None)
    if callable(affinity):
        try:
            effective = min(effective, max(1, len(affinity(0))))
        except OSError:
            pass
    memory = None
    try:
        fields = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if fields[0] != "max":
            effective = min(effective, max(1, int(fields[0]) // int(fields[1])))
        raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if raw != "max":
            memory = int(raw)
    except (OSError, ValueError, IndexError, ZeroDivisionError):
        pass
    # Reserve512MiB for the application when a memory quota
    # exists, then partition one physical-instance budget between both owners.
    capacity = effective
    if memory is not None:
        capacity = min(capacity, max(0, (memory - 512 * 1024 * 1024) // (2 * 1024**3)))
    actors = min(8, max(1, capacity - 1)) if capacity else 0
    live = min(4, max(1, capacity - actors)) if capacity else 0
    shared = capacity == 1
    result = {
        "profiles": [
            {
                "profile_id": "cpu",
                "label": "Bounded CPU workers",
                "host_cpu_count": cpus,
                "effective_cpu_count": effective,
                "memory_limit_bytes": memory,
                "max_training_workers": actors,
                "max_live_plays": live,
                "available": capacity > 0,
                "readiness": {
                    "code": ("cpu_memory_ready" if capacity else "native_memory_capacity_unavailable"),
                    "message": (
                        "Native-compatible CPU/memory admission is available"
                        if capacity
                        else "At least2GiB per native instance plus512MiB application reserve is required"
                    ),
                },
                "combined_instance_capacity": min(capacity, actors + live),
                "shared_single_capacity": shared,
                "global_actor_safety_ceiling": 8,
                "instance_memory_allowance_bytes": 2 * 1024**3,
                "capacity_scope": "Observed CPU/quota and conservative memory admission; no strict cgroup or FPS guarantee",
            }
        ],
        "gpu_available": False,
        "interactive_capacity_reserved": capacity > 1,
    }
    balanced = result["profiles"][0]
    actor_credits = ["game-learning-actor:" + str(index) for index in range(actors)]
    balanced["training_credit_ids"] = actor_credits
    balanced["interactive_capacity_reserved"] = capacity > 1
    # Borrow the SAME live-play credits when the operator explicitly selects
    # throughput. Inventing actor:N slots here would overbook a running player.
    borrowed = [] if shared else ["game-learning-play:" + str(index) for index in range(live)]
    throughput_credits = (actor_credits + borrowed)[: min(8, balanced["combined_instance_capacity"])]
    if len(throughput_credits) > actors:
        result["profiles"].append(
            {
                **balanced,
                "profile_id": "cpu_throughput",
                "label": "Training throughput — borrow idle play slots",
                "max_training_workers": len(throughput_credits),
                "training_credit_ids": throughput_credits,
                "interactive_capacity_reserved": False,
                "readiness": {
                    **balanced["readiness"],
                    "message": "Uses existing CPU/memory credits including idle play slots. Active human play retains its credit; new live play may wait for training to finish.",
                },
            }
        )
    return result


def _worker(request, options, commands, outputs, stopped):
    # Spawn imports this module without database/configuration imports. Strip
    # credentials before importing the canonical environment or native core.
    allow = {
        "PATH",
        "PYTHONPATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMPDIR",
        "SKL_GAME_EMULATOR_REGISTRY",
    }
    for name in tuple(os.environ):
        if name not in allow:
            os.environ.pop(name, None)
    try:
        import resource

        if os.name == "posix":
            os.setsid()
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        native = isinstance(request, dict) and request.get("kind") == "libretro"
        # Keep supervisor soft bounds, while allowing the existing isolated
        # native worker to apply its own declared hard limits after exec.
        resource.setrlimit(resource.RLIMIT_CPU, (900, 3600 if native else 900))
        resource.setrlimit(
            resource.RLIMIT_AS,
            (1536 * 1024 * 1024, (2048 if native else 1536) * 1024 * 1024),
        )
    except (ImportError, OSError, ValueError):
        pass
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_learning_demonstrations import (
        GameDemonstration,
        GameDemonstrationRecorder,
        current_observation,
    )
    from skeleton.jeeves.game_learning import GamePolicyLearner

    def emit(kind, payload):
        _encoded(payload)
        while not stopped.is_set():
            try:
                outputs.put({"kind": kind, "payload": payload}, timeout=0.1)
                return
            except queue.Full:
                continue

    try:
        environment_request = GameEnvironmentRequest.from_dict(request)
        env = environment_request.build(cancel=stopped.is_set)
        observation = dict(env.reset(options["seed"]))
        if options.get("snapshot") is not None:
            observation = current_observation(env, env.restore(options["snapshot"]))
        controller, epoch = options["controller"], options["controller_epoch"]
        policy = (
            GamePolicyLearner.from_snapshot(options["policy"], expected_spec=env.spec)
            if options.get("policy")
            else None
        )
        recording, recorder = options.get("recording"), None
        if recording:
            recorder = GameDemonstrationRecorder(
                env.spec,
                episode_id=recording["episode_id"],
                seed=recording["seed"],
                source_lineage=recording["source_lineage"],
                actor_id=recording["actor_id"],
                consent_ref=recording["consent_ref"],
                initial_observation=recording["initial_observation"],
                start_snapshot=recording.get("start_snapshot"),
            )
            for row in recording["transitions"]:
                recorder.append(
                    row["action"],
                    row["next_observation"],
                    row["reward_components"],
                    row["terminated"],
                    row["truncated"],
                    info=row.get("info"),
                    transition_digest=row.get("transition_digest"),
                )
        replay = options.get("replay")
        replay_rows = []
        if replay:
            demonstration = GameDemonstration.from_dict(replay)

            def replay_authorize():
                if stopped.is_set() or options.get("replay_authority") != {
                    key: replay[key] for key in ("actor_id", "consent_ref", "demonstration_digest")
                }:
                    raise ValueError("canonical recording consent or worker authority was lost")

            demonstration.verify(environment_request, cancel=stopped.is_set, authorize=replay_authorize)
            if replay.get("start_snapshot") is not None:
                observation = current_observation(env, env.restore(replay["start_snapshot"]))
            replay_rows = replay["trace"]["transitions"]
            controller = "replay"
        held, paused, sequence = None, False, 0
        steps, reward = options.get("steps", 0), options.get("reward", 0.0)
        last_input, last_checkpoint, started = time.monotonic(), time.monotonic(), time.monotonic()
        acknowledged = options.get("input_sequence", 0)

        def checkpoint():
            emit(
                "checkpoint",
                {
                    "snapshot": env.snapshot(),
                    "observation": observation,
                    "steps": steps,
                    "reward": reward,
                    "recording": recording,
                    "input_sequence_ack": acknowledged,
                    "controller_epoch": epoch,
                },
            )

        def finish_recording():
            nonlocal recording, recorder
            if recording is not None:
                if recording["transitions"]:
                    emit(
                        "recording",
                        {
                            "recording_id": recording["recording_id"],
                            "demonstration": recorder.finish(
                                collection_stopped=not (
                                    recording["transitions"][-1]["terminated"]
                                    or recording["transitions"][-1]["truncated"]
                                )
                            ).as_dict(),
                        },
                    )
                else:
                    emit("recording_empty", {"recording_id": recording["recording_id"]})
                recording, recorder = None, None

        emit(
            "started",
            {
                "environment": env.spec.as_dict(),
                "observation": observation,
                "actions": list(env.spec.actions),
            },
        )
        emit(
            "frame",
            {
                "worker_frame_sequence": sequence,
                "frame": env.preview(),
                "observation": observation,
                "steps": steps,
                "reward": reward,
                "controller": controller,
                "controller_epoch": epoch,
                "input_sequence_ack": acknowledged,
            },
        )
        checkpoint()
        while not stopped.is_set() and time.monotonic() - started < 900:
            tick = time.monotonic()
            for _ in range(32):
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                if command["kind"] == "control":
                    if command["controller_epoch"] < epoch:
                        continue
                    if command["action"] == "stop":
                        stopped.set()
                        break
                    if command["action"] == "pause":
                        paused, held = True, None
                    elif command["action"] == "resume":
                        paused = False
                    elif command["action"] == "takeover":
                        finish_recording()
                        controller, epoch = command["controller"], command["controller_epoch"]
                        held, acknowledged = None, 0
                        policy = (
                            GamePolicyLearner.from_snapshot(command["policy"], expected_spec=env.spec)
                            if command.get("policy")
                            else None
                        )
                    emit("control_ack", {"command_id": command["command_id"], "controller_epoch": epoch})
                elif (
                    command["kind"] == "input"
                    and controller == "human"
                    and command["controller_epoch"] == epoch
                ):
                    if command["input_sequence"] <= acknowledged:
                        continue
                    if command["action"] not in env.spec.actions:
                        raise ValueError("input action is not declared by actual environment")
                    held = (
                        command["action"]
                        if command["held"]
                        else (None if held == command["action"] else held)
                    )
                    acknowledged, last_input = command["input_sequence"], time.monotonic()
                    emit("input_ack", {"input_sequence": acknowledged, "controller_epoch": epoch})
                elif (
                    command["kind"] == "record_start"
                    and controller == "human"
                    and command["controller_epoch"] == epoch
                    and recording is None
                ):
                    recording = {
                        **command["recording"],
                        "start_snapshot": env.snapshot(),
                        "initial_observation": observation,
                        "transitions": [],
                    }
                    recorder = GameDemonstrationRecorder(
                        env.spec,
                        episode_id=recording["episode_id"],
                        seed=recording["seed"],
                        source_lineage=recording["source_lineage"],
                        actor_id=recording["actor_id"],
                        consent_ref=recording["consent_ref"],
                        initial_observation=observation,
                        start_snapshot=recording["start_snapshot"],
                    )
                    emit("recording_started", {"recording_id": recording["recording_id"]})
                    checkpoint()
                elif (
                    command["kind"] == "record_stop"
                    and recording
                    and command["recording_id"] == recording["recording_id"]
                ):
                    finish_recording()
                    checkpoint()
            if stopped.is_set():
                break
            if paused:
                stopped.wait(0.05)
                if time.monotonic() - last_checkpoint >= 1:
                    checkpoint()
                    last_checkpoint = time.monotonic()
                continue
            if held is not None and time.monotonic() - last_input > 2:
                held = None
            if controller == "replay":
                if sequence >= len(replay_rows):
                    break
                action = replay_rows[sequence]["action"]
            elif controller == "ai":
                if policy is None:
                    raise ValueError("AI controller requires an admitted policy")
                action = policy.predict(observation)["action"]
            else:
                action = held or env.spec.actions[0]
            outcome = env.step(action)
            next_observation = dict(outcome.observation)
            components = dict(outcome.reward_components)
            if controller == "replay":
                expected = replay_rows[sequence]
                if (
                    next_observation != expected["next_observation"]
                    or components != expected["reward_components"]
                ):
                    raise ValueError("actual demonstration replay differs from recorded observation/reward")
            if recorder is not None:
                transition = {
                    "action": action,
                    "next_observation": next_observation,
                    "reward_components": components,
                    "terminated": outcome.terminated,
                    "truncated": outcome.truncated,
                    "info": dict(outcome.info),
                    "transition_digest": outcome.transition_digest,
                }
                _encoded(
                    {**recording, "transitions": recording["transitions"] + [transition]}, 2 * 1024 * 1024
                )
                recorder.append(
                    action,
                    next_observation,
                    components,
                    outcome.terminated,
                    outcome.truncated,
                    info=transition["info"],
                    transition_digest=transition["transition_digest"],
                )
                recording["transitions"].append(transition)
            observation = next_observation
            steps += 1
            reward += outcome.reward
            sequence += 1
            emit(
                "frame",
                {
                    "worker_frame_sequence": sequence,
                    "frame": env.preview(),
                    "observation": observation,
                    "steps": steps,
                    "reward": reward,
                    "action": action,
                    "controller": controller,
                    "controller_epoch": epoch,
                    "input_sequence_ack": acknowledged,
                    "terminated": outcome.terminated,
                    "truncated": outcome.truncated,
                },
            )
            if time.monotonic() - last_checkpoint >= 1 or outcome.terminated or outcome.truncated:
                checkpoint()
                last_checkpoint = time.monotonic()
            if outcome.terminated or outcome.truncated:
                break
            stopped.wait(max(0, 1 / options["fps"] - (time.monotonic() - tick)))
        # Do not suppress the final actual receipt merely because stop was requested.
        stopped.clear()
        finish_recording()
        checkpoint()
        emit("terminal", {"state": "stopped", "steps": steps, "reward": reward, "observation": observation})
    except BaseException as exc:
        code = getattr(exc, "code", None)
        if (
            not isinstance(code, str)
            or not 1 <= len(code) <= 80
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in code)
        ):
            code = "play_worker_rejected"
        try:
            outputs.put(
                {
                    "kind": "failed",
                    "payload": {"code": code, "error_type": type(exc).__name__},
                },
                timeout=1,
            )
        except queue.Full:
            pass
    finally:
        if "env" in locals() and callable(getattr(env, "close", None)):
            env.close()


class GamePlayAuthority:
    def __init__(self, workspace):
        self.workspace = workspace
        self.plays = workspace.database["game_learning_plays"]
        self.recordings = workspace.database["game_learning_recordings"]
        self.frames = workspace.database["game_learning_live_frames"]
        self.workers = workspace.database["game_learning_workers"]
        self.tasks: dict[str, asyncio.Task] = {}
        self.stops = {}
        self.commands = {}
        self.host_id = str(uuid4())
        self._indexes = False

    async def indexes(self):
        if self._indexes:
            return
        await self.plays.create_index([("tenant_id", 1), ("owner_id", 1), ("project_id", 1)])
        await self.recordings.create_index([("tenant_id", 1), ("owner_id", 1), ("project_id", 1)])
        await self.frames.create_index("expires_at", expireAfterSeconds=0)
        self._indexes = True

    async def _read(self, scope, identifier, *, authorize=True):
        row = await self.plays.find_one({"_id": identifier, **scope})
        if row is None:
            raise _error("play_not_found", "Play session not found.", 404)
        if (
            row["status"] in {"starting", "running", "paused", "stopping"}
            and row.get("lease_until") is not None
        ):
            lease = (
                row["lease_until"].replace(tzinfo=timezone.utc)
                if row["lease_until"].tzinfo is None
                else row["lease_until"]
            )
            if lease < _now():
                await self.plays.update_one(
                    {
                        "_id": identifier,
                        **scope,
                        "worker_token": row.get("worker_token"),
                        "lease_until": row["lease_until"],
                    },
                    {
                        "$set": {"status": "interrupted", "updated_at": _now()},
                        "$unset": {"worker_token": "", "lease_until": ""},
                    },
                )
                row = await self.plays.find_one({"_id": identifier, **scope})
        if authorize:
            await self.workspace._authority(scope, row["input"])
        return row

    @staticmethod
    def public(row, token=None):
        result = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
            and key
            not in {
                "tenant_id",
                "owner_id",
                "input",
                "request",
                "request_digest",
                "worker_token",
                "lease_until",
                "policy",
                "snapshot",
                "replay",
            }
        }
        for key, value in tuple(result.items()):
            if isinstance(value, datetime):
                result[key] = (
                    value.replace(tzinfo=timezone.utc).isoformat()
                    if value.tzinfo is None
                    else value.isoformat()
                )
        result["input_sequence"] = row.get("_last_input_sequence", 0)
        result["capabilities"] = {"held_buttons": True, "keyboard": True, "gamepad": True, "max_fps": 30}
        if token:
            result["control_token"] = token
        result["resume_available"] = (
            row["status"] == "interrupted"
            and row.get("snapshot") is not None
            and not row.get("cancel_requested")
        )
        return result

    async def create(self, scope, project_id, body, *, replay=None):
        from core.game_learning import _digest, _key

        await self.indexes()
        project = await self.workspace._project(project_id, scope, body["expected_version"])
        identifier = _key(project_id, "play", body["idempotency_key"])
        request_digest = _digest(body)
        previous = await self.plays.find_one({"_id": identifier, **scope})
        if previous is not None:
            if previous["request_digest"] != request_digest:
                raise _error("idempotency_conflict", "Play key binds different controls.")
            await self._schedule(identifier, scope)
            return self.public(previous)
        if not resource_profiles()["profiles"][0]["available"]:
            raise _error(
                "play_capacity", "Current CPU/memory budget cannot admit a native-compatible instance.", 429
            )
        binding = await self.workspace._input(
            scope, project, source_id=body.get("source_id"), episode_steps=body.get("max_steps", 4096)
        )
        request = await self.workspace.environment_request(scope, binding)
        keyboard_bindings = None
        if request["kind"] == "console_editor":
            from skeleton.jeeves.game_console_editor import ConsoleProject

            authored = ConsoleProject.from_files(request["tree"], target_id=request["target_id"])
            keyboard_bindings = authored.as_dict()["controls"]["bindings"]
        # The parent validates identity; actual emulator execution remains in the child.
        policy = None
        if body.get("controller", "human") == "ai":
            if not body.get("policy_id"):
                raise _error("policy_required", "Choose an admitted policy before AI takeover.")
            saved = await self.workspace._admitted_policy(scope, project_id, body["policy_id"])
            policy = saved["snapshot"]
            binding["episode_steps"] = min(
                binding["episode_steps"], policy["environment"]["max_episode_steps"]
            )
            request = await self.workspace.environment_request(scope, binding)
            binding["generation_policy"] = {
                "policy_id": body["policy_id"],
                "snapshot_digest": policy["snapshot_digest"],
            }
        if replay:
            binding["demonstrations"] = [
                {
                    "recording_id": replay["consent_ref"].split("//", 1)[1],
                    "demonstration_digest": replay["demonstration_digest"],
                }
            ]
            await self.workspace._demonstration_authority(scope, binding)
        # Current version/epoch/tree SHA authorize an immutable executable
        # request; retaining the same full source graph twice exceeds Mongo's
        # document budget for valid large console projects.
        binding.pop("files")
        binding["files_omitted"] = True
        if len(project.get("play_ids", [])) >= 32:
            raise _error("play_limit", "This project has reached its 32-session play limit.", 413)
        active = await self.plays.count_documents(
            {**scope, "status": {"$in": ["queued", "starting", "running", "paused", "stopping"]}}
        )
        if active >= 4:
            raise _error("active_play_limit", "Stop another live play session before starting this one.", 429)
        token = secrets.token_urlsafe(32)
        stamp = _now()
        row = {
            "_id": identifier,
            **scope,
            "play_id": identifier,
            "project_id": project_id,
            "status": "queued",
            "input": binding,
            "request": request,
            "request_digest": request_digest,
            "execution_kind": request["kind"],
            "source_id": binding.get("source_id"),
            "compiled_artifact": binding.get("compiled_artifact"),
            "keyboard_bindings": keyboard_bindings,
            "control_version": 1,
            "controller_epoch": 1,
            "controller": "replay" if replay else body.get("controller", "human"),
            "policy_id": body.get("policy_id"),
            "policy": policy,
            "fps": body.get("fps", 15),
            "seed": body.get("seed", 0),
            "steps": 0,
            "reward": 0.0,
            "frame_sequence": 0,
            "stream_id": str(uuid4()),
            "created_at": stamp,
            "updated_at": stamp,
            "cancel_requested": False,
            "_control_token": hashlib.sha256(token.encode()).hexdigest(),
            "_last_input_sequence": 0,
            "_last_input_digest": None,
            "_pending": [],
            "_recording": None,
            "snapshot": None,
            "replay": replay,
            "input_version": project["version"],
        }
        await self.workspace._admit(
            scope,
            "game-learning-live-play",
            identifier,
            len(_encoded({"input": binding, "request": request, "policy": policy})),
        )
        await self.plays.update_one({"_id": identifier}, {"$setOnInsert": row}, upsert=True)
        issued = await self.plays.find_one({"_id": identifier, **scope})
        if issued["request_digest"] != request_digest:
            raise _error("idempotency_conflict", "Play key already binds another request.")
        changed = await self.workspace.projects.update_one(
            {
                "_id": project_id,
                **scope,
                "version": project["version"],
                "_input_epoch": binding["input_epoch"],
                "play_ids": {"$ne": identifier},
                "play_ids.31": {"$exists": False},
            },
            {"$push": {"play_ids": identifier}},
        )
        if not changed.modified_count:
            current = await self.workspace._project(project_id, scope)
            if identifier not in current.get("play_ids", []):
                raise _error("project_conflict", "Project changed before live play admission.")
        await self._schedule(identifier, scope)
        return self.public(issued, token)

    async def get(self, scope, identifier):
        row = await self._read(scope, identifier)
        projection = await self.frames.find_one(
            {
                "_id": "play:" + identifier,
                **scope,
                "stream_id": row["stream_id"],
                "expires_at": {"$gt": _now()},
            }
        )
        public = self.public(row)
        if projection:
            payload = projection["event"]["payload"]
            public.update(
                latest_frame=payload.get("frame"),
                observation=payload.get("observation"),
                steps=payload.get("steps"),
                reward=payload.get("reward"),
                frame_sequence=projection["event"]["sequence"],
            )
        return public

    async def _schedule(self, identifier, scope):
        if identifier not in self.tasks and len(self.tasks) < 8:
            row = await self.plays.find_one(
                {"_id": identifier, **scope, "status": "queued", "cancel_requested": False}
            )
            if row is None:
                return
            task = asyncio.create_task(self._run(identifier, scope))
            self.tasks[identifier] = task

            def finished(completed):
                self.tasks.pop(identifier, None)
                if not completed.cancelled():
                    completed.exception()

            task.add_done_callback(finished)

    async def input(self, scope, identifier, body):
        from core.game_learning import _digest

        row = await self._read(scope, identifier)
        if row["controller"] != "human" or row["status"] != "running":
            raise _error("controller_unavailable", "Only the active human controller can submit input.")
        if not secrets.compare_digest(
            row["_control_token"], hashlib.sha256(body["control_token"].encode()).hexdigest()
        ):
            raise _error(
                "controller_fenced", "This controller token was replaced; take over explicitly.", 403
            )
        if body["action"] not in row.get("actions", []):
            raise _error("action_unavailable", "The actual adapter does not support this action.", 422)
        digest = _digest(
            {
                key: value
                for key, value in body.items()
                if key not in {"expected_control_version", "control_token"}
            }
        )
        if body["input_sequence"] == row["_last_input_sequence"]:
            if digest != row["_last_input_digest"]:
                raise _error("input_conflict", "Input sequence binds different controls.")
            return await self.get(scope, identifier)
        if body["input_sequence"] != row["_last_input_sequence"] + 1:
            raise _error("input_sequence_gap", "Input sequence must advance exactly once.")
        if len(row["_pending"]) >= 32:
            raise _error(
                "input_backpressure", "Input channel is full; wait for actual acknowledgements.", 429
            )
        command = {
            "kind": "input",
            "input_sequence": body["input_sequence"],
            "action": body["action"],
            "held": body["held"],
            "controller_epoch": row["controller_epoch"],
        }
        result = await self.plays.update_one(
            {
                "_id": identifier,
                **scope,
                "status": "running",
                "control_version": body["expected_control_version"],
                "controller_epoch": row["controller_epoch"],
                "_control_token": row["_control_token"],
                "cancel_requested": False,
            },
            {
                "$push": {"_pending": command},
                "$inc": {"control_version": 1},
                "$set": {
                    "_last_input_sequence": body["input_sequence"],
                    "_last_input_digest": digest,
                    "updated_at": _now(),
                },
            },
        )
        if not result.modified_count:
            raise _error("controller_conflict", "Controller revision changed; reload the current state.")
        return await self.get(scope, identifier)

    async def control(self, scope, identifier, body):
        action = body["action"]
        row = await self._read(scope, identifier, authorize=action != "stop")
        if row["control_version"] != body["expected_control_version"]:
            raise _error("controller_conflict", "Controller revision changed.")
        if action == "reset":
            await self.control(
                scope, identifier, {"action": "stop", "expected_control_version": row["control_version"]}
            )
            if identifier in self.tasks:
                await asyncio.shield(self.tasks[identifier])
            row = await self._read(scope, identifier)
        if action in {"resume", "reset"} and row["status"] in {"interrupted", "stopped", "failed"}:
            if action == "resume" and row.get("snapshot") is None:
                raise _error("resume_unavailable", "No durable snapshot exists for this session.")
            values = {
                "status": "queued",
                "stream_id": str(uuid4()),
                "frame_sequence": 0,
                "cancel_requested": False,
                "updated_at": _now(),
            }
            if action == "reset":
                values.update(snapshot=None, steps=0, reward=0.0, _recording=None)
            await self.plays.update_one(
                {
                    "_id": identifier,
                    **scope,
                    "control_version": row["control_version"],
                    "status": row["status"],
                },
                {"$set": values, "$inc": {"control_version": 1}},
            )
            await self._schedule(identifier, scope)
            return await self.get(scope, identifier)
        if row["status"] not in {"queued", "starting", "running", "paused"}:
            raise _error("play_terminal", "This play session is already terminal.")
        token, policy = None, None
        epoch = row["controller_epoch"]
        changes = {"updated_at": _now()}
        if action == "takeover":
            controller = body.get("controller") or "human"
            if controller == "ai":
                saved = await self.workspace._admitted_policy(
                    scope, row["project_id"], body.get("policy_id") or ""
                )
                if row.get("environment") != saved["snapshot"]["environment"]:
                    raise _error("policy_environment_mismatch", "Policy does not match this play instance.")
                policy = saved["snapshot"]
                updated_input = dict(row["input"])
                updated_input["generation_policy"] = {
                    "policy_id": saved["policy_id"],
                    "snapshot_digest": policy["snapshot_digest"],
                }
                changes["input"] = updated_input
            else:
                updated_input = dict(row["input"])
                updated_input.pop("generation_policy", None)
                changes["input"] = updated_input
            epoch += 1
            token = secrets.token_urlsafe(32)
            changes.update(
                controller=controller,
                controller_epoch=epoch,
                policy_id=body.get("policy_id"),
                policy=policy,
                _control_token=hashlib.sha256(token.encode()).hexdigest(),
                _last_input_sequence=0,
                _last_input_digest=None,
                _pending=[],
            )
        elif action == "pause":
            changes["status"] = "paused"
        elif action == "resume":
            changes["status"] = "running"
        elif action == "stop":
            changes.update(cancel_requested=True, status="stopping")
        command = {
            "kind": "control",
            "action": action,
            "controller_epoch": epoch,
            "controller": changes.get("controller", row["controller"]),
            "policy": policy,
            "command_id": str(uuid4()),
        }
        if "_pending" in changes:
            changes["_pending"] = [command]
            update = {"$set": changes, "$inc": {"control_version": 1}}
        else:
            update = {"$set": changes, "$push": {"_pending": command}, "$inc": {"control_version": 1}}
        result = await self.plays.find_one_and_update(
            {"_id": identifier, **scope, "control_version": row["control_version"], "status": row["status"]},
            update,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise _error("controller_conflict", "Controller revision changed.")
        if action == "stop" and identifier in self.stops:
            self.stops[identifier].set()
        return self.public(result, token)

    async def start_recording(self, scope, identifier, body):
        from core.game_learning import _digest, _key

        row = await self._read(scope, identifier)
        if body["consent"] is not True or row["controller"] != "human" or row["status"] != "running":
            raise _error(
                "recording_consent_required",
                "An active human controller and explicit learning consent are required.",
                403,
            )
        recording_id = _key(identifier, "recording", body["idempotency_key"])
        old = await self.recordings.find_one({"_id": recording_id, **scope})
        if old:
            return self.recording_public(old)
        if row.get("recording_id"):
            raise _error("recording_active", "Stop the existing recording first.")
        actor_id = hashlib.sha256((scope["tenant_id"] + "\0" + scope["owner_id"]).encode()).hexdigest()
        context = {
            "recording_id": recording_id,
            "episode_id": "demonstration:" + recording_id,
            "seed": row["seed"],
            "source_lineage": {
                "project_id": row["project_id"],
                "input_digest": _digest(row["input"]),
                "sources": row["input"]["sources"],
            },
            "actor_id": actor_id,
            "consent_ref": "game-recording-consent://" + recording_id,
        }
        doc = {
            "_id": recording_id,
            **scope,
            "recording_id": recording_id,
            "play_id": identifier,
            "project_id": row["project_id"],
            "input": row["input"],
            "status": "awaiting_start",
            "consent": True,
            "purpose": "local-policy-imitation",
            "label": body.get("label") or "Consented gameplay",
            "created_at": _now(),
            "context": context,
            "feedback": None,
        }
        await self.workspace._admit(scope, "game-learning-recording", recording_id, 2 * 1024 * 1024)
        await self.recordings.update_one({"_id": recording_id}, {"$setOnInsert": doc}, upsert=True)
        command = {"kind": "record_start", "controller_epoch": row["controller_epoch"], "recording": context}
        changed = await self.plays.update_one(
            {
                "_id": identifier,
                **scope,
                "control_version": body["expected_control_version"],
                "recording_id": {"$exists": False},
                "controller": "human",
                "status": "running",
                "cancel_requested": False,
            },
            {
                "$set": {"recording_id": recording_id},
                "$push": {"_pending": command},
                "$inc": {"control_version": 1},
            },
        )
        if not changed.modified_count:
            raise _error("recording_conflict", "Controller or recording state changed.")
        return self.recording_public(doc)

    @staticmethod
    def recording_public(row):
        result = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
            and key not in {"tenant_id", "owner_id", "input", "context", "demonstration"}
        }
        for key, value in tuple(result.items()):
            if isinstance(value, datetime):
                result[key] = (
                    value.replace(tzinfo=timezone.utc).isoformat()
                    if value.tzinfo is None
                    else value.isoformat()
                )
        demo = row.get("demonstration")
        result["step_count"] = demo["trace"]["steps"] if demo else row.get("step_count", 0)
        if demo:
            result["environment"] = demo["trace"]["environment"]
            result["demonstration_digest"] = demo["demonstration_digest"]
        result["usable_for_training"] = (
            row["status"] == "completed" and row.get("consent") is True and not row.get("_input_fenced")
        )
        return result

    async def recording(self, scope, identifier):
        row = await self.recordings.find_one({"_id": identifier, **scope})
        if row is None:
            raise _error("recording_not_found", "Gameplay recording not found.", 404)
        await self.workspace._authority(scope, row["input"])
        return row

    async def stop_recording(self, scope, identifier, body):
        row = await self.recording(scope, identifier)
        if body.get("consent") is not True:
            await self.workspace.database["game_learning_campaigns"].update_many(
                {
                    **scope,
                    "$or": [
                        {"binding.demonstrations.recording_id": identifier},
                        {"binding.inherited_demonstrations.recording_id": identifier},
                        {"binding.derived_demonstrations.recording_id": identifier},
                    ],
                },
                {"$set": {"source_fenced": True, "desired_status": "cancelled"}},
            )
            await self.workspace.jobs.update_many(
                {
                    **scope,
                    "$or": [
                        {"input.demonstrations.recording_id": identifier},
                        {"input.inherited_demonstrations.recording_id": identifier},
                        {"input.derived_demonstrations.recording_id": identifier},
                    ],
                    "status": {"$in": ["queued", "running", "interrupted"]},
                },
                {"$set": {"cancel_requested": True, "input_changed": True}},
            )
            await self.plays.update_many(
                {
                    **scope,
                    "$or": [
                        {"input.demonstrations.recording_id": identifier},
                        {"input.inherited_demonstrations.recording_id": identifier},
                        {"input.derived_demonstrations.recording_id": identifier},
                    ],
                },
                {"$set": {"cancel_requested": True, "_input_fenced": True}},
            )
            await self.recordings.update_one(
                {"_id": identifier, **scope},
                {
                    "$set": {"consent": False, "status": "withdrawn", "feedback": None},
                    "$unset": {"demonstration": ""},
                },
            )
        else:
            await self.recordings.update_one(
                {"_id": identifier, **scope, "status": {"$in": ["awaiting_start", "recording"]}},
                {"$set": {"status": "stopping", "feedback": body.get("feedback")}},
            )
        await self.plays.update_one(
            {"_id": row["play_id"], **scope, "recording_id": identifier},
            {
                "$push": {"_pending": {"kind": "record_stop", "recording_id": identifier}},
                "$inc": {"control_version": 1},
            },
        )
        return self.recording_public(await self.recordings.find_one({"_id": identifier, **scope}))

    async def export_recording(self, scope, identifier):
        row = await self.recording(scope, identifier)
        if row["status"] != "completed" or not row.get("consent"):
            raise _error("recording_unavailable", "A completed, consented recording is required.")
        content = _encoded(row["demonstration"], 2 * 1024 * 1024)
        return {
            "recording_id": identifier,
            "filename": "demonstration-" + identifier + ".json",
            "media_type": "application/json",
            "content": content.decode(),
            "content_digest": hashlib.sha256(content).hexdigest(),
        }

    async def replay(self, scope, identifier, body):
        row = await self.recording(scope, identifier)
        if row["status"] != "completed" or not row.get("consent"):
            raise _error("recording_unavailable", "A completed, consented recording is required.")
        play = await self._read(scope, row["play_id"])
        return await self.create(
            scope,
            row["project_id"],
            {
                **body,
                "seed": play["seed"],
                "source_id": play["input"].get("source_id"),
                "max_steps": play["input"]["episode_steps"],
                "controller": "human",
            },
            replay=row["demonstration"],
        )

    @staticmethod
    def _terminate(process, force=False):
        import signal

        try:
            if os.name == "posix" and os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
            else:
                process.kill() if force else process.terminate()
        except ProcessLookupError:
            return

    async def _run(self, identifier, scope):
        token, slot = str(uuid4()), None
        profile = resource_profiles()["profiles"][0]
        candidates = (
            ["game-learning-actor:0"]
            if profile["shared_single_capacity"]
            else ["game-learning-play:" + str(index) for index in range(profile["max_live_plays"])]
        )
        allowed = candidates + [
            "game-learning-actor:" + str(index) for index in range(profile["max_training_workers"])
        ]
        # Old larger deployments may still be draining a native process. Do
        # not add another human instance while its historical credit is live.
        legacy = await self.workers.find_one(
            {
                "_id": {"$regex": r"^game-learning-(actor|play):[0-9]+$", "$nin": allowed},
                "worker_token": {"$exists": True},
                "lease_until": {"$gt": _now()},
            }
        )
        if legacy is not None:
            return
        for candidate in candidates:
            await self.workers.update_one(
                {"_id": candidate},
                {"$setOnInsert": {"lease_until": datetime(1970, 1, 1, tzinfo=timezone.utc)}},
                upsert=True,
            )
            claimed = await self.workers.find_one_and_update(
                {"_id": candidate, "lease_until": {"$lt": _now()}},
                {
                    "$set": {
                        "worker_token": token,
                        "play_id": identifier,
                        "lease_until": _now() + timedelta(seconds=30),
                        "credit_kind": "native_play",
                    },
                    "$unset": {"job_id": ""},
                },
                return_document=ReturnDocument.AFTER,
            )
            if claimed:
                slot = candidate
                break
        if slot is None:
            return
        process = None
        commands = outputs = stopped = None
        try:
            row = await self.plays.find_one_and_update(
                {"_id": identifier, **scope, "status": "queued", "cancel_requested": False},
                {
                    "$set": {
                        "status": "starting",
                        "worker_token": token,
                        "lease_until": _now() + timedelta(seconds=30),
                        "host_id": self.host_id,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
            if row is None:
                return
            await self.workspace._authority(scope, row["input"])
            ctx = multiprocessing.get_context("spawn")
            commands, outputs, stopped = ctx.Queue(maxsize=32), ctx.Queue(maxsize=8), ctx.Event()
            options = {
                key: row.get(key)
                for key in (
                    "controller",
                    "controller_epoch",
                    "policy",
                    "seed",
                    "fps",
                    "snapshot",
                    "steps",
                    "reward",
                    "replay",
                )
            }
            options.update(
                recording=row.get("_recording"),
                input_sequence=(
                    row.get("_checkpoint_input_ack", 0)
                    if row.get("_checkpoint_controller_epoch") == row["controller_epoch"]
                    else 0
                ),
                replay_authority=(
                    {key: row["replay"][key] for key in ("actor_id", "consent_ref", "demonstration_digest")}
                    if row.get("replay")
                    else None
                ),
            )
            options = self.workspace._stored_evidence(options)
            runtime_request = self.workspace._stored_evidence(row["request"])
            process = ctx.Process(
                target=_worker, args=(runtime_request, options, commands, outputs, stopped), daemon=True
            )
            process.start()
            self.stops[identifier], self.commands[identifier] = stopped, commands
            frame_hub.open("play:" + identifier, row["stream_id"])
            delivered, last_lease = set(), 0.0
            terminal = False
            terminal_state = None
            while process.is_alive() or not outputs.empty():
                state = await self.plays.find_one(
                    {"_id": identifier, **scope},
                    {
                        "_pending": 1,
                        "cancel_requested": 1,
                        "worker_token": 1,
                        "controller_epoch": 1,
                        "input": 1,
                    },
                )
                if state is None or state.get("worker_token") != token or state.get("cancel_requested"):
                    stopped.set()
                for command in state.get("_pending", []) if state else []:
                    identity = _encoded(command).hex()
                    if identity not in delivered:
                        try:
                            commands.put_nowait(command)
                            delivered.add(identity)
                        except queue.Full:
                            break
                for _ in range(16):
                    try:
                        message = outputs.get_nowait()
                    except queue.Empty:
                        break
                    kind, payload = message["kind"], message["payload"]
                    if kind in {"frame", "checkpoint", "recording", "recording_started"}:
                        await self.workspace._authority(scope, row["input"])
                    if kind == "started":
                        row["environment"] = payload["environment"]
                        await self.plays.update_one(
                            {"_id": identifier, **scope, "worker_token": token, "cancel_requested": False},
                            {
                                "$set": {
                                    "status": "running",
                                    "actions": payload["actions"],
                                    "environment": payload["environment"],
                                    "observation": payload["observation"],
                                }
                            },
                        )
                    elif kind == "frame":
                        # Only current controller output reaches an authorized viewer.
                        if payload["controller_epoch"] != state.get("controller_epoch"):
                            continue
                        event = frame_hub.publish(
                            "play:" + identifier,
                            row["stream_id"],
                            {
                                **payload,
                                "play_id": identifier,
                                "environment_digest": row.get("environment", {}).get("environment_digest"),
                            },
                        )
                        await self.frames.update_one(
                            {"_id": "play:" + identifier},
                            {
                                "$set": {
                                    **scope,
                                    "project_id": row["project_id"],
                                    "stream_id": row["stream_id"],
                                    "event": event,
                                    "expires_at": _now() + timedelta(seconds=30),
                                }
                            },
                            upsert=True,
                        )
                    elif kind == "checkpoint":
                        _encoded(payload)
                        result = await self.workspace._guarded_write(
                            scope,
                            row["input"],
                            lambda: self.plays.update_one(
                                {
                                    "_id": identifier,
                                    **scope,
                                    "worker_token": token,
                                    "lease_until": {"$gt": _now()},
                                    "_input_fenced": {"$ne": True},
                                },
                                {
                                    "$set": {
                                        "snapshot": payload["snapshot"],
                                        "observation": payload["observation"],
                                        "steps": payload["steps"],
                                        "reward": payload["reward"],
                                        "_recording": payload["recording"],
                                        "_checkpoint_input_ack": payload["input_sequence_ack"],
                                        "_checkpoint_controller_epoch": payload["controller_epoch"],
                                        "updated_at": _now(),
                                    }
                                },
                            ),
                        )
                        if not result.modified_count:
                            raise _error("play_worker_fenced", "Play lost its checkpoint authority.")
                        if payload["recording"]:
                            await self.recordings.update_one(
                                {"_id": payload["recording"]["recording_id"], **scope, "consent": True},
                                {"$set": {"step_count": len(payload["recording"]["transitions"])}},
                            )
                    elif kind in {"input_ack", "control_ack"}:
                        if kind == "input_ack":
                            await self.plays.update_one(
                                {"_id": identifier, **scope, "worker_token": token},
                                {
                                    "$pull": {
                                        "_pending": {
                                            "kind": "input",
                                            "controller_epoch": payload["controller_epoch"],
                                            "input_sequence": {"$lte": payload["input_sequence"]},
                                        }
                                    }
                                },
                            )
                        else:
                            await self.plays.update_one(
                                {"_id": identifier, **scope, "worker_token": token},
                                {"$pull": {"_pending": {"command_id": payload["command_id"]}}},
                            )
                    elif kind == "recording_started":
                        await self.recordings.update_one(
                            {
                                "_id": payload["recording_id"],
                                **scope,
                                "status": "awaiting_start",
                                "consent": True,
                            },
                            {"$set": {"status": "recording"}},
                        )
                        await self.plays.update_one(
                            {"_id": identifier, **scope, "worker_token": token},
                            {"$pull": {"_pending": {"kind": "record_start"}}},
                        )
                    elif kind == "recording":
                        demo = payload["demonstration"]
                        _encoded(demo, 2 * 1024 * 1024)
                        await self.workspace._guarded_write(
                            scope,
                            row["input"],
                            lambda: self.recordings.update_one(
                                {
                                    "_id": payload["recording_id"],
                                    **scope,
                                    "consent": True,
                                    "status": {"$in": ["recording", "stopping"]},
                                },
                                {
                                    "$set": {
                                        "status": "completed",
                                        "demonstration": demo,
                                        "completed_at": _now(),
                                        "step_count": demo["trace"]["steps"],
                                    }
                                },
                            ),
                        )
                        await self.plays.update_one(
                            {"_id": identifier, **scope, "worker_token": token},
                            {"$unset": {"recording_id": ""}, "$pull": {"_pending": {"kind": "record_stop"}}},
                        )
                    elif kind == "recording_empty":
                        await self.recordings.update_one(
                            {"_id": payload["recording_id"], **scope}, {"$set": {"status": "empty"}}
                        )
                        await self.plays.update_one(
                            {"_id": identifier, **scope, "worker_token": token},
                            {"$unset": {"recording_id": ""}},
                        )
                    elif kind in {"terminal", "failed"}:
                        terminal = True
                        terminal_state = "stopped" if kind == "terminal" else "failed"
                        stopped.set()
                        await self.plays.update_one(
                            {"_id": identifier, **scope, "worker_token": token},
                            {
                                "$set": {
                                    "status": "stopping",
                                    "error": payload if kind == "failed" else None,
                                    "updated_at": _now(),
                                },
                            },
                        )
                if time.monotonic() - last_lease > 1 and not terminal:
                    await self.workspace._authority(scope, row["input"])
                    lease = await self.plays.update_one(
                        {
                            "_id": identifier,
                            **scope,
                            "worker_token": token,
                            "_input_fenced": {"$ne": True},
                            "lease_until": {"$gt": _now()},
                        },
                        {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                    )
                    slot_live = await self.workers.update_one(
                        {"_id": slot, "worker_token": token, "lease_until": {"$gt": _now()}},
                        {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                    )
                    if not lease.modified_count or not slot_live.modified_count:
                        stopped.set()
                    last_lease = time.monotonic()
                if stopped.is_set() and process.is_alive():
                    await asyncio.to_thread(process.join, 2)
                    if process.is_alive():
                        self._terminate(process)
                        await asyncio.to_thread(process.join, 2)
                await asyncio.sleep(0.03)
            if not terminal:
                await self.plays.update_one(
                    {"_id": identifier, **scope, "worker_token": token},
                    {
                        "$set": {"status": "interrupted", "updated_at": _now()},
                        "$unset": {"worker_token": "", "lease_until": ""},
                    },
                )
        except BaseException as exc:
            if stopped:
                stopped.set()
            await self.plays.update_one(
                {"_id": identifier, **scope, "worker_token": token},
                {
                    "$set": {
                        "status": "interrupted",
                        "error": {
                            "code": getattr(exc, "code", "play_interrupted"),
                            "message": "Play stopped; only committed observations and snapshots are retained.",
                        },
                        "updated_at": _now(),
                    },
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            if stopped:
                stopped.set()
            if process:

                async def quiesce():
                    if process.pid is not None:
                        await asyncio.to_thread(process.join, 2)
                        if process.is_alive():
                            self._terminate(process)
                            await asyncio.to_thread(process.join, 2)
                        if process.is_alive():
                            self._terminate(process, force=True)
                            await asyncio.to_thread(process.join)
                    process.close()

                cleanup = asyncio.create_task(quiesce())
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        if stopped:
                            stopped.set()
                await cleanup
            for channel in (commands, outputs):
                if channel is not None:
                    channel.cancel_join_thread()
                    channel.close()
            if process is not None and "terminal_state" in locals() and terminal_state is not None:
                await self.plays.update_one(
                    {"_id": identifier, **scope, "worker_token": token},
                    {
                        "$set": {"status": terminal_state, "updated_at": _now()},
                        "$unset": {"worker_token": "", "lease_until": ""},
                    },
                )
            await self.recordings.update_many(
                {
                    **scope,
                    "play_id": identifier,
                    "status": {"$in": ["awaiting_start", "recording", "stopping"]},
                },
                {"$set": {"status": "interrupted", "updated_at": _now()}},
            )
            self.stops.pop(identifier, None)
            self.commands.pop(identifier, None)
            await self.workers.update_one(
                {"_id": slot, "worker_token": token},
                {
                    "$set": {"lease_until": _now()},
                    "$unset": {"worker_token": "", "play_id": "", "credit_kind": ""},
                },
            )
