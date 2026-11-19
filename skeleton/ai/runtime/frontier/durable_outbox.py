"""Explicit durable transactional outbox over Frontier work custody.

The legacy in-memory BoundedOutbox remains available for local hints only.
Durable sends require receiver-owned idempotency and genuine acknowledgement;
this adapter intentionally never retries a delivery of unknown outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from skeleton.frontier.durable_work import (
    DurableWorkJournal, WorkClaim, WorkConflict, WorkOrder, WorkStatus, work_identity,
)
from skeleton.frontier.payloads import json_snapshot

_KIND = "frontier.outbox.v1"


def _identity(value):
    if (type(value) is not str or not value.strip() or value != value.strip()
            or len(value.encode("utf-8")) > 256 or any(ord(c) < 32 for c in value)):
        raise ValueError("bounded outbox identity required")
    return value


def _digest(value):
    raw = json.dumps(json_snapshot(value, max_bytes=256 << 10), sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    message_id: str
    destination: str
    payload: Any


@dataclass(frozen=True, slots=True)
class Delivery:
    claim: WorkClaim
    message: OutboxMessage
    message_digest: str


@dataclass(frozen=True, slots=True)
class DestinationAcknowledgement:
    message_id: str
    destination: str
    message_digest: str
    durable_receipt_digest: str


class DurableOutbox:
    """No implicit network, path or authorization policy. Caller owns transport."""

    def __init__(self, journal: DurableWorkJournal):
        if type(journal) is not DurableWorkJournal:
            raise TypeError("canonical work journal required")
        self._journal = journal

    def enqueue(self, message: OutboxMessage, *, dependencies: tuple[str, ...] = ()) -> WorkStatus:
        if type(message) is not OutboxMessage:
            raise TypeError("canonical OutboxMessage required")
        mid, destination = _identity(message.message_id), _identity(message.destination)
        body = {"message_id": mid, "destination": destination,
                "payload": json_snapshot(message.payload, max_bytes=240 << 10)}
        wid = work_identity(self._journal.scope, _KIND, [destination, mid])
        return self._journal.submit((WorkOrder(wid, _KIND, body, dependencies),))[0]

    def ready(self, *, limit: int = 64) -> tuple[WorkStatus, ...]:
        return self._journal.ready(kind=_KIND, limit=limit)

    def claim(self, work_id: str, *, owner: str) -> Delivery:
        status = self._journal.status(work_id)
        if status.kind != _KIND:
            raise WorkConflict("work is not an outbox delivery")
        claim = self._journal.claim(work_id, owner=owner)
        body = claim.payload
        if type(body) is not dict or set(body) != {"message_id", "destination", "payload"}:
            raise WorkConflict("claimed outbox payload invalid; reconcile")
        message = OutboxMessage(_identity(body["message_id"]),
                                _identity(body["destination"]), body["payload"])
        return Delivery(claim, message, _digest(body))

    def acknowledge(self, delivery: Delivery, ack: DestinationAcknowledgement,
                    *, verify_acknowledgement) -> WorkStatus:
        """The app provides a reviewed independent receipt-verification callback."""
        if type(delivery) is not Delivery or type(ack) is not DestinationAcknowledgement:
            raise TypeError("canonical delivery and acknowledgement required")
        if not callable(verify_acknowledgement):
            raise ValueError("destination receipt verifier required")
        if type(delivery.message) is not OutboxMessage:
            raise WorkConflict("canonical outbox message required")
        body = self._journal.verify_claim(delivery.claim, kind=_KIND)
        presented = {"message_id": delivery.message.message_id,
                     "destination": delivery.message.destination,
                     "payload": delivery.message.payload}
        if (_digest(body) != _digest(presented)
                or _digest(body) != delivery.message_digest):
            raise WorkConflict("delivery does not bind authenticated stored payload")
        if (ack.message_id != delivery.message.message_id
                or ack.destination != delivery.message.destination
                or ack.message_digest != delivery.message_digest
                or delivery.message_digest != _digest(delivery.claim.payload)
                or type(ack.durable_receipt_digest) is not str
                or len(ack.durable_receipt_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in ack.durable_receipt_digest)):
            raise WorkConflict("acknowledgement does not bind claimed message")
        if verify_acknowledgement(ack) is not True:
            raise WorkConflict("destination receipt could not be independently verified")
        return self._journal.finish(delivery.claim, succeeded=True,
                                    receipt_digest=ack.durable_receipt_digest)

    def mark_uncertain(self, delivery: Delivery, *, evidence_digest: str) -> WorkStatus:
        if type(delivery) is not Delivery:
            raise TypeError("canonical delivery required")
        return self._journal.mark_uncertain(delivery.claim, receipt_digest=evidence_digest)
