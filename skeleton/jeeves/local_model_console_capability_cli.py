#!/usr/bin/env python3
"""CLI for the local-model console emulator capability.

Usage:
  python -m skeleton.ai.agents.jeeves.local_model_console_capability list
  python -m skeleton.ai.agents.jeeves.local_model_console_capability summary
  python -m skeleton.ai.agents.jeeves.local_model_console_capability plan --hardware snes
"""

from __future__ import annotations

import argparse
import json
import sys

from skeleton.ai.agents.jeeves.local_model_console_capability import make_capability


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local model console emulator capability")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all declared cores")
    sub.add_parser("summary", help="Fleet summary for model context")
    p_plan = sub.add_parser("plan", help="Generate a governed session plan")
    p_plan.add_argument("--hardware", default=None)
    p_plan.add_argument("--max-steps", type=int, default=1000)

    sub.add_parser("validate", help="Fleet sanity check")
    p_rec = sub.add_parser("recommend", help="Recommend cores for a learning goal")
    p_rec.add_argument("--goal", default="general")

    args = parser.parse_args(argv)
    cap = make_capability()

    if args.cmd == "list":
        print(json.dumps(cap.list_cores(), indent=2))
    elif args.cmd == "summary":
        print(json.dumps(cap.fleet_summary(), indent=2))
    elif args.cmd == "plan":
        print(json.dumps(cap.plan_session(args.hardware, args.max_steps), indent=2))
    elif args.cmd == "validate":
        print(json.dumps(cap.validate_fleet(), indent=2))
    elif args.cmd == "card":
        print(cap.model_card())
    elif args.cmd == "choices":
        print(json.dumps(cap.emulator_console_choices(), indent=2))
    elif args.cmd == "matrix":
        print(json.dumps(cap.qualification_matrix(), indent=2))
    elif args.cmd == "recommend":
        print(json.dumps(cap.recommend_for_learning(args.goal), indent=2))
    elif args.cmd == "status":
        st = cap.get_status(args.core)
        print(json.dumps({
            "name": st.name,
            "hardware_targets": list(st.hardware_targets),
            "installed": st.installed,
            "qualified": st.qualified,
            "notes": st.notes,
        }, indent=2))
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
