"""Offline designer CLI for the existing combat-design simulation owner.

Consumes an explicit bounded JSON encounter, emits a seed-cohort balance
matrix. Does not execute game source, download assets or apply recommendations.
Run: python -m scripts.balance_combat_encounter --input encounter.json --seeds 32
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from skeleton.simulation.game.combat_design import (
    AttackTelegraph, TelegraphChannel, ThreatTier, evaluate_encounter_design,
)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate input field")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("non-finite input field")


def load_encounter(path: str | Path) -> dict:
    target = Path(path)
    observed = target.lstat()
    if not stat.S_ISREG(observed.st_mode) or not 1 <= observed.st_size <= 65536:
        raise ValueError("encounter must be a bounded regular JSON file")
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (observed.st_dev, observed.st_ino, observed.st_size):
            raise ValueError("encounter identity changed during open")
        raw = stream.read(65537)
        if len(raw) != opened.st_size or os.fstat(stream.fileno()).st_size != opened.st_size:
            raise ValueError("encounter changed during read")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    if not isinstance(doc, dict) or set(doc) != {"schema", "enemy_hp", "player_max_hp", "player_dps", "rotation"}:
        raise ValueError("invalid encounter fields")
    if doc.pop("schema") != "combat.encounter_input.v1":
        raise ValueError("unsupported encounter schema")
    rotation = doc["rotation"]
    if not isinstance(rotation, list) or not 1 <= len(rotation) <= 64:
        raise ValueError("invalid attack rotation")
    attacks = []
    fields = {"name", "tier", "windup_ms", "active_ms", "recovery_ms", "channels", "damage_fraction"}
    for record in rotation:
        if not isinstance(record, dict) or not fields <= set(record) or set(record) - fields - {"escape_distance_m", "persistent_zone"}:
            raise ValueError("invalid attack fields")
        channels = record["channels"]
        if not isinstance(channels, list) or not 1 <= len(channels) <= 5 or len(set(channels)) != len(channels):
            raise ValueError("invalid telegraph channels")
        attacks.append(AttackTelegraph(**{
            **record, "tier": ThreatTier(record["tier"]),
            "channels": frozenset(TelegraphChannel(c) for c in channels),
        }))
    doc["rotation"] = attacks
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--deadline-ms", type=int, default=120000)
    args = parser.parse_args(argv)
    try:
        report = evaluate_encounter_design(
            **load_encounter(args.input), n_seeds=args.seeds, max_time_ms=args.deadline_ms,
        )
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        print(json.dumps({"error": "combat_design_input_rejected", "reason": type(exc).__name__}))
        return 1
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
