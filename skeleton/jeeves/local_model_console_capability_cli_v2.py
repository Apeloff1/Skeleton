#!/usr/bin/env python3
"""CLI v2 for the expanded local-model console emulator capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Prefer the v2 module next to this file
sys.path.insert(0, str(Path(__file__).parent))
from skeleton.ai.agents.jeeves.local_model_console_capability_v2 import make_capability_v2  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local model console emulator capability v2")
    parser.add_argument("--db", default=None, help="Path to fleet_database_v2.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    sub.add_parser("summary")
    sub.add_parser("validate")
    sub.add_parser("card")
    sub.add_parser("choices")
    sub.add_parser("matrix")
    sub.add_parser("csv")
    sub.add_parser("markdown")
    sub.add_parser("eras")
    sub.add_parser("categories")
    sub.add_parser("curriculum")

    p_get = sub.add_parser("get")
    p_get.add_argument("core")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")

    p_filter = sub.add_parser("filter")
    p_filter.add_argument("--era")
    p_filter.add_argument("--category")
    p_filter.add_argument("--hardware")
    p_filter.add_argument("--accuracy")
    p_filter.add_argument("--bios", type=lambda x: x.lower() == "true")

    p_rec = sub.add_parser("recommend")
    p_rec.add_argument("--goal", default="general")
    p_rec.add_argument("--limit", type=int, default=5)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--hardware")
    p_plan.add_argument("--max-steps", type=int, default=1000)
    p_plan.add_argument("--accuracy", action="store_true")

    args = parser.parse_args(argv)
    cap = make_capability_v2(args.db)

    if args.cmd == "list":
        print(json.dumps(cap.list_cores(), indent=2))
    elif args.cmd == "summary":
        print(json.dumps(cap.fleet_summary(), indent=2))
    elif args.cmd == "validate":
        print(json.dumps(cap.validate_fleet(), indent=2))
    elif args.cmd == "card":
        print(cap.model_card("detailed"))
    elif args.cmd == "choices":
        print(json.dumps(cap.emulator_console_choices(), indent=2))
    elif args.cmd == "matrix":
        print(json.dumps(cap.qualification_matrix(), indent=2))
    elif args.cmd == "csv":
        print(cap.to_csv())
    elif args.cmd == "markdown":
        print(cap.to_markdown_table())
    elif args.cmd == "eras":
        print(json.dumps(cap.by_era(), indent=2))
    elif args.cmd == "categories":
        print(json.dumps(cap.by_category(), indent=2))
    elif args.cmd == "curriculum":
        print(json.dumps(cap.curriculum(), indent=2))
    elif args.cmd == "get":
        rec = cap.get(args.core)
        print(json.dumps(rec.__dict__ if rec else {"error": "not_found"}, indent=2, default=str))
    elif args.cmd == "search":
        print(json.dumps([r.__dict__ for r in cap.search(args.query)], indent=2, default=str))
    elif args.cmd == "filter":
        recs = cap.filter(args.era, args.category, args.bios, args.accuracy, args.hardware)
        print(json.dumps([r.__dict__ for r in recs], indent=2, default=str))
    elif args.cmd == "recommend":
        print(json.dumps(cap.recommend_for_learning(args.goal, args.limit), indent=2))
    elif args.cmd == "plan":
        print(json.dumps(cap.plan_session(args.hardware, args.max_steps, args.accuracy), indent=2))
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
