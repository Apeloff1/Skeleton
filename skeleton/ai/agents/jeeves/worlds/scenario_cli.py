"""Explicit operator scenario suite proposal, approval and playable compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .scenario import ScenarioStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-scenario")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "save", "inspect", "approve", "compile", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("propose", "save"):
            cmd.add_argument("--cases-file", required=True)
        if action == "save":
            cmd.add_argument("--expected-world-digest", required=True)
        if action in ("approve", "compile"):
            cmd.add_argument("--expected-suite-digest", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
    args = parser.parse_args(argv)
    try:
        store = ScenarioStore(args.store)
        if args.action in ("propose", "save"):
            with open(args.cases_file, "rb") as stream:
                cases = strict_json(stream.read(524289))
            suite = store.propose(args.world_id, cases)
            if args.action == "propose":
                result = {"ok": True, "suite": suite, "suite_digest": __digest(suite)}
            else:
                result = {"ok": True, "suite_digest": store.save(
                    args.world_id, suite,
                    expected_world_digest=args.expected_world_digest,
                )}
        elif args.action == "inspect":
            result = {"ok": True, **store.inspect(args.world_id)}
        elif args.action == "approve":
            result = {"ok": True, "suite_digest": store.approve(
                args.world_id, expected_suite_digest=args.expected_suite_digest,
                review_note=args.review_note,
            )}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, expected_suite_digest=args.expected_suite_digest,
            )}
        else:
            result = {"ok": True, "receipt": store.verify(args.world_id)}
    except (CanonError, OSError) as exc:
        print(json.dumps({
            "ok": False, "error": exc.code if isinstance(exc, CanonError) else "io_error",
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


def __digest(value):
    from .world_canon import digest
    return digest(value)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
