"""Sales stay closed until runtime qualification and buyer delivery exist."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import pytest

from emergentintegrations.payments.stripe import checkout as stripe_facade
from routes import marketplace, playable_access
from backend.tests.test_playable_private_creation import project_boundary
from backend.tests.test_private_memory_boundary import memory_boundary


def test_new_sales_fail_closed_after_private_project_authorization(project_boundary, monkeypatch):
    client, headers, users, database = project_boundary
    game = {"playable_id": "owned-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a"}
    database.playables.rows.append(game)
    database.marketplace_listings.rows.append({**game, "active": True, "price_usd": 4.99})
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    def unexpected_checkout(*args, **kwargs):
        raise AssertionError("payment provider must not be contacted")
    monkeypatch.setattr(marketplace, "_checkout", unexpected_checkout)
    client.app.include_router(marketplace.router)
    before = {name: deepcopy(collection.rows) for name, collection in database.collections.items()}
    for path, payload in (
        ("/api/marketplace/list", {"playable_id": "owned-game", "price_usd": 4.99, "creator_id": "alice@example.test", "evaluation": {"verdict": "ship"}}),
        ("/api/marketplace/checkout", {"playable_id": "owned-game", "buyer_id": "alice@example.test", "origin_url": "https://example.test"}),
    ):
        response = client.post(path, headers=headers["alice"], json=payload)
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "marketplace_release_unavailable"
        assert "gameplay and buyer access" in response.json()["error"]
        assert client.post(path, json=payload).status_code == 401
        assert client.post(path, headers=headers["bob"], json=payload).status_code == 404
        users["alice@example.test"]["role"] = "viewer"
        assert client.post(path, headers=headers["alice"], json=payload).status_code == 403
        users["alice@example.test"]["role"] = "editor"
    assert {name: collection.rows for name, collection in database.collections.items()} == before
    assert all(not collection.writes for collection in database.collections.values())


def test_existing_listings_and_payment_status_remain_available(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    game = {"playable_id": "owned-game", "owner_id": "alice@example.test", "tenant_id": "tenant-a"}
    database.playables.rows.append({**game, "title": "Existing game"})
    database.marketplace_listings.rows.append({**game, "active": True, "price_usd": 4.99, "created_at": "2026-01-01"})
    database.payment_transactions.rows.append({**game, "session_id": "existing-session", "payment_status": "initiated"})
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    calls = []
    class FakeCheckout:
        async def get_checkout_status(self, session_id):
            calls.append(session_id)
            return SimpleNamespace(status="open", payment_status="unpaid", amount_total=499, currency="usd")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: FakeCheckout())
    client.app.include_router(marketplace.router)
    listing = client.get("/api/marketplace/listings", headers=headers["alice"])
    assert listing.status_code == 200, listing.text
    assert listing.json()["listings"][0]["title"] == "Existing game"
    response = client.get("/api/marketplace/checkout/status/existing-session", headers=headers["alice"])
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "unpaid"
    assert calls == ["existing-session"]
    assert client.get("/api/marketplace/checkout/status/existing-session", headers=headers["bob"]).json() == {"error": "unknown session"}
    assert calls == ["existing-session"]


def test_signed_completed_event_without_payment_status_does_not_imply_paid(monkeypatch):
    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return {"type": "checkout.session.completed", "data": {"object": {
                "object": "checkout.session", "id": "cs_existing",
            }}}

    monkeypatch.setattr(stripe_facade, "_stripe_module", lambda: SimpleNamespace(Webhook=Webhook))
    checkout = stripe_facade.StripeCheckout("key", "https://example.test/webhook", "secret")
    event = asyncio.run(checkout.handle_webhook(b"{}", "valid-signature"))
    assert event.session_id == "cs_existing"
    assert event.payment_status is None


@pytest.mark.parametrize("event_type,payment_status,finalizes", [
    ("checkout.session.completed", None, False),
    ("checkout.session.completed", "unpaid", False),
    ("checkout.session.async_payment_failed", "unpaid", False),
    ("checkout.session.expired", "paid", False),
    ("checkout.session.completed", "paid", True),
    ("checkout.session.async_payment_succeeded", "paid", True),
])
def test_webhook_settles_only_explicitly_paid_checkout_events(
    project_boundary, monkeypatch, event_type, payment_status, finalizes,
):
    client, headers, _, database = project_boundary
    identity = {"owner_id": "alice@example.test", "tenant_id": "tenant-a"}
    database.payment_transactions.rows.append({
        **identity, "session_id": "cs_existing", "payment_status": "initiated",
    })
    event = SimpleNamespace(session_id="cs_existing", payment_status=payment_status, event_type=event_type)
    checkout = SimpleNamespace(handle_webhook=AsyncMock(return_value=event))
    finalize = AsyncMock()
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: checkout)
    monkeypatch.setattr(marketplace, "_finalize_purchase", finalize)
    client.app.include_router(marketplace.router)

    response = client.post("/api/webhook/stripe", headers=headers["alice"], json={})
    assert response.status_code == 200, response.text
    assert response.json() == {"received": True}
    if finalizes:
        finalize.assert_awaited_once()
        assert database.payment_transactions.rows[0]["payment_status"] == "paid"
    else:
        finalize.assert_not_awaited()
        assert database.payment_transactions.writes == []
        assert database.payment_transactions.rows[0]["payment_status"] == "initiated"


def test_webhook_rejects_invalid_signature_without_acknowledging_it(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    checkout = SimpleNamespace(handle_webhook=AsyncMock(side_effect=ValueError("bad signature")))
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: checkout)
    client.app.include_router(marketplace.router)
    response = client.post("/api/webhook/stripe", headers=headers["alice"], json={})
    assert response.status_code == 400
    assert response.json() == {"received": False, "error": "webhook_rejected"}
    assert all(not collection.writes for collection in database.collections.values())
