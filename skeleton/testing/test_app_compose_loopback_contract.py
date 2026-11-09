"""Regression contract for first-install host exposure (no Docker required)."""

from pathlib import Path
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
                lines = text.splitlines()
                start = lines.index("  " + service + ":")
                end = next((i for i in range(start + 1, len(lines))
                            if lines[i].startswith("  ") and not lines[i].startswith("    ")),
                           len(lines))
                section = "\n".join(lines[start:end])
                self.assertIn(
                    '      - "127.0.0.1:${' + port + ':-',
                    section,
                )

    def test_assembly_audit_preserves_loopback_and_selectable_container_port(self):
        checker = (ROOT / "scripts/check_app_assembly.py").read_text(encoding="utf-8")
        expected = '"127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}"'
        self.assertIn(expected, COMPOSE.read_text(encoding="utf-8"))
        self.assertIn(expected + "' in base", checker)
        self.assertNotIn('"' + "${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}" + '"' + "' in base", checker)

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
