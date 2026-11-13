"""Regression tests for direct authenticated local studio readiness probes."""

import json
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler

from skeleton.app import studio_readiness


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps({"schema_version": "test.readiness.v1"}).encode()


class _Opener:
    def open(self, request, timeout):
        assert timeout == 1
        assert request.get_header("Authorization") == "Bearer private-token"
        return _Response()


class StudioDoctorProxyTests(unittest.TestCase):
    def test_local_bearer_probe_explicitly_disables_ambient_proxies(self):
        seen = []

        def capture(*handlers):
            seen.extend(handlers)
            return _Opener()

        with patch.object(studio_readiness, "build_opener", side_effect=capture):
            report = studio_readiness._server_snapshot(
                "http://127.0.0.1:8001", "private-token", 1,
                schema="test.readiness.v1",
            )
        self.assertTrue(report["observed"])
        self.assertTrue(any(isinstance(h, ProxyHandler) and h.proxies == {} for h in seen))
        self.assertTrue(any(isinstance(h, studio_readiness._NoRedirect) for h in seen))

    def test_remote_https_keeps_operator_proxy_policy(self):
        seen = []

        def capture(*handlers):
            seen.extend(handlers)
            return _Opener()

        with patch.object(studio_readiness, "build_opener", side_effect=capture):
            report = studio_readiness._server_snapshot(
                "https://example.org", "private-token", 1,
                schema="test.readiness.v1",
            )
        self.assertTrue(report["observed"])
        self.assertFalse(any(isinstance(h, ProxyHandler) for h in seen))

    def test_remote_http_rejects_bearer_before_transport(self):
        with patch.object(studio_readiness, "build_opener") as opener:
            with self.assertRaises(ValueError):
                studio_readiness._server_snapshot(
                    "http://example.org", "private-token", 1,
                )
            opener.assert_not_called()

    def test_redirect_handler_refuses_external_hop(self):
        handler = studio_readiness._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://example.org"))


if __name__ == "__main__":
    unittest.main()
