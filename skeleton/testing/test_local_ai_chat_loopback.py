"""End-to-end ephemeral IPv4 loopback HTTP transport acceptance.

Uses a real Python stdlib HTTP server but NO real Jeeves app, Mongo,
external network, trusted key, user credential or inference provider.
"""
from __future__ import annotations

import inspect

from scripts import qualify_local_ai_http_loopback as loopback


def test_real_localhost_synthetic_http_replay_and_hostile_denials():
    actual = loopback.exercise_loopback_http()
    assert actual["status"] == (
        "real_loopback_http_transport_exercised_not_real_jeeves"
    )
    assert actual["actual_localhost_tcp_server_executed"] is True
    assert actual["real_http_post_executed"] is True
    assert actual["one_post_only"] is True
    assert actual["canonical_replay_shape_checked"] is True
    for name in (
        "redirect_denied", "duplicate_json_denied",
        "oversized_response_denied", "non200_denied_without_body_leak",
        "unauthorized_bearer_denied",
    ):
        assert actual[name] is True
    for name in (
        "proxied_remote_provider_calls", "production_application_invoked",
        "real_jeeves_inference_executed", "real_user_database_mutated",
        "protected_chat_qualified", "release_qualified",
    ):
        assert actual[name] is False


def test_synthetic_http_server_is_explicitly_loopback_and_ephemeral():
    source = inspect.getsource(loopback.exercise_loopback_http)
    assert 'ThreadingHTTPServer(("127.0.0.1", 0), Handler)' in source
    assert "server.shutdown()" in source
    assert "server.server_close()" in source
    assert "worker.join(timeout=5)" in source
    assert "urlopen(" not in source
    assert "client.post(" not in source
    assert "subprocess.Popen(" not in source


def test_source_does_not_instantiate_any_model_or_database():
    source = inspect.getsource(loopback.exercise_loopback_http)
    for forbidden in (
        "MotorClient(", "MongoClient(", "OpenAI(", "anthropic.",
        "docker run", "docker compose", "subprocess.run(",
    ):
        assert forbidden not in source
