"""Independent negative source checks for loopback-only consumer publication."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.test_compose_local_bindings import EXPECTED, violations

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class ConsumerComposeNetworkContract(unittest.TestCase):
    def test_storage_is_never_bound_to_all_interfaces(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        for service in ("mongo", "chroma"):
            with self.subTest(service=service):
                self.assertIn(f'"{EXPECTED[service]}"', raw)
                self.assertNotIn(f'0.0.0.0:${{{service.upper()}_PORT', raw)

    def test_internal_service_identities_and_healthy_dependencies_survive(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("http://skeleton:8001", raw)
        self.assertIn("condition: service_healthy", raw)
        self.assertEqual(violations(raw), [])

    def test_unsafe_public_binding_rewrite_is_rejected_for_every_service(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        for service, expected in EXPECTED.items():
            exposed = expected.replace("127.0.0.1:", "0.0.0.0:", 1)
            rewritten = raw.replace(f'"{expected}"', f'"{exposed}"')
            with self.subTest(service=service):
                self.assertNotEqual(rewritten, raw)
                self.assertTrue(violations(rewritten))

    def test_no_service_exposes_an_unchecked_unquoted_port(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertFalse(re.search(r'(?m)^      - (?:0[.]0[.]0[.]0:)?${(?:SKELETON|BACKEND|FRONTEND|MONGO|CHROMA)_PORT', raw))


if __name__ == "__main__":
    unittest.main()
