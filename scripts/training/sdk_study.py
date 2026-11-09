"""Offline operator CLI for canonical SDK inventory and training review intake."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.training.sdk_study import (
    SDKStudyError, extend_multidomain, target_inventory, validate_sources,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Inspect SDKs; stage independently reviewed evidence for existing Jeeves trainer."
    )
    sub = p.add_subparsers(dest="operation", required=True)
    sub.add_parser("inventory", help="print complete canonical console SDK target census")
    source = sub.add_parser("verify-sources", help="verify exact operator-installed SDK documents")
    source.add_argument("--sources", required=True, type=Path)
    extend = sub.add_parser("extend-corpus", help="publish reviewed SDK extension, no weight changes")
    extend.add_argument("--sources", required=True, type=Path)
    extend.add_argument("--reviewed", required=True, type=Path)
    extend.add_argument("--base-manifest", required=True, type=Path)
    extend.add_argument("--output-dir", required=True, type=Path)
    extend.add_argument("--prefix", required=True)
    extend.add_argument("--review-id", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "inventory":
            result = target_inventory()
        elif args.operation == "verify-sources":
            result, _ = validate_sources(args.sources)
        else:
            result = extend_multidomain(
                args.sources, args.reviewed, args.base_manifest, args.output_dir,
                prefix=args.prefix, review_id=args.review_id,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (SDKStudyError, ValueError, OSError, RuntimeError, ImportError) as exc:
        print("SDK training intake blocked: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
