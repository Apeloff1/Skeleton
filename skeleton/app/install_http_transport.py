"""Direct, loopback-pinned install diagnostics and bounded JSON framing.

The HTTP/HTTPS handlers retain the declared origin/Host and TLS hostname,
but literal loopback connections never use the host resolver. Generic
explicit remote diagnostics keep standard TLS verification and DNS.
This does not prove the identity of a local listening process.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
from urllib.request import HTTPHandler, HTTPSHandler

_MAX_CONTENT_LENGTH = re.compile(r"[0-9]{1,9}\Z", re.ASCII)


def _loopback_ip(host):
    if not isinstance(host,str):
        return None
    if host.lower()=="localhost":
        return ipaddress.IPv4Address("127.0.0.1")
    try:
        value=ipaddress.ip_address(host)
    except ValueError:
        return None
    return value if value.is_loopback else None


def _direct_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                       source_address=None):
    host,port=address
    local=_loopback_ip(host)
    if local is None:
        return socket.create_connection(address,timeout,source_address)
    # Numeric sockaddr, no getaddrinfo or hosts-file interpretation.
    sock=socket.socket(socket.AF_INET if local.version==4 else socket.AF_INET6,
                       socket.SOCK_STREAM)
    try:
        if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(timeout)
        if source_address is not None:
            sock.bind(source_address)
        sockaddr=(str(local),port) if local.version==4 else (str(local),port,0,0)
        sock.connect(sockaddr)
        return sock
    except BaseException:
        sock.close()
        raise


class DirectHTTPConnection(http.client.HTTPConnection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._create_connection=_direct_connection


class DirectHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._create_connection=_direct_connection


class DirectHTTPHandler(HTTPHandler):
    def http_open(self,req):
        return self.do_open(DirectHTTPConnection,req)


class DirectHTTPSHandler(HTTPSHandler):
    def https_open(self,req):
        return self.do_open(DirectHTTPSConnection,req,
                            context=self._context)


class FramingDenied(ValueError):
    pass


def response_length(headers, *, limit):
    """Require unambiguous, identity-encoded, bounded JSON response framing."""
    if headers is None or not callable(getattr(headers,"get_all",None)):
        raise FramingDenied("metadata missing")
    lengths=headers.get_all("Content-Length") or []
    transfers=headers.get_all("Transfer-Encoding") or []
    encodings=headers.get_all("Content-Encoding") or []
    if any(type(group) is not list or len(group)>1
           or any(type(value) is not str for value in group)
           for group in (lengths,transfers,encodings)):
        raise FramingDenied("duplicate response framing")
    if lengths and transfers:
        raise FramingDenied("conflicting response framing")
    if encodings and encodings[0].strip().lower()!="identity":
        raise FramingDenied("unsupported content encoding")
    if transfers and transfers[0].strip().lower()!="chunked":
        raise FramingDenied("unsupported transfer encoding")
    if not lengths:
        return None
    if _MAX_CONTENT_LENGTH.fullmatch(lengths[0]) is None:
        raise FramingDenied("invalid content length")
    length=int(lengths[0])
    if not 0<length<=limit:
        raise FramingDenied("content length outside budget")
    return length


def checked_body(raw, *, expected_length, limit):
    if (type(raw) is not bytes or not 0<len(raw)<=limit
            or (expected_length is not None and len(raw)!=expected_length)):
        raise FramingDenied("body length outside contract")
    return raw.decode("utf-8","strict")
