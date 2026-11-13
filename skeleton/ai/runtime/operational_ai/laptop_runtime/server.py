"""Reuse the canonical hardened bearer-bound loopback HTTP transport.

Only protocol metadata is specialized for the real production spine; the
existing transport retains its header, Host, Origin, framing, timeout and
max-active request protections.
"""
from __future__ import annotations
from skeleton.ai.runtime.operational_ai.transport.http import LocalHTTPServer,RequestHandler
from .dispatcher import LaptopDispatcher
from .contracts import refuse

class LaptopHandler(RequestHandler):
    def do_GET(self):
        if not self._authorize():
            return
        if self.path!="/v1/protocol":
            self._write(404,"bad-request",{"reason":"unknown-route"})
            return
        self._write(200,"ok",self.server.dispatcher.protocol())

class LaptopHTTPServer(LocalHTTPServer):
    def __init__(self,address,dispatcher,token,*,max_connections=8,io_timeout_seconds=15.0):
        if not isinstance(dispatcher,LaptopDispatcher):
            refuse("real production spine dispatcher required")
        super().__init__(address,dispatcher,token,
                         max_connections=max_connections,
                         io_timeout_seconds=io_timeout_seconds)
        # The base transport owns the exact hardened POST handler; only the
        # authenticated GET protocol path differs for this dispatcher.
        self.RequestHandlerClass=LaptopHandler
