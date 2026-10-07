"""Socket-bound HTTP transport: DNS validation is enforced at connect time."""
from __future__ import annotations
import http.client,ipaddress,ssl,time
from dataclasses import dataclass
from urllib.parse import urlsplit
from .core import FetchResponse
from .dns_binding import ResolvedTarget,resolve_target,peer_is_planned
class BoundConnectionError(ConnectionError):pass
class _PinnedHTTPConnection(http.client.HTTPConnection):
 def __init__(self,target:ResolvedTarget,timeout):super().__init__(target.host,target.port,timeout=timeout);self.target=target
 def connect(self):
  import socket
  last=None
  for address in self.target.addresses:
   try:
    sock=socket.create_connection((address,self.target.port),self.timeout)
    if not peer_is_planned(sock.getpeername()[0],self.target):
     sock.close();raise BoundConnectionError("connected peer outside validated DNS set")
    self.sock=sock;return
   except OSError as exc:last=exc
  raise BoundConnectionError("no validated address connected") from last
class _PinnedHTTPSConnection(_PinnedHTTPConnection):
 def __init__(self,target,timeout,context):super().__init__(target,timeout);self.context=context
 def connect(self):
  super().connect()
  # server_hostname retains original host for SNI and certificate hostname verification.
  self.sock=self.context.wrap_socket(self.sock,server_hostname=self.target.host)
  if not peer_is_planned(self.sock.getpeername()[0],self.target):
   self.sock.close();raise BoundConnectionError("TLS peer outside validated DNS set")
@dataclass
class SocketBoundFetcher:
 timeout_seconds:float=15.0
 allowed_hosts:frozenset[str]|None=None
 ssl_context:ssl.SSLContext|None=None
 def fetch_once(self,url,*,user_agent,max_bytes):
  target=resolve_target(url,self.allowed_hosts);p=urlsplit(target.url)
  if max_bytes < 0:raise ValueError("max_bytes must be non-negative")
  context=self.ssl_context or ssl.create_default_context()
  conn=(_PinnedHTTPSConnection(target,self.timeout_seconds,context) if p.scheme=="https" else _PinnedHTTPConnection(target,self.timeout_seconds))
  path=p.path or "/"
  if p.query:path+="?"+p.query
  host_header=f"[{target.host}]" if ":" in target.host else target.host
  if p.port is not None:host_header=f"{host_header}:{p.port}"
  headers={"Host":host_header,"User-Agent":user_agent,
   "Accept":"text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.1","Accept-Encoding":"identity","Connection":"close"}
  try:
   conn.request("GET",path,headers=headers);response=conn.getresponse()
   status=int(response.status);out_headers={k.lower():v for k,v in response.getheaders()}
   if status in {301,302,303,307,308}:body=b""
   else:
    length=out_headers.get("content-length")
    if length:
     try:size=int(length)
     except ValueError:raise ValueError("invalid Content-Length")
     if size>max_bytes:raise ValueError("response exceeds configured byte limit")
    body=response.read(max_bytes+1)
    if len(body)>max_bytes:raise ValueError("response exceeds configured byte limit")
   return FetchResponse(target.url,status,out_headers,body,time.time())
  finally:conn.close()
