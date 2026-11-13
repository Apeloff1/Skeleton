#!/usr/bin/env python3
"""Operator-only, resumable public game-building diagnostics on one pinned GGUF.

Uses the existing local deployment loader/inference plane. No model acquisition,
hosted provider, generated-code execution, training, promotion, or publication.
Reports are private local artifacts with complete synthetic response text.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.eval.game_builder_quality import (
    GameQualityError, INSTRUCTIONS, REPORT_SCHEMA, SCORER_ID, TASKSET_ID,
    canonical_bytes, digest, score_response, select_tasks,
    summarize, taskset_digest, taskset_manifest,
)

SOURCE_FILES = (
    "skeleton/eval/game_builder_quality.py",
    "scripts/evaluate_jeeves_game_builder_quality.py",
    "tests/test_game_builder_quality.py",
    "skeleton/app/local_ai.py",
    "skeleton/app/jeeves_local_lease.py",
    "skeleton/ai/runtime/inference/local.py",
    "skeleton/ai/runtime/inference/llama_cpp.py",
    "skeleton/ai/runtime/inference/deployment.py",
)
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


def _git(arguments: list[str]) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *arguments],
                            check=True, capture_output=True, text=True, timeout=10)
    return result.stdout.strip()


def source_identity() -> dict[str, object]:
    return {"git_head": _git(["rev-parse", "HEAD"]),
            "files_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in SOURCE_FILES}}


def snapshot_source(directory: Path, source: dict[str, Any], *, resume: bool) -> None:
    """Retain actual measured source bytes, not just unresolvable dirty hashes."""
    for name, expected in source["files_sha256"].items():
        payload = (ROOT / name).read_bytes()
        if sha256(payload).hexdigest() != expected:
            raise GameQualityError("source changed while snapshotting")
        target = directory / "source-snapshot" / name
        if resume:
            if (target.is_symlink() or not target.is_file()
                    or sha256(target.read_bytes()).hexdigest() != expected):
                raise GameQualityError("retained source snapshot changed")
        else:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(target, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())


def output_schema(task) -> dict[str, object]:
    """Types only: no expected values, enums, aliases, or answer hints."""
    properties: dict[str, object] = {}
    for name, kind in task.fields:
        if kind == "string_list":
            properties[name] = {"type": "array", "items": {"type": "string", "minLength": 1}}
        elif kind in {"string", "integer", "boolean"}:
            properties[name] = {"type": kind} | ({"minLength": 1} if kind == "string" else {})
        else:
            raise GameQualityError("task has an unsupported output field type")
    return {"type": "object", "additionalProperties": False,
            "required": [name for name, _ in task.fields], "properties": properties}


def response_text(result, *, structured: bool) -> tuple[str, str]:
    """Use the native contract; never extract a JSON substring from prose."""
    if structured:
        if not isinstance(result.structured_output, dict) or result.text is not None:
            raise GameQualityError("runtime did not return its validated structured object")
        return canonical_bytes(result.structured_output).decode("utf-8"), "canonical-json-of-runtime-validated-structured-output"
    if result.structured_output is not None or not isinstance(result.text, str):
        raise GameQualityError("plain execution did not return model text")
    return result.text, "native-text"


def create_json(path: Path, value: dict[str, object]) -> None:
    """Never overwrite an existing result or follow a substituted leaf link."""
    payload = canonical_bytes(value) + b"\n"
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise GameQualityError("evaluation artifact exceeds its byte bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= MAX_ARTIFACT_BYTES:
        raise GameQualityError("evaluation artifact is not a bounded regular file")
    raw = path.read_bytes()
    # The scorer's 32 KiB cap is for individual model responses, not reports.
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise GameQualityError("evaluation artifact exceeds its byte bound")
    from skeleton.eval.game_builder_quality import _constant, _strict_object
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object,
                            parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise GameQualityError("evaluation artifact contains invalid JSON") from None
    if not isinstance(result, dict):
        raise GameQualityError("evaluation artifact must be an object")
    return result


def load_completed(directory: Path, identity: dict[str, object],
                   task_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous = digest(identity)
    known = {f"{index:02d}-{task_id}.json" for index, task_id in enumerate(task_ids)}
    if any(path.name not in known for path in directory.glob("[0-9][0-9]-*.json")):
        raise GameQualityError("result directory contains an unknown task artifact")
    gap = False
    for index, task_id in enumerate(task_ids):
        path = directory / f"{index:02d}-{task_id}.json"
        if not path.exists():
            gap = True
            continue
        if gap:
            raise GameQualityError("completed task results are not a contiguous prefix")
        envelope = read_json(path)
        proof = envelope.pop("artifact_sha256", None)
        if (proof != digest(envelope) or envelope.get("run_sha256") != digest(identity)
                or envelope.get("previous_sha256") != previous
                or envelope.get("task_id") != task_id):
            raise GameQualityError("task artifact identity or hash chain changed")
        row = envelope.get("result")
        if not isinstance(row, dict) or row.get("task_id") != task_id:
            raise GameQualityError("task artifact is incomplete")
        # Verify score content as well as artifact hashes; hashes are integrity
        # evidence, never an independent attestation of model execution.
        task = select_tasks(task_ids=(task_id,))[0]
        expected = score_response(task, row["response_text"],
                                  elapsed_seconds=row["elapsed_seconds"],
                                  finish_reason=row["finish_reason"])
        if row != expected:
            raise GameQualityError("saved response and score disagree")
        rows.append(envelope | {"artifact_sha256": proof})
        previous = proof
    return rows


async def evaluate(args: argparse.Namespace) -> dict[str, object]:
    # Imports stay inside explicit operator execution: --help and scorer tests
    # never activate a runtime or inspect a user's model files.
    from skeleton.app.local_ai import load_gguf_deployment
    from skeleton.app.jeeves_local_lease import LocalInferenceLease
    from skeleton.ai.runtime.inference.local import LocalInferenceEngine, LocalInferenceRequest

    tasks = select_tasks(limit=args.limit,
                         task_ids=tuple(args.task_ids.split(",")) if args.task_ids else None)
    if not 64 <= args.output_tokens <= 256:
        raise GameQualityError("output tokens must be in [64, 256]")
    if not 1 <= args.task_seconds <= 600 or not args.task_seconds <= args.total_seconds <= 14400:
        raise GameQualityError("finite per-task/total budgets are invalid")
    output = Path(args.output_dir).expanduser()
    if output.is_symlink():
        raise GameQualityError("output directory must not be a symlink")
    if args.resume:
        if not output.is_dir():
            raise GameQualityError("resume requires an existing result directory")
    else:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    if os.name == "posix" and output.stat().st_mode & 0o077:
        raise GameQualityError("result directory must have private 0700 permissions")
    # The existing OS-backed lease prevents concurrent runners in this result
    # workspace and retains POSIX child ownership after supervisor death.
    with LocalInferenceLease(output / "evaluation").hold():
        model = load_gguf_deployment(args.manifest)
        if model.model_id != "jeeves":
            raise GameQualityError("the operator's admitted Jeeves identity is required")
        model.check_readiness()
        source = source_identity()
        manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
        config = json.loads(canonical_bytes(asdict(model.config)))
        identity: dict[str, object] = {
            "schema": REPORT_SCHEMA, "taskset_id": TASKSET_ID,
            "taskset_sha256": taskset_digest(), "scorer_id": SCORER_ID,
            "source": source, "model_id": model.model_id,
            "model_sha256": model.model_digest,
            "runtime_sha256": model.runtime_digest,
            "deployment_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
            "config_sha256": digest(config),
            "execution_profile_sha256": model.execution_profile_digest,
            "config": config,
            "generation_mode": ("runtime-schema-constrained-json" if args.structured_output
                                else "plain-json-instruction"),
            "task_output_schema_sha256": ({task.task_id: digest(output_schema(task)) for task in tasks}
                                           if args.structured_output else {}),
            "request_policy_sha256": digest({"structured_output": args.structured_output,
                                              "temperature": 0.0, "seed": args.seed,
                                              "output_tokens": args.output_tokens,
                                              "schemas": [output_schema(task) for task in tasks]
                                              if args.structured_output else []}),
            "environment": {"platform": platform.platform(), "machine": platform.machine(),
                            "python": platform.python_version(), "cpu_count": os.cpu_count()},
            "task_ids": [task.task_id for task in tasks],
            "budgets": {"output_tokens_per_task": args.output_tokens,
                        "task_seconds": args.task_seconds,
                        "total_seconds_per_invocation": args.total_seconds,
                        "max_inflight": 1},
            "seed": args.seed, "network_provider_used": False,
            "network_sandbox_attested": False,
            "generated_code_executed": False,
        }
        manifest_file = output / "run.json"
        if args.resume:
            if read_json(manifest_file) != identity:
                raise GameQualityError("resume source/model/config/taskset/environment identity differs")
            if read_json(output / "taskset.json") != json.loads(canonical_bytes(taskset_manifest())):
                raise GameQualityError("saved taskset differs from the fixed workload")
        else:
            create_json(manifest_file, identity)
            create_json(output / "taskset.json", taskset_manifest())
        snapshot_source(output, source, resume=args.resume)
        rows = load_completed(output, identity, tuple(task.task_id for task in tasks))
        invocation_started = time.monotonic()
        deadline = invocation_started + args.total_seconds
        engine = LocalInferenceEngine(model, cache_size=0, max_concurrency=1)
        stop_reason = "selected_tasks_complete"
        try:
            for index, task in enumerate(tasks[len(rows):], start=len(rows)):
                if source_identity() != source:
                    stop_reason = "source_identity_changed"
                    break
                if time.monotonic() >= deadline:
                    stop_reason = "total_deadline_reached"
                    break
                request = LocalInferenceRequest(
                    prompt=task.prompt, instructions=INSTRUCTIONS,
                    max_output_tokens=args.output_tokens, seed=args.seed,
                    temperature=0.0, tool_choice="none",
                    structured_output_schema=output_schema(task) if args.structured_output else None,
                )
                started = time.monotonic()
                task_deadline = min(deadline, started + args.task_seconds)
                error_code = None
                result = None
                representation = "no-model-output"
                try:
                    result = await engine.generate(request, deadline=task_deadline,
                                                   resource_max_output_tokens=args.output_tokens)
                    text, representation = response_text(result, structured=args.structured_output)
                    finish = result.finish_reason
                    if finish == "tool_calls":
                        error_code, finish = "unexpected_tool_output", "error"
                    if result.model_digest != model.model_digest or result.cached:
                        raise GameQualityError("model identity or cache policy changed")
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
                except Exception as exc:
                    # Never copy backend exception text or environment values
                    # into shareable evaluation results.
                    error_code = type(exc).__name__
                    text = ""
                    finish = "deadline" if time.monotonic() >= task_deadline else "error"
                elapsed = time.monotonic() - started
                scored = score_response(task, text, elapsed_seconds=elapsed, finish_reason=finish)
                envelope: dict[str, object] = {
                    "run_sha256": digest(identity), "task_id": task.task_id,
                    "previous_sha256": rows[-1]["artifact_sha256"] if rows else digest(identity),
                    "request_sha256": request.digest, "result": scored,
                    "error_code": error_code,
                    "response_representation": representation,
                    "local_execution_receipt_sha256": (
                        result.execution_receipt_digest if result is not None else None),
                    "input_tokens": result.input_tokens if result is not None else None,
                    "output_tokens": result.output_tokens if result is not None else None,
                    "usage_source": result.usage_source if result is not None else None,
                    "inference_authority": "local-runtime-custody-not-independent-attestation",
                }
                envelope["artifact_sha256"] = digest(envelope)
                create_json(output / f"{index:02d}-{task.task_id}.json", envelope)
                rows.append(envelope)
                print(json.dumps({"task_id": task.task_id, "finish_reason": finish,
                                  "all_checks_pass": scored["all_deterministic_checks_pass"],
                                  "elapsed_seconds": round(elapsed, 3)}, sort_keys=True), flush=True)
                if finish in {"deadline", "error", "cancelled"}:
                    stop_reason = "task_execution_failed"
                    break
        finally:
            await engine.close(cancel_running=True)
        summary = {"schema": REPORT_SCHEMA, "run_sha256": digest(identity),
                   "summary": summarize(row["result"] for row in rows),
                   "remaining_task_ids": [task.task_id for task in tasks[len(rows):]],
                   "selected_tasks": len(tasks), "stop_reason": stop_reason,
                   "source_identity_unchanged": source_identity() == source,
                   "resume_cursor": len(rows),
                   "last_result_sha256": rows[-1]["artifact_sha256"] if rows else None}
        # A completed-prefix summary is immutable. Repeated identical resumes
        # reuse it; differing summaries fail rather than destroying evidence.
        summary_path = output / f"summary-{len(rows):02d}.json"
        if summary_path.exists():
            if read_json(summary_path) != summary:
                raise GameQualityError("existing prefix summary differs; retain both attempts separately")
        else:
            create_json(summary_path, summary)
        return summary


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", required=True, help="Existing operator-owned pinned Jeeves GGUF manifest")
    result.add_argument("--output-dir", required=True, help="New private results directory, or same directory with --resume")
    choice = result.add_mutually_exclusive_group()
    choice.add_argument("--limit", type=int)
    choice.add_argument("--task-ids", help="Comma-separated fixed IDs gb01 through gb24")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--output-tokens", type=int, default=192)
    result.add_argument("--task-seconds", type=int, default=120)
    result.add_argument("--total-seconds", type=int, default=1800)
    result.add_argument("--seed", type=int, default=17)
    result.add_argument("--structured-output", action="store_true",
                        help="Explicit candidate: existing native JSON-schema decoding; fixed tasks/scorer unchanged")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        report = asyncio.run(evaluate(args))
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({"status": "held", "error_code": type(exc).__name__,
                          "quality_measured": False,
                          "detail": "No fallback or overwrite; inspect retained private artifacts."}), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if (not report["remaining_task_ids"]
                 and report["stop_reason"] == "selected_tasks_complete"
                 and report["source_identity_unchanged"]) else 3


if __name__ == "__main__":
    raise SystemExit(main())
