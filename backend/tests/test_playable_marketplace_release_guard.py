"""Sales stay closed until runtime qualification and buyer delivery exist."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import pytest

from emergentintegrations.payments.stripe import checkout as stripe_facade
from routes import creator_economy, marketplace, playable_access
from backend.tests.test_playable_private_creation import project_boundary
from backend.tests.test_private_memory_boundary import memory_boundary


def _sale_metadata():
    return {"source": "marketplace", "playable_id": "owned-game", "buyer_id": "alice@example.test"}


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
    database.payment_transactions.rows.append({**game, "session_id": "existing-session", "payment_status": "initiated", "buyer_id": "alice@example.test", "metadata": _sale_metadata()})
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


def test_verified_checkout_event_extracts_amount_and_currency(monkeypatch):
    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            return {"type": "checkout.session.completed", "data": {"object": {
                "object": "checkout.session", "id": "cs_existing", "payment_status": "paid",
                "amount_total": 499, "currency": "usd",
            }}}
    monkeypatch.setattr(stripe_facade, "_stripe_module", lambda: SimpleNamespace(Webhook=Webhook))
    event = asyncio.run(stripe_facade.StripeCheckout("key", "https://example.test", "secret").handle_webhook(b"{}", "sig"))
    assert (event.amount_total, event.currency, event.payment_status) == (499, "usd", "paid")


def test_checkout_status_does_not_coerce_boolean_to_cents(monkeypatch):
    class Session:
        @staticmethod
        def retrieve(*args, **kwargs):
            return SimpleNamespace(status="complete", payment_status="paid", amount_total=True, currency="usd")
    monkeypatch.setattr(stripe_facade, "_stripe_module", lambda: SimpleNamespace(checkout=SimpleNamespace(Session=Session)))
    status = asyncio.run(stripe_facade.StripeCheckout("key", "https://example.test").get_checkout_status("cs_existing"))
    assert status.amount_total is None


def test_stripe_signature_failure_is_distinct_from_sdk_outage(monkeypatch):
    class InvalidSignature(Exception):
        pass

    class Webhook:
        error = InvalidSignature("signature mismatch")

        @staticmethod
        def construct_event(payload, signature, secret):
            raise Webhook.error

    monkeypatch.setattr(stripe_facade, "_stripe_module", lambda: SimpleNamespace(
        Webhook=Webhook, SignatureVerificationError=InvalidSignature,
    ))
    checkout = stripe_facade.StripeCheckout("key", "https://example.test/webhook", "secret")
    with pytest.raises(ValueError, match="webhook verification failed"):
        asyncio.run(checkout.handle_webhook(b"{}", "bad-signature"))
    Webhook.error = RuntimeError("SDK unavailable")
    with pytest.raises(RuntimeError, match="SDK unavailable"):
        asyncio.run(checkout.handle_webhook(b"{}", "signature"))


@pytest.mark.parametrize("amount,provider_cents,provider_currency,matched", [
    (4.99, 499, "USD", True), (4.99, 498, "usd", False),
    (4.99, 500, "usd", False), (4.99, None, "usd", False),
    (4.99, True, "usd", False), (4.99, 499, None, False),
    (4.99, 499, "eur", False), (None, 499, "usd", False),
    (True, 100, "usd", False), (float("nan"), 499, "usd", False),
])
def test_paid_amount_requires_exact_persisted_usd_value(amount, provider_cents, provider_currency, matched):
    assert stripe_facade.paid_amount_matches(
        {"amount": amount, "currency": "usd"}, provider_cents, provider_currency,
    ) is matched


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
    database.playables.rows.append({**identity, "playable_id": "owned-game"})
    database.payment_transactions.rows.append({
        **identity, "session_id": "cs_existing", "payment_status": "initiated", "amount": 4.99, "currency": "usd",
        "playable_id": "owned-game", "buyer_id": "alice@example.test", "metadata": _sale_metadata(),
    })
    event = SimpleNamespace(session_id="cs_existing", payment_status=payment_status, event_type=event_type,
                            amount_total=499, currency="usd")
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


@pytest.mark.parametrize("route", ["marketplace", "premium"])
def test_paid_status_with_wrong_amount_is_not_recorded_or_granted(project_boundary, monkeypatch, route):
    client, headers, _, database = project_boundary
    database.payment_transactions.rows.append({
        "owner_id": "alice@example.test", "tenant_id": "tenant-a", "session_id": "cs_existing",
        "payment_status": "initiated", "amount": 4.99, "currency": "usd",
        "buyer_id": "alice@example.test",
        "playable_id": "owned-game",
        "metadata": (_sale_metadata() if route == "marketplace" else {
            "source": "premium", "plan": "monthly", "days": "30", "visitor_id": "alice@example.test",
        }),
    })
    status = SimpleNamespace(status="complete", payment_status="paid", amount_total=500, currency="usd")
    checkout = SimpleNamespace(get_checkout_status=AsyncMock(return_value=status))
    module = marketplace if route == "marketplace" else creator_economy
    monkeypatch.setattr(module, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(module, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(module, "_checkout", lambda *_: checkout)
    client.app.include_router(module.router)
    path = "/api/marketplace/checkout/status/cs_existing" if route == "marketplace" else "/api/premium/status/session/cs_existing"
    response = client.get(path, headers=headers["alice"])
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "payment_details_mismatch"
    assert database.payment_transactions.writes == []
    assert database.payment_transactions.rows[0]["payment_status"] == "initiated"


def test_paid_webhook_with_mismatched_amount_remains_retryable(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    database.payment_transactions.rows.append({
        "owner_id": "alice@example.test", "tenant_id": "tenant-a", "session_id": "cs_existing",
        "payment_status": "initiated", "amount": 4.99, "currency": "usd", "playable_id": "owned-game",
        "buyer_id": "alice@example.test", "metadata": _sale_metadata(),
    })
    event = SimpleNamespace(session_id="cs_existing", payment_status="paid", event_type="checkout.session.completed",
                            amount_total=500, currency="usd")
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: SimpleNamespace(handle_webhook=AsyncMock(return_value=event)))
    finalize = AsyncMock()
    monkeypatch.setattr(marketplace, "_finalize_purchase", finalize)
    client.app.include_router(marketplace.router)
    response = client.post("/api/webhook/stripe", headers=headers["alice"], json={})
    assert response.status_code == 503
    assert response.json()["error"] == "payment_details_unreconciled"
    assert database.payment_transactions.writes == []
    finalize.assert_not_awaited()


def test_marketplace_session_cannot_grant_premium(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    database.payment_transactions.rows.append({
        "owner_id": "alice@example.test", "tenant_id": "tenant-a", "session_id": "cs_game",
        "payment_status": "initiated", "amount": 4.99, "currency": "usd",
        "buyer_id": "alice@example.test", "metadata": {"source": "marketplace"},
    })
    checkout = SimpleNamespace(get_checkout_status=AsyncMock())
    monkeypatch.setattr(creator_economy, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(creator_economy, "_checkout", lambda *_: checkout)
    client.app.include_router(creator_economy.router)
    response = client.get("/api/premium/status/session/cs_game", headers=headers["alice"])
    assert response.status_code == 409
    assert response.json()["error"] == "payment_source_mismatch"
    checkout.get_checkout_status.assert_not_awaited()
    assert database.payment_transactions.writes == []


@pytest.mark.parametrize("route", ["marketplace", "premium"])
@pytest.mark.parametrize("payment_status,stored_status", [("paid", "initiated"), ("unpaid", "paid")])
def test_matching_poll_settles_or_preserves_paid_status(project_boundary, monkeypatch, route, payment_status, stored_status):
    client, headers, _, database = project_boundary
    metadata = (_sale_metadata() if route == "marketplace" else {
        "source": "premium", "plan": "monthly", "days": "30", "visitor_id": "alice@example.test",
    })
    database.payment_transactions.rows.append({
        "owner_id": "alice@example.test", "tenant_id": "tenant-a", "session_id": "cs_existing",
        "payment_status": stored_status, "amount": 4.99, "currency": "usd", "buyer_id": "alice@example.test", "playable_id": "owned-game",
        "metadata": metadata, "processed": False,
    })
    status = SimpleNamespace(status="complete", payment_status=payment_status, amount_total=499, currency="usd")
    database.playables.rows.append({"owner_id": "alice@example.test", "tenant_id": "tenant-a", "playable_id": "owned-game"})
    module = marketplace if route == "marketplace" else creator_economy
    monkeypatch.setattr(module, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(module, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(module, "_checkout", lambda *_: SimpleNamespace(get_checkout_status=AsyncMock(return_value=status)))
    finalize = AsyncMock()
    if route == "marketplace":
        monkeypatch.setattr(module, "_finalize_purchase", finalize)
    client.app.include_router(module.router)
    path = "/api/marketplace/checkout/status/cs_existing" if route == "marketplace" else "/api/premium/status/session/cs_existing"
    response = client.get(path, headers=headers["alice"])
    assert response.status_code == 200, response.text
    assert database.payment_transactions.rows[0]["payment_status"] == "paid"
    if payment_status == "paid" and route == "marketplace":
        finalize.assert_awaited_once()
    if payment_status == "paid" and route == "premium":
        assert database.premium_entitlements.writes
    if payment_status == "unpaid":
        assert not database.premium_entitlements.writes
        finalize.assert_not_awaited()


@pytest.mark.parametrize("route", ["marketplace", "premium"])
def test_changed_order_between_validation_and_paid_write_is_not_settled(project_boundary, monkeypatch, route):
    client, headers, _, database = project_boundary
    metadata = (_sale_metadata() if route == "marketplace" else {
        "source": "premium", "plan": "monthly", "days": "30", "visitor_id": "alice@example.test",
    })
    transactions = database.payment_transactions
    transactions.rows.append({
        "owner_id": "alice@example.test", "tenant_id": "tenant-a", "session_id": "cs_existing",
        "payment_status": "initiated", "amount": 4.99, "currency": "usd", "buyer_id": "alice@example.test", "playable_id": "owned-game",
        "metadata": metadata, "processed": False,
    })
    database.playables.rows.append({"owner_id": "alice@example.test", "tenant_id": "tenant-a", "playable_id": "owned-game"})
    original_update = transactions.update_one
    async def change_before_update(query, update, *args, **kwargs):
        transactions.rows[0]["amount"] = 5.0
        return await original_update(query, update, *args, **kwargs)
    monkeypatch.setattr(transactions, "update_one", change_before_update)
    status = SimpleNamespace(status="complete", payment_status="paid", amount_total=499, currency="usd")
    module = marketplace if route == "marketplace" else creator_economy
    monkeypatch.setattr(module, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(module, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(module, "_checkout", lambda *_: SimpleNamespace(get_checkout_status=AsyncMock(return_value=status)))
    finalize = AsyncMock()
    if route == "marketplace":
        monkeypatch.setattr(module, "_finalize_purchase", finalize)
    client.app.include_router(module.router)
    path = "/api/marketplace/checkout/status/cs_existing" if route == "marketplace" else "/api/premium/status/session/cs_existing"
    response = client.get(path, headers=headers["alice"])
    assert response.status_code == 409, response.text
    assert transactions.rows[0]["payment_status"] == "initiated"
    finalize.assert_not_awaited()
    assert not database.premium_entitlements.writes


@pytest.mark.parametrize("webhook", [False, True])
def test_changed_recipient_after_paid_write_is_not_finalized(project_boundary, monkeypatch, webhook):
    client, headers, _, database = project_boundary
    identity = {"owner_id": "alice@example.test", "tenant_id": "tenant-a"}
    database.playables.rows.append({**identity, "playable_id": "owned-game"})
    transactions = database.payment_transactions
    transactions.rows.append({
        **identity, "session_id": "cs_existing", "payment_status": "initiated", "amount": 4.99,
        "currency": "usd", "playable_id": "owned-game", "buyer_id": "alice@example.test",
        "metadata": _sale_metadata(),
    })
    original_update = transactions.update_one
    async def change_after_update(query, update, *args, **kwargs):
        result = await original_update(query, update, *args, **kwargs)
        transactions.rows[0]["buyer_id"] = "other@example.test"
        transactions.rows[0]["metadata"]["buyer_id"] = "other@example.test"
        return result
    monkeypatch.setattr(transactions, "update_one", change_after_update)
    status = SimpleNamespace(status="complete", payment_status="paid", amount_total=499, currency="usd")
    event = SimpleNamespace(event_type="checkout.session.completed", session_id="cs_existing",
                            payment_status="paid", amount_total=499, currency="usd")
    checkout = SimpleNamespace(get_checkout_status=AsyncMock(return_value=status), handle_webhook=AsyncMock(return_value=event))
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: checkout)
    finalize = AsyncMock()
    monkeypatch.setattr(marketplace, "_finalize_purchase", finalize)
    client.app.include_router(marketplace.router)
    response = (client.post("/api/webhook/stripe", headers=headers["alice"], json={}) if webhook else
                client.get("/api/marketplace/checkout/status/cs_existing", headers=headers["alice"]))
    assert response.status_code == (503 if webhook else 409), response.text
    finalize.assert_not_awaited()


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


def test_webhook_verifier_outage_is_retryable_and_does_not_write(project_boundary, monkeypatch):
    client, headers, _, database = project_boundary
    checkout = SimpleNamespace(handle_webhook=AsyncMock(side_effect=RuntimeError("secret unavailable")))
    monkeypatch.setattr(marketplace, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(marketplace, "STRIPE_API_KEY", "test-key")
    monkeypatch.setattr(marketplace, "_checkout", lambda *_: checkout)
    client.app.include_router(marketplace.router)
    response = client.post("/api/webhook/stripe", headers=headers["alice"], json={})
    assert response.status_code == 503
    assert response.json() == {"received": False, "error": "webhook_unavailable"}
    assert all(not collection.writes for collection in database.collections.values())


def test_new_premium_checkout_is_blocked_before_provider_or_storage(project_boundary, monkeypatch):
    client, headers, users, database = project_boundary
    monkeypatch.setattr(creator_economy, "_db", playable_access.scoped_database(database))
    monkeypatch.setattr(creator_economy, "STRIPE_API_KEY", "test-key")
    def unexpected_checkout(*args, **kwargs):
        raise AssertionError("payment provider must not be contacted")
    monkeypatch.setattr(creator_economy, "_checkout", unexpected_checkout)
    client.app.include_router(creator_economy.router)
    payload = {"visitor_id": "alice@example.test", "plan": "monthly", "origin_url": "https://example.test"}
    assert client.post("/api/premium/checkout", json=payload).status_code == 401
    users["alice@example.test"]["role"] = "viewer"
    assert client.post("/api/premium/checkout", headers=headers["alice"], json=payload).status_code == 403
    users["alice@example.test"]["role"] = "editor"
    response = client.post("/api/premium/checkout", headers=headers["alice"], json=payload)
    assert response.status_code == 503
    assert response.json()["code"] == "premium_release_unavailable"
    assert all(not collection.writes for collection in database.collections.values())
