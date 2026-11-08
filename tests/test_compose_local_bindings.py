"""Fail-closed local host publishing contract for the canonical Compose app.

Run with: python -m unittest tests.test_compose_local_bindings
No Docker daemon, network, or credentials are required.
"""
from pathlib import Path
import re
import unittest

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
PORTS = {
    "skeleton": ("SKELETON_BIND_HOST", "SKELETON_PORT", "8010", "8001"),
    "backend": ("BACKEND_BIND_HOST", "BACKEND_PORT", "8001", "8001"),
    "frontend": ("FRONTEND_BIND_HOST", "FRONTEND_PORT", "3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
}


def published_ports(text: str) -> dict[str, str]:
    """Inspect service-level port bindings, not comments or environment URLs."""
    result = {}
    current = None
    in_ports = False
    for line in text.splitlines():
        service = re.match(r"^  ([a-z][a-z0-9_-]*):\s*$", line)
        if service:
            current, in_ports = service.group(1), False
        elif re.match(r"^    [a-z_]+:", line):
            in_ports = line.strip() == "ports:"
        elif in_ports and current and re.match(r'^      - "', line):
            result[current] = line.strip()[3:-1]
    return result


class ComposeLocalBindingsTests(unittest.TestCase):
    def test_default_app_services_are_loopback_only(self):
        ports = published_ports(COMPOSE.read_text(encoding="utf-8"))
        for service, (bind, host_port, default_port, container_port) in PORTS.items():
            with self.subTest(service=service):
                self.assertEqual(
                    ports[service],
                    f"${{{bind}:-127.0.0.1}}:${{{host_port}:-{default_port}}}:{container_port}",
                )

    def test_unbound_or_public_default_regression_is_rejected(self):
        original = COMPOSE.read_text(encoding="utf-8")
        for service, (bind, host_port, default_port, container_port) in PORTS.items():
            with self.subTest(service=service):
                original_line = f'"${{{bind}:-127.0.0.1}}:${{{host_port}:-{default_port}}}:{container_port}"'
                for replacement in (
                    f'"${{{host_port}:-{default_port}}}:{container_port}"',
                    f'"0.0.0.0:${{{host_port}:-{default_port}}}:{container_port}"',
                ):
                    mutated = original.replace(original_line, replacement)
                    self.assertNotEqual(mutated, original)
                    self.assertNotEqual(
                        published_ports(mutated)[service],
                        published_ports(original)[service],
                    )

    def test_setup_frontend_has_no_backend_or_engine_dependency(self):
        text = COMPOSE.read_text(encoding="utf-8")
        frontend = text.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("    depends_on:", frontend)
        self.assertIn("    networks:", frontend)


if __name__ == "__main__":
    unittest.main()
