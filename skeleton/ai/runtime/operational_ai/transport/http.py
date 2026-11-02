"""Bearer-authenticated *loopback-only* stdlib HTTP transport.

No public binding, automatic CORS, unauthenticated health disclosure, model
credential interpolation or hosted provider fallback. The caller owns token
custody and must supply a strong random bearer secret.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac
import ipaddress
import json
from typing import Any
from ..authority.canonical import ContractViolation
from .protocol import parse_request,response,MAX_BODY
from .dispatch import Dispatcher


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=False
    daemon_threads=True

    def __init__(self,address:tuple[str,int],dispatcher:Dispatcher,token:str):
        host,port=address
        try:
            ip=ipaddress.ip_address(host)
        except ValueError as exc:
            raise ContractViolation("local API requires literal loopback IP") from exc
        if not ip.is_loopback or type(port) is not int or not 0<=port<=65535:
            raise ContractViolation("public API binding refused")
        if type(token) is not str or not 32<=len(token)<=512:
            raise ContractViolation("bearer secret too short or invalid")
        self.dispatcher=dispatcher
        self.bearer=token.encode("utf-8")
        super().__init__(address,RequestHandler)


class RequestHandler(BaseHTTPRequestHandler):
    server:LocalHTTPServer
    protocol_version="HTTP/1.1"

    def log_message(self,*args:object)->None:
        # Never log request URL, query or potentially secret-bearing headers.
        return

    def _write(self,code:int,status:str,result:dict):
        raw=response(status,result)
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Connection","close")
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection=True

    def _authorize(self)->bool:
        host=self.headers.get("Host","")
        allowed=(f"{self.server.server_address[0]}:{self.server.server_address[1]}",)
        if host not in allowed:
            self._write(403,"denied",{"reason":"host-rejected"})
            return False
        if self.headers.get("Origin") is not None:
            self._write(403,"denied",{"reason":"browser-origin-not-accepted"})
            return False
        header=self.headers.get("Authorization","")
        if not header.startswith("Bearer ") or not hmac.compare_digest(
            header[len("Bearer "):].encode("utf-8"),self.server.bearer):
            self._write(401,"denied",{"reason":"bearer-required"})
            return False
        return True

    def do_GET(self)->None:
        if not self._authorize():return
        if self.path!="/v1/protocol":
            self._write(404,"bad-request",{"reason":"unknown-route"});return
        from .protocol import schema
        self._write(200,"ok",schema())

    def do_POST(self)->None:
        if not self._authorize():return
        if self.path!="/v1/operations":
            self._write(404,"bad-request",{"reason":"unknown-route"});return
        if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
            self._write(415,"bad-request",{"reason":"json-required"});return
        length=self.headers.get("Content-Length","")
        if not length.isascii() or not length.isdecimal() or not 0<int(length)<=MAX_BODY:
            self._write(413,"bad-request",{"reason":"body-size-invalid"});return
        try:
            raw=self.rfile.read(int(length))
            if len(raw)!=int(length):
                raise ContractViolation("malformed request length")
            operation,payload=parse_request(raw)
            data=self.server.dispatcher.dispatch(operation,payload)
            self._write(200,"ok",data)
        except ContractViolation:
            self._write(400,"bad-request",{"reason":"contract-rejected"})
        except Exception:
            self._write(500,"error",{"reason":"operation-failed"})
