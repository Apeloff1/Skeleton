import unittest
from skeleton.ai.training.temporal_signals import *
D="a"*64
def sig(i,year,polarity=1,confidence=900000,valid=2099,observed=None,subject="runtime-safety"):
 return YearSignal(f"s{i}",subject,year,observed or year,D,("%064x"%i)[-64:],confidence,polarity,valid,"primary")
class TestTemporalSignals(unittest.TestCase):
 def test_year_decay(self):
  a=assess_year_signals((sig(1,2024),),policy_year=2026,subject="runtime-safety")
  self.assertEqual(a.support_ppm,729000)
 def test_era_break_invalidates_prior_signal(self):
  b=EraBoundary("break","runtime-safety",2025,"c"*64,0)
  a=assess_year_signals((sig(1,2024),sig(2,2026)),policy_year=2026,subject="runtime-safety",era_boundaries=(b,))
  self.assertEqual(a.support_ppm,900000)
 def test_partial_era_retention(self):
  b=EraBoundary("migration","runtime-safety",2025,"c"*64,500000)
  a=assess_year_signals((sig(1,2024),),policy_year=2026,subject="runtime-safety",era_boundaries=(b,))
  self.assertEqual(a.support_ppm,364500)
 def test_decade_retention_compounds_by_decade_distance(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,3,"b"*64)
  a=assess_decade_signals((sig(1,2026),sig(2,2016),sig(3,2006)),policy=p,policy_year=2026)
  self.assertEqual(a.support_ppm,1000000)
  self.assertEqual(a.oldest_included_decade,2000)
 def test_decade_horizon_excludes_ancient_signal(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,1,"b"*64)
  a=assess_decade_signals((sig(1,2026),sig(2,2006)),policy=p,policy_year=2026)
  self.assertEqual(a.excluded_count,1); self.assertEqual(a.oldest_included_decade,2020)
 def test_decade_policy_cannot_run_in_wrong_decade(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,2,"b"*64)
  with self.assertRaisesRegex(TemporalSignalError,"outside policy decade"):
   assess_decade_signals((sig(1,2030),),policy=p,policy_year=2030)
 def test_future_decade_signal_fails_closed(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,2,"b"*64)
  with self.assertRaisesRegex(TemporalSignalError,"future-observed|future-decade"):
   assess_decade_signals((sig(1,2030,observed=2030),),policy=p,policy_year=2026)
 def test_observation_cannot_predate_event(self):
  with self.assertRaisesRegex(TemporalSignalError,"observation predates event"):
   sig(1,2030,observed=2026)
 def test_cross_subject_decade_contamination_fails(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,2,"b"*64)
  with self.assertRaisesRegex(TemporalSignalError,"cross-subject"):
   assess_decade_signals((sig(1,2026,subject="other"),),policy=p,policy_year=2026)
 def test_decade_contradiction_is_explicit(self):
  p=DecadePolicy("modern","runtime-safety",2020,1000000,2,"b"*64)
  a=assess_decade_signals((sig(1,2026,1),sig(2,2016,-1)),policy=p,policy_year=2026)
  self.assertTrue(a.contradiction)
  with self.assertRaises(TemporalSignalError): require_signal_authority(a)
 def test_expired_signal_excluded_from_decade_authority(self):
  p=DecadePolicy("modern","runtime-safety",2020,500000,2,"b"*64)
  a=assess_decade_signals((sig(1,2019,valid=2020),),policy=p,policy_year=2026)
  self.assertEqual(a.support_ppm,0); self.assertEqual(a.excluded_count,1)
 def test_future_observation_fails_closed(self):
  with self.assertRaisesRegex(TemporalSignalError,"future-observed"):
   assess_year_signals((sig(1,2025,observed=2027),),policy_year=2026,subject="runtime-safety")
 def test_cross_scale_consensus_uses_conservative_support_floor(self):
  signals=(sig(1,2026,confidence=800000),)
  y=assess_year_signals(signals,policy_year=2026,subject="runtime-safety")
  p=DecadePolicy("modern","runtime-safety",2020,500000,2,"b"*64)
  d=assess_decade_signals(signals,policy=p,policy_year=2026)
  x=reconcile_temporal_scales(y,d)
  self.assertEqual(x.support_floor_ppm,800000); self.assertEqual(require_consensus_authority(x),x.digest)
 def test_cross_scale_period_mismatch_fails(self):
  y=assess_year_signals((sig(1,2026),),policy_year=2026,subject="runtime-safety")
  p=DecadePolicy("old","runtime-safety",2010,500000,2,"b"*64)
  d=DecadeAssessment(2010,"runtime-safety",p.digest,(sig(2,2016).digest,),900000,0,0,2010,False)
  with self.assertRaisesRegex(TemporalSignalError,"period mismatch"): reconcile_temporal_scales(y,d)
if __name__=="__main__": unittest.main()
