"""Pack F outbound webhook / callback egress gateway.

Signed callbacks (Standard Webhooks), destination allowlist + SSRF guard,
delivery through the gate-plane pipeline (deadline, retry budget, per-host
breaker), slow redelivery rounds and a dead-letter queue with replay.
Opt-in library code; no edits to ``skeleton/api/server.py``.
"""

from __future__ import annotations

from skeleton.gate_plane.egress.allowlist import EgressAllowlist, EgressDenyReason, EgressVerdict, is_public_address
from skeleton.gate_plane.egress.dlq import DeadLetter, DeadLetterQueue
from skeleton.gate_plane.egress.gateway import (
    DEFAULT_REDELIVERY_SCHEDULE_S,
    Callback,
    DeliveryOutcome,
    DeliveryResult,
    EgressGateway,
    OutboxEntry,
    RedirectRefused,
    Subscription,
)
from skeleton.gate_plane.egress.signing import (
    SecretSet,
    WebhookSignatureError,
    WebhookSigner,
    WebhookVerifier,
    decode_secret,
    encode_secret,
)
from skeleton.gate_plane.egress.transport import (
    ScriptedTransport,
    Transport,
    TransportRequest,
    TransportResponse,
    UrllibTransport,
)

__all__ = [
    "Callback",
    "DEFAULT_REDELIVERY_SCHEDULE_S",
    "DeadLetter",
    "DeadLetterQueue",
    "DeliveryOutcome",
    "DeliveryResult",
    "EgressAllowlist",
    "EgressDenyReason",
    "EgressGateway",
    "EgressVerdict",
    "OutboxEntry",
    "RedirectRefused",
    "ScriptedTransport",
    "SecretSet",
    "Subscription",
    "Transport",
    "TransportRequest",
    "TransportResponse",
    "UrllibTransport",
    "WebhookSignatureError",
    "WebhookSigner",
    "WebhookVerifier",
    "decode_secret",
    "encode_secret",
    "is_public_address",
]
