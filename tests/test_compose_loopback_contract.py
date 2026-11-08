"""Regression contract for consumer Compose network exposure.

Run: python -m unittest discover -s tests -p 'test_compose_loopback_contract.py'
This checks the real deployment source; it does not claim a Docker/device run.
"""
from pathlib import Path
import re
import unittest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


class ConsumerComposeLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COMPOSE.read_text(encoding="utf-8")

    def test_application_ports_are_loopback_by_default(self):
        expected = {
            "SKELETON": ("8010", "8001"),
            "BACKEND": ("8001", "8001"),
            "FRONTEND": ("3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
        }
        for service, (host_port, container_port) in expected.items():
            with self.subTest(service=service):
                bind = "${" + service + "_BIND_ADDRESS:-127.0.0.1}"
                port = "${" + service + "_PORT:-" + host_port + "}"
                publication = '"' + bind + ":" + port + ":" + container_port + '"'
                self.assertIn(publication, self.source)

    def test_database_remains_local_only(self):
        self.assertIn('"127.0.0.1:${MONGO_PORT:-27017}:27017"', self.source)

    def test_service_names_remain_internal(self):
        self.assertIn("http://skeleton:8001", self.source)
        self.assertIn("condition: service_healthy", self.source)

    def test_no_unqualified_public_application_port(self):
        for match in re.finditer(r'^\s+-\s+"([^"]+)"\s*$', self.source, re.M):
            entry = match.group(1)
            if "PORT:-" in entry and "MONGO_PORT" not in entry:
                self.assertTrue(
                    entry.startswith("${") and "_BIND_ADDRESS:-127.0.0.1}" in entry,
                    f"unexpected published application port: {entry}",
                )


if __name__ == "__main__":
    unittest.main()
