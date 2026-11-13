"""Operator CLI for original asset descriptor review and engine compilation."""
from __future__ import annotations

import argparse
import json
import sys

from .asset_briefs import ASSET_SCHEMA, AssetBriefStore, edit_briefs, propose_asset
from .world_canon import CanonError, digest, prove, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-assets")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("propose")
    for field in ("world-id", "id", "scene", "kind", "description", "alt-text"):
        plan.add_argument("--" + field, required=True)
    plan.add_argument("--width", type=int, default=16)
    plan.add_argument("--height", type=int, default=16)
    plan.add_argument("--colors", type=int, default=4)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--world-id", required=True)
    patch = sub.add_parser("edit")
    patch.add_argument("--world-id", required=True)
    patch.add_argument("--expected-digest", required=True)
    patch.add_argument("--operation-file", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--world-id", required=True)
    compile_cmd.add_argument("--expected-digest", required=True)
    compile_cmd.add_argument("--era", required=True)
    args = parser.parse_args(argv)
    try:
        store = AssetBriefStore(args.store)
        if args.action == "propose":
            world = store.worlds.read(args.world_id)
            item = propose_asset(world, asset_id=args.id, scene=args.scene,
                                 kind=args.kind, description=args.description,
                                 alt_text=args.alt_text, width=args.width,
                                 height=args.height, colors=args.colors)
            data = {"schema": ASSET_SCHEMA, "world_id": args.world_id,
                    "world_digest": prove(world).source_digest, "assets": [item]}
            result = {"ok": True, "asset_briefs_digest":
                      store.publish(args.world_id, data, create=True),
                      "review_required": True}
        elif args.action == "inspect":
            data = store.read(args.world_id)
            result = {"ok": True, "asset_briefs": data, "digest": digest(data)}
        elif args.action == "edit":
            with open(args.operation_file, "rb") as stream:
                operation = strict_json(stream.read(524289))
            world = store.worlds.read(args.world_id)
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_asset_source")
            revised = edit_briefs(data, world, operation)
            result = {"ok": True, "asset_briefs_digest":
                      store.publish(args.world_id, revised,
                                    expected_digest=args.expected_digest)}
        else:
            result = {"ok": True, **store.compile(args.world_id,
                      args.expected_digest, args.era)}
    except (CanonError, OSError) as exc:
        print(json.dumps({"ok": False, "error": exc.code if isinstance(exc, CanonError)
                          else "io_error"}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
