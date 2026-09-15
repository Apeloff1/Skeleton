"""Regression tests for fail-closed Gate route-prefix matching."""

from __future__ import annotations

import unittest

from skeleton.api.middleware import GatePolicy


class TestGatePolicyBoundaries(unittest.TestCase):
    def test_open_routes_match_exact_path_and_slash_children(self):
        policy = GatePolicy(open_prefixes=("/health", "/docs", "/"), domains=())

        self.assertTrue(policy.is_open_route("/"))
        self.assertTrue(policy.is_open_route("/health"))
        self.assertTrue(policy.is_open_route("/health/live"))
        self.assertTrue(policy.is_open_route("/docs"))
        self.assertTrue(policy.is_open_route("/docs/oauth2-redirect"))

    def test_open_routes_do_not_match_lookalike_prefixes(self):
        policy = GatePolicy(open_prefixes=("/health", "/api/v1/metrics", "/cockpit"), domains=())

        for path in (
            "/healthcheck",
            "/health-extended",
            "/api/v1/metrics-export",
            "/api/v1/metrics2",
            "/cockpit-admin",
            "/cockpit2",
        ):
            with self.subTest(path=path):
                self.assertFalse(policy.is_open_route(path))

    def test_domain_routes_match_exact_path_and_slash_children(self):
        policy = GatePolicy(
            open_prefixes=(),
            domains=(("/api/v1/jeeves", "jeeves"), ("/api/v1/swarm", "swarm")),
        )

        self.assertEqual(policy.required_domain("/api/v1/jeeves"), "jeeves")
        self.assertEqual(policy.required_domain("/api/v1/jeeves/session"), "jeeves")
        self.assertEqual(policy.required_domain("/api/v1/swarm/tasks/123"), "swarm")

    def test_unwritten_lookalike_routes_remain_unmapped(self):
        policy = GatePolicy(
            open_prefixes=(),
            domains=(("/api/v1/jeeves", "jeeves"), ("/api/v1/swarm", "swarm")),
        )

        for path in (
            "/api/v1/jeeves-admin",
            "/api/v1/jeeves2",
            "/api/v1/swarm-debug",
            "/api/v1/swarm2/tasks",
        ):
            with self.subTest(path=path):
                self.assertIsNone(policy.required_domain(path))

    def test_longest_real_segment_prefix_still_wins(self):
        policy = GatePolicy(
            open_prefixes=(),
            domains=(
                ("/api/v1/swarm", "swarm"),
                ("/api/v1/swarm/operator", "operator"),
            ),
        )

        self.assertEqual(policy.required_domain("/api/v1/swarm/operator"), "operator")
        self.assertEqual(policy.required_domain("/api/v1/swarm/operator/status"), "operator")
        self.assertEqual(policy.required_domain("/api/v1/swarm/tasks"), "swarm")
        self.assertEqual(policy.required_domain("/api/v1/swarm/operatorial"), "swarm")


if __name__ == "__main__":
    unittest.main(verbosity=2)
