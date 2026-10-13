"""Contract tests for repeated creator playthrough checks."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from skeleton.forge.walk_cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, parse_walk_args, run_walk


def sample(era: str, *, ok: bool = True):
    return {
        "passed": ok, "label": era, "extracted": ok, "t": 2.0,
        "hops": 3, "cores": 1, "required_cores": 1,
        "mode": "ideal", "notes": ["walk could not extract"] if not ok else [],
        "_steps_full": [], "heat_peak": 0.0, "vents": 0,
    }


class RepeatedWalkTests(unittest.TestCase):
    def test_repeat_parser_strict_and_bounded(self):
        self.assertEqual(parse_walk_args(["-n", "3"]).repeats, 3)
        self.assertEqual(parse_walk_args(["--repeat", "100"]).repeats, 100)
        for argv in (["-n", "0"], ["-n", "101"], ["-n", "abc"], ["-n"],
                     ["--repeat", "2.0"], ["--repeet", "3"]):
            self.assertEqual(run_walk(argv, out=lambda _: None), EXIT_USAGE)

    def test_repeat_uses_distinct_reproducible_seeds(self):
        lines = []
        with patch("skeleton.forge.walk_cli.walk_once",
                   side_effect=lambda era, **kwargs: sample(era)) as walker:
            result = run_walk(["-n", "3", "--seed", "campaign", "--json"], out=lines.append)
        self.assertEqual(result, EXIT_OK)
        self.assertEqual([c.kwargs["seed"] for c in walker.call_args_list],
                         ["campaign:000", "campaign:001", "campaign:002"])
        report = json.loads(lines[0])
        self.assertEqual(report["repeats"], 3)
        self.assertEqual(report["passed"], 3)
        self.assertEqual(len(report["walks"]), 3)

    def test_any_failed_attempt_fails_entire_run(self):
        attempts = iter([sample("a"), sample("a", ok=False), sample("a")])
        with patch("skeleton.forge.walk_cli.walk_once",
                   side_effect=lambda *a, **k: next(attempts)):
            result = run_walk(["-n", "3"], out=lambda _: None)
        self.assertEqual(result, EXIT_FAIL)

    def test_all_eras_repeat_is_cartesian_product(self):
        seen = []
        def walker(era, **kwargs):
            seen.append((era, kwargs["seed"]))
            return sample(era)
        with patch("skeleton.forge.eras.list_eras", return_value=["soulslike", "cozy_wholesome"]):
            with patch("skeleton.forge.walk_cli.walk_once", side_effect=walker):
                result = run_walk(["--all-eras", "-n", "2"], out=lambda _: None)
        self.assertEqual(result, EXIT_OK)
        self.assertEqual(seen, [
            ("soulslike", "walk:000"), ("soulslike", "walk:001"),
            ("cozy_wholesome", "walk:000"), ("cozy_wholesome", "walk:001"),
        ])

    def test_single_walk_does_not_mutate_historical_seed_behavior(self):
        with patch("skeleton.forge.walk_cli.walk_once",
                   return_value=sample("extraction_now")) as walker:
            self.assertEqual(run_walk(["--seed", "one"], out=lambda _: None), EXIT_OK)
        self.assertEqual(walker.call_args.kwargs["seed"], "one")


if __name__ == "__main__":
    unittest.main()
