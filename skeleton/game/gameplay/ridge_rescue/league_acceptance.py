"""Earned two-entrant original rescue league: gameplay -> ranking -> replay export."""
from __future__ import annotations

from pathlib import Path

from .acceptance import acceptance_actions
from .custody import export_run
from .io import read_bounded
from .league import open_league, submit_run, verify_league, export_league, verify_league_export, parse_league
from .schema import parse_world

SOURCE = Path(__file__).with_name("cinder_ridge_league.json")


def run_acceptance() -> dict:
    """Actually play two different earned endings and publish their verified ranking."""
    league = parse_league(read_bounded(SOURCE, 128_000))
    world = parse_world(league["world"])
    board = open_league(league)
    for handle, ending in (("ridge-protectors", "protect"), ("ridge-salvagers", "salvage")):
        bundle = export_run(world, acceptance_actions(ending))
        board = submit_run(board, expected_head=board["head"], handle=handle, run=bundle)
    checked = verify_league(board)
    if checked["entries"] != 2 or checked["champion"] != "ridge-protectors":
        raise ValueError("earned league standings did not match canonical replay")
    if [entry["status"] for entry in checked["ranking"]] != ["won:protect", "won:salvage"]:
        raise ValueError("league accepted an unexpected ending")
    portable = export_league(board)
    if verify_league_export(portable)["head"] != checked["head"]:
        raise ValueError("portable league replay failed round-trip")
    return portable


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from .io import write_new
    parser = argparse.ArgumentParser(prog="ridge-league-acceptance")
    parser.add_argument("--output", help="create-only offline league export")
    args = parser.parse_args(argv)
    try:
        result = run_acceptance()
        if args.output:
            write_new(args.output, result, 1_000_000)
        else:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"ridge-league-acceptance: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
