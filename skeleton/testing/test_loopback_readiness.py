"""Loopback readiness contract regression tests; no device qualification."""
import unittest
from unittest.mock import patch
from io import BytesIO
from skeleton.install.loopback_readiness import loopback_probe

class Response:
    status = 200
    headers = type("Headers", (), {"get_content_type": lambda self: "application/json"})()
    def __init__(self, payload):
        self.stream = BytesIO(payload)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.stream.read(n)

class LoopbackReadinessTests(unittest.TestCase):
    def test_reject_external_and_credential_urls(self):
        for url in ("http://example.org:80/health", "http://localhost:80/health",
                    "http://127.0.0.1:80/redirect", "https://127.0.0.1:80/health",
                    "http://user:secret@127.0.0.1:80/health",
                    "http://127.0.0.1:80/health?token=abc"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                loopback_probe("backend", url)

    def test_ready_requires_exact_identity(self):
        probe = loopback_probe("backend", "http://127.0.0.1:8000/health")
        for body, expected in [
            (b'{"service":"backend","ready":true}', True),
            (b'{"service":"jeeves","ready":true}', False),
            (b'{"service":"backend","ready":1}', False),
            (b'{"service":"backend","ready":false}', False),
            (b'not json', False),
            (b'x' * 4097, False),
        ]:
            with self.subTest(body=body[:40]), patch(
                "skeleton.install.loopback_readiness.build_opener"
            ) as factory:
                factory.return_value.open.return_value = Response(body)
                self.assertEqual(probe(), expected)

    def test_ai_requires_guard_model_and_reviewer(self):
        probe = loopback_probe("local_ai", "http://127.0.0.1:8000/health")
        for guard, model, reviewer, expected in [
            (True, True, True, True), (True, True, False, False),
            (True, False, True, False), (1, True, True, False),
        ]:
            payload = __import__("json").dumps(dict(service="local_ai", ready=True,
                guard_active=guard, model_bound=model, reviewer_active=reviewer)).encode()
            with patch("skeleton.install.loopback_readiness.build_opener") as factory:
                factory.return_value.open.return_value = Response(payload)
                self.assertEqual(probe(), expected)

    def test_unreachable_fails_closed(self):
        probe = loopback_probe("backend", "http://127.0.0.1:8000/health")
        with patch("skeleton.install.loopback_readiness.build_opener") as factory:
            factory.return_value.open.side_effect = OSError("offline")
            self.assertFalse(probe())

if __name__ == "__main__":
    unittest.main()
