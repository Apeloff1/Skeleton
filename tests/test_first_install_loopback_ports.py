"""Regression contract: first-install host listeners must not expose unauthenticated setup or APIs."""
from pathlib import Path
import re
import unittest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
SERVICES = ("skeleton", "backend", "frontend", "mongo", "chroma")


class FirstInstallLoopbackTests(unittest.TestCase):
    def test_every_published_port_is_loopback_only(self):
        source = COMPOSE.read_text(encoding="utf-8")
        # Match Compose short-syntax host bindings, including interpolated ports.
        bindings = re.findall(r'^\s+- "(?P<binding>[^"]+:[^"]+)"\s*$', source, re.M)
        self.assertEqual(len(bindings), len(SERVICES), "Unexpected or missing published port")
        for binding in bindings:
            with self.subTest(binding=binding):
                self.assertTrue(binding.startswith("127.0.0.1:"), binding)
                self.assertNotIn("0.0.0.0:", binding)

    def test_setup_frontend_has_no_backend_health_dependency(self):
        source = COMPOSE.read_text(encoding="utf-8")
        frontend = source.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", frontend)
        self.assertIn("127.0.0.1:${FRONTEND_PORT:-3000}", frontend)


if __name__ == "__main__":
    unittest.main()
