"""Trusted local operator CLI for the game-builder's reviewed knowledge library.

This is deliberately not a web crawler or a network service. The local invoking
process is responsible for authenticating its operator. A CLI switch is an
explicit acknowledgement, not proof of identity or source permission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .contracts import canonical_json
from .reviewed_knowledge import (
    KnowledgeError, ReviewedDocument, ReviewedKnowledgeStore,
)


MAX_IMPORT_BYTES = 1_800_000


def _json_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise KnowledgeError("duplicate JSON import key")
        result[key] = value
    return result


def _read_import(path: str) -> ReviewedDocument:
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise KnowledgeError("import must be a regular local file")
    if file.stat().st_size > MAX_IMPORT_BYTES:
        raise KnowledgeError("import exceeds bounded byte budget")
    try:
        with file.open("rb") as stream:
            raw = stream.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            raise KnowledgeError("import exceeds bounded byte budget")
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_json_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(KnowledgeError("nonfinite import")),
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise KnowledgeError("invalid UTF-8 JSON import") from exc
    return ReviewedDocument.from_mapping(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.knowledge_cli",
        description="Operator-reviewed, local, rights-aware gameplay knowledge storage.",
    )
    parser.add_argument("--store", required=True, help="Local SQLite database path")
    parser.add_argument(
        "--trusted-local-operator", action="store_true",
        help="Acknowledge that the calling process has separately authenticated this operator",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    imported = commands.add_parser("import", help="Admit a reviewed JSON document revision")
    imported.add_argument("--input", required=True, help="Local JSON source/review package")
    imported.add_argument("--expected-parent", help="Prior revision digest; omit for genesis")

    queried = commands.add_parser("query", help="Search admissible reviewed evidence")
    queried.add_argument("--owner", required=True)
    queried.add_argument("--text", required=True)
    queried.add_argument("--scope", default="design_reference")
    queried.add_argument("--limit", type=int, default=12)
    queried.add_argument("--minimum-confidence-ppm", type=int, default=0)
    queried.add_argument("--no-diversity", action="store_true")

    brief = commands.add_parser("brief", help="Create a citation-linked builder research brief")
    brief.add_argument("--owner", required=True)
    brief.add_argument("--text", required=True)
    brief.add_argument("--scope", default="design_reference")
    brief.add_argument("--limit", type=int, default=12)
    brief.add_argument("--minimum-confidence-ppm", type=int, default=0)
    brief.add_argument("--minimum-independent-groups", type=int, default=1)

    history = commands.add_parser("history", help="List source revision custody")
    history.add_argument("--owner", required=True)
    history.add_argument("--source-id", required=True)

    root = commands.add_parser("root", help="Compute validated owner knowledge root")
    root.add_argument("--owner", required=True)

    refresh = commands.add_parser("plan-recrawl", help="Prioritize source review gaps without network I/O")
    refresh.add_argument("--owner", required=True)
    refresh.add_argument("--as-of", required=True, help="Trusted UTC timestamp, YYYY-MM-DDTHH:MM:SSZ")
    refresh.add_argument("--scope", default="design_reference")
    refresh.add_argument("--max-age-seconds", type=int, default=604800)
    refresh.add_argument("--minimum-independent-groups", type=int, default=2)
    refresh.add_argument("--minimum-confidence-ppm", type=int, default=800000)
    refresh.add_argument("--limit", type=int, default=20)

    queue = commands.add_parser("queue-recrawls", help="Atomically queue reviewed refresh gaps, without network permission")
    queue.add_argument("--owner", required=True)
    queue.add_argument("--at-epoch", type=int, required=True, help="Trusted integer UTC epoch seconds")
    queue.add_argument("--max-age-seconds", type=int, default=604800)
    queue.add_argument("--minimum-independent-groups", type=int, default=2)
    queue.add_argument("--minimum-confidence-ppm", type=int, default=800000)
    queue.add_argument("--limit", type=int, default=20)

    pending = commands.add_parser("pending-recrawls", help="Inspect queued non-executable refresh orders")
    pending.add_argument("--owner", required=True)
    pending.add_argument("--at-epoch", type=int, required=True)
    pending.add_argument("--limit", type=int, default=32)

    hoag = commands.add_parser("hoag-view", help="Display current revocable advisory memory projection")
    hoag.add_argument("--owner", required=True)
    hoag.add_argument("--at-epoch", type=int, required=True)
    hoag.add_argument("--limit", type=int, default=32)

    erased = commands.add_parser("erase-owner", help="Permanently delete owned source excerpts")
    erased.add_argument("--owner", required=True)
    erased.add_argument("--confirm-erasure", required=True, help="Must exactly repeat the owner")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authentication acknowledgement required", file=sys.stderr)
        return 2
    try:
        with ReviewedKnowledgeStore(args.store) as store:
            if args.command == "import":
                doc = _read_import(args.input)
                output: Any = store.import_document(
                    doc, expected_parent_digest=args.expected_parent,
                    authorized=True,
                ).to_payload()
            elif args.command == "query":
                output = {
                    "schema": "skeleton.game_builder.reviewed_query.v1",
                    "owner": args.owner,
                    "knowledge_root": store.snapshot_root(args.owner, authorized=True),
                    "hits": [
                        hit.to_payload() for hit in store.search(
                            args.owner, args.text, scope=args.scope,
                            limit=args.limit,
                            min_confidence_ppm=args.minimum_confidence_ppm,
                            authorized=True,
                            diversify=not args.no_diversity,
                        )
                    ],
                }
            elif args.command == "brief":
                output = store.build_brief(
                    args.owner, args.text, scope=args.scope,
                    max_hits=args.limit,
                    min_confidence_ppm=args.minimum_confidence_ppm,
                    min_independent_groups=args.minimum_independent_groups,
                    authorized=True,
                ).to_payload()
            elif args.command == "history":
                output = {
                    "schema": "skeleton.game_builder.reviewed_history.v1",
                    "owner": args.owner,
                    "source_id": args.source_id,
                    "revisions": [
                        item.to_payload() for item in store.history(
                            args.owner, args.source_id, authorized=True,
                        )
                    ],
                }
            elif args.command == "plan-recrawl":
                output = store.plan_recrawl(
                    args.owner, as_of=args.as_of, scope=args.scope,
                    max_age_seconds=args.max_age_seconds,
                    min_independent_groups=args.minimum_independent_groups,
                    min_confidence_ppm=args.minimum_confidence_ppm,
                    limit=args.limit, authorized=True,
                )
            elif args.command == "queue-recrawls":
                from .dragon_wisdom_pyramid import DragonWisdomPyramid
                output = DragonWisdomPyramid(store).enqueue_canonical_refreshes(
                    args.owner, now=args.at_epoch, authorized=True,
                    trusted_worker=True, max_age_seconds=args.max_age_seconds,
                    min_independent_groups=args.minimum_independent_groups,
                    min_confidence_ppm=args.minimum_confidence_ppm, limit=args.limit,
                )
            elif args.command == "pending-recrawls":
                from .dragon_wisdom_pyramid import DragonWisdomPyramid
                output = {
                    "owner": args.owner, "execution_authorized": False,
                    "orders": DragonWisdomPyramid(store).recrawl_queue(
                        args.owner, now=args.at_epoch, authorized=True,
                        limit=args.limit,
                    ),
                }
            elif args.command == "hoag-view":
                from .dragon_wisdom_pyramid import DragonWisdomPyramid
                output = DragonWisdomPyramid(store).hoag_view(
                    args.owner, now=args.at_epoch, authorized=True,
                    limit=args.limit,
                )
            elif args.command == "root":
                output = {
                    "schema": "skeleton.game_builder.reviewed_root.v1",
                    "owner": args.owner,
                    "root": store.snapshot_root(args.owner, authorized=True),
                }
            elif args.command == "erase-owner":
                if args.confirm_erasure != args.owner:
                    raise KnowledgeError("erasure confirmation must match owner")
                output = {
                    "schema": "skeleton.game_builder.reviewed_erasure.v1",
                    "owner": args.owner,
                    "deleted_revisions": store.erase_owner(args.owner, authorized=True),
                }
            else:
                raise KnowledgeError("unrecognized operator command")
    except (KnowledgeError, PermissionError, OSError, ValueError) as exc:
        # Do not include raw source content in error reporting.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(canonical_json(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MAX_IMPORT_BYTES", "build_parser", "main"]
