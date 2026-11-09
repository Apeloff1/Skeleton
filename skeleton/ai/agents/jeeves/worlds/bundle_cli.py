"""Compile and verify complete offline Jeeves playable bundles."""
from __future__ import annotations

import argparse
import json
import sys

from .bundle import PlayableBundleStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-bundle")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--world-id", required=True)
    compile_cmd.add_argument("--world-digest", required=True)
    compile_cmd.add_argument("--asset-digest", required=True)
    compile_cmd.add_argument("--timeline-digest", required=True)
    compile_cmd.add_argument("--era", required=True)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--world-id", required=True)
    args = parser.parse_args(argv)
    try:
        store = PlayableBundleStore(args.store)
        if args.action == "compile":
            receipt = store.compile(args.world_id,
                                    world_digest=args.world_digest,
                                    asset_digest=args.asset_digest,
                                    timeline_digest=args.timeline_digest,
                                    era=args.era)
        else:
            receipt = store.verify(args.world_id)
        result = {"ok": True, "receipt": receipt}
    except (CanonError, OSError) as exc:
        result = {"ok": False, "error": exc.code if isinstance(exc, CanonError)
                  else "io_error"}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
