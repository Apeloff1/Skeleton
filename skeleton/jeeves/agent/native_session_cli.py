"""Operator-only physical GGUF multi-turn + cold replay acceptance runner.

Without --approve-native there is no model activation; prompt casebook is
read from bounded stdin, never shell arguments or logs. Backend startup
uses the existing independently verified installer and killable process.
Completed outputs are represented by sha256 only, never private answer text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.jeeves.native_fabric.contracts import parse_json
from .native_session_acceptance import (
    NativeSessionHold, SessionCase, SessionBudget,
    run_native_session, verify_cold_session_replay,
)
from .native_readiness import inspect_native_jeeves


def _casebook(raw: bytes) -> tuple[SessionCase, ...]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 262144:
        raise NativeSessionHold("finite operator casebook stdin required")
    value = parse_json(raw, max_bytes=262144)
    if type(value) is not dict or set(value) != {"schema", "cases"}:
        raise NativeSessionHold("operator casebook has unknown fields")
    if value["schema"] != "jeeves.native_session_casebook.v1":
        raise NativeSessionHold("unsupported multi-turn casebook version")
    records = value["cases"]
    if type(records) is not list or not 1 <= len(records) <= 32:
        raise NativeSessionHold("bounded nonempty operator session required")
    result = []
    for record in records:
        if (type(record) is not dict or
            not {"case_id", "prompt"} <= set(record) or
            not set(record) <= {"case_id", "prompt", "expected_output_sha256"}):
            raise NativeSessionHold("malformed native turn casebook entry")
        result.append(SessionCase(**record))
    if len({x.case_id for x in result}) != len(result):
        raise NativeSessionHold("repeated case identifier")
    return tuple(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicit real native GGUF multi-turn and cold SQLite replay acceptance"
    )
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--casebook-stdin", action="store_true")
    parser.add_argument("--cold-replay", action="store_true")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--maximum-turns", type=int, default=8)
    parser.add_argument("--maximum-reserved-output-tokens", type=int, default=8192)
    parser.add_argument("--maximum-prompt-bytes", type=int, default=65536)
    parser.add_argument("--maximum-wall-seconds", type=float, default=900)
    parser.add_argument("--maximum-single-turn-ms", type=int, default=300000)
    args = parser.parse_args(argv)
    try:
        if args.approve_native is not True or args.casebook_stdin is not True:
            raise NativeSessionHold("operator native activation and bounded casebook approval required")
        raw = sys.stdin.buffer.read(262145)
        cases = _casebook(raw)
        budget = SessionBudget(
            maximum_turns=args.maximum_turns,
            maximum_reserved_output_tokens=args.maximum_reserved_output_tokens,
            maximum_prompt_bytes=args.maximum_prompt_bytes,
            maximum_wall_seconds=args.maximum_wall_seconds,
            maximum_single_turn_ms=args.maximum_single_turn_ms,
        )
        if len(cases) > budget.maximum_turns:
            raise NativeSessionHold("operator requested more than approved maximum turns")
        if args.max_new_tokens * len(cases) > budget.maximum_reserved_output_tokens:
            raise NativeSessionHold("native output capacity exceeds operator reservation")
        kwargs = {
            "model_root": args.model_root, "state_dir": args.state_dir,
            "tenant": args.tenant, "subject": args.subject,
            "n_ctx": args.context,
            "max_new_tokens": args.max_new_tokens,
            "n_threads": args.threads, "gpu_layers": args.gpu_layers,
            "capacity_root": args.capacity_root,
            "capacity_budget_bytes": args.capacity_budget_bytes,
            "isolated": True,
        }
        stack, worker, installed = activate_checked(**kwargs)
        with stack:
            readiness = inspect_native_jeeves(worker, installed)
            if not readiness.source_bridge_ready:
                raise NativeSessionHold("source-bound native model readiness gate failed")
            first = run_native_session(worker, cases, approved=True, budget=budget)
        accepted = first
        if args.cold_replay:
            # Closing the previous stack is mandatory before second model
            # activation; the new process must prove committed old output.
            second_stack, second_worker, second_installed = activate_checked(**kwargs)
            with second_stack:
                readiness = inspect_native_jeeves(second_worker, second_installed)
                if not readiness.source_bridge_ready:
                    raise NativeSessionHold("cold-installed native model source identity changed")
                accepted = verify_cold_session_replay(
                    second_worker, cases, first, approved=True,
                )
        sys.stdout.write(json.dumps(
            accepted.to_record(), sort_keys=True, ensure_ascii=False,
        ) + "\n")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema": "jeeves.native_session_acceptance.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "native_physical_inference_qualified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "_casebook"]
