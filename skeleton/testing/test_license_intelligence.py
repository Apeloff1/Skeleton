from skeleton.artifacts.license_intelligence import *
def test_unknown_license_fails_closed():assert not compatible((LicenseRecord("a","1",None,()),),True).compatible
def test_no_redistribution_obligation_blocks_distribution():assert not compatible((LicenseRecord("a","1","x",(LicenseObligation("no-redistribution","yes"),)),),True).compatible

def test_empty_record_set_not_declared_compatible():assert not compatible((),False).compatible
