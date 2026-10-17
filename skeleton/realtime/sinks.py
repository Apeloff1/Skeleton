"""Job/agent event seam between the jobs queue and the realtime hub.

Internal Systems' app services (PR #4097, ``skeleton/app_services/events.py``)
expose a ``JobEventPublisher`` protocol (``publish(event: dict)``), a
``NullJobEventPublisher`` default and a shared ``FanOutPublisher`` at
``AppServices.events`` whose ``subscribe(sink)`` returns an unsubscribe
function. To keep both PRs mergeable in either order this module never
imports ``skeleton.app_services``; it defines a structurally identical
Protocol and the :class:`HubJobEventSink` adapter, and :func:`attach_hub`
subscribes the sink to any publisher that offers ``subscribe``.

The hub owns the delivered ``id``: producer envelopes are re-sequenced onto
the hub's single stream so ``/api/v1/events`` has one resume cursor. The
producer's own (per-channel) id is preserved as ``payload.source_id``.

Access binding (Jenkins S1-1): the owner principal and tenant are read from
the producer envelope's top-level ``actor_id``/``owner``/``principal`` and
``tenant_id``/``tenant`` fields (set by the server-side jobs service), never
from ``payload``, and handed to the hub as hub-side metadata. Events with
no owner are only visible to job-grant holders.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from .envelope import CHANNEL_AGENT, CHANNEL_BUILD, EnvelopeError, RealtimeEvent, channel_for_type, validate_identifier
from .guard import RealtimeSecretError

JOB_CHANNELS = (CHANNEL_BUILD, CHANNEL_AGENT)


@runtime_checkable
class JobEventPublisher(Protocol):
    """Shape shared with ``skeleton.app_services.events.JobEventPublisher``."""

    def publish(self, event: dict) -> None: ...


class NullJobEventPublisher:
    """Local stand-in for the #4097 default sink: drops everything."""

    def publish(self, event: dict) -> None:
        return None


def _field(event: Any, *names: str) -> Any:
    for name in names:
        if isinstance(event, Mapping):
            if name in event:
                return event[name]
        elif hasattr(event, name):
            return getattr(event, name)
    return None


def _ident(value: Any) -> Optional[str]:
    """Keep valid short identifiers; drop empty or free-text values."""
    if value is None or value == "":
        return None
    text = str(value)
    try:
        return validate_identifier(text, "identifier")
    except EnvelopeError:
        return None


def _owner(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (bool, Mapping, list, tuple)):
        return None
    text = str(value).strip()
    return text[:512] or None


class HubJobEventSink:
    """``JobEventPublisher`` that re-sequences producer envelopes into the hub.

    Never raises into the fan-out: invalid or secret-bearing events are
    counted (``realtime.publish_rejected{reason=job_sink}``) and skipped.
    """

    def __init__(self, hub: Any) -> None:
        self.hub = hub
        self.accepted = 0
        self.rejected = 0

    def publish(self, event: dict) -> Optional[RealtimeEvent]:  # type: ignore[override]
        try:
            event_type = str(_field(event, "type", "event_type") or "")
            channel = channel_for_type(event_type)
            if channel not in JOB_CHANNELS:
                raise EnvelopeError(f"job sink only carries {JOB_CHANNELS}")
            payload = _field(event, "payload", "data")
            if payload is None:
                payload = {}
            if not isinstance(payload, Mapping):
                payload = {"value": payload}
            payload = dict(payload)
            source_id = _field(event, "id", "seq")
            if source_id is not None and not isinstance(source_id, bool):
                payload.setdefault("source_id", str(source_id))
            published = self.hub.publish(
                channel,
                event_type,
                payload,
                job_id=_ident(_field(event, "job_id")),
                correlation_id=_ident(_field(event, "correlation_id")),
                owner=_owner(_field(event, "actor_id", "owner", "principal")),
                tenant=_owner(_field(event, "tenant_id", "tenant")),
            )
        except (EnvelopeError, RealtimeSecretError, RuntimeError, ValueError, TypeError):
            self.rejected += 1
            slo = getattr(self.hub, "slo", None)
            if slo is not None:
                try:
                    slo.record_publish_rejected("job_sink")
                except Exception:
                    pass
            return None
        self.accepted += 1
        return published


def attach_hub(publisher: Any, sink: HubJobEventSink) -> Optional[Callable[[], None]]:
    """Subscribe ``sink`` to a ``FanOutPublisher``-shaped object if possible.

    Returns the unsubscribe callable, or ``None`` when ``publisher`` has no
    ``subscribe`` (e.g. #4097 not merged yet / app services not opened).
    """
    subscribe = getattr(publisher, "subscribe", None)
    if not callable(subscribe):
        return None
    unsubscribe = subscribe(sink)
    return unsubscribe if callable(unsubscribe) else (lambda: None)


__all__ = ["HubJobEventSink", "JOB_CHANNELS", "JobEventPublisher", "NullJobEventPublisher", "attach_hub"]
