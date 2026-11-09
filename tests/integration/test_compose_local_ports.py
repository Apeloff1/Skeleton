"""Static regression for local-only first-install API publication."""
from pathlib import Path
import unittest

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


class ComposeLocalPortsTests(unittest.TestCase):
    def test_api_ports_bind_loopback(self):
        config = COMPOSE.read_text(encoding="utf-8")
        for variable, default in (("SKELETON_PORT", 8010), ("BACKEND_PORT", 8001)):
            with self.subTest(variable=variable):
                expected = '127.0.0.1:' + '$' + '{' + variable + ':-' + str(default) + '}:8001'
                unsafe = '"' + '$' + '{' + variable + ':-' + str(default) + '}:8001"'
                self.assertIn(expected, config)
                self.assertNotIn(unsafe, config)

    def test_database_port_remains_local(self):
        config = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('127.0.0.1:' + '$' + '{MONGO_PORT:-27017}:27017', config)


if __name__ == "__main__":
    unittest.main()
