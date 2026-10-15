"""Real isolated local game rollout actors and episode-atomic central learning.

Actors receive a frozen policy and immutable environment request through bounded
JSON IPC. They own no database, credentials or mutable central policy. A durable
pending batch plus acknowledged prefix lets recovery replay only uncommitted
episodes against the same frozen policy, irrespective of completion order.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import math
import os
import queue
import random
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from .game_learning import (
    MAX_LIFETIME_EPISODES,
    GameLearningCancelled,
    GameLearningError,
    GamePolicyLearner,
    _copy_json,
    _descriptor,
    _digest,
    _int,
    _json,
    _name,
    _sha,
)
from .game_learning_demonstrations import (
    _issue_verified_episode,
    close_environment,
    environment_snapshot_digest,
)

REQUEST_SCHEMA = "skeleton.game.environment_request.v1"
BATCH_SCHEMA = "skeleton.game.parallel_batch.v1"
MAX_MESSAGE = 8 * 1024 * 1024
MAX_FRAME = 512 * 1024
MAX_BATCH_TRACES = 32 * 1024 * 1024
log = logging.getLogger(__name__)
_QUARANTINED: dict[int, subprocess.Popen] = {}
_QUARANTINE_LOCK = threading.Lock()


def _central_operation(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def invoke(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self.learner.operation():
            return method(self, *args, **kwargs)

    return invoke


@dataclass(frozen=True, slots=True)
class GameEnvironmentRequest:
    target_id: str
    max_steps: int = 256
    tree: Mapping[str, str] | None = None
    rom_source: bytes | None = None
    cycles_per_step: int = 1824
    kind: str = "builtin"
    core_id: str | None = None
    registry_digest: str | None = None
    content: Mapping[str, Any] | None = None
    filename: str = "game.bin"
    frames_per_step: int = 1
    emulator_timeout_seconds: float = 5.0
    gameplay_dialect: str | None = None
    native_observation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _name(self.target_id, "environment target")
        _int(self.max_steps, "environment episode steps", 1, 4096)
        _int(self.cycles_per_step, "ROM cycles per step", 4, 140448)
        _int(self.frames_per_step, "emulator frames per step", 1, 16)
        if self.kind not in ("builtin", "libretro", "console_editor", "successor"):
            raise GameLearningError("environment request kind is undeclared")
        if (
            isinstance(self.emulator_timeout_seconds, bool)
            or not isinstance(self.emulator_timeout_seconds, (float, int))
            or not math.isfinite(self.emulator_timeout_seconds)
            or not 0.1 <= self.emulator_timeout_seconds <= 300
        ):
            raise GameLearningError("emulator command timeout is outside bounds")
        if self.tree is not None:
            tree = _copy_json(dict(self.tree), limit=8 * 1024 * 1024)
            if (
                len(tree) > 128
                or any(not isinstance(value, str) for value in tree.values())
                or sum(len(value.encode()) for value in tree.values()) > 7 * 1024 * 1024
            ):
                raise GameLearningError("environment project file mapping is invalid")
            object.__setattr__(self, "tree", tree)
        if self.rom_source is not None and (
            not isinstance(self.rom_source, bytes) or len(self.rom_source) > 2 * 1024 * 1024
        ):
            raise GameLearningError("large content needs an admitted private file descriptor")
        if self.content is not None:
            object.__setattr__(self, "content", _copy_json(dict(self.content), limit=1024 * 1024))
        if self.kind == "libretro":
            _name(self.core_id, "approved emulator core")
            _sha(self.registry_digest, "approved emulator registry")
            if self.tree is not None or (self.content is None) == (self.rom_source is None):
                raise GameLearningError("emulator request needs exactly one admitted content source")
            if self.native_observation is not None:
                from .game_emulator_host import validate_native_observation

                object.__setattr__(
                    self,
                    "native_observation",
                    validate_native_observation(
                        self.native_observation, core_id=self.core_id, target_id=self.target_id
                    ),
                )
        elif any(value is not None for value in (self.core_id, self.registry_digest, self.content)):
            raise GameLearningError("builtin request cannot carry an emulator registry or content descriptor")
        if self.kind != "libretro" and self.native_observation is not None:
            raise GameLearningError("native RAM observations require the approved emulator owner")
        if self.kind in ("console_editor", "successor") and (
            self.tree is None or self.rom_source is not None or self.gameplay_dialect is not None
        ):
            raise GameLearningError("authored environment needs an exact file tree without ROM or dialect")
        _name(self.filename, "emulator content filename")
        if self.gameplay_dialect is not None:
            _name(self.gameplay_dialect, "environment gameplay dialect")
            if len(self.gameplay_dialect) > 64 or self.kind == "libretro":
                raise GameLearningError("environment gameplay dialect is incompatible")
        _json(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REQUEST_SCHEMA,
            "target_id": self.target_id,
            "max_steps": self.max_steps,
            "tree": self.tree,
            "rom_base64": (
                None if self.rom_source is None else base64.b64encode(self.rom_source).decode("ascii")
            ),
            "cycles_per_step": self.cycles_per_step,
            "kind": self.kind,
            "core_id": self.core_id,
            "registry_digest": self.registry_digest,
            "content": self.content,
            "filename": self.filename,
            "frames_per_step": self.frames_per_step,
            "emulator_timeout_seconds": float(self.emulator_timeout_seconds),
            "gameplay_dialect": self.gameplay_dialect,
            "native_observation": self.native_observation,
        }

    @property
    def digest(self) -> str:
        semantic = _copy_json(self.as_dict())
        if isinstance(semantic["content"], dict):
            # A rebuilt private cache may live at another approved physical
            # path. Exact files/entrypoint/content and registry remain bound.
            semantic["content"].pop("root", None)
        return _digest(semantic)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GameEnvironmentRequest:
        if not isinstance(value, Mapping):
            raise GameLearningError("environment request must be an object")
        raw = _copy_json(dict(value))
        expected = {
            "schema_version",
            "target_id",
            "max_steps",
            "tree",
            "rom_base64",
            "cycles_per_step",
            "kind",
            "core_id",
            "registry_digest",
            "content",
            "filename",
            "frames_per_step",
            "emulator_timeout_seconds",
            "gameplay_dialect",
            "native_observation",
        }
        # Old serialized requests stay readable; current code identities still
        # fence existing policy and worker evidence at their ordinary owners.
        raw.setdefault("native_observation", None)
        if set(raw) != expected or raw.pop("schema_version") != REQUEST_SCHEMA:
            raise GameLearningError("environment request schema differs")
        encoded = raw.pop("rom_base64")
        if encoded is not None:
            if not isinstance(encoded, str) or len(encoded) > 2800000:
                raise GameLearningError("environment ROM encoding exceeds bounds")
            try:
                raw["rom_source"] = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise GameLearningError("environment ROM encoding is invalid") from exc
        return cls(**raw)

    def build(self, *, cancel: Callable[[], bool] | None = None) -> Any:
        if cancel is not None and cancel():
            raise GameLearningCancelled("environment construction was cancelled")
        if self.kind == "console_editor":
            from .game_console_editor import ConsoleProject
            from .game_console_simulation import EditorSimulationEnvironment

            return EditorSimulationEnvironment(
                ConsoleProject.from_files(self.tree, target_id=self.target_id), max_steps=self.max_steps
            )
        if self.kind == "successor":
            from .game_successor_runtime import SuccessorEnvironment

            encoded = self.tree.get("game/successor/spec.json")
            if not isinstance(encoded, str) or len(encoded.encode()) > 131072:
                raise GameLearningError("successor authored spec is absent or exceeds capacity")
            return SuccessorEnvironment(json.loads(encoded), max_steps=self.max_steps)
        if self.kind == "libretro":
            from .game_emulator_host import create_emulator_environment

            return create_emulator_environment(
                self.target_id,
                core_id=self.core_id,
                expected_registry_digest=self.registry_digest,
                content=self.content,
                rom_source=self.rom_source,
                filename=self.filename,
                max_steps=self.max_steps,
                frames_per_step=self.frames_per_step,
                timeout_seconds=self.emulator_timeout_seconds,
                cancelled=cancel,
                native_observation=self.native_observation,
            )
        from .game_learning_runtime import create_game_environment

        return create_game_environment(
            self.target_id,
            max_steps=self.max_steps,
            tree=self.tree,
            rom_source=self.rom_source,
            cycles_per_step=self.cycles_per_step,
            gameplay_dialect=self.gameplay_dialect,
        )


def _send(channel: socket.socket, value: Mapping[str, Any]) -> None:
    data = _json(value, limit=MAX_MESSAGE)
    channel.sendall(struct.pack("!I", len(data)) + data)


def _receive(channel: socket.socket) -> dict[str, Any]:
    def take(length: int) -> bytes:
        result = bytearray()
        while len(result) < length:
            part = channel.recv(min(65536, length - len(result)))
            if not part:
                raise GameLearningError("actor IPC closed before a complete bounded message")
            result.extend(part)
        return bytes(result)

    length = struct.unpack("!I", take(4))[0]
    if not 1 <= length <= MAX_MESSAGE:
        raise GameLearningError("actor IPC message length is outside bounds")
    try:
        value = json.loads(take(length))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise GameLearningError("actor IPC is not bounded finite JSON") from exc
    if not isinstance(value, dict):
        raise GameLearningError("actor IPC message must be an object")
    _json(value)
    return value


def _implementation() -> str:
    paths = [
        Path(__file__),
        Path(__file__).with_name("game_learning.py"),
        Path(__file__).with_name("game_learning_demonstrations.py"),
    ]
    return _digest(
        {
            "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            "python": list(sys.version_info[:3]),
        }
    )


def _worker(channel: socket.socket) -> None:
    request = _receive(channel)
    environment_request = GameEnvironmentRequest.from_dict(request["environment_request"])
    frozen = GamePolicyLearner.from_snapshot(request["frozen_policy"])
    if request["implementation_digest"] != _implementation():
        raise GameLearningError("actor implementation identity differs")
    expected = request["environment"]
    actor_id, batch_id = request["actor_id"], request["batch_id"]
    instance_id = request["instance_id"]
    frame_sequence = 0
    stopped = False

    def cancelled() -> bool:
        nonlocal stopped
        readable, _, _ = select.select([channel], [], [], 0)
        if readable:
            control = _receive(channel)
            if control != {"type": "cancel"}:
                raise GameLearningError("actor received an undeclared control message")
            stopped = True
        return stopped

    actor_visits = {state: list(values) for state, values in frozen._visits.items()}
    for assignment in request["assignments"]:
        environment = None
        try:
            GamePolicyLearner._guard(cancelled, None)
            environment = environment_request.build(cancel=cancelled)
            if _descriptor(environment.spec) != expected or frozen.descriptor != expected:
                raise GameLearningError("actor constructed a foreign environment")
            observation = frozen._observation(environment.reset(assignment["seed"]))
            rng = random.Random(assignment["rollout_seed"])
            epsilon = max(
                frozen.config.min_epsilon,
                frozen.config.epsilon * frozen.config.epsilon_decay ** assignment["ordinal"],
            )
            transitions = []
            trace_bytes = 0
            for sequence in range(1, expected["max_episode_steps"] + 1):
                GamePolicyLearner._guard(cancelled, None)
                explore = rng.random() < epsilon
                if frozen.config.exploration_strategy == "least_visited":
                    state = frozen._state(observation)
                    if state not in actor_visits:
                        if len(actor_visits) >= frozen.config.max_states:
                            raise GameLearningError("actor exploration state budget exhausted")
                        actor_visits[state] = [0] * len(frozen._actions)
                    scores = frozen._scores(state)
                    candidates = (
                        list(range(len(scores)))
                        if explore
                        else [i for i, v in enumerate(scores) if v == max(scores)]
                    )
                    minimum = min(actor_visits[state][i] for i in candidates)
                    candidates = [i for i in candidates if actor_visits[state][i] == minimum]
                    index = candidates[rng.randrange(len(candidates))]
                    action = frozen._actions[index]
                else:
                    action = (
                        frozen._actions[rng.randrange(len(frozen._actions))]
                        if explore
                        else frozen._greedy(observation)
                    )
                step = environment.step(action)
                value: dict[str, Any] = {
                    "sequence": sequence,
                    "observation": observation,
                    "action": action,
                    "next_observation": step.observation,
                    "reward_components": step.reward_components,
                    "reward": math.fsum(step.reward_components.values()),
                    "terminated": step.terminated,
                    "truncated": step.truncated
                    or (sequence == expected["max_episode_steps"] and not step.terminated),
                }
                if step.info:
                    value["info"] = step.info
                if step.transition_digest:
                    value["transition_digest"] = step.transition_digest
                transition = frozen._transition(value, sequence)
                if frozen.config.exploration_strategy == "least_visited":
                    actor_visits[state][index] += 1
                trace_bytes += len(_json(transition))
                if trace_bytes > frozen.config.trace_byte_limit:
                    raise GameLearningError("actor trace byte budget exhausted")
                transitions.append(transition)
                observation = transition["next_observation"]
                if (
                    sequence == 1
                    or sequence % request["frame_stride"] == 0
                    or transition["terminated"]
                    or transition["truncated"]
                ):
                    frame = environment.preview()
                    _json(frame, limit=MAX_FRAME)
                    frame_sequence += 1
                    _send(
                        channel,
                        {
                            "type": "frame",
                            "batch_id": batch_id,
                            "actor_id": actor_id,
                            "instance_id": instance_id,
                            "actor_pid": os.getpid(),
                            "episode_id": assignment["episode_id"],
                            "ordinal": assignment["ordinal"],
                            "step": sequence,
                            "frame_sequence": frame_sequence,
                            "frame": frame,
                            "observation": observation,
                            "action": action,
                            "policy_digest": frozen.snapshot_digest,
                            "environment_digest": environment.spec.environment_digest,
                        },
                    )
                if transition["terminated"] or transition["truncated"]:
                    break
            trace = {
                "schema_version": "skeleton.game.trace.v1",
                "environment": expected,
                "episode_id": assignment["episode_id"],
                "seed": assignment["seed"],
                "source_lineage": frozen.source_lineage,
                "transitions": transitions,
                "steps": len(transitions),
                "return": math.fsum(row["reward"] for row in transitions),
            }
            trace["trace_digest"] = _digest(trace)
            frozen.validate_trace(trace)
            receipt = {
                "batch_id": batch_id,
                "actor_id": actor_id,
                "instance_id": instance_id,
                "actor_pid": os.getpid(),
                "assignment": assignment,
                "policy_digest": frozen.snapshot_digest,
                "environment_digest": environment.spec.environment_digest,
                "request_digest": environment_request.digest,
                "trace_digest": trace["trace_digest"],
                "steps": trace["steps"],
                "return": trace["return"],
                "final_snapshot_digest": environment_snapshot_digest(environment),
            }
            receipt["receipt_digest"] = _digest(receipt)
            _send(channel, {"type": "episode", "trace": trace, "receipt": receipt})
        finally:
            if environment is not None:
                close_environment(environment)
    _send(
        channel,
        {
            "type": "done",
            "actor_id": actor_id,
            "instance_id": instance_id,
            "actor_pid": os.getpid(),
            "batch_id": batch_id,
        },
    )


@dataclass(frozen=True, slots=True)
class ParallelTrainingResult:
    snapshot: dict[str, Any]
    batch_state: dict[str, Any] | None
    episode_summaries: tuple[dict[str, Any], ...]
    actor_receipts: tuple[dict[str, Any], ...]
    updates: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot": _copy_json(self.snapshot),
            "batch_state": _copy_json(self.batch_state),
            "episode_summaries": _copy_json(self.episode_summaries),
            "actor_receipts": _copy_json(self.actor_receipts),
            "updates": self.updates,
            "algorithm": "frozen_batch_local_actor_q_v1",
        }


class ParallelGamePolicyTrainer:
    def __init__(
        self,
        learner: GamePolicyLearner,
        request: GameEnvironmentRequest,
        *,
        actors: int = 2,
        batch_episodes: int | None = None,
        actor_timeout_seconds: float = 120,
        frame_stride: int = 8,
    ) -> None:
        if not isinstance(learner, GamePolicyLearner) or not isinstance(request, GameEnvironmentRequest):
            raise GameLearningError("typed policy and environment request are required")
        self.learner, self.request = learner, request
        self.actors = _int(actors, "actor count", 1, 8)
        self.batch_episodes = _int(
            actors if batch_episodes is None else batch_episodes, "batch episode count", 1, 8
        )
        self.frame_stride = _int(frame_stride, "actor frame stride", 1, 256)
        if (
            isinstance(actor_timeout_seconds, bool)
            or not isinstance(actor_timeout_seconds, (float, int))
            or not math.isfinite(actor_timeout_seconds)
            or not 1 <= actor_timeout_seconds <= 300
        ):
            raise GameLearningError("actor timeout is outside bounds")
        self.timeout = float(actor_timeout_seconds)
        self._binding = {
            "request_digest": request.digest,
            "environment": learner.descriptor,
            "actors": self.actors,
            "batch_episodes": self.batch_episodes,
            "actor_timeout_seconds": self.timeout,
            "frame_stride": self.frame_stride,
            "implementation_digest": _implementation(),
            "policy_id": learner.policy_id,
        }

    def _batch(self, count: int) -> dict[str, Any]:
        snapshot = self.learner.snapshot()
        start = snapshot["committed_episodes"]
        assignments = []
        for offset in range(count):
            ordinal = start + offset
            seed = self.learner._seed(ordinal)
            identity = _digest(
                {
                    "policy_id": self.learner.policy_id,
                    "ordinal": ordinal,
                    "seed": seed,
                    "request_digest": self.request.digest,
                }
            )
            assignments.append(
                {
                    "ordinal": ordinal,
                    "actor_index": offset % self.actors,
                    "seed": seed,
                    "rollout_seed": int(identity[:16], 16) % (2**63),
                    "episode_id": "actor-episode:" + identity,
                }
            )
        batch_id = _digest(
            {
                "binding": self._binding,
                "frozen_policy_digest": snapshot["snapshot_digest"],
                "assignments": assignments,
            }
        )
        return {
            "schema_version": BATCH_SCHEMA,
            "binding": self._binding,
            "batch_id": batch_id,
            "frozen_policy": snapshot,
            "start_ordinal": start,
            "assignments": assignments,
            "acknowledged": [],
            "phase": "pending",
        }

    def _resume(self, value: Mapping[str, Any]) -> dict[str, Any]:
        state = _copy_json(dict(value))
        if (
            set(state)
            != {
                "schema_version",
                "binding",
                "batch_id",
                "frozen_policy",
                "start_ordinal",
                "assignments",
                "acknowledged",
                "phase",
            }
            or state["schema_version"] != BATCH_SCHEMA
            or state["binding"] != self._binding
            or state["phase"] not in ("pending", "complete")
        ):
            raise GameLearningError("parallel pending batch binding differs")
        frozen = GamePolicyLearner.from_snapshot(
            state["frozen_policy"],
            expected_spec=self.learner.spec,
            expected_config=self.learner.config,
            expected_source_lineage=self.learner.source_lineage,
        )
        start = _int(state["start_ordinal"], "batch starting ordinal", 0, 255)
        if frozen.policy_id != self.learner.policy_id or frozen.snapshot()["committed_episodes"] != start:
            raise GameLearningError("parallel frozen policy cursor differs")
        assignments = state["assignments"]
        if (
            not isinstance(assignments, list)
            or not 1 <= len(assignments) <= self.batch_episodes
            or start + len(assignments) > self.learner.config.max_episodes
        ):
            raise GameLearningError("parallel assignment count differs")
        for offset, assignment in enumerate(assignments):
            ordinal = start + offset
            seed = frozen._seed(ordinal)
            identity = _digest(
                {
                    "policy_id": frozen.policy_id,
                    "ordinal": ordinal,
                    "seed": seed,
                    "request_digest": self.request.digest,
                }
            )
            expected = {
                "ordinal": ordinal,
                "actor_index": offset % self.actors,
                "seed": seed,
                "rollout_seed": int(identity[:16], 16) % (2**63),
                "episode_id": "actor-episode:" + identity,
            }
            if (
                not isinstance(assignment, dict)
                or assignment != expected
                or any(
                    type(assignment[key]) is not int
                    for key in ("ordinal", "actor_index", "seed", "rollout_seed")
                )
            ):
                raise GameLearningError("parallel deterministic assignment differs")
        if state["batch_id"] != _digest(
            {
                "binding": self._binding,
                "frozen_policy_digest": frozen.snapshot_digest,
                "assignments": assignments,
            }
        ):
            raise GameLearningError("parallel batch digest differs")
        acknowledged = state["acknowledged"]
        if not isinstance(acknowledged, list) or len(acknowledged) > len(assignments):
            raise GameLearningError("parallel acknowledgment prefix differs")
        current = self.learner.snapshot()
        if current["committed_episodes"] != start + len(acknowledged):
            raise GameLearningError("parallel acknowledgment and policy cursor differ")
        for index, receipt in enumerate(acknowledged):
            if (
                not isinstance(receipt, dict)
                or set(receipt)
                != {"ordinal", "episode_id", "trace_digest", "actor_receipt_digest", "policy_digest"}
                or type(receipt["ordinal"]) is not int
                or receipt["ordinal"] != start + index
            ):
                raise GameLearningError("parallel acknowledgment identity differs")
            for key in ("trace_digest", "actor_receipt_digest", "policy_digest"):
                _sha(receipt[key], "acknowledgment")
            episode = current["episodes"][start + index]
            if (
                receipt["episode_id"] != assignments[index]["episode_id"]
                or episode["episode_id"] != receipt["episode_id"]
                or episode["trace_digest"] != receipt["trace_digest"]
                or episode["source"] != "local_actor_rollout"
            ):
                raise GameLearningError("parallel acknowledgment differs from committed episode")
        if acknowledged and acknowledged[-1]["policy_digest"] != self.learner.snapshot_digest:
            raise GameLearningError("parallel acknowledgment terminal policy differs")
        if not acknowledged and frozen.snapshot_digest != self.learner.snapshot_digest:
            raise GameLearningError("parallel initial frozen policy differs")
        if (state["phase"] == "complete") != (len(acknowledged) == len(assignments)):
            raise GameLearningError("parallel batch completion phase differs")
        return state

    @staticmethod
    def _child_environment() -> dict[str, str]:
        retained = {
            "PATH",
            "PYTHONPATH",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "LD_LIBRARY_PATH",
            "SKL_GAME_EMULATOR_REGISTRY",
        }
        return {name: value for name, value in os.environ.items() if name in retained}

    def _collect(
        self,
        state: Mapping[str, Any],
        *,
        on_frame: Callable[[dict[str, Any]], None] | None,
        cancel: Callable[[], bool] | None,
        authorize: Callable[[], None] | None,
    ) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
        if os.name != "posix":
            raise GameLearningError("isolated actor process-group cleanup requires POSIX")
        with _QUARANTINE_LOCK:
            for pid, process in list(_QUARANTINED.items()):
                if process.poll() is not None:
                    _QUARANTINED.pop(pid)
            if _QUARANTINED:
                raise GameLearningError("prior actor cleanup is not quiescent; new actors remain fenced")
        pending = state["assignments"][len(state["acknowledged"]) :]
        if not pending:
            return {}
        groups: dict[int, list[dict[str, Any]]] = {}
        for assignment in pending:
            groups.setdefault(assignment["actor_index"], []).append(assignment)
        handles = []
        events: queue.Queue = queue.Queue(maxsize=16)
        stopped = threading.Event()
        results = {}
        done = set()
        total_bytes = 0
        last_frames: dict[int, int] = {}
        deadline = time.monotonic() + self.timeout

        def read(index, channel):
            try:
                while not stopped.is_set():
                    message = _receive(channel)
                    while not stopped.is_set():
                        try:
                            events.put((index, message, None), timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    if message.get("type") in ("done", "error"):
                        return
            except Exception as exc:
                log.exception("actor IPC reader stopped before its completion receipt")
                while not stopped.is_set():
                    try:
                        events.put((index, None, exc), timeout=0.1)
                        return
                    except queue.Full:
                        continue

        try:
            for index, assignments in groups.items():
                GamePolicyLearner._guard(cancel, authorize)
                parent, child = socket.socketpair()
                handle = {
                    "index": index,
                    "channel": parent,
                    "process": None,
                    "thread": None,
                    "actor_id": state["batch_id"] + ":" + str(index),
                    "instance_id": str(uuid4()),
                    "assignments": assignments,
                }
                handles.append(handle)
                try:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "skeleton.jeeves.game_learning_parallel",
                            "--actor-fd",
                            str(child.fileno()),
                        ],
                        pass_fds=(child.fileno(),),
                        env=self._child_environment(),
                        cwd=str(Path(__file__).resolve().parents[2]),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    handle["process"] = process
                finally:
                    child.close()
                parent.settimeout(min(self.timeout, 20.0))
                _send(
                    parent,
                    {
                        "environment_request": self.request.as_dict(),
                        "frozen_policy": state["frozen_policy"],
                        "environment": self.learner.descriptor,
                        "actor_id": handle["actor_id"],
                        "instance_id": handle["instance_id"],
                        "batch_id": state["batch_id"],
                        "assignments": assignments,
                        "frame_stride": self.frame_stride,
                        "implementation_digest": self._binding["implementation_digest"],
                    },
                )
                parent.settimeout(self.timeout)
                thread = threading.Thread(target=read, args=(index, parent), daemon=True)
                handle["thread"] = thread
                thread.start()
            frozen = GamePolicyLearner.from_snapshot(state["frozen_policy"])
            by_index = {handle["index"]: handle for handle in handles}
            while len(done) < len(handles):
                GamePolicyLearner._guard(cancel, authorize)
                if time.monotonic() >= deadline:
                    raise GameLearningError("parallel rollout actor batch timed out")
                try:
                    index, message, error = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                handle = by_index[index]
                if error is not None:
                    raise GameLearningError("parallel actor IPC failed before a complete receipt") from error
                if message.get("type") == "error":
                    raise GameLearningError(
                        "parallel actor failed: " + str(message.get("message", "execution rejected"))[:500]
                    )
                if message.get("type") in ("frame", "done") and (
                    message.get("actor_id") != handle["actor_id"]
                    or message.get("instance_id") != handle["instance_id"]
                    or type(message.get("actor_pid")) is not int
                    or message["actor_pid"] != handle["process"].pid
                    or message.get("batch_id") != state["batch_id"]
                ):
                    raise GameLearningError("parallel actor channel identity differs")
                if message.get("type") == "done":
                    if index in done:
                        raise GameLearningError("parallel actor sent duplicate completion")
                    done.add(index)
                elif message.get("type") == "frame":
                    if (
                        message.get("policy_digest") != frozen.snapshot_digest
                        or message.get("environment_digest") != frozen.descriptor["environment_digest"]
                        or type(message.get("frame_sequence")) is not int
                        or message["frame_sequence"] != last_frames.get(index, 0) + 1
                    ):
                        raise GameLearningError("parallel live frame identity or sequence differs")
                    assignment = next(
                        (
                            item
                            for item in handle["assignments"]
                            if item["episode_id"] == message.get("episode_id")
                        ),
                        None,
                    )
                    if (
                        assignment is None
                        or type(message.get("ordinal")) is not int
                        or message["ordinal"] != assignment["ordinal"]
                        or type(message.get("step")) is not int
                        or not 1 <= message["step"] <= self.request.max_steps
                        or message.get("action") not in frozen._actions
                    ):
                        raise GameLearningError("parallel frame assignment differs")
                    frozen._observation(message.get("observation"))
                    _json(message.get("frame"), limit=MAX_FRAME)
                    last_frames[index] = message["frame_sequence"]
                    if on_frame is not None:
                        on_frame(_copy_json(message))
                elif message.get("type") == "episode":
                    receipt, trace = message.get("receipt"), message.get("trace")
                    if not isinstance(receipt, dict) or set(receipt) != {
                        "batch_id",
                        "actor_id",
                        "instance_id",
                        "actor_pid",
                        "assignment",
                        "policy_digest",
                        "environment_digest",
                        "request_digest",
                        "trace_digest",
                        "steps",
                        "return",
                        "final_snapshot_digest",
                        "receipt_digest",
                    }:
                        raise GameLearningError("parallel actor receipt schema differs")
                    assignment = receipt["assignment"]
                    if (
                        assignment not in handle["assignments"]
                        or receipt["actor_id"] != handle["actor_id"]
                        or receipt["instance_id"] != handle["instance_id"]
                        or type(receipt["actor_pid"]) is not int
                        or receipt["actor_pid"] != handle["process"].pid
                        or receipt["batch_id"] != state["batch_id"]
                        or receipt["policy_digest"] != frozen.snapshot_digest
                        or receipt["request_digest"] != self.request.digest
                        or receipt["environment_digest"] != frozen.descriptor["environment_digest"]
                    ):
                        raise GameLearningError("parallel actor receipt assignment or channel differs")
                    if (
                        _digest({key: value for key, value in receipt.items() if key != "receipt_digest"})
                        != receipt["receipt_digest"]
                    ):
                        raise GameLearningError("parallel actor receipt digest differs")
                    _sha(receipt["final_snapshot_digest"], "actor final state")
                    trace = frozen.validate_trace(trace)
                    if (
                        trace["episode_id"] != assignment["episode_id"]
                        or trace["seed"] != assignment["seed"]
                        or receipt["trace_digest"] != trace["trace_digest"]
                        or type(receipt["steps"]) is not int
                        or receipt["steps"] != trace["steps"]
                        or isinstance(receipt["return"], bool)
                        or receipt["return"] != trace["return"]
                        or assignment["ordinal"] in results
                    ):
                        raise GameLearningError("parallel actor returned conflicting episode usage")
                    total_bytes += len(_json(trace))
                    if total_bytes > MAX_BATCH_TRACES:
                        raise GameLearningError("parallel batch trace byte budget exhausted")
                    results[assignment["ordinal"]] = (trace, receipt)
                else:
                    raise GameLearningError("parallel actor returned an undeclared message")
            if set(results) != {item["ordinal"] for item in pending}:
                raise GameLearningError("parallel actors returned a partial episode barrier")
            return results
        finally:
            stopped.set()
            cleanup_failed = False
            for handle in handles:
                try:
                    handle["channel"].settimeout(0.1)
                    _send(handle["channel"], {"type": "cancel"})
                except (OSError, GameLearningError):
                    pass
            for handle in handles:
                process = handle["process"]
                if process is not None:
                    try:
                        process.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    for sig in (signal.SIGTERM, signal.SIGKILL):
                        try:
                            os.killpg(process.pid, sig)
                        except ProcessLookupError:
                            pass
                        try:
                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            continue
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        with _QUARANTINE_LOCK:
                            _QUARANTINED[process.pid] = process
                        cleanup_failed = True
                handle["channel"].close()
            for handle in handles:
                thread = handle["thread"]
                if thread is not None and thread.ident is not None:
                    thread.join(timeout=1.0)
                    if thread.is_alive():
                        cleanup_failed = True
            if cleanup_failed:
                raise GameLearningError(
                    "parallel cleanup is not quiescent; process handles are quarantined and no completion is acknowledged"
                )

    @_central_operation
    def train(
        self,
        *,
        episodes: int,
        resume_state: Mapping[str, Any] | None = None,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any] | None, dict[str, Any]], None] | None = None,
        on_frame: Callable[[dict[str, Any]], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> ParallelTrainingResult:
        count = _int(episodes, "parallel requested episodes", 0, self.learner.config.max_episodes)
        current = self.learner.snapshot()
        if (
            current["committed_episodes"] + count > self.learner.config.max_episodes
            or len(current["inherited_episodes"]) + current["committed_episodes"] + count > MAX_LIFETIME_EPISODES
        ):
            raise GameLearningError("parallel requested work exceeds cumulative episode budgets")
        initial_updates = current["committed_updates"]
        state = None if resume_state is None else self._resume(resume_state)
        if count == 0:
            if state is not None and state["phase"] != "complete":
                raise GameLearningError("pending actors cannot be acknowledged without executed episodes")
            return ParallelTrainingResult(current, state, (), (), 0)
        if state is not None and state["phase"] == "complete":
            state = None
        summaries, receipts = [], []
        remaining = count
        while remaining:
            GamePolicyLearner._guard(cancel, authorize)
            if state is None:
                state = self._batch(min(self.batch_episodes, remaining))
                if on_checkpoint is not None:
                    on_checkpoint(self.learner.snapshot(), None, _copy_json(state))
            pending_count = len(state["assignments"]) - len(state["acknowledged"])
            if pending_count > remaining:
                raise GameLearningError("resume requested fewer episodes than its pinned pending batch")
            results = self._collect(state, on_frame=on_frame, cancel=cancel, authorize=authorize)
            state = self._resume(state)
            for assignment in state["assignments"][len(state["acknowledged"]) :]:
                trace, receipt = results[assignment["ordinal"]]
                verified = _issue_verified_episode(trace, "local_actor_rollout", receipt["receipt_digest"])
                candidate_state = _copy_json(state)

                def commit(
                    snapshot, episode_trace, *, assigned=assignment, issued=receipt, candidate=candidate_state
                ):
                    candidate["acknowledged"].append(
                        {
                            "ordinal": assigned["ordinal"],
                            "episode_id": episode_trace["episode_id"],
                            "trace_digest": episode_trace["trace_digest"],
                            "actor_receipt_digest": issued["receipt_digest"],
                            "policy_digest": snapshot["snapshot_digest"],
                        }
                    )
                    if len(candidate["acknowledged"]) == len(candidate["assignments"]):
                        candidate["phase"] = "complete"
                    if on_checkpoint is not None:
                        on_checkpoint(snapshot, episode_trace, _copy_json(candidate))

                result = self.learner.learn_verified_episode(
                    verified, on_checkpoint=commit, cancel=cancel, authorize=authorize
                )
                state = candidate_state
                summaries.extend(result.episode_summaries)
                receipts.append(receipt)
                remaining -= 1
            if state["phase"] == "complete" and remaining:
                state = None
        return ParallelTrainingResult(
            self.learner.snapshot(),
            state,
            tuple(summaries),
            tuple(receipts),
            self.learner.snapshot()["committed_updates"] - initial_updates,
        )


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-fd", type=int, required=True)
    args = parser.parse_args()
    channel = socket.socket(fileno=args.actor_fd)
    try:
        _worker(channel)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        log.exception("isolated game rollout actor rejected execution")
        try:
            _send(channel, {"type": "error", "error_type": type(exc).__name__, "message": str(exc)[:1000]})
        except (OSError, GameLearningError):
            pass
        return 1
    finally:
        channel.close()


if __name__ == "__main__":
    raise SystemExit(_main())
