from skeleton.automation.evidence_provenance import append
def test_chain_binds_previous():
 a=append("ci","1","a"*64);b=append("repair","2","b"*64,a);assert b.previous_sha256==a.digest()
