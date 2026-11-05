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
    def _get_events(self)->None:
        from .event_stream.query import parse_path
        from .event_stream.contracts import StreamError,InvalidCursor,StreamConflict,StreamUnavailable
        if self.headers.get('Content-Length') is not None or self.headers.get('Content-Type') is not None:
            self._write(400,'bad-request',{'reason':'GET-body-framing-forbidden'});return
        if self.headers.get('Accept','text/event-stream') not in ('text/event-stream','*/*'):
            self._write(406,'bad-request',{'reason':'event-stream-required'});return
        try:
            query=parse_path(self.path)
            stream=getattr(self.server,'event_stream',None)
            if stream is None:
                self._write(503,'error',{'reason':'event-stream-held'});return
            raw,_=stream.read(query)
        except InvalidCursor:
            self._write(400,'bad-request',{'reason':'unauthenticated-event-cursor'});return
        except StreamConflict:
            self._write(409,'conflict',{'reason':'event-cursor-conflict'});return
        except StreamUnavailable:
            self._write(503,'error',{'reason':'event-ledger-held'});return
        except StreamError:
            self._write(400,'bad-request',{'reason':'event-request-contract'});return
        except (FlightConflict,Conflict):
            self._write(409,'conflict',{'reason':'event-job-ownership-conflict'});return
        except Exception:
            self._write(503,'error',{'reason':'event-ledger-held'});return
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream; charset=utf-8')
        self.send_header('Cache-Control','no-store, no-transform')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Connection','close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection=True

    def do_GET(self)->None:
        if not self._authorize():return
        if self.path.startswith('/v2/jobs/'):
            self._get_events();return
        if self.path=='/v2/health':
            supervisor=getattr(self.server,'supervisor',None)
            if supervisor is None:
                self._write(404,'bad-request',{'reason':'supervisor-unavailable'});return
            from ...orchestration.flight_control.daemon.health import public_health
            try:
                state=public_health(supervisor)
            except Exception:
                # Runtime state or SQLite custody could be corrupt; never
                # report an unauthenticated or misleading green response.
                self._write(503,'error',{'reason':'readiness-integrity-held'})
                return
            self._write(200 if state['admission']['serving'] else 503,
                        'ok' if state['admission']['serving'] else 'error',state)
            return
        if self.path!='/v2/protocol':
            self._write(404,'bad-request',{'reason':'unknown-route'});return
        advertised=dict(PROTOCOL)
        if not self.server.dispatcher.allow_manual_work:
            advertised['operations']={name:args for name,args in PROTOCOL['operations'].items()
                                      if name!='work_one'}
        self._write(200,'ok',advertised)

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
                 io_timeout_seconds:float=15.0,supervisor=None):
        if supervisor is not None and not hasattr(supervisor,'snapshot'):
            raise ContractViolation('invalid supervisor health provider')
        self.supervisor=supervisor
        super().__init__(address,dispatcher,token,max_connections=max_connections,
                         io_timeout_seconds=io_timeout_seconds)
        try:
            from .event_stream.service import EventStream
            ledger=getattr(getattr(dispatcher,'app',None),'ledger',None)
            self.event_stream=EventStream(ledger,token) if ledger is not None else None
            self.RequestHandlerClass=FlightRequestHandler
        except BaseException:
            self.server_close()
            raise
