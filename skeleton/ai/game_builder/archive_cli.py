"""Local operator commands for a rights-safe game hardware history archive.

    python -m skeleton.ai.game_builder.archive_cli summary
    python -m skeleton.ai.game_builder.archive_cli lineage nintendo_famicom nintendo_switch
    python -m skeleton.ai.game_builder.archive_cli import-mame /local/mame-listxml.xml --review-file ./review.jsonl

Nothing is downloaded, emulated or run from imported XML.
"""
from __future__ import annotations

import argparse
import json

from .archive_import import import_mame_listxml, export_review_queue
from .evolution_archive import (
    archive_coverage_report, default_evolution_archive,
    plan_evolution_campaign,
)
from .platform_registry import default_registry
from .port_planner import HomebrewSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Homebrew gaming history and evolution archive")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="Curated records, dated lineage and unsatisfied archive evidence")
    lineage = sub.add_parser("lineage", help="View dated succession chain")
    lineage.add_argument("source")
    lineage.add_argument("destination")
    lineage.add_argument("--reverse", action="store_true")
    ingest = sub.add_parser("import-mame", help="Parse ONLY machine metadata from local MAME -listxml")
    ingest.add_argument("xml_path")
    ingest.add_argument("--review-file", default=None)
    ingest.add_argument("--review-limit", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.command == "summary":
        result = {
            "platform_registry": default_registry().summary(),
            "dated_evolution": default_evolution_archive().summary(),
            "coverage": archive_coverage_report(),
        }
    elif args.command == "lineage":
        archive = default_evolution_archive()
        path = archive.progress(args.source, args.destination, reverse=args.reverse)
        result = {
            "source_platform": args.source,
            "destination_platform": args.destination,
            "reverse": args.reverse,
            "transitions": [
                {
                    "platform_id": n.platform_id,
                    "year": n.year,
                    "historical_signal_hypotheses": n.design_signals,
                    "individual_primary_source_verified": False,
                } for n in path
            ],
            "native_binary_verified": False,
            "commercial_game_assets_imported": False,
        }
    else:
        inventory = import_mame_listxml(args.xml_path)
        result = inventory.summary()
        if args.review_file is not None:
            written = export_review_queue(
                inventory, args.review_file, limit=args.review_limit, authorized=True,
            )
            result["review_file"] = str(written)
            result["review_rows"] = len(inventory.review_queue(limit=args.review_limit))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
