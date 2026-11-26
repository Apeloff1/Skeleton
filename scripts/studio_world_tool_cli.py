"""Offline operator CLI for explicit typed Jeeves world-tool routing."""
from __future__ import annotations

import argparse
import json
import sys

from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    MAX_REQUEST_BYTES, route_world_tool, world_tool_catalog,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def _strict_json(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > MAX_REQUEST_BYTES:
        raise StudioQuestError("invalid bounded Jeeves world tool input")
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise StudioQuestError("duplicate Jeeves world tool JSON key")
                result[key] = value
            return result
        parsed = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite Jeeves world tool JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid Jeeves world tool JSON") from exc
    if type(parsed) is not dict:
        raise StudioQuestError("Jeeves world tool input must be an object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Authorized offline Jeeves world tools")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--catalog", action="store_true",
                       help="List reviewed typed original-world tool contracts")
    modes.add_argument("--execute-stdin", action="store_true",
                       help="Read one strict bounded JSON tool envelope from stdin")
    ap.add_argument("--allow-authoring", action="store_true",
                    help="Explicitly permit authoring adapters for this invocation")
    args = ap.parse_args(argv)
    if args.allow_authoring and not args.execute_stdin:
        ap.error("--allow-authoring requires --execute-stdin")
    try:
        if args.catalog:
            payload = world_tool_catalog()
        else:
            request = _strict_json(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
            payload = route_world_tool(
                request, authorized=True, allow_authoring=args.allow_authoring)
    except (StudioQuestError, PermissionError, TypeError, ValueError,
            UnicodeError, OSError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
