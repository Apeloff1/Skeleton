from skeleton.ai.webcrawler.regimes import RegimeDetector
from skeleton.ai.webcrawler.historical_bias import HistoricalBiasAnalyzer
from skeleton.ai.webcrawler.regime_trajectory import classify_regime_transitions
def row(pos,neg,q=.8,r=.8,h=3,o=4):return {"positive":pos,"negative":neg,"mean_source_score":q,"mean_relevance":r,"distinct_hosts":h,"observations":o}
def test_detector_splits_large_polarity_change():
 s={2000:row(4,0),2001:row(4,0),2002:row(0,4),2003:row(0,4)}
 d=RegimeDetector(s);assert [x.year for x in d.change_points(threshold=.4)]==[2002]
 assert [(r.start_year,r.end_year) for r in d.regimes(threshold=.4)]==[(2000,2001),(2002,2003)]
def test_missing_years_split_regimes_without_fabricating_change_point():
 s={1990:row(3,0),1992:row(3,0)}
 d=RegimeDetector(s);assert not d.change_points()
 assert len(d.regimes())==2
def test_historical_bias_flags_sparse_concentrated_low_quality_bucket():
 s={1981:row(1,0,q=.2,h=1,o=5)}
 b=HistoricalBiasAnalyzer().analyze(s)[0]
 assert b.risk>.6 and {"sparse-year-coverage","source-concentration","low-source-quality"}<=set(b.reasons)
def test_trajectory_classifies_reversal():
 regs=RegimeDetector({2000:row(4,0),2001:row(0,4)}).regimes(threshold=.4)
 t=classify_regime_transitions(regs)
 assert t[-1].label=="reversed"
