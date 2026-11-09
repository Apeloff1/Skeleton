from skeleton.ai.webcrawler.temporal_semantics import infer_temporal_semantics
from skeleton.ai.webcrawler.uncertainty import deterministic_bootstrap
from skeleton.ai.webcrawler.lag_signals import lag_scan
from skeleton.ai.webcrawler.active_research import plan_acquisition
from skeleton.ai.webcrawler.regimes import Regime
from skeleton.ai.webcrawler.historical_bias import HistoricalBias
from skeleton.ai.webcrawler.contradiction_history import ContradictionPersistence
def test_temporal_semantics_separates_event_and_observation_time():
 x=infer_temporal_semantics("Report published 2020-02-01 discusses changes from 1987 to 1991",observed_at=1609459200)
 assert x.event_from_year==1987 and x.event_to_year==2020 and x.observed_at==1609459200 and x.published_at is not None
def test_bootstrap_is_deterministic():
 a=deterministic_bootstrap([1,-1,1,1],seed_key="x");b=deterministic_bootstrap([1,-1,1,1],seed_key="x")
 assert a==b and a.low<=a.center<=a.high
def test_lag_scan_finds_shifted_series():
 left={2000:{"positive":1},2001:{"positive":2},2002:{"positive":4},2003:{"positive":8}}
 right={2001:{"positive":1},2002:{"positive":2},2003:{"positive":4},2004:{"positive":8}}
 assert lag_scan(left,right,max_lag=2)[0].lag_years==1
def test_active_acquisition_prioritizes_biased_contested_regime():
 r=Regime(1980,1989,tuple(range(1980,1990)),1,0,.7,.7)
 b=HistoricalBias(1980,.2,.8,.4,.75,("sparse-year-coverage",))
 c=ContradictionPersistence(1980,1989,2,2,True,.5)
 target=plan_acquisition(regimes=(r,),bias_rows=(b,),contradiction_rows=(c,))[0]
 assert target.start_year==1980 and {"historical-bias","persistent-contestation"}<=set(target.reasons)
