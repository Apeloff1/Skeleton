#!/usr/bin/env python3
"""Build a Godot prototype from a bounded, local Jeeves design proposal.

The operator selects an existing digest-pinned GGUF manifest. Model output is
data only: the existing plan guard and deterministic Forge compiler retain
authority. The same total deadline covers planning and the canonical builder.
No hosted fallback, generated-code execution, or automatic quality promotion.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
        run = subprocess.run([binary, "--headless", "--path", str(project), *arguments],
            capture_output=True, text=True, timeout=min(90, remaining), check=False,
            env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1"})
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


def execute(args: argparse.Namespace) -> dict[str, Any]:
    from skeleton.app.local_ai import load_gguf_deployment, private_desktop_database
    from skeleton.forge.game_builder import build_playable_game, public_payload
    from skeleton.forge.projector import write_project

    if type(args.output_tokens) is not int or not 32 <= args.output_tokens <= 1024:
        raise ValueError("output tokens must be 32..1024")
    if not 10 <= args.planning_timeout <= args.deadline <= 600:
        raise ValueError("require 10 <= planning timeout <= total deadline <= 600 seconds")
    if not isinstance(args.brief, str) or not 1 <= len(args.brief.strip()) <= 4000:
        raise ValueError("brief must contain 1..4000 characters")
    args.out = args.out.expanduser().absolute()
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("choose a new project output directory")
    if args.report and (args.report.exists() or args.report.is_symlink()):
        raise ValueError("choose a new report file")
    started = time.monotonic()
    deadline_at = started + args.deadline
    compiled = compile_brief(args.brief)
    backend = load_gguf_deployment(args.manifest)
    if backend.model_id != "jeeves":
        raise ValueError("an explicit Jeeves local deployment is required")
    workspace = args.workspace_database or private_desktop_database(backend.model_digest)
    planning = {"status": "unavailable", "attempts": [], "quality_qualified": False}
    spec = compiled
    try:
        spec, planning = asyncio.run(propose(
            backend, compiled, output_tokens=args.output_tokens,
            deadline_at=min(deadline_at, time.monotonic() + args.planning_timeout),
            repair=not args.no_repair, workspace_database=workspace,
        ))
    except (ValueError, OSError, RuntimeError):
        # Safe public classification; no private model path/stderr disclosure.
        planning["reason"] = "local_model_or_lease_unavailable"
    if args.require_model and planning["status"] != "accepted":
        return {"schema": SCHEMA, "ok": False, "planning": planning,
                "build": None, "reason": "accepted_model_proposal_required"}
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        return {"schema": SCHEMA, "ok": False, "planning": planning,
                "build": None, "reason": "total_deadline_exceeded"}

    def planner(committed: Mapping[str, Any]) -> Mapping[str, Any]:
        # Reapply only the admitted mutable fields onto the builder's actual
        # resolved spec; never overwrite its locked genre/scope/era/brief.
        return {**committed, **{key: spec[key] for key in
                ("title", "fantasy", "core_loop", "gameplay") if key in spec}}

    result = build_playable_game(args.brief, planner=planner,
        playtest_mode=args.playtest, deadline_s=remaining)
    # Build in memory first. A timed-out daemon stage in the legacy builder
    # can never publish to the user's destination after this command fails.
    if result["ok"]:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.out.parent.resolve() != args.out.parent:
            raise ValueError("project output parent must not contain symbolic links")
        with tempfile.TemporaryDirectory(prefix=".jeeves-game-", dir=args.out.parent) as temporary:
            staged = Path(temporary) / "project"
            manifest = write_project(staged, result["files"], meta={
                "spec_id": result["spec"]["spec_id"], "genre": result["spec"]["genre"],
                "planning_status": planning["status"],
            })
            if args.playtest == "require":
                acceptance = qualify_interactive(staged, result["spec"]["genre"], deadline_at)
                result["interactive"] = {**(result.get("interactive") or {}), **acceptance}
            if time.monotonic() >= deadline_at:
                return {"schema": SCHEMA, "ok": False, "planning": planning,
                        "build": None, "reason": "total_deadline_exceeded"}
            manifest["root"] = str(args.out)
            (staged / "FORGE_MANIFEST.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            publish_create_only(staged, args.out)
            result["project"] = manifest
    return {"schema": SCHEMA, "ok": result["ok"], "planning": planning,
            "build": public_payload(result, include_files=False),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "general_model_quality_qualified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workspace-database", type=Path,
                        help="existing local workspace lease namespace; conversation content is not changed")
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--planning-timeout", type=int, default=90)
    parser.add_argument("--deadline", type=int, default=180)
    parser.add_argument("--no-repair", action="store_true")
    parser.add_argument("--require-model", action="store_true")
    parser.add_argument("--playtest", choices=("off", "auto", "require"), default="require")
    args = parser.parse_args(argv)
    try:
        report = execute(args)
        encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.report:
            descriptor = os.open(args.report,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(encoded)
        print(encoded, end="")
        return 0 if report["ok"] else 1
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print(json.dumps({"schema": SCHEMA, "ok": False,
                          "error": "local_game_build_rejected"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
