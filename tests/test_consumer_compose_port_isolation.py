"""Regression guard: default consumer Compose must not expose unauthenticated setup/API ports on LAN."""
from pathlib import Path
import re
import unittest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


class ConsumerPortIsolationTests(unittest.TestCase):
    def test_all_published_ports_bind_loopback(self):
        source = COMPOSE.read_text(encoding="utf-8")
        # Only inspect Compose port mapping entries, not URLs or internal health probes.
        ports = re.findall(r"""^\s+-\s+["']([^"']+:[^"']+)["']\s*$""", source, re.MULTILINE)
        self.assertGreaterEqual(len(ports), 5, "expected API, backend, frontend, Mongo and Chroma bindings")
        for port in ports:
            with self.subTest(port=port):
                self.assertTrue(port.startswith("127.0.0.1:"), f"public host port: {port}")

    def test_degraded_setup_is_not_gated_on_backend_health(self):
        source = COMPOSE.read_text(encoding="utf-8")
        frontend = source.split("\n  frontend:", 1)[1].split("\n  mongo:", 1)[0]
        self.assertNotIn("depends_on:", frontend)
        self.assertIn("EXPO_PUBLIC_BACKEND_URL", frontend)


if __name__ == "__main__":
    unittest.main()
