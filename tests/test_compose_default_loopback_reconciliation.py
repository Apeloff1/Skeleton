"""Regression: local-first Compose deployment must not publish application APIs to all interfaces.

Source-only checks; no Docker daemon, network or device certification is implied.
Reconciles the intended protection from #4881/#4999/#5000 against the
current canonical Compose syntax (literal loopback rather than stale *_BIND_* knobs).
"""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
ENV_TEMPLATE = ROOT / ".env.example"

APP_PORTS = {
    "skeleton": '"127.0.0.1:${SKELETON_PORT:-8010}:8001"',
    "backend": '"127.0.0.1:${BACKEND_PORT:-8001}:8001"',
    "frontend": '"127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}"',
}


def published_service_line(compose: str, service: str) -> str:
    header = "  " + service + ":\n"
    before, found, after = compose.partition(header)
    if not found:
        raise AssertionError(f"missing service: {service}")
    service_lines = after.split("\n  ", 1)[0].splitlines()
    try:
        ports_index = service_lines.index("    ports:")
    except ValueError as exc:
        raise AssertionError(f"missing published ports: {service}") from exc
    if ports_index + 1 >= len(service_lines):
        raise AssertionError(f"missing port declaration: {service}")
    return service_lines[ports_index + 1].strip()


class ComposeDefaultLoopbackReconciliationTests(unittest.TestCase):
    def test_public_app_services_bind_only_loopback_by_default(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        for service, expected in APP_PORTS.items():
            with self.subTest(service=service):
                self.assertEqual(published_service_line(compose, service), "- " + expected)

    def test_public_binding_mutations_are_detected(self):
        original = COMPOSE.read_text(encoding="utf-8")
        for service, expected in APP_PORTS.items():
            with self.subTest(service=service):
                mutated = original.replace(expected, expected.replace("127.0.0.1:", "0.0.0.0:"), 1)
                self.assertNotEqual(mutated, original)
                self.assertNotEqual(
                    published_service_line(mutated, service),
                    published_service_line(original, service),
                )

    def test_browser_cors_tracks_selected_frontend_port(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        expected = (
            "CORS_ORIGINS=${CORS_ORIGINS:-"
            "http://localhost:${FRONTEND_PORT:-3000},"
            "http://127.0.0.1:${FRONTEND_PORT:-3000}}"
        )
        self.assertIn(expected, compose)
        template = ENV_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("\nCORS_ORIGINS=\n", template)
        self.assertNotIn("CORS_ORIGINS=*", template)

    def test_database_ports_also_remain_local(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:${MONGO_PORT:-27017}:27017"', compose)
        self.assertIn('"127.0.0.1:${CHROMA_PORT:-8000}:8000"', compose)


if __name__ == "__main__":
    unittest.main()
