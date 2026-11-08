"""Regression contract: consumer Compose must not publish unauthenticated ports to LAN.

This is a source-level policy check, not a Docker or Windows device test.
"""
from pathlib import Path
import re
import unittest


COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


class ConsumerLoopbackBindingsTest(unittest.TestCase):
    def test_public_service_ports_are_loopback_only(self):
        source = COMPOSE.read_text(encoding="utf-8")
        expected = {
            "skeleton": r'127\.0\.0\.1:\$\{SKELETON_PORT:-8010\}:8001',
            "backend": r'127\.0\.0\.1:\$\{BACKEND_PORT:-8001\}:8001',
            "frontend": r'127\.0\.0\.1:\$\{FRONTEND_PORT:-3000\}:\$\{FRONTEND_CONTAINER_PORT:-3000\}',
        }
        for service, pattern in expected.items():
            with self.subTest(service=service):
                self.assertEqual(len(re.findall(pattern, source)), 1)

    def test_no_wildcard_public_port_bindings(self):
        source = COMPOSE.read_text(encoding="utf-8")
        # Reject reintroduction of default 0.0.0.0 host bindings.
        for port in ("SKELETON_PORT", "BACKEND_PORT", "FRONTEND_PORT"):
            with self.subTest(port=port):
                self.assertNotRegex(source, r'(?m)^\s+-\s*["\']?\$\{' + port + r':-')

    def test_frontend_has_no_backend_health_dependency(self):
        source = COMPOSE.read_text(encoding="utf-8")
        frontend = source.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", frontend)


if __name__ == "__main__":
    unittest.main()
