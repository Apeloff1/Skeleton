"""Hermetic regression for credential-bearing studio readiness HTTP admission.

A local first-install diagnostics request must not inherit a proxy from the
operator's shell, must not follow redirects, and must never echo the bearer.
This tests the real opener construction without contacting a network service.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import ProxyHandler

from skeleton.app.studio_readiness import _NoRedirect, _server_snapshot


class StudioReadinessProxyCustodyTests(unittest.TestCase):
    _TOKEN = "private-readiness-token-0123456789"
    _PROXIES = {
        "HTTP_PROXY": "http://unsafe-proxy.invalid:17831",
        "HTTPS_PROXY": "http://unsafe-proxy.invalid:17832",
        "ALL_PROXY": "http://unsafe-proxy.invalid:17833",
        "NO_PROXY": "",
        "http_proxy": "http://unsafe-proxy.invalid:17834",
        "https_proxy": "http://unsafe-proxy.invalid:17835",
        "all_proxy": "http://unsafe-proxy.invalid:17836",
        "no_proxy": "",
    }

    @patch.dict(os.environ, _PROXIES)
    def test_authenticated_loopback_uses_explicit_empty_proxy_handler(self) -> None:
        for base in (
            "http://127.0.0.1:8307",
            "http://localhost:8308",
            "https://[::1]:8309",
        ):
            with self.subTest(base=base), patch(
                "skeleton.app.studio_readiness.build_opener"
            ) as factory:
                response = MagicMock()
                response.__enter__.return_value = response
                response.read.return_value = (
                    b'{"schema_version":"skeleton.game.studio_readiness.v1",'
                    b'"status":"ready"}'
                )
                factory.return_value.open.return_value = response
                report = _server_snapshot(base, self._TOKEN, 0.2)

                self.assertTrue(report["observed"])
                self.assertEqual(report["report"]["status"], "ready")
                factory.assert_called_once()
                handlers = factory.call_args.args
                self.assertEqual(len(handlers), 2)
                self.assertIsInstance(handlers[0], ProxyHandler)
                self.assertEqual(handlers[0].proxies, {})
                self.assertIsInstance(handlers[1], _NoRedirect)

                factory.return_value.open.assert_called_once()
                request = factory.return_value.open.call_args.args[0]
                self.assertEqual(
                    request.get_header("Authorization"),
                    "Bearer " + self._TOKEN,
                )
                self.assertEqual(request.full_url, base + "/api/game-studio-health")

    @patch.dict(os.environ, _PROXIES)
    def test_untrusted_http_and_url_credentials_denied_before_transport(self) -> None:
        for base in (
            "http://example.invalid:8300",
            "http://operator:secret@127.0.0.1:8300",
            "http://127.0.0.1:8300/?token=exposed",
            "http://127.0.0.1:8300/#frag",
        ):
            with self.subTest(base=base), patch(
                "skeleton.app.studio_readiness.build_opener"
            ) as factory:
                with self.assertRaises(ValueError):
                    _server_snapshot(base, self._TOKEN, 0.2)
                factory.assert_not_called()

    @patch.dict(os.environ, _PROXIES)
    def test_bearer_reflection_is_denied_without_outputting_secret(self) -> None:
        with patch("skeleton.app.studio_readiness.build_opener") as factory:
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = (
                b'{"schema_version":"skeleton.game.studio_readiness.v1",'
                + self._TOKEN.encode("ascii")
                + b'":"injected"}'
            )
            factory.return_value.open.return_value = response
            result = _server_snapshot("http://127.0.0.1:8307", self._TOKEN, 0.2)
            self.assertEqual(
                result,
                {"observed": False, "code": "server_inventory_returned_credential"},
            )
            self.assertNotIn(self._TOKEN, str(result))
            self.assertEqual(factory.call_args.args[0].proxies, {})


if __name__ == "__main__":
    unittest.main()
