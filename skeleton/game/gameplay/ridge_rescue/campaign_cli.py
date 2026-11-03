"""Command-line campaign play, replay verification and create-only save export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .campaign import (CampaignError, open_campaign, verify_campaign,
                       step_campaign, retry_campaign, export_campaign, verify_export)
from .engine import available_actions
from .io import read_bounded, write_new
from .render import render_map

DEMO = Path(__file__).with_name("cinder_ridge_campaign.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-rescue-campaign")
    parser.add_argument("command", choices=("open", "inspect", "step", "retry", "verify", "export", "interactive"))
    parser.add_argument("--source", help="source campaign JSON; default is bundled original campaign")
    parser.add_argument("--session", help="previous session JSON for inspect, step, retry, export, interactive")
    parser.add_argument("--bundle", help="portable export JSON for verify")
    parser.add_argument("--action", help="canonical JSON action for step")
    parser.add_argument("--expected-head", help="optimistic session revision for step or retry")
    parser.add_argument("--output", help="create-only output JSON; never overwrites")
    args = parser.parse_args(argv)
    try:
        if args.command == "open":
            report = open_campaign(read_bounded(args.source or DEMO, 96_000))
        elif args.command == "verify":
            if not args.bundle:
                raise CampaignError("--bundle required")
            report = verify_export(read_bounded(args.bundle, 1_000_000))
            report = {"valid": True, "index": report["index"], "status": report["status"], "head": report["head"]}
        else:
            if not args.session:
                raise CampaignError("--session required")
            session = json.loads(read_bounded(args.session, 1_000_000))
            if args.command == "step":
                if not args.action or not args.expected_head:
                    raise CampaignError("--action and --expected-head required")
                report = step_campaign(session, json.loads(args.action), expected_head=args.expected_head)
            elif args.command == "retry":
                if not args.expected_head:
                    raise CampaignError("--expected-head required")
                report = retry_campaign(session, expected_head=args.expected_head)
            elif args.command == "export":
                report = export_campaign(session)
            elif args.command == "interactive":
                report = session
                while True:
                    verified = verify_campaign(report)
                    if verified["status"] != "playing":
                        break
                    world = verified["campaign"]["episodes"][verified["index"]]["world"]
                    from .schema import parse_world
                    print(render_map(parse_world(world), verified["state"]))
                    for index, action in enumerate(verified["actions"]):
                        print(f"{index}: {json.dumps(action, sort_keys=True)}")
                    selected = input("action index (q to quit)> ").strip()
                    if selected == "q":
                        break
                    if not selected.isdigit() or not 0 <= int(selected) < len(verified["actions"]):
                        print("invalid choice")
                        continue
                    report = step_campaign(report, verified["actions"][int(selected)], expected_head=verified["head"])
            else:
                verified = verify_campaign(session)
                report = {"valid": True, "index": verified["index"], "status": verified["status"],
                          "head": verified["head"], "actions": verified["actions"],
                          "retries": verified["session"]["retries"],
                          "episode_count": len(verified["campaign"]["episodes"])}
        if args.output:
            write_new(args.output, report, 1_000_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError, EOFError) as exc:
        parser.exit(2, f"ridge-rescue-campaign: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
