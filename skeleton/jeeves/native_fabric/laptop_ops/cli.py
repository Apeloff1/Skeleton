"""Source-only local operational diagnostics from bounded JSON on stdin."""
from __future__ import annotations
import argparse
import json
import sys
from .contracts import LaptopGateHold, canonical
from .policy import DEFAULT_LIMITS
from .redaction import diagnostic
from .runner import domain_coverage, evaluate_domain, list_domains
from .strict_json import record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Jeeves GGUF first-laptop evidence admission"
    )
    parser.add_argument("--json-stdin", action="store_true")
    parser.add_argument("--list-domains", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.list_domains:
            if args.json_stdin:
                raise LaptopGateHold("list mode never reads operator evidence")
            coverage = domain_coverage()
            data = {"schema": "jeeves.laptop_ops.domains.v1",
                    "domains": list_domains(),
                    "coverage": coverage,
                    "source_contracts_complete": all(
                        entry["source_contract_present"] for entry in coverage
                    ),
                    "native_inference_witnessed": False,
                    "device_qualified": False,
                    "release_certified": False}
        else:
            if not args.json_stdin:
                raise LaptopGateHold("explicit bounded evidence stdin required")
            payload = record(sys.stdin.buffer.read(
                DEFAULT_LIMITS.max_evidence_bytes + 1
            ))
            verdict = evaluate_domain(payload["domain"], payload["evidence"])
            data = verdict.to_record()
        output = canonical(data, maximum=DEFAULT_LIMITS.max_report_bytes)
        DEFAULT_LIMITS.assert_report(output)
        sys.stdout.buffer.write(output + b"\n")
        return 0 if args.list_domains or data.get("accepted", False) else 2
    except (Exception, KeyboardInterrupt) as exc:
        # No untrusted operator evidence, model bytes or private paths in logs.
        sys.stderr.write(json.dumps(
            diagnostic(type(exc).__name__), sort_keys=True
        ) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
