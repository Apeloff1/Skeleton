"""Legacy Stripe checkout compatibility surface."""

from .checkout import CheckoutSessionRequest, StripeCheckout

__all__ = ["CheckoutSessionRequest", "StripeCheckout"]
