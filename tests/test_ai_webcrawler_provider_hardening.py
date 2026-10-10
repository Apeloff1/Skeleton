from skeleton.ai.webcrawler.providers import FederatedDiscovery,SourceCandidate
class P:
 def __init__(self,name,rows=None,fail=False):self.name=name;self.rows=rows or [];self.fail=fail
 def search(self,query,*,limit):
  if self.fail:raise RuntimeError("provider unavailable")
  return self.rows[:limit]
def test_provider_failure_does_not_abort_federation():
 d=FederatedDiscovery([P("bad",fail=True),P("good",[SourceCandidate("https://EXAMPLE.org/a?b=2&a=1",score=.5)])])
 out=d.discover("q")
 assert len(out)==1 and out[0].provider=="good"
 assert d.last_failures[0].provider=="bad"
def test_canonical_urls_dedupe_across_providers():
 d=FederatedDiscovery([P("a",[SourceCandidate("https://example.org/x?b=2&a=1",score=.2)]),P("b",[SourceCandidate("https://EXAMPLE.org/x?a=1&b=2#frag",score=.9)])])
 out=d.discover("q")
 assert len(out)==1 and out[0].provider=="b" and out[0].score==.9
def test_provider_cannot_spoof_provider_identity():
 d=FederatedDiscovery([P("trusted-adapter",[SourceCandidate("https://example.org/x",provider="other")])])
 assert d.discover("q")[0].provider=="trusted-adapter"
