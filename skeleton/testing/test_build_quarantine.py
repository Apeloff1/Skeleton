from skeleton.automation.build_quarantine import Quarantine
def test_quarantine_is_evidence_bound():assert len(Quarantine("trust","x","a"*40,"unsafe","b"*64).digest())==64
