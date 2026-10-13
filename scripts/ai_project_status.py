#!/usr/bin/env python3
"""Print evidence-bound AI masterplan, capability and enterprise readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skeleton.ai.product.completion_status import (  # noqa: E402
    CompletionStatusError,
    inspect_project,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of Skeleton AI project completion"
    )
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="machine-readable JSON")
    parser.add_argument("--strict", action="store_true",
                        help="return nonzero unless all project gates are proven")
    args = parser.parse_args(argv)
    try:
        status = inspect_project(args.root)
    except CompletionStatusError as exc:
        print(f"Cannot verify project status: {exc}", file=sys.stderr)
        return 2
    report = status.to_dict()
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    else:
        print(f"Masterplan: {status.plan_mature}/{status.plan_volume_total} "
              f"({status.plan_percent}%) implemented/verified")
        print(f"Product capabilities: {status.product_complete}/"
              f"{status.product_capability_total} ({status.product_percent}%)")
        print(f"Enterprise: {status.enterprise_qualified}/"
              f"{status.plan_volume_total} ({status.enterprise_percent}%)")
        print(f"Current signature index: "
              f"{'valid' if status.signature_index_fresh else 'STALE'}")
        print("Total project %: not defensibly quantifiable until live acceptance")
        print("Blocking prerequisites:")
        for blocker in status.blockers:
            print(f"  - {blocker}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
