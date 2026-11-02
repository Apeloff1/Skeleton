"""Reuse mature v1 loopback TLS-free/hostile-header gate with a v2 protocol.

The protocol is intentionally local-only and must never be directly exposed
through port forwarding, a public reverse proxy, browser origins, or an
untrusted multiuser host without an independent TLS/security frontend.
"""
from __future__ import annotations
from ..http import LocalHTTPServer,RequestHandler as LegacyRequestHandler
from ..protocol import parse_request,MAX_BODY
from ...authority.canonical import ContractViolation
from ...orchestration.flight_control.contracts import FlightError,FlightBusy,FlightConflict
from ...orchestration.execution_spine.contracts import SpineError,Busy,Conflict,IntegrityFailure
from .contracts import PROTOCOL


class FlightRequestHandler(LegacyRequestHandler):
    """Same bearer, Host, Origin and request-framing checks as the hardened v1."""
    def do_GET(self)->None:
        if not self._authorize():return
        if self.path!='/v2/protocol':
            self._write(404,'bad-request',{'reason':'unknown-route'});return
        self._write(200,'ok',PROTOCOL)

    def do_POST(self)->None:
        if not self._authorize():return
        if self.path!='/v2/operations':
            self._write(404,'bad-request',{'reason':'unknown-route'});return
        kind=self.headers.get('Content-Type','')
        if kind.split(';')[0].strip().lower()!='application/json':
            self._write(415,'bad-request',{'reason':'json-required'});return
        length=self.headers.get('Content-Length','')
        if not length.isascii() or not length.isdecimal() or not 0<int(length)<=MAX_BODY:
            self._write(413,'bad-request',{'reason':'body-size-invalid'});return
        try:
            raw=self.rfile.read(int(length))
            if len(raw)!=int(length):
                raise ContractViolation('partial request body')
            operation,payload=parse_request(raw)
            value=self.server.dispatcher.dispatch(operation,payload)
            self._write(200,'ok',value)
        except ContractViolation:
            self._write(400,'bad-request',{'reason':'invalid-operation-contract'})
        except (FlightBusy,Busy):
            self._write(409,'conflict',{'reason':'bounded-execution-busy'})
        except (FlightConflict,Conflict):
            self._write(409,'conflict',{'reason':'execution-ownership-conflict'})
        except (IntegrityFailure,SpineError,FlightError):
            # Do not leak source contents, model text or private SQLite paths.
            self._write(500,'error',{'reason':'runtime-held'})
        except Exception:
            self._write(500,'error',{'reason':'runtime-failed'})


class FlightHTTPServer(LocalHTTPServer):
    def __init__(self,address,dispatcher,token,*,max_connections:int=8,
                 io_timeout_seconds:float=15.0):
        super().__init__(address,dispatcher,token,max_connections=max_connections,
                         io_timeout_seconds=io_timeout_seconds)
        self.RequestHandlerClass=FlightRequestHandler
