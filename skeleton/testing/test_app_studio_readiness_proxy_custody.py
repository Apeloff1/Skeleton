"""Hermetic regression for credential-bearing studio readiness HTTP admission.

A local first-install diagnostics request must not inherit a proxy from the
operator's shell, must not follow redirects, and must never echo the bearer.
This tests the real opener construction without contacting a network service.
"""
from __future__ import annotations

import os
import unittest
from email.message import Message

import pytest
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
                response.status = 200
                response.geturl.return_value = base + "/api/game-studio-health"
                response.headers = Message()
                response.headers["Content-Type"] = "application/json"
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
            response.status = 200
            response.geturl.return_value = "http://127.0.0.1:8307/api/game-studio-health"
            response.headers = Message()
            response.headers["Content-Type"] = "application/json"
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



_BASE = "http://127.0.0.1:8307"
_PATH = "/api/game-studio-health"
_TOKEN = "private-readiness-token-0123456789"
_SCHEMA = "skeleton.game.studio_readiness.v1"


def _response(body, *, status=200, url=_BASE + _PATH, types=("application/json",)):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = status
    response.geturl.return_value = url
    response.headers = Message()
    for value in types:
        response.headers["Content-Type"] = value
    response.read.return_value = body
    return response


@pytest.mark.parametrize("base", [
    _BASE + "?", _BASE + "#", _BASE + "/unexpected", _BASE + "\n",
    "http://local%68ost:8307", "http://localhost:0", "http://localhost:bad",
    "http://[::1", "http://localhost:8307\\",
])
def test_ambiguous_readiness_origin_never_dispatches(base):
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        with pytest.raises(ValueError):
            _server_snapshot(base, _TOKEN, 0.2)
        factory.assert_not_called()


@pytest.mark.parametrize("endpoint", ["//evil.invalid", "/../health", "/api/x?secret=1",
                                     "/api/x#frag", "/api/%2e%2e", "api/x", "/api//x"])
def test_unreviewed_endpoint_never_dispatches(endpoint):
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        with pytest.raises(ValueError):
            _server_snapshot(_BASE, _TOKEN, 0.2, endpoint=endpoint)
        factory.assert_not_called()


@pytest.mark.parametrize("status,url,types", [
    (None, _BASE + _PATH, ("application/json",)),
    (True, _BASE + _PATH, ("application/json",)),
    ("200", _BASE + _PATH, ("application/json",)),
    (302, _BASE + _PATH, ("application/json",)),
    (503, _BASE + _PATH, ("application/json",)),
    (200, _BASE + "/login", ("application/json",)),
    (200, None, ("application/json",)),
    (200, _BASE + _PATH, ()),
    (200, _BASE + _PATH, ("text/html",)),
    (200, _BASE + _PATH, ("application/json", "application/json")),
])
def test_invalid_transport_metadata_is_refused_before_body(status, url, types):
    response = _response(b"{}", status=status, url=url, types=types)
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        factory.return_value.open.return_value = response
        result = _server_snapshot(_BASE, _TOKEN, 0.2)
    assert result == {"observed": False, "code": "server_inventory_protocol_invalid"}
    response.read.assert_not_called()


@pytest.mark.parametrize("body", [
    b'{"schema_version":"skeleton.game.studio_readiness.v1","status":"ready","status":"blocked"}',
    b'{"schema_version":"skeleton.game.studio_readiness.v1","nested":{"ok":true,"ok":false}}',
    b'{"schema_version":"skeleton.game.studio_readiness.v1","score":1e999}',
    b'{"schema_version":"skeleton.game.studio_readiness.v1","score":NaN}',
    b'{"schema_version":"skeleton.game.studio_readiness.v1","score":Infinity}',
    b'{"schema_version":"skeleton.game.studio_readiness.v1","bad":"\xff"}',
])
def test_readiness_rejects_ambiguous_or_nonfinite_json(body):
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        factory.return_value.open.return_value = _response(body)
        assert _server_snapshot(_BASE, _TOKEN, 0.2) == {
            "observed": False, "code": "server_inventory_protocol_invalid",
        }


@pytest.mark.parametrize("as_key", [False, True])
def test_json_escaped_bearer_reflection_is_rejected(as_key):
    escaped = b"\\u0070" + _TOKEN[1:].encode()
    member = b'"' + escaped + b'":true' if as_key else b'"value":"' + escaped + b'"'
    raw = b'{"schema_version":"' + _SCHEMA.encode() + b'","nested":{' + member + b'}}'
    assert _TOKEN.encode() not in raw
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        factory.return_value.open.return_value = _response(raw)
        assert _server_snapshot(_BASE, _TOKEN, 0.2) == {
            "observed": False, "code": "server_inventory_returned_credential",
        }


def test_external_https_diagnostics_are_direct_even_with_proxy_environment():
    base = "https://operator.example.invalid"
    with patch.dict(os.environ, StudioReadinessProxyCustodyTests._PROXIES), \
            patch("skeleton.app.studio_readiness.build_opener") as factory:
        factory.return_value.open.return_value = _response(
            b'{"schema_version":"skeleton.game.studio_readiness.v1"}',
            url=base + _PATH,
        )
        assert _server_snapshot(base, _TOKEN, 0.2)["observed"]
        assert factory.call_args.args[0].proxies == {}


@pytest.mark.parametrize("token", ["short", "invalid secret with space", "a"*8193, "é"*20])
def test_invalid_bearer_is_rejected_before_transport(token):
    with patch("skeleton.app.studio_readiness.build_opener") as factory:
        with pytest.raises(ValueError):
            _server_snapshot(_BASE, token, 0.2)
        factory.assert_not_called()
