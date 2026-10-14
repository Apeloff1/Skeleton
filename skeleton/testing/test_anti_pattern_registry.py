from __future__ import annotations
import pytest
from skeleton.eval.antipatterns import *
def pattern():return AntiPattern("ANTIPATTERN.BROAD_EXCEPT","historically swallowed durable failures",r"except\\s+Exception\\s*:", "catch typed exceptions and preserve failure evidence")
def test_detector_emits_deterministic_location():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","x=1\nexcept Exception:\n pass");assert f[0].line==2 and f[0].pattern_id=="ANTIPATTERN.BROAD_EXCEPT"
def test_unexcepted_finding_remains_blocking():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","except Exception:");assert r.unresolved(f,(),10)==f
def test_active_exception_requires_owner_rationale_expiry_and_suppresses_exact_path():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","except Exception:");e=AntiPatternException(pattern().pattern_id,"a.py","OWNER.SECURITY","legacy boundary pending typed migration",20);assert r.unresolved(f,(e,),10)==()
def test_expired_exception_stops_suppressing():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","except Exception:");e=AntiPatternException(pattern().pattern_id,"a.py","OWNER.SECURITY","temporary",9);assert r.unresolved(f,(e,),10)==f
def test_exception_without_rationale_rejected():
 with pytest.raises(AntiPatternError):AntiPatternException(pattern().pattern_id,"a.py","OWNER.X","",10)
def test_invalid_detector_rejected():
 with pytest.raises(AntiPatternError,match="regex"):AntiPattern("ANTIPATTERN.X","history","[","alternative")

def test_duplicate_registry_identity_rejected():
 with pytest.raises(AntiPatternError,match="duplicate"):AntiPatternRegistry((pattern(),pattern()))
def test_unknown_exception_policy_rejected():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","except Exception:")
 e=AntiPatternException("ANTIPATTERN.UNKNOWN","a.py","OWNER.SECURITY","temporary",20)
 with pytest.raises(AntiPatternError,match="unknown"):r.unresolved(f,(e,),10)
def test_expiry_clock_rejects_boolean_alias():
 r=AntiPatternRegistry((pattern(),));f=r.scan("a.py","except Exception:")
 with pytest.raises(AntiPatternError,match="current_tick"):r.unresolved(f,(),True)
def test_exception_expiry_rejects_boolean_alias():
 with pytest.raises(AntiPatternError):AntiPatternException(pattern().pattern_id,"a.py","OWNER.X","temporary",True)
