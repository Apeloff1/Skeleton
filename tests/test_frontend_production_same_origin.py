"""Regression contract for the production browser's first-install API ingress.

The default exported bundle must not embed the build host's loopback ports.
The web client resolves an unset endpoint to the browser origin, where nginx
routes the application and engine APIs independently.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductionSameOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        cls.resolver = (ROOT / "frontend" / "src" / "utils" / "apiBase.ts").read_text(encoding="utf-8")
        cls.nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    def test_production_defaults_do_not_pin_visitor_loopback(self):
        production = self.docker.split("# Stage 3: Web Build", 1)[1]
        for name in ("EXPO_PUBLIC_BACKEND_URL", "EXPO_PUBLIC_SKELETON_URL"):
            match = re.search(r"^ARG " + name + r"=(.*)$", production, re.MULTILINE)
            self.assertIsNotNone(match, name)
            self.assertEqual(match.group(1).strip(), "", name)
            self.assertIn(name + "=$" + name, production)

    def test_explicit_override_and_browser_fallback_remain_wired(self):
        self.assertIn("if (explicit) return explicit;", self.resolver)
        self.assertIn("const sameOrigin = browserOrigin();", self.resolver)
        self.assertIn("if (sameOrigin) return sameOrigin;", self.resolver)
        self.assertIn("Platform.OS !== 'web'", self.resolver)
        self.assertIn("if (!origin || origin.startsWith('file:')) return '';", self.resolver)

    def test_ingress_separates_backend_and_engine(self):
        self.assertRegex(self.nginx, r"location \\^~ /api/ \\{\\s*proxy_pass http://application_backend;")
        self.assertRegex(self.nginx, r"location \\^~ /api/v1/ \\{\\s*proxy_pass http://application_engine;")
        self.assertIn("location = /healthz", self.nginx)

    def test_no_fallback_to_visitor_loopback_in_production_stage(self):
        production = self.docker.split("# Stage 3: Web Build", 1)[1]
        self.assertNotRegex(production, r"ARG EXPO_PUBLIC_(?:BACKEND|SKELETON)_URL=http://localhost:")


if __name__ == "__main__":
    unittest.main()
