"""Source-only Docker Compose admission tests for five bound consumer services.

These tests inspect the shipped Compose declaration, not a fake container or
host network. They prevent accidental public bind defaults and preserve setup
availability while retaining explicit operator port and origin overrides.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
EXPECTED = {
    "skeleton": '127.0.0.1:${SKELETON_PORT:-8010}:8001',
    "backend": '127.0.0.1:${BACKEND_PORT:-8001}:8001',
    "frontend": '127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}',
    "mongo": '127.0.0.1:${MONGO_PORT:-27017}:27017',
    "chroma": '127.0.0.1:${CHROMA_PORT:-8000}:8000',
}
CORS = ('CORS_ORIGINS=${CORS_ORIGINS:-'
        'http://localhost:${FRONTEND_PORT:-3000},'
        'http://127.0.0.1:${FRONTEND_PORT:-3000}}')


def published_ports(source: str) -> dict[str, list[str]]:
    """Inspect service-level ports, ignoring URLs and comments."""
    result: dict[str, list[str]] = {}
    current = None
    in_ports = False
    for line in source.splitlines():
        service = re.fullmatch(r"  ([a-z][a-z0-9_-]*):", line)
        if service:
            current = service.group(1)
            in_ports = False
            continue
        if current and re.match(r"^    [a-z_]+:", line):
            in_ports = line.strip() == "ports:"
            continue
        if in_ports and current and re.fullmatch(r'      - "([^"]+)"', line):
            result.setdefault(current, []).append(line.strip()[3:-1])
    return result


def violations(source: str) -> list[str]:
    actual = published_ports(source)
    return [f"{service}: unsafe or changed host publication"
            for service, expected in EXPECTED.items()
            if actual.get(service) != [expected]]


class LocalComposePortsTests(unittest.TestCase):
    def test_exact_loopback_for_all_host_published_services(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertEqual(violations(source), [])
        self.assertTrue(set(EXPECTED).issubset(published_ports(source)))

    def test_public_or_unqualified_mutations_are_detected(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for service, expected in EXPECTED.items():
            for mutant in (
                expected.replace("127.0.0.1:", "", 1),
                expected.replace("127.0.0.1:", "0.0.0.0:", 1),
                expected.replace("127.0.0.1:", "${HOST_BIND:-127.0.0.1}:", 1),
            ):
                with self.subTest(service=service, mutant=mutant):
                    modified = source.replace(f'"{expected}"', f'"{mutant}"', 1)
                    self.assertNotEqual(modified, source)
                    self.assertIn(
                        f"{service}: unsafe or changed host publication",
                        violations(modified),
                    )

    def test_frontend_setup_starts_without_healthy_backend_dependency(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("\n  frontend:\n", source)
        frontend = source.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("\n    depends_on:", frontend)
        self.assertIn("\n    networks:", frontend)

    def test_public_browser_urls_track_selected_published_ports(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn(CORS, source)
        self.assertIn(
            'EXPO_PUBLIC_BACKEND_URL=${EXPO_PUBLIC_BACKEND_URL:-http://localhost:${BACKEND_PORT:-8001}}',
            source,
        )
        self.assertIn(
            'EXPO_PUBLIC_SKELETON_URL=${EXPO_PUBLIC_SKELETON_URL:-http://localhost:${SKELETON_PORT:-8010}}',
            source,
        )

    def test_operator_cors_policy_can_override_without_exposing_bind_address(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('CORS_ORIGINS=${CORS_ORIGINS:-', source)
        for published in published_ports(source).values():
            for port in published:
                self.assertNotIn("_BIND_HOST", port)
                self.assertNotIn("_BIND_ADDRESS", port)
                self.assertTrue(port.startswith("127.0.0.1:"), port)


if __name__ == "__main__":
    unittest.main()
