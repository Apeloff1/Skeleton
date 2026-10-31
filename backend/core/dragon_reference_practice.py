"""Source-bound measured exercises inside the existing Dragon practice store.

This adapter plays one fixed coded reference environment. A reviewed annotation
labels the exercise; it does not supply executable code, truth or model weights.
SQLite owns finite attempt credits and receipts. Futures are physical handles.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex

from core.game_learning import GameLearningError

MAX_BYTES = 1024 * 1024
MAX_SECONDS = 10
TARGET = "eight_bit_tile_1983"
_active = {}


def _json(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError) as exc:
        raise GameLearningError("practice_payload", "Practice evidence must be finite JSON.") from exc
    if len(raw) > MAX_BYTES:
        raise GameLearningError("practice_evidence_limit", "Practice evidence exceeded one MiB.", 413)
    return raw


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _connect(path):
    path = Path(path)
    try:
        info = path.lstat()
        if (
            not path.is_absolute()
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise OSError("private regular existing practice storage required")
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=2)
        after = path.lstat()
        if (info.st_dev, info.st_ino) != (after.st_dev, after.st_ino):
            db.close()
            raise OSError("practice storage identity changed")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=2000")
        db.execute("PRAGMA foreign_keys=ON")
        return db
    except (OSError, sqlite3.Error) as exc:
        raise GameLearningError(
            "practice_storage_unavailable",
            "Initialize private Dragon practice storage through app setup.",
            503,
        ) from exc


def _schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS dragon_reference_practice_intents(
          owner TEXT NOT NULL, practice_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
          request_digest TEXT NOT NULL, source_pin_json TEXT NOT NULL,
          runtime_digest TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL,
          worker_token TEXT NOT NULL, lease_until REAL NOT NULL, created_at REAL NOT NULL,
          PRIMARY KEY(owner,practice_id));
        CREATE TABLE IF NOT EXISTS dragon_reference_practice_attempts(
          owner TEXT NOT NULL, practice_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
          status TEXT NOT NULL, started_at REAL NOT NULL, completed_at REAL,
          checkpoint_json TEXT NOT NULL, result_json TEXT, result_digest TEXT,
          error_code TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(owner,practice_id,ordinal),
          FOREIGN KEY(owner,practice_id)
            REFERENCES dragon_reference_practice_intents(owner,practice_id));
        CREATE INDEX IF NOT EXISTS dragon_reference_practice_daily
          ON dragon_reference_practice_attempts(owner,started_at);
    """)


def initialize_reference_practice(path: Path) -> None:
    db = _connect(path)
    try:
        _schema(db)
    finally:
        db.close()


def _source_pin(candidate):
    if not isinstance(candidate, dict) or candidate.get("state") != "approved":
        raise GameLearningError("practice_review_required", "Approve a current source reference first.", 409)
    pin = {
        key: candidate.get(key)
        for key in (
            "candidate_id",
            "version",
            "mechanic",
            "knowledge",
            "source_ref",
            "source_digest",
            "valid_until",
        )
    }
    knowledge = pin["knowledge"]
    if (
        not isinstance(pin["candidate_id"], str)
        or not 1 <= len(pin["candidate_id"]) <= 128
        or type(pin["version"]) is not int
        or pin["version"] < 1
        or not isinstance(knowledge, dict)
        or any(
            not isinstance(knowledge.get(key), str) or not knowledge[key]
            for key in ("source_id", "revision_digest", "note_id")
        )
        or not isinstance(pin["source_ref"], dict)
        or set(pin["source_ref"])
        != {
            "schema_version",
            "session_id",
            "source_id",
            "source_digest",
            "request_digest",
            "consent_id",
        }
        | (
            {"source_use_version"}
            if pin["source_ref"].get("schema_version") == "skeleton.dragon.crawler_reference.v2"
            else set()
        )
        or pin["source_ref"].get("schema_version")
        not in {"skeleton.dragon.crawler_reference.v1", "skeleton.dragon.crawler_reference.v2"}
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 256
            for key, value in pin["source_ref"].items()
            if key != "source_use_version"
        )
        or pin["source_ref"].get("schema_version") == "skeleton.dragon.crawler_reference.v2"
        and (
            type(pin["source_ref"]["source_use_version"]) is not int
            or not 0 <= pin["source_ref"]["source_use_version"] <= 2**31 - 1
        )
        or not isinstance(pin["source_digest"], str)
        or len(pin["source_digest"]) != 64
        or not isinstance(pin["mechanic"], str)
        or not 1 <= len(pin["mechanic"]) <= 64
    ):
        raise GameLearningError(
            "practice_source_pin", "Exact reviewed reference evidence is incomplete.", 409
        )
    if len(_json(pin)) > 16384:
        raise GameLearningError("practice_source_pin", "Reviewed reference identity exceeds its bound.", 413)
    return pin


def _runtime_digest():
    from skeleton.jeeves import game_learning_runtime

    return _digest(
        {
            "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime": hashlib.sha256(Path(game_learning_runtime.__file__).read_bytes()).hexdigest(),
            "engine_sources": game_learning_runtime._source_digest(),
            "target": TARGET,
            "controller": "goal_dx_directional_reference_v1",
        }
    )


def _claim(path, owner, pin, request, runtime):
    identifier = _digest([owner, pin["candidate_id"], request["idempotency_key"]])
    active = _active.get((str(path), owner, identifier))
    if active is not None and not active.done():
        raise GameLearningError("practice_running", "This exact practice attempt is still running.", 409)
    now = time.time()
    db = _connect(path)
    try:
        _schema(db)
        db.execute("BEGIN IMMEDIATE")
        size = db.execute(
            "SELECT length(CAST(source_pin_json AS BLOB)) FROM dragon_reference_practice_intents "
            "WHERE owner=? AND practice_id=?",
            (owner, identifier),
        ).fetchone()
        if size is not None and (type(size[0]) is not int or not 1 <= size[0] <= 16384):
            raise GameLearningError(
                "practice_receipt_corrupt", "Stored practice identity exceeds its bound.", 503
            )
        prior = db.execute(
            "SELECT * FROM dragon_reference_practice_intents WHERE owner=? AND practice_id=?",
            (owner, identifier),
        ).fetchone()
        if prior:
            if prior["request_digest"] != _digest(request) or prior["source_pin_json"] != _json(pin).decode():
                raise GameLearningError(
                    "practice_idempotency_conflict", "Practice key binds different input.", 409
                )
            if prior["status"] == "completed":
                size = db.execute(
                    "SELECT length(CAST(result_json AS BLOB)) FROM dragon_reference_practice_attempts "
                    "WHERE owner=? AND practice_id=? AND ordinal=? AND status='completed'",
                    (owner, identifier, prior["attempt"]),
                ).fetchone()
                if size is None or type(size[0]) is not int or not 1 <= size[0] <= MAX_BYTES:
                    raise GameLearningError(
                        "practice_receipt_corrupt",
                        "Stored practice evidence exceeds its bound.",
                        503,
                    )
                receipt = db.execute(
                    "SELECT result_json,result_digest FROM dragon_reference_practice_attempts "
                    "WHERE owner=? AND practice_id=? AND ordinal=? AND status='completed'",
                    (owner, identifier, prior["attempt"]),
                ).fetchone()
                if (
                    receipt is None
                    or hashlib.sha256(receipt["result_json"].encode()).hexdigest() != receipt["result_digest"]
                ):
                    raise GameLearningError(
                        "practice_receipt_corrupt", "Stored practice evidence differs.", 503
                    )
                return identifier, None, prior["attempt"], json.loads(receipt["result_json"])
            if prior["status"] == "running" and prior["lease_until"] > now:
                raise GameLearningError("practice_running", "A bounded practice lease is still active.", 409)
            if prior["runtime_digest"] != runtime:
                raise GameLearningError(
                    "practice_runtime_changed",
                    "Start a new practice request for this runtime.",
                    409,
                )
            if prior["attempt"] >= 3:
                raise GameLearningError(
                    "practice_attempt_limit",
                    "This request exhausted its three attempt credits.",
                    429,
                )
            db.execute(
                "UPDATE dragon_reference_practice_attempts SET status='interrupted',error_code='lease_expired',completed_at=? "
                "WHERE owner=? AND practice_id=? AND status='running'",
                (now, owner, identifier),
            )
        elif (
            db.execute(
                "SELECT COUNT(*) FROM dragon_reference_practice_intents WHERE owner=?", (owner,)
            ).fetchone()[0]
            >= 512
        ):
            raise GameLearningError(
                "practice_intent_limit",
                "This owner reached the stored practice request limit.",
                429,
            )
        active_count = sum(not future.done() for future in _active.values())
        live = db.execute(
            "SELECT owner FROM dragon_reference_practice_intents WHERE status='running' AND lease_until>?",
            (now,),
        ).fetchall()
        local_owner_active = any(key[1] == owner and not future.done() for key, future in _active.items())
        if (
            active_count >= 2
            or local_owner_active
            or len(live) >= 2
            or any(row["owner"] == owner for row in live)
        ):
            raise GameLearningError(
                "practice_capacity",
                "Practice allows one live exercise per owner and two in total.",
                429,
            )
        day = int(now // 86400) * 86400
        if (
            db.execute(
                "SELECT COUNT(*) FROM dragon_reference_practice_attempts WHERE owner=? AND started_at>=? AND started_at<?",
                (owner, day, day + 86400),
            ).fetchone()[0]
            >= 16
        ):
            raise GameLearningError(
                "practice_daily_limit",
                "The sixteen-attempt daily practice budget is exhausted.",
                429,
            )
        ordinal = 1 if prior is None else prior["attempt"] + 1
        token = token_hex(24)
        if prior is None:
            db.execute(
                "INSERT INTO dragon_reference_practice_intents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    owner,
                    identifier,
                    pin["candidate_id"],
                    _digest(request),
                    _json(pin).decode(),
                    runtime,
                    "running",
                    ordinal,
                    token,
                    now + MAX_SECONDS + 5,
                    now,
                ),
            )
        else:
            db.execute(
                "UPDATE dragon_reference_practice_intents SET status='running',attempt=?,worker_token=?,lease_until=? "
                "WHERE owner=? AND practice_id=?",
                (ordinal, token, now + MAX_SECONDS + 5, owner, identifier),
            )
        db.execute(
            "INSERT INTO dragon_reference_practice_attempts "
            "(owner,practice_id,ordinal,status,started_at,checkpoint_json) VALUES(?,?,?,'running',?,'[]')",
            (owner, identifier, ordinal, now),
        )
        db.commit()
        return identifier, token, ordinal, None
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def _save(path, owner, identifier, token, ordinal, *, trace=None, result=None, error=None):
    db = _connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        intent = db.execute(
            "SELECT * FROM dragon_reference_practice_intents WHERE owner=? AND practice_id=? "
            "AND worker_token=? AND attempt=? AND status='running'",
            (owner, identifier, token, ordinal),
        ).fetchone()
        if intent is None or intent["lease_until"] <= time.time():
            raise GameLearningError(
                "practice_lease_lost", "Practice no longer owns a live execution lease.", 409
            )
        if trace is not None:
            db.execute(
                "UPDATE dragon_reference_practice_attempts SET checkpoint_json=? "
                "WHERE owner=? AND practice_id=? AND ordinal=? AND status='running'",
                (_json(trace).decode(), owner, identifier, ordinal),
            )
        if result is not None or error is not None:
            status_value = "completed" if result is not None else "interrupted"
            payload = None if result is None else _json(result).decode()
            db.execute(
                "UPDATE dragon_reference_practice_attempts SET status=?,completed_at=?,result_json=?,result_digest=?,error_code=?, "
                "checkpoint_json=CASE WHEN ? IS NOT NULL THEN '[]' ELSE checkpoint_json END "
                "WHERE owner=? AND practice_id=? AND ordinal=? AND status='running'",
                (
                    status_value,
                    time.time(),
                    payload,
                    None if payload is None else hashlib.sha256(payload.encode()).hexdigest(),
                    error or "",
                    payload,
                    owner,
                    identifier,
                    ordinal,
                ),
            )
            db.execute(
                "UPDATE dragon_reference_practice_intents SET status=?,worker_token='',lease_until=0 "
                "WHERE owner=? AND practice_id=? AND worker_token=?",
                (status_value, owner, identifier, token),
            )
        # Serialization and SQLite statement work are part of publication;
        # holding the write lock does not extend the issued execution lease.
        if intent["lease_until"] <= time.time():
            raise GameLearningError("practice_lease_lost", "Practice lease expired before publication.", 409)
        db.commit()
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def _execute(
    path,
    owner,
    pin,
    request,
    identifier,
    token,
    ordinal,
    runtime,
    cancelled,
    check_authority,
    deadline,
):
    from skeleton.jeeves.game_learning_runtime import create_game_environment

    started = time.time()
    trace = []
    environment = None

    def guard():
        if cancelled.is_set():
            raise GameLearningError("practice_cancelled", "Practice stopped before completion.", 409)
        if time.monotonic() >= deadline:
            raise GameLearningError(
                "practice_deadline", "Practice reached its ten-second execution limit.", 409
            )

    try:
        guard()
        check_authority()
        environment = create_game_environment(TARGET, max_steps=request["max_steps"])
        observation = environment.reset(request["seed"])
        totals = {key: 0.0 for key in environment.spec.reward_components}
        terminated = truncated = False
        for sequence in range(1, request["max_steps"] + 1):
            guard()
            if (sequence - 1) % 16 == 0:
                check_authority()
                guard()
            goal = observation.get("goal_dx", 0)
            action = "right" if goal > 0.03 else "left" if goal < -0.03 else "noop"
            if action not in environment.spec.actions:
                action = environment.spec.actions[0]
            outcome = environment.step(action)
            guard()
            observation = dict(outcome.observation)
            for key in totals:
                value = outcome.reward_components[key]
                if type(value) not in (float, int) or not math.isfinite(value):
                    raise GameLearningError(
                        "practice_runtime_evidence", "Runtime returned a nonfinite reward.", 503
                    )
                totals[key] += value
            terminated, truncated = outcome.terminated, outcome.truncated
            trace.append(
                {
                    "step": sequence,
                    "action": action,
                    "observation": observation,
                    "reward": outcome.reward,
                    "reward_components": dict(outcome.reward_components),
                    "transition_digest": outcome.transition_digest,
                    "terminated": terminated,
                    "truncated": truncated,
                }
            )
            if sequence % 16 == 0 or terminated or truncated:
                check_authority()
                guard()
                _save(path, owner, identifier, token, ordinal, trace=trace)
            if terminated or truncated:
                break
        guard()
        check_authority()
        if _runtime_digest() != runtime:
            raise GameLearningError(
                "practice_runtime_changed", "Practice implementation changed during execution.", 409
            )
        descriptor = environment.descriptor
        result = {
            "schema_version": "skeleton.dragon.reference_practice.v1",
            "practice_id": identifier,
            "status": "completed",
            "attempt": ordinal,
            "steps": len(trace),
            "return": math.fsum(item["reward"] for item in trace),
            "reward_components": totals,
            "trace": trace,
            "trace_digest": _digest(trace),
            "runtime_kind": descriptor["runtime_kind"],
            "target_id": TARGET,
            "environment_digest": environment.spec.environment_digest,
            "runtime_digest": runtime,
            "controller": "goal_dx_directional_reference_v1",
            "source_pin": pin,
            "terminated": terminated,
            "truncated": truncated,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "lesson": {
                "text": f"Observed {len(trace)} actual reference-engine steps for the reviewed {pin['mechanic']} exercise. "
                "The source annotation was not experimentally verified; inspect the recorded task rewards and transitions.",
                "evidence_digest": _digest(trace),
                "classification": "measured_reference_observation",
                "training_allowed": False,
            },
            "policy_trained": False,
            "xp_awarded": 0,
            "quality_improvement_verified": False,
        }
        preview = environment.preview()
        if preview is not None and len(_json(preview)) <= 160000:
            result["preview"] = preview
        _json(result)
        return result
    finally:
        if environment is not None:
            close = getattr(environment, "close", None)
            if callable(close):
                close()


async def run_reference_practice(
    *, path: Path, owner: str, candidate: dict, request: dict, authorize
) -> dict:
    if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
        raise GameLearningError("practice_owner", "An exact scoped practice owner is required.", 403)
    if (
        not isinstance(request, dict)
        or set(request) != {"expected_version", "seed", "max_steps", "idempotency_key", "practice_consent"}
        or request.get("practice_consent") is not True
        or type(request.get("seed")) is not int
        or not 0 <= request["seed"] <= 2**31 - 1
        or type(request.get("max_steps")) is not int
        or not 16 <= request["max_steps"] <= 512
        or not isinstance(request.get("idempotency_key"), str)
        or not 1 <= len(request["idempotency_key"]) <= 256
        or request["idempotency_key"] != request["idempotency_key"].strip()
    ):
        raise GameLearningError("practice_request", "A bounded explicit practice request is required.")
    pin = _source_pin(candidate)
    if type(request["expected_version"]) is not int or request["expected_version"] != pin["version"]:
        raise GameLearningError("practice_candidate_changed", "Reload the current reviewed reference.", 409)
    await authorize()
    runtime = _runtime_digest()
    deadline = time.monotonic() + MAX_SECONDS
    identifier, token, ordinal, prior = _claim(path, owner, pin, request, runtime)
    if prior is not None:
        await authorize()
        return {"practice": prior, "replayed": True}
    loop = asyncio.get_running_loop()
    cancelled = threading.Event()

    def check_authority():
        pending = asyncio.run_coroutine_threadsafe(authorize(), loop)
        try:
            pending.result(timeout=2)
        except BaseException:
            pending.cancel()
            raise

    start_gate = threading.Lock()
    started = threading.Event()

    def execute():
        # A queued wrapper can be cancelled without pretending an already
        # running thread exited. The lock makes the start/cancel choice exact.
        with start_gate:
            if cancelled.is_set():
                raise GameLearningError("practice_cancelled", "Practice stopped before dispatch.", 409)
            started.set()
        return _execute(
            path,
            owner,
            pin,
            request,
            identifier,
            token,
            ordinal,
            runtime,
            cancelled,
            check_authority,
            deadline,
        )

    try:
        worker = loop.run_in_executor(None, execute)
    except Exception as exc:
        _save(path, owner, identifier, token, ordinal, error="practice_dispatch_unavailable")
        raise GameLearningError(
            "practice_dispatch_unavailable", "The admitted practice worker could not be dispatched.", 503
        ) from exc
    key = (str(path), owner, identifier)
    _active[key] = worker
    try:
        complete, _ = await asyncio.wait({worker}, timeout=max(0.0, deadline - time.monotonic()))
        if not complete:
            raise GameLearningError(
                "practice_deadline", "Practice reached its ten-second execution limit.", 409
            )
        result = await asyncio.shield(worker)
        await authorize()
        if time.monotonic() >= deadline:
            raise GameLearningError(
                "practice_deadline", "Practice reached its ten-second execution limit.", 409
            )
        _save(path, owner, identifier, token, ordinal, result=result)
        return {"practice": result, "replayed": False}
    except BaseException as exc:
        with start_gate:
            cancelled.set()
            if not started.is_set():
                # The only callback that can enter _execute checks this same
                # gate/event first. No practice work can start after this point.
                worker.cancel()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled.set()
            except BaseException:
                break
        if not worker.cancelled():
            worker.exception()
        code = exc.code if isinstance(exc, GameLearningError) else "practice_interrupted"
        try:
            _save(path, owner, identifier, token, ordinal, error=code)
        except (GameLearningError, sqlite3.Error):
            # A lost/expired durable lease is already fenced. Keep its actual
            # partial checkpoint for explicit recovery after expiry.
            pass
        raise
    finally:
        if _active.get(key) is worker and worker.done():
            _active.pop(key, None)


def read_reference_practice(path, owner, candidate_id, practice_id) -> dict:
    """Read one exact committed receipt; caller supplies live source authority."""
    db = _connect(path)
    try:
        identity = (owner, candidate_id, practice_id)
        selected = (
            " FROM dragon_reference_practice_intents i "
            "JOIN dragon_reference_practice_attempts a ON a.owner=i.owner "
            "AND a.practice_id=i.practice_id AND a.ordinal=i.attempt "
            "WHERE i.owner=? AND i.candidate_id=? AND i.practice_id=? "
            "AND i.status='completed' AND a.status='completed'"
        )
        size = db.execute(
            "SELECT length(CAST(a.result_json AS BLOB)),length(CAST(i.source_pin_json AS BLOB))" + selected,
            identity,
        ).fetchone()
        if size is None:
            raise GameLearningError(
                "practice_receipt_not_found", "A completed practice receipt is required.", 404
            )
        if (
            type(size[0]) is not int
            or not 1 <= size[0] <= MAX_BYTES
            or type(size[1]) is not int
            or not 1 <= size[1] <= 16384
        ):
            raise GameLearningError(
                "practice_receipt_corrupt", "Stored practice evidence exceeds its bound.", 503
            )
        row = db.execute(
            "SELECT a.result_json,a.result_digest,i.runtime_digest,i.source_pin_json,i.attempt" + selected,
            identity,
        ).fetchone()
        if row is None or hashlib.sha256(row["result_json"].encode()).hexdigest() != row["result_digest"]:
            raise GameLearningError("practice_receipt_corrupt", "Stored practice evidence differs.", 503)
        try:
            value = json.loads(row["result_json"])
            source_pin = json.loads(row["source_pin_json"])
        except (ValueError, TypeError, RecursionError) as exc:
            raise GameLearningError(
                "practice_receipt_corrupt", "Stored practice JSON is invalid.", 503
            ) from exc
        if (
            not isinstance(value, dict)
            or not isinstance(source_pin, dict)
            or _json(value).decode() != row["result_json"]
            or value.get("schema_version") != "skeleton.dragon.reference_practice.v1"
            or value.get("practice_id") != practice_id
            or value.get("status") != "completed"
            or value.get("attempt") != row["attempt"]
            or value.get("source_pin") != source_pin
            or source_pin.get("candidate_id") != candidate_id
            or value.get("runtime_digest") != row["runtime_digest"]
            or not isinstance(value.get("trace"), list)
            or value.get("steps") != len(value["trace"])
            or value.get("trace_digest") != _digest(value["trace"])
        ):
            raise GameLearningError("practice_receipt_corrupt", "Stored practice identities differ.", 503)
        _source_pin({**source_pin, "state": "approved"})
        value.pop("trace")
        value.pop("preview", None)
        value["trace_retained"] = True
        return {"practice": value, "receipt_digest": row["result_digest"]}
    finally:
        db.close()


def list_reference_practice(path, owner, candidate_id, limit=20) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise GameLearningError("practice_page", "Practice history is bounded to twenty attempts.")
    db = _connect(path)
    try:
        _schema(db)
        db.execute("BEGIN")
        selection = (
            " FROM dragon_reference_practice_attempts a "
            "JOIN dragon_reference_practice_intents i ON i.owner=a.owner AND i.practice_id=a.practice_id "
            "WHERE a.owner=? AND i.candidate_id=? ORDER BY a.started_at DESC LIMIT ?"
        )
        parameters = (owner, candidate_id, limit)
        sizes = db.execute(
            "SELECT length(CAST(a.result_json AS BLOB)),length(CAST(a.checkpoint_json AS BLOB)),"
            "length(CAST(i.source_pin_json AS BLOB))" + selection,
            parameters,
        ).fetchall()
        for result_size, checkpoint_size, pin_size in sizes:
            if (
                (
                    result_size is not None
                    and (type(result_size) is not int or not 1 <= result_size <= MAX_BYTES)
                )
                or type(checkpoint_size) is not int
                or not 2 <= checkpoint_size <= MAX_BYTES
                or type(pin_size) is not int
                or not 1 <= pin_size <= 16384
            ):
                raise GameLearningError(
                    "practice_receipt_corrupt", "Stored practice history exceeds its bound.", 503
                )
        rows = db.execute(
            "SELECT a.*,i.source_pin_json,i.runtime_digest,i.lease_until" + selection,
            parameters,
        ).fetchall()
        output = []
        for row in rows:
            if row["result_json"]:
                value = read_reference_practice(path, owner, candidate_id, row["practice_id"])["practice"]
            else:
                trace = json.loads(row["checkpoint_json"])
                value = {
                    "practice_id": row["practice_id"],
                    "attempt": row["ordinal"],
                    "status": (
                        "interrupted"
                        if row["status"] == "running" and row["lease_until"] <= time.time()
                        else row["status"]
                    ),
                    "steps": len(trace),
                    "trace_digest": _digest(trace),
                    "source_pin": json.loads(row["source_pin_json"]),
                    "error_code": row["error_code"],
                    "runtime_digest": row["runtime_digest"],
                    "runtime_kind": "reference_game_simulation",
                    "lesson": None,
                    "policy_trained": False,
                    "xp_awarded": 0,
                }
            output.append(value)
        return output
    finally:
        db.close()
