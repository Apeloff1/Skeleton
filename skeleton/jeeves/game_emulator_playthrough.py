"""Checkpointed, uninterrupted native-core game study beyond 256/4096 steps.

This runner plays operator-supplied compressed input programs on one approved
libretro core. It cannot infer a win screen or invent a gameplay-solving agent.
A completion watch is an operator-declared exact observation, never proof of a
game's ending, legal rights, model learning, or hardware compatibility.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .game_emulator_host import (
    EmulatorEnvironment, EmulatorHostError, _ACTIONS, _KEY_ACTIONS, _controls, _digest,
)

PLAN_SCHEMA = "skeleton.game.native_playthrough_plan.v1"
CHECKPOINT_SCHEMA = "skeleton.game.native_playthrough_checkpoint.v1"
RECEIPT_SCHEMA = "skeleton.game.native_playthrough_receipt.v1"
MAX_TOTAL_STEPS = 100_000_000
MAX_INSTRUCTIONS = 4096
MAX_FILE_BYTES = 12 * 1024 * 1024


class PlaythroughError(ValueError):
    """Rejected playthrough inputs, checkpoints or execution boundaries."""


def _integer(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise PlaythroughError(f"{label} must be in [{low}, {high}]")
    return value


def _watch(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PlaythroughError("completion watch must be an object")
    kind = value.get("kind")
    if kind == "frame_sha256":
        if set(value) != {"kind", "sha256", "poll_every"}:
            raise PlaythroughError("frame completion watch fields differ")
        digest = value["sha256"]
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PlaythroughError("completion frame digest is invalid")
        _integer(value["poll_every"], 1, 4096, "completion poll interval")
    elif kind == "memory_equals":
        if set(value) != {"kind", "region", "offset", "expected_hex", "poll_every"}:
            raise PlaythroughError("memory completion watch fields differ")
        _integer(value["region"], 0, 3, "memory region")
        _integer(value["offset"], 0, 256 * 1024**2, "memory offset")
        data = value["expected_hex"]
        if type(data) is not str or not 2 <= len(data) <= 16 or len(data) % 2 or any(c not in "0123456789abcdef" for c in data):
            raise PlaythroughError("expected memory bytes must be 1–8 lowercase hex octets")
        _integer(value["poll_every"], 1, 4096, "completion poll interval")
    else:
        raise PlaythroughError("unknown game-specific completion watch")
    return dict(value)


def normalize_plan(raw: object) -> dict[str, object]:
    """Validate the entire compressed tape before any native execution."""
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "instructions", "max_total_steps", "completion", "seed"
    } or raw["schema_version"] != PLAN_SCHEMA:
        raise PlaythroughError("exact playthrough plan schema is required")
    limit = _integer(raw["max_total_steps"], 1, MAX_TOTAL_STEPS, "total gameplay step budget")
    seed = _integer(raw["seed"], 0, 2**63 - 1, "native reset seed label")
    instructions = raw["instructions"]
    if not isinstance(instructions, list) or not 1 <= len(instructions) <= MAX_INSTRUCTIONS:
        raise PlaythroughError("playthrough requires 1–4096 compressed instructions")
    actions = set(_ACTIONS) | set(_KEY_ACTIONS)
    canonical, total = [], 0
    for row in instructions:
        if not isinstance(row, dict) or set(row) not in (
            {"action", "repeat"}, {"controllers", "repeat"}
        ):
            raise PlaythroughError("each instruction declares exactly action or controllers and repeat")
        repeat = _integer(row["repeat"], 1, MAX_TOTAL_STEPS, "instruction repetition")
        total += repeat
        if total > limit:
            raise PlaythroughError("compressed program exceeds declared absolute step budget")
        if "action" in row:
            if type(row["action"]) is not str or row["action"] not in actions:
                raise PlaythroughError("undeclared native input action")
            canonical.append({"action": row["action"], "repeat": repeat})
        else:
            canonical.append({"controllers": _controls(row["controllers"]), "repeat": repeat})
    return {
        "schema_version": PLAN_SCHEMA, "instructions": canonical,
        "max_total_steps": limit, "completion": _watch(raw["completion"]),
        "seed": seed,
    }


def _private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise PlaythroughError("checkpoint directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = path.resolve(strict=True)
    mode = root.stat()
    if not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.geteuid() or mode.st_mode & 0o077:
        raise PlaythroughError("checkpoint directory must be private and owned by this user")
    return root


def _load(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise PlaythroughError("checkpoint or plan file may not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE_BYTES:
            raise PlaythroughError("input is not a bounded regular file")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise PlaythroughError("file changed during admission")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise PlaythroughError("JSON input must be an object")
        return value
    finally:
        os.close(descriptor)


def load_playthrough_plan(path: Path) -> dict[str, object]:
    return normalize_plan(_load(path))


def _save(path: Path, value: Mapping[str, object], *, replace: bool) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(data) > MAX_FILE_BYTES:
        raise PlaythroughError("durable playthrough evidence exceeds file budget")
    if path.is_symlink() or path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise PlaythroughError("refusing nonregular or symlink evidence destination")
    fd, tmp = tempfile.mkstemp(prefix=".playthrough-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
        folder = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _completion_matches(environment: EmulatorEnvironment, watch: dict[str, object], index: int) -> bool:
    if index % watch["poll_every"]:
        return False
    if watch["kind"] == "frame_sha256":
        return environment._frame["pixel_sha256"] == watch["sha256"]
    expected = bytes.fromhex(watch["expected_hex"])
    observed = environment.read_memory(watch["region"], watch["offset"], len(expected))
    return observed == expected


def _instruction_cursor(plan: dict[str, object], absolute: int) -> tuple[int, int]:
    if not 0 <= absolute <= sum(row["repeat"] for row in plan["instructions"]):
        raise PlaythroughError("checkpoint cursor exceeds the exact input program")
    index, remainder = 0, absolute
    for row in plan["instructions"]:
        if remainder < row["repeat"]:
            return index, remainder
        remainder -= row["repeat"]
        index += 1
    return index, 0


def run_native_full_playthrough(
    environment: EmulatorEnvironment,
    plan: Mapping[str, object],
    *,
    checkpoint_directory: Path,
    resume: bool = False,
    checkpoint_every: int = 4096,
    evidence_every: int = 64,
    max_run_seconds: float = 3600,
    cancelled: Callable[[], bool] | None = None,
    rights_evidence_digest: str | None = None,
) -> dict[str, object]:
    """Execute compressed real controls, checkpointing opaque native state.

    A clock deadline or input exhaustion stops cleanly with a resumable
    checkpoint; neither implies game completion. Full traversal of a game's
    branches requires additional separately supplied plans and terminal rules.
    """
    if not isinstance(environment, EmulatorEnvironment):
        raise PlaythroughError("actual native emulator environment is required")
    canonical = normalize_plan(dict(plan))
    if type(resume) is not bool:
        raise PlaythroughError("resume must be explicit boolean")
    _integer(checkpoint_every, 1, 4096, "checkpoint interval")
    _integer(evidence_every, 1, 4096, "evidence sampling interval")
    if type(max_run_seconds) not in (int, float) or not math.isfinite(max_run_seconds) or not 1 <= max_run_seconds <= 7200:
        raise PlaythroughError("operator run time budget must be 1–7200 seconds")
    if cancelled is not None and not callable(cancelled):
        raise PlaythroughError("cancellation probe is not callable")
    if rights_evidence_digest is not None and (
        type(rights_evidence_digest) is not str or len(rights_evidence_digest) != 64
        or any(c not in "0123456789abcdef" for c in rights_evidence_digest)
    ):
        raise PlaythroughError("rights source receipt must be exact lowercase SHA256")
    directory = _private_dir(Path(checkpoint_directory))
    lock = directory / ".playthrough.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError as exc:
        raise PlaythroughError("checkpoint destination has an active or stale operator lock") from exc

    try:
        environment._authority()
        plan_digest = _digest(canonical)
        environment_digest = environment.spec.environment_digest
        total = sum(row["repeat"] for row in canonical["instructions"])
        if (total + checkpoint_every - 1) // checkpoint_every > 250000:
            raise PlaythroughError("checkpoint schedule exceeds 250,000 durable evidence files")
        checkpoint_path = directory / "checkpoint.json"
        receipt_chain = _digest({
            "plan_digest": plan_digest, "environment_digest": environment_digest,
            "seed": canonical["seed"], "rights_evidence_digest": rights_evidence_digest,
        })
        absolute, last_checkpoint, previous_receipt, windows = 0, 0, None, 0
        if resume:
            state = _load(checkpoint_path)
            if (set(state) != {
                "schema_version", "plan_digest", "environment_digest",
                "rights_evidence_digest", "absolute_step", "windows",
                "previous_receipt_digest", "receipt_chain", "native_snapshot",
                "status", "checkpoint_digest"
            } or state["schema_version"] != CHECKPOINT_SCHEMA):
                raise PlaythroughError("playthrough checkpoint schema differs")
            signed = dict(state)
            digest = signed.pop("checkpoint_digest")
            if _digest(signed) != digest or state["plan_digest"] != plan_digest or state["environment_digest"] != environment_digest or state["rights_evidence_digest"] != rights_evidence_digest:
                raise PlaythroughError("checkpoint integrity or source identity differs")
            absolute = _integer(state["absolute_step"], 0, total, "restored input cursor")
            windows = _integer(state["windows"], 0, MAX_TOTAL_STEPS, "native continuation count")
            previous_receipt = state["previous_receipt_digest"]
            if previous_receipt is not None and (type(previous_receipt) is not str or len(previous_receipt) != 64):
                raise PlaythroughError("restored receipt chain identity differs")
            receipt_chain = state["receipt_chain"]
            if type(receipt_chain) is not str or len(receipt_chain) != 64:
                raise PlaythroughError("restored transition chain is invalid")
            if state["status"] not in ("time_budget_exhausted", "cancelled", "running"):
                raise PlaythroughError("terminal checkpoint is not eligible for resume")
            environment.restore(state["native_snapshot"])
            last_checkpoint = absolute
        else:
            if checkpoint_path.exists():
                raise PlaythroughError("checkpoint already exists; resume explicitly or use a new directory")
            environment.reset(canonical["seed"])

        started = time.monotonic()
        deadline = started + max_run_seconds
        samples: list[dict[str, object]] = []
        index, offset = _instruction_cursor(canonical, absolute)
        status = "running"
        completion_watch = canonical["completion"]

        def persist(current_status: str) -> None:
            nonlocal last_checkpoint, previous_receipt, samples
            if absolute == last_checkpoint and current_status == "running":
                return
            frame = environment._frame or {}
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "plan_digest": plan_digest, "environment_digest": environment_digest,
                "from_step": last_checkpoint, "to_step": absolute,
                "continuation_windows": windows,
                "transition_chain": receipt_chain,
                "native_frame_digest": frame.get("pixel_sha256"),
                "native_audio_digest": frame.get("audio_sha256"),
                "native_runs": frame.get("runs"),
                "previous_receipt_digest": previous_receipt,
                "samples": samples, "stop_reason": current_status,
                "completion_watch_observed": current_status == "completion_rule_matched",
                "certified_game_completion": False,
                "model_weights_promoted": False,
                "rights_verified": False,
            }
            receipt_digest = _digest(receipt)
            receipt["receipt_digest"] = receipt_digest
            snapshot = environment.snapshot()
            state = {
                "schema_version": CHECKPOINT_SCHEMA,
                "plan_digest": plan_digest, "environment_digest": environment_digest,
                "rights_evidence_digest": rights_evidence_digest,
                "absolute_step": absolute, "windows": windows,
                "previous_receipt_digest": receipt_digest,
                "receipt_chain": receipt_chain,
                "native_snapshot": snapshot,
                "status": current_status,
            }
            state["checkpoint_digest"] = _digest(state)
            _save(directory / f"receipt-{absolute:012d}.json", receipt, replace=False)
            _save(checkpoint_path, state, replace=True)
            previous_receipt, last_checkpoint, samples = receipt_digest, absolute, []

        while index < len(canonical["instructions"]):
            if cancelled is not None and cancelled():
                status = "cancelled"
                break
            if time.monotonic() >= deadline:
                status = "time_budget_exhausted"
                break
            if environment.done:
                continuation = environment.continue_playthrough()
                if continuation["native_core_reset"] is not False:
                    raise PlaythroughError("native continuation unexpectedly reset the core")
                windows += 1
                receipt_chain = _digest({
                    "prior": receipt_chain, "window": windows,
                    "continuation_digest": continuation["continuation_digest"]
                })
            instruction = canonical["instructions"][index]
            if "action" in instruction:
                step = environment.step(instruction["action"])
            else:
                step = environment.input_step(instruction["controllers"])
            absolute += 1
            offset += 1
            evidence = step.info.get("evidence", {})
            if (evidence.get("environment_digest") != environment_digest
                or evidence.get("frame_digest") != environment._frame["pixel_sha256"]
                or evidence.get("native_runs") != environment._frame["runs"]
                or step.transition_digest != environment._chain):
                raise PlaythroughError("native transition evidence differs")
            receipt_chain = _digest({
                "prior": receipt_chain, "absolute_step": absolute,
                "native_transition": step.transition_digest,
                "action_digest": evidence["controller_digest"],
            })
            if absolute % evidence_every == 0:
                samples.append({
                    "step": absolute, "frame_sha256": evidence["frame_digest"],
                    "audio_sha256": evidence.get("audio_sha256"),
                    "controller_sha256": evidence["controller_digest"],
                    "native_runs": evidence["native_runs"],
                    "transition_digest": step.transition_digest,
                })
            if completion_watch is not None and _completion_matches(environment, completion_watch, absolute):
                status = "completion_rule_matched"
                break
            if offset == instruction["repeat"]:
                index, offset = index + 1, 0
            if absolute - last_checkpoint >= checkpoint_every:
                persist("running")
        else:
            status = "input_exhausted"
        persist(status)
        return {
            "schema_version": "skeleton.game.native_full_playthrough_result.v1",
            "status": status, "absolute_steps": absolute,
            "planned_steps": total, "continuation_windows": windows,
            "native_frames_per_step": environment.frames_per_step,
            "native_core_reset_at_continuation": False,
            "plan_digest": plan_digest, "environment_digest": environment_digest,
            "last_receipt_digest": previous_receipt, "transition_chain": receipt_chain,
            "checkpoint_directory": str(directory),
            "game_success_verified": False,
            "completion_watch_matched": status == "completion_rule_matched",
            "game_completion_scope": "operator_declared_observation_only",
            "production_model_training_performed": False,
        }
    finally:
        lock.unlink(missing_ok=True)


def audit_native_playthrough_directory(directory: Path) -> dict[str, object]:
    """Verify durable ledger continuity; do not infer a game's real ending."""
    root = _private_dir(Path(directory))
    checkpoint = _load(root / "checkpoint.json")
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA:
        raise PlaythroughError("playthrough checkpoint schema differs")
    encoded = dict(checkpoint)
    digest = encoded.pop("checkpoint_digest", None)
    if digest != _digest(encoded):
        raise PlaythroughError("checkpoint integrity differs")
    filenames = sorted(root.glob("receipt-*.json"))
    if not 1 <= len(filenames) <= 250000:
        raise PlaythroughError("playthrough receipt count outside audited bounds")
    previous = None
    cursor = 0
    windows = 0
    status = "running"
    for filename in filenames:
        if filename.is_symlink():
            raise PlaythroughError("playthrough receipt cannot be a symlink")
        value = _load(filename)
        if value.get("schema_version") != RECEIPT_SCHEMA:
            raise PlaythroughError("playthrough receipt schema differs")
        payload = dict(value)
        signature = payload.pop("receipt_digest", None)
        if signature != _digest(payload):
            raise PlaythroughError("playthrough receipt digest differs")
        start = _integer(value.get("from_step"), 0, MAX_TOTAL_STEPS, "receipt start")
        finish = _integer(value.get("to_step"), start, MAX_TOTAL_STEPS, "receipt finish")
        count = _integer(value.get("continuation_windows"), 0, MAX_TOTAL_STEPS, "receipt windows")
        if (filename.name != f"receipt-{finish:012d}.json"
            or start != cursor or count < windows
            or value.get("previous_receipt_digest") != previous
            or value.get("plan_digest") != checkpoint["plan_digest"]
            or value.get("environment_digest") != checkpoint["environment_digest"]
            or value.get("certified_game_completion") is not False
            or value.get("model_weights_promoted") is not False):
            raise PlaythroughError("playthrough receipt identity, order, or unverified claims differ")
        samples = value.get("samples")
        if not isinstance(samples, list) or len(samples) > 4096:
            raise PlaythroughError("evidence sample sequence exceeds bounded audit")
        last = start
        for sample in samples:
            if not isinstance(sample, dict):
                raise PlaythroughError("evidence sample row is not an object")
            sampled_step = _integer(sample.get("step"), start + 1, finish, "sample cursor")
            if sampled_step <= last:
                raise PlaythroughError("evidence samples are not strictly ordered")
            for field in ("frame_sha256", "controller_sha256", "transition_digest"):
                item = sample.get(field)
                if type(item) is not str or len(item) != 64 or any(c not in "0123456789abcdef" for c in item):
                    raise PlaythroughError("evidence sample is missing a native SHA256")
            last = sampled_step
        previous, cursor, windows = signature, finish, count
        status = value["stop_reason"]
        if status not in ("running", "input_exhausted", "completion_rule_matched", "cancelled", "time_budget_exhausted"):
            raise PlaythroughError("unknown native playthrough stop reason")
        if status in ("input_exhausted", "completion_rule_matched") and filename != filenames[-1]:
            raise PlaythroughError("a terminal playthrough receipt has unexpected successors")
    if (checkpoint["absolute_step"] != cursor
        or checkpoint["windows"] != windows
        or checkpoint["previous_receipt_digest"] != previous
        or checkpoint["status"] != status):
        raise PlaythroughError("latest durable checkpoint and receipt ledger disagree")
    return {
        "schema_version": "skeleton.game.native_playthrough_audit.v1",
        "status": status,
        "audited_receipts": len(filenames),
        "audited_steps": cursor,
        "continued_windows": windows,
        "last_receipt_digest": previous,
        "checkpoint_digest": digest,
        "receipt_integrity_verified": True,
        "game_completion_verified": False,
        "external_execution_attestation": False,
    }
