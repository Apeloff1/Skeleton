from dataclasses import replace
from skeleton.ai.webcrawler.bitemporal import BitemporalFact
from skeleton.ai.webcrawler.temporal_scope import TemporalScope,filter_temporal
from skeleton.ai.webcrawler.source_dependence import source_dependence,independent_host_count
from skeleton.ai.webcrawler.acquisition_queries import synthesize_acquisition_queries
from skeleton.ai.webcrawler.active_research import AcquisitionTarget
from skeleton.ai.webcrawler.regime_assurance import gate_change_points
from skeleton.ai.webcrawler.regimes import ChangePoint
from skeleton.ai.webcrawler.research import EvidenceObservation
def obs(i,host,text,years,h=None):
 return EvidenceObservation(i,h or i,"https://"+host+"/x",host,100,"",text,1,.9,1,tuple(years))
def test_bitemporal_fact_requires_valid_and_known_time():
 f=BitemporalFact(1990,1999,100,200)
 assert f.visible(year=1995,as_of=150) and not f.visible(year=2001,as_of=150) and not f.visible(year=1995,as_of=250)
def test_temporal_scope_filters_event_and_asof_dimensions():
 a=obs("a","a.example","x",(1980,));b=replace(a,observation_id="b",signal_years=(2000,),fetched_at=300)
 assert filter_temporal((a,b),TemporalScope(1970,1990,as_of=200))==(a,)
def test_mirrors_collapse_independence_even_across_hosts():
 a=obs("a","a.example","same copied evidence",(2000,),"hash");b=obs("b","b.example","same copied evidence",(2000,),"hash")
 edges=source_dependence((a,b));assert edges and independent_host_count((a,b),edges)==1
def test_acquisition_query_synthesis_is_bounded_and_reasoned():
 t=AcquisitionTarget(1980,1989,.8,("historical-bias","persistent-contestation"))
 q=synthesize_acquisition_queries("neural networks",(t,),per_target=2)
 assert len(q)==2 and all("1980 1989" in x.query for x in q)
def test_change_point_assurance_rejects_high_uncertainty():
 p=ChangePoint(2001,.8,.8,0,0,0);signals={2001:{"distinct_hosts":3}}
 assert not gate_change_points((p,),signals,{2001:.8})[0].accepted
 assert gate_change_points((p,),signals,{2001:.1})[0].accepted
