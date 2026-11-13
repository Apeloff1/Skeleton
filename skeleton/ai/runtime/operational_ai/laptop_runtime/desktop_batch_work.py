"""One-owner serial work-batch executor for the actual offline Jeeves model.

The operator reviews a finite set of ORIGINAL tasks before execution, approves
one aggregate manifest SHA-256 and starts a foreground-owned worker-thread
queue. Every task is a separate canonical SQLite NativeDurableJeevesAgent
start with its own previously visible immutable run ID. The native child,
source fence, rights, pressure guard and SQLite ledger are NOT reimplemented.

No autonomous scheduling, background daemon, model-selected jobs, simultaneous
GGUF callers, external tools, hidden provider, task reissue, source write or
automatic pending/failed checkpoint resume can occur through this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import secrets
import threading
from typing import Any, Callable, Protocol

from .desktop_protocol import MAX_PROMPT
from .contracts import identifier

SCHEMA = "jeeves.desktop.durable-work-batch.v1"
MAX_BATCH_ITEMS = 32
MAX_BATCH_INPUT = 262144
MAX_AGGREGATE_PROMPTS = 131072
MAX_BATCH_MODEL_CALLS = 512
MAX_BATCH_WALL_SECONDS = 7200


class BatchHold(ValueError):
    """A finite approved serial native work order is not safely executable."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BatchHold("ambiguous duplicate batch key")
        result[key] = value
    return result


def _bad_constant(_):
    raise BatchHold("nonfinite batch JSON denied")


def _utf8(value: object, *, maximum: int, label: str) -> bytes:
    if type(value) is not str or not value.strip() or chr(0) in value:
        raise BatchHold("nonempty exact " + label + " required")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise BatchHold("invalid Unicode in " + label) from exc
    if not 1 <= len(raw) <= maximum:
        raise BatchHold("finite UTF-8 byte limit for " + label + " exceeded")
    return raw


def _number(value: object, label: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise BatchHold("finite " + label + " outside native budget")
    return value


@dataclass(frozen=True, slots=True)
class DurableBatchItem:
    title: str
    task: str
    run_id: str
    maximum_steps: int
    maximum_model_calls: int
    maximum_wall_seconds: int

    def __post_init__(self):
        _utf8(self.title, maximum=128, label="task title")
        _utf8(self.task, maximum=MAX_PROMPT, label="original operator task")
        identifier(self.run_id, "durable run ID")
        if not self.run_id.startswith("wrun_") or len(self.run_id) != 37:
            raise BatchHold("unique native durable work ID required")
        _number(self.maximum_steps, "step budget", 64)
        _number(self.maximum_model_calls, "model-call budget", 64)
        _number(self.maximum_wall_seconds, "wall clock budget", 600)


@dataclass(frozen=True, slots=True)
class DurableBatchPlan:
    manifest_sha256: str
    items: tuple[DurableBatchItem, ...]
    aggregate_prompt_bytes: int
    aggregate_model_calls: int
    aggregate_wall_seconds: int

    def __post_init__(self):
        if (
            type(self.items) is not tuple
            or not 1 <= len(self.items) <= MAX_BATCH_ITEMS
            or any(type(item) is not DurableBatchItem for item in self.items)
            or len({x.run_id for x in self.items}) != len(self.items)
        ):
            raise BatchHold("invalid unique finite source-bound work plan")
        total = sum(len(x.task.encode("utf-8", "strict")) for x in self.items)
        calls = sum(x.maximum_model_calls for x in self.items)
        wall = sum(x.maximum_wall_seconds for x in self.items)
        if (
            type(self.aggregate_prompt_bytes) is not int
            or self.aggregate_prompt_bytes != total
            or type(self.aggregate_model_calls) is not int
            or self.aggregate_model_calls != calls
            or type(self.aggregate_wall_seconds) is not int
            or self.aggregate_wall_seconds != wall
            or total > MAX_AGGREGATE_PROMPTS
            or calls > MAX_BATCH_MODEL_CALLS
            or wall > MAX_BATCH_WALL_SECONDS
            or not (1 <= total and 1 <= calls and 1 <= wall)
        ):
            raise BatchHold("aggregate work exceeds native resource custody")
        if (
            type(self.manifest_sha256) is not str
            or len(self.manifest_sha256) != 64
            or self.manifest_sha256 != _digest(self.items)
        ):
            raise BatchHold("reviewed task/budget/run manifest identity changed")

    def to_public(self) -> dict[str, object]:
        """Deliberately exclude all private tasks from receipts and logs."""
        return {
            "schema": "jeeves.desktop.batch-review.v1",
            "manifest_sha256": self.manifest_sha256,
            "task_count": len(self.items),
            "run_ids": [item.run_id for item in self.items],
            "titles": [item.title for item in self.items],
            "aggregate_prompt_bytes": self.aggregate_prompt_bytes,
            "maximum_model_calls": self.aggregate_model_calls,
            "maximum_wall_seconds": self.aggregate_wall_seconds,
            "worker_count": 1,
            "provider_count": 1,
            "uses_canonical_durable_sqlite": True,
            "automatic_retries": False,
            "automatic_resume": False,
            "release_certified": False,
        }


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (UnicodeError, TypeError, ValueError) as exc:
        raise BatchHold("invalid canonical UTF-8 work manifest") from exc


def _digest(items: tuple[DurableBatchItem, ...]) -> str:
    return sha256(_canonical({
        "schema": SCHEMA,
        "items": [{
            "title": x.title,
            "task": x.task,
            "run_id": x.run_id,
            "maximum_steps": x.maximum_steps,
            "maximum_model_calls": x.maximum_model_calls,
            "maximum_wall_seconds": x.maximum_wall_seconds,
        } for x in items],
    })).hexdigest()


def parse_durable_batch(raw: str | bytes) -> DurableBatchPlan:
    """Preflight the entire batch without starting GGUF or creating SQLite."""
    if type(raw) is str:
        try:
            data = raw.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise BatchHold("invalid batch Unicode") from exc
    elif type(raw) is bytes:
        data = raw
    else:
        raise BatchHold("strict human-provided JSON batch required")
    if not 2 <= len(data) <= MAX_BATCH_INPUT:
        raise BatchHold("finite work-batch manifest input exceeded")
    try:
        parsed = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_unique, parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise BatchHold("untrusted work-batch JSON structure") from exc
    if type(parsed) is not dict or set(parsed) != {"schema", "items"}:
        raise BatchHold("unknown or unapproved batch manifest")
    if parsed["schema"] != SCHEMA:
        raise BatchHold("unknown batch source schema")
    rows = parsed["items"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_BATCH_ITEMS:
        raise BatchHold("too few or too many operator work tasks")
    items = []
    for row in rows:
        if type(row) is not dict or set(row) != {
            "title", "task", "maximum_steps",
            "maximum_model_calls", "maximum_wall_seconds",
        }:
            raise BatchHold("unknown per-task durable work authority")
        item = DurableBatchItem(
            title=row["title"],
            task=row["task"],
            run_id="wrun_" + secrets.token_hex(16),
            maximum_steps=row["maximum_steps"],
            maximum_model_calls=row["maximum_model_calls"],
            maximum_wall_seconds=row["maximum_wall_seconds"],
        )
        items.append(item)
    fixed = tuple(items)
    total = sum(len(x.task.encode("utf-8", "strict")) for x in fixed)
    plan = DurableBatchPlan(
        manifest_sha256=_digest(fixed),
        items=fixed,
        aggregate_prompt_bytes=total,
        aggregate_model_calls=sum(x.maximum_model_calls for x in fixed),
        aggregate_wall_seconds=sum(x.maximum_wall_seconds for x in fixed),
    )
    return plan


@dataclass(frozen=True, slots=True)
class BatchItemReceipt:
    sequence: int
    title: str
    run_id: str
    status: str
    model_sha256: str | None
    output_sha256: str | None

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 1:
            raise BatchHold("nonpositive work sequence")
        _utf8(self.title, maximum=128, label="receipt title")
        identifier(self.run_id, "run ID")
        if self.status not in ("durable-work-committed", "held"):
            raise BatchHold("unsupported terminal per-task status")
        for name in ("model_sha256", "output_sha256"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not str
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise BatchHold("untrusted native source receipt hash")

    def to_public(self):
        return {
            "sequence": self.sequence,
            "title": self.title,
            "run_id": self.run_id,
            "status": self.status,
            "model_sha256": self.model_sha256,
            "answer_sha256": self.output_sha256,
            "automatic_retry": False,
        }


@dataclass(frozen=True, slots=True)
class BatchRunReceipt:
    manifest_sha256: str
    status: str
    items_started: int
    items_committed: int
    stopped_at_sequence: int | None
    completed: tuple[BatchItemReceipt, ...]

    def __post_init__(self):
        if (
            self.status not in ("completed", "held", "operator-stopped")
            or type(self.items_started) is not int or self.items_started < 0
            or type(self.items_committed) is not int or self.items_committed < 0
            or self.items_committed > self.items_started
            or type(self.completed) is not tuple
            or len(self.completed) != self.items_started
        ):
            raise BatchHold("invalid bounded sequence of native work receipts")
        if self.stopped_at_sequence is not None and (
            type(self.stopped_at_sequence) is not int
            or self.stopped_at_sequence < 1
        ):
            raise BatchHold("invalid uncertain batch stop sequence")
        if len(self.manifest_sha256) != 64:
            raise BatchHold("batch digest missing")

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "jeeves.desktop.batch-run.v1",
            "manifest_sha256": self.manifest_sha256,
            "status": self.status,
            "items_started": self.items_started,
            "items_committed": self.items_committed,
            "stopped_at_sequence": self.stopped_at_sequence,
            "results": [x.to_public() for x in self.completed],
            "source_of_truth": "canonical-principal-bound-SQLite-work-orders",
            "automatic_resume": False,
            "automatic_retry": False,
            "release_certified": False,
        }


class BoundNativeWorker(Protocol):
    @property
    def connected(self) -> bool: ...
    def request(self, op: str, **fields: object) -> dict[str, Any]: ...
    def exclusive_batch(self, manifest_sha256: str): ...


class SerialDurableBatchRunner:
    """Owned one-process serial executor. Call .execute from a UI worker thread."""

    def __init__(
        self, worker: BoundNativeWorker, plan: DurableBatchPlan,
        *, expected_manifest_sha256: str,
        approved: bool,
        progress: Callable[[BatchItemReceipt], None] | None = None,
    ):
        if type(plan) is not DurableBatchPlan:
            raise BatchHold("previously reviewed typed work plan required")
        plan.__post_init__()
        if (
            approved is not True
            or type(expected_manifest_sha256) is not str
            or expected_manifest_sha256 != plan.manifest_sha256
        ):
            raise BatchHold("full exact operator-approved task manifest digest required")
        if (
            not hasattr(worker, "connected")
            or not callable(getattr(worker, "request", None))
            or not callable(getattr(worker, "exclusive_batch", None))
        ):
            raise BatchHold("one exclusively leased source-fenced native worker required")
        if progress is not None and not callable(progress):
            raise BatchHold("bounded progress publication callback required")
        self.worker = worker
        self.plan = plan
        self.progress = progress
        self._mutex = threading.RLock()
        self._stop_requested = False
        self._started = False

    def stop_after_current(self) -> None:
        """Cooperative stop ONLY between native tasks; no hidden cancellation."""
        with self._mutex:
            self._stop_requested = True

    def execute(self) -> BatchRunReceipt:
        with self._mutex:
            if self._started:
                raise BatchHold("batch runner cannot execute same native jobs twice")
            self._started = True
        # This lock is held across the complete approved work manifest.
        # Without it another UI request could interleave at task boundaries.
        # The bridge's RLock permits only this executing thread to submit
        # individual durable requests during the lease.
        with self.worker.exclusive_batch(self.plan.manifest_sha256):
            return self._execute_owned()

    def _execute_owned(self) -> BatchRunReceipt:
        records: list[BatchItemReceipt] = []
        committed = 0
        outcome = "completed"
        stopped = None

        for sequence, item in enumerate(self.plan.items, start=1):
            with self._mutex:
                halted = self._stop_requested
            if halted:
                outcome = "operator-stopped"
                stopped = sequence
                break
            if self.worker.connected is not True:
                outcome = "held"
                stopped = sequence
                break
            # Every task is its own original run ID + exact prompt/budget.
            # No automatic resume/retry of a pending or failed model effect.
            try:
                record = self.worker.request(
                    "durable", action="start",
                    run_id=item.run_id,
                    prompt=item.task,
                    maximum_steps=item.maximum_steps,
                    maximum_model_calls=item.maximum_model_calls,
                    maximum_wall_seconds=item.maximum_wall_seconds,
                )
                if (
                    type(record) is not dict
                    or record.get("status") != "durable-work-committed"
                    or record.get("run_id") != item.run_id
                    or type(record.get("durable")) is not dict
                    or record["durable"].get("status") != "terminal-committed"
                    or record["durable"].get("success") is not True
                    or record["durable"].get("run_id") != item.run_id
                    or record["durable"].get("automatic_resume") is not False
                    or record["durable"].get("native_generation_executed") is not True
                    or record["durable"].get("release_certified") is not False
                    or record["durable"].get("usage", {}).get("tool_calls") != 0
                ):
                    raise BatchHold("durable worker returned uncertified SQLite commit")
                model_sha = record["durable"].get("model_sha256")
                answer_sha = record["durable"].get("output_sha256")
                result = BatchItemReceipt(
                    sequence, item.title, item.run_id,
                    "durable-work-committed", model_sha, answer_sha,
                )
                committed += 1
            except BaseException:
                # Original SQLite work may have committed, failed or be pending.
                # Preserve the run ID; never requeue or invent a second effect.
                result = BatchItemReceipt(
                    sequence, item.title, item.run_id,
                    "held", None, None,
                )
                records.append(result)
                if self.progress is not None:
                    self.progress(result)
                outcome = "held"
                stopped = sequence
                break

            records.append(result)
            if self.progress is not None:
                self.progress(result)

        return BatchRunReceipt(
            self.plan.manifest_sha256, outcome, len(records),
            committed, stopped, tuple(records),
        )


__all__ = [
    "SCHEMA", "BatchHold", "DurableBatchItem", "DurableBatchPlan",
    "BatchItemReceipt", "BatchRunReceipt",
    "parse_durable_batch", "SerialDurableBatchRunner",
]
