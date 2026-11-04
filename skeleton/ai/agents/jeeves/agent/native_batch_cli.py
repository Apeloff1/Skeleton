"""Operator CLI for deterministic native batch jobs and SQLite cold replay.

Casebook is bounded stdin JSON; no model activation without --approve-native
and a source-verified installed GGUF. A no-model preview intentionally
requires an explicit model identity record from a prior approved source and
makes no device claim. Unknown effects always remain held, never auto-retried.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.jeeves.native_fabric.contracts import parse_json
from .native_batch_runtime import (
    NativeBatchHold, NativeBatchTask, NativeBatchPolicy, NativeBatchConveyor,
    preflight_batch_tasks,
)
from .native_readiness import inspect_native_jeeves


def parse_casebook(raw: bytes) -> tuple[str, tuple[NativeBatchTask, ...]]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 1048576:
        raise NativeBatchHold("bounded operator-native batch stdin required")
    content = parse_json(raw, max_bytes=1048576)
    if type(content) is not dict or set(content) != {"schema", "batch_id", "tasks"}:
        raise NativeBatchHold("operator batch has unexpected fields")
    if content["schema"] != "jeeves.native_batch_casebook.v1":
        raise NativeBatchHold("unsupported operator batch schema")
    batch_id = content["batch_id"]
    rows = content["tasks"]
    if type(rows) is not list or not 1 <= len(rows) <= 1000:
        raise NativeBatchHold("bounded native batch task list required")
    tasks = []
    for row in rows:
        if (type(row) is not dict or not {"task_id", "prompt"} <= set(row)
            or not set(row) <= {
                "task_id", "prompt", "exact_output_sha256",
            }):
            raise NativeBatchHold("invalid typed batch task contract")
        tasks.append(NativeBatchTask(**row))
    if len({item.task_id for item in tasks}) != len(tasks):
        raise NativeBatchHold("batch task identity duplicated")
    return batch_id, tuple(tasks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One source-bound native worker executing a bounded idempotent batch"
    )
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--batch-stdin", action="store_true")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--maximum-jobs", type=int, default=64)
    parser.add_argument("--maximum-prompt-bytes", type=int, default=262144)
    parser.add_argument("--maximum-reserved-output-tokens", type=int, default=65536)
    parser.add_argument("--maximum-wall-seconds", type=float, default=1800)
    parser.add_argument("--maximum-single-job-ms", type=int, default=300000)
    args = parser.parse_args(argv)
    try:
        if not args.batch_stdin or not args.approve_native:
            raise NativeBatchHold("explicit approved native batch and stdin required")
        raw = sys.stdin.buffer.read(1048577)
        batch_id, tasks = parse_casebook(raw)
        policy = NativeBatchPolicy(
            maximum_jobs=args.maximum_jobs,
            maximum_prompt_bytes=args.maximum_prompt_bytes,
            maximum_reserved_output_tokens=args.maximum_reserved_output_tokens,
            maximum_wall_seconds=args.maximum_wall_seconds,
            maximum_single_job_ms=args.maximum_single_job_ms,
        )
        preflight_batch_tasks(
            batch_id, tasks, policy,
            configured_output_tokens=args.max_new_tokens,
        )
        stack, worker, installed = activate_checked(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject,
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            isolated=True,
        )
        with stack:
            readiness = inspect_native_jeeves(worker, installed)
            if not readiness.source_bridge_ready:
                raise NativeBatchHold("source-installed native model identity is unqualified")
            conveyor = NativeBatchConveyor(worker, approved=True, policy=policy)
            result = conveyor.run(batch_id, tasks)
        sys.stdout.write(json.dumps(
            result.to_public_record(), sort_keys=True, ensure_ascii=False,
        ) + "\n")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema": "jeeves.native_batch_result.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "native_device_qualified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["parse_casebook", "main"]
