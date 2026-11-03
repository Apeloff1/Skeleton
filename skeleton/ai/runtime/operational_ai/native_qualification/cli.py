"""Strict operator-initiated real-native qualification; never downloads weights."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from pathlib import Path
import json
import sys
from .canonical import hex64
from .contracts import ModelIdentity, ExecutionLimits
from .corpus import DOMAINS, inventory, iter_cases
from .diagnostics import inspect_report
from .errors import QualificationError, deny
from .result_writer import save_new_private
from .runner import NativeQualificationRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure actual Skeleton offline native model against original conformance tasks"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--doctor-report", type=Path)
    mode.add_argument("--run-native", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--tokenizer-sha256")
    parser.add_argument("--license")
    parser.add_argument("--model-name", default="native")
    parser.add_argument("--tenant", default="local")
    parser.add_argument("--user", default="operator")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--memory-db", type=Path)
    parser.add_argument("--journal-db", type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--domain", choices=DOMAINS)
    parser.add_argument("--context-tokens", type=int, default=8192)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--input-bytes", type=int, default=8192)
    parser.add_argument("--output-bytes", type=int, default=16384)
    parser.add_argument("--max-total-wall-ms", type=int, default=10800000)
    parser.add_argument("--max-case-wall-ms", type=int, default=300000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.inventory:
            report = inventory()
            print(json.dumps({
                "schema": report["schema"], "count": report["count"],
                "domains": report["domains"],
                "actual_model_tested": False,
                "qualification_issued": False,
            }, sort_keys=True))
            return 0
        if args.doctor_report:
            raw = args.doctor_report.read_bytes()
            result = inspect_report(raw)
            print(json.dumps(result, sort_keys=True))
            return 0
        if not all([
            args.checkpoint, args.sha256, args.license,
            args.database, args.memory_db, args.journal_db,
            args.output_directory,
        ]):
            deny("native-required-arguments")
        hex64(args.sha256, "checkpoint")
        if args.tokenizer_sha256 is not None:
            hex64(args.tokenizer_sha256, "tokenizer")
        from skeleton.ai.runtime.operational_ai.transport.cli import build_service
        with ExitStack() as stack:
            service = build_service(args, stack)
            model = ModelIdentity(
                model_sha256=service.actor.model_digest,
                tokenizer_sha256=service.actor.tokenizer_digest,
                tenant=service.actor.tenant, user=service.actor.user,
                license_id=args.license, checkpoint_sha256=args.sha256,
            )
            cases = tuple(
                x for x in iter_cases()
                if args.domain is None or x.domain == args.domain
            )
            runner = NativeQualificationRunner(
                service, model=model,
                limits=ExecutionLimits(
                    max_cases=len(cases), max_total_wall_ms=args.max_total_wall_ms,
                    max_case_wall_ms=args.max_case_wall_ms,
                ),
            )
            report = runner.run(cases, complete_corpus=args.domain is None)
            written = save_new_private(
                report, args.output_directory,
                "native_" + report.run_id,
            )
        print(json.dumps({
            "report_sha256": written["sha256"],
            "report_path": written["path"],
            "cases_total": len(report.cases),
            "cases_passed": sum(case.passed for case in report.cases),
            "policy_threshold_met": report.record()["policy_threshold_met"],
            "release_certified": False, "ci_qualified": False,
        }, sort_keys=True))
        return 0 if report.record()["policy_threshold_met"] else 1
    except (QualificationError, OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({
            "status": "blocked", "reason": getattr(exc, "code", type(exc).__name__),
            "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
