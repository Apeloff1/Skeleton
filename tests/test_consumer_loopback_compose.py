"""Regression: default Compose must not expose consumer services on the LAN.

This checks the shipped Compose source without requiring Docker or credentials.
It does not certify a running Windows/WSL2 installation.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class ConsumerLoopbackPortsTest(unittest.TestCase):
    def test_public_ports_are_loopback_only(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for service, variable, default, target in (
            ("skeleton", "SKELETON_PORT", "8010", "8001"),
            ("backend", "BACKEND_PORT", "8001", "8001"),
            ("frontend", "FRONTEND_PORT", "3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
        ):
            with self.subTest(service=service):
                expression = "${" + variable + ":-" + default + "}"
                expected = '"127.0.0.1:' + expression + ":" + target + '"'
                self.assertIn(expected, text)
                self.assertNotIn('"' + expression + ":" + target + '"', text)

    def test_optional_unauthed_services_are_not_public(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:${MONGO_PORT:-27017}:27017"', text)
        self.assertIn('"127.0.0.1:${CHROMA_PORT:-8000}:8000"', text)

    def test_frontend_stays_independent_of_backend_health(self):
        text = COMPOSE.read_text(encoding="utf-8")
        frontend = text.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotRegex(frontend, r"(?m)^    depends_on:")
        self.assertIn("EXPO_PUBLIC_BACKEND_URL", frontend)


if __name__ == "__main__":
    unittest.main()
