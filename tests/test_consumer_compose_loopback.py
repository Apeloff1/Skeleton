"""Regression contracts for safe default Compose publication on first install.

These source assertions do not replace a real Docker/Windows acceptance test.
"""
from pathlib import Path
import re
import unittest


COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


class ConsumerPortBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COMPOSE.read_text(encoding="utf-8")

    def test_application_services_default_to_loopback(self):
        for service, port in (
            ("skeleton", "SKELETON_PORT"),
            ("backend", "BACKEND_PORT"),
            ("frontend", "FRONTEND_PORT"),
        ):
            section = re.search(
                rf"(?m)^  {service}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
                self.source, re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(section, service)
            self.assertRegex(
                section.group(1),
                rf'(?m)^\s+- "\$\{{APP_BIND_HOST:-127\.0\.0\.1\}}:\$\{{{port}:-\d+\}}:',
            )

    def test_database_ports_remain_loopback(self):
        for service, port in (("mongo", "MONGO_PORT"), ("chroma", "CHROMA_PORT")):
            self.assertIn(f'127.0.0.1:${{{port}:-', self.source)

    def test_frontend_has_no_backend_health_dependency(self):
        section = self.source.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", section)

    def test_no_default_wildcard_bind(self):
        self.assertNotIn("APP_BIND_HOST:-0.0.0.0", self.source)


if __name__ == "__main__":
    unittest.main()
