"""Regression for the default first-install Compose host exposure boundary.

These source-level checks intentionally do not certify a running Docker host.
A real Windows/WSL2 device must separately confirm bound sockets and firewall.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
EXPECTED = {
    "skeleton": "127.0.0.1:${SKELETON_PORT:-8010}:8001",
    "backend": "127.0.0.1:${BACKEND_PORT:-8001}:8001",
    "frontend": "127.0.0.1:${FRONTEND_PORT:-3000}:${FRONTEND_CONTAINER_PORT:-3000}",
    "mongo": "127.0.0.1:${MONGO_PORT:-27017}:27017",
    "chroma": "127.0.0.1:${CHROMA_PORT:-8000}:8000",
}

def service_port_lines(source: str, service: str) -> list[str]:
    # Scope to the service's two-space-indented Compose block. Avoid
    # mistaking comments, environment URLs or a sibling's ports for a bind.
    match = re.search(r"(?m)^  " + re.escape(service) + r":\s*\n(.*?)(?=^  [a-z][\w-]*:\s*$|^networks:\s*$|\Z)", source, re.S | re.M)
    if match is None:
        raise AssertionError(f"missing Compose service: {service}")
    lines = match.group(1).splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "ports:" and line.startswith("    ")), None)
    if start is None:
        raise AssertionError(f"missing published ports: {service}")
    result = []
    for line in lines[start + 1:]:
        if not line.startswith("      - "):
            break
        result.append(line.strip()[2:].strip().strip('"').strip("'"))
    return result

class FirstInstallLoopbackTests(unittest.TestCase):
    def test_all_published_ports_loopback_only(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for service, expected in EXPECTED.items():
            with self.subTest(service=service):
                self.assertEqual(service_port_lines(source, service), [expected])

    def test_no_wildcard_or_implicit_host_bind(self):
        source = COMPOSE.read_text(encoding="utf-8")
        for service in EXPECTED:
            for binding in service_port_lines(source, service):
                self.assertTrue(binding.startswith("127.0.0.1:"), (service, binding))
                self.assertNotIn("0.0.0.0:", binding)

    def test_negative_regression_wildcard_is_rejected(self):
        source = COMPOSE.read_text(encoding="utf-8")
        bad = source.replace('"127.0.0.1:${BACKEND_PORT:-8001}:8001"', '"${BACKEND_PORT:-8001}:8001"')
        self.assertNotEqual(service_port_lines(bad, "backend"), [EXPECTED["backend"]])

    def test_restart_source_is_stable(self):
        # No ephemeral port selection: compose parsing across restarts must
        # preserve the same deterministic host bindings.
        first = COMPOSE.read_text(encoding="utf-8")
        second = COMPOSE.read_text(encoding="utf-8")
        self.assertEqual({s: service_port_lines(first, s) for s in EXPECTED},
                         {s: service_port_lines(second, s) for s in EXPECTED})

if __name__ == "__main__":
    unittest.main()
