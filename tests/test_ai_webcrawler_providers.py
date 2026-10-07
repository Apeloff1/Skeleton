from skeleton.ai.webcrawler.providers import FederatedDiscovery,SourceCandidate
class P:
 def __init__(self,name,rows):self.name=name;self.rows=rows
 def search(self,q,limit):return self.rows[:limit]
def test_federation_dedupes_and_keeps_stronger_candidate():
 a=P("a",[SourceCandidate("https://x/","x",provider="a",score=.2)])
 b=P("b",[SourceCandidate("https://x/","x",provider="b",score=.9)])
 out=FederatedDiscovery([a,b]).discover("q")
 assert len(out)==1 and out[0].provider=="b"
def test_federation_interleaves_providers_for_discovery_diversity():
 a=P("a",[SourceCandidate(f"https://a/{i}",provider="a",score=1-i/10) for i in range(3)])
 b=P("b",[SourceCandidate(f"https://b/{i}",provider="b",score=1-i/10) for i in range(3)])
 out=FederatedDiscovery([a,b]).discover("q",total_limit=4)
 assert [x.provider for x in out]==["a","b","a","b"]
