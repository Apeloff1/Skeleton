"""Regression contract: consumer Compose ports are private unless opted in.

This is source-level admission, not proof of a running Docker/Windows host.
"""
from pathlib import Path
import re
import unittest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


class ConsumerComposeBindingTests(unittest.TestCase):
    def test_first_install_app_ports_are_loopback_only(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for service, port, target in (
            ("SKELETON", "8010", "8001"),
            ("BACKEND", "8001", "8001"),
            ("FRONTEND", "3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
        ):
            with self.subTest(service=service):
                expected = f'"${{{service}_BIND_HOST:-127.0.0.1}}:${{{service}_PORT:-{port}}}:{target}"'
                self.assertIn(expected, source)
                self.assertNotIn(f'"${{{service}_PORT:-{port}}}:{target}"', source)

    def test_internal_services_keep_private_network_and_auth(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("SKL_ENGINE_SERVICE_TOKEN=${SKL_ENGINE_SERVICE_TOKEN:?", source)
        self.assertIn("JWT_SECRET=${JWT_SECRET:?", source)
        self.assertIn('"127.0.0.1:${MONGO_PORT:-27017}:27017"', source)
        self.assertIn('"127.0.0.1:${CHROMA_PORT:-8000}:8000"', source)
        self.assertIn("condition: service_healthy", source)

    def test_no_wildcard_bind_default_for_consumer_services(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for service in ("SKELETON", "BACKEND", "FRONTEND"):
            self.assertNotRegex(source, rf"\$\{{{service}_BIND_HOST:-(?:0\.0\.0\.0|::)\}}")


if __name__ == "__main__":
    unittest.main()
