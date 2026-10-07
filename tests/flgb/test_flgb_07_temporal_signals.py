import unittest
from skeleton.ai.training.temporal_signals import TemporalSignalError,YearSignal,EraBoundary,assess_year_signals,require_signal_authority
D="a"*64
def sig(i,year,polarity=1,confidence=900000,valid=2030,observed=None):
 return YearSignal(f"s{i}","runtime-safety",year,observed or year,D,("%064x"%i)[-64:],confidence,polarity,valid,"primary")
class TestTemporalSignals(unittest.TestCase):
 def test_year_decay_is_deterministic(self):
  a=assess_year_signals((sig(1,2024),),policy_year=2026,subject="runtime-safety")
  self.assertEqual(a.support_ppm,729000)
  self.assertEqual(require_signal_authority(a),a.digest)
 def test_expired_signal_is_stale_not_rewritten_current(self):
  a=assess_year_signals((sig(1,2020,valid=2022),),policy_year=2026,subject="runtime-safety")
  self.assertEqual(a.support_ppm,0); self.assertEqual(a.stale_count,1)
 def test_future_observation_fails_closed(self):
  with self.assertRaisesRegex(TemporalSignalError,"future-observed"):
   assess_year_signals((sig(1,2025,observed=2027),),policy_year=2026,subject="runtime-safety")
 def test_cross_subject_contamination_fails(self):
  x=YearSignal("x","other",2026,2026,D,"b"*64,900000,1,2030,"primary")
  with self.assertRaisesRegex(TemporalSignalError,"cross-subject"):
   assess_year_signals((x,),policy_year=2026,subject="runtime-safety")
 def test_contradiction_is_explicit_and_blocks_authority(self):
  a=assess_year_signals((sig(1,2026,1),sig(2,2026,-1)),policy_year=2026,subject="runtime-safety")
  self.assertTrue(a.contradiction)
  with self.assertRaisesRegex(TemporalSignalError,"opposition|contradictory"):
   require_signal_authority(a)
 def test_duplicate_signal_identity_rejected(self):
  x=sig(1,2026)
  with self.assertRaisesRegex(TemporalSignalError,"duplicate signal id"):
   assess_year_signals((x,x),policy_year=2026,subject="runtime-safety")
 def test_regime_boundary_can_invalidate_pre_era_evidence(self):
  boundary=EraBoundary("post-architecture-break","runtime-safety",2025,"c"*64,0)
  a=assess_year_signals((sig(1,2024),sig(2,2026)),policy_year=2026,subject="runtime-safety",era_boundaries=(boundary,))
  self.assertEqual(a.support_ppm,900000)
 def test_regime_boundary_can_retain_fraction_of_prior_evidence(self):
  boundary=EraBoundary("migration-era","runtime-safety",2025,"c"*64,500000)
  a=assess_year_signals((sig(1,2024),),policy_year=2026,subject="runtime-safety",era_boundaries=(boundary,))
  self.assertEqual(a.support_ppm,364500)
 def test_future_regime_boundary_rejected(self):
  boundary=EraBoundary("future","runtime-safety",2027,"c"*64,0)
  with self.assertRaisesRegex(TemporalSignalError,"future era boundary"):
   assess_year_signals((sig(1,2026),),policy_year=2026,subject="runtime-safety",era_boundaries=(boundary,))
if __name__=="__main__": unittest.main()
