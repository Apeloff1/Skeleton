"""Render a source-bound offline editor; reviewed edits return through world-canon."""
from __future__ import annotations

import argparse
import json
import sys

from .editor import WorldEditorStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-editor")
    parser.add_argument("--store", required=True)
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--expected-digest", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = WorldEditorStore(args.store).render(
            args.world_id, args.expected_digest)
        result = {"ok": True, "receipt": receipt}
    except (CanonError, OSError) as exc:
        result = {"ok": False, "error": exc.code if isinstance(exc, CanonError)
                  else "io_error"}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
