"""Read-only machine interface for the static Jeeves world tool registry."""
from __future__ import annotations

import argparse
import json
import sys

from .tools import invoke_world_tool, manifest
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-tools")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("manifest")
    invoke = sub.add_parser("invoke")
    invoke.add_argument("--request-json", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "manifest":
            result = {"ok": True, "manifest": manifest()}
        else:
            request = strict_json(args.request_json.encode("utf-8"))
            result = {"ok": True, "response": invoke_world_tool(args.store, request)}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
