from skeleton.ai.webcrawler.decade_signals import DecadeSignalSeries
from skeleton.ai.webcrawler.research import frontier_priority
from skeleton.ai.webcrawler.providers import FederatedDiscovery,SourceCandidate
def test_decade_aggregation_preserves_coverage_and_weighted_quality():
 s=DecadeSignalSeries({1990:{"observations":1,"distinct_hosts":1,"mean_relevance":1,"mean_source_score":.5,"positive":1,"negative":0},1995:{"observations":3,"distinct_hosts":2,"mean_relevance":.5,"mean_source_score":1,"positive":1,"negative":2}})
 d=s.aggregate()[1990]
 assert d["years_observed"]==2 and d["coverage"]==.2 and d["observations"]==4
 assert d["mean_source_score"]==.875 and d["net_polarity"]==0
def test_undercovered_decades_include_absent_regimes():
 s=DecadeSignalSeries({2001:{"observations":1}})
 assert s.undercovered_decades(1980,2010,minimum_coverage=.2)==(1980,1990,2000,2010)
def test_frontier_priority_rewards_target_decade():
 a=frontier_priority("ai systems","https://x/report",target_decades=(1980,))
 b=frontier_priority("ai systems","https://x/report-1987",target_decades=(1980,))
 assert b>a
class P:
 name="p"
 def search(self,q,*,limit):
  return [SourceCandidate("https://x/new","new",score=.9),SourceCandidate("https://x/old","AI history 1987",score=.4)]
def test_federated_discovery_can_prioritize_missing_decade():
 out=FederatedDiscovery([P()]).discover_temporal("AI",target_decades=(1980,),total_limit=2)
 assert out[0].url=="https://x/old"
