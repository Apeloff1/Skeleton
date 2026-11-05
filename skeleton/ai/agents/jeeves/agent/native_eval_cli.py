"""Operator-only deterministic native GGUF evaluation with no answer disclosure.

Every test case is explicitly supplied on stdin, bounded and validated before
native activation, and evaluated through the canonical installed model plus
authoritative SQLite receipts. A source-only unit test may mock these
boundaries but is never accepted as physical model/device qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from .native_quality_eval import (
    EvalBudget, NativeJeevesEvaluation, NativeEvaluationHold,
    load_evaluation_cases,
)
from .native_readiness import inspect_native_jeeves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicit, finite, source-bound local GGUF Jeeves evaluation"
    )
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--cases-stdin", action="store_true")
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--maximum-cases", type=int, default=32)
    parser.add_argument("--maximum-reserved-tokens", type=int, default=8192)
    parser.add_argument("--maximum-wall-seconds", type=float, default=900)
    args = parser.parse_args(argv)
    try:
        if not args.approve_native or not args.cases_stdin:
            raise NativeEvaluationHold("operator approval and stdin casebook required")
        raw = sys.stdin.buffer.read(262145)
        if not 1 <= len(raw) <= 262144:
            raise NativeEvaluationHold("operator evaluation casebook byte ceiling exceeded")
        cases = load_evaluation_cases(raw)
        budget = EvalBudget(
            maximum_cases=args.maximum_cases,
            maximum_reserved_tokens=args.maximum_reserved_tokens,
            maximum_wall_seconds=args.maximum_wall_seconds,
        )
        if len(cases) > budget.maximum_cases:
            raise NativeEvaluationHold("case count exceeds operator-approved batch")
        if len(cases) * args.max_new_tokens > budget.maximum_reserved_tokens:
            raise NativeEvaluationHold("batch capacity exceeds explicit reservation")
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
                raise NativeEvaluationHold("source-verified installed model is not bound")
            report = NativeJeevesEvaluation(
                worker, approved=True, budget=budget,
            ).run(cases)
        sys.stdout.write(json.dumps(report, sort_keys=True, ensure_ascii=False) + "\n")
        return 0 if report["failed"] == 0 else 3
    except (Exception, KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema": "jeeves.native_evaluation_result.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "actual_native_evaluation_certified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
