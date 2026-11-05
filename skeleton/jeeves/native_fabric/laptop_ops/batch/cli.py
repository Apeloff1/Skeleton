"""Operator-only whole-stack source diagnostics, no native model startup."""
from __future__ import annotations

import argparse
import json
import sys

from skeleton.jeeves.native_fabric.laptop_ops.contracts import canonical
from skeleton.jeeves.native_fabric.laptop_ops.redaction import diagnostic
from .catalog import manifest
from .limits import DEFAULT_BUNDLE_LIMITS
from .runner import evaluate_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Source-only twenty-domain Jeeves local startup diagnostic"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--json-stdin", action="store_true")
    mode.add_argument("--catalog", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.catalog:
            report = manifest()
            accepted = True
        else:
            raw = sys.stdin.buffer.read(
                DEFAULT_BUNDLE_LIMITS.max_evidence_bytes + 1
            )
            report = evaluate_json(raw).to_record()
            accepted = report["accepted_source_only"]
        output = DEFAULT_BUNDLE_LIMITS.require_report(
            canonical(report, maximum=DEFAULT_BUNDLE_LIMITS.max_report_bytes)
        )
        sys.stdout.buffer.write(output + b"\n")
        return 0 if accepted else 2
    except (Exception, KeyboardInterrupt) as exc:
        # Diagnostic failures disclose no private source, path or prompt.
        sys.stderr.write(json.dumps(
            diagnostic(type(exc).__name__), sort_keys=True
        ) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
