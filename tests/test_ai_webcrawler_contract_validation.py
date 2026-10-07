import math
from skeleton.ai.webcrawler.research import ResearchQuery,EvidenceSet
from skeleton.ai.webcrawler.providers import FederatedDiscovery,SourceCandidate
def test_research_query_rejects_invalid_assurance_state():
 for kw in ({"required_sources":0},{"freshness_half_life_seconds":float("nan")},{"diversity_weight":.9,"contradiction_weight":.2}):
  try:ResearchQuery("q",**kw)
  except ValueError:pass
  else:raise AssertionError(kw)
class P:
 name="p"
 def search(self,q,*,limit):return [SourceCandidate("https://a.example/x",score=float("nan")),SourceCandidate("https://a.example/y",score=.5)]
def test_discovery_drops_nonfinite_scores():
 out=FederatedDiscovery([P()]).discover("q")
 assert [x.url for x in out]==["https://a.example/y"]
def test_discovery_rejects_duplicate_provider_names():
 try:FederatedDiscovery([P(),P()])
 except ValueError:pass
 else:raise AssertionError("duplicate provider accepted")
