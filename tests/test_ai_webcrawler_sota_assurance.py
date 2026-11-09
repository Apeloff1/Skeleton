from skeleton.ai.webcrawler.stopping import decide_research_stop
from skeleton.ai.webcrawler.temporal_retrieval import TemporalFragment,TemporalRetrievalCatalog
from skeleton.ai.webcrawler.source_dependence import merge_citation_dependence,DependenceEdge,independent_host_count
from skeleton.ai.webcrawler.research import EvidenceObservation
def o(i,host):
 return EvidenceObservation(i,i,"https://"+host+"/"+i,host,1,"","alpha",1,.9,1,(2000,))
def test_direct_citation_collapses_otherwise_independent_hosts():
 a=o("a","a.example");b=o("b","b.example")
 edges=merge_citation_dependence((a,b),(),(("a","b"),))
 assert independent_host_count((a,b),edges)==1 and "direct-citation" in edges[0].reasons
def test_stopping_policy_requires_robust_independent_evidence():
 good={"score":.9,"independent_evidence_clusters":4}
 assert decide_research_stop(assurance=good,uncertainty=.1,max_influence=.1).action=="stop"
 assert decide_research_stop(assurance=good,uncertainty=.1,max_influence=.5).action=="continue"
def test_temporal_catalog_filters_asof_and_event_year():
 c=TemporalRetrievalCatalog()
 c.put(TemporalFragment("a","u",100,(1980,), "h1"));c.put(TemporalFragment("b","v",300,(2000,),"h2"))
 assert c.filter(("a","b"),event_from=1970,event_to=1990,as_of=200)==("a",)
