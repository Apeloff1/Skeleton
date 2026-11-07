"""Regression contract for first-install host exposure (no Docker required)."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


class ConsumerLoopbackComposeTests(unittest.TestCase):
    def test_public_http_services_are_loopback_only(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for service, port in (
            ("skeleton", "SKELETON_PORT"),
            ("backend", "BACKEND_PORT"),
            ("frontend", "FRONTEND_PORT"),
        ):
            with self.subTest(service=service):
                section = re.search(
                    rf"(?ms)^  {service}:\\n(.*?)(?=^  [a-z][a-z0-9_-]*:|^networks:|\\Z)",
                    text,
                )
                self.assertIsNotNone(section)
                self.assertRegex(
                    section.group(1),
                    rf'(?m)^      - "127\\.0\\.0\\.1:\\$\\{{{port}:-[0-9]+\\}}:',
                )

    def test_mongo_and_chroma_remain_loopback(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for port in ("MONGO_PORT", "CHROMA_PORT"):
            self.assertIn("127.0.0.1:${" + port + ":-", text)

    def test_frontend_has_no_backend_health_dependency(self):
        text = COMPOSE.read_text(encoding="utf-8")
        frontend = text.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", frontend)


if __name__ == "__main__":
    unittest.main()
