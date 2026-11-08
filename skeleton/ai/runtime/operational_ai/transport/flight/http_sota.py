"""Quarantined flight HTTP adapter bound to the proven local transport.

The historical SOTA handler was not a BaseHTTPRequestHandler and silently
discarded responses. Never hash an unauthenticated Authorization header into a
principal or expose an unauthenticated synthetic protocol endpoint.

This adapter adds no routes or privileges: the canonical FlightRequestHandler
performs loopback Host, Origin, framing and bearer checks before dispatch.
"""
from __future__ import annotations

from .http import FlightHTTPServer, FlightRequestHandler


class FlightRequestHandlerSOTA(FlightRequestHandler):
    """Use the production handler's authenticated GET/POST and bounded _write.

    All status, response-framing, event-cursor, and error operations deliberately
    remain on the canonical implementation; no independent auth policy exists.
    """


class FlightHTTPServerSOTA(FlightHTTPServer):
    """Opt-in class selection, with canonical socket and worker admission."""

    def __init__(self, address, dispatcher, token, **kwargs):
        super().__init__(address, dispatcher, token, **kwargs)
        # Parent creates an authenticated, bounded loopback server and sets
        # event_stream only after the ledger and token were validated.
        self.RequestHandlerClass = FlightRequestHandlerSOTA
