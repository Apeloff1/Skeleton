"""Boot-safe Stripe Checkout facade for the retired Emergent payments SDK.

Marketplace and creator-economy routes import this module at process start.
Importing it must not open a network connection or require a configured key.
Checkout calls go through the official ``stripe`` package, which is already a
backend dependency, and fail closed when the key or webhook secret is absent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


@dataclass(frozen=True)
class CheckoutSessionRequest:
    amount: float
    currency: str
    success_url: str
    cancel_url: str
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CheckoutSession:
    session_id: str
    url: str


@dataclass(frozen=True)
class CheckoutStatus:
    status: str
    payment_status: str
    amount_total: int | None
    currency: str | None


@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    session_id: str | None
    payment_status: str | None


class StripeCheckout:
    """One-time Checkout sessions. Amounts are server-owned, never client prices."""

    def __init__(self, api_key: str, webhook_url: str, webhook_secret: str | None = None):
        self.api_key = str(api_key or "").strip()
        self.webhook_url = str(webhook_url or "").strip()
        self.webhook_secret = str(webhook_secret or "").strip() or None

    async def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSession:
        if not self.api_key:
            raise RuntimeError("payments not configured")
        payload = _session_create_kwargs(request)
        stripe = _stripe_module()

        def _create():
            return stripe.checkout.Session.create(api_key=self.api_key, **payload)

        session = await asyncio.to_thread(_create)
        session_id = str(getattr(session, "id", "") or "")
        url = str(getattr(session, "url", "") or "")
        if not session_id.startswith("cs_") or not url.startswith("https://"):
            raise RuntimeError("stripe returned an unusable checkout session")
        return CheckoutSession(session_id=session_id, url=url)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatus:
        if not self.api_key:
            raise RuntimeError("payments not configured")
        safe_id = str(session_id or "").strip()
        if not safe_id.startswith("cs_") or len(safe_id) > 255:
            raise ValueError("invalid checkout session id")
        stripe = _stripe_module()

        def _retrieve():
            return stripe.checkout.Session.retrieve(safe_id, api_key=self.api_key)

        session = await asyncio.to_thread(_retrieve)
        amount = getattr(session, "amount_total", None)
        return CheckoutStatus(
            status=str(getattr(session, "status", "") or "unknown"),
            payment_status=str(getattr(session, "payment_status", "") or "unknown"),
            amount_total=int(amount) if isinstance(amount, int) else None,
            currency=(str(getattr(session, "currency", "") or "") or None),
        )

    async def handle_webhook(self, payload: bytes, signature: str | None) -> WebhookEvent:
        if not self.webhook_secret:
            raise RuntimeError("webhook secret not configured")
        if not signature or not isinstance(payload, (bytes, bytearray)):
            raise ValueError("webhook signature required")
        stripe = _stripe_module()

        def _construct():
            return stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )

        event = await asyncio.to_thread(_construct)
        event_type = str(event.get("type") or "")
        data = event.get("data") if isinstance(event, Mapping) else None
        obj = data.get("object") if isinstance(data, Mapping) else None
        if not isinstance(obj, Mapping):
            obj = {}
        session_id = obj.get("id") if str(obj.get("object") or "") == "checkout.session" else None
        payment_status = obj.get("payment_status")
        if event_type == "checkout.session.completed" and not payment_status:
            payment_status = "paid"
        return WebhookEvent(
            event_type=event_type,
            session_id=str(session_id) if isinstance(session_id, str) else None,
            payment_status=str(payment_status) if isinstance(payment_status, str) else None,
        )


def _stripe_module():
    import stripe

    return stripe


def _session_create_kwargs(request: CheckoutSessionRequest) -> dict[str, Any]:
    if not isinstance(request, CheckoutSessionRequest):
        raise TypeError("CheckoutSessionRequest required")
    amount = request.amount
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("invalid checkout amount")
    try:
        cents = int(
            (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid checkout amount") from exc
    if cents <= 0 or cents > 50_000_00:
        raise ValueError("checkout amount out of range")
    currency = str(request.currency or "").strip().lower()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("invalid checkout currency")
    success_url = str(request.success_url or "").strip()
    cancel_url = str(request.cancel_url or "").strip()
    for label, url in (("success_url", success_url), ("cancel_url", cancel_url)):
        if not url.startswith(("https://", "http://")) or len(url) > 2000:
            raise ValueError(f"invalid {label}")
    if "{CHECKOUT_SESSION_ID}" not in success_url:
        raise ValueError("success_url must include the checkout session placeholder")
    metadata = _string_metadata(request.metadata)
    return {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": currency,
                    "unit_amount": cents,
                    "product_data": {"name": metadata.get("source") or "Skeleton purchase"},
                },
            }
        ],
    }


def _string_metadata(raw: Mapping[str, Any] | None) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > 40:
        raise ValueError("invalid checkout metadata")
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        text = str(value)
        if not name or len(name) > 40 or len(text) > 500:
            raise ValueError("invalid checkout metadata")
        out[name] = text
    return out
