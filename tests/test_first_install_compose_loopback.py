"""Regression contract for local-only first-install Compose exposure.

This source-only test does not replace Docker or Windows acceptance.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class FirstInstallLoopbackTests(unittest.TestCase):
    def test_first_install_host_ports_are_loopback_only(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for variable, container_port in (
            ("SKELETON_PORT", "8001"),
            ("BACKEND_PORT", "8001"),
            ("FRONTEND_PORT", "${FRONTEND_CONTAINER_PORT:-3000}"),
            ("MONGO_PORT", "27017"),
            ("CHROMA_PORT", "8000"),
        ):
            expression = re.compile(
                r'^\s*-\s*"127\.0\.0\.1:\$\{' + variable +
                r':-[^}]+\}:' + re.escape(container_port) + r'"\s*$',
                re.MULTILINE,
            )
            self.assertRegex(text, expression, variable)

    def test_frontend_has_no_backend_health_dependency(self):
        text = COMPOSE.read_text(encoding="utf-8")
        frontend = text.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", frontend)
        self.assertIn("EXPO_PUBLIC_BACKEND_URL", frontend)

    def test_backend_still_requires_guarded_engine(self):
        text = COMPOSE.read_text(encoding="utf-8")
        backend = text.split("\n  backend:\n", 1)[1].split("\n  frontend:\n", 1)[0]
        self.assertRegex(backend, r"skeleton:\s*\n\s*condition: service_healthy")


if __name__ == "__main__":
    unittest.main()
