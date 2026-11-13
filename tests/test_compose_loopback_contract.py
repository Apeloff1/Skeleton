"""Independent negative source checks for loopback-only consumer publication."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

EXPECTED = {
    "skeleton": '127.0.0.1:${SKELETON_PORT:-8010}:8001',
    "backend": '127.0.0.1:${BACKEND_PORT:-8001}:8001',
    "frontend": '127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}',
    "mongo": '127.0.0.1:${MONGO_PORT:-27017}:27017',
    "chroma": '127.0.0.1:${CHROMA_PORT:-8000}:8000',
}


def violations(source: str) -> list[str]:
    """Independently ensure one exact host publication per governed service."""
    return [name for name, expected in EXPECTED.items()
            if source.count(f'"{expected}"') != 1]

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class ConsumerComposeNetworkContract(unittest.TestCase):
    def test_storage_is_never_bound_to_all_interfaces(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        for service in ("mongo", "chroma"):
            with self.subTest(service=service):
                self.assertIn(f'"{EXPECTED[service]}"', raw)
                self.assertNotIn(f'0.0.0.0:${{{service.upper()}_PORT', raw)

    def test_internal_service_identities_and_healthy_dependencies_survive(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("http://skeleton:8001", raw)
        self.assertIn("condition: service_healthy", raw)
        self.assertEqual(violations(raw), [])

    def test_unsafe_public_binding_rewrite_is_rejected_for_every_service(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        for service, expected in EXPECTED.items():
            exposed = expected.replace("127.0.0.1:", "0.0.0.0:", 1)
            rewritten = raw.replace(f'"{expected}"', f'"{exposed}"')
            with self.subTest(service=service):
                self.assertNotEqual(rewritten, raw)
                self.assertTrue(violations(rewritten))

    def test_no_service_exposes_an_unchecked_unquoted_port(self):
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertFalse(re.search(r'(?m)^      - (?:0[.]0[.]0[.]0:)?${(?:SKELETON|BACKEND|FRONTEND|MONGO|CHROMA)_PORT', raw))


if __name__ == "__main__":
    unittest.main()
