from skeleton.ai.webcrawler.dns_binding import ResolvedTarget
from skeleton.ai.webcrawler.bound_http import _PinnedHTTPConnection,BoundConnectionError
import skeleton.ai.webcrawler.bound_http as mod
class Sock:
 def __init__(self,peer):self.peer=peer;self.closed=False
 def getpeername(self):return (self.peer,443)
 def close(self):self.closed=True
def test_connection_rejects_peer_not_in_resolution_plan(monkeypatch):
 target=ResolvedTarget("http://example.org/","example.org",80,("93.184.216.34",))
 bad=Sock("127.0.0.1")
 monkeypatch.setattr("socket.create_connection",lambda *a,**k:bad)
 c=_PinnedHTTPConnection(target,1)
 try:c.connect()
 except BoundConnectionError:pass
 else:raise AssertionError("unplanned peer accepted")
 assert bad.closed
def test_connection_accepts_exact_validated_peer(monkeypatch):
 target=ResolvedTarget("http://example.org/","example.org",80,("93.184.216.34",))
 good=Sock("93.184.216.34")
 monkeypatch.setattr("socket.create_connection",lambda *a,**k:good)
 c=_PinnedHTTPConnection(target,1);c.connect();assert c.sock is good
