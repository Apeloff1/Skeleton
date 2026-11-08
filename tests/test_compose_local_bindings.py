"""Regression for local-first Compose published-port exposure.

Run: python -m unittest tests.test_compose_local_bindings
This is a source contract test, not a Docker or Windows device test.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class ComposeLocalBindingsTest(unittest.TestCase):
    def test_default_user_facing_services_bind_loopback(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for service, host, target in (
            ("skeleton", "SKELETON_PORT:-8010", "8001"),
            ("backend", "BACKEND_PORT:-8001", "8001"),
            ("frontend", "FRONTEND_PORT:-3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
        ):
            with self.subTest(service=service):
                block = re.search(
                    rf"(?m)^  {service}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|^networks:)",
                    text, re.DOTALL | re.MULTILINE,
                )
                self.assertIsNotNone(block)
                self.assertIn(f'127.0.0.1:${{{host}}}:{target}', block.group(1))
                self.assertNotRegex(block.group(1), r'(?m)^\s+- "\$\{(?:SKELETON_PORT|BACKEND_PORT|FRONTEND_PORT)')


if __name__ == "__main__":
    unittest.main()
