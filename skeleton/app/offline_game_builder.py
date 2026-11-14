"""Build a Godot prototype from a bounded, local Jeeves design proposal.

The operator selects an existing digest-pinned GGUF manifest. Model output is
data only: the existing plan guard and deterministic Forge compiler retain
authority. The same total deadline covers planning and the canonical builder.
No hosted fallback, generated-code execution, or automatic quality promotion.
"""
from __future__ import annotations

import asyncio
import ctypes
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Mapping, Callable
import io
import secrets
import sqlite3
import stat
import threading
import zipfile
from pathlib import PurePosixPath

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _identifier
from skeleton.app.jeeves_local_lease import LocalInferenceLease, LocalInferenceLeaseBusy

from skeleton.forge.ai_builder.plan_guard import guard_proposal
from skeleton.forge.ai_builder.plan_schema import PLAN_SCHEMA, RESPONSE_SCHEMA, PlanParseError, parse_model_plan
from skeleton.forge.game_design_spec import compile_brief

SCHEMA = "skeleton.jeeves.local-game-build.v1"
POLICY_ID = "policy://game.forge_design/local-data-proposal@1"
SYSTEM = (
    "You design a small playable game. Return one JSON object only. "
    "Allowed keys: title, fantasy, core_loop, gameplay. "
    "gameplay must contain exactly: difficulty (easy|normal|hard), "
    "theme (moss|neon|ember|frost), objective_label (short text), "
    "player_speed (integer 120..360), encounter_style (swarm|patrol|ranged). "
    "Respect the user's genre, scope and constraints. Never include code, "
    "paths, providers, tools, genre, engine, scope or brief in the object."
)
PROPOSAL_SCHEMA = {**RESPONSE_SCHEMA,
    "required": ["title", "fantasy", "core_loop", "gameplay"],
    "properties": {key: RESPONSE_SCHEMA["properties"][key] for key in
                   ("title", "fantasy", "core_loop", "gameplay")}}


def admit_proposal(compiled: Mapping[str, Any], raw: object) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Whole-proposal admission; a rejected field cannot hide behind good prose."""
    try:
        if isinstance(raw, str) and not raw.lstrip().startswith("{"):
            return dict(compiled), ("json_object_required",)
        parsed = parse_model_plan(raw)
        if set(parsed) != {"title", "fantasy", "core_loop", "gameplay"}:
            return dict(compiled), ("complete_design_required",)
        spec, violations = guard_proposal(compiled, parsed)
    except (PlanParseError, ValueError, TypeError, OverflowError):
        return dict(compiled), ("invalid_json_or_schema",)
    if violations:
        return dict(compiled), tuple(violations)
    if spec.get("spec_id") == compiled.get("spec_id"):
        return dict(compiled), ("no_change",)
    return spec, ()


async def propose(backend: Any, compiled: Mapping[str, Any], *,
                  output_tokens: int, deadline_at: float, repair: bool,
                  workspace_database: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from skeleton.app.jeeves_local_lease import LocalInferenceLease
    from skeleton.ai.runtime.inference.local import (
        LocalInferenceCancelled, LocalInferenceEngine, LocalInferenceRequest,
    )

    engine = LocalInferenceEngine(backend, cache_size=0, max_concurrency=1)
    attempts: list[dict[str, Any]] = []
    prompt = json.dumps({"brief": compiled["brief"], "committed_genre": compiled["genre"],
                         "defaults": compiled.get("gameplay", {})}, ensure_ascii=False)
    status = "rejected"
    spec = dict(compiled)
    closed = False
    try:
        with LocalInferenceLease(workspace_database).hold():
            try:
                for index in range(2 if repair else 1):
                    if deadline_at <= time.monotonic():
                        status = "timed_out"
                        break
                    started = time.monotonic()
                    request = LocalInferenceRequest(
                        prompt=prompt, instructions=SYSTEM, max_output_tokens=output_tokens,
                        structured_output_schema=PROPOSAL_SCHEMA, temperature=0.0,
                        tool_choice="none",
                    )
                    try:
                        answer = await engine.generate(request, deadline=deadline_at,
                                                       resource_max_output_tokens=output_tokens)
                    except (TimeoutError, LocalInferenceCancelled):
                        if time.monotonic() >= deadline_at:
                            status = "timed_out"
                            break
                        raise
                    if (answer.model_digest != backend.model_digest or answer.tool_calls
                            or answer.structured_output is None
                            or answer.finish_reason in {"deadline", "cancelled"}
                            or not answer.execution_receipt_digest):
                        raise ValueError("local model returned no bound structured design")
                    payload = dict(answer.structured_output)
                    spec, violations = admit_proposal(compiled, payload)
                    attempts.append({
                        "attempt": index + 1,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "output_tokens": answer.output_tokens,
                        "response_sha256": sha256(json.dumps(payload, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
                        "execution_receipt_sha256": answer.execution_receipt_digest,
                        "violations": list(violations),
                    })
                    if not violations:
                        status = "accepted"
                        break
                    prompt = json.dumps({
                        "brief": compiled["brief"], "committed_genre": compiled["genre"],
                        "defaults": compiled.get("gameplay", {}),
                        "repair": "Return a complete valid JSON design object; fix these rejected fields.",
                        "rejected_fields": list(violations),
                    }, ensure_ascii=False)
            finally:
                # Physical cleanup occurs while the OS lease is still held.
                await engine.close(cancel_running=True)
                closed = True
    finally:
        if not closed:
            await engine.close(cancel_running=True)
    return spec, {"status": status, "attempts": attempts,
                  "proposal_schema": PLAN_SCHEMA,
                  "model_digest": backend.model_digest,
                  "runtime_digest": backend.runtime_digest,
                  "instruction_policy": POLICY_ID,
                  "instruction_sha256": sha256(SYSTEM.encode("utf-8")).hexdigest(),
                  "network_provider_used": False,
                  "generated_source_admitted": False,
                  "quality_qualified": False}


def publish_create_only(source: Path, destination: Path) -> None:
    """Atomically publish a complete project without replacing another path.

    The pinned Linux runtime uses renameat2(RENAME_NOREPLACE). Windows rename
    already rejects an existing destination. Unsupported hosts fail closed.
    """
    if os.name == "nt":
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        raise OSError(errno.ENOTSUP, "create-only project publication unavailable")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, "create-only project publication rejected")


def qualify_interactive(project: Path, genre: str, deadline_at: float) -> dict[str, Any]:
    """Exercise maintained runtime input; table arithmetic cannot satisfy this."""
    from skeleton.forge.playable_runtime import SMOKE_PATH
    from skeleton.forge.playtest import resolve_binary, scan_log

    binary, source, verified = resolve_binary()
    if not binary:
        raise ValueError("native interactive verification requires Godot")
    logs = []
    for arguments in (("--import",), ("--fixed-fps", "60", "--script", "res://" + SMOKE_PATH)):
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("total deadline exceeded")
        from skeleton.ai.runtime.inference.lease_custody import gguf_child_pass_fds
        inherited = {"pass_fds": gguf_child_pass_fds()} if os.name == "posix" else {}
        run = subprocess.run([binary, "--headless", "--path", str(project), *arguments],
            capture_output=True, text=True, timeout=min(90, remaining), check=False,
            env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1"}, **inherited)
        output = run.stdout + run.stderr
        if run.returncode or scan_log(output):
            raise ValueError("native interactive verification failed")
        logs.append(output)
    lines = [line.split("FORGE_INTERACTIVE_OK ", 1)[1] for line in logs[-1].splitlines()
             if line.startswith("FORGE_INTERACTIVE_OK ")]
    if len(lines) != 1:
        raise ValueError("native runtime produced no unique input receipt")
    receipt = json.loads(lines[0])
    if (receipt.get("genre") != genre or receipt.get("phase") != "won"
            or receipt.get("pause_verified") is not True
            or receipt.get("restart_verified") is not True
            or receipt.get("input_frames", 0) < 20
            or receipt.get("movement_distance", 0) <= 100):
        raise ValueError("native input receipt did not prove the required journey")
    if genre == "platformer":
        if receipt.get("jumps", 0) < 1 or receipt.get("collected", 0) < 5:
            raise ValueError("platformer receipt did not prove jumping and collection")
    elif receipt.get("shots", 0) < 1 or receipt.get("defeated", 0) < 3:
        raise ValueError("combat receipt did not prove the encounter loop")
    return {"input_journey_verified": True, "binary_source": source,
            "binary_artifact_verified": verified, "receipt": receipt,
            "acceptance": "native input journey observed; human playtesting and device performance remain unqualified",
            "log_sha256": sha256("\n".join(logs).encode("utf-8")).hexdigest()}


def run_local_game_build(backend: Any, brief: str, out: Path, *,
                         workspace_database: Path, output_tokens: int = 256,
                         planning_timeout: int = 90, deadline: int = 180,
                         repair: bool = True, require_model: bool = True,
                         playtest: str = "require",
                         cancellation: threading.Event | None = None,
                         on_stage: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Shared operator/workspace operation over the installed model and Forge.

    No model source, engine path or generated program is selected here. The
    caller supplies the already admitted backend; model output remains data.
    All materialization happens privately before create-only publication.
    """
    from skeleton.forge.game_builder import build_playable_game, public_payload
    from skeleton.forge.projector import write_project

    if (not isinstance(brief, str) or not brief.strip()
            or len(brief.encode("utf-8", errors="strict")) > 4000):
        raise ValueError("brief must contain 1..4000 UTF-8 bytes")
    if type(output_tokens) is not int or not 32 <= output_tokens <= 1024:
        raise ValueError("output tokens must be 32..1024")
    if (type(planning_timeout) is not int or type(deadline) is not int
            or not 10 <= planning_timeout <= deadline <= 600):
        raise ValueError("invalid finite planning/total deadline")
    if type(repair) is not bool or type(require_model) is not bool or playtest not in {"off", "auto", "require"}:
        raise ValueError("invalid build controls")
    out = Path(out).expanduser().absolute()
    if out.exists() or out.is_symlink():
        raise ValueError("choose a new project output directory")
    if getattr(backend, "model_id", None) != "jeeves":
        raise ValueError("the installed Jeeves model is required")
    started = time.monotonic()
    deadline_at = started + deadline
    compiled = compile_brief(brief)

    def stage(name: str) -> None:
        if cancellation is not None and cancellation.is_set():
            raise GameBuildRejected(409, "build_interrupted", "The local build was stopped before publication.")
        if time.monotonic() >= deadline_at:
            raise TimeoutError("total build deadline exceeded")
        if on_stage is not None:
            on_stage(name)

    async def planning_call():
        task = asyncio.create_task(propose(
            backend, compiled, output_tokens=output_tokens,
            deadline_at=min(deadline_at, time.monotonic() + planning_timeout),
            repair=repair, workspace_database=workspace_database,
        ))
        cancel_sent = False
        try:
            while not task.done():
                if cancellation is not None and cancellation.is_set() and not cancel_sent:
                    task.cancel()
                    cancel_sent = True
                await asyncio.wait({task}, timeout=0.05)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    stage("planning")
    planning = {"status": "unavailable", "attempts": [], "quality_qualified": False}
    spec = compiled
    try:
        spec, planning = asyncio.run(planning_call())
    except asyncio.CancelledError:
        raise GameBuildRejected(409, "build_interrupted", "The local build was stopped before publication.") from None
    except (ValueError, OSError, RuntimeError):
        planning["reason"] = "local_model_or_lease_unavailable"
    if require_model and planning["status"] != "accepted":
        return {"schema": SCHEMA, "ok": False, "planning": planning,
                "build": None, "reason": "accepted_model_proposal_required"}
    stage("building")

    def planner(committed: Mapping[str, Any]) -> Mapping[str, Any]:
        return {**committed, **{key: spec[key] for key in
                ("title", "fantasy", "core_loop", "gameplay") if key in spec}}

    result = build_playable_game(brief, planner=planner,
        playtest_mode=playtest, deadline_s=max(0.001, deadline_at - time.monotonic()))
    if result["ok"]:
        stage("verifying")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.parent.resolve() != out.parent:
            raise ValueError("project output parent must not contain symbolic links")
        with tempfile.TemporaryDirectory(prefix=".jeeves-game-", dir=out.parent) as temporary:
            staged = Path(temporary) / "project"
            manifest = write_project(staged, result["files"], meta={
                "spec_id": result["spec"]["spec_id"], "genre": result["spec"]["genre"],
                "planning_status": planning["status"],
            })
            if playtest == "require":
                acceptance = qualify_interactive(staged, result["spec"]["genre"], deadline_at)
                result["interactive"] = {**(result.get("interactive") or {}), **acceptance}
            stage("verifying")
            manifest["root"] = str(out)
            (staged / "FORGE_MANIFEST.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
            publish_create_only(staged, out)
            result["project"] = manifest
    return {"schema": SCHEMA, "ok": bool(result["ok"]), "planning": planning,
            "build": public_payload(result, include_files=False),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "general_model_quality_qualified": False}


MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_FILES = 2048
MAX_RECORD_BYTES = 262144
MAX_HISTORY_JOBS = 64
JOB_STATES = ("queued", "planning", "building", "verifying", "complete", "failed")
ACTIVE_STATES = JOB_STATES[:4]
RECEIPT_SCHEMA = "skeleton.jeeves.workspace-game-artifact.v1"


class GameBuildRejected(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def _encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8", errors="strict")


def _object(raw: bytes) -> dict[str, Any]:
    from skeleton.ai.model_runtime.offline_chat import _strict_pairs, _reject_constant
    value = json.loads(raw.decode("utf-8", errors="strict"),
                       object_pairs_hook=_strict_pairs, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def _safe_name(name: object) -> str:
    if (not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= 240
            or "\\" in name or ":" in name or PurePosixPath(name).is_absolute()
            or any(ord(ch) < 32 for ch in name)
            or any(part in {"", ".", ".."} or part.rstrip(" .") != part
                   for part in name.split("/"))):
        raise ValueError("invalid source archive member")
    return name


def _read_regular(path: Path, maximum: int, *, private: bool = False) -> bytes:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 <= before.st_size <= maximum
            or (os.name == "posix" and (before.st_uid != os.getuid()
                or (private and before.st_mode & 0o077)))):
        raise ValueError("unsafe local artifact")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("local artifact changed")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    if (len(raw) > maximum or len(raw) != before.st_size
            or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
               != (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
        raise ValueError("local artifact changed")
    return raw


def _write_private(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    """Commit authority directory entries before terminal SQLite publication.

    POSIX directory fsync is required. Windows rename remains create-only,
    while power-loss directory-flush qualification is independently pending.
    The downloadable ZIP/receipt are authority; the project tree is derived.
    """
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError("artifact publication requires a directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _public_result(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project maintained receipts, excluding host commands, paths and logs."""
    build = report.get("build")
    clean_build = None
    if isinstance(build, Mapping):
        clean_build = {key: build[key] for key in
            ("schema_version", "ok", "spec", "content_schema", "marker", "proof", "file_names")
            if key in build}
        for key in ("check", "core_loop"):
            item = build.get(key)
            if isinstance(item, Mapping):
                clean_build[key] = {name: item[name] for name in ("ok", "passed", "marker", "proof") if name in item}
        item = build.get("playtest")
        if isinstance(item, Mapping):
            clean_build["playtest"] = {name: item[name] for name in ("status", "passed") if name in item}
        item = build.get("interactive")
        if isinstance(item, Mapping):
            clean_build["interactive"] = {name: item[name] for name in
                ("schema", "controls", "features", "native_boot_verified", "input_journey_verified",
                 "binary_artifact_verified", "receipt", "log_sha256", "acceptance") if name in item}
        item = build.get("project")
        if isinstance(item, Mapping):
            clean_build["project"] = {name: item[name] for name in
                ("files", "count", "sha256", "source_sha256") if name in item}
            if isinstance(item.get("meta"), Mapping):
                clean_build["project"]["meta"] = {name: item["meta"][name] for name in
                    ("spec_id", "genre", "planning_status") if name in item["meta"]}
    result = {"schema": SCHEMA, "ok": report.get("ok") is True,
              "planning": report.get("planning"), "build": clean_build,
              "general_model_quality_qualified": False}
    for key in ("reason", "elapsed_seconds"):
        if key in report:
            result[key] = report[key]
    if len(_encoded(result)) > MAX_RECORD_BYTES:
        raise ValueError("game result exceeds record budget")
    return result


class LocalGameBuilder:
    """One durable, model-scoped operation journal in the existing chat file.

    The work lease is distinct from the inference lease: it protects build
    admission/recovery/publication while chat may run after planning finishes.
    No pending request is automatically executed again after process restart.
    """

    def __init__(self, backend: Any, database: str | Path, artifact_root: Path | None = None) -> None:
        from skeleton.app.local_ai import _model_tokenizer_digest
        self.backend = backend
        self.database = Path(database).expanduser().absolute()
        if str(database) == ":memory:" or self.database.parent.resolve() != self.database.parent:
            raise GameBuildRejected(503, "private_workspace_required", "A private persistent local workspace is required.")
        self.model_digest = backend.model_digest
        self.tokenizer_digest = _model_tokenizer_digest(backend)
        self.runtime_digest = backend.runtime_digest
        self.model_id = str(getattr(backend, "model_id", ""))
        self.artifact_root = (Path(artifact_root).expanduser().absolute() if artifact_root is not None else
            self.database.with_name("." + self.database.stem + ".game-builds"))
        if self.artifact_root.parent.resolve() != self.artifact_root.parent:
            raise GameBuildRejected(503, "private_artifacts_required", "Private game artifact storage is unavailable.")
        self.artifact_root.mkdir(mode=0o700, parents=False, exist_ok=True)
        self._root_identity = self._check_root(initial=True)
        self._work_lease = LocalInferenceLease(self.database.with_name(self.database.name + ".game-build"))
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._closing = False
        self._closed = False
        self._store = OfflineChatStore(self.database)
        try:
            self._store._db.execute("""CREATE TABLE IF NOT EXISTS offline_game_builds (
                model_digest TEXT NOT NULL, tokenizer_digest TEXT NOT NULL,
                request_id TEXT NOT NULL, request_digest TEXT NOT NULL,
                runtime_digest TEXT NOT NULL, model_id TEXT NOT NULL,
                brief TEXT NOT NULL, brief_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','planning','building','verifying','complete','failed')),
                stage TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                artifact_id TEXT NOT NULL, result_json TEXT, error_code TEXT,
                archive_sha256 TEXT, archive_bytes INTEGER, file_count INTEGER,
                receipt_sha256 TEXT,
                PRIMARY KEY(model_digest,tokenizer_digest,request_id)
            )""")
            self._store._db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS offline_game_build_active
                ON offline_game_builds((1)) WHERE state IN ('queued','planning','building','verifying')""")
            try:
                with self._work_lease.hold():
                    self._recover()
            except LocalInferenceLeaseBusy:
                pass  # A live peer owns these rows; startup never fails it.
        except BaseException:
            self._store.close()
            raise

    def _check_root(self, *, initial: bool = False) -> tuple[int, int]:
        item = self.artifact_root.lstat()
        if (not stat.S_ISDIR(item.st_mode)
                or (os.name == "posix" and (item.st_uid != os.getuid() or item.st_mode & 0o077))):
            raise GameBuildRejected(503, "private_artifacts_required", "Private game artifact storage is unavailable.")
        identity = (item.st_dev, item.st_ino)
        if not initial and identity != self._root_identity:
            raise GameBuildRejected(503, "artifact_storage_changed", "Private game artifact storage changed.")
        return identity

    @staticmethod
    def limits() -> dict[str, int]:
        return {"brief_utf8_bytes": 4000, "archive_bytes": MAX_ARCHIVE_BYTES,
                "deadline_seconds": 180, "output_tokens": 256, "history_jobs": MAX_HISTORY_JOBS}

    def availability(self) -> dict[str, Any]:
        from skeleton.forge.playtest import resolve_binary
        if self._closing:
            return {"ready": False, "code": "local_service_shutting_down"}
        try:
            if (self.model_id != "jeeves" or self.backend.model_digest != self.model_digest
                    or self.backend.runtime_digest != self.runtime_digest):
                return {"ready": False, "code": "local_primary_identity_changed"}
            from skeleton.app.local_ai import _model_tokenizer_digest
            if _model_tokenizer_digest(self.backend) != self.tokenizer_digest:
                return {"ready": False, "code": "local_tokenizer_identity_changed"}
            checker = getattr(self.backend, "check_readiness", None)
            if not callable(checker) or not callable(getattr(self.backend, "infer", None)):
                return {"ready": False, "code": "local_structured_model_unavailable"}
            checker()
            getter = getattr(self.backend, "generation_limits", None)
            limits = getter() if callable(getter) else None
            if (not isinstance(limits, dict) or type(limits.get("max_output_tokens")) is not int
                    or limits["max_output_tokens"] < 256
                    or "structured-output" not in getattr(self.backend, "protocol_capabilities", ())):
                return {"ready": False, "code": "local_structured_model_budget_unavailable"}
            if not resolve_binary()[0]:
                return {"ready": False, "code": "native_godot_unavailable"}
            self._check_root()
            if self._work_lease.inspect()["state"] in {"busy", "unavailable"}:
                return {"ready": False, "code": "local_game_build_busy"}
            if LocalInferenceLease(self.database).inspect()["state"] in {"busy", "unavailable"}:
                return {"ready": False, "code": "local_inference_busy"}
        except Exception:
            return {"ready": False, "code": "local_model_or_storage_unavailable"}
        return {"ready": True, "code": "ready"}

    def _row(self, request_id: str) -> dict[str, Any] | None:
        with self._store._lock:
            cursor = self._store._db.execute(
                "SELECT * FROM offline_game_builds WHERE model_digest=? AND tokenizer_digest=? AND request_id=?",
                (self.model_digest, self.tokenizer_digest, request_id))
            row = cursor.fetchone()
            return None if row is None else dict(zip((x[0] for x in cursor.description), row))

    def _public(self, row: Mapping[str, Any]) -> dict[str, Any]:
        state = row["state"]
        if state not in JOB_STATES:
            raise GameBuildRejected(503, "invalid_build_record", "The saved game build record is unavailable.")
        result = None if row["result_json"] is None else _object(row["result_json"].encode("utf-8"))
        archive = None if state != "complete" else {
            "sha256": row["archive_sha256"], "bytes": row["archive_bytes"], "file_count": row["file_count"]}
        error = None if row["error_code"] is None else {
            "code": row["error_code"], "message": "The build did not complete. Its saved request will not run again automatically."}
        return {"request_id": row["request_id"], "state": state, "terminal": state in {"complete", "failed"},
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "brief_sha256": row["brief_sha256"], "result": result, "archive": archive, "error": error}

    def get(self, request_id: str) -> dict[str, Any]:
        try:
            rid = _identifier("game request id", request_id)
        except ValueError:
            raise GameBuildRejected(400, "invalid_request_id", "Use a bounded game request identifier.") from None
        row = self._row(rid)
        if row is None:
            raise GameBuildRejected(404, "unknown_game_build", "This local model has no saved build with that identifier.")
        return self._public(row)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._store._lock:
            rows = self._store._db.execute(
                "SELECT request_id FROM offline_game_builds WHERE model_digest=? AND tokenizer_digest=? "
                "ORDER BY created_at DESC, request_id LIMIT 100", (self.model_digest, self.tokenizer_digest)).fetchall()
        return [self.get(row[0]) for row in rows]

    def submit(self, request_id: str, brief: str) -> dict[str, Any]:
        try:
            rid = _identifier("game request id", request_id)
            if (not isinstance(brief, str) or not brief.strip()
                    or not 1 <= len(brief.encode("utf-8", errors="strict")) <= 4000):
                raise ValueError("brief budget")
            compile_brief(brief)
        except (ValueError, UnicodeError, TypeError):
            raise GameBuildRejected(400, "invalid_game_brief", "Use a valid game brief of 1..4000 UTF-8 bytes and supported gameplay choices.") from None
        digest = sha256(_encoded({"brief": brief, "model": self.model_digest,
            "tokenizer": self.tokenizer_digest, "runtime": self.runtime_digest,
            "policy": POLICY_ID, "instruction_sha256": sha256(SYSTEM.encode("utf-8")).hexdigest(),
            "proposal_schema_sha256": sha256(_encoded(PROPOSAL_SCHEMA)).hexdigest(),
            "limits": self.limits()})).hexdigest()
        with self._lock:
            existing = self._row(rid)
            if existing is not None:
                if existing["request_digest"] != digest:
                    raise GameBuildRejected(409, "game_request_conflict", "This request identifier already belongs to a different game brief or runtime policy.")
                return self._public(existing)
            if self._worker is not None and self._worker.is_alive():
                raise GameBuildRejected(423, "local_game_build_busy", "Another local game build is already active.")
            readiness = self.availability()
            if not readiness["ready"]:
                raise GameBuildRejected(423 if readiness["code"] in {"local_game_build_busy", "local_inference_busy"} else 503,
                    readiness["code"], "A ready local Jeeves model and native Godot are required for a new build.")
            self._cancel = threading.Event()
            admitted = threading.Event()
            failures: list[GameBuildRejected] = []
            worker = threading.Thread(target=self._run, args=(rid, brief, digest, admitted, failures),
                                      name="jeeves-local-game", daemon=False)
            self._worker = worker
            worker.start()
        if not admitted.wait(12):
            self._cancel.set()
            raise GameBuildRejected(503, "game_admission_unavailable", "Local build admission did not settle; check this request before submitting a new one.")
        if failures:
            existing = self._row(rid)
            if existing is not None and existing["request_digest"] == digest:
                return self._public(existing)
            raise failures[0]
        return self.get(rid)

    def _set_state(self, rid: str, state: str, *, stage: str | None = None) -> None:
        if state not in ACTIVE_STATES:
            raise ValueError("invalid active game state")
        with self._store._transaction():
            cursor = self._store._db.execute(
                "UPDATE offline_game_builds SET state=?,stage=?,updated_at=? WHERE model_digest=? "
                "AND tokenizer_digest=? AND request_id=? AND state IN ('queued','planning','building','verifying')",
                (state, stage or state, time.time(), self.model_digest, self.tokenizer_digest, rid))
            if cursor.rowcount != 1:
                raise ValueError("game build finality conflict")

    def _fail(self, rid: str, code: str, result: dict[str, Any] | None = None) -> None:
        with self._store._transaction():
            self._store._db.execute(
                "UPDATE offline_game_builds SET state='failed',stage='failed',updated_at=?,error_code=?,result_json=? "
                "WHERE model_digest=? AND tokenizer_digest=? AND request_id=? AND state IN ('queued','planning','building','verifying')",
                (time.time(), code, None if result is None else _encoded(result).decode("utf-8"),
                 self.model_digest, self.tokenizer_digest, rid))

    def _run(self, rid: str, brief: str, digest: str, admitted: threading.Event,
             failures: list[GameBuildRejected]) -> None:
        inserted = False
        try:
            with self._work_lease.hold():
                self._recover()
                now = time.time()
                artifact_id = "game-" + sha256(_encoded([self.model_digest, self.tokenizer_digest, rid])).hexdigest()
                with self._store._transaction():
                    if self._cancel.is_set() or self._closing:
                        raise GameBuildRejected(503, "local_service_shutting_down", "The local service is shutting down.")
                    count = self._store._db.execute("SELECT COUNT(*) FROM offline_game_builds").fetchone()[0]
                    if count >= MAX_HISTORY_JOBS:
                        raise GameBuildRejected(429, "local_game_history_full", "This workspace has reached its bounded game build history limit.")
                    self._store._db.execute(
                        "INSERT INTO offline_game_builds (model_digest,tokenizer_digest,request_id,request_digest,"
                        "runtime_digest,model_id,brief,brief_sha256,state,stage,created_at,updated_at,artifact_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.model_digest, self.tokenizer_digest, rid, digest, self.runtime_digest, self.model_id,
                         brief, sha256(brief.encode("utf-8")).hexdigest(), "queued", "queued", now, now, artifact_id))
                inserted = True
                admitted.set()
                deadline_at = time.monotonic() + 180
                self._check_root()
                with tempfile.TemporaryDirectory(prefix=".pending-game-", dir=self.artifact_root) as temporary:
                    bundle = Path(temporary) / "bundle"
                    bundle.mkdir(mode=0o700)
                    report = run_local_game_build(self.backend, brief, bundle / "project",
                        workspace_database=self.database, output_tokens=256, planning_timeout=90, deadline=180,
                        repair=True, require_model=True, playtest="require", cancellation=self._cancel,
                        on_stage=lambda state: self._set_state(rid, state))
                    result = _public_result(report)
                    build = result.get("build") or {}
                    if (not result["ok"] or (result.get("planning") or {}).get("status") != "accepted"
                            or (result.get("planning") or {}).get("model_digest") != self.model_digest
                            or (result.get("planning") or {}).get("runtime_digest") != self.runtime_digest
                            or build.get("ok") is not True
                            or (build.get("interactive") or {}).get("native_boot_verified") is not True
                            or (build.get("interactive") or {}).get("input_journey_verified") is not True):
                        self._fail(rid, "model_or_native_qualification_failed", result)
                        return
                    if self._cancel.is_set() or self._closing:
                        self._fail(rid, "build_interrupted")
                        return
                    if time.monotonic() >= deadline_at:
                        self._fail(rid, "total_deadline_exceeded")
                        return
                    self._set_state(rid, "verifying", stage="packaging")
                    archive, count = self._package(bundle / "project", result)
                    row = self._row(rid)
                    receipt = {"schema": RECEIPT_SCHEMA,
                        **{key: row[key] for key in ("request_id", "request_digest", "model_digest", "tokenizer_digest", "runtime_digest", "artifact_id")},
                        "archive_sha256": sha256(archive).hexdigest(), "archive_bytes": len(archive),
                        "file_count": count, "result": result}
                    encoded_receipt = _encoded(receipt)
                    if len(encoded_receipt) > MAX_RECORD_BYTES:
                        raise ValueError("artifact receipt exceeds byte budget")
                    _write_private(bundle / "project.zip", archive)
                    _write_private(bundle / "receipt.json", encoded_receipt)
                    with self._store._transaction():
                        cursor = self._store._db.execute(
                            "UPDATE offline_game_builds SET stage='publishing',updated_at=?,result_json=?,"
                            "archive_sha256=?,archive_bytes=?,file_count=?,receipt_sha256=? WHERE model_digest=? "
                            "AND tokenizer_digest=? AND request_id=? AND state='verifying'",
                            (time.time(), _encoded(result).decode("utf-8"), receipt["archive_sha256"], len(archive), count,
                             sha256(encoded_receipt).hexdigest(), self.model_digest, self.tokenizer_digest, rid))
                        if cursor.rowcount != 1:
                            raise ValueError("game publication state conflict")
                    self._check_root()
                    if self._cancel.is_set() or self._closing:
                        self._fail(rid, "build_interrupted")
                        return
                    if time.monotonic() >= deadline_at:
                        self._fail(rid, "total_deadline_exceeded")
                        return
                    try:
                        _fsync_directory(bundle)
                        publish_create_only(bundle, self.artifact_root / artifact_id)
                        # A crash here is reconciled only from the previously
                        # recorded exact identities, never a model rerun.
                        self._verify(self._row(rid))
                        _fsync_directory(self.artifact_root)
                        self._complete(rid)
                    except Exception:
                        # Ordinary publication failures settle while this
                        # worker still owns the work lease. Hard process death
                        # alone leaves the row for startup reconciliation.
                        try:
                            self._verify(self._row(rid))
                            _fsync_directory(self.artifact_root / artifact_id)
                            _fsync_directory(self.artifact_root)
                            self._complete(rid)
                        except Exception:
                            self._fail(rid, "artifact_publication_failed")
        except LocalInferenceLeaseBusy:
            if inserted:
                self._fail(rid, "local_game_build_busy")
            else:
                failures.append(GameBuildRejected(423, "local_game_build_busy", "Another local game build owns this workspace."))
        except GameBuildRejected as exc:
            if inserted:
                self._fail(rid, exc.code)
            else:
                failures.append(exc)
        except BaseException:
            if inserted:
                row = self._row(rid)
                # Preserve a publishing record when durable source may already
                # exist; the next lease owner performs exact recovery.
                if row is not None and row["stage"] != "publishing":
                    self._fail(rid, "build_interrupted" if self._cancel.is_set() else "local_game_build_failed")
            else:
                failures.append(GameBuildRejected(503, "game_admission_unavailable", "Local game build admission failed."))
        finally:
            admitted.set()

    def _complete(self, rid: str) -> None:
        with self._store._transaction():
            cursor = self._store._db.execute(
                "UPDATE offline_game_builds SET state='complete',stage='complete',updated_at=?,error_code=NULL "
                "WHERE model_digest=? AND tokenizer_digest=? AND request_id=? AND state='verifying' AND stage='publishing'",
                (time.time(), self.model_digest, self.tokenizer_digest, rid))
            if cursor.rowcount != 1:
                raise ValueError("game build terminal conflict")

    def _package(self, project: Path, result: dict[str, Any]) -> tuple[bytes, int]:
        from skeleton.forge.source_manifest import source_manifest
        manifest_path = project / "FORGE_MANIFEST.json"
        manifest = _object(_read_regular(manifest_path, MAX_RECORD_BYTES))
        names, hashes = manifest.get("files"), manifest.get("sha256")
        if (not isinstance(names, list) or not 1 <= len(names) <= MAX_FILES - 2
                or not isinstance(hashes, dict) or set(names) != set(hashes) or len(names) != len(set(names))):
            raise ValueError("invalid canonical source manifest")
        files: dict[str, str] = {}
        total = 0
        for name in names:
            _safe_name(name)
            candidate = project / name
            if candidate.parent.resolve() != candidate.parent:
                raise ValueError("source directory symlink")
            raw = _read_regular(candidate, MAX_SOURCE_BYTES - total)
            total += len(raw)
            if sha256(raw).hexdigest() != hashes[name]:
                raise ValueError("canonical source changed")
            files[name] = raw.decode("utf-8", errors="strict")
        if source_manifest(files)["sha256"] != manifest.get("source_sha256"):
            raise ValueError("canonical source manifest digest mismatch")
        manifest["root"] = "project"
        manifest_path.write_bytes(_encoded(manifest))
        bodies = {name: text.encode("utf-8") for name, text in files.items()}
        bodies["FORGE_MANIFEST.json"] = _encoded(manifest)
        bodies["JEEVES_BUILD.json"] = _encoded(result)
        if sum(map(len, bodies.values())) > MAX_SOURCE_BYTES:
            raise ValueError("source archive exceeds expanded byte budget")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, raw in sorted(bodies.items()):
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(item, raw)
        payload = stream.getvalue()
        if not 1 <= len(payload) <= MAX_ARCHIVE_BYTES:
            raise ValueError("source archive exceeds compressed byte budget")
        return payload, len(bodies)

    def _verify(self, row: Mapping[str, Any]) -> bytes:
        self._check_root()
        expected_id = "game-" + sha256(_encoded([row["model_digest"], row["tokenizer_digest"], row["request_id"]])).hexdigest()
        if row["artifact_id"] != expected_id:
            raise ValueError("artifact scope mismatch")
        bundle = self.artifact_root / expected_id
        details = bundle.lstat()
        if (not stat.S_ISDIR(details.st_mode)
                or (os.name == "posix" and (details.st_uid != os.getuid() or details.st_mode & 0o077))):
            raise ValueError("unsafe artifact directory")
        raw = _read_regular(bundle / "project.zip", MAX_ARCHIVE_BYTES, private=True)
        if (len(raw) != row["archive_bytes"] or sha256(raw).hexdigest() != row["archive_sha256"]):
            raise ValueError("source archive changed")
        encoded_receipt = _read_regular(bundle / "receipt.json", MAX_RECORD_BYTES, private=True)
        if sha256(encoded_receipt).hexdigest() != row["receipt_sha256"]:
            raise ValueError("artifact receipt changed")
        receipt = _object(encoded_receipt)
        for key in ("request_id", "request_digest", "model_digest", "tokenizer_digest", "runtime_digest", "artifact_id",
                    "archive_sha256", "archive_bytes", "file_count"):
            if receipt.get(key) != row[key]:
                raise ValueError("artifact receipt scope mismatch")
        if (receipt.get("schema") != RECEIPT_SCHEMA
                or _encoded(receipt.get("result")) != row["result_json"].encode("utf-8")):
            raise ValueError("artifact result identity mismatch")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if (not 1 <= len(members) <= MAX_FILES or len(members) != row["file_count"]
                    or sum(member.file_size for member in members) > MAX_SOURCE_BYTES):
                raise ValueError("invalid archive bounds")
            seen = set()
            content: dict[str, bytes] = {}
            for member in members:
                name = _safe_name(member.filename)
                mode = member.external_attr >> 16
                if (name.casefold() in seen or member.is_dir() or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                        or member.flag_bits & 1 or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                    raise ValueError("invalid archive entry")
                seen.add(name.casefold())
                content[name] = archive.read(member)
                if len(content[name]) != member.file_size:
                    raise ValueError("archive content length mismatch")
            if "project.godot" not in seen or "forge_manifest.json" not in seen or "jeeves_build.json" not in seen:
                raise ValueError("incomplete source archive")
            from skeleton.forge.source_manifest import source_manifest
            manifest = _object(content["FORGE_MANIFEST.json"])
            sources = {name: body.decode("utf-8", errors="strict") for name, body in content.items()
                       if name not in {"FORGE_MANIFEST.json", "JEEVES_BUILD.json"}}
            source = source_manifest(sources)
            if (manifest.get("root") != "project" or set(manifest.get("files", [])) != set(sources)
                    or manifest.get("sha256") != source["files"]
                    or manifest.get("source_sha256") != source["sha256"]
                    or _encoded(_object(content["JEEVES_BUILD.json"])) != row["result_json"].encode("utf-8")):
                raise ValueError("archive source provenance mismatch")
        return raw

    def archive(self, request_id: str) -> bytes:
        self.get(request_id)
        row = self._row(request_id)
        if row["state"] != "complete":
            raise GameBuildRejected(409, "game_archive_not_ready", "A verified source archive is available only after the build completes.")
        try:
            return self._verify(row)
        except Exception:
            raise GameBuildRejected(409, "game_archive_changed", "The saved source archive failed its integrity check; no bytes were exported.") from None

    def _recover(self) -> None:
        # Caller owns the distinct work lease. A live peer can therefore never
        # be mistaken for an interrupted job, including before first inference.
        with self._store._lock:
            cursor = self._store._db.execute("SELECT * FROM offline_game_builds WHERE state IN ('queued','planning','building','verifying')")
            rows = [dict(zip((x[0] for x in cursor.description), row)) for row in cursor.fetchall()]
        for row in rows:
            completed = False
            if row["stage"] == "publishing":
                try:
                    self._verify(row)
                    _fsync_directory(self.artifact_root / row["artifact_id"])
                    _fsync_directory(self.artifact_root)
                    completed = True
                except Exception:
                    pass
            with self._store._transaction():
                self._store._db.execute(
                    "UPDATE offline_game_builds SET state=?,stage=?,updated_at=?,error_code=? WHERE model_digest=? "
                    "AND tokenizer_digest=? AND request_id=? AND state IN ('queued','planning','building','verifying')",
                    ("complete" if completed else "failed", "complete" if completed else "failed", time.time(),
                     None if completed else "interrupted_build", row["model_digest"], row["tokenizer_digest"], row["request_id"]))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closing = True
            self._cancel.set()
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=190)
            if worker.is_alive():
                # Keep the authority open while an owned worker drains. The
                # caller must not close the application underneath it.
                raise GameBuildRejected(503, "game_worker_draining", "The local build worker is still settling.")
        with self._lock:
            if not self._closed:
                self._store.close()
                self._closed = True


__all__ = ["LocalGameBuilder", "GameBuildRejected", "run_local_game_build", "admit_proposal",
           "publish_create_only", "propose", "qualify_interactive", "SCHEMA", "SYSTEM", "PROPOSAL_SCHEMA"]

