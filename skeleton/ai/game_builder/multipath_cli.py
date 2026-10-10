"""Local, offline original-homebrew multipath inspection and level evolution.

This CLI takes only a user-selected bounded JSON tile map. It never crawls,
downloads, invokes a provider, accesses proprietary ROMs or signs a release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from .multipath_design import (
    MultipathError, RouteProblem, evaluate_level_challenge,
    evolve_challenge_level, pareto_hazard_routes, route_portfolio,
    solve_route, verify_route_proof,
)

_MAX_FILE_BYTES = 16_384
_SCHEMA = "skeleton.game_builder.multipath_cli.v1"


def _read_rows(path: Path) -> tuple[str, ...]:
    """Bind a local regular-file read to one stable inode and bounded snapshot."""
    fd = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= _MAX_FILE_BYTES:
            raise MultipathError("input must be a bounded regular file, not a link")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            fd = None
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise MultipathError("input changed during admission")
            raw = source.read(_MAX_FILE_BYTES + 1)
            after = os.fstat(source.fileno())
            current = path.lstat()
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) !=
                    (opened.st_dev, opened.st_ino)
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) !=
                    (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
                    or len(raw) != opened.st_size):
                raise MultipathError("input changed while reading")
    except (OSError, ValueError) as exc:
        if isinstance(exc, MultipathError):
            raise
        raise MultipathError("input is not a readable bounded regular file") from exc
    finally:
        if fd is not None:
            os.close(fd)
    if len(raw) > _MAX_FILE_BYTES:
        raise MultipathError("input byte budget exceeded")
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise MultipathError("ambiguous repeated JSON input field")
            result[key] = value
        return result

    try:
        data = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(
                MultipathError("nonfinite JSON input denied")),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MultipathError("invalid UTF-8 JSON grid") from exc
    if not isinstance(data, dict) or set(data) != {"rows"}:
        raise MultipathError("grid payload must contain only the rows field")
    if not isinstance(data["rows"], list):
        raise MultipathError("tile rows must be a JSON list")
    return tuple(data["rows"])


def _result(problem: RouteProblem, *, mode: str, portfolio_size: int,
            authorized: bool, min_loops: int, add_hazards: int,
            max_changes: int) -> dict[str, object]:
    if mode == "inspect":
        report = evaluate_level_challenge(problem, portfolio_size=portfolio_size)
        return {"schema": _SCHEMA, "status": "analyzed", "report": report}
    if mode == "solve":
        shortest = solve_route(problem)
        alternatives = route_portfolio(problem, max_routes=portfolio_size)
        for proof in alternatives:
            verify_route_proof(problem, proof)
        frontier = pareto_hazard_routes(problem)
        return {
            "schema": _SCHEMA, "status": "solved", "world_digest": problem.digest,
            "minimum_safe_moves": shortest.steps, "minimum_safe_actions": list(shortest.actions),
            "solutions": [
                {"actions": list(proof.actions), "steps": proof.steps,
                 "digest": proof.digest, "hazard_visits": proof.hazard_visits}
                for proof in alternatives
            ],
            "speed_risk_frontier": [
                {"steps": proof.steps, "hazard_visits": proof.hazard_visits,
                 "digest": proof.digest}
                for proof in frontier
            ],
            "native_binary_verified": False,
            "player_enjoyment_verified": False,
        }
    if mode == "evolve":
        if not authorized:
            raise PermissionError("explicit --authorize-edit required")
        evolved = evolve_challenge_level(
            problem, min_loops=min_loops, add_hazards=add_hazards,
            max_changes=max_changes, authorized=True,
        )
        return {
            "schema": _SCHEMA, "status": "edited_design_only",
            "original_digest": problem.digest, "result_digest": evolved.result.digest,
            "rows": list(evolved.result.rows),
            "edit_digests": [receipt.digest for receipt in evolved.edits],
            "design_receipt": evolved.digest, "challenge_report": evolved.dossier,
            "native_binary_verified": False, "release_authorized": False,
        }
    raise MultipathError("unknown CLI mode")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline original game-level route laboratory")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mode", choices=("inspect", "solve", "evolve"), default="inspect")
    parser.add_argument("--portfolio-size", type=int, default=4)
    parser.add_argument("--min-loops", type=int, default=1)
    parser.add_argument("--add-hazards", type=int, default=0)
    parser.add_argument("--max-changes", type=int, default=4)
    parser.add_argument("--authorize-edit", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = args.input.expanduser()
        problem = RouteProblem.from_rows(_read_rows(path))
        payload = _result(
            problem, mode=args.mode, portfolio_size=args.portfolio_size,
            authorized=args.authorize_edit, min_loops=args.min_loops,
            add_hazards=args.add_hazards, max_changes=args.max_changes,
        )
    except (MultipathError, PermissionError, ValueError, OSError) as exc:
        # Never print file bytes or raw untrusted exception values.
        print(json.dumps({"schema": _SCHEMA, "status": "rejected",
                          "reason": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
