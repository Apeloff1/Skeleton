from __future__ import annotations

import pytest

from skeleton.api.webhooks import (
    Subscription as ApiSubscription,
    WebhookDispatcher,
    WebhookError,
)
from skeleton.integrations.webhooks import WebhookSystem
from skeleton.security.outbound_url import validate_public_https_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://localhost/hook",
        "https://service.localhost/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://2130706433/hook",
        "https://[::1]/hook",
        "https://224.0.0.1/hook",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://user:password@example.com/hook",
        "https://internal/hook",
        "https://example.com/hook#fragment",
    ],
)
def test_outbound_url_policy_rejects_unsafe_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_https_url(url, purpose="webhook endpoint")


def test_outbound_url_policy_allows_public_https_path_and_query() -> None:
    url = "https://hooks.example.com/events?tenant=1"
    assert validate_public_https_url(url, purpose="webhook endpoint") == (
        url,
        "hooks.example.com",
    )


def test_integration_webhook_generates_unique_random_default_secrets() -> None:
    system = WebhookSystem()
    first = system.subscribe("build", "https://hooks.example.com/a")
    second = system.subscribe("build", "https://hooks.example.com/b")

    assert first.secret != second.secret
    assert first.secret != "whsec_default"
    assert len(first.secret) >= 32


def test_integration_webhook_rejects_private_endpoint() -> None:
    system = WebhookSystem()

    with pytest.raises(ValueError):
        system.subscribe("build", "https://127.0.0.1/hook", "s" * 32)


def test_api_dispatcher_rejects_private_endpoint() -> None:
    dispatcher = WebhookDispatcher()

    with pytest.raises(WebhookError, match="invalid webhook endpoint"):
        dispatcher.subscribe(
            ApiSubscription(
                endpoint="https://169.254.169.254/latest/meta-data",
                secret=b"x" * 32,
            )
        )


def test_api_dispatcher_rejects_weak_secret() -> None:
    dispatcher = WebhookDispatcher()

    with pytest.raises(WebhookError, match="at least 16 bytes"):
        dispatcher.subscribe(
            ApiSubscription(
                endpoint="https://hooks.example.com/events",
                secret=b"short",
            )
        )


def test_api_dispatcher_accepts_public_endpoint_and_dispatches() -> None:
    seen: list[tuple[str, dict]] = []
    dispatcher = WebhookDispatcher(
        sender=lambda url, payload: seen.append((url, payload))
    )
    dispatcher.subscribe(
        ApiSubscription(
            endpoint="https://hooks.example.com/events",
            secret=b"x" * 32,
            events=("build",),
        )
    )

    assert dispatcher.dispatch("build", {"ok": True}) == 1
    assert seen[0][0] == "https://hooks.example.com/events"
    assert len(seen[0][1]["sig"]) == 64
