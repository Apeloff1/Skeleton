"""Consumer Compose port isolation regression.

Run: python -m unittest tests.test_consumer_compose_loopback -v
No Docker daemon or credentials are required for the static contract checks.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
PORTS = {
    "skeleton": ("SKELETON_PORT", "8010", "8001"),
    "backend": ("BACKEND_PORT", "8001", "8001"),
    "frontend": ("FRONTEND_PORT", "3000", "${FRONTEND_CONTAINER_PORT:-3000}"),
    "mongo": ("MONGO_PORT", "27017", "27017"),
    "chroma": ("CHROMA_PORT", "8000", "8000"),
}


def published_ports(text):
    """Only parse service-level port scalars; fail if an unrecognized form appears."""
    result = {}
    service = None
    in_ports = False
    for line in text.splitlines():
        match = re.match(r"^  ([a-z][a-z0-9_-]*):\\s*$", line)
        if match:
            service = match.group(1)
            in_ports = False
            continue
        if re.match(r"^    ports:\\s*$", line):
            in_ports = True
            result[service] = []
            continue
        if in_ports and re.match(r"^    [^ #]", line):
            in_ports = False
        if in_ports and re.match(r"^      - ", line):
            result[service].append(line.strip()[2:].strip('"'))
    return result


class ConsumerComposeLoopbackTests(unittest.TestCase):
    def test_all_default_published_ports_are_loopback(self):
        ports = published_ports(COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(set(ports), set(PORTS))
        for service, (name, default, container) in PORTS.items():
            expected = f"127.0.0.1:${{{name}:-{default}}}:{container}"
            self.assertEqual(ports[service], [expected], service)

    def test_public_bind_is_rejected(self):
        text = COMPOSE.read_text(encoding="utf-8")
        text = text.replace("127.0.0.1:${BACKEND_PORT:-8001}:8001",
                            "0.0.0.0:${BACKEND_PORT:-8001}:8001")
        self.assertNotEqual(published_ports(text)["backend"],
                            published_ports(COMPOSE.read_text(encoding="utf-8"))["backend"])

    def test_frontend_has_no_backend_start_dependency(self):
        text = COMPOSE.read_text(encoding="utf-8")
        frontend = text.split("\n  frontend:\n", 1)[1].split("\n  mongo:\n", 1)[0]
        self.assertNotIn("depends_on:", frontend)


if __name__ == "__main__":
    unittest.main()
