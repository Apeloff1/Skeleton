"""Regression contract: default consumer Compose listeners stay on loopback.

This is a static source-policy test, not Docker or Windows device evidence.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class ConsumerPortFenceTests(unittest.TestCase):
    def test_default_http_listeners_are_loopback_only(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for name, port in (("SKELETON_PORT", "8010"), ("BACKEND_PORT", "8001"), ("FRONTEND_PORT", "3000")):
            with self.subTest(name=name):
                self.assertIn(f'127.0.0.1:${{{name}:-{port}}}:', source)
                self.assertNotIn(f'"${{{name}:-{port}}}:', source)

    def test_no_wildcard_or_unqualified_published_ports(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- ") or "PORT:-" not in stripped or ":" not in stripped:
                continue
            if stripped.startswith("- \"") and re.search(r'\$\{[A-Z_]+PORT:-\d+\}', stripped):
                self.assertTrue(stripped.startswith('- "127.0.0.1:'), stripped)

    def test_frontend_has_no_transitive_backend_start_dependency(self):
        source = COMPOSE.read_text(encoding="utf-8")
        frontend = source.split("\n  frontend:", 1)[1].split("\n  mongo:", 1)[0]
        self.assertNotIn("depends_on:", frontend)


if __name__ == "__main__":
    unittest.main()
